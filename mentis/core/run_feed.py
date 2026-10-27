"""What a run held here is doing, as MARS reports it: a bounded, sequenced feed.

MARS streams standard ACP updates for every turn it runs (agent message and
thought chunks, tool calls and their updates, plans, usage). Mentis used to
keep only the latest one (`last_event`). A person watching a run in Fluid
wants more than that -- what the agent is saying, which tools it ran, its
plan -- so each run this process holds keeps a FEED of them:

  * ONE ENTRY PER THING, updated in place. Message and thought chunks are
    joined into the entry they continue; a tool call's updates go into that
    call's entry; the plan and the usage are one entry each. An entry that
    changes moves to the end of the feed with a new `seq`, so a reader that
    asks `since(seq)` gets every entry that is new or changed since, by its
    stable `id`, and replaces what it held.
  * BOUNDED. At most `KEPT` entries, oldest dropped; a message entry keeps at
    most `TEXT_KEPT` characters (its tail).
  * NEVER RECORDED. The feed lives in this process and dies with the run's
    observation. The record keeps what it always kept: the run's start, its
    end and what it returned. A transient stream is not the record.

`activity` is the one line a person reads over the composer: what the agent
is doing now, in its own tool's words ("Read AGENTS.md", "Run npm test"),
taken from the latest tool call in progress, else the plan's step in
progress, else "Writing" / "Thinking". It describes; it never judges (a
quiet run is not "stuck").
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

#: Entries a feed keeps; a long run's oldest go first.
KEPT = 300
#: Characters one message or thought entry keeps (its tail).
TEXT_KEPT = 20_000
#: Characters of a tool call's raw input or output kept in its entry.
FIELD_KEPT = 2_000

_TEXT_KINDS = {"agent_message_chunk": "message", "agent_thought_chunk": "thought"}


def _clip(value: Any, limit: int = FIELD_KEPT) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, (dict, list)):
        import json
        text = json.dumps(value, default=str)
        return value if len(text) <= limit else text[:limit] + "…"
    return value


def _text_of(data: dict) -> str:
    if isinstance(data.get("text"), str):
        return data["text"]
    content = data.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


class RunFeed:
    """One run's feed. Thread-safe: MARS events arrive on the ACP loop's
    thread, readers come from HTTP handler threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, dict] = OrderedDict()
        self._seq = 0
        self._n = 0
        self._last_text: str | None = None   # the id the next chunk continues
        self.activity: str | None = None
        self.activity_at: float | None = None

    # -- writing -----------------------------------------------------------

    def _put(self, eid: str, entry: dict) -> None:
        self._seq += 1
        entry["seq"] = self._seq
        self._entries.pop(eid, None)
        self._entries[eid] = entry
        while len(self._entries) > KEPT:
            self._entries.popitem(last=False)

    def _fresh(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"

    def add(self, kind: str, data: dict | None, at: float) -> None:
        data = data or {}
        with self._lock:
            if kind in _TEXT_KINDS:
                self._text(_TEXT_KINDS[kind], _text_of(data), at)
            elif kind in ("tool_call", "tool_call_update"):
                self._last_text = None
                self._tool(data, at)
            elif kind == "plan":
                self._last_text = None
                entries = [{"content": e.get("content"), "status": e.get("status"),
                            "priority": e.get("priority")}
                           for e in data.get("entries") or () if isinstance(e, dict)]
                self._put("plan", {"id": "plan", "kind": "plan", "at": at,
                                   "entries": entries})
                step = next((e["content"] for e in entries
                             if e.get("status") == "in_progress" and e.get("content")), None)
                if step:
                    self._now(step, at, over_tool=False)
            elif kind == "usage_update":
                self._put("usage", {"id": "usage", "kind": "usage", "at": at,
                                    "usage": {k: v for k, v in data.items()
                                              if isinstance(v, (int, float, str))}})
            elif kind == "permission":
                self._last_text = None
                eid = self._fresh("permission")
                self._put(eid, {"id": eid, "kind": "permission", "at": at,
                                "title": (data.get("tool_call") or {}).get("title"),
                                "outcome": data.get("outcome"),
                                "answered_by": data.get("answered_by"),
                                "option": data.get("selected_option_id")})

    def _text(self, which: str, text: str, at: float) -> None:
        last = self._entries.get(self._last_text) if self._last_text else None
        if last is not None and last["kind"] == which:
            joined = (last["text"] + text)[-TEXT_KEPT:]
            self._put(last["id"], {**last, "text": joined, "at": at})
        else:
            eid = self._fresh(which)
            self._put(eid, {"id": eid, "kind": which, "at": at, "text": text[-TEXT_KEPT:]})
            self._last_text = eid
        if not self.activity or self.activity in ("Writing", "Thinking") or \
                self._tool_running() is None:
            self._now("Writing" if which == "message" else "Thinking", at)

    def _tool_running(self) -> dict | None:
        for e in reversed(self._entries.values()):
            if e["kind"] == "tool" and e.get("status") in ("pending", "in_progress"):
                return e
        return None

    def _tool(self, data: dict, at: float) -> None:
        tid = str(data.get("tool_call_id") or data.get("toolCallId") or self._fresh("t"))
        eid = "tool-" + tid
        old = self._entries.get(eid) or {"id": eid, "kind": "tool", "started_at": at}
        entry = dict(old)
        for key in ("title", "kind", "status"):
            if data.get(key) is not None:
                entry["tool_kind" if key == "kind" else key] = data[key]
        for key in ("raw_input", "raw_output"):
            if data.get(key) is not None:
                entry[key] = _clip(data[key])
        locations = data.get("locations")
        if locations:
            entry["locations"] = [loc.get("path") for loc in locations
                                  if isinstance(loc, dict) and loc.get("path")][:10]
        entry["at"] = at
        self._put(eid, entry)
        title = entry.get("title")
        if entry.get("status") in (None, "pending", "in_progress") and title:
            self._now(str(title), at)
        elif self.activity == title:
            running = self._tool_running()
            if running and running.get("title"):
                self._now(str(running["title"]), at)

    def _now(self, words: str, at: float, *, over_tool: bool = True) -> None:
        if not over_tool and self._tool_running() is not None:
            return
        words = " ".join(words.split())
        self.activity = words if len(words) <= 120 else words[:119] + "…"
        self.activity_at = at

    # -- reading -----------------------------------------------------------

    @property
    def seq(self) -> int:
        return self._seq

    def since(self, after: int = 0) -> list[dict]:
        """Every entry new or changed after `after`, oldest change first."""
        with self._lock:
            return [dict(e) for e in self._entries.values() if e["seq"] > after]
