"""``enclosure.weather.display`` must send an icon the firmware can draw (#55).

``MycroftMouth::showIcon`` in the Mark 1 firmware copies at most 60
characters of a single icon message and refuses to draw when the declared
width needs more data than that. ``FaceplateGrid.encode()`` pads the 8x8
weather glyph to the full 32x8 plate (66 characters), so the icon never
appeared; only the temperature did. The classic skill sent the 8x8 codes
that each icon class still carries in ``encoded``.
"""
from unittest.mock import MagicMock

import pytest
from ovos_bus_client.message import Message
from ovos_mark1.faceplate.icons import (CloudyIcon, LightRainIcon, PartlyCloudyIcon,
                                        RainIcon, SnowIcon, StormIcon, SunnyIcon,
                                        WindIcon)

from ovos_PHAL_plugin_mk1 import MycroftMark1

SINGLE_ICON_LIMIT = 60
EIGHT_WIDE = "I"


def _plugin():
    plugin = MycroftMark1.__new__(MycroftMark1)
    plugin.bus = MagicMock()
    plugin.writer = MagicMock()
    return plugin


def _written(plugin):
    return [c.args[0] for c in plugin.writer.write.call_args_list]


def test_sunny_sends_the_8x8_code_the_classic_skill_sent():
    plugin = _plugin()

    plugin.on_weather_display(Message("enclosure.weather.display",
                                      {"img_code": 0, "temp": 72}))

    assert _written(plugin) == ["weather.display=72,x=2,IICEIBMDNLMDIBCEAA"]


@pytest.mark.parametrize("img_code, icon", enumerate([
    SunnyIcon, PartlyCloudyIcon, CloudyIcon, LightRainIcon,
    RainIcon, StormIcon, SnowIcon, WindIcon]))
def test_every_icon_fits_a_single_firmware_message(img_code, icon):
    plugin = _plugin()

    plugin.on_weather_display(Message("enclosure.weather.display",
                                      {"img_code": img_code, "temp": -10}))

    [command] = _written(plugin)
    payload = command.split("x=2,")[1]
    assert payload == icon.encoded
    assert payload[0] == EIGHT_WIDE
    assert len(payload) <= SINGLE_ICON_LIMIT


def test_a_numeric_string_code_is_accepted():
    plugin = _plugin()

    plugin.on_weather_display(Message("enclosure.weather.display",
                                      {"img_code": "6", "temp": 30}))

    assert _written(plugin) == [f"weather.display=30,x=2,{SnowIcon.encoded}"]


@pytest.mark.parametrize("data", [
    {"img_code": 8, "temp": 72},
    {"img_code": "fog", "temp": 72},
    {"temp": 72},
    {"img_code": 0},
])
def test_nothing_is_sent_without_a_known_icon_and_a_temperature(data):
    plugin = _plugin()

    plugin.on_weather_display(Message("enclosure.weather.display", data))

    assert _written(plugin) == []
