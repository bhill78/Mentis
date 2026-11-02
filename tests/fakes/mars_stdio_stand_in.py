"""Stands where ``mars stdio`` stands, for a run that has to be dispatched and go on being one.

Row J10 needs `answer` and `timer` under a dispatched execution's grant. A grant lasts as long as its
run, and its run is what dispatch starts through `--mars`, so this answers the ACP that
`mentis.execution.mars` speaks, lists one backend, writes what each session was given to the file
named on its command line, and holds the turn until it is cancelled or the server goes.

It is no runtime and no MARS. Everything Mentis does with a run is Mentis's own: dispatch, the
grant, the MCP server's command. Nothing here calls Mentis.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import acp
from acp.schema import PromptResponse

from mars_acp_agent import ScriptedAgent

BACKEND = "j10-stand-in"


class HoldingAgent(ScriptedAgent):
    def __init__(self, told: str) -> None:
        super().__init__()
        self.told = told

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "mars/backends":
            return {"backends": [{"id": BACKEND, "kind": "stand-in", "installed": True,
                                  "available": True,
                                  "supports": {"mcp": ["stdio"], "permissions": "forwarded"}}]}
        if method == "mars/capacity":
            return {"capacity": {}}
        return {}

    async def new_session(self, cwd: str, mcp_servers: list[Any] | None = None, **kwargs: Any):
        made = await super().new_session(cwd, mcp_servers, **kwargs)
        with open(self.told, "a", encoding="utf-8") as told:
            told.write(json.dumps([server.model_dump(mode="json")
                                   for server in mcp_servers or []]) + "\n")
        return made

    async def prompt(self, session_id: str, prompt: list[Any], **kwargs: Any) -> PromptResponse:
        await self.sessions[session_id]["cancelled"].wait()
        return PromptResponse(stop_reason="cancelled")


def main() -> None:
    asyncio.run(acp.run_agent(HoldingAgent(sys.argv[1]), use_unstable_protocol=True))


if __name__ == "__main__":
    main()
