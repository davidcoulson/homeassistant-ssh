import re
from types import SimpleNamespace as NS

import jinja2
import pytest
import ssh_terminal_manager as library
from source import ROOT, definitions
from test_command import module as guarded


class Template:
    def __init__(self, source, hass):
        self.template = jinja2.Template(source)

    def async_render(self, variables=None, **kwargs):
        return self.template.render(**(variables or {}))


@pytest.fixture
def converter_namespace():
    constants = {
        name: name.removeprefix("CONF_").lower()
        for name in re.findall(
            r"\bCONF_\w+", (ROOT / "custom_components/ssh/converter.py").read_text()
        )
    }
    ns = {
        **vars(library),
        **constants,
        "Command": guarded.Command,
        "ActionCommand": guarded.ActionCommand,
        "SensorCommand": guarded.SensorCommand,
        "SENSOR_ATTR_DEFAULTS": {},
        "ACTION_ATTR_DEFAULTS": {},
        "SENSOR_ATTR_KEYS": (
            "device_class",
            "icon",
            "entity_registry_enabled_default",
            "suggested_unit_of_measurement",
            "suggested_display_precision",
            "mode",
        ),
        "ACTION_ATTR_KEYS": ("device_class", "icon", "entity_registry_enabled_default"),
    }
    ns.update(
        definitions(
            "helpers.py",
            ["get_command_renderer", "get_value_renderer"],
            {"Template": Template},
        )
    )
    return definitions("converter.py", ["remove_none_items", "Converter"], ns)


@pytest.mark.parametrize("sensor_type", ["text", "number", "binary", "version"])
def test_templates_and_attributes_survive_command_roundtrip(
    converter_namespace, sensor_type
):
    converter = converter_namespace["Converter"](None)
    attributes = {
        "mode": "password",
        "icon": "mdi:lock",
        "device_class": "test",
        "entity_registry_enabled_default": False,
        "suggested_unit_of_measurement": "MB",
        "suggested_display_precision": 2,
    }
    sensor = dict(
        type=sensor_type,
        key="secret",
        name="Secret",
        value_template="{{ value | trim }}",
        command_set="set @{value}",
        timeout_set=5,
        **attributes,
    )
    if sensor_type == "binary":
        sensor.update(
            command_on="on @{id}", command_off="off @{id}", timeout_on=1, timeout_off=2
        )
    command_data = {
        "command": "poll",
        "timeout": 10,
        "scan_interval": 20,
        "separator": "|",
        "sensors": [sensor],
    }
    command = guarded.SensorCommand(**converter.get_sensor_command_kwargs(command_data))
    assert converter.get_sensor_command_config(command) == command_data
    assert command.sensors[0].renderer("  secret  ") == "secret"
    action_data = {
        "command": "run @{token}",
        "key": "run",
        "name": "Run",
        "icon": "mdi:lock",
        "device_class": "restart",
        "entity_registry_enabled_default": False,
    }
    action = guarded.ActionCommand(**converter.get_action_command_kwargs(action_data))
    assert converter.get_action_command_config(action) == action_data


@pytest.mark.parametrize("reset_defaults,remove_custom", [(True, False), (False, True)])
def test_reset_preserves_retained_command_metadata(
    converter_namespace, reset_defaults, remove_custom
):
    import ast

    # Execute the actual reset method without requiring HA's options-flow runtime.
    tree = ast.parse((ROOT / "custom_components/ssh/config_flow.py").read_text())
    flow_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OptionsFlow"
    )
    reset = next(
        n for n in flow_class.body if getattr(n, "name", "") == "reset_commands"
    )
    ns = dict(converter_namespace)
    exec(  # noqa: S102 - execute repository definitions with explicit fakes
        compile(ast.Module(body=[reset], type_ignores=[]), "config_flow.py", "exec"), ns
    )
    converter = ns["Converter"](None)

    def sensor(key):
        return {
            "type": "text",
            "key": key,
            "name": key,
            "value_template": "{{ value }}",
            "mode": "password",
            "icon": "mdi:lock",
        }

    data = {
        "action_commands": [],
        "sensor_commands": [
            {"command": "poll", "sensors": [sensor("default"), sensor("custom")]}
        ],
    }
    default = converter.get_collection(
        {
            "action_commands": [],
            "sensor_commands": [{"command": "poll", "sensors": [sensor("default")]}],
        }
    )
    flow = NS(hass=None, _data=data, _default_collection=default)
    ns["reset_commands"](flow, reset_defaults, remove_custom)
    retained = "custom" if reset_defaults else "default"
    sensors = [
        s
        for c in flow._data["sensor_commands"]
        for s in c["sensors"]
        if s.get("key") == retained
    ]
    assert sensors == [sensor(retained)]


@pytest.mark.asyncio
async def test_initial_discovery_uses_guarded_default_commands(converter_namespace):
    import ast
    from unittest.mock import AsyncMock, Mock

    from ssh_terminal_manager import ExecutionError, default_collections

    tree = ast.parse((ROOT / "custom_components/ssh/config_flow.py").read_text())
    cls = next(node for node in tree.body if getattr(node, "name", "") == "ConfigFlow")
    method = next(
        node for node in cls.body if getattr(node, "name", "") == "async_validate_user"
    )
    body = [
        ast.ImportFrom(module="__future__", names=[ast.alias("annotations")], level=0),
        method,
    ]
    converter = converter_namespace["Converter"](None)

    def options(collection):
        return {
            "action_commands": [
                converter.get_action_command_config(command)
                for command in collection.action_commands
            ],
            "sensor_commands": [
                converter.get_sensor_command_config(command)
                for command in collection.sensor_commands
            ],
        }

    captured = []

    def manager_factory(terminal, collection, **kwargs):
        captured.append(collection)
        manager = AsyncMock()
        manager.__aenter__.return_value = manager
        return manager

    ns = {
        **converter_namespace,
        **{
            name: name[5:].lower()
            for name in (
                "CONF_HOST",
                "CONF_PORT",
                "CONF_USERNAME",
                "CONF_PASSWORD",
                "CONF_KEY_FILENAME",
                "CONF_HOST_KEYS_FILENAME",
                "CONF_ADD_HOST_KEYS",
                "CONF_LOAD_SYSTEM_HOST_KEYS",
                "CONF_INVOKE_SHELL",
                "CONF_DEFAULT_COMMANDS",
                "CONF_MAC",
                "CONF_NAME",
            )
        },
        "SSHTerminal": Mock(),
        "SSHManager": manager_factory,
        "default_collections": default_collections,
        "PayloadFreeLogger": Mock(),
    }
    exec(  # noqa: S102 - execute repository definitions with explicit fakes
        compile(
            ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
            "config_flow.py",
            "exec",
        ),
        ns,
    )
    flow = NS(
        hass=None,
        logger=Mock(),
        get_options=lambda obj: (
            options(obj) if isinstance(obj, library.Collection) else {}
        ),
        get_mac_address=Mock(),
        async_get_hostname=AsyncMock(),
    )
    await ns["async_validate_user"](
        flow,
        {
            "host": "fake",
            "port": 22,
            "default_commands": "linux",
            "add_host_keys": False,
            "load_system_host_keys": False,
            "invoke_shell": False,
        },
    )
    command = next(
        command
        for command in captured[0].sensor_commands
        if "&{network_interface}" in command.string
    )
    manager = NS(
        async_poll_sensors=AsyncMock(
            return_value=([NS(key="network_interface", value="eth0;id")], [])
        )
    )
    with pytest.raises(ExecutionError):
        await command.async_render_string(manager)
    assert all(
        isinstance(command, guarded.SensorCommand)
        for command in captured[0].sensor_commands
    )
