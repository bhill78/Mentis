"""Stands where ``mars stdio`` stands, for the send-boundary tests
(`mentis.execution.send`).

`python mars_send_boundary_stand_in.py <log> <mode>`: speaks the ACP that
`mentis.execution.mars` speaks and writes one JSON line per event to `<log>`,
so a test can see exactly whether a prompt was ever sent. `<mode>`:

  * ``ok`` -- a session that opens at once, and a prompt answered with one
    agent message and `end_turn`;
  * ``slow`` -- as ``ok``, but session/new takes a second: the window a send
    gate has to be entered in, after the session is open and before the bytes;
  * ``quiet`` -- a prompt answered with `end_turn` and no session update at
    all: the turn ran, and the result is the only acknowledgement there is;
  * ``refuse`` -- a prompt the backend answers with an ACP error: MARS took
    the request and the send failed;
  * ``vanish`` -- the prompt arrives and the process dies without answering:
    whether the bytes reached the runtime is not known.

It is no runtime and no MARS; nothing here calls Mentis.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import acp
from acp import RequestError, update_agent_message_text
from acp.schema import PromptResponse

from mars_acp_agent import ScriptedAgent


class SendBoundaryAgent(ScriptedAgent):
    def __init__(self, log: str, mode: str) -> None:
        super().__init__()
        self.log, self.mode = log, mode

    def _write(self, **what: Any) -> None:
        with open(self.log, "a", encoding="utf-8") as out:
            out.write(json.dumps(what) + "\n")
            out.flush()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "mars/backends":
            return {"backends": [{"id": "stand-in", "kind": "stand-in", "installed": True,
                                  "available": True,
                                  "supports": {"mcp": ["stdio"], "permissions": "forwarded"}}]}
        if method == "mars/capacity":
            return {"capacity": {}}
        return {}

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        self._write(event="cancel", session=session_id)
        await super().cancel(session_id, **kwargs)

    async def new_session(self, cwd: str, mcp_servers: list[Any] | None = None, **kwargs: Any):
        if self.mode == "slow":
            await asyncio.sleep(1.0)
        made = await super().new_session(cwd, mcp_servers, **kwargs)
        self._write(event="new", session=made.session_id)
        return made

    async def prompt(self, session_id: str, prompt: list[Any], **kwargs: Any) -> PromptResponse:
        text = "".join(getattr(block, "text", "") for block in prompt)
        self._write(event="prompt", session=session_id, text=text)
        if self.mode == "vanish":
            # NOTHING IS EVER ANSWERED and the pipe closes: the bytes may or
            # may not have reached a runtime, and nothing here can say.
            sys.stdout.flush()
            os._exit(0)
        if self.mode == "refuse":
            raise RequestError.internal_error({"why": "the backend would not take it"})
        if self.mode != "quiet":
            await self.conn.session_update(session_id=session_id,
                                           update=update_agent_message_text("ok"))
        return PromptResponse(stop_reason="end_turn")


def main() -> None:
    asyncio.run(acp.run_agent(SendBoundaryAgent(sys.argv[1], sys.argv[2]),
                              use_unstable_protocol=True))


if __name__ == "__main__":
    main()
