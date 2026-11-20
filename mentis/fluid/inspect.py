"""WHAT A NEEDS YOU REQUEST IS ABOUT, so it can be inspected before it is
decided (owner, 2026-11-20: "Needs You: inspect before deciding").

  GET /fluid/api/needs-you/about?ids=<ask>,<ask>

For each request (`expectation-recorded` act) asked of somebody: what kind of
request it is, a plain sentence saying what is asked, and every thing it
names, each resolved BY ITS EXACT ID to what a person reads -- a post's first
line and where it is, a Brain record's Kind and words, a finding, a file --
or to the plain reason it cannot be read. A request of a decision form
answers for the whole form.

THE ROLES COME FROM THE RECORD'S STRUCTURE, NEVER FROM WORDS:

  subject     what would be approved: the record an adoption request names
              (`material`, `adoption_request`), each finding of a decision
              about findings (`reconsideration.findings`), the operation of a
              run's permission question (the form's `operation`), the exact
              response set an input waits on (`response_set`: the set the
              owner's Done is matched against, named by its block and part,
              never the post it happens to be in), the material any other
              ask names (`material`)
  evidence    what the record says supports it: what the record to adopt
              rests on (`ladder.basis_of`), what an ask recorded as its
              `evidence`
  context     where it was asked and the work it belongs to: the asking
              post, the request the asking work answers, the work the findings
              were found during, the run that asks
  referenced  ids written in the request's own words (its questions, options,
              reasons and asking post). The record does not say what part
              they play, so none is claimed

NOTHING IS LOOKED UP BY TITLE, and a `#12` in somebody's prose is not
resolved at all: it may be a post number or the twelfth item of a list, and
guessing would put an unrelated post in front of a decision. An id that
resolves to nothing says so (`state`), and is still listed.

Read-only. It answers what every other Fluid read answers to, through the
same door, and changes nothing about who may decide what.
"""

from __future__ import annotations

import hashlib
import re

from mentis.conversation import DECISION_FORM, knowing_of
from mentis.conversation.versions import flow_text, presented

from . import read as _read

#: An id as Mentis writes one, wherever it stands in words.
MENTION = re.compile(r"(?<![0-9A-Za-z_-])((?:ent|opr|adm)-[0-9a-f]{6,})(?![0-9A-Za-z_-])")
#: At most this many ids read out of a request's words.
MENTIONS_MAX = 24
#: At most this many of what a record rests on.
BASIS_MAX = 8
LABEL = 160

#: Why a reference cannot be opened, in the words shown for it.
WHY = {
    "missing": "This Brain holds nothing with this id.",
    "deleted": "This post was deleted.",
    "erased": "This was permanently deleted with its conversation.",
    "unreadable": "This could not be read.",
    "purged": "Mentis no longer holds this file.",
    "not-held": "Mentis does not hold this file's contents.",
    "held-but-missing": "This file's contents are missing from this Brain.",
    "held-but-corrupt": "This file's contents are damaged in this Brain.",
}


def mentions(*texts) -> list[str]:
    """Every id written in these words, once each, in the order written."""
    out: dict[str, None] = {}
    for t in texts:
        if isinstance(t, str):
            for m in MENTION.finditer(t):
                out.setdefault(m.group(1))
    return list(out)


def _line(text) -> str | None:
    line = next((s for s in (re.sub(r"^[#>*\-\s]+", "", x).replace("**", "").strip()
                             for x in (text or "").splitlines()) if s), None)
    if line and len(line) > LABEL:
        line = line[:LABEL - 1].rstrip() + "…"
    return line


class _Resolver:
    """Each id to what it is, by that id alone; asked once per answer."""

    def __init__(self, st):
        self.st, self.cv, self.corpus = st, st.cv, st.corpus
        self._got: dict[str, dict] = {}

    def of(self, ref) -> dict:
        if ref not in self._got:
            try:
                self._got[ref] = self._read(ref)
            except Exception:                              # noqa: BLE001
                # ONE UNREADABLE REFERENCE NEVER HIDES THE REST, and is never
                # dropped: it is listed as what it is, unreadable.
                self._got[ref] = self._gone(ref, "unreadable")
        return dict(self._got[ref])

    @staticmethod
    def _gone(ref, state, **more) -> dict:
        return {"id": ref, "type": more.pop("type", "unknown"), "label": None,
                "available": False, "state": state, "why": WHY[state],
                "opens": None, **more}

    def _where(self, turn) -> dict:
        home = _read.homes_of(self.corpus, [turn]).get(turn)
        number = _read.numbers_of(self.corpus, {turn: home}).get(turn) if home else None
        name = _read._names(self.corpus, [home]).get(home) if home else None
        return {"post": turn, "conversation": home, "conversation_name": name,
                "number": number}

    def _post(self, entry, type_="post", label=None) -> dict:
        from mentis.spine.erasure import erased_by
        ref = entry["id"]
        where = self._where(ref)
        if erased_by(entry.get("body")):
            return self._gone(ref, "erased", type=type_, **where)
        now = presented(self.corpus, entry)
        if now.get("deleted"):
            return self._gone(ref, "deleted", type=type_, **where)
        said = _line(flow_text((now.get("body") or {}).get("parts")))
        return {"id": ref, "type": type_, "label": label or said,
                "by_name": self.cv.alias(entry.get("attributed_to")),
                "available": bool(where["conversation"]), "state": "ok",
                "why": None if where["conversation"] else
                "This post is in no conversation, so it cannot be opened.",
                "opens": "post" if where["conversation"] else None, **where}

    def response_set(self, sid) -> dict:
        """THE SET AN INPUT WAITS ON, by its own id: the block and part it
        is the answers of, and the post that block is in. This -- not the
        post -- is what the owner's Done is matched against
        (`worker.request_input`, `Conversations._input_given`), and one post
        may carry several."""
        from mentis.conversation import responses
        from mentis.spine.erasure import erased_by
        try:
            got = self.corpus.read([sid]) if sid else []
        except Exception:                                  # noqa: BLE001
            return self._gone(sid, "unreadable", type="form")
        if not got:
            return self._gone(sid or "", "missing", type="form")
        e = got[0]
        if erased_by(e.get("body")):
            return self._gone(sid, "erased", type="form")
        body = e.get("body") or {}
        if (e.get("definition") or {}).get("name") != responses.RESPONSE_SET \
                or not body.get("post") or not body.get("block"):
            return {**self._gone(sid, "unreadable", type="form"),
                    "why": "This is not a set of answers to a form."}
        post = (self.corpus.read([body["post"]]) or [None])[0]
        if post is None or not _read._is_post(post):
            return {**self._gone(sid, "unreadable", type="form"),
                    "why": "The post this form is in could not be read."}
        at = self._post(post, "form")
        part = body.get("part") or 0
        return {**at, "id": sid, "label": body["block"] if at["state"] == "ok" else None,
                "block": body["block"], "part": part, "set": sid,
                "anchor": f"block:{body['block']}"}

    def _read(self, ref) -> dict:
        if ref.startswith("opr-"):
            return self._act(ref)
        got = self.corpus.read([ref])
        if not got:
            return self._gone(ref, "missing")
        e = got[0]
        if e.get("family") == "admission":
            return self._file(ref)
        from mentis.spine.erasure import erased_by
        if _read._is_post(e):
            return self._post(e)
        if erased_by(e.get("body")):
            return self._gone(ref, "erased")
        kind = (e.get("definition") or {}).get("name")
        body = e.get("body") or {}
        if e.get("link"):
            return {"id": ref, "type": "link", "kind": kind,
                    "label": f"a link ({e['link'].get('relation')})",
                    "available": True, "state": "ok", "why": None, "opens": None}
        if _read._is_conversation(e):
            return {"id": ref, "type": "conversation",
                    "label": _read._names(self.corpus, [ref]).get(ref),
                    "conversation": ref, "available": True, "state": "ok",
                    "why": None, "opens": "conversation"}
        if _read._is_participant(e):
            return {"id": ref, "type": "participant", "label": self.cv.alias(ref),
                    "available": True, "state": "ok", "why": None, "opens": None}
        from mentis.web.ladder import _name, _said
        label = _name(e) or _line(_said(e)) or None
        if knowing_of(self.corpus, kind) in ("that", "how"):
            from mentis.conversation import ladder
            return {"id": ref, "type": "record", "kind": kind, "label": label,
                    "status": ladder.adoption_status(self.corpus, ref),
                    "available": True, "state": "ok", "why": None,
                    "opens": "record"}
        return {"id": ref, "type": "entry", "kind": kind,
                "label": label or body.get("name"), "available": True,
                "state": "ok", "why": None, "opens": None}

    def _file(self, ref) -> dict:
        from mentis.artifacts import describe
        a = describe(self.corpus, ref, verify=False)
        state = a.get("state")
        held = state == "held"
        return {"id": ref, "type": "file", "label": a.get("name"),
                "available": held, "state": "ok" if held else state,
                "why": None if held else WHY.get(state, WHY["unreadable"]),
                "opens": "file" if held else None,
                "file": ({"state": state, "name": a.get("name"),
                          "size": a.get("size"),
                          "claimed_media_type": a.get("claimed_media_type")}
                         if held else None)}

    def _act(self, ref) -> dict:
        a = self.cv._act(ref)
        if a is None:
            return self._gone(ref, "missing")
        from mentis.spine.erasure import erased_by
        if erased_by(a.get("detail")):
            return self._gone(ref, "erased")
        act, d = a["act"], a.get("detail") or {}
        turn = (self.cv.asked_on(a) if act == "expectation-recorded"
                else self.cv._form_post(ref) if act == DECISION_FORM
                else a.get("turn"))
        entry = (self.corpus.read([turn]) or [None])[0] if turn else None
        if act == "expectation-recorded":
            found = any(x["act"] == "work-discovered"
                        for x in self.corpus.operational(about=ref))
            type_ = "finding" if found else "request"
            words = d.get("question")
        elif act == "execution-started":
            # A RUN IS NOT ITS REQUEST'S POST: its own activity is under
            # Working, so it is named and nothing else is opened in its place.
            return {"id": ref, "type": "run",
                    "label": f"{self.cv.alias(a['actor'])}'s run",
                    "available": True, "state": "ok", "opens": None,
                    "why": "Its activity is under Working."}
        elif act == DECISION_FORM:
            type_, words = "request", None
        else:
            # ANY OTHER ACT has no page of its own; the post it was recorded
            # on is not it, so that post is not opened in its place.
            return {"id": ref, "type": "activity",
                    "label": "a record of activity (" + act.replace("-", " ") + ")",
                    "available": True, "state": "ok", "opens": None,
                    "why": "It has no page of its own to open."}
        if entry is not None and _read._is_post(entry):
            return {**self._post(entry, type_, _line(words) if type_ != "finding" else None),
                    "id": ref}
        return {"id": ref, "type": type_, "label": _line(words) or _line(a.get("because")),
                "available": False, "state": "ok",
                "why": "It is on no post, so there is nothing to open.",
                "opens": None}


def _kind(cv, act) -> str:
    d = act.get("detail") or {}
    form = d.get("form")
    if form and cv._permission_form(form):
        return "permission"
    if form:
        return "form"
    if d.get("reconsideration"):
        return "findings"
    if d.get("adoption_request"):
        return "adoption"
    if d.get("expects") == "input":
        return "input"
    return "decision" if d.get("expects") == "decision" else "request"


def _about(r: _Resolver, act) -> dict:
    cv, corpus = r.cv, r.corpus
    d = act.get("detail") or {}
    kind = _kind(cv, act)
    by = cv.alias(act["actor"]) or "Somebody"
    form = cv.decision_form(d["form"]) if d.get("form") else None
    questions = ([a for a in (cv._act(q["expectation"]) for q in form["questions"]) if a]
                 if form else [act])
    turn = cv.asked_on(act)
    post = (corpus.read([turn]) or [None])[0] if turn else None
    post_words = (flow_text((presented(corpus, post).get("body") or {}).get("parts"))
                  if post is not None and _read._is_post(post) else "")
    lead = _line(post_words)

    def ref(i, relation, **more):
        return {**r.of(i), "relation": relation, **more}

    subject, evidence, context = [], [], []
    operation = None
    if turn:
        context.append(ref(turn, "where it was asked"))
    material = list(dict.fromkeys(m for q in questions
                                  for m in ((q.get("detail") or {}).get("material") or ())))
    if kind == "adoption":
        from mentis.conversation import ladder
        link = (corpus.read([d["adoption_request"]]) or [None])[0]
        for m in material:
            subject.append(ref(m, "the record you would adopt"))
            for b in ladder.basis_of(corpus, m)[:BASIS_MAX]:
                evidence.append(ref(b["ref"], "what the record rests on"))
        for old in ((link or {}).get("body") or {}).get("replaces") or ():
            context.append(ref(old, "the record it would replace"))
        named = subject[0] if subject else None
        says = (f"{by} asks you to adopt this {(named or {}).get('kind') or 'record'}"
                + (f": “{named['label']}”" if named and named.get("label") else "."))
    elif kind == "findings":
        rec = d["reconsideration"]
        for f in rec.get("findings") or ():
            subject.append(ref(f, "a finding to decide"))
        if rec.get("originating_turn"):
            context.append(ref(rec["originating_turn"],
                               "the work they were found during"))
        n = len(subject)
        says = (f"{by} asks what should happen to "
                f"{'the one thing' if n == 1 else f'the {n} things'} found along the way.")
    elif kind == "permission":
        asked = cv._act(d["form"]) or {}
        fd = asked.get("detail") or {}
        op = fd.get("operation") or {}
        operation = {k: op.get(k) for k in (
            "summary", "command", "cwd", "tool", "tool_label", "resources",
            "workspace", "within", "outside", "why", "agent_says") if op.get(k) is not None}
        if fd.get("run"):
            context.append(ref(fd["run"], "the run that asks"))
        req = cv._act(asked.get("caused_by")) if asked.get("caused_by") else None
        if req and req.get("turn") and req["turn"] != turn:
            context.append(ref(req["turn"], "the request this run is working on"))
        says = (f"{by} asks permission to {op['summary'][:1].lower() + op['summary'][1:]}."
                if op.get("summary") else f"{by} asks permission for an operation.")
    elif kind == "input":
        # THE SUBJECT IS THE RESPONSE SET THE REQUEST NAMES, by its id: the
        # exact set a Done must be written to for this wait to be answered.
        sid = d.get("response_set")
        form_ref = {**r.response_set(sid), "relation": "the form to fill in"}
        subject.append(form_ref)
        block = form_ref.get("block")
        if form_ref.get("post") == turn:
            context.clear()
        says = (f"{by} waits for you to fill in "
                + (f"the form “{block}”." if block else "a form."))
    else:
        for m in material:
            subject.append(ref(m, "what this is about"))
        if form and form.get("request"):
            req = cv._act(form["request"])
            if req and req.get("turn") and req["turn"] != turn:
                context.append(ref(req["turn"], "the request this work answers"))
        n = len(questions)
        expects = d.get("expects")
        says = (f"{by} asks you to decide {n} questions." if kind == "form" and n > 1
                else f"{by} asks you to decide: {d.get('question') or lead or 'see the asking post'}"
                if expects == "decision"
                else f"{by} asks you: {lead}" if lead and expects == "clarification"
                else f"{by} waits on you for a {expects or 'reply'}"
                     + (f": {lead}" if lead else "."))
    for q in questions:
        for e in (q.get("detail") or {}).get("evidence") or ():
            if isinstance(e, str):
                evidence.append(ref(e, "recorded as its evidence"))

    # IDS IN THE REQUEST'S OWN WORDS. Listed whatever they resolve to; what
    # part each plays is not stated by the record, so none is claimed.
    words = [post_words, (form or {}).get("because")]
    for q in questions:
        qd = q.get("detail") or {}
        words += [qd.get("question"), q.get("because")]
        for o in qd.get("options") or ():
            if isinstance(o, dict):
                words += [o.get("label"), o.get("consequence")]
                for f in o.get("findings") or ():
                    words += [f.get("label"), f.get("why")]
    placed = {x["id"] for x in subject + evidence + context}
    referenced = [ref(i, "named in the request's words")
                  for i in mentions(*words)[:MENTIONS_MAX] if i not in placed]

    def once(rows):
        seen, out = set(), []
        for x in rows:
            if x["id"] not in seen:
                seen.add(x["id"])
                out.append(x)
        return out

    return {"id": act["id"], "kind": kind, "form": d.get("form"),
            "says": says, "asked_by_name": by,
            "subject": once(subject), "evidence": once(evidence),
            "context": once(context), "referenced": once(referenced),
            **({"operation": operation} if operation is not None else {})}


def about(st, ids) -> dict:
    """`GET /fluid/api/needs-you/about?ids=`: each request as `_about` reads
    it, in the order asked. One that is not a request is `{"id", "error"}`."""
    cv = st.cv
    r = _Resolver(st)
    out = []
    for i in ids:
        act = cv._act(i) if i.startswith("opr-") else None
        if act is None or act["act"] != "expectation-recorded":
            out.append({"id": i, "error": "not a request" if act
                        else "the record holds no such act"})
            continue
        try:
            out.append(_about(r, act))
        except Exception as exc:                           # noqa: BLE001
            out.append({"id": i, "error": "what this request is about could "
                                          f"not be read ({type(exc).__name__})"})
    return {"about": out, "limit": _read.BATCH, "brain": brain_of(st.corpus)}


def brain_of(corpus) -> dict:
    """WHICH BRAIN ANSWERED, so a page never shows one Brain's answer as another's -- WITHOUT
    WHERE IT IS ON DISK. A Brain's id alone does not tell a restored copy from the Brain it was
    copied from (they share it), so `instance` is a fingerprint of the id and the folder the
    Brain is served from: it differs between a Brain and its copy, and says nothing of the
    folder itself."""
    cid = getattr(corpus, "corpus_id", None)
    root = str(getattr(corpus, "root", "") or "")
    return {"corpus_id": cid,
            "instance": hashlib.sha256(f"{cid}\0{root}".encode("utf-8")).hexdigest()[:16] if cid else None}
