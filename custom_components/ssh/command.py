"""Command guards for the pinned manager's unsafe substitution order."""

from __future__ import annotations

import re

from ssh_terminal_manager import (
    ActionCommand as ManagerActionCommand,
)
from ssh_terminal_manager import (
    Command as ManagerCommand,
)
from ssh_terminal_manager import (
    ExecutionError,
)
from ssh_terminal_manager import (
    SensorCommand as ManagerSensorCommand,
)

_SUBSTITUTION = re.compile(r"([@&])\{([a-zA-Z_][a-zA-Z_0-9]*)\}")
_SAFE_VALUE = re.compile(r"[a-zA-Z0-9_./:-]+")


class _SafeRendering:
    async def async_render_string(self, manager, variables=None) -> str:
        # Only administrator-authored source may be compiled as a HA template.
        string = self.renderer(self.string) if self.renderer else self.string
        matches = list(_SUBSTITUTION.finditer(string))
        sensor_keys = {m[2] for m in matches if m[1] == "&"}
        sensors, _ = await manager.async_poll_sensors(sensor_keys)
        sensor_values = {sensor.key: sensor.value for sensor in sensors}
        variables = variables or {}

        def substitute(match):
            values = variables if match[1] == "@" else sensor_values
            value = values.get(match[2])
            # The API does not identify the remote shell or the quote context of
            # a placeholder. Fail closed rather than guess an escaping dialect.
            # This includes dynamic ids, which come from device output.
            if value is None or not _SAFE_VALUE.fullmatch(str(value)):
                raise ExecutionError("Unsafe or missing command substitution")
            return str(value)

        # A single pass prevents variable data becoming a sensor placeholder.
        return _SUBSTITUTION.sub(substitute, string)


class Command(_SafeRendering, ManagerCommand):
    """Command with template-before-data rendering and conservative arguments."""


class ActionCommand(_SafeRendering, ManagerActionCommand):
    """Action with guarded rendering."""


class SensorCommand(_SafeRendering, ManagerSensorCommand):
    """Sensor command with guarded rendering."""
