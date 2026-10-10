"""The firmware only answers a namespaced ``system.version`` (#54).

The Mark 1 firmware dispatches every command on its ``<namespace>.`` prefix,
so a bare ``version`` is echoed back and never answered. The plugin then
learns the firmware version only from the boot banner, and the
``enclosure.started`` event, which the reader emits on the echo of
``system.version``, never fires on real hardware.
"""
from unittest.mock import patch

from ovos_bus_client.message import Message


def _written(plugin):
    return [c.args[0] for c in plugin.writer.write.call_args_list]


def test_startup_asks_with_the_command_the_firmware_dispatches(plugin_factory):
    plugin = plugin_factory(config={"enabled": True})

    assert "system.version" in _written(plugin)
    assert "version" not in _written(plugin)


def test_reflash_asks_again_with_the_same_command(plugin_factory):
    plugin = plugin_factory(config={"enabled": True, "timeout": 0.01}, admin=True)

    with patch("ovos_PHAL_plugin_mk1.os.geteuid", return_value=0), \
         patch("ovos_PHAL_plugin_mk1.build_and_flash"), \
         patch("ovos_PHAL_plugin_mk1.serial"), \
         patch("ovos_PHAL_plugin_mk1.EnclosureReader"), \
         patch("ovos_PHAL_plugin_mk1.EnclosureWriter"):
        plugin.handle_firmware_update(Message("enclosure.firmware.update"))

    assert _written(plugin) == ["system.version"]
