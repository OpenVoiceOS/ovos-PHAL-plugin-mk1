"""Helpers to build and flash the Mark 1 faceplate firmware on-device.

There is no prebuilt firmware binary published anywhere for the faceplate
Arduino any more (the old S3 bucket the upstream ``publish.sh`` script used
to upload to is gone), so the only way to get a given firmware version onto
the board is to clone the source and build it locally with PlatformIO before
flashing it with avrdude.
"""
import os
import shutil
import subprocess
from os.path import join, isdir
from typing import Callable, Optional

from ovos_utils.log import LOG
from ovos_utils.xdg_utils import xdg_cache_home

FIRMWARE_REPO_URL = "https://github.com/OpenVoiceOS/mycroft-mark1-firmware"
SUPPORTED_FIRMWARE_VERSION = "1.4.2"
FIRMWARE_TAG = f"v{SUPPORTED_FIRMWARE_VERSION}"
PIO_ENV = "pro16MHzatmega328"
AVRDUDE_PARTNO = "atmega328p"
AVRDUDE_PROGRAMMER = "linuxgpio"


class FirmwareUpdateError(RuntimeError):
    """Raised when any step of the on-device build/flash sequence fails."""


def _run(cmd, cwd=None, progress: Optional[Callable[[str, str], None]] = None,
         step: str = ""):
    LOG.info(f"firmware update - running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    log = (proc.stdout or "") + (proc.stderr or "")
    if progress:
        progress(step, log)
    if proc.returncode != 0:
        raise FirmwareUpdateError(
            f"'{' '.join(cmd)}' failed with code {proc.returncode}: {log}")
    return log


def get_firmware_repo_path() -> str:
    return join(xdg_cache_home(), "ovos-PHAL-plugin-mk1", "mycroft-mark1-firmware")


def fetch_firmware_source(tag: str = FIRMWARE_TAG,
                          progress: Optional[Callable[[str, str], None]] = None) -> str:
    """Clone (or update) the firmware source into an XDG cache dir and
    check out the requested tag. Returns the path to the checkout."""
    repo_path = get_firmware_repo_path()
    if not isdir(join(repo_path, ".git")):
        os.makedirs(os.path.dirname(repo_path), exist_ok=True)
        if isdir(repo_path):
            shutil.rmtree(repo_path)
        _run(["git", "clone", FIRMWARE_REPO_URL, repo_path],
             progress=progress, step="clone")
    else:
        _run(["git", "fetch", "--all", "--tags"], cwd=repo_path,
             progress=progress, step="fetch")
    _run(["git", "checkout", tag], cwd=repo_path,
         progress=progress, step="checkout")
    return repo_path


def build_firmware(repo_path: str,
                   progress: Optional[Callable[[str, str], None]] = None) -> str:
    """Build the firmware with PlatformIO, returns the path to the built hex."""
    if shutil.which("pio") is None:
        raise FirmwareUpdateError(
            "PlatformIO ('pio') is not installed/importable, "
            "install it to build the mk1 firmware")
    _run(["pio", "run", "-e", PIO_ENV], cwd=repo_path,
         progress=progress, step="build")
    hex_path = join(repo_path, ".pio", "build", PIO_ENV, "firmware.hex")
    if not os.path.isfile(hex_path):
        raise FirmwareUpdateError(
            f"PlatformIO build did not produce {hex_path}")
    return hex_path


def flash_firmware(repo_path: str, hex_path: str,
                   progress: Optional[Callable[[str, str], None]] = None):
    """Flash the built hex with avrdude, using the firmware repo's own
    avrdude config for the GPIO bit-bang programmer."""
    if os.geteuid() != 0:
        raise FirmwareUpdateError("flashing the faceplate requires root")
    avrdude_conf = join(repo_path, "avrdude-gpio.conf")
    if not os.path.isfile(avrdude_conf):
        raise FirmwareUpdateError(f"missing avrdude config: {avrdude_conf}")
    _run(["sudo", "avrdude", "-p", AVRDUDE_PARTNO, "-C", avrdude_conf,
         "-c", AVRDUDE_PROGRAMMER, "-v",
         "-U", f"flash:w:{hex_path}"],
         progress=progress, step="flash")


def build_and_flash(tag: str = FIRMWARE_TAG,
                    progress: Optional[Callable[[str, str], None]] = None):
    """Full on-device build + flash sequence. Raises FirmwareUpdateError on
    any failure."""
    if os.geteuid() != 0:
        raise FirmwareUpdateError("firmware update requires root")
    repo_path = fetch_firmware_source(tag, progress=progress)
    hex_path = build_firmware(repo_path, progress=progress)
    flash_firmware(repo_path, hex_path, progress=progress)
