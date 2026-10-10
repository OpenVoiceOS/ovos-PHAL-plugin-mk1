"""Shared helpers: build a ``MycroftMark1`` with the hardware stubbed out."""
from unittest.mock import MagicMock, patch

import pytest
from ovos_bus_client.message import Message


@pytest.fixture
def plugin_factory():
    """Return a builder for ``MycroftMark1`` with serial, reader and writer stubbed.

    ``admin`` builds the root-mode variant instead.
    ``config`` is what PHAL passes to the constructor. ``phal_config`` stands in
    for the ``PHAL`` section of mycroft.conf, which the plugin falls back to
    when PHAL hands it an empty block. The stubbed ``serial_for_url`` is kept
    on ``plugin.serial_opener`` so tests can check what port was opened, and
    the stubbed ``EnclosureReader`` class on ``plugin.reader_factory``.
    """
    def build(config=None, phal_config=None, admin=False):
        from ovos_PHAL_plugin_mk1 import MycroftMark1, MycroftMark1AdminPlugin

        plugin_class = MycroftMark1AdminPlugin if admin else MycroftMark1
        bus = MagicMock()
        bus.wait_for_response.return_value = Message("resp", {"status": True})
        with patch("ovos_PHAL_plugin_mk1.serial") as fake_serial, \
             patch("ovos_PHAL_plugin_mk1.Configuration",
                   return_value={"PHAL": phal_config or {}}), \
             patch("ovos_PHAL_plugin_mk1.is_connected", return_value=True), \
             patch("ovos_PHAL_plugin_mk1.EnclosureReader") as fake_reader, \
             patch("ovos_PHAL_plugin_mk1.EnclosureWriter"):
            plugin = plugin_class(bus=bus, config=config)
        plugin.serial_opener = fake_serial.serial_for_url
        plugin.reader_factory = fake_reader
        return plugin

    return build
