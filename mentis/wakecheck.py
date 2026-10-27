"""The wake check: what became of runs the record started and nothing ended.

A run's end is recorded by the dispatch waiter that watched it, and that
waiter lives in the server process. When the server stops -- or the machine
restarts under it -- the record is left with a start and nothing else, and the
request that run carried reads as live forever (`expectation_state`), so
nothing resumes it and nobody is told. On 2026-10-08 two Builder runs were
left exactly so by a computer restart.

A SERVER STARTING ASKS, OF EVERY RUN THE RECORD HOLDS OPEN, WHAT BECAME OF IT
-- by process evidence observed now, never by age alone:

  running       a process on this machine still names the run's execution
                (its runtime or its Mentis tool worker carries the execution
                id on its command line), or this process holds it
  interrupted   CONFIRMED gone: the machine booted after the run started, so
                no process of it can exist; or no process names it and nothing
                of it has been written for `recovery.QUIET_S` -- and it left
                no finished result to recover
  ended-unseen  gone the same way, but its runtime wrote a final message that
                ended its turn (`recovery.final_message`): a result that is
                preserved, and is the owner's to recover. Nothing is written,
                because an end here would refuse that recovery
  unknown       anything short of that: the process table could not be read,
                or nothing names the run but it was active too recently

ONLY `interrupted` IS RECORDED, as the existing run end `delivery-failed`
caused by the run's start, with `terminal: "interrupted"` and the evidence in
its detail. That closes the run everywhere a run's end is read -- the request
no longer reads as live -- and every reader that words a failed run by its
`terminal` (`_child_state`, work status) says "interrupted". It invents no
result, posts nothing as the run's answer, and claims nothing met: the request
stays owed, exactly as before.

AND NOTHING RESTARTS BY ITSELF. Closing the run would otherwise let the
request be resumed automatically the next time one of its children ends.
`claim_resumption` refuses that while an interruption is the latest thing that
happened to the work (`Conversations.interruption_hold`): continuing
interrupted work is a person's act, as continuing on a recovered result is.

WHAT IS LEFT FOR A PERSON. Interrupted work whose request is still unmet and
older than `REVIEW_AFTER_S` is put to a person once, as an ordinary owed
decision with three options -- keep, resume, discard. Answering it records the
answer and does nothing else: no option restarts or deletes anything. Agents
are told about interrupted work in their Conversation, and what of it is
preserved, through orientation (`interrupted_work`).

THE PERSON IS THE OWNER, WHOEVER ASKED FOR THE WORK (opr-6148accd1324). It
used to be the request's requester, and when an agent had delegated the work
the decision was owed by that agent: the owner's interface offers Decide only
on what the owner owes, and no agent tool answers somebody else's decision, so
nobody could answer it. The record draws no human/agent line on a Participant;
the one person it names is the owner (`baseline.OWNER_ABOUT`), so the review
is put to them -- as a decision about work found along the way is put to the
owner (`operational.ask_about_findings`). Who requested the work is kept on
the decision (`requester`), and decisions already asked of somebody else are
assigned to the owner by the ordinary append-only `expectation-assigned`
(`put_to_owner`): the decision, its Turn, its options and the work's history
stay exactly as they were.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from mentis import recovery
from mentis.conversation import DELIVERY_FAILED, RUN_START
from mentis.foundation import scratch

RUNNING, INTERRUPTED, ENDED_UNSEEN, UNKNOWN = (
    "running", "interrupted", "ended-unseen", "unknown")

#: Which `delivery-failed` ends are interruptions: their `terminal`.
TERMINAL = "interrupted"

#: How long interrupted work may stay unresolved before its requester is asked
#: what to do with it. Younger interrupted work is only shown to agents.
REVIEW_AFTER_S = 6 * 3600

REVIEW_OPTIONS = [
    {"label": "keep",
     "consequence": "leave it owed as it is; nothing is restarted"},
    {"label": "resume",
     "consequence": "continue it yourself -- answering does not restart it"},
    {"label": "discard",
     "consequence": "you no longer want it -- answering deletes nothing"},
]

#: Marks the decision this module asked, so it is asked once per run.
REVIEW_KIND = "interrupted-work-review"


def _owner(cv) -> str | None:
    """This Brain's owner Participant, identified as the baseline identifies
    them; None where the record names none."""
    from mentis.bootstrap.baseline import OWNER_ABOUT
    # THE ROWS OF THE KIND, NOT `all_participants`: a rename's version is a
    # row of the Kind carrying the same `about`, but it is written after the
    # Participant it renames, so the first row that says so is the owner
    # itself -- the answer `all_participants` gives, without asking which rows
    # are versions on every read that wants only the owner (opr-15cd9eb266f9).
    owners = [p["id"] for p in cv.corpus.entries_of_kind("participant")
              if (p.get("body") or {}).get("about") == OWNER_ABOUT]
    return owners[0] if owners else None


def _default_boot_time() -> float | None:
    """When this machine last started, or None if that cannot be read."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"
                 ".ToUniversalTime().ToString('o')"],
                capture_output=True, text=True, timeout=60, check=True)
            return recovery._epoch(out.stdout.strip())
        with open("/proc/stat", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("btime "):
                    return float(line.split()[1])
    except Exception:                                     # noqa: BLE001
        return None
    return None


#: Replaced in tests, like `recovery.processes`.
boot_time = _default_boot_time


def _newest_under(top) -> float | None:
    newest = None
    for root, _dirs, files in os.walk(top):
        for f in files:
            try:
                t = os.path.getmtime(os.path.join(root, f))
            except OSError:
                continue
            newest = t if newest is None or t > newest else newest
    return newest


def _last_activity(record, start) -> tuple[float, list[str]]:
    """The newest sign of this run working, and where it was looked for:
    its start, everything under its private scratch, and -- for Claude --
    the transcript folder the runtime files that scratch's sessions under."""
    seen, looked = [start["at"]], ["the run's start act"]
    ex = start.get("execution")
    if ex:
        try:
            where = scratch.path_for(record, ex)
        except ValueError:
            where = None
        if where is not None:
            looked.append(str(where))
            t = _newest_under(where)
            if t is not None:
                seen.append(t)
            if start.get("runtime") == "claude":
                from mentis.foundation.runtimes import claude as _claude
                folder = os.path.join(
                    os.path.expanduser("~"), ".claude", "projects",
                    _claude.transcript_folder(str(where)))
                looked.append(folder)
                t = _newest_under(folder)
                if t is not None:
                    seen.append(t)
    return max(seen), looked


def process_table() -> list[tuple[int, str]] | None:
    """One read of this machine's processes, for a whole check; None when it
    cannot be read -- which is "could not look", never "nothing there"."""
    try:
        return list(recovery.processes())
    except Exception:                                     # noqa: BLE001
        return None


def _naming(table, ex) -> list[dict]:
    me = os.getpid()
    return [{"pid": pid, "command": cmd[:200]} for pid, cmd in table
            if pid != me and ex.lower() in (cmd or "").lower()]


def classify(cv, record, start, *, booted=None, held=(), now=None,
             table=None) -> dict:
    """What became of one open run, from evidence observed now. Writes
    nothing. `booted` is the machine's boot time (None if unknown), `held`
    the execution ids this process holds, `table` one `process_table()`
    read (None: unreadable)."""
    now = now if now is not None else time.time()
    ex = start.get("execution")
    out = {"run": start["id"], "execution": ex,
           "runtime": start.get("runtime"), "request": start.get("caused_by"),
           "participant": start.get("actor"),
           "conversation": start.get("conversation"),
           "started_at": start["at"], "checked_at": now}

    def said(state, reason, **evidence):
        out.update(state=state, why=reason, evidence=evidence)
        return out

    if ex and ex in held:
        return said(RUNNING, "this process holds it", held_here=True)
    if table is None:
        return said(UNKNOWN, "the process table could not be read, so "
                             "whether this run's runtime is alive cannot be "
                             "said")
    rebooted = booted is not None and booted > start["at"]
    # PROCESSES FIRST, whatever the boot time says: a clock corrected after
    # boot can stamp a live run before it. Evidence that disagrees is not
    # resolved by picking a side -- it is unknown, and nothing is written.
    naming = _naming(table, ex) if ex else []
    if naming:
        if rebooted:
            return said(UNKNOWN, f"the machine started after this run did, "
                                 f"yet {len(naming)} process(es) name its "
                                 "execution; the evidence disagrees",
                        processes=naming, machine_booted_at=booted)
        return said(RUNNING, f"{len(naming)} process(es) on this machine "
                             "still name its execution", processes=naming)
    if rebooted:
        gone = {"machine_booted_at": booted, "processes_naming_run": 0,
                "why": "the machine started after this run did, and no "
                       "process names it"}
    else:
        last, looked = _last_activity(record, start)
        quiet = now - last
        if quiet < recovery.QUIET_S:
            return said(UNKNOWN,
                        f"no process names it, but it was active "
                        f"{int(quiet)}s ago; it is taken as gone only after "
                        f"{recovery.QUIET_S // 60} minutes quiet",
                        last_activity_at=last, looked_at=looked)
        gone = {"processes_naming_run": 0, "last_activity_at": last,
                "quiet_for_s": int(quiet), "looked_at": looked,
                "machine_booted_at": booted,
                "why": "no process on this machine names it and nothing of "
                       f"it has been written for {recovery.QUIET_S // 60}+ "
                       "minutes"}
    # GONE. Whether it left a finished result decides what it is. ONLY a
    # definite "there is none" (`recovery.NoResult`) makes it interrupted: any
    # other refusal is about what could not be established, and an end
    # written over a result that exists would make `recover_result` refuse
    # it forever.
    if start.get("runtime") in recovery.SUPPORTED and ex:
        try:
            window = cv.run_window(start["id"])
            got = recovery.final_message(
                record, execution=ex, runtime=start["runtime"],
                since=window["since"], until=window["until"], now=now,
                require_quiet=not rebooted)
        except recovery.NoResult as exc:
            gone["no_result_because"] = str(exc)
        except ValueError as exc:
            return said(UNKNOWN, "it is gone, but whether it left a finished "
                                 f"result could not be established: {exc}",
                        **{k: v for k, v in gone.items() if k != "why"})
        else:
            return said(ENDED_UNSEEN,
                        "it is gone, and its runtime wrote a final message "
                        "that ended its turn; recover it to record that "
                        "result", **gone,
                        result={"source": got["evidence"]["source"],
                                "session": got["session"],
                                "chars": len(got["said"])})
    else:
        gone["no_result_because"] = (
            f"a finished result is read back only for "
            f"{', '.join(recovery.SUPPORTED)} runs")
    return said(INTERRUPTED, gone["why"], **gone)


def record_interruption(cv, found) -> str | None:
    """Write the end for a run `classify` found interrupted, unless the
    record already holds one. Returns the act written, or None."""
    if found["state"] != INTERRUPTED:
        raise ValueError(f"{found['run']} is {found['state']}, not "
                         "interrupted; nothing is recorded for it")
    with cv._c.atomic():
        if cv.run_end(found["run"]) is not None:
            return None
        start = cv._act(found["run"])
        return cv.record_act(
            actor="mentis", act=DELIVERY_FAILED,
            conversation=start.get("conversation"), turn=start.get("turn"),
            caused_by=start["id"], execution=start.get("execution"),
            runtime=start.get("runtime"),
            about=[start["caused_by"]] if start.get("caused_by") else (),
            because=f"interrupted: {found['why']}",
            detail={"terminal": TERMINAL, "observed_end": False,
                    "result": None, "evidence": found["evidence"],
                    "checked_at": found["checked_at"],
                    "not_established": [
                        "what the run had done when it stopped: only what it "
                        "returned or committed before then is held",
                        "processes this server cannot see the command line "
                        "of -- another user's, or an elevated one"]})


def reconcile(cv, record, *, held=(), now=None) -> dict:
    """Every run the record holds open, classified now; confirmed
    interruptions recorded. Says what it found and what it wrote."""
    now = now if now is not None else time.time()
    booted = boot_time()
    runs = cv.open_runs()
    table = process_table() if runs else []
    found = [classify(cv, record, s, booted=booted, held=set(held), now=now,
                      table=table)
             for s in runs]
    written = []
    for f in found:
        if f["state"] == INTERRUPTED:
            act = record_interruption(cv, f)
            if act:
                f["recorded"] = act
                written.append(act)
    return {"checked_at": now, "machine_booted_at": booted, "runs": found,
            "recorded": written,
            "counts": {s: sum(1 for f in found if f["state"] == s)
                       for s in (RUNNING, INTERRUPTED, ENDED_UNSEEN, UNKNOWN)}}


# -- dispatches lost before their run started ---------------------------------
#
# A RUN THAT NEVER STARTED HAS NO START TO CLASSIFY. A dispatch is a thread of
# the server that made it, and between it being recorded and its run starting
# sit runtime selection, summoning and worktree setup. Every failure there is
# recorded while the server lives (`dispatch._failed_before_start`); a server
# stopping in that gap leaves the request with nothing after it at all.
#
# For a CONTINUATION that is a hold nothing lifts: `claim_resumption` counts a
# continuation dispatched and not yet started as the work it continues running
# (`continuation_pending`), so the work would never resume again -- while its
# status promised it would (opr-3da43202b497, opr-75c43ce26650). So a server
# starting closes every continuation still pending from before it: no thread
# of this server dispatched it, and none of the one that did is left. The end
# is the ordinary failure-before-start, saying why, and it is written once.

#: What `delivery-failed` says of a dispatch lost with its server: its
#: `terminal`, which work status shows as the way it ended.
LOST = "dispatch-lost"


def pending_continuations(cv, *, before=None) -> list[str]:
    """Every continuation the record holds pending (`continuation_pending`),
    narrowed to those that became pending -- recorded, or last resumed --
    before `before` when given."""
    out = []
    for g in cv.history(act="authority-granted"):
        cont, origin = g.get("caused_by"), (g.get("detail") or {}).get("origin")
        if not cont or not origin or cont in out:
            continue
        exp = cv._act(cont)
        if (exp is None or exp.get("caused_by") != origin
                or cont not in cv.continuations_of(origin)
                or not cv.continuation_pending(cont)):
            continue
        if before is not None:
            since = max([exp["at"]] + [a["at"] for a in cv._own_acts(cont)
                                       if a["act"] == "work-resumed"])
            if since >= before:
                continue
        out.append(cont)
    return out


def close_lost_dispatches(cv, *, before) -> list[dict]:
    """Close every continuation still pending from before `before` -- when
    this server started -- with `delivery-failed`, before execution started,
    `terminal: "dispatch-lost"`. Returns what was closed: the continuation,
    the work it continued and the act written. Nothing is re-dispatched."""
    from mentis.conversation import DELIVERY_FAILED as _FAILED
    closed = []
    for cont in pending_continuations(cv, before=before):
        with cv._c.atomic():
            if not cv.continuation_pending(cont):
                continue
            exp = cv._act(cont)
            act = cv.record_act(
                actor="mentis", act=_FAILED,
                conversation=exp.get("conversation"), turn=exp.get("turn"),
                caused_by=cont, about=[cont],
                because="dispatch lost: the server that dispatched this "
                        "continuation stopped before its run started, so "
                        "nothing will run it; the work it continues is no "
                        "longer held by it",
                detail={"terminal": LOST, "stage": "dispatch",
                        "before_execution_started": True,
                        "continues": exp.get("caused_by"),
                        "server_started_at": before,
                        "not_established": [
                            "why the server stopped: only that this "
                            "dispatch's run never started is recorded"]})
        closed.append({"continuation": cont, "continues": exp.get("caused_by"),
                       "recorded": act})
    return closed


def after_restart(st, *, before) -> list[dict]:
    """What a starting server does about dispatches its predecessor lost:
    close them, then ask -- as a run ending asks -- whether the work each
    continued may now resume. That is ordinary resumption, never a retry of
    the lost dispatch: a child that ended while it was pending was refused
    then, and nothing else would ask again."""
    from mentis.web.dispatch import resume_if_ready
    closed = close_lost_dispatches(st.cv, before=before)
    for c in closed:
        c["resumed"] = resume_if_ready(st, c["continuation"])
    return closed


# -- what is preserved, and what a person decides ------------------------------

def preserved(cv, request) -> dict:
    """What interrupted work left that Mentis holds: artifacts it returned and
    the repository branch its request owns."""
    from mentis import worktrees as W
    from mentis.conversation import ARTIFACT_RETURNED
    artifacts = [a["about"][0] for a in cv.history(caused_by=request)
                 if a["act"] == ARTIFACT_RETURNED and a["about"]]
    tree = W.recorded(cv, request)
    branch = None
    if tree and not tree["removed_by"] and not tree["abandoned_by"]:
        branch = {"branch": tree["branch"], "path": tree["path"],
                  "base": tree["base"]}
    return {"artifacts": artifacts, "branch": branch}


def _continued_since(cv, start) -> bool:
    """Whether the run's request was run or resumed AFTER this run started,
    in the record's write order -- never by clock, and never from the time
    the interruption was found, which can be after a person had already
    continued the work."""
    request = start.get("caused_by")
    later = [a for a in cv.history(caused_by=request)
             if a["act"] in (RUN_START, "work-resumed")
             and a["id"] != start["id"]]
    if not later:
        return False
    order = cv._write_order([start["id"], *(a["id"] for a in later)])
    return any(order.get(a["id"], -1) > order.get(start["id"], -1)
               for a in later)


def _entry(cv, start, *, state, because, stopped_at, result=None
           ) -> dict | None:
    """One piece of stopped work as orientation and review say it, or None
    when its request is met or somebody has continued it since."""
    request = start.get("caused_by")
    if not request:
        return None
    try:
        owed = cv.expectation_state(request)
    except ValueError:
        return None
    if owed["satisfied_by"] or _continued_since(cv, start):
        return None
    return {"run": start["id"], "request": request, "state": state,
            "execution": start.get("execution"),
            "participant": start.get("actor"),
            "carrier": cv.alias(start["actor"]) if start.get("actor") else None,
            "conversation": start.get("conversation"),
            "runtime": start.get("runtime"), "started_at": start["at"],
            "stopped_at": stopped_at, "because": because, "result": result,
            "preserved": preserved(cv, request),
            "review": _review_of(cv, start["id"])}


def _stopped_at(evidence, fallback) -> float:
    """When the run is known to have stopped, at the latest: the machine's
    boot for a run it rebooted under, or its last sign of activity."""
    if evidence.get("machine_booted_at") and evidence.get(
            "last_activity_at") is None:
        return evidence["machine_booted_at"]
    return evidence.get("last_activity_at") or fallback


def interrupted_work(cv, *, conversation=None, unreviewed_older_than=None,
                     now=None) -> list[dict]:
    """Stopped work whose request is still owed, newest first: runs recorded
    interrupted, and runs that ended unseen with a preserved result their
    requester has been asked about. What stopped, when, why that is known,
    what is preserved, and whether the requester answered. From the record,
    narrowed by the record's own indexes to `conversation` when given."""
    # `unreviewed_older_than`: only what review could still ask about, sifted
    # by the cheap, indexed lookups BEFORE any entry is built -- review runs
    # after every dispatch, and every interruption ever recorded must not be
    # rebuilt each time.
    sifting = unreviewed_older_than is not None
    now = now if now is not None else time.time()
    out = []
    for end in cv.history(act=DELIVERY_FAILED, conversation=conversation,
                          detail_is={"terminal": TERMINAL}):
        stopped = _stopped_at((end.get("detail") or {}).get("evidence") or {},
                              end["at"])
        if sifting and (now - stopped < unreviewed_older_than
                        or _review_of(cv, end["caused_by"])):
            continue
        start = cv._act(end["caused_by"])
        if start is None:
            continue
        e = _entry(cv, start, state=INTERRUPTED, because=end.get("because"),
                   stopped_at=stopped)
        if e:
            out.append(e)
    for d in ([] if sifting else cv.history(
            act="expectation-recorded", conversation=conversation,
            detail_is={"review": REVIEW_KIND, "run_state": ENDED_UNSEEN})):
        detail = d.get("detail") or {}
        start = cv._act(detail.get("review_of"))
        if start is None or cv.run_end(start["id"]) is not None:
            continue                     # recovered (or otherwise ended) since
        e = _entry(cv, start, state=ENDED_UNSEEN,
                   because=detail.get("because"),
                   stopped_at=detail.get("stopped_at") or start["at"],
                   result=detail.get("result"))
        if e:
            out.append(e)
    keep, seen = [], set()
    for e in sorted(out, key=lambda e: e["started_at"], reverse=True):
        if e["request"] not in seen:
            seen.add(e["request"])
            keep.append(e)
    return keep


def _review_of(cv, run) -> dict | None:
    """The owner decision asked about this stopped run, if any, and the
    requester's answer in their own words once given."""
    for a in cv.history(act="expectation-recorded",
                        detail_is={"review_of": run, "review": REVIEW_KIND}):
        s = cv.expectation_state(a["id"])
        replies = list(s["replies_from_expected"])
        answer = None
        if replies:
            body = cv._c.read([replies[-1]])[0]["body"]
            answer = " ".join(p.get("text", "") for p in body["parts"]
                              if p.get("type") == "text").strip() or None
        return {"decision": a["id"], "turn": a["turn"],
                "answered": bool(s["satisfied_by"] or replies),
                "answer": answer}
    return None


def review(cv, *, found=(), now=None) -> list[dict]:
    """Ask the owner, once, what to do with work that has been stopped
    for longer than `REVIEW_AFTER_S`: runs recorded interrupted, and runs a
    check `found` ended unseen with a result preserved. An ordinary owed
    decision with options; answering it restarts, recovers and deletes
    nothing. Reviews already asked of somebody else are first assigned
    to the owner (`put_to_owner`). Returns what was asked."""
    from mentis.conversation import text as text_part
    now = now if now is not None else time.time()
    put_to_owner(cv)
    candidates = list(interrupted_work(cv, unreviewed_older_than=REVIEW_AFTER_S,
                                       now=now))
    for f in found:
        if f["state"] == ENDED_UNSEEN:
            e = _entry(cv, cv._act(f["run"]), state=ENDED_UNSEEN,
                       because=f["why"],
                       stopped_at=_stopped_at(f["evidence"], f["started_at"]),
                       result=f["evidence"].get("result"))
            if e:
                candidates.append(e)
    asked = []
    for w in candidates:
        if w["review"] or now - w["stopped_at"] < REVIEW_AFTER_S:
            continue
        requester = cv.expectation_state(w["request"])["requested_by"]
        if not requester or not w["conversation"] or not w["participant"]:
            continue
        # The owner; where the record names none, whoever requested it.
        owner = _owner(cv) or requester
        hours = (now - w["stopped_at"]) / 3600
        kept = w["preserved"]
        held = [f"{len(kept['artifacts'])} returned artifact(s)"]
        if kept["branch"]:
            held.append(f"branch {kept['branch']['branch']}")
        if w["state"] == ENDED_UNSEEN:
            what = ("stopped without Mentis seeing it end, and its runtime's "
                    "final message is preserved ("
                    f"{(w['result'] or {}).get('source')}); it can be "
                    "recovered as the run's result")
        else:
            what = "was interrupted before it could finish"
        asked_for = _request_said(cv, w["request"])
        origin = (f" {cv.alias(requester)} requested it"
                  + (f" in #{asked_for['number']}" if asked_for["number"]
                     else "")
                  + (f": \u201c{asked_for['said']}\u201d" if asked_for["said"]
                     else "") + "."
                  + (" It is put to you as the owner."
                     if owner != requester else ""))
        words = (f"Mentis wake check: {w['carrier']}'s run of this request "
                 f"({w['run']}, execution {w['execution']}) {what}.{origin} "
                 f"Stopped for {hours:.0f}h. Why that "
                 f"is known: {w['because']}. Preserved: {', '.join(held)}. "
                 f"Keep it owed, resume it yourself, or discard it? "
                 f"Answering records your choice; nothing restarts, is "
                 f"recovered or is deleted because of it.")
        with cv._c.atomic():
            if _review_of(cv, w["run"]):
                continue
            turn = cv.say(w["conversation"], w["participant"],
                          [text_part(words)], addressed_to=[owner],
                          written_by="mentis/wake-check")
            exp = cv.expect(turn, of=owner, kind="decision", by="mentis",
                            because="stopped work is the owner's to keep, "
                                    "resume or discard",
                            caused_by=w["request"],
                            detail={"options": REVIEW_OPTIONS,
                                    "review": REVIEW_KIND,
                                    "review_of": w["run"],
                                    "requester": requester,
                                    "run_state": w["state"],
                                    "because": w["because"],
                                    "stopped_at": w["stopped_at"],
                                    **({"result": w["result"]}
                                       if w["result"] else {})})
            cv.record_act(actor="mentis", act="decision-requested",
                          conversation=w["conversation"], turn=turn,
                          about=[exp], caused_by=w["request"])
        asked.append({"run": w["run"], "request": w["request"],
                      "state": w["state"], "decision": exp, "turn": turn})
    return asked


def _request_said(cv, request, *, clip=240) -> dict:
    """The request's Turn, its number and its words as they now read."""
    from mentis.conversation.versions import presented
    act = cv._act(request) or {}
    turn = act.get("turn")
    got = cv._c.read([turn]) if turn else []
    said = ""
    if got:
        body = presented(cv._c, got[0]).get("body") or {}
        said = " ".join(p.get("text") or "" for p in body.get("parts") or ()
                        if p.get("type") == "text").strip()
        if len(said) > clip:
            said = said[:clip - 1].rstrip() + "\u2026"
    return {"turn": turn, "number": cv.turn_number(turn) if turn else None,
            "said": said or None}


def put_to_owner(cv) -> list[str]:
    """Review decisions still owed by somebody other than the owner, assigned
    to the owner. Returns the assignment acts written, usually none.

    APPEND-ONLY, through the ordinary reassignment (`Conversations.assign`):
    the decision keeps its Turn, options, causes and who it was first asked
    of, and the work's request and runs are not touched. An answered or
    withdrawn decision is history and is left alone."""
    owner = _owner(cv)
    if not owner:
        return []
    written = []
    for d in cv.history(act="expectation-recorded",
                        detail_is={"review": REVIEW_KIND}):
        if d["about"] == [owner]:
            continue                       # asked of the owner from the start
        with cv._c.atomic():
            s = cv.expectation_state(d["id"])
            if (s["expected_of"] == owner or s["response_present"]
                    or s["withdrawn"]):
                continue
            requester = ((d.get("detail") or {}).get("requester")
                         or (cv._act(d["caused_by"]) or {}).get("actor"))
            written.append(cv.assign(
                d["id"], owner, by="mentis",
                because=f"{cv.alias(requester) if requester else 'somebody'} "
                        "requested the stopped work, and stopped work is the "
                        "owner's to keep, resume or discard "
                        "(opr-6148accd1324)",
                detail={"review": REVIEW_KIND, "requester": requester,
                        "was_of": s["expected_of"]}))
    return written


def put_decision_to_owner(cv, decision, *, because) -> str | None:
    """One open decision asked with `request_decision` and owed by somebody
    other than the owner, assigned to the owner. Returns the assignment act,
    or None where the owner already owes it.

    NAMED, NEVER SWEPT. `request_decision` owed its decisions to the carried
    work's requester until it was repaired, and under a finding the owner
    chose to pursue that is the agent who recorded the finding (UI/UX #655 and
    #668, owed by @Builder). Which of those still-open decisions are really
    the owner's is the owner's call, so each is moved only when named
    (`tools/put_decisions_to_owner.py`); nothing calls this at start.

    The same append-only reassignment `put_to_owner` uses: the decision, its
    Turn, options and causes are untouched, and who it was first asked of
    stays in the record. Refused for anything that is not an open decision
    asked with `request_decision`. Written by Mentis at the owner's direction
    (`directed_by`), as `put_to_owner` writes its own."""
    with cv._c.atomic():
        c = decision_to_owner(cv, decision)
        if c["already"]:
            return None
        return cv.assign(decision, c["owner"], by="mentis", because=because,
                         detail={"asked_with": "request_decision",
                                 "directed_by": c["owner"],
                                 "requester": c["requester"],
                                 "was_of": c["was_of"]})


def decision_to_owner(cv, decision) -> dict:
    """Whether `put_decision_to_owner` would move this decision, without
    moving it: raises ValueError saying why not, or says who owes it now, who
    requested the work, and whether the owner already owes it. The one check,
    so that a dry run refuses exactly what a write would."""
    owner = _owner(cv)
    if not owner:
        raise ValueError("this record names no owner")
    d = cv._act(decision)
    if (d is None or d["act"] != "expectation-recorded"
            or (d.get("detail") or {}).get("expects") != "decision"):
        raise ValueError(f"{decision!r} is not a decision in this record")
    if (d.get("detail") or {}).get("review") == REVIEW_KIND:
        raise ValueError(f"{decision!r} is a wake-check review; "
                         "put_to_owner moves those")
    if not d["caused_by"] or not any(
            # A question asked through a decision form records the form
            # beside it (`about=[*questions, form]`), so the decision is IN
            # `about`, not all of it.
            a["act"] == "decision-requested"
            and decision in (a["about"] or ())
            for a in cv.history(caused_by=d["caused_by"])):
        raise ValueError(f"{decision!r} was not asked with request_decision")
    s = cv.expectation_state(decision)
    already = s["expected_of"] == owner
    if not already and (s["response_present"] or s["withdrawn"]):
        raise ValueError(f"{decision!r} is already answered or withdrawn; "
                         "it is history and is left alone")
    requester = ((d.get("detail") or {}).get("requester")
                 or cv.expectation_state(d["caused_by"])["requested_by"])
    return {"owner": owner, "already": already, "requester": requester,
            "was_of": s["expected_of"], "turn": s["turn"]}


def stopped_work(cv, decision) -> dict | None:
    """What a review decision is about, for whoever answers it: the original
    request -- its Turn, number, words and who requested it -- and the stopped
    run with its execution. None for any other expectation."""
    d = cv._act(decision)
    detail = (d or {}).get("detail") or {}
    if detail.get("review") != REVIEW_KIND:
        return None
    start = cv._act(detail.get("review_of")) or {}
    request = d.get("caused_by")
    requester = (detail.get("requester")
                 or (cv._act(request) or {}).get("actor"))
    said = _request_said(cv, request)
    return {"request": request, "request_turn": said["turn"],
            "request_number": said["number"], "request_said": said["said"],
            "requester": requester,
            "requester_alias": cv.alias(requester) if requester else None,
            "run": detail.get("review_of"),
            "execution": start.get("execution"),
            "runtime": start.get("runtime"),
            "carrier": start.get("actor"),
            "carrier_alias": (cv.alias(start["actor"])
                              if start.get("actor") else None),
            "run_state": detail.get("run_state"),
            "stopped_at": detail.get("stopped_at")}


def report_lines(rec: dict, asked: list[dict]) -> list[str]:
    """What a starting server prints."""
    c = rec["counts"]
    lines = [f"wake check: {sum(c.values())} open run(s): {c[RUNNING]} "
             f"running, {c[INTERRUPTED]} interrupted "
             f"({len(rec['recorded'])} newly recorded), {c[ENDED_UNSEEN]} "
             f"ended unseen with a result to recover, {c[UNKNOWN]} unknown; "
             f"{len(asked)} owner review(s) asked"]
    for f in rec["runs"]:
        if f["state"] != RUNNING:
            lines.append(f"  {f['state']} {f['run']} ({f['runtime']}, "
                         f"request {f['request']}): {f['why']}")
    return lines


# ORIENTATION, from this layer: the Conversation layer reaches no further
# inward than the spine, so what this module knows is added, not imported.
from mentis.conversation import ORIENTATION_ADDITIONS  # noqa: E402

ORIENTATION_ADDITIONS["interrupted_work"] = (
    lambda cv, conversation: interrupted_work(cv, conversation=conversation))


# -- a request that said nothing twice: retry or park ------------------------

def ask_about_empty_run(cv, child, need, why_not) -> str | None:
    """Ask the owner, once per end, what to do with a request whose run ended
    with nothing reported and which could not be moved again: retry it once
    more, or park it. An ordinary owed decision with options (the shape the
    wake check asks in), so it reaches Needs You; answering it is
    `dispatch.retry_if_chosen`'s to act on; asked from
    `dispatch.recover_child`. Returns the question, or None when it was
    already asked for this end or the record names nobody to ask."""
    from mentis.conversation import text as text_part
    from mentis.web.dispatch import EMPTY_RUN_OPTIONS, EMPTY_RUN_REVIEW, STARTED
    exp = cv._act(child)
    if exp is None:
        return None
    for a in cv.history(caused_by=child):
        d = a.get("detail") or {}
        if (a["act"] == "expectation-recorded"
                and d.get("recovery") == EMPTY_RUN_REVIEW
                and d.get("ended_by") == need["ended_by"]):
            return None                    # this end was already put to them
    carrier = cv.assigned_carrier(child)["carrier"]
    owner = _owner(cv) or cv.expectation_state(child)["requested_by"]
    if not owner or not carrier:
        return None
    runs = sorted((a for a in cv._own_acts(child) if a["act"] == STARTED),
                  key=lambda a: a["at"])
    where = ", ".join(dict.fromkeys(a.get("runtime") or "?" for a in runs))
    who = cv.alias(carrier)
    how = ("made no progress and was stopped by the Mentis watchdog"
           if need.get("reason") == "stalled" else
           "ended with nothing reported (exit 0, no error from the runtime)")
    words = (f"Mentis recovery: {who}'s run of this request ({child}) {how}, "
             f"and it could not be moved to another runtime: {why_not}. "
             f"It has run on {where or 'no runtime'}. Retry it once more, or "
             f"park it? Retrying sends the same request to {who} again, with the "
             f"model and effort it was asked with, on the runtime its binding "
             f"or {who}'s default names (else the one selection picks); "
             f"parking leaves it where it "
             f"stopped until you say to continue.")
    with cv._c.atomic():
        turn = cv.say(exp["conversation"], carrier, [text_part(words)],
                      addressed_to=[owner], written_by="mentis/recovery")
        dec = cv.expect(turn, of=owner, kind="decision", by="mentis",
                        because=("a request whose run stalled and could "
                                 "not be moved is the owner's to retry or "
                                 "park" if need.get("reason") == "stalled"
                                 else "a request that ended with nothing "
                                 "reported twice is the owner's to retry "
                                 "or park"),
                        caused_by=child,
                        detail={"options": EMPTY_RUN_OPTIONS,
                                "recovery": EMPTY_RUN_REVIEW,
                                "retry_of": child, "carrier": carrier,
                                "ended_by": need["ended_by"],
                                "from_runtime": need["runtime"],
                                "why_not": why_not})
        cv.record_act(actor="mentis", act="decision-requested",
                      conversation=exp["conversation"], turn=turn,
                      about=[dec], caused_by=child)
    return dec
