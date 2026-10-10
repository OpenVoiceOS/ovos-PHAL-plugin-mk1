"""Shared helpers: build a ``MycroftMark1`` with the hardware stubbed out."""
from unittest.mock import MagicMock, patch

import pytest
from ovos_bus_client.message import Message


@pytest.fixture
def plugin_factory():
    """Return a builder for ``MycroftMark1`` with serial, reader and writer stubbed.

    ``config`` is what PHAL passes to the constructor. ``phal_config`` stands in
    for the ``PHAL`` section of mycroft.conf, which the plugin falls back to
    when PHAL hands it an empty block. The stubbed ``serial_for_url`` is kept
    on ``plugin.serial_opener`` so tests can check what port was opened.
    """
    def build(config=None, phal_config=None):
        from ovos_PHAL_plugin_mk1 import MycroftMark1

        bus = MagicMock()
        bus.wait_for_response.return_value = Message("resp", {"status": True})
        with patch("ovos_PHAL_plugin_mk1.serial") as fake_serial, \
             patch("ovos_PHAL_plugin_mk1.Configuration",
                   return_value={"PHAL": phal_config or {}}), \
             patch("ovos_PHAL_plugin_mk1.is_connected", return_value=True), \
             patch("ovos_PHAL_plugin_mk1.EnclosureReader"), \
             patch("ovos_PHAL_plugin_mk1.EnclosureWriter"):
            plugin = MycroftMark1(bus=bus, config=config)
        plugin.serial_opener = fake_serial.serial_for_url
        return plugin

    return build
