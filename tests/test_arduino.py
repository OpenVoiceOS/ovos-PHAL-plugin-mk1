import unittest
from unittest.mock import MagicMock

from ovos_PHAL_plugin_mk1.arduino import EnclosureReader, FIRMWARE_VERSION_RE


class TestFirmwareVersionParsing(unittest.TestCase):
    def setUp(self):
        self.serial = MagicMock()
        self.bus = MagicMock()
        # EnclosureReader.__init__ starts the thread, stop it right away so
        # only .process() is exercised directly in these tests
        self.reader = EnclosureReader(self.serial, self.bus)
        self.reader.stop()

    def test_version_reply_is_parsed(self):
        self.reader.process("Mycroft Mark 1 v1.4.2")
        self.assertEqual(self.reader.firmware_version, "1.4.2")

    def test_boot_banner_is_parsed(self):
        self.reader.process("Mycroft Mark 1 v1.4.2 - Connected")
        self.assertEqual(self.reader.firmware_version, "1.4.2")

    def test_version_reply_emits_bus_message(self):
        self.reader.process("Mycroft Mark 1 v1.4.2")
        emitted = [c.args[0] for c in self.bus.emit.call_args_list]
        version_msgs = [m for m in emitted if m.msg_type == "enclosure.firmware.version"]
        self.assertEqual(len(version_msgs), 1)
        self.assertEqual(version_msgs[0].data["version"], "1.4.2")

    def test_older_version_string_is_parsed(self):
        self.reader.process("Mycroft Mark 1 v0.1.9")
        self.assertEqual(self.reader.firmware_version, "0.1.9")

    def test_junk_does_not_set_version(self):
        self.reader.process("garbage line from the serial buffer")
        self.assertIsNone(self.reader.firmware_version)

    def test_unrelated_command_reply_does_not_set_version(self):
        self.reader.process("Command: system.version")
        self.assertIsNone(self.reader.firmware_version)

    def test_regex_directly_rejects_malformed_version(self):
        self.assertIsNone(FIRMWARE_VERSION_RE.search("Mycroft Mark 1 v1.4"))
        self.assertIsNone(FIRMWARE_VERSION_RE.search("Mycroft Mark 2 v1.4.2"))

    def test_system_version_reply_still_emits_enclosure_started(self):
        self.reader.process("Command: system.version")
        emitted = [c.args[0] for c in self.bus.emit.call_args_list]
        self.assertTrue(any(m.msg_type == "enclosure.started" for m in emitted))


if __name__ == "__main__":
    unittest.main()
