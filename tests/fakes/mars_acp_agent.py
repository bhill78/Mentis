"""Scripted ACP backend used by ``test_execution_mars``.

This is intentionally a separate process.  MARS launches it exactly as it would a
real configured ACP backend, so the tests cover both sides of MARS's forwarding.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import acp
from acp import RequestError, start_tool_call, update_agent_message_text, update_tool_call
from acp.schema import (
    AgentCapabilities,
    CloseSessionResponse,
    Implementation,
    InitializeResponse,
    NewSessionResponse,
    PermissionOption,
    PromptResponse,
    SessionCapabilities,
    SessionCloseCapabilities,
    ToolCallLocation,
    ToolCallUpdate,
    UsageUpdate,
)


class ScriptedAgent:
    def __init__(self, auth_failure: bool = False) -> None:
        self.auth_failure = auth_failure
        self.conn: Any = None
        self.sessions: dict[str, dict[str, Any]] = {}

    def on_connect(self, conn: Any) -> None:
        self.conn = conn

    async def initialize(self, protocol_version: int, **kwargs: Any) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=acp.PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                session_capabilities=SessionCapabilities(close=SessionCloseCapabilities())
            ),
            agent_info=Implementation(name="mentis-test-agent", version="1.0"),
        )

    async def new_session(
        self, cwd: str, mcp_servers: list[Any] | None = None, **kwargs: Any
    ) -> NewSessionResponse:
        if self.auth_failure:
            raise RequestError.auth_required({"authMethods": ["test-login"]})
        session_id = f"test-{os.getpid()}-{len(self.sessions)}"
        self.sessions[session_id] = {
            "cwd": cwd,
            "mcp_names": [server.name for server in (mcp_servers or [])],
            "cancelled": asyncio.Event(),
        }
        return NewSessionResponse(session_id=session_id)

    async def close_session(self, session_id: str, **kwargs: Any) -> CloseSessionResponse:
        self.sessions.pop(session_id, None)
        return CloseSessionResponse()

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        session = self.sessions.get(session_id)
        if session is not None:
            session["cancelled"].set()

    async def prompt(self, session_id: str, prompt: list[Any], **kwargs: Any) -> PromptResponse:
        text = "".join(getattr(block, "text", "") for block in prompt)
        command, _, argument = text.partition(" ")
        session = self.sessions[session_id]

        if command == "run":
            await self.conn.session_update(
                session_id=session_id, update=update_agent_message_text("hello from fake")
            )
            location = ToolCallLocation(path=os.path.join(session["cwd"], "result.txt"), line=3)
            await self.conn.session_update(
                session_id=session_id,
                update=start_tool_call(
                    "tool-1", "write result", kind="edit", status="pending", locations=[location]
                ),
            )
            await self.conn.session_update(
                session_id=session_id,
                update=update_tool_call("tool-1", status="completed"),
            )
            await self.conn.session_update(
                session_id=session_id,
                update=UsageUpdate(session_update="usage_update", used=7, size=100),
            )
            return PromptResponse(stop_reason="end_turn")

        if command == "permission":
            response = await self.conn.request_permission(
                session_id=session_id,
                tool_call=ToolCallUpdate(
                    tool_call_id="permission-1",
                    title="run test command",
                    kind="execute",
                    status="pending",
                ),
                options=[
                    PermissionOption(option_id="once", name="Allow once", kind="allow_once"),
                    PermissionOption(option_id="always", name="Allow", kind="allow_always"),
                    PermissionOption(option_id="no", name="Reject", kind="reject_once"),
                ],
            )
            option_id = getattr(response.outcome, "option_id", None)
            await self.conn.session_update(
                session_id=session_id,
                update=update_agent_message_text(
                    f"permission:{response.outcome.outcome}:{option_id}"
                ),
            )
            return PromptResponse(stop_reason="end_turn")

        if command == "slow":
            await self.conn.session_update(
                session_id=session_id, update=update_agent_message_text("waiting")
            )
            await session["cancelled"].wait()
            return PromptResponse(stop_reason="cancelled")

        if command == "mcp":
            await self.conn.session_update(
                session_id=session_id,
                update=update_agent_message_text(",".join(session["mcp_names"])),
            )
            return PromptResponse(stop_reason="end_turn")

        if command == "echo":
            await asyncio.sleep(0.2)
            await self.conn.session_update(
                session_id=session_id, update=update_agent_message_text(argument)
            )
            return PromptResponse(stop_reason="end_turn")

        raise RequestError.invalid_params({"prompt": text})


def main() -> None:
    asyncio.run(
        acp.run_agent(
            ScriptedAgent(auth_failure="--auth" in sys.argv), use_unstable_protocol=True
        )
    )


if __name__ == "__main__":
    main()
