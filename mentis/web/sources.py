"""The `/api/sources` routes: Manage Sources, for the owner (Sources slice 1).

OWNER-SIDE ONLY. `_api` refuses a worker grant on every route but
`/api/worker`, so no dispatched run reaches these; a worker keeps the source
READS through its grant (`mentis.worker.SOURCE_READS`), which read the record
and never a bound folder. `search` is the owner's side of one of them,
`search_sources` (Sources A).

WHO WROTE IT IS WHAT THE SERVER OBSERVED (Sources B, follow-up of
opr-b234b23b6ba5). Every route that writes -- declare, revise-scope, sweep,
and the machine-local bind -- and every run it starts records
`_observed_writer` of the request: the grant it presented, or
`unattributed-local-request` when it presented none, which is what an owner's
browser presents. It used to record the constant `filesystem-connector`,
which said which code wrote it and nothing about who asked. A request that
presents a worker grant is refused here as well as by `_api`, as on
`/api/artifacts`: these are the owner's routes.

RECORDED AS THE OWNER'S OWN ACTS, and asked of nobody else. Declaring,
revising a scope and sweeping are written with `actor` = the Participant
named in `by`, the way every other owner act on this server is -- and,
confirmed by the owner (B4), with no separate Governance ask: these are
explicit manual owner source actions. Binding, unbinding, planning, the
folder chooser and showing a live file record nothing at all.

NO ROUTE HERE SERVES BYTES THAT ARE NOT HELD (G3). Pages are read from the
held store; links are statuses from the record; `reveal` opens Explorer on
this machine and returns no bytes and no path. Rendering unacquired targets
live is Slice 2 and is not built.

LONG WORK RUNS IN THE BACKGROUND (`mentis.sources.runs`): `plan` and
`sweep` start a run and answer at once; `/api/sources/<key>/run` says how far
it has got, and `/run/cancel` stops it before its transaction opens.
"""

from __future__ import annotations

import uuid

import mentis.api as api
from mentis.sources import Refused, runs, canonical
from mentis.sources import reading

PREFIX = "/api/sources"


def _src(st):
    return api.sources(st.corpus)


def _refusal(exc) -> dict:
    return {"error": str(exc), "kind": type(exc).__name__, "refused": True}


def _by(st, body):
    from mentis.web import _attributed
    return _attributed(body or {}, "by", corpus=st.corpus)


def _row(st, d: dict) -> dict:
    """A collection as the overview lists it: the record, plus this
    machine's binding state (never the path).

    `d` is the collection's declaration. Its history is read ONCE here and
    handed to every consumer -- the overview, the extraction progress --
    which used to read it again each (opr-1f9237698d13). Read per request,
    never kept between them, so the row is as fresh as it was."""
    src = _src(st)
    lat = reading._latest(st.corpus, d)
    view = reading.overview(st.corpus, d["collection"], decl=d, lat=lat)
    try:
        bnd = src.binding_state(d["collection"])
    except Refused as exc:
        bnd = {"bound": False, "binding": None, "state": str(exc)}
    swept = view["last_sweep"] is not None
    state = ("not bound on this machine" if not bnd["bound"]
             else "acquired · not refreshing" if swept
             else "declared · nothing acquired yet")
    from mentis.sources.extract import engine
    return {**view, "binding": bnd, "state": state,
            "run": runs.get(st.corpus, d["collection"]),
            "extraction": engine.progress(st.corpus, lat.values())}


#: WHAT EACH BODY FIELD MAY BE, checked before anything uses one. A `draft`
#: sent as an object to `/sweep` was used as a run key and raised TypeError
#: out of the route (review note 8): a malformed body is the caller's
#: mistake, and is answered as a refusal that names the field.
_TEXT = ("collection", "plan", "within", "because", "name", "connector",
         "root", "remote", "object", "decision_plan", "folder", "table", "mode", "purpose", "start")
_PATTERNS = ("include", "exclude")


def _malformed(bits, body) -> str | None:
    """Why this POST body cannot be acted on, or None."""
    if not isinstance(body, dict):
        return "the request body must be a JSON object"

    def patterns(where, v):
        if v is not None and not (isinstance(v, list)
                                  and all(isinstance(p, str) for p in v)):
            return f"`{where}` must be a list of text patterns"
        return None

    def options(where, v):
        # A CONNECTOR'S OWN SCOPE FIELDS (a Git ref, a commit window): an
        # object of text or whole numbers. Which names a connector has is
        # its own to say (`registry._options`); only the shape is checked here.
        if v is None:
            return None
        if not isinstance(v, dict) or not all(
                isinstance(k, str) and (x is None or isinstance(x, str) or
                    (isinstance(x, (dict, list)) and len(canonical(x).encode("utf-8")) <= 65536) or (
                    isinstance(x, int) and not isinstance(x, bool)))
                for k, x in v.items()):
            return f"`{where}` must be an object of text or whole numbers"
        return None

    def fields(where, d, text):
        for k in text:
            v = d.get(k)
            if v is not None and not isinstance(v, str):
                return f"`{where}{k}` must be text"
        for k in _PATTERNS:
            why = patterns(where + k, d.get(k))
            if why:
                return why
        return options(where + "options", d.get("options"))

    why = fields("", body, _TEXT)
    if why:
        return why
    draft = body.get("draft")
    if bits == ["plan"]:
        if draft is not None and not isinstance(draft, dict):
            return "`draft` must be an object naming the folder to preview"
        if isinstance(draft, dict):
            why = fields("draft.", draft,
                         ("connector", "name", "root", "remote", "decision_plan"))
            if why:
                return why
        scope = body.get("scope")
        if scope is not None:
            if not isinstance(scope, dict):
                return "`scope` must be an object with `include` and `exclude`"
            why = fields("scope.", scope, ())
            if why:
                return why
    elif draft is not None and not isinstance(draft, str):
        return "`draft` must be the draft's reference, as text"
    return None


def _number(one, key, default=0):
    """A query argument that must be a whole number, or a refusal naming
    it -- never a generic error (review nit, opr-b234b23b6ba5)."""
    raw = one(key, default)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise Refused(f"`{key}` must be a whole number, not {raw!r}") \
            from None


def _start(st, key, kind, work, wait, wrote=None):
    view = runs.start(st.corpus, key, kind, work, started_by=wrote)
    if wait:
        view = runs.wait(st.corpus, key, timeout=600) or view
    return view


def routes(st, path, query, body, method, presented=None, *, peer=None):
    """None when the path is not Sources'."""
    if path != PREFIX and not path.startswith(PREFIX + "/"):
        return None
    one = lambda k, d=None: (query.get(k) or [d])[0]        # noqa: E731
    if presented:
        raise PermissionError("a worker grant authorises /api/worker and "
                              "nothing else; the source reads are its own")
    try:
        return _routes(st, path, one, {} if body is None else body, method,
                       presented, peer=peer)
    except Refused as exc:
        return _refusal(exc)


def _routes(st, path, one, body, method, presented=None, *, peer=None):
    from mentis.sources import picker
    from mentis.web import _observed_writer
    src = _src(st)
    wrote = _observed_writer(st, presented)
    corpus = st.corpus
    tail = path[len(PREFIX):].strip("/")
    bits = tail.split("/") if tail else []

    # ---- reads -------------------------------------------------------------
    if method == "GET" and not bits:
        return {"collections": [_row(st, d) for d in
                                reading.declarations(corpus)],
                "descriptors": src.descriptors(),
                "picker": picker.available(st, peer),
                "note": "acquired material held in this Brain: past "
                        "observations, usable from every Conversation, not "
                        "the live sources"}

    if method == "GET" and bits == ["folders"]:
        # THE FOLDER CHOOSER: a local read of this machine, never recorded.
        return src.folders(one("path"))

    if method == "GET" and bits == ["compare"]:
        return src.compare(one("a"), one("b"))

    if method == "GET" and bits == ["search"]:
        # WHERE A PHRASE OCCURS INSIDE ACQUIRED TEXT (Sources A, A2): the
        # scan `search_sources` gives a worker, for the owner's page. Reads
        # the record and the held store; writes nothing, reads no folder.
        return src.search(one("q"), collection=one("collection") or None,
                          offset=_number(one, "offset"),
                          limit=_number(one, "limit", 0) or None,
                          continuation=one("continuation") or None)

    if method == "GET" and bits == ["provenance"]:
        return src.provenance(one("ref"))

    if method == "GET" and bits == ["page"]:
        # ONE PAGE OF ONE OBSERVATION'S HELD BYTES, by its reference -- or,
        # with `extraction`, one window of that exact extraction of it, in
        # code points (Sources C, C3), under the same reach.
        return src.read(ref=one("ref"), offset=_number(one, "offset"),
                        extraction=one("extraction") or None)

    if method == "GET" and bits == ["cite"]:
        # WHETHER A CITATION OF A SOURCE STILL SAYS WHAT IT SAID (Sources C,
        # C4), for the chip on a cite in a Turn: verified, or not
        # reproducible here with what the cite and the Turn carry. Returns
        # no more of a representation than the cited span itself. A hover
        # never builds an extraction while it waits: a missing one is
        # started in the background and the answer is `pending`.
        from mentis.sources.extract import verify
        return verify.verify(corpus, one("cite") or "",
                             quote=one("quote") or None, make=False)

    if method == "GET" and bits == ["rendered"]:
        # ONE STORED NOTE, WHOLE, WITH ITS EMBEDS RESOLVED FROM THE RECORD
        # (Sources B, B3). Reads the held store; writes nothing.
        return reading.rendered(corpus, one("ref") or "")

    if method == "GET" and bits == ["record"]:
        return reading.record(corpus, one("ref") or "")

    if method == "GET" and len(bits) == 2 and bits[1] == "run":
        return {"run": runs.get(corpus, bits[0])}

    if method == "GET" and len(bits) == 1:
        c = reading._collection(corpus, bits[0])
        return _row(st, c)

    if method == "GET" and len(bits) == 2:
        col, what = bits
        if what == "objects":
            return src.objects(col, q=one("q"), state=one("state", "present")
                               or None, offset=_number(one, "offset"),
                               limit=_number(one, "limit", reading.LIST)
                               or reading.LIST,
                               prefix=one("prefix"))
        if what == "history":
            return src.history(col, one("key") or "")
        if what == "links":
            return src.links(col, one("key") or "", ref=one("ref"))
        if what == "page":
            ref = one("ref")
            return src.read(ref=ref, collection=None if ref else col,
                            path=None if ref else one("key"),
                            offset=_number(one, "offset"))
        return None

    if method != "POST":
        return None
    why = _malformed(bits, body)
    if why:
        raise Refused(why)

    if bits == ["sqlite", "inspect"]:
        if not body.get("root") and not body.get("collection"):
            raise Refused("`root` or `collection` must name a database file")
        return _start(st, "new-"+uuid.uuid4().hex[:12], "inspect",
                      lambda run: src.sqlite_inspect(body.get("root"), **({"collection": body["collection"]} if body.get("collection") else {}), progress=run), bool(body.get("wait")), wrote)
    if bits == ["sqlite", "find"]:
        if not body.get("folder"):
            raise Refused("`folder` must name a folder")
        return src.sqlite_find(body["folder"])
    if bits == ["sqlite", "sample"]:
        if not body.get("plan") or not body.get("table"):
            raise Refused("`plan` and `table` must be text")
        return src.sqlite_sample(body["plan"], body["table"], body.get("rules"))
    if bits == ["pick"]:
        status = picker.available(st, peer)
        if not status["available"]:
            raise Refused(status["why_not"])
        return picker.start(st, body, wait=bool(body.get("wait")), wrote=wrote)

    # ---- this machine: nothing recorded ----------------------------------
    if bits == ["bind"]:
        # A FOLDER ON THIS MACHINE, OR AN ADDRESS (a connector that declares
        # `address` among its locations): either way nothing is recorded.
        return src.bind(body.get("collection"), body.get("root"),
                        written_by=wrote, remote=body.get("remote"))

    if bits == ["unbind"]:
        return src.unbind(body.get("collection"), written_by=wrote)

    if len(bits) == 2 and bits[1] == "reveal":
        return src.reveal(bits[0], body.get("object"))

    if len(bits) == 3 and bits[1:] == ["run", "cancel"]:
        return runs.cancel(corpus, bits[0])

    # ---- previews: background, nothing recorded --------------------------
    if bits == ["plan"]:
        wait = bool(body.get("wait"))
        draft = body.get("draft")
        if isinstance(draft, dict):
            src.check_options(draft.get("connector") or "filesystem", draft.get("options"))
            key = f"new-{uuid.uuid4().hex[:12]}"
            return _start(st, key, "preview", lambda run: src.preview_new(
                connector=draft.get("connector") or "filesystem",
                name=draft.get("name"), root=draft.get("root"),
                remote=draft.get("remote"),
                include=draft.get("include"), exclude=draft.get("exclude"),
                options=draft.get("options"), sensitive_decisions=draft.get("sensitive_decisions"),
                category_decisions=draft.get("category_decisions"), decision_plan=draft.get("decision_plan"), progress=run), wait, wrote)
        col = body.get("collection")
        reading._collection(corpus, col or "")
        scope = body.get("scope")
        # Refused here, at once, rather than as a run that fails (F4).
        src._scope_options(col, scope)
        return _start(st, col, "plan", lambda run: src.plan(
            col, within=body.get("within"), scope=scope, sensitive_decisions=body.get("sensitive_decisions"),
            category_decisions=body.get("category_decisions"), decision_plan=body.get("decision_plan"), progress=run), wait,
            wrote)

    # ---- owner acts: recorded, actor = the owner, no Governance ask ---------
    by, unattributed = _by(st, body)
    if unattributed:
        return unattributed

    if bits == ["declare"]:
        return src.declare(body.get("name"),
                           connector=body.get("connector") or "filesystem",
                           include=body.get("include"),
                           exclude=body.get("exclude"),
                           options=body.get("options"), declarer=by,
                           written_by=wrote)

    if bits == ["revise-scope"]:
        col = body.get("collection")
        scope = {"include": body.get("include"), "exclude": body.get("exclude")}
        if body.get("options") is not None:
            scope["options"] = body["options"]
        if body.get("plan"):
            # REVISE AND SWEEP, one transaction: the revision act exists only
            # if the previewed plan is still what would be recorded.
            src._scope_options(col, scope)
            return _start(st, col, "sweep", lambda run: src.sweep(
                col, body["plan"], scope=scope, because=body.get("because"),
                sensitive_decisions=body.get("sensitive_decisions"),
                category_decisions=body.get("category_decisions"),
                acknowledge_binding_change=bool(
                    body.get("acknowledge_binding_change")),
                actor=by, progress=run, written_by=wrote),
                bool(body.get("wait")), wrote)
        return src.revise_scope(col, include=scope["include"],
                                exclude=scope["exclude"], by=by,
                                because=body.get("because"),
                                written_by=wrote,
                                options=scope.get("options"))

    if bits == ["sweep"]:
        wait = bool(body.get("wait"))
        if body.get("draft"):
            draft = body["draft"]
            return _start(st, draft, "sweep", lambda run: src.acquire_new(
                draft, body.get("plan"), actor=by, progress=run,
                written_by=wrote), wait, wrote)
        col = body.get("collection")
        reading._collection(corpus, col or "")
        return _start(st, col, "sweep", lambda run: src.sweep(
            col, body.get("plan"), within=body.get("within"),
            sensitive_decisions=body.get("sensitive_decisions"),
            category_decisions=body.get("category_decisions"),
            acknowledge_binding_change=bool(
                body.get("acknowledge_binding_change")),
            actor=by, progress=run, written_by=wrote), wait, wrote)

    return None

