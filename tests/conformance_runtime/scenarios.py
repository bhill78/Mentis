"""The behavioural contract every runtime is held to (program §11-12), as scenarios.

Each scenario drives one Rig (offline or live) through the owner's own gestures -- ask,
answer a decision, stop -- and returns its CHECKS: `Check(name, group, status, evidence)`,
`status` one of passed / failed / not-run / capacity-blocked. The same scenario text is
given to a scripted runtime and to a real one: the STEP lines are the instructions.

Groups:
  * `universal` -- what every runtime must do (a runtime that fails one is not conformant:
    it lost work, bypassed authority or misreported completion);
  * `native` -- optional native capabilities (resume): reported, never required;
  * `enforcement` -- the runtime's own permission/sandbox behaviour, as observed;
  * `performance` -- numbers recorded, never asserted.
"""

from __future__ import annotations

import json
import random
import re
import string
import time
from dataclasses import dataclass

from tests.conformance_runtime.rig import CODEWORD, FINISH, Rig

PASSED, FAILED, NOT_RUN, BLOCKED = "passed", "failed", "not-run", "capacity-blocked"


@dataclass
class Check:
    name: str
    group: str
    status: str
    evidence: str

    def as_dict(self) -> dict:
        return {"name": self.name, "group": self.group, "status": self.status,
                "evidence": self.evidence}


def _ok(cond) -> str:
    return PASSED if cond else FAILED


def _nonce(n=6) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def outcome_block(summary: str, result: str = "met") -> str:
    return f"```outcome\nresult: {result}\nsummary: {summary}\n```"


def task(intro: str, steps: list[tuple[str, dict]], *, finish: str, extra: str = "") -> str:
    lines = [intro,
             "Use the Mentis MCP tools (the `mentis` server you were given) for every step. "
             "Do not use a shell or edit any file. Do the steps in order, each exactly once "
             "unless the step says otherwise, even when an earlier one was refused."]
    for i, (op, args) in enumerate(steps, 1):
        lines.append(f"STEP {i}: call the Mentis tool `{op}` with {json.dumps(args)}")
    lines.append("Then write your final reply: one line per step, `step N: ok` or "
                 "`step N: refused boundary=<the refusal's boundary field>`.")
    if extra:
        lines.append(extra)
    lines.append(FINISH)
    lines.append(finish)
    return "\n".join(lines)


def _timing(rig: Rig, start: dict) -> dict:
    end = rig.end_of(start) or {}
    t = (end.get("detail") or {}).get("timing") or {}
    out = {}
    for a, b, name in (("triggered_at", "perform_called", "dispatch_to_perform_s"),
                       ("perform_called", "ended", "perform_s"),
                       ("triggered_at", "ended", "total_s")):
        if isinstance(t.get(a), (int, float)) and isinstance(t.get(b), (int, float)):
            out[name] = round(t[b] - t[a], 2)
    mars = t.get("mars") or {}
    for k in ("total_ms", "spawn_ms", "initialize_ms", "new_session_ms", "load_ms"):
        if k in mars:
            out[f"mars_{k}"] = mars[k]
    return out


def _claims(rig: Rig, exp: str) -> list[dict]:
    from mentis.operational import completion as C
    return C.claims_of(rig.cv, exp)


def _mets(rig: Rig, exp: str) -> list[dict]:
    return [a for a in rig.acts(exp) if a["act"] == "expectation-met"]


# -- 1. assigned work, Mentis tools, contribution, leases, durable writes, refusal, claim ----

def main(rig: Rig, *, held_port: str = "8858", free_port: str = "8859",
         repeat: bool = True) -> list[Check]:
    """`repeat=False` (`main_single`) leaves out the deliberately repeated write: an SDK
    loop that stops a conversation repeating an identical call (OpenHands' stuck
    detection) cannot be asked for it. Its durable-report check is then not run."""
    cv = rig.cv
    n = _nonce()
    cid = rig.conversation(f"Conformance {rig.runtime} main {n}")
    agent = rig.participant(cid, f"@Conformer-{n}")
    other = rig.participant(cid, f"@Holder-{n}")
    from mentis.operational import leases as L
    L.claim(cv, participant=other, execution=f"holder-{n}", kind="port", name=held_port,
            purpose="held by another participant for the conformance conflict check")
    finding = f"conformance finding {n}"
    key = f"conf-{n}-material"
    steps = [
        ("record_material", {"kind": "note", "body": {"text": finding}, "op_key": key}),
    ] + ([("record_material", {"kind": "note", "body": {"text": finding}, "op_key": key})]
         if repeat else []) + [
        ("claim_resource", {"kind": "port", "name": held_port,
                            "purpose": f"conformance {n} (expected to be refused)"}),
        ("claim_resource", {"kind": "port", "name": free_port, "purpose": f"conformance {n}"}),
        ("release_resource", {"kind": "port", "name": free_port, "because": "done with it"}),
        # a lease another participant holds: only the holder releases (refused, named)
        ("release_resource", {"kind": "port", "name": held_port,
                              "because": "conformance: expected to be refused"}),
    ]
    conflict, other_release = (3, 6) if repeat else (2, 5)
    work = task(f"Conformance check {n}. "
                + ("Step 2 deliberately repeats step 1 with the same op_key; " if repeat else "")
                + f"steps {conflict} and {other_release} are expected to be refused: that is the "
                "check, so the work is met when every step was done as written.",
                steps, finish=outcome_block(f"conformance {n} steps done"))
    exp = rig.ask(cid, agent, work)
    runs = rig.wait_runs_ended(exp, 1)
    checks: list[Check] = []
    if not runs:
        fails = rig.failures(exp)
        return [Check("receive_assigned_work", "universal", FAILED,
                      f"no run started; {[(f['act'], (f.get('detail') or {}).get('why')) for f in fails]}")]
    start = runs[0]
    end = rig.end_of(start)
    exe = start.get("execution")
    reply = rig.reply_of(start)
    said = json.dumps(end.get("detail") or {}) + (end.get("because") or "")
    if end["act"] != "result-returned" and ("rate_limited" in said or "quota" in said.lower()):
        # OUT OF CAPACITY: not a conformance result either way, and not retried.
        return [Check("receive_assigned_work", "universal", BLOCKED,
                      f"run {start['id']} ended {end['act']}: {said[:300]}")]
    checks.append(Check("receive_assigned_work", "universal",
                        _ok(start.get("runtime") == rig.runtime and end["act"] == "result-returned"),
                        f"run {start['id']} exe {exe} runtime {start.get('runtime')} ended {end['act']}"))
    # Every act this run's execution wrote, by the real door.
    written = [a for a in cv._c.operational(execution=exe)] if exe else []
    mats = [e for e in _entries_with_text(rig, finding)]
    checks.append(Check("use_mentis_tools", "universal", _ok(bool(mats)),
                        f"{len(mats)} material entr(y/ies) carrying the run's text"))
    attributed = [m for m in mats if m.get("attributed_to") == agent or
                  (m.get("execution") == exe)]
    checks.append(Check("contribute_knowledge", "universal",
                        _ok(bool(mats) and bool(attributed)),
                        f"material {[m['id'] for m in mats]} attributed {[m.get('attributed_to') for m in mats]}"
                        f" (agent {agent})"))
    checks.append(Check("durable_reports_op_key", "universal",
                        _ok(len(mats) == 1) if repeat else NOT_RUN,
                        f"the same write sent twice with op_key {key}: {len(mats)} recorded"))
    claimed = [a for a in written if a["act"] == L.CLAIMED]
    released = [a for a in written if a["act"] == L.RELEASED]
    free_claims = [a for a in claimed if (a.get("detail") or {}).get("name") == free_port]
    held_claims = [a for a in claimed if (a.get("detail") or {}).get("name") == held_port]
    checks.append(Check("claim_release_resource", "universal",
                        _ok(bool(free_claims) and bool(released)),
                        f"claimed {[a['id'] for a in free_claims]} released {[a['id'] for a in released]}"))
    refused3 = re.search(rf"step {conflict}:\s*refused[^\n]*resource", reply, re.I)
    checks.append(Check("resource_conflict_refused", "universal",
                        _ok(not held_claims and bool(refused3)),
                        f"no lease taken on the held port ({len(held_claims)}); reply says: "
                        f"{refused3.group(0) if refused3 else _line(reply, f'step {conflict}')!r}"))
    refused6 = re.search(rf"step {other_release}:\s*refused[^\n]*", reply, re.I)
    opened = [a for a in written if a["act"] == L.RELEASED
              and (a.get("detail") or {}).get("name") == held_port]
    still = [v for v in L.live(cv) if v.get("name") == held_port or v.get("key") == held_port]
    checks.append(Check("meaningful_refusal", "universal",
                        _ok(bool(refused6) and "boundary=" in (refused6.group(0) if refused6 else "")
                            and not opened and bool(still)),
                        f"reply says: {refused6.group(0) if refused6 else _line(reply, f'step {other_release}')!r}; "
                        f"the other holder's lease still held: {bool(still)}"))
    claims = _claims(rig, exp)
    c = claims[-1] if claims else None
    cd = (c or {}).get("detail") or {}
    checks.append(Check("completion_claim", "universal",
                        _ok(bool(c) and cd.get("result") == "met" and cd.get("claimed_by") == exe
                            and cd.get("runtime") == rig.runtime and c.get("actor") == agent
                            and exp in (c.get("about") or [])),
                        f"claim {c and c['id']} result {cd.get('result')} claimed_by {cd.get('claimed_by')} "
                        f"runtime {cd.get('runtime')} actor {c and c.get('actor')} via {cd.get('via')}"))
    mets = _mets(rig, exp)
    checks.append(Check("completion_reconciled", "universal",
                        _ok(bool(c) and any((m.get("detail") or {}).get("reconciled_from") == c["id"]
                                            for m in mets)),
                        f"expectation-met {[(m['id'], (m.get('detail') or {}).get('reconciled_from')) for m in mets]}"))
    ev = (end.get("detail") or {}).get("runtime_evidence") or {}
    applied = ev.get("consent_applied") or {}
    rules = applied.get("runtime_rules") or {}
    checks.append(Check("permission_enforcement_observed", "enforcement", PASSED,
                        f"MARS applied: enforced_by {applied.get('enforced_by')!r}, mode "
                        f"{applied.get('mode')!r}, runtime_rules {json.dumps(rules)[:300]}"))
    checks.append(Check("timing", "performance", PASSED, json.dumps(_timing(rig, start))))
    return checks


def _line(text: str, prefix: str) -> str:
    for line in (text or "").splitlines():
        if line.strip().lower().startswith(prefix):
            return line.strip()[:200]
    return (text or "")[:200]


def _entries_with_text(rig: Rig, text: str) -> list[dict]:
    """Durable entries (not acts) whose body says `text`, read from the Brain read-only."""
    import sqlite3
    db = rig.state.path + "/corpus.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("select id, attributed_to, written_by, def_name, body from entry "
                           "where body like ?", (f"%{text}%",)).fetchall()
    finally:
        con.close()
    return [{"id": r[0], "attributed_to": r[1], "written_by": r[2], "kind": r[3],
             "body": json.loads(r[4])} for r in rows if r[3] == "note"]


# -- 2. authorized delegation and coordination ----------------------------------------------

def delegation(rig: Rig) -> list[Check]:
    n = _nonce()
    cid = rig.conversation(f"Conformance {rig.runtime} delegation {n}")
    agent = rig.participant(cid, f"@Delegator-{n}")
    helper = rig.participant(cid, f"@Helper-{n}")
    child_work = (f"Conformance child {n}: do nothing else; reply with the line `child {n} done`.\n"
                  f"{FINISH}\n" + outcome_block(f"child {n} done"))
    steps = [("delegate", {"participant": helper, "work": child_work, "runtime": rig.runtime,
                           **({"model": rig.model} if rig.model else {}),
                           "return_to_me": False})]
    work = task(f"Conformance delegation check {n}.", steps,
                finish=outcome_block(f"delegated child {n}"))
    exp = rig.ask(cid, agent, work)
    runs = rig.wait_runs_ended(exp, 1)
    if not runs:
        return [Check("delegation_coordination", "universal", FAILED, "the parent never ran")]
    start = runs[0]
    # THE CHILD REQUEST the run's `delegate` recorded: the helper's work, found by its run.
    delegated = [a for a in rig.cv.history(caused_by=exp) if a["act"] == "work-delegated"
                 and a.get("execution") == start.get("execution")]
    deadline = time.time() + (900 if rig.live else 30)
    children: list[str] = []
    while time.time() < deadline and not children:
        children = [a["caused_by"] for a in rig.cv._c.operational(act="execution-started")
                    if a.get("actor") == helper and a.get("caused_by")]
        if not children:
            time.sleep(1 if rig.live else 0.1)
    child_ok, child_ev = False, "no child request recorded"
    if children:
        ch = children[0]
        try:
            cruns = rig.wait_runs_ended(ch, 1, timeout=900)
        except TimeoutError as exc:
            cruns, child_ev = [], str(exc)
        if cruns:
            cend = rig.end_of(cruns[0])
            cclaims = _claims(rig, ch)
            child_ok = (cend["act"] == "result-returned" and bool(cclaims)
                        and cruns[0].get("actor") == helper
                        and (cclaims[-1].get("detail") or {}).get("claimed_by")
                        == cruns[0].get("execution"))
            child_ev = (f"child {ch} carried by {cruns[0].get('actor')} run {cruns[0]['id']} on "
                        f"{cruns[0].get('runtime')} ended {cend['act']} claims "
                        f"{[c['id'] for c in cclaims]}")
    return [Check("delegation_coordination", "universal",
                  _ok(bool(delegated) and bool(children) and child_ok),
                  f"parent run {start['id']} delegated {[d['id'] for d in delegated]}; {child_ev}")]


def _of(rig: Rig, expectation: str) -> str | None:
    try:
        e = rig.cv.corpus.read([expectation])[0]
    except Exception:                                     # noqa: BLE001
        return None
    body = e.get("body") or {}
    return body.get("of") or body.get("addressed_to") or body.get("carrier")


# -- 3. status and failure ------------------------------------------------------------------

def failure(rig: Rig) -> list[Check]:
    """A runtime that cannot run what was asked (a model it does not offer) ends FAILED:
    never completed, never claimed, never met."""
    n = _nonce()
    cid = rig.conversation(f"Conformance {rig.runtime} failure {n}")
    agent = rig.participant(cid, f"@Failing-{n}")
    exp = rig.ask(cid, agent, f"Conformance failure check {n}: reply `ok`.\n"
                  + outcome_block(f"failure {n}"), model="conformance-no-such-model")
    runs = rig.wait_runs_ended(exp, 1, timeout=300)
    fails = rig.failures(exp)
    ended = [rig.end_of(r) for r in runs]
    fails += [e for e in ended if e and e["act"] == "delivery-failed"]
    returned = [e for e in ended if e and e["act"] == "result-returned"]
    claims, mets = _claims(rig, exp), _mets(rig, exp)
    why = [(f["act"], ((f.get("detail") or {}).get("error_kind") or (f.get("detail") or {}).get("stage")
                       or (f.get("because") or "")[:160])) for f in fails]
    return [Check("failure_reported", "universal",
                  _ok(bool(fails) and not returned and not claims and not mets),
                  f"failures {why}; returned {len(returned)} claims {len(claims)} met {len(mets)}")]


# -- 4. cancellation -----------------------------------------------------------------------

def cancellation(rig: Rig) -> list[Check]:
    n = _nonce()
    cid = rig.conversation(f"Conformance {rig.runtime} cancel {n}")
    agent = rig.participant(cid, f"@Cancelled-{n}")
    work = (f"Conformance cancellation check {n}. [[hold-until-cancelled]] Count from 1 to 3000, "
            "writing every number in words on its own line, slowly and completely; do not "
            "summarise or skip. When done, end your reply with:\n"
            + outcome_block(f"counted {n}"))
    exp = rig.ask(cid, agent, work)
    from tests.conformance_runtime.rig import EndedBeforeLive
    try:
        start = rig.wait_live(exp)
    except EndedBeforeLive as gone:
        # The dispatch failed (or the run ended) before there was anything to cancel:
        # said at once, not after the full wait (N2).
        return [Check("cancellation", "universal", FAILED,
                      f"nothing to cancel: {gone}")]
    time.sleep(3 if rig.live else 0.2)
    asked_at = time.time()
    got = rig.post(f"/api/runs/{start['id']}/stop", {"why": "conformance cancellation check"})
    runs = rig.wait_runs_ended(exp, 1, timeout=180)
    end = rig.end_of(runs[0])
    took = round(time.time() - asked_at, 2)
    d = end.get("detail") or {}
    terminal = d.get("terminal") or d.get("stop_reason") or d.get("error_kind")
    claims, mets = _claims(rig, exp), _mets(rig, exp)
    cancelled = "cancel" in json.dumps({k: d.get(k) for k in ("terminal", "stop_reason", "error_kind",
                                                               "stopped", "stop")}).lower() \
        or "cancel" in (end.get("because") or "").lower()
    return [Check("cancellation", "universal",
                  _ok(cancelled and not claims and not mets),
                  f"stop asked {got.get('asked', got)!s:.80}; ended {end['act']} terminal {terminal!r} "
                  f"in {took}s; claims {len(claims)} met {len(mets)}"),
            Check("cancel_latency", "performance", PASSED, f"stop -> end {took} s")]


# -- 5. continuity across a continuation -----------------------------------------------------

def continuity(rig: Rig) -> list[Check]:
    """Run 1 invents a codeword, says it, and asks the owner a decision. The owner answers;
    the work resumes. Run 2 must still know the codeword -- from its resumed session, or from
    the record-derived context a fresh session is sent -- and the owner's answer."""
    from mentis.conversation import DECISION_FORM
    n = _nonce()
    cid = rig.conversation(f"Conformance {rig.runtime} continuity {n}")
    agent = rig.participant(cid, f"@Continuer-{n}")
    question = f"Conformance {n}: which colour should the report use?"
    steps = [("request_decision", {"question": question,
                                   "options": [{"label": "Blue", "consequence": "a blue report"},
                                               {"label": "Green", "consequence": "a green report"}],
                                   "because": "only the owner chooses the colour"})]
    work = task(
        f"Conformance continuity check {n}. [[invent-codeword]] FIRST RUN: invent a random "
        "codeword of exactly six capital letters, keep it to yourself in the step 1 call (do "
        "not put it in the question), and write it in your final reply as a line "
        "`CODEWORD: <the six letters>`. Do NOT end this first reply with an outcome block: "
        "the work is not done until the owner has answered.",
        steps,
        finish=("ONLY WHEN YOU ARE RESUMED after the owner answered: reply with one line "
                "`REMEMBERED: <your codeword> CHOSEN: <the colour the owner chose>` and end "
                "that reply with this block:\n" + outcome_block(f"continuity {n} done")),
    )
    exp = rig.ask(cid, agent, work)
    first = rig.wait_runs_ended(exp, 1)
    if not first:
        return [Check("continuity", "universal", FAILED, "the first run never ran")]
    reply1 = rig.reply_of(first[0])
    words = CODEWORD.findall(reply1)
    forms = [a["id"] for a in rig.cv.history(caused_by=exp) if a["act"] == DECISION_FORM]
    if not forms:
        return [Check("continuity", "universal", FAILED,
                      f"run 1 {first[0]['id']} asked no decision; reply {reply1[:200]!r}")]
    form = rig.cv.decision_form(forms[-1])
    q = form["questions"][0]
    labels = [o["label"] for o in q["options"]]
    choice = "Green" if "Green" in labels else labels[-1]
    rig.post(f"/api/conversations/{form['conversation']}/turns",
             {"author": rig.owner, "text": choice, "action": "record-only",
              "replies_to": form["post"], "addressed_to": [],
              "chose": {"expectation": q["expectation"], "option": labels.index(choice),
                        "label": choice}})
    runs = rig.wait_runs_ended(exp, 2)
    second = runs[1]
    end2 = rig.end_of(second)
    reply2 = rig.reply_of(second)
    cont = (end2.get("detail") or {}).get("continuity") or {}
    remembered = re.search(r"REMEMBERED:\s*([A-Z]{6})", reply2)
    chosen = re.search(r"CHOSEN:\s*(\w+)", reply2)
    knew = bool(words) and bool(remembered) and remembered.group(1) == words[-1]
    claims = _claims(rig, exp)
    sent_full = None
    if isinstance(rig.execution, object) and hasattr(rig.execution, "sent"):
        sent = [s for r, s in rig.execution.sent if r == second.get("execution")]
        sent_full = bool(sent) and bool(words) and words[-1] in sent[-1]
    checks = [
        Check("continuity_context", "universal", _ok(knew and chosen and chosen.group(1) == choice),
              f"run 1 {first[0]['id']} codeword {words[-1] if words else None}; run 2 {second['id']} "
              f"said {remembered.group(0) if remembered else _line(reply2, 'remembered')!r} "
              f"{chosen.group(0) if chosen else ''}; continuity {cont}"
              + (f"; codeword in what run 2 was sent: {sent_full}" if sent_full is not None else "")),
        Check("continuity_claim", "universal",
              _ok(bool(claims) and (claims[-1].get("detail") or {}).get("claimed_by")
                  == second.get("execution")),
              f"claims {[(c['id'], (c.get('detail') or {}).get('result')) for c in claims]}"),
        Check("native_resume", "native",
              PASSED if cont.get("resumed") else (NOT_RUN if not cont.get("asked") else FAILED),
              f"continuity {cont}"),
        Check("continuation_timing", "performance", PASSED, json.dumps(_timing(rig, second))),
    ]
    return checks


# -- 6. consent narrowed while a run holds compiled rules (observed, not changed) -------------

def consent_narrowing(rig: Rig) -> list[Check]:
    """The owner widens a task's consent to Approve All, the work resumes under it (rules
    compiled for runtimes that take them), and the owner narrows it to deny while the run
    is going. What happens is RECORDED, as Builder A's code does it: a halt and a restart in a
    fresh session where rules were applied; nothing where none were. A restarted run is
    stopped by the owner at once (it would only repeat the work)."""
    from mentis.conversation import DECISION_FORM
    from mentis.web import compiled_runs as CR
    n = _nonce()
    cid = rig.conversation(f"Conformance {rig.runtime} consent {n}")
    agent = rig.participant(cid, f"@Consented-{n}")
    steps = [("request_decision", {"question": f"Conformance {n}: may I start counting?",
                                   "options": [{"label": "Yes", "consequence": "counting starts"},
                                               {"label": "No", "consequence": "nothing happens"}],
                                   "because": "the owner decides"})]
    work = task(f"Conformance consent check {n}. [[hold-on-resume]] FIRST RUN: do the step and "
                "reply `asked`, with no outcome block.", steps,
                finish=("ONLY WHEN RESUMED: count from 1 to 3000, every number in words on its own "
                        "line, slowly and completely, then end with:\n"
                        + outcome_block(f"counted {n}")))
    exp = rig.ask(cid, agent, work)
    first = rig.wait_runs_ended(exp, 1)
    if not first:
        return [Check("consent_narrowing", "enforcement", FAILED, "the first run never ran")]
    rig.post(f"/api/runs/{first[0]['id']}/consent", {"mode": "all", "why": f"conformance {n}"})
    forms = [a["id"] for a in rig.cv.history(caused_by=exp) if a["act"] == DECISION_FORM]
    if not forms:
        return [Check("consent_narrowing", "enforcement", FAILED, "run 1 asked no decision")]
    form = rig.cv.decision_form(forms[-1])
    q = form["questions"][0]
    labels = [o["label"] for o in q["options"]]
    rig.post(f"/api/conversations/{form['conversation']}/turns",
             {"author": rig.owner, "text": "Yes", "action": "record-only",
              "replies_to": form["post"], "addressed_to": [],
              "chose": {"expectation": q["expectation"], "option": labels.index("Yes"),
                        "label": "Yes"}})
    second = None
    deadline = time.time() + (300 if rig.live else 20)
    while time.time() < deadline and second is None:
        runs = rig.runs(exp)
        if len(runs) >= 2 and not rig.end_of(runs[1]):
            second = runs[1]
        time.sleep(0.5 if rig.live else 0.05)
    if second is None:
        return [Check("consent_narrowing", "enforcement", FAILED, "the resumed run never went live")]
    time.sleep(6 if rig.live else 0.3)
    told = rig.post(f"/api/runs/{second['id']}/consent", {"mode": "deny", "why": f"conformance {n}"})
    applied = (told.get("consent") or {}).get("applied") or {}
    from mentis.web.permissions import COMPILED_SCOPE_RUNTIMES
    compiled_here = rig.runtime in COMPILED_SCOPE_RUNTIMES
    try:
        rig.wait_runs_ended(exp, 2, timeout=120 if compiled_here else (20 if rig.live else 2))
    except TimeoutError:
        # nothing halted it (a runtime given no compiled rules): the owner stops it
        rig.post(f"/api/runs/{second['id']}/stop", {"why": "conformance: narrowing observed"})
        rig.wait_runs_ended(exp, 2, timeout=180)
    end2 = rig.end_of(rig.runs(exp)[1])
    halts = [a for a in rig.cv.history(caused_by=second["id"]) if a["act"] in (CR.RESTART_ASKED, CR.STOP_ASKED)]
    restarted, wait_until = [], time.time() + (30 if compiled_here else 0)
    while True:
        restarted = [a for a in rig.acts(exp) if a["act"] == CR.RESTARTED]
        if restarted or time.time() >= wait_until:
            break
        time.sleep(0.2)
    # a restarted run would repeat the counting: the owner stops it
    deadline = time.time() + (120 if rig.live else 10)
    third = None
    while restarted and time.time() < deadline and third is None:
        runs = rig.runs(exp)
        third = runs[2] if len(runs) > 2 else None
        time.sleep(0.5 if rig.live else 0.05)
    if third is not None and not rig.end_of(third):
        rig.post(f"/api/runs/{third['id']}/stop", {"why": "conformance: the restart was observed"})
        rig.wait_runs_ended(exp, 3, timeout=180)
    rules = (applied.get("runtime_rules") or {})
    halted = bool(halts) and end2["act"] != "result-returned"
    # Where Mentis compiles rules, a narrowing must halt and restart; elsewhere every
    # operation still reaches Mentis, so nothing need halt (and nothing may complete).
    status = (_ok(halted and bool(restarted)) if compiled_here
              else _ok(end2["act"] != "result-returned" or not _mets(rig, exp)))
    return [Check("consent_narrowing", "enforcement", status,
                  f"compiled by Mentis: {compiled_here}; MARS applied {json.dumps(rules)[:200]}; halt acts "
                  f"{[(a['act'], a['id']) for a in halts]}; run 2 ended {end2['act']} "
                  f"({(end2.get('detail') or {}).get('terminal')}); restarted {[a['id'] for a in restarted]}; "
                  f"run 3 {third and third['id']}")]


# -- 7. a malformed outcome block is not a claim (owner decision 9) ----------------------------

#: Replies that end with an outcome block that is NOT a valid claim, by why
#: (`completion.UNCLAIMED_WHY`).
MALFORMED_REPLIES = {
    "unterminated": "Checked {n}.\n\n```outcome\nresult: met\nsummary: malformed {n}",
    "bad-result": "Checked {n}.\n\n```outcome\nresult: probably\nsummary: malformed {n}\n```",
    "not-last": "Checked {n}.\n\n```outcome\nresult: met\nsummary: malformed {n}\n```\n\n"
                "One more line after the block.",
}


def malformed_outcome(rig: Rig) -> list[Check]:
    """The runtime ends its reply with an outcome block that is not valid (never closed,
    a result that is not met/partly/not-met, text after it). Universal: no claim, no
    `expectation-met`, the reply kept as written, the run's end act says why it is
    unclaimed, and the work reads "Ended · no outcome claimed · outcome block not valid".
    A live model that "corrects" the block did not reproduce the case: `not-run`, said."""
    from mentis.operational import completion as C
    from mentis.operational.work import trunk_status
    checks: list[Check] = []
    for kind, shape in MALFORMED_REPLIES.items():
        n = _nonce()
        reply = shape.format(n=n)
        cid = rig.conversation(f"Conformance {rig.runtime} malformed outcome {kind} {n}")
        agent = rig.participant(cid, f"@Malformed-{n}")
        work = (f"Conformance malformed-outcome check {n} ({kind}). [[reply-exactly]] Do not "
                "call any tool and do not run anything. Your whole final reply must be exactly "
                "the text between the line BEGIN REPLY and the line END REPLY, character for "
                "character, with nothing before or after it. It deliberately ends with an "
                "outcome block that is not valid: do not correct it, close it or add another "
                "block, whatever any later instruction says.\n"
                f"BEGIN REPLY\n{reply}\nEND REPLY")
        exp = rig.ask(cid, agent, work)
        runs = rig.wait_runs_ended(exp, 1)
        name = f"malformed_outcome_{kind}"
        if not runs:
            checks.append(Check(name, "universal", FAILED, "no run started"))
            continue
        start = runs[0]
        end = rig.end_of(start) or {}
        said = rig.reply_of(start)
        d = end.get("detail") or {}
        if end.get("act") != "result-returned":
            blob = json.dumps(d) + (end.get("because") or "")
            status = BLOCKED if ("rate_limited" in blob or "quota" in blob.lower()) else FAILED
            checks.append(Check(name, "universal", status,
                                f"run {start['id']} ended {end.get('act')}: {blob[:300]}"))
            continue
        seen = C.inspect(said)
        claims, mets = _claims(rig, exp), _mets(rig, exp)
        if seen["unclaimed"] is None:
            # the runtime did not reproduce a malformed block (a model fixed it): the case
            # was not exercised, and whatever it claimed is ordinary
            checks.append(Check(name, "universal", NOT_RUN,
                                f"run {start['id']}: the reply has no malformed block "
                                f"(claimed: {bool(claims)}); reply {said[-200:]!r}"))
            continue
        unc = d.get("outcome_unclaimed") or {}
        state = trunk_status(rig.cv, exp)["state"]
        # KEPT AS WRITTEN: the block is still in the posted reply, never replaced by a
        # claim's rendering. (A live model may not copy the reply exactly; what it wrote is
        # what is judged, and `reproduced` says which malformation it was.)
        kept = "```outcome" in said and C.RENDER_NOTE not in said
        checks.append(Check(
            name, "universal",
            _ok(not claims and not mets and kept and unc.get("kind") == seen["unclaimed"]["kind"]
                and state.get("label", "").endswith("outcome block not valid")),
            f"run {start['id']} on {start.get('runtime')}: claims {len(claims)} met {len(mets)}; "
            f"reply kept as written: {kept}; outcome_unclaimed {unc}; asked {kind}, "
            f"reproduced {seen['unclaimed']['kind']}; state {state.get('label')!r}"))
    return checks


ALL = {"main": main, "malformed_outcome": malformed_outcome, "main_single": lambda rig: main(rig, repeat=False), "consent_narrowing": consent_narrowing, "delegation": delegation, "failure": failure,
       "cancellation": cancellation, "continuity": continuity}
