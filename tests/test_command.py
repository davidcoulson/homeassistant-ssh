import importlib.util
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jinja2
import pytest
from source import ROOT
from ssh_terminal_manager import ExecutionError

spec = importlib.util.spec_from_file_location(
    "guarded_command", ROOT / "custom_components/ssh/command.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_type", [module.Command, module.ActionCommand, module.SensorCommand]
)
async def test_admin_template_before_substitution(command_type):
    seen = []

    def renderer(source):
        seen.append(source)
        return jinja2.Template(source).render(prefix="echo")

    kwargs = {"key": "action"} if command_type is module.ActionCommand else {}
    command = command_type(
        "{{ prefix }} @{value} &{sensor}", renderer=renderer, **kwargs
    )
    manager = SimpleNamespace(
        async_poll_sensors=AsyncMock(
            return_value=([SimpleNamespace(key="sensor", value="device")], [])
        )
    )
    assert (
        await command.async_render_string(manager, {"value": "literal"})
        == "echo literal device"
    )
    assert seen == ["{{ prefix }} @{value} &{sensor}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        "{{ secret }}",
        "'; printf INJECTED; #",
        "$(id)",
        "`id`",
        "&{other}",
        "%PATH%",
        "a\nb",
        "a b",
        '"',
        "$x",
        "a|b",
        "a&b",
        "a>b",
        "a^b",
        "a!b",
        None,
    ],
)
@pytest.mark.parametrize(
    "source", ["echo '@{value}'", 'echo "@{id}"', "echo &{sensor}"]
)
async def test_untrusted_data_fails_closed(value, source):
    seen = []
    command = module.Command(source, renderer=lambda text: seen.append(text) or text)
    manager = SimpleNamespace(
        async_poll_sensors=AsyncMock(
            return_value=([SimpleNamespace(key="sensor", value=value)], [])
        )
    )
    with pytest.raises(ExecutionError, match="Unsafe or missing"):
        await command.async_render_string(manager, {"value": value, "id": value})
    assert seen == [source]
