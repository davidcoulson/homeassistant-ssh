from types import SimpleNamespace as NS

import pytest
from source import definitions
from ssh_terminal_manager import VersionSensor


class BaseSensor:
    def __init__(self, entry_data, sensor):
        self._manager = entry_data.manager
        self._sensor = sensor
        self.writes = 0

    async def async_added_to_hass(self):
        pass

    async def async_will_remove_from_hass(self):
        pass

    def schedule_update_ha_state(self):
        self.writes += 1

    def _handle_sensor_update(self, sensor):
        self.schedule_update_ha_state()


@pytest.mark.asyncio
async def test_late_companion_replacement_removal_and_unsubscribe():
    cls = definitions(
        "update.py",
        ["Entity"],
        {
            "BaseSensorEntity": BaseSensor,
            "UpdateEntity": object,
            "ENTITY_ID_FORMAT": "update.{}",
            "EntityCategory": NS(DIAGNOSTIC="diagnostic"),
        },
    )["Entity"]
    parent = VersionSensor(key="latest", dynamic=True)
    sensors = {"latest": parent}
    entity = cls(
        NS(manager=NS(sensors_by_key=sensors)),
        VersionSensor(key="installed_pkg", latest="latest_pkg"),
    )
    await entity.async_added_to_hass()
    assert entity.latest_version is None
    child = VersionSensor(key="latest_pkg")
    child.value = "2.0"
    sensors[child.key] = child
    # Lazy access resolves even before the parent notification.
    assert entity.latest_version == "2.0"
    parent.on_update.notify(parent)
    assert entity.writes == 1
    child.on_update.notify(child)
    assert entity.writes == 2
    replacement = VersionSensor(key=child.key)
    replacement.value = "3.0"
    sensors[child.key] = replacement
    parent.on_update.notify(parent)
    assert entity.latest_version == "3.0"
    writes = entity.writes
    child.on_update.notify(child)
    assert entity.writes == writes
    del sensors[child.key]
    parent.on_update.notify(parent)
    assert entity.latest_version is None
    writes = entity.writes
    replacement.on_update.notify(replacement)
    assert entity.writes == writes
    await entity.async_will_remove_from_hass()
    parent.on_update.notify(parent)
    assert entity.writes == writes
