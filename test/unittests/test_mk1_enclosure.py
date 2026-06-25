"""Unit tests for the Mark-1 PHAL plugin's enclosure-protocol wiring.

ovos-plugin-manager dropped the baked-in enclosure abstraction, so MycroftMark1
now **instantiates** an EnclosureProtocolListener (composition) and routes the
enclosure.* commands + record/speak/wake/sleep lifecycle to its own handlers
via callbacks.

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


def _bare_plugin() -> MycroftMark1:
    """A MycroftMark1 with just enough state for the enclosure handlers."""
    plugin = MycroftMark1.__new__(MycroftMark1)
    plugin.bus = MagicMock()
    plugin.writer = MagicMock()
    plugin._current_rgb = [(0, 0, 0)] * 24
    plugin._num_pixels = 24
    plugin.speaking = False
    plugin.listening = False
    return plugin


def _wire(plugin, bus):
    """Wire a listener with the plugin's handlers as __init__ does."""
    return EnclosureProtocolListener(
        bus=bus,
        on_no_internet=plugin.on_no_internet,
        on_reset=plugin.on_reset,
        on_system_blink=plugin.on_system_blink,
        on_eyes_on=plugin.on_eyes_on,
        on_eyes_color=plugin.on_eyes_color,
        on_talk=plugin.on_talk,
        on_text=plugin.on_text,
        on_record_begin=plugin.on_record_begin,
        on_audio_output_start=plugin.on_audio_output_start,
        on_awoken=plugin.on_awake,
    )


class FakeBus:
    def __init__(self):
        self.handlers = {}

    def on(self, msg_type, cb):
        self.handlers.setdefault(msg_type, []).append(cb)

    def remove(self, msg_type, cb):
        self.handlers.get(msg_type, []).remove(cb)

    def emit_event(self, msg_type, message=None):
        for cb in list(self.handlers.get(msg_type, [])):
            cb(message)


class TestMk1UsesComposition(unittest.TestCase):
    def test_does_not_subclass_the_listener(self):
        """The plugin composes the listener; it must not inherit it."""
        self.assertNotIn(EnclosureProtocolListener, MycroftMark1.__mro__)

    def test_listener_routes_enclosure_command_to_writer(self):
        from ovos_bus_client.message import Message
        plugin = _bare_plugin()
        bus = FakeBus()
        plugin.enclosure = _wire(plugin, bus)
        bus.emit_event("enclosure.eyes.on")
        plugin.writer.write.assert_called_with("eyes.on")
        bus.emit_event("enclosure.eyes.color",
                       Message("enclosure.eyes.color", {"r": 0, "g": 1, "b": 2}))
        plugin.writer.write.assert_called_with("eyes.color=" + str((1 * 256) + 2))

    def test_listener_routes_core_lifecycle_to_writer(self):
        plugin = _bare_plugin()
        bus = FakeBus()
        plugin.enclosure = _wire(plugin, bus)
        bus.emit_event("recognizer_loop:record_begin")  # on_record_begin -> on_listen
        plugin.writer.write.assert_called_with("mouth.listen")
        self.assertTrue(plugin.listening)


class TestMk1MouthGating(unittest.TestCase):
    def test_audio_output_start_respects_gating(self):
        plugin = _bare_plugin()
        bus = FakeBus()
        plugin.enclosure = _wire(plugin, bus)

        # gating off: on_audio_output_start must not drive a talk animation
        plugin.enclosure.deactivate_mouth_events()
        bus.emit_event("recognizer_loop:audio_output_start")
        self.assertTrue(plugin.speaking)
        talk_calls = [c for c in plugin.writer.write.call_args_list
                      if c.args and c.args[0] == "mouth.talk"]
        self.assertEqual(talk_calls, [])

        # gating on: now it drives the talk animation
        plugin.enclosure.activate_mouth_events()
        bus.emit_event("recognizer_loop:audio_output_start")
        plugin.writer.write.assert_called_with("mouth.talk")


if __name__ == "__main__":
    unittest.main()
