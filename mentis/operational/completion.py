"""Completion and accountability: an agent's CLAIM, and what the record makes
of it (WS-C, `docs/modernization/CONTRACT.md`).

FOUR FACTS, NONE IMPLYING ANOTHER:

    execution ended        `result-returned` / `result-recovered` / failures
    outcome claimed        `outcome-claimed` (this module), by the agent: the
                           ```outcome block ending its final reply, `respond`
                           (`fulfils` / `outcome`), or `record_outcome`
    objective met          `expectation-met`, written HERE by reconciliation,
                           `detail.reconciled_from` naming the claim
    verified               a `review-verdict` with verdict `pass`

A run ending never completes work by itself. A claim of `met` becomes
`expectation-met` only when `reconcile`'s four rules hold; otherwise an
`outcome-pending` act says why. `partly` and `not-met` claims are recorded as
they stand and never become met. Reconciling the same claim again writes
nothing new.

A claim is only ever about the claimant's OWN assigned expectation (the run's
`expectation`, the session's request). Making one needs no organising or
`coordinate` authority, confers nothing, launches nothing, establishes nothing.

REVIEW BEFORE COMPLETION (rule 4). Mentis records no machine-readable "this
Workflow requires review" flag. What it does record is a Workflow's activity
rows, each with a `who.persona` and a `what`; `stage.is_review` already reads
a Persona whose name says review, or a brief that opens as one, as review
work. So a request whose governing Workflow (`governed_named`) has such an
activity requires a review before its claim of met is recorded -- unless the
request is itself review work, or is itself one activity of a Workflow (the
review covers the whole, not each step). A `review-verdict` `pass` recorded
under it (by a review it delegated, or by a request declared `review_of` it)
satisfies the rule, and recording one reconciles the claim waiting on it
(`on_review_pass`).

Also here: `regards` links (`link_regarding`), neutral references from a later
record to an expectation, a claim or a Turn, and the `later_findings` read.
"""

from __future__ import annotations

import re

OUTCOME_CLAIMED = "outcome-claimed"
OUTCOME_PENDING = "outcome-pending"
EXPECTATION_MET = "expectation-met"
REVIEW_VERDICT = "review-verdict"
STARTED = "execution-started"
FAILED = "delivery-failed"
#: The neutral link from a later record to what it is about.
REGARDS = "regards"
REGARDS_INVERSE = "regarded-by"
REGARDS_MEANING = (
    "This record was made later about that expectation, outcome claim or "
    "Turn. Neutral: it reopens nothing, blames nobody and rewrites nothing; "
    "the original claim and its evidence stand as recorded.")
#: The most ids one record may say it regards.
MAX_REGARDING = 20

RESULTS = ("met", "partly", "not-met")
_RESULT_WORDS = {"met": "met", "partly": "partly done", "not-met": "not met"}
_ALIASES = {
    "met": "met", "done": "met", "complete": "met", "completed": "met",
    "yes": "met",
    "partly": "partly", "partial": "partly", "partially": "partly",
    "partly-met": "partly", "partially-met": "partly",
    "not-met": "not-met", "notmet": "not-met", "not": "not-met",
    "no": "not-met", "not-done": "not-met", "failed": "not-met",
    "blocked": "not-met", "abandoned": "not-met", "unmet": "not-met",
}
#: `record_outcome`'s words, mapped onto a claim.
RECORD_OUTCOME_RESULTS = {"done": "met", "partial": "partly",
                          "abandoned": "not-met", "blocked": "not-met",
                          "failed": "not-met"}

#: A fenced ```outcome block. The LAST one in a reply is the claim.
_BLOCK = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*outcome[ \t]*\r?\n"
                    r"(?P<body>.*?)"
                    r"^[ \t]*\1[ \t]*$\r?\n?",
                    re.MULTILINE | re.DOTALL | re.IGNORECASE)
_KEY = re.compile(r"^\s*([A-Za-z_][\w\- ]*?)\s*:\s*(.*)$")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")

#: THE CLOSING INSTRUCTION every dispatched run is given (`dispatch.
#: _closing_block`): how to end its reply with a claim. Short and exact.
CLOSING_INSTRUCTION = (
    "End your final reply with an outcome block, exactly this shape -- it is "
    "your claim about this request, recorded as yours, and no extra call is "
    "needed:\n"
    "```outcome\n"
    "result: met | partly | not-met\n"
    "summary: one line saying what was done or not done\n"
    "evidence:\n"
    "- commit, test result, record id, path or URL\n"
    "```\n"
    "Claim met only for what you actually did. A claim is checked before it "
    "is recorded as met: open decisions, children you wait on, and a "
    "required review keep it pending.")


# -- the claim, as written ------------------------------------------------------

def normalize_result(value) -> str | None:
    """`met` | `partly` | `not-met`, or None for anything else."""
    text = str(value or "").split("#", 1)[0].strip().lower()
    text = re.sub(r"[\s_]+", "-", text).strip("-.")
    return _ALIASES.get(text)


def normalize(outcome, *, default_result=None) -> dict | None:
    """`{result, summary, evidence[], ...unknown keys}` from a dict the
    caller supplied, or None when it names no result this understands."""
    if not isinstance(outcome, dict):
        outcome = {}
    result = normalize_result(outcome.get("result")) or default_result
    if result not in RESULTS:
        return None
    evidence = outcome.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    evidence = [str(e).strip() for e in evidence if str(e).strip()][:50]
    out = {k: v for k, v in outcome.items()
           if k not in ("result", "summary", "evidence")}
    out.update(result=result,
               summary=str(outcome.get("summary") or "").strip()[:1000],
               evidence=evidence)
    return out


def _parse_body(body: str) -> dict:
    """Lenient `key: value` lines; `evidence` takes the list items after it
    (or an inline value). Key order is free; unknown keys are kept."""
    out: dict = {}
    current = None
    for raw in body.splitlines():
        if not raw.strip():
            continue
        item = _ITEM.match(raw)
        if item and current is not None:
            if not isinstance(out.get(current), list):
                first = out.get(current)
                out[current] = [first] if first else []
            out[current].append(item.group(1).strip())
            continue
        kv = _KEY.match(raw)
        if kv:
            key = kv.group(1).strip().lower().replace(" ", "_")
            value = kv.group(2).strip()
            if key == "result":
                value = value.split("#", 1)[0].strip()
            out[key] = value
            current = key
            continue
        if current == "summary" and isinstance(out.get("summary"), str):
            out["summary"] = (out["summary"] + " " + raw.strip()).strip()
    return out


def extract(text: str | None) -> tuple[dict | None, str]:
    """(the claim in the LAST ```outcome block, the text without it).

    A block naming no result this understands is not a claim: it is left in
    the text, untouched, and None is returned."""
    text = text or ""
    blocks = list(_BLOCK.finditer(text))
    if not blocks:
        return None, text
    last = blocks[-1]
    claim = normalize(_parse_body(last.group("body")))
    if claim is None:
        return None, text
    stripped = (text[:last.start()] + text[last.end():]).strip()
    return claim, stripped


def render(claim: dict) -> str:
    """The one line a reply shows instead of the block."""
    line = (f"Outcome claimed: {_RESULT_WORDS.get(claim['result'], claim['result'])}"
            + (f" — {claim['summary']}" if claim.get("summary") else ""))
    ev = claim.get("evidence") or []
    if ev:
        shown = "; ".join(ev[:5]) + (f" (+{len(ev) - 5} more)"
                                     if len(ev) > 5 else "")
        line += f" · evidence: {shown}"
    return line


def with_rendering(text: str, claim: dict) -> str:
    """The reply text with the block's one-line rendering added."""
    line = render(claim)
    return (text.rstrip() + "\n\n" + line) if text.strip() else line


def claim(cv, expectation, outcome: dict, *, actor, execution=None,
          runtime=None, via, reply_turn=None, conversation=None,
          participant=None, extra=None) -> str:
    """Write `outcome-claimed` about `expectation`. Returns the act id."""
    exp = cv._act(expectation) or {}
    detail = {**{k: v for k, v in outcome.items()
                 if k not in ("result", "summary", "evidence")},
              **(extra or {}),
              "result": outcome["result"], "summary": outcome.get("summary")
              or "", "evidence": list(outcome.get("evidence") or ()),
              "claimed_by": execution, "runtime": runtime,
              "participant": participant or actor, "via": via,
              "reply_turn": reply_turn}
    return cv.record_act(
        actor=actor, act=OUTCOME_CLAIMED,
        conversation=conversation or exp.get("conversation"),
        turn=reply_turn, execution=execution, runtime=runtime,
        caused_by=expectation, about=[expectation],
        because=(outcome.get("summary") or f"claimed {outcome['result']}")[:400],
        detail=detail)


def claims_of(cv, expectation) -> list[dict]:
    """Every claim about this expectation, in write order."""
    got = [a for a in cv._children(expectation)
           if a["act"] == OUTCOME_CLAIMED]
    seq = cv._write_order([a["id"] for a in got])
    return sorted(got, key=lambda a: seq.get(a["id"], -1))


def latest_claim(cv, expectation) -> dict | None:
    got = claims_of(cv, expectation)
    return got[-1] if got else None


# -- reconciliation ---------------------------------------------------------------

def _persona_name(cv, persona) -> str:
    if not persona:
        return ""
    try:
        got = cv.corpus.read([persona])
    except Exception:                                     # noqa: BLE001
        return ""
    return str(((got[0].get("body") or {}).get("name") or "")) if got else ""


def _text_of(cv, turn) -> str:
    if not turn:
        return ""
    try:
        got = cv.corpus.read([turn])
    except Exception:                                     # noqa: BLE001
        return ""
    parts = ((got[0].get("body") or {}).get("parts") or []) if got else []
    return " ".join(str(p.get("text") or "") for p in parts
                    if isinstance(p, dict))


def is_review_work(cv, expectation) -> bool:
    """This request is itself a review: by the Persona it wears, by a
    declared `review_of`, or by what it was asked (`stage.is_review`)."""
    from mentis.operational.stage import is_review
    exp = cv._act(expectation) or {}
    d = exp.get("detail") or {}
    repo = d.get("repository")
    if isinstance(repo, dict) and repo.get("review_of"):
        return True
    persona = d.get("persona")
    if not persona and exp.get("caused_by"):
        # the delegation that made it says what it wears
        for a in cv._children(exp["caused_by"]):
            if a["act"] == "work-delegated" and (a.get("about") or [None])[0] \
                    == expectation:
                persona = (a.get("detail") or {}).get("persona") or persona
    return is_review(_text_of(cv, exp.get("turn")), exp.get("because"),
                     _persona_name(cv, persona))


def review_required(cv, expectation) -> bool:
    """Whether the Workflow governing this request has a review activity it
    must pass before a claim of met is recorded (module docstring)."""
    from mentis.conversation import activities_of
    from mentis.operational.stage import is_review
    if cv.activity_named(expectation):
        return False
    governed = cv.governed_named(expectation)
    if not governed:
        return False
    try:
        entries = cv.corpus.read(list(governed))
    except Exception:                                     # noqa: BLE001
        return False
    for e in entries:
        for row in activities_of(cv.corpus, e):
            who = row.get("who") or {}
            if is_review(row.get("what"), row.get("key"),
                         _persona_name(cv, who.get("persona"))):
                return not is_review_work(cv, expectation)
    return False


def review_passed(cv, expectation) -> dict | None:
    """The newest `review-verdict` under this work, or naming it through a
    review declared `review_of` it, when that verdict is `pass`."""
    under = cv._descendants(expectation)
    reviewers = {a["id"] for a in under if a["act"] == "expectation-recorded"}
    verdicts = [a for a in under if a["act"] == REVIEW_VERDICT]
    every = (cv._recall(("acts", REVIEW_VERDICT),
                        lambda: cv.history(act=REVIEW_VERDICT))
             if hasattr(cv, "_recall") else cv.history(act=REVIEW_VERDICT))
    for v in every:
        target = (v.get("about") or [None])[0]
        if target in reviewers or v["id"] in {x["id"] for x in verdicts}:
            continue
        d = ((cv._act(target) or {}).get("detail") or {}) if target else {}
        repo = d.get("repository")
        if isinstance(repo, dict) and repo.get("review_of") == expectation:
            verdicts.append(v)
    if not verdicts:
        return None
    seq = cv._write_order([a["id"] for a in verdicts])
    newest = max(verdicts, key=lambda a: seq.get(a["id"], -1))
    verdict = str((newest.get("detail") or {}).get("verdict") or "").lower()
    return newest if verdict == "pass" else None


def _rules(cv, expectation, claim_act) -> tuple[list[str], list[str]]:
    """(reasons that keep a claim of met pending, notes that do not)."""
    reasons, notes = [], []
    own = cv._own_acts(expectation)
    # 1. the latest execution ended normally: no failure or cancel after the
    #    claim, and not still running
    starts = [a for a in own if a["act"] == STARTED]
    if starts:
        seq = cv._write_order([a["id"] for a in starts] + [claim_act["id"]])
        latest = max(starts, key=lambda a: seq.get(a["id"], -1))
        end = cv.run_end(latest["id"])
        if end is None:
            reasons.append("its run has not ended yet")
        elif end["act"] == FAILED:
            order = cv._write_order([end["id"], claim_act["id"]])
            if order.get(end["id"], -1) > order.get(claim_act["id"], -1) \
                    or end.get("execution") == claim_act.get("execution"):
                cancelled = "terminal 'cancelled'" in (end.get("because") or "")
                reasons.append("its run was cancelled after the claim"
                               if cancelled else
                               "its run failed after the claim")
    # 2. no decision or input it asked for is open
    waiting = cv.waiting_on(expectation)
    for d in waiting["decisions"]:
        if not d["answered"]:
            reasons.append(f"decision {d['expectation']} is open")
    for i in waiting["inputs"]:
        if not i["answered"]:
            reasons.append(f"input {i['expectation']} is awaited")
    # 3. no child it declared it waits on is unended; children that ended
    #    unmet are listed, and block nothing by themselves
    waited = set()
    for c in waiting["required"]:
        waited.add(c["expectation"])
        if c["state"] in ("running", "not-ended"):
            reasons.append(f"child {c['expectation']} has not ended")
    for w in waiting["awaited"]:
        waited.add(w["expectation"])
        if not w.get("ended"):
            reasons.append(f"awaited work {w['expectation']} has not ended")
    for a in cv._children(expectation):
        if a["act"] != "work-delegated" or not a.get("about"):
            continue
        child = a["about"][0]
        try:
            s = cv._child_state(child)
        except Exception:                                 # noqa: BLE001
            continue
        if s["state"] not in ("running", "not-ended") \
                and not s["claimed_met_by"]:
            notes.append(f"child {child} not met")
    # 4. review before completion, where its Workflow requires it
    if review_required(cv, expectation) and not review_passed(cv, expectation):
        reasons.append("review required")
    return reasons, notes


def _resolve(cv, claim_act) -> dict | None:
    if isinstance(claim_act, dict):
        return claim_act
    got = cv._act(claim_act)
    return got if got and got["act"] == OUTCOME_CLAIMED else None


def reconcile(cv, expectation, claim_act) -> dict:
    """What the record makes of one claim: `{"recorded": "met" | "pending" |
    "partly" | "not-met", "reasons": [...], "notes": [...], "act": id|None}`.

    Idempotent: a claim already reconciled met, or pending for the same
    reasons, writes nothing new."""
    c = _resolve(cv, claim_act)
    if c is None:
        raise ValueError(f"{claim_act!r} is not an outcome claim")
    d = c.get("detail") or {}
    result = d.get("result")
    if result != "met":
        return {"recorded": result, "reasons": [], "notes": [], "act": None}
    own = cv._own_acts(expectation)
    done = [a for a in own if a["act"] == EXPECTATION_MET
            and (a.get("detail") or {}).get("reconciled_from") == c["id"]]
    if done:
        return {"recorded": "met", "reasons": [], "notes": [],
                "act": done[0]["id"], "already": True}
    if cv.expectation_state(expectation)["satisfied_by"]:
        # met by another path already: the claim stands beside it
        return {"recorded": "met", "reasons": [], "notes": [], "act": None,
                "already": True}
    reasons, notes = _rules(cv, expectation, c)
    if not reasons:
        reply = d.get("reply_turn")
        results = [str(r) for r in (d.get("results") or ()) if r]
        met = cv.record_act(
            actor=c["actor"], act=EXPECTATION_MET,
            conversation=c.get("conversation"), turn=reply,
            execution=c.get("execution"), runtime=c.get("runtime"),
            caused_by=expectation,
            about=[x for x in [reply, *results] if x] or [c["id"]],
            because=(d.get("because") or d.get("summary")
                     or "claimed met and reconciled"),
            detail={"claimed_by": d.get("claimed_by"),
                    "reconciled_from": c["id"],
                    "reconciled_by": "mentis",
                    "via": d.get("via"),
                    "result_kind": d.get("result_kind"),
                    **({"notes": notes} if notes else {})})
        return {"recorded": "met", "reasons": [], "notes": notes, "act": met}
    pending = [a for a in own if a["act"] == OUTCOME_PENDING
               and (a.get("detail") or {}).get("claim") == c["id"]]
    if pending:
        seq = cv._write_order([a["id"] for a in pending])
        last = max(pending, key=lambda a: seq.get(a["id"], -1))
        if list((last.get("detail") or {}).get("reasons") or ()) == reasons:
            return {"recorded": "pending", "reasons": reasons, "notes": notes,
                    "act": last["id"], "already": True}
    act = cv.record_act(
        actor="mentis", act=OUTCOME_PENDING,
        conversation=c.get("conversation"), turn=d.get("reply_turn"),
        caused_by=expectation, about=[expectation, c["id"]],
        because="claimed met; pending: " + reasons[0],
        detail={"claim": c["id"], "reasons": reasons,
                **({"notes": notes} if notes else {})})
    return {"recorded": "pending", "reasons": reasons, "notes": notes,
            "act": act}


def reconcile_latest(cv, expectation) -> dict | None:
    """Reconcile this expectation's newest claim, if it has one."""
    if not expectation:
        return None
    c = latest_claim(cv, expectation)
    return reconcile(cv, expectation, c) if c else None


def on_review_pass(cv, reviewer_expectation) -> list[dict]:
    """A `review-verdict pass` was recorded under `reviewer_expectation`:
    reconcile every claim it may have been holding -- the work it was
    delegated under (each request up its lineage) and a request it was
    declared `review_of`."""
    targets = []
    d = ((cv._act(reviewer_expectation) or {}).get("detail") or {})
    repo = d.get("repository")
    if isinstance(repo, dict) and isinstance(repo.get("review_of"), str):
        targets.append(repo["review_of"])
    cur, seen = (cv._act(reviewer_expectation) or {}).get("caused_by"), set()
    while cur and cur not in seen and len(seen) < 64:
        seen.add(cur)
        a = cv._act(cur)
        if a is None:
            break
        if a["act"] == "expectation-recorded":
            targets.append(a["id"])
        cur = a.get("caused_by")
    out = []
    for t in dict.fromkeys(targets):
        c = latest_claim(cv, t)
        if c and (c.get("detail") or {}).get("result") == "met":
            out.append(reconcile(cv, t, c))
    return out


# -- what the record says of a claim, for the work views ---------------------------

def claim_view(cv, expectation, *, own=None) -> dict | None:
    """The newest claim about this expectation, and what reconciliation made
    of it: `{act, result, summary, evidence, claimed_by, participant, via,
    at, recorded: met|pending|partly|not-met|None, reasons}`. None without
    a claim. Read only; nothing is written."""
    own = own if own is not None else cv._own_acts(expectation)
    claims = [a for a in own if a["act"] == OUTCOME_CLAIMED
              and a.get("caused_by") == expectation]
    if not claims:
        return None
    seq = cv._write_order([a["id"] for a in claims])
    c = max(claims, key=lambda a: seq.get(a["id"], -1))
    d = c.get("detail") or {}
    recorded, reasons = None, []
    if d.get("result") in ("partly", "not-met"):
        recorded = d["result"]
    elif any(a["act"] == EXPECTATION_MET for a in own):
        recorded = "met"
    else:
        pend = [a for a in own if a["act"] == OUTCOME_PENDING
                and (a.get("detail") or {}).get("claim") == c["id"]]
        if pend:
            ps = cv._write_order([a["id"] for a in pend])
            last = max(pend, key=lambda a: ps.get(a["id"], -1))
            recorded = "pending"
            reasons = list((last.get("detail") or {}).get("reasons") or ())
    return {"act": c["id"], "result": d.get("result"),
            "summary": d.get("summary") or "",
            "evidence": list(d.get("evidence") or ()),
            "claimed_by": d.get("claimed_by"),
            "participant": d.get("participant") or c.get("actor"),
            "via": d.get("via"), "at": c.get("at"),
            "recorded": recorded, "reasons": reasons}


# -- later findings ----------------------------------------------------------------

def _ensure_relation(cv) -> None:
    corpus = cv.corpus
    if corpus.current_definition(REGARDS) is None:
        corpus.define_relation(REGARDS, inverse=REGARDS_INVERSE,
                               properties={"meaning": REGARDS_MEANING},
                               attributed_to="human")


def check_regarding(cv, ids) -> list[str]:
    """The ids, de-duplicated, each an expectation, an outcome claim or a
    Turn in this record. Raises ValueError naming the first that is not."""
    if ids is None:
        return []
    if isinstance(ids, str):
        ids = [ids]
    out = list(dict.fromkeys(str(i).strip() for i in ids if str(i).strip()))
    if len(out) > MAX_REGARDING:
        raise ValueError(f"`regarding` names at most {MAX_REGARDING} records")
    for i in out:
        act = cv._act(i) if i.startswith("opr-") else None
        if act is not None:
            if act["act"] not in ("expectation-recorded", OUTCOME_CLAIMED):
                raise ValueError(
                    f"{i!r} is a {act['act']!r} act; `regarding` names an "
                    f"expectation, an outcome claim or a Turn")
            continue
        try:
            got = cv.corpus.read([i])
        except Exception:                                 # noqa: BLE001
            got = []
        if not got:
            raise ValueError(f"{i!r} is not an expectation, an outcome claim "
                             f"or a Turn in this record")
    return out


def link_regarding(cv, record_id, ids, actor, *, written_by=None) -> list[str]:
    """Write a `regards` link from `record_id` to each of `ids`, attributed
    to `actor`. Neutral: nothing is reopened, blamed or rewritten. Returns
    the link ids. The ids are checked first (`check_regarding`); a refusal
    writes nothing."""
    ids = check_regarding(cv, ids)
    if not ids or not record_id:
        return []
    _ensure_relation(cv)
    return cv.corpus.link_many(
        [{"from": record_id, "to": i, "relation": REGARDS} for i in ids],
        body={"reason": "recorded later, regarding this"},
        attributed_to=actor, written_by=written_by)


def later_findings(cv, expectation, *, own=None) -> list[dict]:
    """`[{id, kind, at}]`: records linked `regards` to this expectation, to
    a claim about it, or to its own Turn or a claim's reply Turn."""
    try:
        if cv.corpus.current_definition(REGARDS) is None:
            return []
    except Exception:                                     # noqa: BLE001
        return []
    exp = cv._act(expectation) or {}
    own = own if own is not None else cv._children(expectation)
    targets = {expectation}
    if exp.get("turn"):
        targets.add(exp["turn"])
    for a in own:
        if a["act"] == OUTCOME_CLAIMED:
            targets.add(a["id"])
            reply = (a.get("detail") or {}).get("reply_turn")
            if reply:
                targets.add(reply)
    links = cv.corpus.links(relation=REGARDS, to_any=sorted(targets))
    out, seen = [], set()
    for link in links:
        frm = (link.get("link") or {}).get("from")
        if not frm or frm in seen:
            continue
        seen.add(frm)
        kind = None
        a = cv._act(frm) if str(frm).startswith("opr-") else None
        if a is not None:
            kind = a["act"]
        else:
            try:
                got = cv.corpus.read([frm])
            except Exception:                             # noqa: BLE001
                got = []
            if got:
                kind = (got[0].get("definition") or {}).get("name")
        out.append({"id": frm, "kind": kind,
                    "at": link.get("recorded_at") or link.get("at")})
    return out


# -- re-reconciling when what held a claim clears ---------------------------------

def pending_claim(cv, expectation) -> dict | None:
    """The newest claim about this expectation when it is a claim of met
    that reconciliation left pending, and nothing has moved the work on
    since (no `work-resumed` after it: a resumed run decides for itself).
    None otherwise. Cheap: one walk of the expectation's own acts."""
    own = cv._own_acts(expectation)
    claims = [a for a in own if a["act"] == OUTCOME_CLAIMED
              and a.get("caused_by") == expectation]
    if not claims or any(a["act"] == EXPECTATION_MET for a in own):
        return None
    seq = cv._write_order([a["id"] for a in own])
    c = max(claims, key=lambda a: seq.get(a["id"], -1))
    if (c.get("detail") or {}).get("result") != "met":
        return None
    if not any(a["act"] == OUTCOME_PENDING
               and (a.get("detail") or {}).get("claim") == c["id"]
               for a in own):
        return None
    if any(a["act"] == "work-resumed"
           and seq.get(a["id"], -1) > seq.get(c["id"], -1) for a in own):
        return None
    return c


def reconcile_if_pending(cv, expectation) -> dict | None:
    """Reconcile this expectation's pending claim again, if it has one."""
    c = pending_claim(cv, expectation) if expectation else None
    return reconcile(cv, expectation, c) if c else None


def _enclosing_work(cv, expectation) -> str | None:
    """The expectation this one was asked or delegated under, if any."""
    cur, seen = (cv._act(expectation) or {}).get("caused_by"), set()
    while cur and cur not in seen and len(seen) < 64:
        seen.add(cur)
        a = cv._act(cur)
        if a is None:
            return None
        if a["act"] == "expectation-recorded":
            return a["id"]
        cur = a.get("caused_by")
    return None


def reconcile_held_by(cv, cleared) -> list[dict]:
    """`cleared` -- a decision or input that was answered, or a child or
    awaited piece of work that ended -- may have been what held a claim of
    met pending. Reconcile the pending claim of the work it was asked or
    delegated under, and of every work that declared it waits on it. Only
    expectations whose newest claim is pending are touched; idempotent."""
    if not cleared:
        return []
    targets = [_enclosing_work(cv, cleared)]
    try:
        targets += cv.awaited_by(cleared)
    except Exception:                                     # noqa: BLE001
        pass
    out = []
    for t in dict.fromkeys(x for x in targets if x):
        got = reconcile_if_pending(cv, t)
        if got is not None:
            out.append(got)
    return out


def reconcile_held_by_quietly(cv, cleared) -> list[dict]:
    """`reconcile_held_by` for paths whose own write must never fail
    because of it: an error is printed and nothing is returned."""
    try:
        return reconcile_held_by(cv, cleared)
    except Exception:                                     # noqa: BLE001
        import traceback
        traceback.print_exc()
        return []
