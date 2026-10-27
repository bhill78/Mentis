"""What will not render in an agent's Markdown, said to the agent, never refused.

THE UI'S OWN READERS, NOT A COPY. The rules a marked block is held to live in
`ui/src/experimental/spec/` (TypeScript), which the UI draws from. The UI build
bundles them into `apps/fluid-web/dist/render-check.js` (`apps/fluid-web/render-check.mjs`), so a
release carries the readers its own UI runs. This module runs that file in
QuickJS-NG (`quickjs-ng`), an embedded JavaScript engine pinned in
`requirements.txt` as a binary wheel like `regex` -- no Node, nothing
installed beside Mentis. The release's dist is read from disk, as the server
reads it for the UI.

ACCEPT, DON'T REFUSE (owner decision, Conversation "Markdown Renderer
Maturation"). Nothing here can stop a post. `check` never raises: when the
engine, the bundle or the time limit fails, or the engine hands back anything
but a well-formed report, it says so in `why_not` and the caller posts anyway
and passes that on, so a failed check is reported rather than mistaken for a
clean one.

NOT CHECKED ON INTEL macOS, BY DECISION (owner, option B). quickjs-ng
publishes no wheel for Intel macOS (macosx x86_64), only an sdist that needs
a C compiler. So `requirements.txt` leaves it out there with an environment
marker, the install succeeds without a compiler, and every check there is
`checked: false` with a `why_not` saying the engine is not installed and that
this is expected on that platform. Posting, and the rest of Mentis, work as
everywhere else. On every platform with a wheel (Windows, Apple Silicon
macOS, Linux x86_64 and aarch64) the engine is required and checks run.

    report = check(text)        # {"checked": True, "errors": 1, "problems": [...]}
    report = check_parts(parts) # the text parts of a Turn, each as the UI scopes it
    report = of_turn(corpus, t) # a written Turn, read back, with a `note` to act on
    words = owed(cv, p, c, run) # a reply written at exit, said to p's next run in c
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import platform
import os
import sys
import threading

#: The Fluid build this server serves (`apps/fluid-web`, `npm run build`), or
#: MENTIS_FLUID_DIST. A headless server with no interface built can still have
#: the bundle alone: `node apps/fluid-web/render-check.mjs <dist>/render-check.js`.
DIST = pathlib.Path(os.environ.get("MENTIS_FLUID_DIST") or
                    pathlib.Path(__file__).resolve().parents[2] / "apps" / "fluid-web" / "dist")
#: The bundle the UI build writes, in the dist this server serves.
BUNDLE = DIST / "render-check.js"
BUILD_FILE = "build-identity.json"
#: Generous for a Turn (a large one checks in well under 10 ms); a bound, not a budget.
TIME_LIMIT_S = 2.0
MEMORY_LIMIT = 64 * 1024 * 1024
#: Longer text is not checked for rendering, and says so; it is still posted.
#: Answers are checked whatever the post's length (`answers`).
MAX_CHARS = 400_000

_lock = threading.Lock()
_engine: dict = {}


def _load(path: pathlib.Path):
    """The compiled checker for the bundle at `path`, reused while it is unchanged."""
    import quickjs  # the embedded engine; absent means "not checked", never a refusal
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if _engine.get("digest") == digest and _engine.get("path") == str(path):
        return _engine
    fn = quickjs.Function(
        "mentisCheck",
        raw.decode("utf-8") + "\nfunction mentisCheck(text) {"
        " return JSON.stringify(MentisRenderCheck.checkRendering(text)) }")
    fn.set_time_limit(TIME_LIMIT_S)
    fn.set_memory_limit(MEMORY_LIMIT)
    built = None
    try:
        built = json.loads((path.parent / BUILD_FILE).read_text("utf-8"))
    except Exception:                                     # noqa: BLE001
        pass
    _engine.clear()
    _engine.update(fn=fn, digest=digest, path=str(path), renderer={
        "bundle": str(path), "sha256": digest[:16],
        "built_from": (built or {}).get("commit"),
        "built_dirty": (built or {}).get("dirty")})
    return _engine


def check(text, *, bundle: pathlib.Path | None = None) -> dict:
    """The diagnostics for one Markdown text. Never raises.

    `checked` False means nothing was checked and `why_not` says why; it never
    means the text is fine.
    """
    path = pathlib.Path(bundle) if bundle else BUNDLE
    text = text if isinstance(text, str) else ("" if text is None else str(text))
    if len(text) > MAX_CHARS:
        return {"checked": False,
                "why_not": f"the text is {len(text)} characters; the check reads at most {MAX_CHARS}"}
    try:
        with _lock:
            eng = _load(path)
            got = json.loads(eng["fn"](text))
            renderer = dict(eng["renderer"])
        wrong = malformed(got)
        if wrong:
            return {"checked": False,
                    "why_not": f"the render check returned a malformed report ({wrong})"[:600]}
        got = {k: v for k, v in got.items() if k != "types"}
    except ModuleNotFoundError as exc:
        return {"checked": False, "why_not": _no_engine(exc)}
    except FileNotFoundError:
        return {"checked": False,
                "why_not": f"the render check is not built: {path} is missing (it is written by the UI build)"}
    except Exception as exc:                              # noqa: BLE001
        # A compiled function that failed (a time or memory limit, an engine
        # fault) is not reused: the next check compiles afresh.
        with _lock:
            _engine.clear()
        return {"checked": False,
                "why_not": f"the render check failed: {type(exc).__name__}: {exc}"[:600]}
    return {"checked": True, **got, "renderer": renderer}


_answers_engine: dict = {}


def _load_answers(path: pathlib.Path):
    """The compiled fill-rule checker for the bundle at `path` (forms build, P1)."""
    import quickjs  # absent means "not checked here", never a refusal
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if _answers_engine.get("digest") == digest and _answers_engine.get("path") == str(path):
        return _answers_engine
    fn = quickjs.Function(
        "mentisAnswers",
        raw.decode("utf-8") + "\nfunction mentisAnswers(args) {"
        " if (typeof MentisRenderCheck.checkAnswers !== 'function')"
        "   throw new Error('this bundle has no checkAnswers: rebuild the UI');"
        " var a = JSON.parse(args);"
        " if (a.block) {"
        "   if (typeof MentisRenderCheck.fillOf !== 'function')"
        "     throw new Error('this bundle has no fillOf: rebuild the UI');"
        "   return JSON.stringify(MentisRenderCheck.fillOf(a.block)) }"
        " return JSON.stringify(MentisRenderCheck.checkAnswers(a.text, a.name, a.values)) }")
    fn.set_time_limit(TIME_LIMIT_S)
    fn.set_memory_limit(MEMORY_LIMIT)
    _answers_engine.clear()
    _answers_engine.update(fn=fn, digest=digest, path=str(path),
                           renderer={"bundle": str(path), "sha256": digest[:16]})
    return _answers_engine


def answers(text, name, values, *, bundle: pathlib.Path | None = None) -> dict:
    """The UI's fill rules applied to `values` for the block `name` in `text`
    (one Turn part). Never raises.

    THE SAME RULES AS THE CONTROLS. `checkAnswers` in
    `ui/src/experimental/spec/fill.ts` is what the form the owner fills in
    runs; this runs that function from the same bundle. `checked` False means
    nothing was checked (no engine, no bundle, a failure) and `why_not` says
    why; it never means the values are fine.

    ONLY AN ABSENT ENGINE IS `engine_absent` (owner choice R5: such an answer
    is recorded, marked 'not checked here'). Every other `checked` False -- no
    bundle, a bundle older than `checkAnswers`, a time or memory limit, a
    malformed result -- is a check that should have run and did not, and a
    writer refuses on it (`responses._refuse_unsaveable`). NO LENGTH LIMIT:
    unlike `check`, which never stops a post, a post too long to check would
    be a way to record answers nobody checked, so a long post is checked like
    any other and only the time and memory limits bound it."""
    path = pathlib.Path(bundle) if bundle else BUNDLE
    text = text if isinstance(text, str) else ("" if text is None else str(text))
    try:
        payload = json.dumps({"text": text, "name": str(name), "values": dict(values or {})})
        with _lock:
            eng = _load_answers(path)
            got = json.loads(eng["fn"](payload))
            renderer = dict(eng["renderer"])
        if not isinstance(got, dict) or not isinstance(got.get("found"), bool) \
                or not isinstance(got.get("fields"), list):
            return {"checked": False, "why_not": "the fill check returned a malformed result"}
    except ModuleNotFoundError as exc:
        return {"checked": False, "engine_absent": True, "why_not": (
            "the render engine (quickjs-ng) is not installed, so these values "
            "were not checked here"
            + ("; that is expected on Intel macOS, where requirements.txt "
               "leaves it out" if intel_mac() else
               f" ({exc}); requirements.txt pins it for this platform, so the "
               "install is incomplete"))}
    except FileNotFoundError:
        return {"checked": False,
                "why_not": f"the fill check is not built: {path} is missing (it is written by the UI build)"}
    except Exception as exc:                              # noqa: BLE001
        with _lock:
            _answers_engine.clear()
        if "has no checkAnswers" in str(exc):
            return {"checked": False, "stale_bundle": True, "why_not": (
                f"the fill check bundle {path} is older than this server: it "
                "has no checkAnswers. The UI must be rebuilt (npm run build in "
                "ui/) before answers can be checked")}
        return {"checked": False,
                "why_not": f"the fill check failed: {type(exc).__name__}: {exc}"[:600]}
    return {"checked": True, **got, "renderer": renderer}


def fill_of(block, *, bundle: pathlib.Path | None = None) -> dict:
    """Whether one block -- `{type, info, body, closed}`, as a post's objects
    give it -- takes anything filled in, and its fields, read by `fillOf` in
    `ui/src/experimental/spec/fill.ts`: the same block reader the fill rules
    use, named or not. Never raises; `checked` False says why not."""
    path = pathlib.Path(bundle) if bundle else BUNDLE
    try:
        b = dict(block or {})
        payload = json.dumps({"block": {
            "type": str(b.get("type") or ""), "info": str(b.get("info") or ""),
            "body": str(b.get("body") or ""), "closed": b.get("closed", True)
            is not False}})
        with _lock:
            eng = _load_answers(path)
            got = json.loads(eng["fn"](payload))
        if not isinstance(got, dict) or not isinstance(got.get("fillable"), bool) \
                or not isinstance(got.get("fields"), list):
            return {"checked": False, "why_not": "the fill reader returned a malformed result"}
    except ModuleNotFoundError as exc:
        return {"checked": False, "engine_absent": True,
                "why_not": f"the render engine (quickjs-ng) is not installed ({exc})"}
    except FileNotFoundError:
        return {"checked": False,
                "why_not": f"the fill check is not built: {path} is missing (it is written by the UI build)"}
    except Exception as exc:                              # noqa: BLE001
        with _lock:
            _answers_engine.clear()
        return {"checked": False,
                "why_not": f"the fill reader failed: {type(exc).__name__}: {exc}"[:600]}
    return {"checked": True, **got}


def intel_mac() -> bool:
    """The one platform `requirements.txt` leaves the engine out on."""
    return sys.platform == "darwin" and platform.machine() == "x86_64"


def _no_engine(exc) -> str:
    if intel_mac():
        return ("the render engine (quickjs-ng) is not installed, so this "
                "Markdown was not checked. That is expected on Intel macOS: "
                "quickjs-ng has no wheel for it, so requirements.txt leaves it "
                "out there (a documented degradation, not an install failure). "
                "The post is unaffected")
    return ("the render engine (quickjs-ng) is not installed, so this Markdown "
            f"was not checked ({exc}). requirements.txt pins it for this "
            "platform, so the install is incomplete: install it with "
            "`pip install -r requirements.txt`. The post is unaffected")


#: What every problem in a report must carry, and of what type.
_PROBLEM = {"block": str, "line": int, "severity": str, "where": str, "message": str}


def malformed(report) -> str | None:
    """What makes `report` not a well-formed checked report, or None.

    A report is what everything here reads it as: counts that are integers,
    and problems each saying where they are and what is wrong."""
    if not isinstance(report, dict):
        return f"a {type(report).__name__}, not an object"
    for k in ("blocks", "errors", "warnings"):
        if type(report.get(k)) is not int:
            return f"{k} is {report.get(k)!r}, not an integer"
    problems = report.get("problems")
    if not isinstance(problems, list):
        return f"problems is {type(problems).__name__}, not a list"
    for n, p in enumerate(problems):
        if not isinstance(p, dict):
            return f"problem {n} is a {type(p).__name__}, not an object"
        for k, kind in _PROBLEM.items():
            if type(p.get(k)) is not kind:
                return f"problem {n} has no {kind.__name__} {k}"
        if not (p.get("type") is None or isinstance(p.get("type"), str)):
            return f"problem {n} has a type that is not text"
        if not (p.get("fix") is None or isinstance(p.get("fix"), str)):
            return f"problem {n} has a fix that is not text"
        if "part" in p and type(p["part"]) is not int:
            return f"problem {n} has a part that is not an integer"
    return None


def check_parts(parts, *, bundle: pathlib.Path | None = None) -> dict | None:
    """The diagnostics for a Turn's text parts; None when it has no text.

    The UI reads each text part on its own (its blocks are scoped by part), so
    each is checked on its own and, where a Turn has several, problems say
    which part (0-based, as `parts` is) they are in.
    """
    texts = [(i, p.get("text")) for i, p in enumerate(parts or ())
             if isinstance(p, dict) and p.get("type") == "text"
             and isinstance(p.get("text"), str)]
    if not texts:
        return None
    if len(texts) == 1:
        return check(texts[0][1], bundle=bundle)
    out = {"checked": True, "blocks": 0, "errors": 0, "warnings": 0, "problems": []}
    for i, t in texts:
        got = check(t, bundle=bundle)
        if not got["checked"]:
            return got
        out["renderer"] = got["renderer"]
        for k in ("blocks", "errors", "warnings"):
            out[k] += got[k]
        out["problems"] += [{"part": i, **p} for p in got["problems"]]
        out.setdefault("about", []).extend(
            {"part": i, **a} for a in got.get("about") or [])
    return out


def about_unresolved(report, corpus):
    """The report, with a WARNING for each timer about= id the record does
    not hold as a Topic, Conversation or post (R6). The UI's reader can only
    say an id is malformed (an error); whether the record holds it is known
    here. Such an id is shown as unresolved, never dropped. Never raises."""
    if not isinstance(report, dict) or not report.get("checked")             or not report.get("about") or corpus is None:
        return report
    try:
        from .timers import _about_one
        extra = []
        for a in report["about"]:
            for ref in a.get("ids") or []:
                one = _about_one(corpus, ref)
                if one["resolved"]:
                    continue
                extra.append({
                    "block": a["block"], "type": "timer", "line": a["line"],
                    "where": "about", "severity": "warning",
                    "message": f"about= names {ref}, but {one['why']}: it is "
                               "shown as unresolved, and no time spent is "
                               "added up for it.",
                    "fix": f"Replace {ref} with the id of an existing Topic, "
                           "Conversation or post, found with the tools.",
                    "from": "check",
                    **({"part": a["part"]} if "part" in a else {})})
    except Exception:                                     # noqa: BLE001
        return report
    if not extra:
        return report
    return {**report, "warnings": report["warnings"] + len(extra),
            "problems": report["problems"] + extra}


def said(report: dict | None, *, posted: bool = True) -> str | None:
    """One plain paragraph for an agent: what was delivered and what to change.
    Never raises: a report that is not well formed (one read back off the
    record, say) is said as not checked.

    `posted` False is the dry run, where nothing was delivered."""
    if not report:
        return None
    lead = "Posted as written. " if posted else ""
    if not isinstance(report, dict):
        report = {"checked": False, "why_not": f"its check is a {type(report).__name__}"}
    elif report.get("checked") and malformed(report):
        report = {"checked": False,
                  "why_not": f"its check is malformed ({malformed(report)})"}
    if not report.get("checked"):
        return (lead + "Its Markdown was NOT checked for rendering: "
                + str(report.get("why_not") or "no reason was given"))
    if not report["problems"]:
        return None
    lines = [lead + f"{report['errors']} error(s) and {report['warnings']} "
             f"warning(s) in its Markdown blocks: a block with an error is shown "
             f"as readable source instead of being drawn. "
             + ("Fix them in your next post, or check a draft first with "
                "check_rendering." if posted else "Fix them before posting.")]
    for p in report["problems"]:
        where = (f"part {p['part']}, " if "part" in p else "") + f"line {p['line']}"
        lines.append(f"- block {p['block']} ({p.get('type') or 'bare fence'}), {where}, "
                     f"{p['severity']} ({p['where']}): {p['message']}"
                     + (f" Fix: {p['fix']}" if p.get("fix") else ""))
    return "\n".join(lines)


def of_turn(corpus, turn: str) -> dict:
    """The check of a WRITTEN Turn, read back from the record, with a `note`
    saying what to change when there is anything to say. Never raises."""
    try:
        got = corpus.read([turn])
        parts = (got[0].get("body") or {}).get("parts") if got else None
    except Exception as exc:                                # noqa: BLE001
        report = {"checked": False,
                  "why_not": f"the Turn could not be read back: {type(exc).__name__}: {exc}"}
    else:
        try:
            report = about_unresolved(check_parts(parts) or {
                "checked": True, "blocks": 0, "errors": 0, "warnings": 0, "problems": []},
                corpus)
        except Exception as exc:                            # noqa: BLE001
            report = {"checked": False,
                      "why_not": f"the render check failed: {type(exc).__name__}: {exc}"[:600]}
    words = said(report)
    return {**report, **({"note": words} if words else {})}


def owed(cv, participant, conversation, started) -> str | None:
    """What a participant's EARLIER reply here will not render, for the run
    `started` is beginning, or None. Never raises.

    THE SCRATCH MECHANISM, FOR A CONVERSATION. When dispatch writes a reply at
    a run's exit, the run is gone, so the check goes on that run's
    `result-returned` act (`rendering`). Scratch says its last answer's check
    in the next answer's prompt; this says the last completion-path reply's
    check in the same participant's next run in the same Conversation. Nothing
    is started, woken or scheduled for it: it is read only by a run that was
    starting anyway.

    UNRESOLVED, AND ONCE, READ OFF THE RECORD -- nothing is written for it.
    The participant's latest `result-returned` here, if dispatch wrote its
    reply and that check found problems, is said when
      * that reply is still the participant's latest Turn in the Conversation
        (any later post of theirs supersedes it, checked clean or not: that
        post had its own check handed back by the tool that wrote it), and
      * no run of theirs here has started since that act, other than
        `started` (the run that started first after it was the one told).
    So it is said at most once. It can be said NONE: a run that started and
    failed before its prompt was composed, or two runs that started together,
    each counts as told. Under-telling is the direction to be wrong in.
    """
    try:
        acts = cv.history(actor=participant, conversation=conversation,
                          act=("result-returned", "execution-started"))
        order = cv._write_order(a["id"] for a in acts)
        acts.sort(key=lambda a: order.get(a["id"], -1))
        ends = [a for a in acts if a["act"] == "result-returned"]
        if not ends:
            return None
        last = ends[-1]
        detail = last.get("detail") or {}
        report = detail.get("rendering")
        if (detail.get("response_owner") != "dispatch-completion"
                or not isinstance(report, dict) or not report.get("checked")
                or malformed(report)
                or not report.get("problems") or not last.get("turn")):
            return None
        since = order.get(last["id"], -1)
        if any(a["act"] == "execution-started" and a["id"] != started
               and order.get(a["id"], -1) > since for a in acts):
            return None
        mine = [t for t in cv.turns(conversation)
                if t["entry"].get("attributed_to") == participant]
        if not mine or mine[-1]["turn"] != last["turn"]:
            return None
        words = said(report)
        number = cv.turn_number(last["turn"])
    except Exception:                                       # noqa: BLE001
        return None
    return ("YOUR LAST REPLY HERE WILL NOT RENDER AS WRITTEN. Mentis posted "
            f"Turn {last['turn']}" + (f" (#{number})" if number else "")
            + " from what your run printed at exit, then checked its Markdown; "
            "that run had ended, so it is said now, once. That Turn cannot be "
            "edited: if the fix matters, post again with it corrected.\n"
            + words)


# -- a choice written instead of asked (forms build P8) ------------------------

#: What the warning says, and what to do instead.
CHOICE_SAYS = ("a choice for the owner is written here as a {kind} of {n} "
               "options, and this run has raised no decision: nothing waits "
               "for the answer and the owner cannot answer it where it is "
               "asked")
CHOICE_FIX = ("Ask it with request_decision (one question, or several at once "
              "in `questions`, each with its options) and leave the options "
              "out of the reply.")


def raised_decision(corpus, execution) -> bool:
    """Whether the run `execution` has asked the owner for a decision."""
    if not execution:
        return False
    try:
        return bool(corpus.operational(execution=execution,
                                       act="decision-requested", limit=1))
    except Exception:                                       # noqa: BLE001
        return False


#: What it says instead once Mentis has asked the choice itself
#: (`mentis.web.prose_decisions`).
CHOICE_ASKED = ("a choice for the owner is written here as a {kind} of {n} "
                "options; this run raised no decision, so Mentis asked it as "
                "decision form {form}, owed by the owner, on this post")
CHOICE_ASKED_FIX = ("Next time ask it with request_decision and leave the "
                    "options out of the reply.")


def with_choices(report, texts, corpus, execution, *, posted=True,
                 asked=None) -> dict:
    """`report` with a warning for each choice written into `texts` -- a list
    of (part index or None, Markdown) -- when the run `execution` raised no
    decision (`mentis.conversation.choices`). Nothing without a run: a
    Scratch answer or a call with no execution is never warned. Never
    raises, and never changes what was written: the warning is said, the
    post stands."""
    from mentis.conversation import choices as _choices
    if not isinstance(report, dict) or not execution:
        return report
    try:
        found = [(i, c) for i, t in texts for c in _choices.find(t)]
        if not found or (not asked and raised_decision(corpus, execution)):
            return report
    except Exception:                                       # noqa: BLE001
        return report
    # `asked`: the decision form Mentis raised from this very prose -- said
    # as that, so the run learns where its question went.
    problems = [{**({"part": i} if i is not None else {}),
                 "block": "prose", "type": "choice", "line": c["line"],
                 "where": "choice", "severity": "warning",
                 "message": (CHOICE_ASKED.format(kind=c["kind"],
                                                 n=len(c["items"]),
                                                 form=asked) if asked else
                             CHOICE_SAYS.format(kind=c["kind"],
                                                n=len(c["items"]))),
                 "fix": CHOICE_ASKED_FIX if asked else CHOICE_FIX,
                 "from": "decision-check",
                 **({"asked_as": asked} if asked else {})}
                for i, c in found]
    out = dict(report)
    if out.get("checked") and not malformed(out):
        out["problems"] = list(out["problems"]) + problems
        out["warnings"] = out["warnings"] + len(problems)
        words = said(out, posted=posted)
        if words:
            out["note"] = words
        return out
    # Not checked for rendering, but the choice is still said.
    out["choices"] = problems
    lines = [f"- line {p['line']}: {p['message']}. Fix: {p['fix']}"
             for p in problems]
    out["note"] = "\n".join(filter(None, [report.get("note"),
                                          "A choice written instead of asked:",
                                          *lines]))
    return out


def texts_of_turn(corpus, turn) -> list:
    """A written Turn's text parts as `with_choices` reads them."""
    try:
        got = corpus.read([turn])
        parts = (got[0].get("body") or {}).get("parts") if got else None
    except Exception:                                       # noqa: BLE001
        return []
    texts = [(i, p["text"]) for i, p in enumerate(parts or ())
             if isinstance(p, dict) and p.get("type") == "text"
             and isinstance(p.get("text"), str)]
    return [(i if len(texts) > 1 else None, t) for i, t in texts]
