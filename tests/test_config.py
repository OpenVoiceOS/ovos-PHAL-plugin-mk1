"""The plugin must honour the config block PHAL actually hands it (#53).

PHAL looks plugins up by entry-point name (``ovos-phal-mk1``) and passes that
block to both the validator and the constructor. Older configs used the
package name (``ovos-PHAL-plugin-mk1``); in that case PHAL passes an empty
dict and the plugin has to find the block itself. Either way one key must be
enough, and ``port`` must never silently fall back to ``/dev/ttyAMA0``.
"""
from unittest.mock import patch

import pytest

from ovos_PHAL_plugin_mk1 import MycroftMark1Validator

SOCKET_PORT = "socket://127.0.0.1:5555"
ENABLED = {"enabled": True, "port": SOCKET_PORT}
CONFIG_KEYS = ["ovos-phal-mk1", "ovos-PHAL-plugin-mk1"]


def _validate(config, phal_config, on_hardware=False):
    with patch("ovos_PHAL_plugin_mk1.Configuration",
               return_value={"PHAL": phal_config}), \
         patch("ovos_PHAL_plugin_mk1.is_mark_1", return_value=on_hardware):
        return MycroftMark1Validator.validate(config)


def test_validator_accepts_the_block_phal_passes():
    assert _validate(ENABLED, {}) is True


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_validator_finds_either_key_when_phal_passes_an_empty_block(key):
    assert _validate({}, {key: ENABLED}) is True


def test_validator_declines_off_hardware_without_config():
    assert _validate({}, {}) is False


def test_validator_still_accepts_real_hardware_without_config():
    assert _validate({}, {}, on_hardware=True) is True


def test_port_comes_from_the_block_phal_passes(plugin_factory):
    plugin = plugin_factory(config=ENABLED)

    assert plugin.port == SOCKET_PORT
    plugin.serial_opener.assert_called_once_with(
        url=SOCKET_PORT, baudrate=9600, timeout=5.0)


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_port_comes_from_the_config_file_when_phal_passes_an_empty_block(
        plugin_factory, key):
    plugin = plugin_factory(config={}, phal_config={key: ENABLED})

    assert plugin.port == SOCKET_PORT


def test_defaults_fill_in_missing_serial_settings(plugin_factory):
    plugin = plugin_factory(config={"enabled": True})

    assert (plugin.port, plugin.rate, plugin.timeout) == ("/dev/ttyAMA0", 9600, 5.0)
