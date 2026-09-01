"""The eye-colour readback must actually be reachable.

`handle_get_color` is the only thing the faceplate can be *asked*, rather than
told. It was defined and never bound, so it answered nothing: a caller wanting
to know what the eyes are showing saw silence, which is indistinguishable from
no Mark 1 being present at all.
"""
from unittest.mock import Mock

from ovos_utils.fakebus import FakeBus


def _plugin():
    from ovos_PHAL_plugin_mk1 import MycroftMark1

    bus = FakeBus()
    plugin = MycroftMark1.__new__(MycroftMark1)
    plugin.bus = bus
    plugin._current_rgb = [(1, 2, 3)] * 24
    return plugin, bus


def test_asking_what_the_eyes_show_gets_an_answer():
    from ovos_bus_client.message import Message

    plugin, bus = _plugin()
    bus.on("enclosure.eyes.rgb.get", plugin.handle_get_color)

    seen = []
    bus.on("enclosure.eyes.rgb", lambda m: seen.append(m.data))
    bus.emit(Message("enclosure.eyes.rgb.get"))

    assert seen, "nothing answered the only readback the faceplate offers"
    assert seen[0]["pixels"] == [(1, 2, 3)] * 24


def test_the_readback_is_registered_at_startup():
    """The handler existing is not the same as it being reachable."""
    import inspect

    from ovos_PHAL_plugin_mk1 import MycroftMark1

    source = inspect.getsource(MycroftMark1)
    assert 'self.bus.on("enclosure.eyes.rgb.get"' in source, (
        "handle_get_color is defined but never bound, so it answers nothing"
    )
