"""The `/api/scratch` routes, and how a Scratch question is answered.

See `mentis.scratch_store` for what Scratch is and is not. This module is the
only door to it: `_api` refuses a worker grant on every route but
`/api/worker`, so no dispatched run can reach these, and nothing that reads the
record reads the Scratch tables.

ANSWERING IS NOT DISPATCH. A Scratch question does not go through
`dispatch.py`: no expectation, no execution-started act, no delivery record, no
reply Turn, no instance. It goes to `Foundation.answer_once`, which runs the
Brain's designated carrier of unaddressed requests -- whoever that is today,
read from the designation and never named here -- with the four read tools and
nothing else, and the answer is written back into the Scratch tables. Every
follow-up is answered from the persisted Scratch, rebuilt into a prompt: there
is no session to continue, so there is no session identity to keep.

WHERE IT WAS ASKED FROM is a small envelope of REFERENCES the interface sends
when a Scratch starts (`context`). It is stored as sent, after being bounded.
At answer time each reference is read again and said as what it is NOW, with
whether it changed after the Scratch began -- so "what you were looking at"
and "what the record says now" are never silently the same thing.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time

from mentis.scratch_store import (RETENTION_CHOICES, ScratchGone,
                                  ScratchRefused, ScratchStore, _text_of)
from mentis.web import scratch_paths as _paths
from mentis.conversation.renderers import RENDERER_GUIDE
from mentis.conversation import render_check

#: What carrying a Scratch question needs of a runtime: to call the Mentis
#: read tools. Same requirement as carrying an unaddressed request.
REQUIRES = ("call_mentis_tools",)

#: Bounds on the envelope the interface sends. A bound, not a policy.
MAX_REFS = 24
MAX_LABEL = 160
#: How much of each referenced Turn is put in front of the answerer. The rest
#: is one `resolve` away, and the answerer is told so.
SOURCE_CHARS = 900
#: How much of the Scratch so far is replayed into a follow-up.
HISTORY_CHARS = 24000
ANSWER_DEADLINE_S = 180
MAX_ANSWERS = 4
_answer_lock = threading.Lock()
_answers = {}

_REF_KEYS = ("turn", "conversation", "expectation", "run", "answers")


def _clean_context(ctx) -> dict:
    """The envelope, bounded and with only the keys it is made of."""
    ctx = ctx if isinstance(ctx, dict) else {}
    s = lambda v, n=MAX_LABEL: (v if isinstance(v, str) else "")[:n]  # noqa
    refs = []
    for r in (ctx.get("refs") or ())[:MAX_REFS]:
        if not isinstance(r, dict):
            continue
        row = {k: r[k] for k in _REF_KEYS if isinstance(r.get(k), str)}
        if not row:
            continue
        row["role"] = s(r.get("role"), 40) or "shown"
        row["label"] = s(r.get("label"))
        refs.append(row)
    return {"surface": s(ctx.get("surface"), 40) or "brain",
            "label": s(ctx.get("label")),
            "invoked_at": ctx.get("invoked_at")
            if isinstance(ctx.get("invoked_at"), (int, float)) else time.time(),
            "timezone": s(ctx.get("timezone"), 64),
            "period": s(ctx.get("period"), 40),
            "incomplete": bool(ctx.get("incomplete")),
            "refs": refs}


def store_of(st) -> ScratchStore:
    if getattr(st, "scratch", None) is None:
        st.scratch = ScratchStore(st.corpus)
    return st.scratch


# -- the answer ---------------------------------------------------------------

def _when(at) -> str:
    return time.strftime("%a %d %b %H:%M", time.localtime(at)) if at else "?"


def _source_lines(st, ctx) -> list[str]:
    """Each referenced item, read NOW, and said as what it is now."""
    from mentis.conversation.versions import presented
    cv, corpus = st.cv, st.corpus
    since = ctx.get("invoked_at") or 0
    out = []
    for r in ctx.get("refs") or ():
        bits = [f"- ({r.get('role')}) {r.get('label') or ''}".rstrip()]
        t = r.get("turn")
        if t:
            got = corpus.read([t])
            if not got:
                bits.append(f"  Turn {t}: not held by this Brain.")
            else:
                e = presented(corpus, got[0])
                conv = cv.conversation_of(t)
                cname = cv.conversation_name(conv) if conv else "?"
                said = _text_of((e.get("body") or {}).get("parts") or [])
                head = (f"  Turn {t} = #{cv.turn_number(t)} in "
                        f"\"{cname}\" ({conv}), by "
                        f"{cv.alias(e['attributed_to'])}, "
                        f"{_when(e.get('recorded_at'))}.")
                if e.get("deleted"):
                    head += " DELETED since; its words are not used."
                    said = ""
                elif e.get("revision") and (
                        (e["revision"] or {}).get("edited_at") or 0) > since:
                    head += (" EDITED after this Scratch began; below is the "
                             "current wording.")
                bits.append(head)
                if said:
                    clip = said[:SOURCE_CHARS]
                    more = (f" [... {len(said) - SOURCE_CHARS} more "
                            f"characters; resolve {t} to read it all]"
                            if len(said) > SOURCE_CHARS else "")
                    bits.append("  It says: " + clip.replace("\n", "\n  ")
                                + more)
        x = r.get("expectation")
        if x:
            try:
                s = cv.expectation_state(x)
                bits.append(
                    f"  Request {x}: expects {s.get('expects')} of "
                    f"{cv.alias(s['expected_of']) if s.get('expected_of') else 'nobody'}"
                    f", asked by {cv.alias(s['requested_by'])}; "
                    f"answered: {'yes' if s.get('response_present') else 'no'}"
                    f"; running now: {'yes' if s.get('live_execution') else 'no'}"
                    + (f"; because: {s['because']}" if s.get("because") else ""))
            except Exception as exc:                      # noqa: BLE001
                bits.append(f"  Request {x}: could not be read ({exc}).")
        for k in ("conversation", "run", "answers"):
            if r.get(k) and not (k == "conversation" and t):
                bits.append(f"  {k}: {r[k]}")
        out.append("\n".join(bits))
    return out


def _files_line(access) -> str:
    """What the answerer is told about files: none, or exactly the files and
    folders the owner selected for this question, what each allows, and
    what writing means. `access` is a `FilePlan` (or, as before, a list of
    folders to read and write)."""
    from mentis.web.scratch_paths import FilePlan
    plan = access if isinstance(access, FilePlan) else FilePlan(
        [{"path": f, "kind": "folder", "access": "write"} for f in access or ()])
    if not plan:
        return ("You cannot record, decide, delegate, start work or change "
                "anything, and you have no shell or files. If the owner wants "
                "something done, say what you would ask for and tell them they "
                "can Sidebar it.")
    tools = "Read, Write, Edit, Glob, Grep" if plan.writes else "Read, Glob, Grep"
    return ("You cannot record, decide, delegate or start work in Mentis. "
            "The owner SELECTED these files and folders for this question, "
            f"and you have file tools ({tools}) that work inside them and "
            "your own working directory and nowhere else:\n"
            + "\n".join(plan.lines()) + "\nYou have no shell. "
            + ("What you write in a WRITE HERE folder, and every file Mentis "
               "copies or builds for you, is REAL and stays after this "
               "Scratch is dismissed or expires, so do not overwrite or "
               "replace a file the owner did not ask you to change, and say "
               "in your answer exactly which files you created or changed. "
               if plan.writes or plan.zips else
               "Nothing here lets you change a file; say so if the owner "
               "asks for a change, and which folder or file they would "
               "choose to Write here. ")
            + "If a step needs a file outside these, or something only a "
            "shell could do, do not look for another way: say which file or "
            "folder you would need, and the owner can select it for the next "
            "question.")


def build_prompt(st, scratch, behaviour: str, access=()) -> str:
    ctx = scratch.get("context") or {}
    msgs = [m for m in scratch["messages"] if m["status"] != "pending"]
    # THE LAST ANSWER'S RENDER CHECK, said where that answer is replayed: the
    # run that wrote it had ended before it could be told.
    last = next((m for m in reversed(msgs) if m["role"] == "mentis"
                 and m["status"] == "done"), None)
    convo, used = [], 0
    for m in reversed(msgs):
        if m["role"] == "mentis" and m["status"] != "done":
            line = f"Mentis ({_when(m['at'])}): [no answer -- {m['status']}]"
        else:
            who = "Owner" if m["role"] == "owner" else "Mentis"
            line = f"{who} ({_when(m['at'])}):\n{_text_of(m['parts']).strip()}"
            check = (m.get("provenance") or {}).get("rendering") if m is last else None
            words = render_check.said(check) if isinstance(check, dict) else None
            if words:
                line += ("\n[Mentis checked that answer's Markdown after it was "
                         "shown: " + words + "]")
        used += len(line)
        if used > HISTORY_CHARS and convo:
            convo.append(f"[... {len(msgs) - len(convo)} earlier messages "
                         f"not repeated]")
            break
        convo.append(line)
    convo.reverse()
    sources = _source_lines(st, ctx)
    where = ctx.get("label") or ctx.get("surface") or "Mentis"
    parts = [
        behaviour.strip(),
        "---",
        "YOU ARE ANSWERING IN SCRATCH. Scratch is a temporary conversation "
        "between the owner and Mentis inside this Brain. Nothing said here is "
        "recorded as Brain material, knowledge or work; the owner decides "
        "what, if anything, crosses into the durable Brain (Sidebar, which "
        "takes chosen parts into an ordinary request, or Keep as "
        "Conversation). You can READ the Brain "
        "with the Mentis tools (orient, find, resolve, history, the source "
        "reads, and read_artifact, which shows you an image -- including an "
        "acquired image from a source collection -- so you can look at it "
        "and describe it; write its adm- reference in your answer and the "
        "owner sees the image there). To answer from acquired material, "
        "call search_sources; quote with read_source on a hit's excerpt (with "
        "extraction=<its extractor id> for a hit in extracted text) and "
        "put the quoted passage and its cite in your answer; to show a picture from that passage, open the "
        "embeds_in_excerpt target_ref with read_artifact and write its adm- "
        "reference. If not_searched lists files that may matter (a file "
        "with no extractor, or one whose extraction is pending, empty or "
        "failed), say they were not searched. " + _files_line(access),
        "",
        f"WHERE THIS SCRATCH WAS STARTED: {where}, at "
        f"{_when(ctx.get('invoked_at'))}"
        + (f" ({ctx['timezone']})" if ctx.get("timezone") else "")
        + (f", period: {ctx['period']}" if ctx.get("period") else "") + ".",
    ]
    if ctx.get("incomplete"):
        parts.append("The surface it was started from said its list was "
                     "incomplete; more may exist than is referenced below.")
    if sources:
        parts += ["What the owner had in front of them, by reference, READ "
                  f"AGAIN NOW ({_when(time.time())}):", *sources]
    else:
        parts.append("No particular item was referenced; use the tools to "
                     "look if the question needs it.")
    parts += ["", "DELETED MATERIAL: a tool answer that carries material "
              "from a deleted Turn or Conversation says so in a `deleted` "
              "field. You may use it, but mark every passage that does, "
              "inline, as deleted material. The owner is also shown that "
              "this answer had access to it.",
              "", "If a question is ambiguous (e.g. 'those two agents' with "
              "nothing that identifies two), ask the owner rather than guess.",
              "", RENDERER_GUIDE, "", "THE SCRATCH SO FAR (answer the last "
              "message from the Owner):", "", "\n\n".join(convo)]
    return "\n".join(parts)


def _fits(ad, access) -> bool:
    """Can this adapter carry this Scratch answer: no saved session, and --
    where folders were selected -- file access confined to them."""
    return bool(getattr(ad, "transient_ok", False) and (
        not access or getattr(ad, "folder_bounded", False)))


def _choose_runtime(st, execution=None, access=()):
    """The ordinary selection, then the first runtime that can answer
    read-only if the ordinary choice cannot. Said, not guessed.

    WITH SELECTED FOLDERS, only a runtime that confines file access to them
    (`folder_bounded`) can answer. An explicit choice that cannot is refused
    with what it cannot enforce -- never substituted, never run wider."""
    f = st.agents._foundation
    execution = execution or {}
    sel = st.agents.execution_select(requires=REQUIRES, **execution)
    chosen = f.adapter(sel.runtime)
    if _fits(chosen, access):
        return sel, None
    cannot = None
    if access and not getattr(chosen, "folder_bounded", False):
        why = getattr(chosen, "folder_bounds_why", "") or (
            f"{sel.runtime} does not confine file access to selected folders")
        if execution:
            raise ScratchRefused(f"{why}; the explicit choice will not be "
                                 "substituted")
        cannot = (f"{sel.runtime} was selected but cannot work only in the "
                  f"selected folders ({why})")
    elif execution:
        raise ScratchRefused(f"{sel.runtime} cannot answer Scratch read-only; "
                             "the explicit choice will not be substituted")
    # Every adapter that promises the transient contract is eligible.
    for kind, ad in f._adapters.items():
        if _fits(ad, access):
            try:
                return (st.agents.execution_select(runtime=kind,
                                                   requires=REQUIRES),
                        f"{cannot}; {kind} can" if cannot else
                        f"{sel.runtime} was selected but cannot answer "
                        f"read-only; {kind} can")
            except Exception:                             # noqa: BLE001
                continue
    if access:
        raise ScratchRefused("no runtime present here can work only in the "
                             f"selected folders (selected: {sel.runtime}"
                             + (f"; {cannot}" if cannot else "") + ")")
    raise ScratchRefused(f"no runtime present here can answer Scratch "
                         f"read-only (selected: {sel.runtime})")


def answer(st, sid, n, cancel_event=None):
    """Produce answer `n` of Scratch `sid`. Runs on its own thread."""
    store = store_of(st)
    cv = st.cv
    prov = {"asked_at": time.time()}
    wrote = []         # what Mentis wrote for this answer, as it is written
    try:
        carrier = cv.intake_carrier()
        if not carrier.get("resolved"):
            raise ScratchRefused(
                "nobody is designated to answer for Mentis in this Brain "
                f"({carrier.get('detail')})")
        prov.update({"participant": carrier["participant"],
                     "alias": carrier.get("alias")
                     or cv.alias(carrier["participant"]),
                     "persona": carrier["persona"],
                     "designation": carrier["designation"]})
        scratch = store.get(sid)
        question_row = next(m for m in scratch["messages"]
                            if m["n"] == n - 1 and m["role"] == "owner")
        question = _text_of(question_row["parts"])
        asked = question_row.get("provenance") or {}
        execution = asked.get("execution") or {}
        # THE FILES AND FOLDERS THIS QUESTION WAS SENT WITH, and no others
        # (`scratch_paths`). A question from before refs carried folders to
        # read and write, and still means exactly that.
        refs = list(asked.get("refs") or ()) or [
            {"path": f, "kind": "folder", "access": "write", "exists": True}
            for f in asked.get("access") or ()]
        plan = _paths.FilePlan(refs)
        access = list(plan.access)
        prov["execution"] = execution
        if access:
            prov["access"] = access
        if refs:
            prov["refs"] = refs
        # THE CARRIER'S OWN BEHAVIOUR, by the ordinary composition seam --
        # read-only, and `record_delivery` is deliberately never called.
        comp = cv.compose(participant=carrier["participant"],
                          persona=carrier["persona"], question=question)
        named = [r["path"] for r in refs]
        sel, why_other = (_choose_runtime(st, execution, named) if named
                          else _choose_runtime(st, execution) if execution
                          else _choose_runtime(st))
        prov.update({"runtime": sel.runtime, "requested_model": sel.model,
                     "requested_effort": sel.requested_effort,
                     "runtime_switch": why_other,
                     "selection": list(sel.because)
                     + ([why_other] if why_other else [])})
        # Publish the switch while the answer is pending, not only afterward.
        if not store.pending_provenance(sid, n, prov):
            return
        prompt = build_prompt(st, scratch, comp.payload(), plan)
        t0 = time.time()
        files = {"access": access} if access else {}
        if plan and not plan.legacy():
            # WHAT MENTIS DOES AROUND THE RUN, inside the run's own private
            # scratch: copies in before it starts, copies out and ZIPs after
            # it finishes -- before that scratch is discarded.
            files.update(
                read_only=plan.read_only, files=plan.files,
                stage=lambda where: _paths.stage(plan, where),
                collect=lambda where, res: _paths.collect(
                    st.corpus, plan, where, res, into=wrote))
        res = st.agents.agents_answer_once(
            prompt, runtime=sel.runtime, model=sel.model,
            effort=sel.requested_effort, live_key=(sid, n),
            deadline_s=ANSWER_DEADLINE_S, cancel_event=cancel_event,
            **files)
        # WHAT THE RUNTIME REPORTED DOING TO FILES, kept beside the answer: a
        # real effect outlives this Scratch, and the owner is shown which.
        acts = [dict(a) for a in (getattr(res, "actions", None) or ())]
        if acts:
            prov["actions"] = acts
        # AND WHAT MENTIS ITSELF WROTE for this answer: copies out, ZIPs.
        if wrote:
            prov["mentis_actions"] = wrote
        # DELETED MATERIAL THE DOOR SERVED THIS RUN, as the door noted it --
        # the banner is drawn from this whether or not the answer used it.
        # Kept beside the Scratch like the rest of its provenance; nothing is
        # written to the record.
        gone = list(getattr(res, "deleted_material", None) or ())
        if gone:
            prov["deleted_material"] = gone
        prov.update({
            "seconds": round(time.time() - t0, 1),
            "model": getattr(res.actual_model, "value", None),
            "effort": getattr(res.actual_effort, "value", None),
            "tool_calls": list(res.tool_calls or ()),
            "usage": {k: v for k, v in (res.usage or {}).items()
                      if isinstance(v, (int, float))}})
        said = (res.reported or "").strip()
        if res.exit_code != 0 or res.error or not said:
            prov["error"] = (f"answer time limit ({ANSWER_DEADLINE_S} seconds) reached"
                             if getattr(res, "timed_out", False) else res.error or ("the answer was empty"
                                           if not said else
                                           f"exit {res.exit_code}"))[:600]
            store.settle(sid, n, status="failed", provenance=prov)
            return
        # WHAT IN THE ANSWER WILL NOT RENDER. The run has ended, so it is kept
        # beside the answer, and the next answer is shown it (`build_prompt`).
        # The answer is settled as written whatever it says.
        prov["rendering"] = render_check.check(said)
        store.settle(sid, n, status="done",
                     parts=[{"type": "text", "text": said}], provenance=prov)
    except ScratchGone:
        return            # dismissed or kept meanwhile; nothing to settle
    except Exception as exc:                              # noqa: BLE001
        prov["error"] = f"{type(exc).__name__}: {exc}"[:600]
        if wrote:
            # A FILE ALREADY WRITTEN IS WRITTEN, whatever stopped the rest.
            prov["mentis_actions"] = wrote
        try:
            store.settle(sid, n, status="failed", provenance=prov)
        except Exception:                                 # noqa: BLE001
            pass


#: Replaced by tests, so an ask can be answered without a runtime.
def answer_soon(st, sid, n):
    key = (id(st), sid, n)
    event = threading.Event()
    with _answer_lock:
        if len(_answers) >= MAX_ANSWERS:
            store_of(st).settle(sid, n, status="failed", provenance={
                "error": "Scratch answer capacity reached; ask again shortly"})
            return
        _answers[key] = event
    def run():
        try:
            if not event.is_set():
                answer(st, sid, n, event)
        finally:
            with _answer_lock:
                _answers.pop(key, None)
    threading.Thread(target=run, daemon=True,
                     name=f"scratch-{sid}-{n}").start()


# -- the routes ----------------------------------------------------------------

def _execution(body) -> dict:
    """Per-question constraints. Identity and authority are never selectable."""
    value = body.get("execution")
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - {"runtime", "model"}:
        raise ScratchRefused("Scratch selection accepts only runtime and model")
    for key, item in value.items():
        if not isinstance(item, str) or not item.strip() or len(item) > 200:
            raise ScratchRefused(f"Scratch {key} must be a nonempty name")
    return dict(value)


#: How many files and folders one question may be given.
MAX_ACCESS = 8


def _access(st, body) -> list:
    """The files and folders the owner selected for this question
    (`scratch_paths.refs_of`): each checked the way the folder chooser
    checks a folder -- absolute, real, not a link or junction, neither
    inside nor holding this Brain's record -- and as resolved. Returned as
    PathRefs, in order. Selecting grants nothing to anybody else and is not
    recorded: it travels with the question, in the Scratch."""
    try:
        return _paths.refs_of(st.corpus, body)
    except _paths.Refused as exc:
        raise ScratchRefused(str(exc))


def _given(refs) -> list:
    """The folders a question's runtime is given (`provenance.access`, kept
    for what reads it): WRITE folders, then READ folders."""
    from mentis.web.scratch_paths import FilePlan
    return list(FilePlan(refs).access)


_PLAIN_ONLY = _paths.PLAIN_ONLY
_device_or_network = _paths.device_or_network


def _parts(body) -> list:
    parts = body.get("parts")
    if not isinstance(parts, list) or not parts:
        parts = [{"type": "text", "text": body.get("text") or ""}]
    return [p for p in parts if isinstance(p, dict)
            and p.get("type") in ("text", "turn", "topic", "conversation")]


def _settings(store) -> dict:
    return {"retain_days": store.retain_days(),
            "choices": list(RETENTION_CHOICES),
            "usage": store.usage()}


def _participant(corpus, ref):
    got = corpus.read([ref])
    return bool(got and (got[0].get("definition") or {}).get("name") == "participant")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def sidebar(st, store, sid, body, presented=None) -> dict:
    # Serialize preview validation, the ordinary post, and its durable receipt.
    # The receipt contains only the deliberate crossing, never unchosen text.
    author = body.get("author")
    key = body.get("send_key")
    fingerprint = _digest({k: v for k, v in body.items()
                           if k not in ("preview", "send_key", "preview_token")})
    dispatches = []
    def enqueue(state, **kw):
        dispatches.append(kw)
    with st.corpus.atomic():
        if not body.get("preview"):
            if not author:
                raise ScratchRefused("only this Scratch's owner can sidebar it")
            try:
                s = store.get(sid)
                if s["owner"] != author:
                    raise ScratchRefused("only this Scratch's owner can sidebar it")
            except ScratchGone:
                pass  # A completed send remains retryable after Dismiss/Keep.
            if not isinstance(key, str) or not 8 <= len(key) <= 128:
                raise ScratchRefused("Sidebar sending needs a one-time send key")
            for act in st.cv.history(act="scratch-sidebar-sent", actor=author):
                detail = act.get("detail") or {}
                if detail.get("scratch") == sid and detail.get("send_key") == key:
                    if detail.get("fingerprint") != fingerprint:
                        raise ScratchRefused("this send key already carried different content")
                    return {**detail["result"], "retried": True}
        result = _sidebar(st, store, sid, body, presented, _dispatch=enqueue)
        if not body.get("preview"):
            st.cv.record_act(actor=author, act="scratch-sidebar-sent",
                             conversation=result["conversation"], turn=result["turn"],
                             detail={"scratch": sid, "send_key": key,
                                     "fingerprint": fingerprint, "result": result})
    # No answering process can start until the request and receipt commit.
    from mentis.web import dispatch_soon
    for kw in dispatches:
        dispatch_soon(st, **kw)
    return result


def _sidebar(st, store, sid, body, presented=None, *, _dispatch=None) -> dict:
    """Let's Sidebar this: chosen parts of a Scratch, as an ordinary request.

    `preview: true` writes nothing and returns exactly the Turn that sending
    would post. Sending posts it THROUGH THE ORDINARY ROUTES -- the same
    `/api/conversations` and `/api/conversations/<id>/turns` the composer
    uses -- so it is owed, assigned, dispatched and governed like any request,
    and nothing here decides any of that. The Scratch is not changed.
    """
    from mentis.scratch_crossing import sidebar_parts
    from mentis.web import ASK_MENTIS, ASK_PARTICIPANT, _routes
    cv = st.cv
    s = store.get(sid)
    author = body.get("author")
    if not author or author != s["owner"]:
        raise ScratchRefused("only this Scratch's owner can sidebar it")
    turn = sidebar_parts(s, st.corpus, request=body.get("request"),
                         carry=body.get("carry") or (),
                         refs=body.get("refs") or ())
    # WHERE: an existing Conversation, or a new one by name.
    conv = body.get("conversation")
    new_name = (body.get("new_conversation") or "").strip()
    if conv:
        if conv not in {c["id"] for c in cv.all_conversations()}:
            raise ScratchRefused(f"{conv} is not a Conversation in this Brain")
        new_name = ""
    elif not new_name:
        new_name = body["request"].strip().split("\n")[0][:80]
    # WHO: Mentis -- whoever carries requests addressed to nobody, resolved by
    # the ordinary path when it is posted -- or a Participant by name.
    to = body.get("to") or None
    if to and (to == author or not _participant(st.corpus, to)):
        raise ScratchRefused("ask Mentis, or another Participant this Brain "
                             "holds")
    out = {"preview": bool(body.get("preview")), **turn,
           "conversation": conv, "new_conversation": new_name or None,
           "to": to, "action": ASK_PARTICIPANT if to else ASK_MENTIS}
    from mentis.conversation.versions import presented as current
    versions = [current(st.corpus, st.corpus.read([r["ref"]])[0])
                for r in turn["references"]]
    # `preview` differs between reading and sending, so normalize it.
    normalized = {**out, "preview": True}
    token = _digest({"scratch": sid, "owner": author, "turn": normalized,
                     "versions": versions})
    # WHO IT WILL REACH, said before sending -- read now, from the ordinary
    # designation, and NOT part of the token: the ordinary path resolves the
    # carrier again when it posts, and the send reports what it did.
    routes_to = _routes_to(st, to)
    if body.get("preview"):
        return {**out, "preview_token": token, "routes_to": routes_to}
    if body.get("preview_token") != token:
        raise ScratchRefused("the Sidebar preview changed; refresh and review it before sending")

    if not conv:
        made = _routes(st, "/api/conversations", {},
                       {"name": new_name, "author": author}, "POST",
                       presented)
        if "error" in made:
            raise ScratchRefused(made["error"])
        conv = made["conversation"]
    said = _routes(st, f"/api/conversations/{conv}/turns", {}, {
        "author": author, "parts": turn["parts"], "text": turn["text"],
        "addressed_to": [to] if to else [], "topics": [], "because": None,
        "action": out["action"],
        "dispatch": [{"participant": to}] if to else []}, "POST", presented,
        _enqueue_dispatch=_dispatch)
    if "error" in said:
        raise ScratchRefused(said["error"])
    # Using a Scratch is activity: the retention clock restarts.
    store.touch(sid)
    return {**out, "preview": False, "conversation": conv,
            "name": st.cv.conversation_name(conv),
            "turn": said["turn"], "number": said.get("number"),
            "expectations": said.get("expectations") or [],
            "routes_to": routes_to, **_went_to(st, to, said)}


def _routes_to(st, to) -> dict:
    """Who a Sidebar asking `to` (None: Mentis) would reach, as the record
    says today. A reading for the owner, never a choice made here."""
    cv = st.cv
    if to:
        return {"participant": to, "alias": cv.alias(to), "via": "addressed"}
    carrier = cv.intake_carrier()
    if not carrier.get("resolved"):
        return {"participant": None, "alias": None, "via": "intake",
                "why_not": carrier.get("detail"),
                "reason": carrier.get("reason")}
    return {"participant": carrier["participant"],
            "alias": carrier.get("alias") or cv.alias(carrier["participant"]),
            "via": "intake"}


def _went_to(st, to, said) -> dict:
    """WHERE THE WORK WENT, as the ordinary Turn route reported it: the
    addressee, the carrier intake assigned, or nobody yet and why. Read from
    what was done, not from what the preview expected."""
    if to:
        return {"carried_by": {"participant": to, "alias": st.cv.alias(to)}}
    if said.get("assigned"):
        return {"carried_by": {"participant": said.get("carrier"),
                               "alias": said.get("alias")
                               or st.cv.alias(said.get("carrier"))}}
    return {"carried_by": None,
            "unassigned": {"why_not": said.get("why_not"),
                           "reason": said.get("reason")}}


def routes(st, path, query, body, method, presented=None):
    """None when the path is not Scratch's."""
    if path != "/api/scratch" and not path.startswith("/api/scratch/"):
        return None
    store = store_of(st)
    one = lambda k, d=None: (query.get(k) or [d])[0]      # noqa: E731

    if path == "/api/scratch" and method == "GET":
        return {"recent": store.recent(owner=one("owner")),
                **_settings(store)}

    if path == "/api/scratch/settings" and method == "GET":
        days = one("retain_days")
        out = _settings(store)
        if days is not None:
            try:
                d = None if days in ("never", "") else int(days)
            except (TypeError, ValueError):
                raise ScratchRefused("retention must be a number of days or never")
            if d not in RETENTION_CHOICES:
                raise ScratchRefused("retention is 1, 7, 30, 90 days or never")
            out["would_delete"] = store.would_expire(d)
        return out

    if path == "/api/scratch/settings" and method == "POST":
        got = store.set_retain_days(body.get("retain_days"),
                                    confirm_deleting=body.get(
                                        "confirm_deleting"))
        return {**got, **_settings(store)}

    if path == "/api/scratch" and method == "POST":
        owner = body.get("owner")
        if not owner or not _participant(st.corpus, owner):
            raise ScratchRefused("a Scratch needs its owner, as a Participant "
                                 "this Brain holds")
        parts = _parts(body)
        execution = _execution(body)
        refs = _access(st, body)
        with store.write():
            sid = store.create(owner=owner,
                               context=_clean_context(body.get("context")))
            n = store.ask(sid, parts, execution=execution,
                          access=_given(refs), refs=refs)
        answer_soon(st, sid, n)
        return {"scratch": sid, "pending": n}

    # THE `//` PATH SELECTOR'S LISTING: one folder, bounded, never recorded.
    # Behind the same boundary as every route here (the client header, no
    # worker grant -- `_api`); it reads the disk of the machine Mentis runs on.
    if path == "/api/scratch/paths" and method == "GET":
        return _paths.listing(st.corpus, one("prefix", "") or "")

    sid, _, tail = path[len("/api/scratch/"):].partition("/")

    if method == "GET" and not tail:
        try:
            got = store.get(sid)
        except ScratchGone as exc:
            return {"scratch": sid, "gone": True, "why": str(exc)}
        got["answering_now"] = [n for s, n in st.agents.agents_answering_now()
                                if s == sid]
        return got

    if method == "POST" and tail == "ask":
        refs = _access(st, body)
        n = store.ask(sid, _parts(body), execution=_execution(body),
                      access=_given(refs), refs=refs)
        answer_soon(st, sid, n)
        return {"scratch": sid, "pending": n}

    if method == "POST" and tail == "dismiss":
        with _answer_lock:
            for (state, scratch, _), event in _answers.items():
                if state == id(st) and scratch == sid:
                    event.set()
        return {"scratch": sid, "dismissed": store.dismiss(sid)}

    if method == "POST" and tail == "sidebar":
        return sidebar(st, store, sid, body, presented)

    if method == "POST" and tail == "keep":
        from mentis.scratch_crossing import keep
        from mentis.web import _observed_writer
        return keep(store, st.cv, st.corpus, sid, by=body.get("author"),
                    name=body.get("name"),
                    written_by=_observed_writer(st, presented))

    return None
