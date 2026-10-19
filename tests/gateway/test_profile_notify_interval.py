"""The native gateway heartbeat uses the current turn's profile configuration."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.run import GatewayRunner
from gateway.turn_context import TurnContext


@pytest.fixture
def heartbeat(monkeypatch):
    monkeypatch.setenv("HERMES_AGENT_NOTIFY_INTERVAL", "180")
    sleep = AsyncMock()
    monkeypatch.setattr("gateway.run_turn.asyncio.sleep", sleep)
    runner = object.__new__(GatewayRunner)
    runner._delivery_adapter_for = Mock(return_value=SimpleNamespace(send=AsyncMock()))
    # Stop after the first timer tick without sending a network notification.
    runner._should_emit_long_running_notification = Mock(return_value=False)
    return runner, sleep


@pytest.mark.asyncio
async def test_native_heartbeat_keeps_each_profiles_interval(heartbeat):
    runner, sleep = heartbeat
    for profile, interval in [
        ("secondary", 60), ("secondary", 0), ("other", 120),
        ("secondary", 0.25), ("secondary", 60),
    ]:
        config = {"agent": {"gateway_notify_interval": interval}}
        disp = SimpleNamespace(user_config=config, _display_surface_mode=lambda *a, **kw: "on")
        ctx = TurnContext(
            source=SimpleNamespace(profile=profile, chat_id="chat", platform="telegram"),
            session_key=f"agent:{profile}:telegram:chat",
        )
        sleep.reset_mock()
        runner._delivery_adapter_for.reset_mock()

        await runner._run_agent_notify_long_running(disp, ctx, [None])

        if interval == 0:
            sleep.assert_not_awaited()
            runner._delivery_adapter_for.assert_not_called()
        else:
            sleep.assert_awaited_once_with(interval)
        assert config == {"agent": {"gateway_notify_interval": interval}}
        assert os.environ["HERMES_AGENT_NOTIFY_INTERVAL"] == "180"


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [
    {}, {"agent": {}}, {"agent": None},
    {"agent": {"gateway_notify_interval": None}},
    {"agent": {"gateway_notify_interval": "invalid"}},
    {"agent": {"gateway_notify_interval": ""}},
    {"agent": {"gateway_notify_interval": []}},
    {"agent": {"gateway_notify_interval": float("nan")}},
    {"agent": {"gateway_notify_interval": float("inf")}},
    {"agent": {"gateway_notify_interval": float("-inf")}},
])
async def test_native_heartbeat_falls_back_to_environment(heartbeat, config):
    runner, sleep = heartbeat
    disp = SimpleNamespace(user_config=config, _display_surface_mode=lambda *a, **kw: "on")
    ctx = TurnContext(source=SimpleNamespace(chat_id="chat", platform="telegram"), session_key="sess")

    await runner._run_agent_notify_long_running(disp, ctx, [None])

    sleep.assert_awaited_once_with(180)
