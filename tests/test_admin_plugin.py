import unittest
from unittest.mock import patch, MagicMock

from ovos_bus_client.message import Message

from ovos_PHAL_plugin_mk1 import MycroftMark1AdminPlugin
from ovos_PHAL_plugin_mk1.firmware import FirmwareUpdateError


def _make_plugin():
    bus = MagicMock()
    bus.wait_for_response.return_value = Message("resp", {"status": True})
    with patch("ovos_PHAL_plugin_mk1.serial"), \
         patch("ovos_PHAL_plugin_mk1.is_connected", return_value=True), \
         patch("ovos_PHAL_plugin_mk1.EnclosureReader"), \
         patch("ovos_PHAL_plugin_mk1.EnclosureWriter"):
        plugin = MycroftMark1AdminPlugin(bus=bus, config={
            "port": "/dev/null", "rate": 9600, "timeout": 0.01
        })
    return plugin, bus


class TestFirmwareUpdateHandler(unittest.TestCase):
    def test_refuses_without_root(self):
        plugin, bus = _make_plugin()
        with patch("ovos_PHAL_plugin_mk1.os.geteuid", return_value=1000):
            plugin.handle_firmware_update(Message("enclosure.firmware.update"))

        emitted = [c.args[0] for c in bus.emit.call_args_list]
        failed = [m for m in emitted if m.msg_type == "enclosure.firmware.update.failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("root", failed[0].data["error"])

    def test_serial_restored_when_build_raises(self):
        plugin, bus = _make_plugin()
        old_reader = plugin.reader
        old_writer = plugin.writer

        with patch("ovos_PHAL_plugin_mk1.os.geteuid", return_value=0), \
             patch("ovos_PHAL_plugin_mk1.build_and_flash",
                   side_effect=FirmwareUpdateError("pio not found")), \
             patch("ovos_PHAL_plugin_mk1.serial"), \
             patch("ovos_PHAL_plugin_mk1.EnclosureReader"), \
             patch("ovos_PHAL_plugin_mk1.EnclosureWriter"):
            plugin.handle_firmware_update(Message("enclosure.firmware.update"))

        # a fresh reader/writer pair must have been created, serial reopened
        self.assertIsNotNone(plugin.reader)
        self.assertIsNotNone(plugin.writer)
        self.assertIsNot(plugin.reader, old_reader)
        self.assertIsNot(plugin.writer, old_writer)

        emitted = [c.args[0] for c in bus.emit.call_args_list]
        failed = [m for m in emitted if m.msg_type == "enclosure.firmware.update.failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].data["error"], "pio not found")
        self.assertFalse(
            any(m.msg_type == "enclosure.firmware.update.complete" for m in emitted))

    def test_reports_version_on_success(self):
        plugin, bus = _make_plugin()

        stub_reader = MagicMock()
        stub_reader.firmware_version = "1.4.2"

        with patch("ovos_PHAL_plugin_mk1.os.geteuid", return_value=0), \
             patch("ovos_PHAL_plugin_mk1.build_and_flash"), \
             patch("ovos_PHAL_plugin_mk1.serial"), \
             patch("ovos_PHAL_plugin_mk1.EnclosureReader", return_value=stub_reader), \
             patch("ovos_PHAL_plugin_mk1.EnclosureWriter"):
            plugin.handle_firmware_update(Message("enclosure.firmware.update"))

        emitted = [c.args[0] for c in bus.emit.call_args_list]
        complete = [m for m in emitted if m.msg_type == "enclosure.firmware.update.complete"]
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0].data["version"], "1.4.2")


if __name__ == "__main__":
    unittest.main()
