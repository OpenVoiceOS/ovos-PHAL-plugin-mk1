import os
import unittest
from unittest.mock import patch, MagicMock

from ovos_PHAL_plugin_mk1.firmware import build_and_flash, flash_firmware, \
    FirmwareUpdateError


class TestBuildAndFlashRoot(unittest.TestCase):
    @patch("ovos_PHAL_plugin_mk1.firmware.os.geteuid", return_value=1000)
    def test_build_and_flash_refuses_without_root(self, _geteuid):
        with self.assertRaises(FirmwareUpdateError):
            build_and_flash()

    @patch("ovos_PHAL_plugin_mk1.firmware.os.geteuid", return_value=1000)
    def test_flash_firmware_refuses_without_root(self, _geteuid):
        with self.assertRaises(FirmwareUpdateError):
            flash_firmware("/some/repo", "/some/repo/firmware.hex")

    @patch("ovos_PHAL_plugin_mk1.firmware.flash_firmware")
    @patch("ovos_PHAL_plugin_mk1.firmware.build_firmware")
    @patch("ovos_PHAL_plugin_mk1.firmware.fetch_firmware_source")
    @patch("ovos_PHAL_plugin_mk1.firmware.os.geteuid", return_value=0)
    def test_build_and_flash_runs_full_sequence_as_root(
            self, _geteuid, fetch, build, flash):
        fetch.return_value = "/cache/mycroft-mark1-firmware"
        build.return_value = "/cache/mycroft-mark1-firmware/firmware.hex"

        build_and_flash("v1.4.2")

        fetch.assert_called_once()
        build.assert_called_once_with("/cache/mycroft-mark1-firmware", progress=None)
        flash.assert_called_once_with(
            "/cache/mycroft-mark1-firmware",
            "/cache/mycroft-mark1-firmware/firmware.hex", progress=None)


if __name__ == "__main__":
    unittest.main()
