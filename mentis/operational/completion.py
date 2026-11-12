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
    "required review keep it pending. Presenting work for approval means asking "
    "a decision: include approval: <exact commit/artifact ids> in the outcome "
    "block, or outcome.approval={artifacts:[...]} in respond. This creates "
    "request_decision on your result post; the owner's answer resumes this "
    "request. A partly claim needs a recorded continuation: delegate with "
    "resume_on_return, await_work, request_decision/request_input, or "
    "arm_detached before promising a later check.")


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
    evidence = [one_line(e, 300) for e in evidence if str(e).strip()][:50]
    out = {"result": result,
           "summary": one_line(outcome.get("summary"), 1000),
           "evidence": evidence}
    if outcome.get("approval"):
        approval = outcome["approval"]
        if isinstance(approval, str):
            approval = {"artifacts": [approval]}
        if not isinstance(approval, dict):
            raise ValueError("approval names exact artifacts")
        refs = approval.get("artifacts") or evidence
        if not isinstance(refs, list) or not refs or not all(
                isinstance(r, str) and r.strip() for r in refs):
            raise ValueError("approval.artifacts needs exact commit/artifact ids")
        out["approval"] = {"artifacts": [one_line(r, 300) for r in refs],
                           "question": one_line(approval.get("question"), 1000)}
    if outcome.get("owner_wait"):
        out["owner_wait"] = one_line(outcome["owner_wait"], 1000)
    # UNKNOWN KEYS ARE KEPT, AND KEPT APART: under `extra`, as plain short
    # strings, never beside the keys Mentis reads (`because`, `results`,
    # `about`, ...), so a claim can never set what a system act says.
    extra = {str(k)[:40]: one_line(v, 300) for k, v in outcome.items()
             if k not in ("result", "summary", "evidence", "extra", "approval", "owner_wait")}
    if isinstance(outcome.get("extra"), dict):
        extra.update({str(k)[:40]: one_line(v, 300)
                      for k, v in outcome["extra"].items()})
    if extra:
        out["extra"] = dict(list(extra.items())[:10])
    return out


def one_line(value, limit=200) -> str:
    """Text as one clipped plain line: whitespace and newlines collapsed,
    control characters dropped. For labels and the rendered claim."""
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(v) for v in value)
    text = " ".join(str(value if value is not None else "").split())
    text = "".join(ch for ch in text if ch.isprintable())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def label_text(value, limit=120) -> str:
    """A claimant's words inside a status label: one line, clipped, with
    markdown markers removed so they cannot restyle or extend the label."""
    return one_line(re.sub(r"[`*_#>\[\]|~<]", "", one_line(value, 4 * limit)),
                    limit)


_MD = re.compile(r"([\\`*_\[\]#<>|~])")


def _md(value, limit=200) -> str:
    """One line, with markdown escaped, for the rendered reply line."""
    return _MD.sub(r"\\\1", one_line(value, limit))


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


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)")
_FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")


def _top_level_outcome_blocks(text: str) -> list[tuple[int, int, str]]:
    """`(start, end, body)` of every ```outcome fence that is not inside
    another fence and not in a quote (a quoted line opens nothing)."""
    return _scan(text)[0]


def _scan(text: str) -> tuple[list[tuple[int, int, str]], tuple | None]:
    """`(blocks, dangling)`: the closed top-level ```outcome fences, and the
    fence still open when the text ends -- `(info word, start)` -- or None."""
    blocks, pos, open_ = [], 0, None
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if open_ is None:
            m = _FENCE_OPEN.match(bare)
            if m and not (m.group(1)[0] == "`" and "`" in bare[m.end():]):
                open_ = (m.group(1)[0], len(m.group(1)),
                         m.group(2).lower(), pos, pos + len(line))
        else:
            m = _FENCE_CLOSE.match(bare)
            if m and m.group(1)[0] == open_[0] and len(m.group(1)) >= open_[1]:
                if open_[2] == "outcome":
                    blocks.append((open_[3], pos + len(line),
                                   text[open_[4]:pos]))
                open_ = None
        pos += len(line)
    return blocks, ((open_[2], open_[3]) if open_ is not None else None)


def _result_values(body: str) -> list[str]:
    """Every `result:` value the block's own lines give (not list items)."""
    out = []
    for raw in body.splitlines():
        if _ITEM.match(raw):
            continue
        kv = _KEY.match(raw)
        if kv and kv.group(1).strip().lower().replace(" ", "_") == "result":
            out.append(kv.group(2).split("#", 1)[0].strip())
    return out


#: An ```outcome / ~~~outcome fence line anywhere, quoted or indented: used
#: only to explain why a reply that mentions one makes no claim.
_ANY_OUTCOME_FENCE = re.compile(r"^[ \t>]*(`{3,}|~{3,})[ \t]*outcome\b", re.M | re.I)

#: Why a reply that tried to claim makes no claim (`inspect`), by kind.
UNCLAIMED_WHY = {
    "unterminated": "its outcome block is never closed (no closing fence "
                    "line), so it is not a claim",
    "not-last": "its outcome block is followed by more text; only a block "
                "that ends the reply is a claim",
    "no-result": "its outcome block names no result; a claim says met, "
                 "partly or not-met",
    "bad-result": "its outcome block's result is not met, partly or not-met",
    "two-results": "its outcome block names more than one result",
    "quoted-only": "its only outcome block is inside another code block or "
                   "a quote, where it is text, not a claim",
}


def inspect(text: str | None) -> dict:
    """`{claim, text, unclaimed}` for a reply.

    `claim` and `text` are what `extract` returns. `unclaimed` is None when
    the reply makes a valid claim or never tries to; otherwise
    `{kind, why}` (`UNCLAIMED_WHY`) says why what looks like an outcome
    block is not one. Nothing is repaired: a malformed block is never read
    as a claim, and the reply's text is returned as it was written."""
    text = text or ""
    blocks, dangling = _scan(text)

    def no(kind, detail=None):
        why = UNCLAIMED_WHY[kind] + (f" ({detail})" if detail else "")
        return {"claim": None, "text": text,
                "unclaimed": {"kind": kind, "why": why}}

    if dangling is not None and dangling[0] == "outcome":
        return no("unterminated")
    if not blocks:
        if dangling is not None and _ANY_OUTCOME_FENCE.search(text, dangling[1]):
            # an outcome fence inside a code block that is itself never
            # closed: neither is a claim, and the reply ends unterminated
            return no("unterminated")
        if _ANY_OUTCOME_FENCE.search(text):
            return no("quoted-only")
        return {"claim": None, "text": text, "unclaimed": None}
    start, end, body = blocks[-1]
    if text[end:].strip():
        return no("not-last")
    values = _result_values(body)
    known = {normalize_result(v) for v in values}
    if not values or not any(values):
        return no("no-result")
    if None in known:
        bad = next(v for v in values if normalize_result(v) is None)
        return no("bad-result", f"got {one_line(bad, 40)!r}")
    if len(known) > 1:
        return no("two-results", ", ".join(sorted(known)))
    claim = normalize(_parse_body(body))
    if claim is None:                                # pragma: no cover
        return no("no-result")
    return {"claim": claim, "text": text[:start].strip(), "unclaimed": None}


def extract(text: str | None) -> tuple[dict | None, str]:
    """(the claim, the text without its block).

    ONLY A BLOCK THAT ENDS THE REPLY IS A CLAIM: a top-level ```outcome
    fence with nothing but whitespace after it. One mid-reply, one inside
    another fence (an example, a quoted earlier reply) or inside a quote is
    text, and is never taken out. A block naming no result this understands,
    or naming two different ones, is not a claim either, and neither is a
    block that is never closed. `inspect` says why."""
    got = inspect(text)
    return got["claim"], got["text"]


#: Said after every rendered claim: the line is the agent's words, and what
#: Mentis recorded of them is read from the record, never from this text.
RENDER_NOTE = "(the agent's claim; what Mentis recorded is shown with the work)"


def render(claim: dict, who: str | None = None) -> str:
    """The one line a reply shows instead of the block: ATTRIBUTED as the
    agent's claim, its words escaped and clipped to one line, so the reply
    text cannot pass for Mentis's reconciliation."""
    word = _RESULT_WORDS.get(claim["result"], claim["result"])
    line = (f"Claim by {_md(who or 'the agent', 60)}: {word}"
            + (f" — {_md(claim['summary'], 300)}" if claim.get("summary")
               else ""))
    ev = claim.get("evidence") or []
    if ev:
        shown = "; ".join(_md(e, 120) for e in ev[:5]) + (
            f" (+{len(ev) - 5} more)" if len(ev) > 5 else "")
        line += f" · evidence: {shown}"
    return line + " " + RENDER_NOTE


def with_rendering(text: str, claim: dict, who: str | None = None) -> str:
    """The reply text with the block's one-line rendering added."""
    line = render(claim, who)
    return (text.rstrip() + "\n\n" + line) if text.strip() else line


#: What the CALLER of a claim (respond's own arguments, record_outcome) may
#: say beside it, which reconciliation reads. Never taken from a block.
TRUSTED = ("because", "result_kind", "results")


def continuation(cv, expectation, *, owner_wait=None):
    """What the record says can continue this request, without reading prose."""
    waiting = cv.waiting_on(expectation)
    sources = [{"kind": "child", "ref": c["expectation"]}
               for c in waiting["required"] if c["state"] in ("running", "not-ended")]
    sources += [{"kind": "work", "ref": w["expectation"]}
                for w in waiting["awaited"] if not w["ended"]]
    sources += [{"kind": "decision", "ref": d["expectation"]}
                for d in waiting["decisions"] if not d["answered"]]
    sources += [{"kind": "input", "ref": i["expectation"]}
                for i in waiting["inputs"] if not i["answered"]]
    handed = {r["report"]["id"] for a in cv._own_acts(expectation)
              if a["act"] == "work-resumed"
              for r in (a.get("detail") or {}).get("detached_reports", [])}
    sources += [{"kind": "detached", "ref": d["operation"]}
                for d in waiting.get("detached", [])
                if not d["report"] or d["report"]["id"] not in handed]
    if owner_wait:
        sources.append({"kind": "owner-wait", "action": owner_wait,
                        "automatic": False})
    return {"recorded": bool(sources), "sources": sources}


NO_CONTINUATION = ("stopped: nothing will resume it. Record delegate with "
                   "resume_on_return, await_work, request_decision/request_input, "
                   "or arm_detached; or name the future owner's action in owner_wait. "
                   "A promise in prose does not schedule a check.")


def claim(cv, expectation, outcome: dict, *, actor, execution=None,
          runtime=None, via, reply_turn=None, conversation=None,
          participant=None, trusted=None) -> str:
    """Write `outcome-claimed` about `expectation`. Returns the act id.
    `trusted` holds only `TRUSTED` keys, from the operation's own checked
    arguments; the claim's unknown keys stay under `detail.extra`."""
    outcome = normalize(outcome)
    exp = cv._act(expectation) or {}
    approval = None
    if outcome.get("approval"):
        # The ordinary decision-form path, on the exact result post. No new
        # approval lifecycle or governance is established by a claim.
        from mentis.worker import _decision_form
        named = outcome["approval"]["artifacts"]
        question = (outcome["approval"].get("question") or "Approve this work?")
        question += "\nArtifacts: " + ", ".join(named)
        if reply_turn:
            question += "\nResult post: " + reply_turn
        approval = _decision_form(
            cv, {"question": question, "on": reply_turn,
                 "options": [{"label": "Approve", "consequence": "continue this request with the named work"},
                             {"label": "Revise", "consequence": "revise this work before proceeding"}]},
            actor=actor, parent=expectation,
            here=conversation or exp.get("conversation"), wrote=None,
            act=lambda kind, **kw: cv.record_act(
                actor=actor, act=kind, caused_by=expectation,
                execution=execution, runtime=runtime, **kw),
            where=lambda cid: cid, execution=execution,
            form_detail={"approval_artifacts": named, "approval_request": expectation})
    continues = continuation(cv, expectation, owner_wait=outcome.get("owner_wait"))
    detail = {"result": outcome["result"],
              **({"continuation": continues, "no_continuation": not continues["recorded"]}
                 if outcome["result"] == "partly" else {}),
              **({"owner_wait": outcome["owner_wait"]} if outcome.get("owner_wait") else {}),
              **({"approval": approval["form"]} if approval else {}),
              "summary": one_line(outcome.get("summary"), 1000),
              "evidence": list(outcome.get("evidence") or ()),
              **({"extra": dict(outcome["extra"])}
                 if isinstance(outcome.get("extra"), dict) else {}),
              **{k: v for k, v in (trusted or {}).items()
                 if k in TRUSTED and v},
              "claimed_by": execution, "runtime": runtime,
              "participant": participant or actor, "via": via,
              "reply_turn": reply_turn}
    return cv.record_act(
        actor=actor, act=OUTCOME_CLAIMED,
        conversation=conversation or exp.get("conversation"),
        turn=reply_turn, execution=execution, runtime=runtime,
        caused_by=expectation, about=[expectation],
        because=one_line(outcome.get("summary")
                         or f"claimed {outcome['result']}", 400),
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


def _claimants(cv, expectation, own=None) -> tuple[set, set]:
    """(participants, executions) that claimed this work, or marked it met:
    a verdict by any of them verifies nothing about it."""
    own = own if own is not None else cv._own_acts(expectation)
    who, runs = set(), set()
    for a in own:
        if a["act"] == OUTCOME_CLAIMED and a.get("caused_by") == expectation:
            d = a.get("detail") or {}
            who |= {x for x in (a.get("actor"), d.get("participant")) if x}
            runs |= {x for x in (a.get("execution"), d.get("claimed_by")) if x}
        elif a["act"] == EXPECTATION_MET:
            if a.get("actor"):
                who.add(a["actor"])
            if a.get("execution"):
                runs.add(a["execution"])
    return who, runs


def verdict_index(cv, memo=None) -> dict:
    """`{work expectation: [review-verdict acts that may verify it]}`, built
    ONCE per read (in `memo`, else for the `reading()` scope): one read of
    the verdicts, and for each, the request it was recorded on. A verdict
    may verify only work its request REVIEWS: that request must be review
    work (`is_review_work`), and the work is the one it was delegated under
    or the one it declares `review_of`. A verdict on anything else -- an
    implementer's own request, the claimant's own work -- verifies nothing.
    """
    if memo is not None and "_wsc_verdicts" in memo:
        return memo["_wsc_verdicts"]

    def build():
        idx = {}
        for v in cv.history(act=REVIEW_VERDICT):
            r = (v.get("about") or [None])[0] or v.get("caused_by")
            ra = cv._act(r) if r else None
            if not ra or ra["act"] != "expectation-recorded":
                continue
            if not is_review_work(cv, r):
                continue
            targets = {_enclosing_work(cv, r)}
            repo = (ra.get("detail") or {}).get("repository")
            if isinstance(repo, dict) and isinstance(repo.get("review_of"),
                                                     str):
                targets.add(repo["review_of"])
            for t in targets - {None, r}:
                idx.setdefault(t, []).append(v)
        return idx
    got = (cv._recall(("wsc-verdict-index",), build)
           if hasattr(cv, "_recall") else build())
    if memo is not None:
        memo["_wsc_verdicts"] = got
    return got


def review_passed(cv, expectation, *, memo=None, own=None) -> dict | None:
    """The newest verdict that may verify this work (`verdict_index`), by a
    participant other than its claimants and from none of their runs, when
    that verdict is `pass`; else None."""
    candidates = verdict_index(cv, memo).get(expectation) or []
    if not candidates:
        return None
    who, runs = _claimants(cv, expectation, own)
    valid = [v for v in candidates if v.get("actor") not in who
             and not (v.get("execution") and v["execution"] in runs)]
    if not valid:
        return None
    seq = cv._write_order([a["id"] for a in valid])
    newest = max(valid, key=lambda a: seq.get(a["id"], -1))
    verdict = str((newest.get("detail") or {}).get("verdict") or "").lower()
    return newest if verdict == "pass" else None


def _rules(cv, expectation, claim_act) -> tuple[list[str], list[str]]:
    """(reasons that keep a claim of met pending, notes that do not)."""
    reasons, notes = [], []
    own = cv._own_acts(expectation)
    seq = cv._write_order([a["id"] for a in own] + [claim_act["id"]])
    at = seq.get(claim_act["id"], -1)
    # 1. the claimant's own run ended normally -- not still going, not
    #    failed or cancelled -- and no run of this work started after the
    #    claim: a later run makes its own claim, whatever it did.
    starts = [a for a in own if a["act"] == STARTED]
    if any(seq.get(a["id"], -1) > at for a in starts):
        reasons.append("a later run started after the claim; it must make "
                       "its own claim")
    mine = [a for a in starts if claim_act.get("execution")
            and a.get("execution") == claim_act.get("execution")
            and seq.get(a["id"], -1) < at]
    if mine:
        run = max(mine, key=lambda a: seq.get(a["id"], -1))
        end = cv.run_end(run["id"])
        refused = refused_in(end)
        if end is None:
            reasons.append("its run has not ended yet")
        elif end["act"] == FAILED:
            cancelled = "terminal 'cancelled'" in (end.get("because") or "")
            # A RUN THAT ENDED ON A PERMISSION REFUSAL never makes its earlier
            # claim met: what was refused is named, so it is not mistaken for
            # finished work.
            if cancelled:
                reasons.append("its run was cancelled after the claim")
            elif refused:
                reasons.append("its run ended on a permission refusal after "
                               "the claim: " + ", ".join(refused))
            else:
                reasons.append("its run failed after the claim")
        elif refused:
            # A REFUSAL THE RUN WENT ON FROM (a pre-turn runtime handed it back
            # to the model, which carried on with its other tools). The work and
            # the claim stand, but a claim of met after a refusal is never
            # recorded met on the agent's word alone -- measured live, a model
            # refused its listing claimed met with a wrong one -- so it waits for
            # an independent review pass (`on_review_pass` reconciles it then).
            if review_passed(cv, expectation, own=own):
                notes.append("the runtime refused during its run: "
                             + ", ".join(refused))
            else:
                reasons.append("the runtime refused during its run: "
                               + ", ".join(refused)
                               + "; an independent review must pass first")
    # 1b. an owner follow-up handed to this work that the claimant's run
    #    was never given (`follow_ups_unseen`): recorded met, nothing would
    #    ever deliver it, so it holds the claim until a run is given it
    if claim_act.get("execution"):
        unseen = cv.follow_ups_unseen(expectation, claim_act["execution"])
        if unseen:
            reasons.append("an owner follow-up arrived after this run "
                           "began: " + ", ".join(unseen))
    # 2. no decision or input it asked for is open
    waiting = cv.waiting_on(expectation)
    handed_reports = {r["report"]["id"] for a in own if a["act"] == "work-resumed"
                      for r in (a.get("detail") or {}).get("detached_reports", [])}
    for operation in waiting.get("detached", []):
        if not operation["report"]:
            reasons.append(f"detached operation {operation['operation']} has no report yet")
        elif operation["report"]["id"] not in handed_reports:
            # A person may explicitly continue the request after Stop or a
            # lost dispatch. Its NEW run can reconcile the durable report.
            report_order = cv._write_order([operation["report"]["id"],
                                           *[a["id"] for a in mine]])
            started_after = any(report_order.get(a["id"], -1) >
                                report_order[operation["report"]["id"]] for a in mine)
            if not started_after:
                reasons.append(f"detached report {operation['report']['id']} has not been handed to its carrier")
    for d in waiting["decisions"]:
        if not d["answered"]:
            reasons.append(f"decision {d['expectation']} is open")
    for i in waiting["inputs"]:
        if not i["answered"]:
            reasons.append(f"input {i['expectation']} is awaited")
    # 3. no child it declared it waits on is unended, and no work it
    #    delegated is still running at all; children that ended unmet are
    #    listed, and block nothing by themselves
    declared, halted_children = set(), []
    for c in waiting["required"]:
        declared.add(c["expectation"])
        if c["state"] in ("running", "not-ended"):
            reasons.append(f"child {c['expectation']} has not ended")
        elif c["state"] == "interrupted":
            halted_children.append(c["expectation"])
    for w in waiting["awaited"]:
        if not w.get("ended"):
            reasons.append(f"awaited work {w['expectation']} has not ended")
    running = []
    for a in cv._children(expectation):
        if a["act"] != "work-delegated" or not a.get("about"):
            continue
        child = a["about"][0]
        try:
            s = cv._child_state(child)
        except Exception:                                 # noqa: BLE001
            continue
        if s["state"] in ("running", "not-ended"):
            if child not in declared:
                running.append(child)
        elif s["state"] == "interrupted":
            # HALTED FOR A CONSENT CHANGE AND NOT RESTARTED: its work did
            # not end, so it holds the claim as unfinished work does
            halted_children.append(child)
        elif not s["claimed_met_by"]:
            notes.append(f"child {child} not met")
    if running:
        reasons.append("delegated work still running: "
                       + ", ".join(dict.fromkeys(running)))
    if halted_children:
        reasons.append("delegated work stopped for a consent change and not "
                       "restarted: " + ", ".join(dict.fromkeys(halted_children)))
    # 4. review before completion, where its Workflow requires it
    if review_required(cv, expectation) and not review_passed(
            cv, expectation, own=own):
        reasons.append("review required")
    return reasons, notes


def refused_in(end) -> list[str]:
    """What the runtime's own rules refused in the run `end` ended, as its end
    act recorded MARS's report (`runtime_evidence.denied`): command `dir`,
    or the action alone when no command line was named. Bounded."""
    ev = ((end or {}).get("detail") or {}).get("runtime_evidence") or {}
    out = []
    for d in (ev.get("denied") if isinstance(ev, dict) else None) or ():
        if not isinstance(d, dict) or not d.get("action"):
            continue
        words = str(d["action"])[:40]
        if isinstance(d.get("command"), str) and d["command"].strip():
            words += f" `{one_line(d['command'], 120)}`"
        if words not in out:
            out.append(words)
    return out[:10]


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
        stopped = result == "partly" and d.get("no_continuation", False)
        return {"recorded": result, "reasons": [],
                "notes": [NO_CONTINUATION] if stopped else [], "act": None,
                **({"no_continuation": stopped, "continuation": d.get("continuation")}
                   if result == "partly" else {})}
    # CHECK AND WRITE AS ONE, under the write lock: two reconciliations of
    # the same claim at once write one answer, never two.
    with cv.corpus.atomic():
        return _reconcile_met(cv, expectation, c, d)


def _reconcile_met(cv, expectation, c, d) -> dict:
    own = cv._own_acts(expectation)
    done = [a for a in own if a["act"] == EXPECTATION_MET
            and (a.get("detail") or {}).get("reconciled_from") == c["id"]]
    if done:
        return {"recorded": "met", "reasons": [], "notes": [],
                "act": done[0]["id"], "already": True}
    if any(a["act"] == EXPECTATION_MET for a in own):
        # met by another path already: the claim stands beside it
        return {"recorded": "met", "reasons": [], "notes": [], "act": None,
                "already": True}
    reasons, notes = _rules(cv, expectation, c)
    if not reasons:
        reply = d.get("reply_turn")
        # ONLY WHAT THE OPERATION ITSELF SAID (`TRUSTED`): never a block's
        # keys, which live under `detail.extra`
        results = [str(r) for r in (d.get("results") or ()) if r]
        met = cv.record_act(
            actor=c["actor"], act=EXPECTATION_MET,
            conversation=c.get("conversation"), turn=reply,
            execution=c.get("execution"), runtime=c.get("runtime"),
            caused_by=expectation,
            about=[x for x in [reply, *results] if x] or [c["id"]],
            because=one_line(d.get("because") or d.get("summary")
                             or "claimed met and reconciled", 400),
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
    """A `review-verdict pass` was recorded on `reviewer_expectation`. If
    that request is review work, reconcile the pending claim of the work it
    reviews: the work it was delegated under, or the one it declares
    `review_of`. Whether the verdict counts is `review_passed`'s to say."""
    if not reviewer_expectation or not is_review_work(cv, reviewer_expectation):
        return []
    targets = [_enclosing_work(cv, reviewer_expectation)]
    d = ((cv._act(reviewer_expectation) or {}).get("detail") or {})
    repo = d.get("repository")
    if isinstance(repo, dict) and isinstance(repo.get("review_of"), str):
        targets.append(repo["review_of"])
    out = []
    for t in dict.fromkeys(x for x in targets if x):
        got = reconcile_if_pending(cv, t)
        if got is not None:
            out.append(got)
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
    elif any(a["act"] == EXPECTATION_MET
             and (a.get("detail") or {}).get("reconciled_from") == c["id"]
             for a in own):
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
            **({"continuation": continuation(cv, expectation, owner_wait=d.get("owner_wait")),
                "no_continuation_at_claim": d.get("no_continuation")}
               if d.get("result") == "partly" else {}),
            "summary": one_line(d.get("summary"), 1000),
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


def _regards_defined(cv) -> bool:
    try:
        return cv.corpus.current_definition(REGARDS) is not None
    except Exception:                                     # noqa: BLE001
        return False


def _targets(exp_act, claims) -> set:
    """What a later record about this work may name: the expectation, its
    Turn, each claim about it and each claim's reply Turn."""
    out = {exp_act["id"]}
    if exp_act.get("turn"):
        out.add(exp_act["turn"])
    for a in claims:
        out.add(a["id"])
        reply = (a.get("detail") or {}).get("reply_turn")
        if reply:
            out.add(reply)
    return out


def prefetch_regards(cv, exp_acts) -> dict:
    """`{expectation: [regards links]}` for many pieces of work in TWO
    reads, whatever their number: every claim, then every `regards` link to
    any of their targets. For the work views, which list many items."""
    exp_acts = [a for a in exp_acts if a]
    if not exp_acts or not _regards_defined(cv):
        return {a["id"]: [] for a in exp_acts}
    ids = {a["id"] for a in exp_acts}
    claims = {}
    for c in cv.history(act=OUTCOME_CLAIMED):
        if c.get("caused_by") in ids:
            claims.setdefault(c["caused_by"], []).append(c)
    owner, every = {}, set()
    for a in exp_acts:
        for t in _targets(a, claims.get(a["id"], ())):
            owner.setdefault(t, set()).add(a["id"])
            every.add(t)
    out = {a["id"]: [] for a in exp_acts}
    for link in cv.corpus.links(relation=REGARDS, to_any=sorted(every)):
        for e in owner.get((link.get("link") or {}).get("to"), ()):
            out[e].append(link)
    return out


def later_findings(cv, expectation, *, own=None, links=None) -> list[dict]:
    """`[{id, kind, at}]`: records linked `regards` to this expectation, to
    a claim about it, or to its own Turn or a claim's reply Turn. `links`,
    when given, is this work's entry of `prefetch_regards`."""
    if links is None:
        if not _regards_defined(cv):
            return []
        exp = cv._act(expectation) or {"id": expectation}
        own = own if own is not None else cv._children(expectation)
        claims = [a for a in own if a["act"] == OUTCOME_CLAIMED]
        links = cv.corpus.links(relation=REGARDS,
                                to_any=sorted(_targets(exp, claims)))
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
