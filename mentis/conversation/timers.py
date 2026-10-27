"""A timer in a post: each person's starts and stops, and what they add up to.

TIMER BLOCK (owner decisions T1-T4, T6; plan adm-4fc92741cf96, package A).
A ```timer version=1 name=... box=25m break=5m``` block in a Turn is a
stopwatch with an optional time box. Its Markdown says only what the timer is
(`ui/src/experimental/spec/timer.ts`); what it has counted is kept here.

  LEDGER        Each person's own response set on the block, mode `each`,
                holder = that person (T3; `responses.open_set`). No new
                table: the set is the one forms use.
  MARK          `timer-mark`, `in-response-set` that set:
                {action: start|stop|continue|box-end|break-end, at, run,
                replaces[], reason?, problems[], direction?}. `at` is ISO-8601
                UTC. `run` is the start mark the mark belongs to (a start's
                own run is itself).

KEPT EXACTLY AS ANSWERS ARE. A mark is not knowledge (`timer-mark` declares no
`knowing` and `standing_apt` is False), no generic door writes one
(`versions.GENERIC_WRITE_CLOSED`), nothing deletes one, a deleted post takes
no new mark (`versions.inert_refusal`), and a write carrying an operation key
is one occurrence however often it is sent (`anchors.keyed`).

NOTHING IS STORED BUT THE MARKS. Runs, today, total, the box and the check-in
are read from the marks every time (`timer_state`), at the moment asked, in
the viewer's own time zone. No background job runs, so a closed tab or a
sleeping machine loses nothing and changes nothing.

  WHEN          `at` is the moment the server writes a start, continue,
                box-end or break-end. Only a STOP may say another time: the
                real time a run ended (T4), which must lie between that run's
                start and now, and before the next run's start.
  CHECK-IN (T6) Two hours after a run's start, or after its last `continue`,
                the timer asks "Still going?". An answer within
                CHECKIN_GRACE of that moment is an answer in time: Continue
                (a `continue` mark; the next check-in is two hours after it),
                Stop now, or "I stopped at ...". UNANSWERED PAST THE GRACE IS
                FORGOTTEN: the run is read as ending at the check-in moment
                ("forgotten, counted to the 2h check-in"), and nothing pressed
                later brings the forgotten hours back. Continue then leaves it
                capped and STARTS A NEW RUN now ("Start fresh"); Stop now
                closes it AT THE CHECK-IN ("Stop at the check-in"); only "I
                stopped at T", a stop with the real time (start < T <= now),
                counts past the check-in.
  CORRECTIONS   A stop on a run that already has one must name it in
                `replaces`, and gives the corrected time. Two stops replacing
                the same one are both kept and the run reads as a CONFLICT,
                counted to the earlier of them, until a stop names both.
  TWO STARTS    A start while a run is going is recorded WITH A PROBLEM, not
                refused (as a wrong answer is), and names the run it fell in
                (`run`). It is kept and is NEVER a run, whatever is corrected
                later: starts and stops are paired by the run they name, not
                by their position in time.
  BOXES         From the run's start and the block's box= and break=: box,
                break, box, ... The clock never stops on its own. `box-end`
                and `break-end` marks are a record of what the browser
                showed; no total depends on them.
  TODAY         From the viewer's local midnight. The browser sends its IANA
                zone and the server finds that day's midnight with zoneinfo,
                so a clock-change day is right; failing that, the browser's
                own local midnight; failing both, its current UTC offset.

WHO WRITES (A4, R1-R2, and the owner's constraint).
  A PERSON marks their OWN ledger: holder = whoever marks, and nothing more
  is asked of them. A person is never treated as an agent.
  AN AGENT marks only on the owner's explicit direction, never by itself,
  and only into the ledger of the owner who directed it, attributed to the
  agent, with the direction on the mark. Every one of these must hold:
    a. the direction is the request the agent's CURRENT run carries (the
       tool passes the run's own request; the agent cannot name another);
    b. the owner made that request of this agent, and it is still OPEN: not
       answered, met or withdrawn;
    c. the owner's request Turn names THIS timer exactly, as a reference
       `ent-<post>#<name>` (`reference`), in its text or a reference part.
       A bare word never counts, nor the same name on another post;
    d. the authority ends with that run: once any run of the request has
       ended, or another run has marked under it, it no longer holds, and a
       later run needs a new direction.
  No action word is read: the scope is "use this timer during this run".

ABOUT (R6). about="ent-..., ent-..." names the Topics, Conversations or posts
the timer's time is spent on. "Time spent on X" (`time_spent`) is one
person's runs, summed across every timer whose CURRENT post version names X,
read when asked: no Kind, no stored total, and an edit to about= moves that
timer's time with it.

NOTHING FROM OUTSIDE `mentis.conversation` IS IMPORTED, as in `responses`.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from . import responses
from .anchors import keyed
from .versions import Refused, deletion_of, inert_refusal, supersedes_relation

TIMER_MARK = responses.TIMER_MARK
ACTIONS = ("start", "stop", "continue", "box-end", "break-end")
#: How long a run goes before the timer asks whether it is still going (T6).
CHECK_IN_S = 2 * 3600
#: HOW LONG AFTER THE CHECK-IN AN ANSWER STILL COUNTS AS IN TIME (R3). Past
#: it the run is forgotten, capped at the check-in, whatever is pressed. One
#: named constant: the owner is being asked whether 15 minutes is right.
CHECKIN_GRACE = 15 * 60
#: The answers the check-in offers while it is answered in time.
CHECK_IN_OPTIONS = ("continue", "stop", "stopped-at")
#: The same answers once the run is forgotten, the primary first, and what
#: each does then (R3).
FORGOTTEN_OPTIONS = ("stopped-at", "continue", "stop")
FORGOTTEN_LABELS = {"stopped-at": "I stopped at...",
                    "continue": "Start fresh",
                    "stop": "Stop at the check-in"}
#: What a forgotten run says it was counted to.
FORGOTTEN_SAYS = "forgotten, counted to the 2h check-in"
#: Bounds on a viewer's offset from UTC, in minutes.
MAX_OFFSET = 14 * 60
#: The longest a day can be, with a clock change: a local midnight the
#: browser sends lies at most this far before now.
LONGEST_DAY_S = 26 * 3600
#: A timer named exactly, as an owner's direction must name it (R1c):
#: `ent-<post>#<name>`. Its name follows the block-name rule.
TIMER_REF = re.compile(r"(?<![A-Za-z0-9-])(ent-[0-9a-f]{6,})#"
                       r"([a-z][a-z0-9-]{0,39})(?![A-Za-z0-9-])")
#: What an about= reference may name (R6).
ABOUT_KINDS = {"topic": "Topic", "conversation": "Conversation",
               responses.CONTRIBUTION: "post"}


# -- time ---------------------------------------------------------------------

def iso(t: float) -> str:
    """Seconds since the epoch as ISO-8601 UTC, to the second."""
    return datetime.fromtimestamp(int(t), timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def epoch(text) -> float:
    """An ISO-8601 time WITH its offset (or Z) as seconds; refused otherwise."""
    if not isinstance(text, str) or not text.strip():
        raise Refused({"error": "a time is ISO-8601 with its offset, e.g. "
                                "2026-10-25T14:30:00Z", "at": text})
    s = text.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        raise Refused({"error": "that is not an ISO-8601 time, e.g. "
                                "2026-10-25T14:30:00Z", "at": text})
    if d.tzinfo is None:
        raise Refused({"error": "a time needs its offset from UTC (Z, or "
                                "+01:00 ...), or it could be any of 24 hours",
                       "at": text})
    return d.timestamp()


def local_midnight(now: float, utc_offset: int) -> float:
    """The start of the viewer's day, as seconds since the epoch. The
    offset is the viewer's, in minutes east of UTC."""
    local = now + utc_offset * 60
    return (local // 86400) * 86400 - utc_offset * 60


def zone_midnight(now: float, zone) -> float:
    """The start of the day `now` falls in, in that zone (a `ZoneInfo`),
    clock changes included. A midnight the clocks skip is the moment they
    jumped: the first instant of that local date."""
    d = datetime.fromtimestamp(now, zone).date()
    return datetime(d.year, d.month, d.day, tzinfo=zone).timestamp()


def _offset(utc_offset) -> int:
    if utc_offset is None:
        return 0
    if isinstance(utc_offset, bool) or not isinstance(utc_offset, int)             or abs(utc_offset) > MAX_OFFSET:
        raise Refused({"error": "utc_offset is the viewer's offset from UTC "
                                "in whole minutes east (-840 to 840)",
                       "utc_offset": utc_offset})
    return utc_offset


def _zone(tz):
    """The `ZoneInfo` for an IANA name, or None when this server cannot read
    it (an unknown name, or no time zone data installed)."""
    if not isinstance(tz, str) or not tz.strip() or len(tz) > 64:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz.strip())
    except Exception:                                     # noqa: BLE001
        return None


def day_start(now: float, *, tz=None, midnight=None, utc_offset=None
              ) -> tuple[float, dict]:
    """(the viewer's local midnight, how it was found) -- R5.

    The browser's IANA zone first, read with zoneinfo, so a day the clocks
    change is right. Without one the server can read, the local midnight the
    browser worked out itself. Only when neither is given, its current
    offset from UTC, which is wrong by the change on a clock-change day."""
    zone = _zone(tz)
    if zone is not None:
        return zone_midnight(now, zone), {"today_by": "zone", "zone": tz}
    said = {"zone_not_read": tz} if tz else {}
    if midnight not in (None, ""):
        m = epoch(midnight)
        if not (now - LONGEST_DAY_S < m <= now):
            raise Refused({"error": "midnight is the viewer's own local "
                                    "midnight today: at most 26 hours before "
                                    "now, and not after it",
                           "midnight": midnight, "now": iso(now)})
        return m, {"today_by": "midnight", **said}
    off = _offset(utc_offset)
    return local_midnight(now, off), {"today_by": "offset", **said}


# -- the block and its ledger --------------------------------------------------

def _timer(corpus, root, part, block) -> tuple[dict, str]:
    """The block's own reading (box, break, title) and the post version, by
    the UI's reader. Refused for anything that is not a savable timer."""
    check, version = responses._block_check(corpus, root, part, block, {})
    responses._refuse_unsaveable(check, block)
    if check.get("checked") and check.get("type") != "timer":
        raise Refused({"error": f"name={block} is a {check.get('type')}, not "
                                "a timer", "block": block,
                       "type": check.get("type")})
    return check, version


def _block_info(check) -> dict:
    t = check.get("timer") or {}
    return {"box": t.get("box"), "break": t.get("break"),
            "title": t.get("title"), "about": list(t.get("about") or []),
            "checked": bool(check.get("checked")),
            **({} if check.get("checked")
               else {"says": responses.NOT_CHECKED_HERE,
                     "why_not": check.get("why_not")})}


def ledger(cv, post, block, holder, *, part=0) -> str | None:
    """The holder's own set on this timer, or None when they have none yet.
    Reads; never opens one."""
    root = responses.post_root(cv.corpus, post)
    for s in responses.sets_on(cv, root):
        b = s["body"]
        if (b.get("part"), b.get("block"), b.get("mode"), b.get("holder")) \
                == (part, block, "each", holder) and not b.get("started_from"):
            return s["id"]
    return None


def marks_in(cv, sid) -> list[dict]:
    """Every mark in the set, in the order written."""
    return responses._members(cv.corpus, sid, TIMER_MARK)


# -- an owner's direction -------------------------------------------------------

def reference(post, block) -> str:
    """How an owner names this timer to an agent: `ent-<post>#<name>`."""
    return f"{post}#{block}"


def _said(entry) -> list[str]:
    """Every string a Turn's parts say: its text, and any reference part."""
    out = []
    for p in (entry.get("body") or {}).get("parts") or []:
        if isinstance(p, dict):
            out += [p[k] for k in ("text", "ref", "id", "reference")
                    if isinstance(p.get(k), str)]
    return out


def names_timer(corpus, entry, root, block) -> bool:
    """Does this Turn name THIS timer exactly: `ent-<post>#<name>`, the post
    being this one (any version of it) and the name this block's? A bare
    word never counts, nor the same name on another post (R1c)."""
    for said in _said(entry):
        for post, name in TIMER_REF.findall(said):
            if name != block:
                continue
            try:
                if corpus.read([post]) and                         responses.post_root(corpus, post) == root:
                    return True
            except Exception:                             # noqa: BLE001
                continue
    return False


def _directed(cv, direction, *, by, owner, root, block, execution) -> dict:
    """The owner's direction this agent's mark acts on, checked; refused
    otherwise. Every condition of R1 (the module docstring) must hold, and
    the refusal says which did not: an agent never marks a timer by itself."""
    corpus = cv.corpus

    def no(why):
        raise Refused({"error": "an agent starts or stops a timer only when "
                                "the owner explicitly asked for it, and never "
                                "by itself: " + why + ". Nothing was marked",
                       "needs": "direction", "block": block,
                       "reference": reference(root, block)})
    if not isinstance(direction, str) or not direction.strip():
        no("this run carries no request from the owner")
    if not isinstance(execution, str) or not execution.strip():
        no("this mark is not made by a run, so no run's request can direct it")
    try:
        st = cv.expectation_state(direction)
    except ValueError:
        no(f"{direction} is not a request anybody made")
    if owner is None or st.get("requested_by") != owner:
        no("the request this run carries was not made by the owner")
    if st.get("expected_of") != by:
        no("the request this run carries was not made of you")
    if st.get("response_present") or st.get("satisfied_by")             or st.get("withdrawn"):
        no("the request this run carries is no longer open: it was answered, "
           "met or withdrawn")
    got = corpus.read([st["turn"]]) if st.get("turn") else []
    turn = got[0] if got else None
    if turn is None or turn.get("attributed_to") != owner:
        no("the request is not in a Turn the owner wrote")
    if not names_timer(corpus, turn, root, block):
        no("the owner's request does not name this timer exactly; it must "
           f"say {reference(root, block)} (the post and the timer's name)")
    # (d) THE AUTHORITY ENDS WITH THE RUN. Once a run of this request has
    # ended, or another run has marked under it, this is a later run.
    acts = cv._own_acts(direction)
    from . import RUN_ENDS
    if any(a["act"] in RUN_ENDS for a in acts):
        no("a run of that request has already ended, and the owner's "
           "direction ended with it; a later run needs a new direction")
    if any(a["act"] == "timer-marked" and a.get("execution")
           and a["execution"] != execution for a in acts):
        no("another run already marked a timer under that request, and the "
           "owner's direction ended with that run; a later run needs a new "
           "direction")
    return {"expectation": direction, "turn": st["turn"],
            "execution": execution}


# -- reading ------------------------------------------------------------------

def _heads(marks) -> list[dict]:
    replaced = {r for m in marks for r in (m["body"].get("replaces") or [])}
    return [m for m in marks if m["id"] not in replaced]


def _at(m) -> float:
    return epoch(m["body"]["at"])


def _order(marks) -> list[dict]:
    """By `at`, ties kept in the order written."""
    return [m for _, _, m in sorted(
        ((_at(m), i, m) for i, m in enumerate(marks)), key=lambda x: x[:2])]


def _check_in_of(start, conts) -> float:
    """When this run's check-in is due: two hours after its start, or after
    its last continue given in time (by the check-in plus the grace)."""
    due = start + CHECK_IN_S
    for c in sorted(conts):
        if c > due + CHECKIN_GRACE:
            break
        due = max(due, c + CHECK_IN_S)
    return due


def runs_of(marks, now) -> tuple[list[dict], list[dict]]:
    """(runs, problems): every run the head marks make, oldest first, each
    with how it ended and the moment it is counted to; and what the marks
    say is wrong. Pure.

    PAIRED BY RUN, NOT BY POSITION (R4). Each stop and continue names its
    run; a start that names another run is a second start while that run
    was going, and is never a run itself, whatever is corrected later."""
    heads = _heads(marks)
    by_run: dict[str, list[dict]] = {}
    for m in heads:
        if m["body"]["action"] != "start" and m["body"].get("run"):
            by_run.setdefault(m["body"]["run"], []).append(m)
    runs, problems = [], []
    for m in marks:
        for p in m["body"].get("problems") or []:
            problems.append({"mark": m["id"], "action": m["body"]["action"],
                             "at": m["body"]["at"], "problem": p})
    starts = _order([m for m in heads if m["body"]["action"] == "start"])
    again = [s for s in starts
             if s["body"].get("run") not in (None, s["id"])]
    for s in starts:
        if s in again:
            continue
        start = _at(s)
        mine = by_run.get(s["id"], [])
        stops = _order([m for m in mine if m["body"]["action"] == "stop"])
        conts = [_at(m) for m in mine if m["body"]["action"] == "continue"]
        check_in = _check_in_of(start, conts)
        run = {"run": s["id"], "start": s["body"]["at"], "by":
               s["attributed_to"], "also_started": [],
               "stops": [m["id"] for m in stops],
               "corrected": any(m["body"].get("replaces") for m in stops),
               "conflict": [m["id"] for m in stops] if len(stops) > 1
               else None, "continued": len(conts),
               "_start": start, "_check_in": check_in}
        if stops:
            end = _at(stops[0])
            run.update(state="stopped", end=iso(end), counted_to=iso(end),
                       _end=end)
        elif now < check_in + CHECKIN_GRACE:
            run.update(state="running", end=None, counted_to=iso(now),
                       check_in_at=iso(check_in), _end=now)
        else:
            run.update(state="forgotten", end=None, counted_to=iso(check_in),
                       check_in_at=iso(check_in), says=FORGOTTEN_SAYS,
                       _end=check_in)
        run["seconds"] = int(max(0.0, run["_end"] - start))
        runs.append(run)
    for s in again:
        into = next((r for r in runs if r["run"] == s["body"]["run"]), None)
        if into is not None:
            into["also_started"].append(s["id"])
    return runs, problems


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _boxes(run, box, brk, since, now) -> int:
    """Boxes this run finished between `since` and `now`."""
    if not box:
        return 0
    cycle = box + (brk or 0)
    n, k = 0, 0
    while True:
        end = run["_start"] + k * cycle + box
        if end > run["_end"] or end > now:
            return n
        if end >= since:
            n += 1
        k += 1


def _public(run) -> dict:
    return {k: v for k, v in run.items() if not k.startswith("_")}


def timer_state(cv, post, block, *, holder, part=0, now=None,
                utc_offset=0, tz=None, midnight=None) -> dict:
    """The holder's timer as it stands now, read from their marks.

    "Today" starts at the VIEWER's local midnight (`day_start`): their IANA
    zone `tz`, else their own `midnight`, else their `utc_offset` (minutes
    east of UTC). Nothing here is stored."""
    corpus = cv.corpus
    now = time.time() if now is None else float(now)
    root = responses.post_root(corpus, post)
    gone = deletion_of(corpus, root)
    sid = ledger(cv, root, block, holder, part=part)
    # A deleted post's text is still read: its marks are kept as history,
    # and its box is what the block said.
    check, _ = responses._block_check(corpus, root, part, block, {})
    if not check.get("found") and check.get("checked"):
        raise Refused({"error": f"no block in this post says name={block}",
                       "block": block})
    info = _block_info(check)
    marks = marks_in(cv, sid) if sid else []
    runs, problems = runs_of(marks, now)
    midnight_s, how = day_start(now, tz=tz, midnight=midnight,
                                utc_offset=utc_offset)
    box, brk = info.get("box"), info.get("break")
    current = runs[-1] if runs and runs[-1]["state"] in ("running",
                                                        "forgotten") else None
    out = {"post": root, "block": block, "part": part, "holder": holder,
           "holder_alias": cv.alias(holder) if holder else None,
           "set": sid, "now": iso(now),
           "utc_offset": utc_offset if isinstance(utc_offset, int) else 0,
           "today_from": iso(midnight_s), **how, "title": info.get("title"),
           "reference": reference(root, block),
           "about": about_of(corpus, info.get("about") or []),
           "box_s": box, "break_s": brk, "checked": info.get("checked"),
           **({"says": info["says"], "why_not": info.get("why_not")}
              if info.get("says") or info.get("why_not") else {}),
           "runs": [_public(r) for r in runs],
           "today_s": int(sum(_overlap(r["_start"], r["_end"], midnight_s,
                                       now) for r in runs)),
           "total_s": int(sum(r["seconds"] for r in runs)),
           "boxes_today": sum(_boxes(r, box, brk, midnight_s, now)
                              for r in runs),
           "state": current["state"] if current else "stopped",
           "running": bool(current and current["state"] == "running"),
           "problems": problems,
           "conflicts": [r["run"] for r in runs if r["conflict"]],
           "source_deleted": ({"record": gone["id"], "at": gone["recorded_at"],
                               "by": gone["attributed_to"]} if gone else None)}
    out["box"] = _box_now(current, box, brk, now)
    out["check_in"] = _check_in(current, now)
    return out


def _box_now(run, box, brk, now) -> dict | None:
    """Where the running run is in its boxes: phase, box number, time left."""
    if not box or not run or run["state"] != "running":
        return None
    cycle = box + (brk or 0)
    elapsed = max(0.0, now - run["_start"])
    k, pos = divmod(elapsed, cycle)
    if pos < box:
        return {"phase": "box", "number": int(k) + 1,
                "remaining_s": int(box - pos), "length_s": box,
                "ends_at": iso(now + (box - pos))}
    return {"phase": "break", "number": int(k) + 1,
            "remaining_s": int(cycle - pos), "length_s": brk,
            "ends_at": iso(now + (cycle - pos))}


def _check_in(run, now) -> dict | None:
    if not run:
        return None
    due = run["_check_in"]
    if run["state"] == "running" and now < due:
        return {"due_at": run["check_in_at"], "in_s": int(due - now),
                "asking": False, "grace_s": CHECKIN_GRACE}
    ask = {"due_at": run["check_in_at"], "asking": True,
           "question": "Still going?", "grace_s": CHECKIN_GRACE,
           "grace_until": iso(due + CHECKIN_GRACE),
           "stopped_at_from": run["start"], "stopped_at_to": iso(now)}
    if run["state"] == "running":
        # Answered within the grace, any answer is an answer in time.
        return {**ask, "forgotten": False,
                "options": list(CHECK_IN_OPTIONS),
                "labels": {"continue": "Continue", "stop": "Stop now",
                           "stopped-at": "I stopped at..."}}
    return {**ask, "forgotten": True, "says": FORGOTTEN_SAYS,
            "options": list(FORGOTTEN_OPTIONS), "primary": "stopped-at",
            "labels": dict(FORGOTTEN_LABELS)}


# -- writing ------------------------------------------------------------------

def mark(cv, post, block, *, action, by, owner=None, part=0, at=None,
         run=None, replaces=(), reason=None, direction=None, execution=None,
         now=None, written_by=None, op=None, act_kw=None) -> dict:
    """Record one mark on a timer. See the module docstring for the rules.

    A PERSON (no `direction`) marks their own ledger: holder = `by`. AN
    AGENT names `direction`, the request its current run carries, and
    `execution`, that run; it marks the ledger of `owner`, the Brain's owner
    who directed it, only when `_directed` holds. `run` names the run a stop
    closes (its start mark); without it, the run going now. `at`, only on a
    stop, is when it really ended."""
    corpus = cv.corpus
    responses._one(corpus, by, "participant", "participant")
    agent = direction is not None or execution is not None
    if agent and owner is None:
        raise Refused({"error": "this record names no owner, so no owner's "
                                "direction can be checked; nothing was "
                                "marked"})
    responses._one(corpus, post, responses.CONTRIBUTION, "Turn")
    root = responses.post_root(corpus, post)
    if isinstance(replaces, str):
        replaces = [replaces]
    replaces = list(replaces or [])
    asked = {"route": "timer-mark", "post": root, "part": part,
             "block": block, "action": action, "at": at, "run": run,
             "replaces": replaces, "reason": reason, "direction": direction,
             "execution": execution}

    def write():
        refusal = inert_refusal(corpus, root)
        if refusal:
            raise Refused({**refusal, "error": "the post this timer is in was "
                           "deleted, so it takes no new marks; what was "
                           "already marked is kept as history",
                           "source_deleted": True})
        if action not in ACTIONS:
            raise Refused({"error": "a timer mark is one of: "
                                    + ", ".join(ACTIONS), "action": action})
        _timer(corpus, root, part, block)
        directed = None
        holder = by
        if agent:
            directed = _directed(cv, direction, by=by, owner=owner,
                                 root=root, block=block, execution=execution)
            holder = owner
        t = time.time() if now is None else float(now)
        sid = ledger(cv, root, block, holder, part=part)
        marks = marks_in(cv, sid) if sid else []
        runs, _ = runs_of(marks, t)
        latest = runs[-1] if runs else None
        going = latest if latest and latest["state"] != "stopped" else None
        if at is not None and action != "stop":
            raise Refused({"error": f"a {action} is marked when it happens; "
                                    "only a stop says another time (when a "
                                    "run really ended)", "action": action})
        if replaces and action != "stop":
            raise Refused({"error": "only a stop replaces a mark: a "
                                    "corrected stop", "action": action})
        problems, target, written, why = [], None, action, reason
        fresh = None
        when = t
        if action == "start":
            if run is not None:
                raise Refused({"error": "a start begins a run of its own"})
            if going and going["state"] == "running":
                # Kept, naming the run it fell in: never a run itself (R4).
                target = going["run"]
                problems.append(
                    f"the timer was already running, since {going['start']}; "
                    "this start is kept, and the run goes on from its first "
                    "start")
        elif action == "stop":
            target, when = _stop(marks, runs, going, run, replaces, at, t)
        else:
            if run is not None and (not going or run != going["run"]):
                raise Refused({"error": f"a {action} belongs to the run going "
                                        "now", "run": run})
            if not going:
                raise Refused({"error": "nothing is running, so there is "
                                        f"nothing to {action}",
                               "action": action})
            if going["state"] == "forgotten":
                if action != "continue":
                    raise Refused({"error": "this run was forgotten at its "
                                            "check-in, so it has no box "
                                            "going", "action": action})
                # A LATE CONTINUE STARTS FRESH (R3): the forgotten run stays
                # counted to its check-in, and a new run starts now.
                fresh, written = going["run"], "start"
                why = ("started fresh: the run before was forgotten at its "
                       f"check-in ({going['check_in_at']})")
            else:
                target = going["run"]
        sid = sid or responses.open_set(
            cv, root, block=block, part=part, mode="each", by=by,
            holder=holder, written_by=written_by, act_kw=act_kw)["set"]
        mid = corpus.write(kind=TIMER_MARK, body={
            "set": sid, "action": written, "at": iso(when), "run": target,
            "replaces": replaces,
            "reason": why if isinstance(why, str) and why.strip() else None,
            "problems": problems, "direction": directed},
            attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "a mark on this timer"}, attributed_to=by,
                     written_by=written_by,
                     link={"from": mid, "to": sid, "relation":
                           responses.IN_RESPONSE_SET})
        sup = supersedes_relation(corpus)
        for r in replaces:
            corpus.write(body={"reason": "a corrected stop"},
                         attributed_to=by, written_by=written_by,
                         link={"from": mid, "to": r, "relation": sup})
        cv.record_act(actor=by, act="timer-marked",
                      conversation=cv.conversation_of(root), turn=root,
                      about=[mid, sid, *replaces],
                      detail={"set": sid, "block": block, "action": written,
                              "holder": holder,
                              **({"asked": action} if written != action
                                 else {}),
                              **({"direction": directed} if directed
                                 else {})}, **(act_kw or {}))
        out = {"mark": mid, "set": sid, "action": written, "at": iso(when),
               "run": target or mid, "holder": holder, "problems": problems}
        if fresh:
            out.update(asked=action, started_fresh=True, forgotten=fresh)
        if action == "stop":
            torn = [m["id"] for m in _heads(marks_in(cv, sid))
                    if m["body"]["action"] == "stop"
                    and m["body"].get("run") == target and m["id"] != mid]
            if torn:
                out["conflict"] = sorted([mid, *torn])
        return out

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


def _stop(marks, runs, going, run, replaces, at, now) -> tuple[str, float]:
    """(the run this stop closes, when it ended), or refused.

    Without `at`, a run going now ends now -- unless it was FORGOTTEN, which
    ends at its check-in (R3). Only `at`, the real time, counts past it."""
    every = {m["id"]: m for m in marks}
    if run is None:
        if replaces:
            run = every.get(replaces[0], {}).get("body", {}).get("run")
        elif going:
            run = going["run"]
        else:
            raise Refused({"error": "nothing is running, so there is nothing "
                                    "to stop"})
    found = next((r for r in runs if r["run"] == run), None)
    if found is None:
        raise Refused({"error": "no run of this timer started with that mark",
                       "run": run})
    for r in replaces:
        old = every.get(r)
        if old is None or old["body"]["action"] != "stop" \
                or old["body"].get("run") != run:
            raise Refused({"error": "a stop replaces only a stop of the same "
                                    "run, in the same timer", "replaces": r})
    # As answers are: a correction names the stop(s) it was made against.
    # Two made against the same one (two tabs) are both kept, as a conflict.
    heads = set(found["stops"])
    if heads and not replaces:
        raise Refused({"error": "this run is already stopped; to correct "
                                "when it ended, name its stop in `replaces` "
                                "and give the real time in `at`",
                       "stops": sorted(heads), "run": run})
    i = runs.index(found)
    later = runs[i + 1]["_start"] if i + 1 < len(runs) else None
    if at is None:
        if replaces or later is not None:
            raise Refused({"error": "say when this run really ended (`at`): "
                                    "it is not the run going now",
                           "run": run})
        if found["state"] == "forgotten":
            return run, found["_check_in"]
        return run, now
    when = epoch(at)
    if when <= found["_start"] or when > now:
        raise Refused({"error": "when a run ended lies between its start "
                                f"({found['start']}) and now ({iso(now)}): "
                                "after the start, and no later than now",
                       "at": at, "start": found["start"], "now": iso(now)})
    if later is not None and when > later:
        raise Refused({"error": "this run cannot end after the next run "
                                f"started ({runs[i + 1]['start']})",
                       "at": at, "next_start": runs[i + 1]["start"]})
    return run, when


# -- about= (R6) ----------------------------------------------------------------

def _about_one(corpus, ref) -> dict:
    """One about= reference as the record holds it: resolved to a Topic, a
    Conversation or a post, or unresolved (shown, never dropped)."""
    got = None
    try:
        got = corpus.read([ref])
    except Exception:                                     # noqa: BLE001
        got = None
    e = got[0] if got else None
    kind = responses._kind(e) if e else None
    if e is None or kind not in ABOUT_KINDS:
        return {"ref": ref, "resolved": False, "kind": None, "label": None,
                "why": ("Mentis holds no entry with that id" if e is None
                        else f"it is a {kind}, not a Topic, Conversation or "
                             "post")}
    body = e.get("body") or {}
    name = body.get("name") or body.get("title") or body.get("alias")
    root = ref
    if kind == responses.CONTRIBUTION:
        root = responses.post_root(corpus, ref)
    return {"ref": ref, "resolved": True, "kind": ABOUT_KINDS[kind],
            "entry": root, "label": name if isinstance(name, str) else None}


def about_of(corpus, refs) -> list[dict]:
    """The about= references of a timer, each resolved or not, in order."""
    return [_about_one(corpus, r) for r in refs]


def _same(corpus, a, b) -> bool:
    """Do two references name the same thing: the same id, or two versions
    of the same post?"""
    if a == b:
        return True
    try:
        return responses.post_root(corpus, a) == responses.post_root(corpus, b)
    except Exception:                                     # noqa: BLE001
        return False


def time_spent(cv, ref, holder, *, now=None, tz=None, midnight=None,
               utc_offset=None) -> dict:
    """TIME SPENT ON `ref`, by ONE person (R6): the sum of `holder`'s runs
    across every timer whose CURRENT post version names `ref` in about=,
    each listed with its post. Read now, from the marks; nothing is stored,
    and nobody else's time is ever in it.

    Which timers: every timer block somebody has kept marks on (each set on
    a timer), read in its post's current version -- so an edit to about=
    moves that timer's time with it. A timer nobody ever started has no
    time to add."""
    corpus = cv.corpus
    now = time.time() if now is None else float(now)
    if not isinstance(ref, str) or not ref.strip():
        raise Refused({"error": "name what the time was spent on: a Topic, "
                                "Conversation or post (ent-...)"})
    ref = ref.strip()
    if holder is None:
        raise Refused({"error": "name whose time to add up: time spent is "
                                "one person's, never mixed"})
    midnight_s, how = day_start(now, tz=tz, midnight=midnight,
                                utc_offset=utc_offset)
    seen, timers = set(), []
    for s in corpus.entries_of_kind(responses.RESPONSE_SET):
        b = s.get("body") or {}
        if b.get("mode") != "each" or b.get("type") != "timer" \
                or b.get("started_from"):
            continue
        key = (b.get("post"), b.get("part", 0), b.get("block"))
        if key in seen or not key[0]:
            continue
        seen.add(key)
        root, part, block = key
        try:
            check, version = responses._block_check(corpus, root, part,
                                                    block, {})
        except Refused:
            continue
        if not check.get("found") or check.get("type") != "timer":
            continue
        about = (check.get("timer") or {}).get("about") or []
        if not any(_same(corpus, ref, a) for a in about):
            continue
        st = timer_state(cv, root, block, holder=holder, part=part, now=now,
                         tz=tz, midnight=midnight, utc_offset=utc_offset)
        timers.append({"post": root, "version": version, "part": part,
                       "block": block, "title": st["title"],
                       "conversation": cv.conversation_of(root),
                       "reference": st["reference"],
                       "total_s": st["total_s"], "today_s": st["today_s"],
                       "running": st["running"], "state": st["state"],
                       "source_deleted": bool(st["source_deleted"])})
    return {"about": _about_one(corpus, ref), "holder": holder,
            "holder_alias": cv.alias(holder), "now": iso(now),
            "today_from": iso(midnight_s), **how,
            "total_s": sum(t["total_s"] for t in timers),
            "today_s": sum(t["today_s"] for t in timers),
            "timers": timers}
