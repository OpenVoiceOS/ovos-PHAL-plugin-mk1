"""A dropped serial link must back off and reopen, not spin (#52).

``EnclosureReader.read`` caught every ``readline`` error and looped straight
back into it, logging thousands of lines a second and never touching the
port again. The faceplate stayed frozen on whatever it was showing until
PHAL was restarted.
"""
import threading
import time
from unittest.mock import MagicMock, patch

from ovos_bus_client.message import Message
from serial import SerialException

from ovos_PHAL_plugin_mk1.arduino import EnclosureReader

FOREVER = 10 ** 6


class FlakyPort:
    """``readline`` raises ``failures`` times, then behaves like a quiet port."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0
        self.recovered = threading.Event()

    def readline(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise SerialException("read failed: socket disconnected")
        self.recovered.set()
        time.sleep(0.01)
        return b""


def _reader(port, **kwargs):
    return EnclosureReader(port, MagicMock(), min_retry_delay=0.02,
                           max_retry_delay=0.08, **kwargs)


def test_read_errors_are_paced_not_spun():
    port = FlakyPort(failures=FOREVER)
    reader = _reader(port)

    time.sleep(0.3)
    reader.stop()

    # 0.02 + 0.04 + 0.08 + 0.08 ... fits a handful of retries in 0.3 s;
    # without the backoff this is tens of thousands
    assert port.calls < 50


def test_owner_is_asked_for_a_fresh_port_after_an_error():
    dead = FlakyPort(failures=FOREVER)
    fresh = FlakyPort(failures=0)
    reader = _reader(dead, reconnect_callback=lambda: fresh)

    assert fresh.recovered.wait(1.0), "the reader never moved to the reopened port"
    reader.stop()
    assert reader.serial is fresh


def test_a_failed_reopen_is_retried():
    dead = FlakyPort(failures=FOREVER)
    fresh = FlakyPort(failures=0)
    attempts = []

    def reopen():
        attempts.append(time.monotonic())
        if len(attempts) < 3:
            raise SerialException("could not open port")
        return fresh

    reader = _reader(dead, reconnect_callback=reopen)

    assert fresh.recovered.wait(1.0)
    reader.stop()
    assert len(attempts) == 3


def test_the_retry_delay_grows_then_resets_after_a_good_read():
    port = FlakyPort(failures=3)
    reader = _reader(port)

    assert port.recovered.wait(1.0)
    time.sleep(0.05)
    reader.stop()

    assert reader.retry_delay == reader.min_retry_delay


def test_stop_cuts_the_backoff_wait_short():
    port = FlakyPort(failures=FOREVER)
    reader = EnclosureReader(port, MagicMock(), min_retry_delay=5.0,
                             max_retry_delay=5.0)
    time.sleep(0.05)  # let it hit the first error and start waiting

    reader.stop()
    reader.join(timeout=1.0)

    assert not reader.is_alive()


def test_a_handler_error_does_not_trigger_a_reconnect():
    port = FlakyPort(failures=0)
    reopen = MagicMock()
    bus = MagicMock()
    bus.emit.side_effect = RuntimeError("bus is down")
    reader = EnclosureReader(port, bus, reconnect_callback=reopen,
                             min_retry_delay=0.02, max_retry_delay=0.08)
    reader.stop()

    reader._handle(b"Command: system.version")

    reopen.assert_not_called()


def test_reopen_swaps_the_port_for_both_threads_and_asks_the_version_again(
        plugin_factory):
    plugin = plugin_factory(config={"enabled": True, "port": "socket://127.0.0.1:5555"})
    dead = plugin.serial
    fresh = MagicMock(name="fresh port")

    with patch("ovos_PHAL_plugin_mk1.serial") as fake_serial:
        fake_serial.serial_for_url.return_value = fresh
        returned = plugin._reopen_serial()

    dead.close.assert_called_once_with()
    assert returned is fresh
    assert plugin.serial is fresh
    assert plugin.writer.serial is fresh
    assert plugin.writer.write.call_args_list[-1].args[0] == "system.version"


def test_the_reader_is_wired_to_the_reopen_hook(plugin_factory):
    plugin = plugin_factory(config={"enabled": True})

    kwargs = plugin.reader_factory.call_args.kwargs
    assert kwargs["reconnect_callback"] == plugin._reopen_serial


def test_the_reader_built_after_a_reflash_is_wired_too(plugin_factory):
    plugin = plugin_factory(config={"enabled": True, "timeout": 0.01}, admin=True)

    with patch("ovos_PHAL_plugin_mk1.os.geteuid", return_value=0), \
         patch("ovos_PHAL_plugin_mk1.build_and_flash"), \
         patch("ovos_PHAL_plugin_mk1.serial"), \
         patch("ovos_PHAL_plugin_mk1.EnclosureReader") as fake_reader, \
         patch("ovos_PHAL_plugin_mk1.EnclosureWriter"):
        plugin.handle_firmware_update(Message("enclosure.firmware.update"))

    assert fake_reader.call_args.kwargs["reconnect_callback"] == plugin._reopen_serial
