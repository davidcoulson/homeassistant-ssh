import asyncio
from functools import wraps
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from source import definitions


class SensorEntity:
    def __init__(self, entity_id, coordinator):
        self.entity_id = self.name = self.key = entity_id
        self.coordinator = coordinator


@pytest.fixture
def services():
    registered = {}
    entries = {}
    entities = []
    for host in ("a", "b"):
        coordinator = object()
        entries[host] = NS(
            state_coordinator=coordinator,
            manager=NS(
                async_set_sensor_values=AsyncMock(return_value=([], [None, None])),
                async_poll_sensors=AsyncMock(return_value=([], [None, None])),
            ),
        )
        for index in (1, 2):
            entities.append(SensorEntity(f"text.{host}{index}", coordinator))
    hass = NS(
        data={"ssh": entries},
        services=NS(
            async_register=lambda domain, name, handler, *args: registered.update(
                {name: handler}
            )
        ),
    )

    async def extract_entries(call):
        return list(
            dict.fromkeys(
                entity_id.split(".")[1][0] for entity_id in call.data["entity_id"]
            )
        )

    # HA 2026.10 signature; deliberately returns platform order, not target order.
    async def extract_entities(candidates, call, expand_group=True):
        return [
            entity
            for entity in candidates
            if entity.entity_id in call.data["entity_id"]
        ]

    constants = {
        key: key.removeprefix("SERVICE_")
        .removeprefix("CONF_")
        .removeprefix("ATTR_")
        .lower()
        for key in (
            "SERVICE_SET_VALUE",
            "SERVICE_POLL_SENSOR",
            "SERVICE_EXECUTE_COMMAND",
            "SERVICE_RUN_ACTION",
            "SERVICE_TURN_ON",
            "SERVICE_TURN_OFF",
            "SERVICE_RESTART",
            "ATTR_ENTITY_ID",
            "CONF_VALUES",
        )
    }
    ns = definitions(
        "__init__.py",
        ["async_register_services"],
        {
            **constants,
            "asyncio": asyncio,
            "wraps": wraps,
            "BaseSensorEntity": SensorEntity,
            "ServiceValidationError": vol.Invalid,
            "SET_VALUE_SCHEMA": None,
            "EXECUTE_COMMAND_SCHEMA": None,
            "RUN_ACTION_SCHEMA": None,
            "SupportsResponse": NS(OPTIONAL=None),
            "async_extract_config_entry_ids": extract_entries,
            "async_extract_entities": extract_entities,
            "entity_platform": NS(
                async_get_platforms=lambda *args: [
                    NS(entities={e.entity_id: e for e in entities})
                ]
            ),
        },
    )
    ns["async_register_services"](hass, "ssh")
    return registered, entries


@pytest.mark.asyncio
async def test_poll_uses_current_helper_signature(services):
    handlers, entries = services
    await handlers["poll_sensor"](
        NS(data={"entity_id": ["text.a1"]}, return_response=True)
    )
    entries["a"].manager.async_poll_sensors.assert_awaited_once_with(
        ["text.a1"], raise_errors=False
    )


@pytest.mark.asyncio
async def test_values_follow_targets_across_hosts_and_platform_order(services):
    handlers, entries = services
    await handlers["set_value"](
        NS(
            data={
                "entity_id": ["text.b2", "text.a2", "text.a1"],
                "values": ["B2", "A2", "A1"],
            },
            return_response=True,
        )
    )
    entries["a"].manager.async_set_sensor_values.assert_awaited_once_with(
        ["text.a1", "text.a2"], ["A1", "A2"], raise_errors=False
    )
    entries["b"].manager.async_set_sensor_values.assert_awaited_once_with(
        ["text.b2"], ["B2"], raise_errors=False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "targets,values",
    [
        (["text.a1"], []),
        (["text.a1"], ["x", "y"]),
        (["text.a1", "text.a1"], ["x", "y"]),
        (["text.a1", "text.missing"], ["x", "y"]),
    ],
)
async def test_invalid_mapping_fails_before_any_write(services, targets, values):
    handlers, entries = services
    with pytest.raises(vol.Invalid):
        await handlers["set_value"](
            NS(data={"entity_id": targets, "values": values}, return_response=False)
        )
    for entry in entries.values():
        entry.manager.async_set_sensor_values.assert_not_awaited()
