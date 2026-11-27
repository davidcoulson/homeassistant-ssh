import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
from source import definitions
from ssh_terminal_manager import Sensor


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["refresh", "device_info", "platforms", "cancel"])
async def test_failed_setup_rolls_back_and_shutdown_is_idempotent(stage):
    entry_cls = definitions(
        "entry_data.py", ["EntryData"], {"dataclass": dataclass, "field": field}
    )["EntryData"]
    sensor = Sensor(key="device")
    manager = NS(
        name="host",
        sensor_commands=[object()],
        sensors_by_key={"device": sensor},
        async_reset=AsyncMock(),
    )
    state = NS(async_config_entry_first_refresh=AsyncMock(), async_shutdown=AsyncMock())
    command = NS(async_shutdown=AsyncMock())
    if stage in ("refresh", "cancel"):
        state.async_config_entry_first_refresh.side_effect = (
            asyncio.CancelledError() if stage == "cancel" else RuntimeError("refresh")
        )
    device_info = Mock(return_value={})
    if stage == "device_info":
        device_info.side_effect = RuntimeError("device_info")
    forward = AsyncMock()
    if stage == "platforms":
        forward.side_effect = RuntimeError("platforms")
    entry = NS(
        domain="ssh",
        entry_id="entry",
        unique_id="unique",
        options={"update_interval": 30},
        async_on_unload=Mock(),
        add_update_listener=Mock(),
    )
    hass = NS(data={}, config_entries=NS(async_forward_entry_setups=forward))
    stored = []

    def make_entry(*args):
        result = entry_cls(*args)
        stored.append(result)
        return result

    ns = definitions(
        "__init__.py",
        ["async_initialize_entry"],
        {
            "StateCoordinator": lambda *args: state,
            "SensorCommandCoordinator": lambda *args: command,
            "EntryData": make_entry,
            "CONF_UPDATE_INTERVAL": "update_interval",
            "DEVICE_SENSOR_KEYS": ["device"],
            "async_reload_entry": Mock(),
            "dr": NS(async_get=lambda *args: NS(async_get_or_create=Mock())),
            "get_device_info": device_info,
            "get_device_sensor_update_handler": Mock(return_value=Mock()),
            "_LOGGER": Mock(),
        },
    )
    with pytest.raises(asyncio.CancelledError if stage == "cancel" else RuntimeError):
        await ns["async_initialize_entry"](hass, entry, manager, [])
    assert hass.data["ssh"] == {}
    manager.async_reset.assert_awaited_once()
    state.async_shutdown.assert_awaited_once()
    command.async_shutdown.assert_awaited_once()
    assert sensor.on_update._subscribers == []
    await stored[0].async_shutdown()
    manager.async_reset.assert_awaited_once()
