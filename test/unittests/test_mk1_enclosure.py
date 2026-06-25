"""Unit tests for the Mark-1 PHAL plugin's enclosure-protocol wiring.

ovos-plugin-manager dropped the baked-in enclosure.* abstraction, so
MycroftMark1 now mixes in EnclosureProtocolListener from
ovos-ui-enclosure-protocol. These tests verify the mix-in resolves correctly
and that the hardware handlers drive the faceplate writer.

The Mark-1 hardware modules (pyserial, ovos_mark1, ovos_i2c_detection) are not
available in CI, so they are stubbed at import time. The plugin is built with
``__new__`` to bypass the real serial connection in ``__init__``.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock


def _stub_hardware_modules():
    """Install lightweight stubs for the Mark-1-only runtime dependencies."""
    sys.modules.setdefault("serial", MagicMock())

    i2c = types.ModuleType("ovos_i2c_detection")
    i2c.is_mark_1 = lambda: False
    sys.modules["ovos_i2c_detection"] = i2c

    mark1 = types.ModuleType("ovos_mark1")
    faceplate = types.ModuleType("ovos_mark1.faceplate")
    icons = types.ModuleType("ovos_mark1.faceplate.icons")
    for name in ("MusicIcon", "WarningIcon", "SnowIcon", "StormIcon",
                 "SunnyIcon", "CloudyIcon", "PartlyCloudyIcon", "WindIcon",
                 "RainIcon", "LightRainIcon"):
        setattr(icons, name, MagicMock())
    sys.modules.update({
        "ovos_mark1": mark1,
        "ovos_mark1.faceplate": faceplate,
        "ovos_mark1.faceplate.icons": icons,
    })


_stub_hardware_modules()

from ovos_PHAL_plugin_mk1 import MycroftMark1  # noqa: E402
from ovos_ui_enclosure_protocol import EnclosureProtocolListener  # noqa: E402


def _make_plugin() -> MycroftMark1:
    """Build a MycroftMark1 without opening a real serial port."""
    plugin = MycroftMark1.__new__(MycroftMark1)
    plugin.bus = MagicMock()
    plugin.writer = MagicMock()
    plugin._current_rgb = [(0, 0, 0)] * 24
    plugin._num_pixels = 24
    return plugin


class TestMk1ListenerMixin(unittest.TestCase):
    def test_mixes_in_enclosure_protocol_listener(self):
        self.assertIn(EnclosureProtocolListener, MycroftMark1.__mro__)

    def test_protocol_helpers_come_from_the_listener(self):
        for method in ("register_enclosure_namespace",
                       "shutdown_enclosure_namespace",
                       "_activate_mouth_events",
                       "_deactivate_mouth_events",
                       "mouth_events_active"):
            owner = next(c.__name__ for c in MycroftMark1.__mro__
                         if method in c.__dict__)
            self.assertEqual(owner, "EnclosureProtocolListener", method)


class TestMk1EnclosureWiring(unittest.TestCase):
    def setUp(self):
        self.plugin = _make_plugin()
        self.plugin.register_enclosure_namespace()
        self.wired = {call.args[0] for call in self.plugin.bus.on.call_args_list}

    def test_wires_enclosure_namespace(self):
        self.assertTrue({"enclosure.eyes.color",
                         "enclosure.mouth.text",
                         "enclosure.system.blink"} <= self.wired)

    def test_no_core_lifecycle_wired_here(self):
        # register_core_events lives in PHALPlugin, not this call
        self.assertFalse(any(t.startswith("recognizer_loop:") for t in self.wired))

    def test_eyes_handler_drives_faceplate(self):
        self.plugin.on_eyes_on()
        self.plugin.writer.write.assert_called_with("eyes.on")

    def test_color_handler_encodes_rgb(self):
        from ovos_bus_client.message import Message
        self.plugin.on_eyes_color(Message("enclosure.eyes.color",
                                          {"r": 0, "g": 1, "b": 2}))
        self.plugin.writer.write.assert_called_with("eyes.color=" + str((0 * 65536) + (1 * 256) + 2))


class TestMk1MouthGating(unittest.TestCase):
    def test_mouth_events_toggle(self):
        plugin = _make_plugin()
        plugin._activate_mouth_events()
        self.assertTrue(plugin.mouth_events_active)
        plugin._deactivate_mouth_events()
        self.assertFalse(plugin.mouth_events_active)


if __name__ == "__main__":
    unittest.main()
