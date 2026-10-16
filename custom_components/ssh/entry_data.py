from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.device_registry import DeviceEntry
from ssh_terminal_manager import ActionKey, SensorKey, SSHManager

from .coordinator import BaseCoordinator, SensorCommandCoordinator, StateCoordinator


@dataclass
class EntryData:
    config_entry: ConfigEntry
    manager: SSHManager
    state_coordinator: StateCoordinator
    command_coordinators: list[SensorCommandCoordinator]
    platforms: list[Platform]
    ignored_action_keys: list[ActionKey] | None = None
    ignored_sensor_keys: list[SensorKey] | None = None
    device_entry: DeviceEntry | None = None

    unsubscribe_callbacks: list[Callable] = field(default_factory=list)
    _shutdown: bool = field(default=False, init=False)

    @property
    def coordinators(self) -> list[BaseCoordinator]:
        """All coordinators of the config entry."""
        return [self.state_coordinator, *self.command_coordinators]

    async def async_shutdown(self) -> None:
        """Shutdown all coordinators and reset manager."""
        if self._shutdown:
            return
        self._shutdown = True
        for unsubscribe in self.unsubscribe_callbacks:
            unsubscribe()
        self.unsubscribe_callbacks.clear()
        try:
            for coordinator in self.coordinators:
                await coordinator.async_shutdown()
        finally:
            await self.manager.async_reset()
