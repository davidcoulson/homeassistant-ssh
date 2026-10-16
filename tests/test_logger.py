import logging
from unittest.mock import AsyncMock

import pytest
from source import definitions
from ssh_terminal_manager import Command, CommandOutput, SSHManager, TextSensor


@pytest.mark.asyncio
async def test_dependency_command_and_password_payloads_are_not_logged(caplog):
    logger_cls = definitions("logger.py", ["PayloadFreeLogger"], {"logging": logging})[
        "PayloadFreeLogger"
    ]
    logger = logger_cls(logging.getLogger("ssh.offline.test"))
    manager = SSHManager(AsyncMock(), logger=logger)
    manager.async_execute = AsyncMock(
        return_value=CommandOutput(
            "tool TOKEN_SECRET", 0, ["STDOUT_SECRET"], ["STDERR_SECRET"], 0
        )
    )
    with caplog.at_level(logging.DEBUG):
        await manager.async_execute_command(Command("tool TOKEN_SECRET"))
        TextSensor(key="password", attributes={"mode": "password"}).update(
            manager, "PASSWORD_SECRET"
        )
        logger.error(
            "EXCEPTION_SECRET %s", "ARG_SECRET", exc_info=ValueError("TRACE_SECRET")
        )
    assert caplog.records
    assert all(
        record.getMessage() == "SSH manager event (payload omitted)"
        for record in caplog.records
    )
    assert "SECRET" not in caplog.text
