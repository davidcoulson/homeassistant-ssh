import ast
from types import MethodType, SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol

from source import ROOT


def flow_methods():
    tree = ast.parse((ROOT / 'custom_components/ssh/config_flow.py').read_text())
    cls = next(node for node in tree.body if getattr(node, 'name', '') == 'ConfigFlow')
    names = ('async_handle_step_user_success', 'async_step_user')
    body = [ast.ImportFrom(module='__future__', names=[ast.alias('annotations')], level=0), *[node for node in cls.body if getattr(node, 'name', '') in names]]
    tree = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
    constants = {node.id: node.id.removeprefix('CONF_').lower() for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id.startswith('CONF_')}
    ns = {**constants, 'vol': vol, 'format_mac': lambda value: value.lower().replace('-', ':'),
          'config_entries': NS(SOURCE_REAUTH='reauth'), 'CONFIG_FLOW_USER_SCHEMA': vol.Schema({vol.Required('host'): str, vol.Required('default_commands'): str}),
          'DEFAULT_PORT': 22, 'DEFAULT_HOST_KEYS_FILENAME': 'known_hosts', 'DEFAULT_ADD_HOST_KEYS': False, 'DEFAULT_LOAD_SYSTEM_HOST_KEYS': False, 'DEFAULT_INVOKE_SHELL': False}
    exec(compile(tree, 'config_flow.py', 'exec'), ns)
    return ns


@pytest.mark.asyncio
@pytest.mark.parametrize('detected', ['aa:bb:cc:dd:ee:ff', None])
async def test_reconfigure_rejects_other_or_unverified_identity(detected):
    ns = flow_methods()
    flow = NS(_existing_entry=NS(data={'mac': '00:11:22:33:44:55'}), _data={'mac': detected}, async_abort=Mock(), async_update_reload_and_abort=Mock())
    await ns['async_handle_step_user_success'](flow)
    flow.async_abort.assert_called_once_with(reason='device_identity_mismatch')
    flow.async_update_reload_and_abort.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['reconfigure', 'reauth'])
async def test_same_identity_keeps_name_mac_and_command_options(source):
    ns = flow_methods()
    entry = NS(data={'mac': 'aa:bb:cc:dd:ee:ff', 'name': 'Original'})
    flow = NS(_existing_entry=entry, _data={'host': 'new-address', 'mac': 'AA-BB-CC-DD-EE-FF', 'name': 'Detected'}, source=source, async_update_reload_and_abort=Mock())
    await ns['async_handle_step_user_success'](flow)
    kwargs = flow.async_update_reload_and_abort.call_args.kwargs
    assert kwargs['data'] == {'host': 'new-address', **entry.data}
    assert 'options' not in kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize('existing', [True, False])
async def test_command_collection_selector_only_for_new_entries(existing):
    ns = flow_methods()
    flow = NS(_existing_entry=NS(data={'default_commands': 'linux'}) if existing else None,
              _data={}, hass=NS(config=NS(config_dir='/fake')), async_show_form=Mock(),
              add_suggested_values_to_schema=lambda schema, values: schema)
    await ns['async_step_user'](flow)
    schema = flow.async_show_form.call_args.kwargs['data_schema']
    assert ('default_commands' in {str(key) for key in schema.schema}) is not existing


@pytest.mark.asyncio
async def test_reconfigure_preserves_collection_even_if_submitted():
    ns = flow_methods()
    flow = NS(_existing_entry=NS(data={'default_commands': 'linux'}), async_validate_user=AsyncMock(return_value=({}, {})), async_handle_step_user_success=AsyncMock())
    await ns['async_step_user'](flow, {'host': 'same-host', 'default_commands': 'none'})
    flow.async_validate_user.assert_awaited_once_with({'host': 'same-host', 'default_commands': 'linux'})
