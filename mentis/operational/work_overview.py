"""The Work Overview: every piece of work, grouped and worded, read-only.

A PROJECTION, NOT A STATUS SYSTEM. Nothing here is stored and there is no
field anywhere that this reads back. Each Work item is a TRUNK
(`work.is_trunk`) and every word about it comes from what the record already
holds, through the readers that already say it:

    state, you owe, last act    `work.trunk_status` (or `work._unreadable`)
    each execution              `runs.run_state`, one run at a time
    decisions                   `expectation_state` of each decision under it
    contributing agents         the trunk's carrier and every delegated
                                descendant's, through `cv._descendants`
    origin and replies          the trunk's Turn, its number, and the Turns
                                under it, counted as `web._placed` counts them

Shaped exactly as `ui/src/work/contract.ts` (Work Overview contract v1).

WHERE THE WORK STANDS (`stage`, `stage.stage_of`): building, awaiting
review, needs the owner's decision, ready to deploy, deployed, blocked, or
answered with nothing produced -- derived from the commits, reviews and runs
under the trunk and from git, beside `group`, which older readers keep.

WORK COMPLETION IS NOT EXECUTION COMPLETION. `objective_met` is true only when
an `expectation-met` act is recorded on the trunk itself. Every run having
finished leaves it false, and says so in words.

UNKNOWN IS SAID. Where a source cannot say -- an unreadable trunk, a run open
by the record that nothing here holds, a viewer nobody named -- the field is
null or `unknown` and `why_unknown` says why. Nothing is guessed.

THERE IS NO QUEUE IN MARK IV (`web/dispatch.py:dispatch_soon` starts a thread),
so no execution is ever "queued": a request nothing has run for is
`not_started`.

TODAY'S LEDGER (`active_since`, owner decision A). Almost nothing on a real
Brain is ever claimed met, so "everything not met" is every request ever made.
Scoped, the read keeps what needs the viewer, what something is still moving
on, and what was active since the given moment -- and decides that BEFORE any
status is computed, from the walk of each trunk's acts and Brain-wide reads of
what is still owed, what is claimed met and what was kept as discovered work
(`_in_scope`). What the status then says places it (`_scoped_group`).

IN FLIGHT IS MOVING WORK, WHENEVER IT BEGAN (owner decision #548): a run
observed going, or work waiting on a child, on a decision, or on other work
that is itself moving (`_motion`). Being touched since then puts nothing In
flight. A run recorded as started
with no end recorded is placed by what this process OBSERVES of that run
(`_seen_open`): observed going is In flight, observed ended is ended work, and
not observed at all is `unknown`, said why -- no end recorded is never taken
to mean still running. Work whose runs ended without its objective claimed
met is `returned` (the Ended line), its own group, never Completed. Work that has not started
is never In flight: it needs the viewer or it is left out, and how many were
left out is said, by reason (`scope.left_out_by`).

WAITING ON OTHER WORK IS MOVING ONLY WHILE THAT WORK MOVES (owner decision,
answering opr-03026547b87e). The awaited work is read by these same rules:
running or observed going, waiting on a child or a decision, or itself
waiting on work that moves. Where every piece it waits on has ended without
being claimed met it is "Waiting on ended work", placed with ended work and
never said to have ended itself: its `state` stays `waiting-on-work`. Where
what it waits on cannot be read, or waits on it in turn, whether it moves is
not established, and it is `unknown`, said why.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from mentis.conversation import ASKED_UNDER_WORK, closed_starts
from mentis.operational import stage as _stage
from mentis.operational.runs import run_state
from mentis.operational.work import (ENDS, FAILED, RECOVERED, RETURNED,
                                     STARTED, UNKNOWN, _Seq, _unreadable,
                                     is_trunk, trunk_status)

#: In the order items are returned. `returned` is only ever filled by a read
#: scoped with `active_since`; unscoped, it is always empty.
GROUPS = ("needs_you", "in_flight", "completed", "returned", "unknown")
#: What In flight holds whenever it began: something is actually moving on it
#: -- a run observed going, or a child or a decision it waits on. Waiting on
#: other work is In flight only while that work moves (`_motion`).
MOVING = ("running", "waiting-on-child", "waiting-on-decision",
          # its continuation running, or dispatched to (`trunk_status`)
          "continuing")
#: Of work waited on: these move whoever is looking (waiting on the viewer
#: is waiting on a live decision).
_AWAITED_MOVING = MOVING + ("waiting-on-you",)
#: How deep a chain of work waiting on work is followed before saying that
#: whether it moves cannot be established.
AWAIT_DEPTH = 12
#: Its runs ended and nobody claimed the objective met: the Ended line.
ENDED = ("returned", "recovered", "replied", "failed")
#: Nothing it waits on is out and nothing of it is running, but the record
#: says resumption will not happen by itself. Not moving and not met: placed
#: as ended work is.
STALLED = ("not-resumed", "resumable-not-resumed")
#: Nothing has run for it (or nothing since it was resumed): never In flight.
NOT_STARTED = ("owed", "unassigned", "resumed-no-run")
#: `run_state`'s words for a run this process holds and has not seen end.
_RUN_LIVE = ("tool-running", "model-outstanding", "helper-outstanding",
             "not-launched", "no-event")
#: Why a scoped read left a trunk out, in the order `scope.left_out_by` says.
LEFT_OUT = ("not_started", "inactive", "completed_earlier",
            "discovered_unassigned")
NO_VIEWER = ("nobody said who is looking and the record names no owner, so "
             "what anybody owes cannot be said")
EXEC_STATES = ("finished", "failed", "running", "not_started", "unknown")
#: The order an agent's or a work item's executions are worded in: what is
#: moving or wrong first, what is done last.
_WORD_ORDER = ("running", "failed", "not_started", "unknown", "finished")
_EXEC_WORD = {"finished": "finished", "failed": "failed", "running": "running",
              "not_started": "not started", "unknown": "unknown"}
TITLE_MAX = 90
NO_COMPLETES_WHEN = "the request did not say what completes it"
#: Where work stands (`stage.stage_of`), in the order the Ledger lists them.
STAGES = _stage.STAGES


# -- small readers -----------------------------------------------------------

def iso(at) -> str | None:
    """An act's epoch time as ISO 8601 UTC, or None."""
    if at is None:
        return None
    return (datetime.fromtimestamp(float(at), timezone.utc)
            .isoformat().replace("+00:00", "Z"))


def parse_since(text) -> float | None:
    """`completed_since` as epoch seconds. ISO 8601; a time with no offset is
    UTC (the Ledger sends `Date.toISOString()`, which always carries `Z`).
    Raises ValueError for anything else, so the route can refuse it by name."""
    if text in (None, ""):
        return None
    d = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _name(cv, pid) -> str | None:
    """A Participant as the Ledger writes it: the alias without its `@`."""
    if not pid:
        return None
    return (cv.alias(pid) or pid).lstrip("@")


_MD = [
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),    # images
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),     # links
    (re.compile(r"\[\[([^\]]+)\]\]"), r"\1"),          # wiki links
    (re.compile(r"`+([^`]*)`+"), r"\1"),               # code
    (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),          # bold
    (re.compile(r"(?<![\w*])[*_](\S(?:.*?\S)?)[*_](?![\w*])"), r"\1"),  # em
    (re.compile(r"~~(.+?)~~"), r"\1"),                 # strike
]
_LEAD = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)+")


def _plain_line(text) -> str | None:
    """The first non-empty line of some Markdown, as plain text."""
    for line in str(text or "").splitlines():
        line = _LEAD.sub("", line)
        for pat, rep in _MD:
            line = pat.sub(rep, line)
        line = " ".join(line.split())
        if line and not re.fullmatch(r"[-*_=`~|:\s]+", line):
            return line
    return None


def _clip(text, limit) -> str | None:
    if not text:
        return None
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


_SENTENCE_END = re.compile(r"[.!?] ")


def _sentences(text, limit=280) -> str | None:
    """One or two sentences of some prose, plain, for an outcome line.

    READ ONLY AS FAR AS THE TWO SENTENCES (the owner's slowdown,
    2026-10-25): every line of a long result was made plain -- ~40 lines a
    request, 1.5 s of Home's Work over ~1,800 requests -- to keep the first
    two sentences. Once the text read so far holds the start of a third,
    what follows cannot change the first two, so the rest is not read; the
    answer is the one the whole text gives."""
    # `flat` is kept as the whole would be made (words joined by single
    # spaces), and the sentence ends in it -- ".", "!" or "?" then a space --
    # counted as it grows: two of them mean a third sentence has begun.
    flat, ends = "", 0
    for line in str(text or "").splitlines():
        piece = " ".join((_plain_line(line) or "").split())
        if not piece:
            continue
        before = len(flat)
        flat = f"{flat} {piece}" if flat else piece
        ends += len(_SENTENCE_END.findall(flat, max(before - 1, 0)))
        if ends >= 2:
            break
    if not flat:
        return None
    parts = re.split(r"(?<=[.!?])\s+", flat)
    return _clip(" ".join(parts[:2]), limit)


class _Ctx:
    """What one read has already looked up, so a Brain-wide read asks each
    question once: Turn texts, Turn numbers, reply counts and Conversation
    names. Lives for one call and is then dropped -- not a cache of the
    record, which `cv.reading()` already scopes."""

    def __init__(self, cv):
        self.cv, self.order = cv, _Seq(cv)
        self._conv_rows, self._conv_names, self._texts = {}, {}, {}
        self._replies, self._below, self._states = {}, {}, {}
        # what each piece of awaited work was found to be (`_motion`), and
        # the chain being followed now, so a cycle is seen and not walked
        self.motion, self.visiting = {}, set()

    def descendants(self, expectation) -> list[dict]:
        """Every act under this one, walked once per read: the scope check
        and the projection both read it."""
        if expectation not in self._below:
            self._below[expectation] = self.cv._descendants(expectation)
        return self._below[expectation]

    def state(self, expectation) -> dict:
        if expectation not in self._states:
            self._states[expectation] = self.cv.expectation_state(expectation)
        return self._states[expectation]

    def text(self, turn) -> str | None:
        if not turn:
            return None
        if turn not in self._texts:
            from mentis.conversation.versions import flow_text
            got = self.cv.corpus.read([turn])
            self._texts[turn] = (flow_text((got[0].get("body") or {})
                                           .get("parts")) if got else None)
        return self._texts[turn]

    def _rows(self, conversation):
        if conversation not in self._conv_rows:
            rows = self.cv.turns(conversation)
            self._conv_rows[conversation] = (
                rows, {r["turn"]: r["number"] for r in rows})
        return self._conv_rows[conversation]

    def conversation_name(self, cid) -> str | None:
        if not cid:
            return None
        if cid not in self._conv_names:
            # UNDER ITS CURRENT NAME, as every reader of one reads it.
            self._conv_names[cid] = self.cv.conversation_name(cid)
        return self._conv_names[cid]

    def link(self, turn, conversation=None) -> dict | None:
        """A TurnLink, or None when there is no Turn to link to."""
        if not turn:
            return None
        conversation = conversation or self.cv.conversation_of(turn)
        number = None
        if conversation:
            number = self._rows(conversation)[1].get(turn)
        return {"turn": turn, "number": number, "conversation": conversation,
                "conversation_name": self.conversation_name(conversation)}

    def replies(self, turn, conversation) -> int | None:
        """How many Turns are under this one, whole: `thread_replies` exactly
        as `web._placed` counts it, from the same two helpers."""
        if not turn or not conversation:
            return None
        if conversation not in self._replies:
            from mentis.web import _reply_chain, _subtree
            rows = self._rows(conversation)[0]
            chain = _reply_chain(self.cv.corpus, [r["turn"] for r in rows])
            self._replies[conversation] = {
                t: len(kids) for t, kids in _subtree(rows, chain).items()}
        return self._replies[conversation].get(turn)


# -- executions --------------------------------------------------------------

def _exec_state(rs: dict) -> str:
    """`run_state`'s word, in the contract's five.

    `runtime-ended` -- the runtime has stopped and the record has not caught
    up -- is `failed` when its exit code is non-zero or absent, as the
    contract maps it. ONE NARROWING, said rather than hidden: where the
    runtime itself reported success (a zero exit, or its own terminal `ok`)
    calling that run failed would state the opposite of what was observed,
    so it is `unknown` until the record says how it ended.
    """
    s = rs.get("state")
    if s in ("completed", "recovered"):
        return "finished"
    if s == "failed":
        return "failed"
    if s in ("tool-running", "model-outstanding", "helper-outstanding"):
        return "running"
    if s == "not-launched":
        return "not_started"
    if s == "runtime-ended":
        return "unknown" if rs.get("_ok") else "failed"
    return "unknown"


def _runtime_ok(obs) -> bool:
    """Whether the runtime itself reported a run that ended as succeeding."""
    if not obs:
        return False
    if obs.get("exited_at") is not None:
        code = obs.get("process_exit")
    elif obs.get("ended_at") is not None:
        code = obs.get("exit_code")
    else:
        code = None
    term = obs.get("terminal")
    if term and not term.get("ok"):
        return False
    if code is not None:
        return code == 0
    return bool(term and term.get("ok"))


def _executions_of(ctx, exp_act, runtime, task) -> list[dict]:
    """Every run of ONE expectation (its own acts only), each in the
    contract's words. A request nothing has run for is one `not_started`
    row -- the honest reading of "recorded as owed; nothing has started"."""
    cv, order = ctx.cv, ctx.order
    own = cv._own_acts(exp_act["id"])
    order.prime(own)
    pos = order.key
    starts = sorted((a for a in own if a["act"] == STARTED), key=pos)
    ends = [a for a in own if a["act"] in ENDS]
    end_of = {}
    for e in sorted(ends, key=pos):
        if e.get("caused_by"):
            end_of.setdefault(e["caused_by"], e)
    closed = closed_starts(starts + ends, pos)
    last_end = max(ends, key=pos) if ends else None
    runs = (runtime or {}).get("runs")
    out = []
    for s in starts:
        end = end_of.get(s["id"])
        obs = None if end or runs is None else runs.get(s["id"])
        if end is None and s["id"] in closed:
            # CLOSED BY A LATER RUN ON THE SAME HANDLE, with no end of its own:
            # the rule `closed_starts` states. How it ended is not recorded.
            rs = {"state": "superseded", "words": "no end recorded; a later "
                  "run on the same handle ended, so it is not open"}
        else:
            rs = run_state(s, end, obs)
            rs["_ok"] = _runtime_ok(obs)
        state = _exec_state(rs)
        detail = (end or {}).get("detail") or {}
        code = detail.get("exit_code")
        if state == "finished":
            summary = (_sentences(ctx.text(end.get("turn")), 160)
                       if end and end["act"] == RETURNED else None) \
                or _clip(rs.get("words"), 160)
        elif state == "failed" and end:
            summary = _clip(_plain_line(end.get("because"))
                            or "failed; no reason recorded", 160)
        else:
            summary = _clip(rs.get("words"), 160)
        out.append({
            "expectation": exp_act["id"], "execution": s.get("execution"),
            "runtime": s.get("runtime"), "task": task, "state": state,
            "summary": summary, "started_at": iso(s.get("at")),
            "ended_at": iso(end["at"]) if end else None,
            "exit_code": code if isinstance(code, int) else None,
            "origin": ctx.link(exp_act.get("turn"),
                               exp_act.get("conversation")),
            "_actor": s.get("actor"), "_key": pos(s),
            # `run_state`'s own word, and whether the run is open by the rule
            # `trunk_status` states (no end, and after the last end) or is
            # observed going: what places started-no-end work (`_seen_open`)
            "_run": rs.get("state"),
            "_open": end is None and s["id"] not in closed and (
                last_end is None or pos(s) > pos(last_end)
                or rs.get("state") in _RUN_LIVE)})
    # A FAILURE THAT ENDED NO RUN: delivery failed before anything started.
    started_ids = {s["id"] for s in starts}
    for e in ends:
        if e.get("caused_by") in started_ids or e["act"] != FAILED:
            continue
        d = e.get("detail") or {}
        out.append({
            "expectation": exp_act["id"], "execution": e.get("execution"),
            "runtime": e.get("runtime"), "task": task, "state": "failed",
            "summary": _clip(_plain_line(e.get("because"))
                             or "failed before it started", 160),
            "started_at": None, "ended_at": iso(e.get("at")),
            "exit_code": d.get("exit_code")
            if isinstance(d.get("exit_code"), int) else None,
            "origin": ctx.link(exp_act.get("turn"),
                               exp_act.get("conversation")),
            "_actor": e.get("actor"), "_key": pos(e)})
    if not out and not any(a["act"] == "expectation-met" for a in own):
        out.append({
            "expectation": exp_act["id"], "execution": None, "runtime": None,
            "task": task, "state": "not_started", "summary": None,
            "started_at": None, "ended_at": None, "exit_code": None,
            "origin": ctx.link(exp_act.get("turn"),
                               exp_act.get("conversation")),
            "_actor": None, "_key": pos(exp_act)})
    return out


def _counts(execs) -> dict:
    c = {k: 0 for k in EXEC_STATES}
    for e in execs:
        c[e["state"]] += 1
    c["total"] = len(execs)
    return c


def _words_of(c) -> str:
    """"3 of 6 finished · 1 failed · 1 running · 1 not started"."""
    if not c["total"]:
        return "no executions recorded"
    parts = [f"{c['finished']} of {c['total']} finished"]
    parts += [f"{c[k]} {_EXEC_WORD[k]}" for k in _WORD_ORDER
              if k != "finished" and c[k]]
    return " · ".join(parts)


def _agent_words(execs) -> str:
    """"finished", "running · 1 not started", "2 running · 1 failed"."""
    if not execs:
        return "no executions recorded"
    c = _counts(execs)
    present = [k for k in _WORD_ORDER if c[k]]
    if len(present) == 1:
        k = present[0]
        return _EXEC_WORD[k] if c[k] == 1 else f"{c[k]} {_EXEC_WORD[k]}"
    first, rest = present[0], present[1:]
    head = (_EXEC_WORD[first] if c[first] == 1
            else f"{c[first]} {_EXEC_WORD[first]}")
    return " · ".join([head] + [f"{c[k]} {_EXEC_WORD[k]}" for k in rest])


# -- one trunk ---------------------------------------------------------------

def _work_tree(ctx, trunk_id):
    """The trunk's descendants, its delegated expectations and the decisions
    asked anywhere under it -- from the read's one walk (`_Ctx.descendants`)."""
    everything = ctx.descendants(trunk_id)
    delegated = {a["about"][0] for a in everything
                 if a["act"] == "work-delegated" and a["about"]}
    exps = [a for a in everything if a["act"] == "expectation-recorded"]
    children = [a for a in exps if a["id"] in delegated
                and (a.get("detail") or {}).get("expects") != "decision"]
    decisions = [a for a in exps
                 if (a.get("detail") or {}).get("expects") == "decision"]
    return everything, children, decisions


def _title(ctx, act) -> str | None:
    # A question of a decision form carries its own words; its post is the
    # asking post, whose text is not the question (P7).
    line = (_plain_line((act.get("detail") or {}).get("question"))
            or _plain_line(ctx.text(act.get("turn")))
            or _plain_line(act.get("because")))
    return _clip(line, TITLE_MAX)


def _options(raw) -> list[str]:
    out = []
    for o in raw or ():
        if isinstance(o, dict):
            label = o.get("label") or o.get("text") or o.get("name")
            if label:
                out.append(str(label))
        elif o is not None:
            out.append(str(o))
    return out


def _seen_open(execs, trunk_id, runtime) -> tuple[str, str | None]:
    """WHAT THIS PROCESS OBSERVES of the trunk's own open runs, for work the
    record says started with no end recorded: `live`, `failed`, `ended` or
    `unknown`, and why when unknown. Read only from `run_state` over what
    `_runtime_observation` holds; nothing is stored and no end is assumed.

    Any run observed going is enough to call it moving. Otherwise any run no
    process here holds leaves it unknown -- it may be running elsewhere, or
    its process may have died, and the record cannot tell those apart. Only
    when every open run was observed ending is it ended work, and `failed`
    where the runtime reported one failing.
    """
    if (runtime or {}).get("runs") is None:
        return "unknown", ("a run was recorded as started and nothing has "
                           "recorded its end, and what this server holds of "
                           "open runs could not be asked: "
                           + str((runtime or {}).get("why_not")))
    mine = [e for e in execs if e["expectation"] == trunk_id and e["_open"]]
    if any(e["_run"] in _RUN_LIVE for e in mine):
        return "live", None
    if not mine or any(e["_run"] != "runtime-ended" for e in mine):
        return "unknown", ("a run was recorded as started and nothing has "
                           "recorded its end, and no process here holds it, "
                           "so whether it is still running cannot be "
                           "established")
    return ("failed" if any(e["state"] == "failed" for e in mine)
            else "ended"), None


def _status_words(group, ts_state, c, decisions_open, owed_n, seen=None,
                  awaits=None):
    v = ts_state.get("value")
    if group == "unknown":
        return ("Unknown — could not be read" if v == "unreadable"
                else "Unknown — " + (_clip(ts_state.get("why"), 80)
                                     or "the record cannot say"))
    if group == "completed":
        return "Objective met"
    if group == "needs_you":
        if decisions_open and decisions_open == owed_n:
            ask = (f"{decisions_open} decision"
                   + ("" if decisions_open == 1 else "s"))
        else:
            ask = f"{owed_n} question" + ("" if owed_n == 1 else "s")
        if v == "claimed-met":
            return f"Objective met · {ask} for you"
        if c["running"]:
            return f"In flight · {ask} for you"
        return f"Waiting on you · {ask}"
    # in flight: open or recently ended, and not met
    progress = (f"{c['finished']} of {c['total']} executions finished"
                if c["total"] else None)
    # started with no end recorded, and its run observed ending: the words
    # of the ended work it is placed with
    if v == "failed" or (v == "started-no-end" and seen == "failed"):
        return "Stopped · last run failed — not complete"
    if v == "returned" or (v == "started-no-end" and seen == "ended"):
        return "Ended · not marked complete"
    if v == "recovered":
        return "Recovered · not claimed met — not complete"
    if v == "replied":
        return "Replied · not claimed met — not complete"
    if v == "owed":
        return "Not started · nothing has run"
    if v == "unassigned":
        return "Not started · unassigned"
    # NOT MOVING, SO NOT SAID TO BE IN FLIGHT: nothing has run since it was
    # resumed, or the record says it will not resume by itself
    if v == "resumed-no-run":
        return "Not started · " + (ts_state.get("label") or v)
    if v in STALLED:
        return ts_state.get("label") or v
    # WAITING ON WORK THAT IS NOT MOVING: what it waits on is said, never
    # that this work itself ended
    if v == "waiting-on-work" and awaits in _AWAIT_WORDS:
        label = ts_state.get("label") or ""
        what = label[len("Waiting on "):] if label.startswith(
            "Waiting on ") else label
        return (_AWAIT_WORDS[awaits] + (f" · {what}" if what else "")
                + " — not complete")
    if v in ("running", "started-no-end", "waiting-on-child"):
        return "In flight · " + (progress or ts_state.get("label") or v)
    return "In flight · " + (ts_state.get("label") or v)


#: Waiting on other work that is not moving, by what that work is
#: (`_motion`): the leading words, and the drawer's heading. Neither says this
#: work ended, stopped or completed.
_AWAIT_WORDS = {"ended": "Waiting on ended work",
                "stalled": "Waiting on work that is not moving"}
_AWAIT_HEADING = {"ended": "WAITING ON ENDED WORK — NOT COMPLETE",
                  "stalled": "WAITING ON WORK NOT MOVING — NOT COMPLETE",
                  "unknown": "WORK STATE UNKNOWN"}


def _heading(v: str | None, seen: str | None = None,
             awaits: str | None = None) -> str:
    """The drawer's heading, from the same state the Ledger groups by: work
    whose runs ended without the objective claimed met is never "in flight",
    and neither is work nothing has run for. Started with no end recorded, it
    follows what is observed of the run (`_seen_open`); waiting on other
    work, what that work is (`_motion`)."""
    if v == "waiting-on-work" and awaits in _AWAIT_HEADING:
        return _AWAIT_HEADING[awaits]
    if v == "started-no-end":
        v = {"failed": "failed", "ended": "returned",
             "unknown": None}.get(seen, v)
        if v is None:
            return "WORK STATE UNKNOWN"
    if v == "claimed-met":
        return "OBJECTIVE MET"
    if v == "failed":
        return "STOPPED — NOT COMPLETE"
    if v in ENDED or v in STALLED:
        return "ENDED — NOT MARKED COMPLETE"
    if v == "unassigned":
        return "NOT STARTED — UNASSIGNED"
    if v in NOT_STARTED:
        return "NOT STARTED — NOT COMPLETE"
    return "WORK IN FLIGHT — NOT COMPLETE"


def _motion(ctx, expectation, *, viewer, runtime,
            depth) -> tuple[str, str | None]:
    """WHAT A PIECE OF AWAITED WORK IS, by the rules this projection places
    work by: `moving`, `ended` (its runs ended and nobody claimed it met),
    `stalled` (nothing of it moves and it has not ended: not started, held,
    or itself waiting on work that does not move), `met`, or `unknown` with
    why. Read through `project`, once per read. A chain that comes back to
    itself, or runs deeper than AWAIT_DEPTH, is `unknown` -- never guessed
    to be moving."""
    if expectation in ctx.motion:
        return ctx.motion[expectation]
    if expectation in ctx.visiting:
        return "unknown", ("whether the work it waits on is moving cannot be "
                           "established: that work waits, in turn, on this "
                           "work")
    if depth > AWAIT_DEPTH:
        return "unknown", ("whether the work it waits on is moving cannot be "
                           f"established: it waits on other work more than "
                           f"{AWAIT_DEPTH} deep")
    act = ctx.cv._act(expectation)
    if act is None or act["act"] != "expectation-recorded":
        got = ("unknown", "whether the work it waits on is moving cannot be "
               f"established: {expectation} is not a request in this record")
        ctx.motion[expectation] = got
        return got
    ctx.visiting.add(expectation)
    try:
        it = project(ctx, act, viewer=viewer, runtime=runtime, _depth=depth)
    except Exception as exc:                              # noqa: BLE001
        it = {"state": "unreadable", "group": "unknown",
              "why_unknown": f"{type(exc).__name__}: {exc}"}
    finally:
        ctx.visiting.discard(expectation)
    v, awaits = it["state"], it.get("_awaits")
    if it.get("objective_met") or v == "claimed-met":
        got = "met", None
    elif v == "waiting-on-work" and awaits == "unknown":
        # already worded as not established, one link further on
        got = "unknown", it.get("why_unknown")
    elif v == "waiting-on-work" and awaits is not None:
        got = ("moving" if awaits == "moving" else "stalled"), None
    elif v in _AWAITED_MOVING or (v == "started-no-end"
                                  and it.get("_seen") == "live"):
        got = "moving", None
    elif v == "started-no-end" and it.get("_seen") in ("ended", "failed"):
        got = "ended", None
    elif v in ENDED:
        got = "ended", None
    elif v in STALLED or v in NOT_STARTED:
        got = "stalled", None
    else:
        got = "unknown", ("whether the work it waits on is moving cannot be "
                          "established: " + (it.get("why_unknown")
                                             or "its state could not be read"))
    ctx.motion[expectation] = got
    return got


def _awaits_motion(ctx, act, ts, *, viewer, runtime, depth):
    """What the work this trunk waits on is, taken together: `moving` if any
    of it moves; otherwise `unknown` if any cannot be established; otherwise
    `ended` if all of it ended without being claimed met; otherwise
    `stalled`. Only work whose wait has not ended is asked: not claimed met
    and, for delegated work, its run not ended (`awaited_state`) -- the same
    set `trunk_status` counts as still awaited."""
    awaited = [w["expectation"] for w in
               (ts["children"]["value"] or {}).get("awaits") or ()
               if not w.get("ended", w.get("met"))]
    ctx.visiting.add(act["id"])
    try:
        found = [_motion(ctx, e, viewer=viewer, runtime=runtime,
                         depth=depth + 1) for e in awaited]
    finally:
        ctx.visiting.discard(act["id"])
    kinds = {k for k, _ in found}
    if "moving" in kinds:
        return "moving", None
    if "unknown" in kinds or not found:
        return "unknown", next(
            (w for k, w in found if k == "unknown"),
            "whether the work it waits on is moving cannot be established: "
            "the record names none whose wait has not ended")
    if "ended" in kinds and kinds <= {"ended", "met"}:
        return "ended", None
    return "stalled", None


def project(ctx, act, *, viewer, runtime, full=False, _depth=0) -> dict:
    """One trunk as a WorkItem -- or, with `full`, a WorkDetail."""
    cv = ctx.cv
    why = []
    try:
        ts = trunk_status(cv, act["id"], viewer=viewer, runtime=runtime,
                          order=ctx.order)
        readable = True
    except Exception as exc:                              # noqa: BLE001
        ts = _unreadable(cv, act, exc)
        readable = False
    state = ts["state"]
    origin = ctx.link(act.get("turn"), act.get("conversation")) or {
        "turn": act.get("turn"), "number": None,
        "conversation": act.get("conversation"),
        "conversation_name": ctx.conversation_name(act.get("conversation"))}
    try:
        replies = ctx.replies(act.get("turn"), act.get("conversation"))
    except Exception:                                     # noqa: BLE001
        replies = None

    from mentis.operational import discovery, follow_up_of
    gravity = discovery(cv, act["id"])
    base = {"expectation": act["id"], "title": _title(ctx, act),
            "state": state["value"] or "unreadable",
            "state_source": state["source"], "origin": origin,
            "replies": replies,
            "follow_up": follow_up_of(cv, gravity["origin"]),
            "generation": gravity["generation"]}
    if not readable:
        empty = _counts([])
        item = {**base, "group": "unknown",
                **_stage.unknown(state.get("why") or "could not be read"),
                "status_words": _status_words("unknown", state, empty, 0, 0),
                "objective_met": None, "met_at": None, "decisions_open": 0,
                "executions": empty, "agents": [],
                "last_activity_at": iso(act.get("at")),
                "why_unknown": state.get("why")}
        if full:
            item.update(heading="WORK STATE UNKNOWN", completes_when=None,
                        completes_when_why=state.get("why"),
                        executions_words="unknown — " + (state.get("why")
                                                         or ""),
                        agents_detail=[], decisions=[], outcome=None,
                        started_at=None)
        return item

    everything, children, decision_acts = _work_tree(ctx, act["id"])
    order = ctx.order
    order.prime(everything)
    own_met = sorted((a for a in cv._own_acts(act["id"])
                      if a["act"] == "expectation-met"), key=order.key)
    met = state["value"] == "claimed-met"

    # -- decisions under this work, and which the viewer owes --------------
    decisions = []
    for d in decision_acts:
        try:
            s = ctx.state(d["id"])
        except Exception as exc:                          # noqa: BLE001
            why.append(f"a decision under this work could not be read: "
                       f"{type(exc).__name__}: {exc}")
            continue
        # A question of a decision form carries its own words; its post is
        # the asking post, or none yet (P7/P9).
        q = (d.get("detail") or {}).get("question") or ctx.text(d.get("turn"))
        on = cv.asked_on(d) if (d.get("detail") or {}).get("form")             else d.get("turn")
        decisions.append({
            "expectation": d["id"],
            "question": _clip(" ".join((q or "").split()), 400)
            or _clip(s.get("because"), 400),
            "options": _options(s.get("options")),
            "answered": bool(s["response_present"]),
            "owed_by": s["expected_of"],
            "owed_by_alias": _name(cv, s["expected_of"]),
            "origin": ctx.link(on, d.get("conversation"))})
    decisions_open = (sum(1 for d in decisions if not d["answered"]
                          and d["owed_by"] == viewer)
                      if viewer is not None else 0)
    owed = ts["you_owe"]["value"]
    if owed is None:
        why.append(ts["you_owe"].get("why") or "what the viewer owes is unknown")
    owed_ids = {r["expectation"] for r in owed or ()} | {
        d["expectation"] for d in decisions
        if not d["answered"] and viewer is not None and d["owed_by"] == viewer}

    # -- executions, the trunk's and every delegated descendant's -----------
    execs = _executions_of(ctx, act, runtime, base["title"])
    for ch in children:
        execs += _executions_of(ctx, ch, runtime, _title(ctx, ch))
    if (runtime or {}).get("runs") is None and any(
            e["state"] == "unknown" for e in execs):
        why.append("what this server holds of open runs could not be asked: "
                   + str((runtime or {}).get("why_not")))
    c = _counts(execs)
    # STARTED, NO END RECORDED: placed by what is observed of its runs
    seen, seen_why = (_seen_open(execs, act["id"], runtime)
                      if state["value"] == "started-no-end" else (None, None))
    words_state = state
    if seen == "unknown":
        why.insert(0, seen_why)
        words_state = {**state, "why": seen_why}
    # WAITING ON OTHER WORK: placed by what that work is
    awaits, awaits_why = (_awaits_motion(ctx, act, ts, viewer=viewer,
                                         runtime=runtime, depth=_depth)
                          if state["value"] == "waiting-on-work"
                          else (None, None))
    if awaits == "unknown":
        why.insert(0, awaits_why)
        words_state = {**state, "why": awaits_why}

    # -- group: most urgent wins --------------------------------------------
    if owed_ids:
        group = "needs_you"
    elif met:
        group = "completed"
    elif (state["source"] == UNKNOWN or seen == "unknown"
          or awaits == "unknown"):
        group = "unknown"
    else:
        group = "in_flight"

    # -- agents: the carrier first, then each delegated carrier and runner --
    carrier = ts["carrier"]["value"]["participant"]
    carrier_of = {act["id"]: carrier}
    # `trunk_status` already read each direct child's carrier; only a child it
    # did not itemise (deeper, or past CHILDREN_SHOWN) is asked here.
    shown = {k["expectation"]: k["carrier"]
             for k in ts["children"]["value"]["items"]}
    for ch in children:
        carrier_of[ch["id"]] = (shown[ch["id"]] if ch["id"] in shown
                                else ctx.state(ch["id"])["expected_of"])
    who = list(carrier_of.values())
    who += [e["_actor"] for e in sorted(execs, key=lambda e: e["_key"])]
    agents = [p for p in dict.fromkeys(who) if p]
    last = ts["last_act"]["value"] or {}

    # -- stage: where the work stands, not whether its runs ended -----------
    try:
        staged = _stage.stage_of(
            ctx, act, state=words_state, everything=everything,
            children=children, execs=execs, owed_n=len(owed_ids), met=met,
            seen=seen, awaits=awaits)
    except Exception as exc:                              # noqa: BLE001
        staged = _stage.unknown(f"its stage could not be read: "
                                f"{type(exc).__name__}: {exc}")

    item = {**base, "group": group, **staged,
            "status_words": _status_words(group, words_state, c,
                                          decisions_open, len(owed_ids),
                                          seen, awaits),
            "objective_met": met,
            "met_at": iso(own_met[0]["at"]) if met and own_met else None,
            "decisions_open": decisions_open,
            "executions": c,
            "agents": [_name(cv, p) for p in agents],
            "last_activity_at": iso(last.get("at")),
            "why_unknown": "; ".join(dict.fromkeys(why)) or None,
            # for the scoped read's placing only; never sent
            "_seen": seen, "_awaits": awaits}
    _continued(ctx, act, item, viewer=viewer, runtime=runtime, depth=_depth)
    if not full:
        return item

    # -- the drawer --------------------------------------------------------
    by_agent = {p: [] for p in agents}
    for e in sorted(execs, key=lambda e: e["_key"]):
        p = e["_actor"] or carrier_of.get(e["expectation"])
        if p:
            by_agent.setdefault(p, []).append(e)
    agents_detail = [{
        "participant": p, "alias": _name(cv, p),
        "state_words": _agent_words(xs),
        "executions": [{k: v for k, v in x.items() if not k.startswith("_")}
                       for x in xs]} for p, xs in by_agent.items()]

    done_when = [w.get("done_when") for w in (ts["workflow"]["value"] or ())
                 if (w.get("done_when") or "").strip()]
    results = [a for a in everything if a["act"] in (RETURNED, RECOVERED)]
    newest = max(results, key=order.key) if results else None
    outcome = None
    if newest is not None:
        outcome = (_sentences(ctx.text(newest.get("turn")))
                   if newest["act"] == RETURNED else None) or _sentences(
            ((newest.get("detail") or {}).get("text")) or newest.get("because"))
    starts = [e["started_at"] for e in execs if e["started_at"]]
    del item["_seen"], item["_awaits"]
    item.update(
        heading=_heading(state["value"], seen, awaits),
        # WHAT COMPLETES IT, AS RECORDED. The contract named `detail.expects`,
        # but that is the expectation's KIND ("result", "decision") and says
        # nothing about completion. The only recorded words for it are a
        # governing Workflow's `done_when`, so those are said, and otherwise
        # nothing is.
        completes_when=" / ".join(dict.fromkeys(done_when)) or None,
        completes_when_why=None if done_when else NO_COMPLETES_WHEN,
        executions_words=_words_of(c),
        agents_detail=agents_detail,
        decisions=decisions,
        outcome=outcome,
        started_at=min(starts) if starts else None,
        workflow=_workflow_view(cv, act, ts))
    return item


def _workflow_view(cv, act, ts) -> dict:
    """WHICH WORKFLOW GOVERNS THIS WORK, AND HOW IT CAME TO: the current
    Workflow and its origin, every change with its reason and evidence
    (`workflow_change.history`), and the activity progress the work status
    already computes (`trunk_status`'s `workflow`). All read from the record;
    one block that cannot be read says why instead of failing the drawer."""
    from mentis.conversation import workflow_change
    try:
        view = workflow_change.history(cv, act["id"])
    except Exception as exc:                              # noqa: BLE001
        view = {"current": [], "origin": "unknown", "history": [],
                "why_unknown": f"the Workflow history could not be read: "
                               f"{type(exc).__name__}: {exc}"}
    progress = ts.get("workflow") or {}
    return {**view, "progress": progress.get("value") or [],
            "progress_source": progress.get("source"),
            **({"progress_why": progress.get("why")}
               if progress.get("source") == "unknown" else {})}


#: How many continuations deep a request's stage is followed.
CONTINUATION_DEPTH = 3
#: The stages a continuation's stage replaces. A request with its own run
#: live, or its own question open to the owner, keeps its own.
_FOLDABLE = ("blocked", "awaiting_review", "parked", "ready_to_deploy",
             "ended", "not_started")


def _continued(ctx, act, item, *, viewer, runtime, depth) -> None:
    """A REQUEST THE OWNER CONTINUED names its newest continuation, and reads
    by that continuation's stage once it is not itself moving.

    The owner's reply under a request that dispatches its carrier again is a
    request of its own (`continuations_of`: same requester, authority whose
    origin is this work), so its runs, reviews and commits are its own and
    the original kept reading from where it stopped -- "Blocked: the review
    found problems to fix" for days after the continuation's re-review had
    passed (owner, 2026-10-26). While the continuation is pending or running
    the original already reads Building (a continuation is this work
    running: `claim_resumption`); once it has ended, the original says it
    was continued and carries the continuation's stage. `continued_by`
    names the continuation either way. A request with its own run live, or
    its own question open to the owner, keeps its own stage.
    """
    cv = ctx.cv
    try:
        conts = [cv._act(c) for c in cv.continuations_of(act["id"])]
    except Exception:                                     # noqa: BLE001
        return
    conts = [c for c in conts if c]
    if not conts:
        return
    newest = max(conts, key=ctx.order.key)
    link = ctx.link(newest.get("turn"), newest.get("conversation")) or {}
    item["continued_by"] = {"expectation": newest["id"], "origin": link}
    if depth >= CONTINUATION_DEPTH or item.get("stage") not in _FOLDABLE:
        return
    try:
        sub = project(ctx, newest, viewer=viewer, runtime=runtime,
                      _depth=depth + 1)
    except Exception:                                     # noqa: BLE001
        return
    item["continued_by"].update(stage=sub.get("stage"),
                                stage_words=sub.get("stage_words"))
    if sub.get("stage") in (None, "unknown"):
        return
    where = f"#{link['number']}" if link.get("number") else "later"
    item["stage"] = sub["stage"]
    item["stage_words"] = f"Continued at {where} · {sub['stage_words']}"
    item["stage_source"] = sub.get("stage_source") or item.get("stage_source")
    item["stage_evidence"] = {**(item.get("stage_evidence") or {}),
                              "continued_by": newest["id"]}


# -- the two reads -----------------------------------------------------------

def _trunks(cv, conversation=None) -> list[dict]:
    if conversation:
        rows = [a for a in cv.history(conversation=conversation)
                if a["act"] == "expectation-recorded"]
    else:
        rows = [a for a in cv.history(act="expectation-recorded")
                if a.get("conversation")]
    # `is_trunk`'s own rule, asked of every row from ONE read of the record's
    # delegations instead of two `caused_by` reads per row.
    handed = {}
    try:
        for d in cv.history(act="work-delegated"):
            if d.get("caused_by") and d["about"]:
                handed.setdefault(d["caused_by"], set()).add(d["about"][0])
    except Exception:                                     # noqa: BLE001
        handed = None

    def trunk(a):
        if handed is None:
            return is_trunk(cv, a)
        if (a.get("detail") or {}).get("expects") in ASKED_UNDER_WORK:
            return False
        if a["id"] in handed.get(a.get("caused_by"), ()):
            return a["id"] in handed
        return True

    out = []
    for a in rows:
        try:
            if trunk(a):
                out.append(a)
        except Exception:                                 # noqa: BLE001
            # WHETHER IT IS A TRUNK COULD NOT BE READ: it is not dropped. It
            # is shown as work whose state could not be read.
            out.append(a)
    return out


def _newest(item):
    at = item.get("met_at") if item["group"] == "completed" else None
    return at or item.get("last_activity_at") or ""


def _open_now(cv):
    """Every expectation nobody has answered yet, Brain-wide, by id: one read
    of what is owed, which the scope check asks of every trunk."""
    return {r["expectation"]: r for r in cv.expectations(open_only=True)}


def _met_ids(cv) -> set:
    """Every expectation somebody claimed met, Brain-wide, from one read."""
    return {a.get("caused_by") for a in cv.history(act="expectation-met")}


def _found_ids(cv) -> set:
    """Every expectation kept as discovered work, Brain-wide, from one read:
    `is_finding`'s rule without a read per trunk."""
    return {x for a in cv.history(act="work-discovered")
            for x in (a["about"] or ())}


def _in_scope(ctx, act, since, open_now, viewer, met_ids=()) -> bool:
    """WHETHER A SCOPED READ COMPUTES THIS TRUNK'S STATUS AT ALL. Asked before
    any status, from the acts under it alone, and generous: it may keep work
    the status then leaves out, never the other way round.

    Kept: anything under it at or after `since`; anything under it the viewer
    still owes; an unanswered decision or other open expectation under it (it
    may be waiting on a decision or a child); other work it declared it waits
    on (`work-awaited`) that nobody has claimed met; a run started under it
    whose end is not recorded (it may be running); and a trunk whose acts
    cannot be walked, which is then shown as unknown rather than dropped.
    """
    try:
        below = ctx.descendants(act["id"])
    except Exception:                                     # noqa: BLE001
        return True
    acts = [act, *below]
    if max(a.get("at") or 0 for a in acts) >= since:
        return True
    if any(a["act"] == "work-awaited" and a["about"]
           and a["about"][0] not in met_ids for a in acts):
        return True
    # Only a decision, an input or a delegated child can hold work waiting.
    # Discovered work found under it is caused by it too, and holds nothing.
    delegated = {a["about"][0] for a in below
                 if a["act"] == "work-delegated" and a["about"]}
    for a in acts:
        if a["act"] != "expectation-recorded" or a["id"] not in open_now:
            continue
        r = open_now[a["id"]]
        if ((viewer is not None and r["expected_of"] == viewer)
                or r["expects"] in ASKED_UNDER_WORK
                or a["id"] in delegated):
            return True
    ended = {a.get("caused_by") for a in below if a["act"] in ENDS}
    return any(a["act"] == STARTED and a["id"] not in ended for a in below)


def _left_out_unseen(ctx, act, open_now, found) -> str:
    """Why `_in_scope` left a trunk out, from the same walk: still owed with
    no run ever started for it is `not_started` (or `discovered_unassigned`);
    anything else had nothing under it since then and is `inactive`."""
    row = open_now.get(act["id"])
    if row is None:
        return "inactive"
    try:
        below = ctx.descendants(act["id"])
    except Exception:                                     # noqa: BLE001
        return "inactive"
    if any(a["act"] == STARTED and a.get("caused_by") == act["id"]
           for a in below):
        return "inactive"
    if row.get("unassigned") and act["id"] in found:
        return "discovered_unassigned"
    return "not_started"


def _scoped_group(cv, act, item, *, since, completed_since, found=None):
    """Where a scoped read puts an item: `(group, None)`, or `(None, reason)`
    to leave it out, the reason one of LEFT_OUT.

    In flight is moving work, whenever it began; being touched since `since`
    puts nothing there. Started with no end recorded, the run as observed
    decides (`project` has already made the unobservable `unknown`). Work
    nothing has run for is never In flight. Waiting on other work, the work
    it waits on decides (`_motion`): moving is In flight, and otherwise it is
    placed as ended work is, its own state untouched. Ended work, and work
    the record says will not resume by itself, is `returned` when active
    since then."""
    group = item["group"]
    if group in ("needs_you", "unknown"):
        return group, None
    if group == "completed":
        met = item["met_at"]
        window = completed_since if completed_since is not None else since
        return ((group, None) if met is not None and parse_since(met) >= window
                else (None, "completed_earlier"))
    v = item["state"]
    if (v in MOVING or (v == "started-no-end" and item.get("_seen") == "live")
            or (v == "waiting-on-work" and item.get("_awaits") == "moving")):
        return "in_flight", None
    if v in NOT_STARTED:
        finding = (act["id"] in found if found is not None
                   else cv.is_finding(act["id"]))
        return None, ("discovered_unassigned"
                      if v == "unassigned" and finding else "not_started")
    last = item["last_activity_at"]
    if last is None or parse_since(last) < since:
        return None, "inactive"
    return "returned", None


def overview(cv, *, viewer, runtime, conversation=None, completed_since=None,
             limit=None, active_since=None) -> dict:
    """`WorkOverview`: every trunk once, in exactly one group -- or, with
    `active_since`, today's Ledger (see the module docstring)."""
    ctx = _Ctx(cv)
    since = parse_since(completed_since)
    active = parse_since(active_since)
    trunks = _trunks(cv, conversation)
    left_out = {k: 0 for k in LEFT_OUT}
    found = None
    if active is not None:
        open_now, met_ids, found = _open_now(cv), _met_ids(cv), _found_ids(cv)
        trunks_in = []
        for a in trunks:
            if _in_scope(ctx, a, active, open_now, viewer, met_ids):
                trunks_in.append(a)
            else:
                left_out[_left_out_unseen(ctx, a, open_now, found)] += 1
    else:
        trunks_in = trunks
    items = []
    for a in trunks_in:
        item = project(ctx, a, viewer=viewer, runtime=runtime)
        if active is not None:
            item["group"], reason = _scoped_group(
                cv, a, item, since=active, completed_since=since, found=found)
            if item["group"] is None:
                left_out[reason] += 1
                continue
        elif since is not None and item["group"] == "completed":
            met = item["met_at"]
            if met is None or parse_since(met) < since:
                continue
        item.pop("_seen", None)
        item.pop("_awaits", None)
        items.append(item)
    counts = {g: 0 for g in GROUPS}
    for it in items:
        counts[it["group"]] += 1
    counts["all"] = len(items)
    stage_counts = {s: 0 for s in STAGES}
    for it in items:
        stage_counts[it.get("stage") or "unknown"] += 1
    ordered, omitted = [], {g: 0 for g in GROUPS}
    cap = None if limit in (None, "") else max(0, int(limit))
    for g in GROUPS:
        mine = sorted((i for i in items if i["group"] == g),
                      key=_newest, reverse=True)
        if cap is not None and len(mine) > cap:
            omitted[g] = len(mine) - cap
            mine = mine[:cap]
        ordered += mine
    return {"viewer": viewer, "counts": counts, "items": ordered,
            "omitted": omitted,
            # BY STAGE, over the same items as `counts` (before `limit`)
            "stage_counts": stage_counts,
            # A FALSE ZERO IS NOT SAID: with nobody looking, Needs you is
            # unknown, and why travels with it.
            "needs_you_unknown": viewer is None,
            "needs_you_why": NO_VIEWER if viewer is None else None,
            "scope": None if active is None else {
                "active_since": iso(active),
                "left_out": len(trunks) - len(items),
                # the same count, by reason; sums to `left_out`
                "left_out_by": left_out,
                "why": "neither needs you nor is moving, and nothing under "
                       "it since then; or not started; or completed before "
                       "then; or unassigned discovered work"},
            "runtime_why_not": (runtime or {}).get("why_not")}


def detail(cv, expectation, *, viewer, runtime) -> dict | None:
    """`WorkDetail` for one trunk, or None when it is not a trunk."""
    act = cv._act(expectation)
    if act is None or act["act"] != "expectation-recorded":
        return None
    try:
        trunk = is_trunk(cv, act)
    except Exception:                                     # noqa: BLE001
        trunk = True          # unreadable work is still work; said as unknown
    if not trunk:
        return None
    return project(_Ctx(cv), act, viewer=viewer, runtime=runtime, full=True)


def owner_of(cv) -> str | None:
    """The viewer when none is named: this Brain's owner Participant, as the
    baseline identifies them. None where the record names none -- and then
    what anybody owes is UNKNOWN, never nothing."""
    from mentis.conversation.owner import _owner
    return _owner(cv)
