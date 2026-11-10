"""Stands where ``mars stdio`` stands, for the WS-P session-continuity and timing tests.

`python mars_continuity_stand_in.py <log> <mode>`: answers the ACP that `mentis.execution.mars`
speaks and writes, per session, the `_meta` session/new was given and the prompt it was sent, to
`<log>` (one JSON line per event). `<mode>`:

  * ``new`` -- a MARS with the WS-P keys: `mars/timing` and `mars/resume` on every session/new,
    and `mars/resumed` answering a `mars/resume` token it gave out;
  * ``refuse`` -- as ``new``, but it never resumes (`resumed: false`);
  * ``old`` -- a MARS without them: none of the keys, whatever it is sent.

It is no runtime and no MARS; nothing here calls Mentis.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import acp
from acp import update_agent_message_text
from acp.schema import NewSessionResponse, PromptResponse

from mars_acp_agent import ScriptedAgent


class ContinuityAgent(ScriptedAgent):
    def __init__(self, log: str, mode: str) -> None:
        super().__init__()
        self.log, self.mode = log, mode
        self.tokens: set[str] = set()

    def _write(self, **what: Any) -> None:
        with open(self.log, "a", encoding="utf-8") as out:
            out.write(json.dumps(what) + "\n")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "mars/backends":
            return {"backends": [{"id": "stand-in", "kind": "stand-in", "installed": True,
                                  "available": True,
                                  "supports": {"mcp": ["stdio"], "permissions": "forwarded"}}]}
        if method == "mars/capacity":
            return {"capacity": {}}
        return {}

    async def new_session(self, cwd: str, mcp_servers: list[Any] | None = None, **kwargs: Any):
        made = await super().new_session(cwd, mcp_servers, **kwargs)
        meta = dict(kwargs.get("field_meta") or kwargs)
        self._write(event="new", session=made.session_id,
                    meta={k: v for k, v in meta.items() if k.startswith("mars/")})
        if self.mode == "old":
            return made
        asked = (meta.get("mars/resume") or {}).get("token")
        token = f"rt-{len(self.tokens)}"
        out: dict[str, Any] = {"mars/timing": {"spawn_ms": 12, "initialize_ms": 30,
                                               "new_session_ms": 40, "load_ms": 0,
                                               "resolve_ms": 1}}
        if asked:
            ok = self.mode == "new" and asked in self.tokens
            out["mars/resumed"] = {"resumed": ok, "why": "loaded" if ok else "not loaded"}
            if ok:
                token = asked
        self.tokens.add(token)
        out["mars/resume"] = {"token": token, "supported": self.mode == "new"}
        return NewSessionResponse(session_id=made.session_id, field_meta=out)

    async def prompt(self, session_id: str, prompt: list[Any], **kwargs: Any) -> PromptResponse:
        text = "".join(getattr(block, "text", "") for block in prompt)
        self._write(event="prompt", session=session_id, text=text)
        await self.conn.session_update(session_id=session_id,
                                       update=update_agent_message_text("ok"))
        return PromptResponse(stop_reason="end_turn")


def main() -> None:
    asyncio.run(acp.run_agent(ContinuityAgent(sys.argv[1], sys.argv[2]),
                              use_unstable_protocol=True))


if __name__ == "__main__":
    main()
