"""Fluid Workspace: its own API under `/fluid/api`, beside production's.

STAGES F0 AND F1 ARE READ-ONLY (F1: a post's Markdown objects, addressed:
`mentis.fluid.objects`), and every route in this module is a GET. F2 WRITES,
in `mentis.fluid.commands` only: a post, and addressing one, through the same
domain-level write operations production uses
(`mentis.conversation.posting`) -- never by calling production's HTTP routes.
Any other POST is refused before anything is read. F4a READS THE HOME AND
WORK (`mentis.fluid.home`: Needs you, Work, Activity, the briefing, For you,
work and runs by id) and keeps ARRANGEMENTS beside the record
(`mentis.fluid.arrangements`, saved through the command door). F5 reads the
stream of every post and a client's selection (`collections/stream`,
`collections/selection`), and what asks the owner in each listed
Conversation. A post's ANNOTATIONS -- its anchors, reactions, anchored
replies and deep dives -- are read by `mentis.fluid.anchored`, and the
toolbar's acts that make them are commands.

MOUNTED BY ONE PREFIX CHECK in the existing handler: a path under `/fluid/api/`
is handed here after the same Host check and `X-Mentis-Client` check every
JSON route has, and before production's `_api` / `_routes` are reached. Every
other path takes exactly the code path it took before.

The read model is `mentis.fluid.read`; this module only maps a request onto
it and says how it went.
"""
from __future__ import annotations

import urllib.parse

from mentis.spine.store import beside_writer_refused, reading_beside_writer

from . import anchored as _annotations
from . import arrangements as _arrangements
from . import home as _home
from . import latest as _latest
from . import objects as _objects
from . import read as _read

PREFIX = "/fluid/api/"


def route(st, path: str, query: dict) -> dict:
    """The answer to one Fluid GET. Raises `read.BadRequest` (400) or
    `read.NotFound` (404)."""
    corpus, cv = st.corpus, st.cv

    def one(name, default=None):
        got = query.get(name)
        return got[0] if got else default

    rest = path[len(PREFIX):].rstrip("/")
    # EACH COLLECTION SAYS THE CHANGE CURSOR IT WAS READ AT, taken BEFORE the
    # read, so a change landing during it is reported again rather than lost.
    at = _read.change_cursor(corpus.advance())
    if rest == "posts":
        out = _read.posts(corpus, _read._ids(one("ids")), cv)
        # F6, ADDITIVE AND ASKED FOR: `&thread=1` adds each post's whole
        # thread -- its count and what This post shows for it -- and
        # changes nothing else in the answer.
        if one("thread") == "1":
            _objects.thread_summaries(corpus, out["posts"])
        return out
    if rest == "conversations":
        if one("ids"):
            return _read.conversations(corpus, cv, _read._ids(one("ids")),
                                       agents=st.agents)
        if one("activity"):
            out = _read.conversation_list(
                corpus, cv, _read._limit(one("limit"), _read.LIST,
                                         _read.LIST_MAX),
                after=one("cursor"), q=one("q"), agents=st.agents)
            return {**out, "key": "conversations", "cursor": at}
        raise _read.BadRequest("ask for ?ids=<id>,<id> or ?activity=1")
    if rest == "collections/conversation":
        if not one("id"):
            raise _read.BadRequest("name the conversation: ?id=<id>")
        out = _read.conversation_collection(
            corpus, one("id"), before=one("before"), after=one("after"),
            limit=_read._limit(one("limit"), _read.PAGE, _read.PAGE_MAX),
            shape=one("shape", "threads"), start=one("from"),
            topic=one("topic") or None)
        return {**out, "cursor": at}
    if rest == "collections/thread":
        if not one("root"):
            raise _read.BadRequest("name the post: ?root=<id>")
        out = _read.thread_collection(
            corpus, one("root"), before=one("before"), after=one("after"),
            limit=_read._limit(one("limit"), _read.PAGE, _read.PAGE_MAX),
            start=one("from"))
        return {**out, "cursor": at}
    if rest == "collections/stream":
        out = _read.stream_collection(
            corpus, before=one("before"), after=one("after"),
            limit=_read._limit(one("limit"), _read.STREAM_PAGE,
                               _read.PAGE_MAX), start=one("from"))
        return {**out, "cursor": at}
    if rest == "collections/selection":
        return {**_read.selection(corpus, _read._ids(one("ids"))),
                "cursor": at}
    if rest == "changes":
        out = _read.changes(corpus, cv, one("since"))
        if one("threads") == "1":
            _read.thread_roots(corpus, out)
        return out
    if rest == "objects":
        # F6, ADDITIVE: many posts' listings in one read (`posts=`), and a
        # post's with its whole thread's (`thread=`); `post=` is unchanged.
        if "conversation" in query:
            if not one("conversation"):
                raise _read.BadRequest(
                    "name the conversation: ?conversation=<id>")
            return {**_objects.conversation_objects(
                corpus, one("conversation"), before=one("before"),
                limit=_read._limit(one("limit"), _read.PAGE,
                                   _read.PAGE_MAX)),
                    "cursor": at}
        if "posts" in query:
            return {**_objects.posts_objects(
                corpus, _read._ids(one("posts"), name="posts")), "cursor": at}
        if "thread" in query:
            if not one("thread"):
                raise _read.BadRequest("name the post: ?thread=<root id>")
            return {**_objects.thread_objects(corpus, one("thread")),
                    "cursor": at}
        if not one("post"):
            raise _read.BadRequest("name the post: ?post=<root id>")
        return {**_objects.post_objects(corpus, one("post"), one("version")),
                "cursor": at}
    # F6, ADDITIVE: a document attachment's words, at most what is drawn.
    if rest == "document":
        if not one("ref"):
            raise _read.BadRequest("name the document: ?ref=<artifact ref>")
        return _objects.document_text(corpus, one("ref"))
    if rest == "participants":
        return _read.participants(cv, q=one("q"),
                                  limit=_read._limit(one("limit"), _read.LIST,
                                                     _read.LIST_MAX))
    # WHAT THE COMPOSER'S USE PANEL READS (F3), from the same functions
    # production's `/api/governed` and `/api/governance/authoring` answer
    # with, so the two doors give the same content.
    if rest == "governed":
        from mentis.conversation.register import governed
        return governed(st.brain, kind=one("kind"), q=one("q"),
                        state=one("state"), limit=one("limit"),
                        cursor=one("cursor"))
    if rest == "governance/authoring":
        from mentis.web.governance_ui import authoring_listing
        return authoring_listing(corpus)
    # HOME AND WORK (F4a, `mentis.fluid.home`): production's Brain Home
    # meaning, in Fluid's shape -- collections of ids, entities by id.
    page = lambda: _read._limit(one("limit"), _home.PAGE,       # noqa: E731
                                _home.PAGE_MAX)
    if rest == "home/needs-you":
        return _home.needs_you(st, before=one("before"), limit=page(), at=at)
    if rest == "home/work":
        # Shared while the record and the runs observed hold still
        # (`foundation.shared_answer`): the page asks this twice as it opens.
        from mentis.conversation.shared_answer import answers_of
        from mentis.web import _runtime_observation
        from mentis.operational import stage as _stage
        args = (one("state", "all"), one("before"), page(), at)
        return answers_of(st).get(
            ("fluid/home/work", args),
            lambda: _home.work_collection(st, state=args[0], before=args[1],
                                          limit=args[2], at=args[3]),
            version=lambda: (None if st.cv.corpus.steady is None else
                             (st.cv.corpus.steady,
                              repr(_runtime_observation(st)),
                              _stage.answer_version(st))))
    if rest == "home/activity":
        return _home.activity(st, limit=page(), at=at)
    if rest == "home/briefing":
        return _home.briefing(st, period=one("period"), day=one("date"),
                              limit=page(), at=at)
    if rest == "home/for-you":
        return _home.for_you(st, before=one("before"), limit=page(), at=at)
    # #576, ADDITIVE: what on one post or its thread needs the owner, and
    # those requests by id -- Needs you's rule, scoped to a post.
    # P11: what asks the owner, one item per form, as the bell counts it.
    if rest == "needs-you/items":
        return _home.needs_you_items(st, at=at)
    if rest == "needs-you":
        if one("ids"):
            return _home.asks(st, _read._ids(one("ids")))
        if not one("post"):
            raise _read.BadRequest("name the post: ?post=<id>, or ?ids=")
        return _home.needs_you_on(st, one("post"), at=at)
    # ANNOTATIONS, ADDITIVE (`mentis.fluid.anchored`): a post's anchors
    # as production's turn read draws them, with each one's reaction history.
    if rest.startswith("posts/") and rest.endswith("/anchors") \
            and rest.count("/") == 2:
        return {**_annotations.of_post(cv, rest.split("/")[1]), "cursor": at}
    if rest == "anchors":
        return {**_annotations.of_posts(
            cv, _read._ids(one("posts"), name="posts")), "cursor": at}
    # WHAT IS FILLED IN (forms build P3, `mentis.conversation.responses`):
    # a post's sets, one set as it stands -- answers, own words and
    # interpretations -- a field's or the own words' history, and the
    # accounting of the own words.
    if rest == "response-sets" or rest.startswith("response-sets/"):
        return response_sets(st, rest, one, at)
    # DECISIONS, DRAWN AS ONE FORM IN EVERY VIEW (forms build P9): every
    # ask on a post, or these asks by id (a form on no post yet).
    if rest == "decisions":
        from mentis.web import decisions_read
        if one("ids"):
            return {**decisions_read(st, ids=_read._ids(one("ids"))),
                    "cursor": at}
        if not one("post"):
            raise _read.BadRequest("name the post: ?post=<id>, or ?ids=")
        got = decisions_read(st, post=one("post"))
        if got is None:
            raise _read.NotFound(one("post"))
        return {**got, "cursor": at}
    if rest == "latest":
        # The newest posts, replies included, each with its thread's top
        # (`mentis.fluid.latest`): what Fluid's Latest opens.
        # Agent work is left out unless `?agent_work=1` asks for it.
        return {**_latest.latest(
            corpus, conversation=one("conversation") or None,
            limit=_read._limit(one("limit"), _latest.LIMIT,
                               _latest.LIMIT_MAX), cv=cv,
            agent_work=(one("agent_work") or "") in ("1", "true", "yes")),
            "cursor": at}
    if rest == "work":
        return _home.work(st, _read._ids(one("ids")))
    if rest == "runs":
        return _home.runs(st, _read._ids(one("ids")))
    if rest.startswith("arrangements/"):
        return arrangement_of(st, rest[len("arrangements/"):])
    if rest == "layouts":
        return _arrangements.layouts(st.corpus.root)
    if rest.startswith("objects/"):
        # ONE PERCENT-ENCODED SEGMENT: the key in it holds `/` and spaces.
        address = urllib.parse.unquote(rest[len("objects/"):])
        return {**_objects.one_object(corpus, address, one("format", "json")),
                "cursor": at}
    raise _read.NotFound(path)


def response_sets(st, rest, one, at) -> dict:
    """`GET /fluid/api/response-sets?post=<id>`, `.../<id>`,
    `.../<id>/history?field=<id>` (or `?words=1`), `.../<id>/accounting`.
    A set the record does not hold is 404, saying so.

    THE POST'S LIST ALSO SAYS WHAT THE SCREEN DRAWS AROUND IT (P5a): `you`,
    the owner these routes act as, so a value somebody else set can be told
    apart; the post's `author`, whom Send back hands to; and on each set
    `awaited`, whether work declared it waits for it (`request_input`), so
    a ready set can say it was handed to that agent."""
    from mentis.conversation import responses
    from mentis.conversation.versions import Refused
    cv = st.cv
    bits = rest.split("/")
    try:
        if len(bits) == 1:
            from mentis.conversation.owner import _owner
            from mentis.web.inputs import waits_for
            if not one("post"):
                raise _read.BadRequest("name the post: ?post=<id>")
            sets = responses.sets_on(cv, one("post"))
            root = responses.post_root(cv.corpus, one("post"))
            author = cv.corpus.read([root])[0].get("attributed_to")
            return {"post": root, "you": _owner(cv), "author": author,
                    "author_alias": cv.alias(author) if author else None,
                    "sets": [{**responses.state(cv, s["id"]),
                              "awaited": bool(waits_for(cv, s["id"]))}
                             for s in sets],
                    "cursor": at}
        sid, tail = bits[1], "/".join(bits[2:])
        if tail == "":
            return {**responses.state(cv, sid), "cursor": at}
        if tail == "history":
            if one("words") == "1":
                return {"set": sid, "words": responses.words_history(
                    cv, sid, by=one("by")), "cursor": at}
            if not one("field"):
                raise _read.BadRequest("name the field: ?field=<id>, or "
                                       "?words=1 for the own words")
            return {"set": sid, "field": one("field"),
                    "history": responses.field_history(cv, sid, one("field")),
                    "cursor": at}
        if tail == "accounting":
            return {**responses.accounting(cv, sid), "cursor": at}
    except Refused as refused:
        raise _objects.Unresolved(sid if len(bits) > 1 else one("post"),
                                  refused.refusal.get("error"))
    except (IndexError, KeyError):
        raise _objects.Unresolved(one("post"), "the record holds no such post")
    raise _read.NotFound(rest)


def arrangement_key(st, key: str) -> str:
    """`home`, or a Conversation the record holds under its own id -- not a
    rename's later version, which is that Conversation. Raises BadRequest."""
    try:
        _arrangements.check_key(key)
    except _arrangements.Refused as exc:
        raise _read.BadRequest(str(exc))
    if key == _arrangements.HOME:
        return key
    got = st.corpus.read([key])
    if not got or not _read._is_conversation(got[0]) \
            or _read._later_versions(st.corpus, [key]):
        raise _read.BadRequest(f"not a conversation: {key!r}; an "
                               "arrangement is the Home's or a "
                               "Conversation's")
    return key


def arrangement_of(st, key: str) -> dict:
    """`GET /fluid/api/arrangements/<key>`."""
    key = arrangement_key(st, key)
    try:
        return _arrangements.arrangement(st.corpus.root, key)
    except _arrangements.Refused as exc:
        raise _read.BadRequest(str(exc))


def handle_get(handler, parsed) -> None:
    """Answer one GET under `/fluid/api/` on the production handler.

    READ BESIDE THE WRITER, as production GETs are (`_Handler._api`): nothing
    here writes, and if anything inside were refused a write the answer is
    void and read again outside the scope, every read under the lock."""
    from mentis.worker import CAPABILITY_HEADER
    # A DOCUMENT'S WORDS ARE A FILE'S CONTENTS: every answer on that route --
    # refusals included -- carries the artifact routes' serving protections
    # (nosniff, sandbox CSP, CORP same-origin, no referrer).
    send = (handler._artifact_send
            if parsed.path[len(PREFIX):].rstrip("/") == "document"
            else handler._send)
    if handler.headers.get(CAPABILITY_HEADER):
        return send(403, {"error": "a worker grant authorises "
                                            "/api/worker and nothing else",
                                   "kind": "PermissionError",
                                   "asked_for": parsed.path})
    st = handler.state
    query = urllib.parse.parse_qs(parsed.query)
    # F6's `objects?posts=` and `?thread=` asked EMPTY are questions about
    # them, and are answered so -- not as a missing `?post=`.
    if parsed.path.rstrip("/").endswith("/objects"):
        blank = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        for name in ("posts", "thread"):
            if name in blank and name not in query:
                query[name] = [""]
    try:
        try:
            with reading_beside_writer(), st.cv.reading():
                result = route(st, parsed.path, query)
        except (_read.BadRequest, _read.NotFound, _objects.Unresolved):
            raise
        except Exception:                                 # noqa: BLE001
            if not beside_writer_refused():
                raise
        if beside_writer_refused():
            with st.cv.reading():
                result = route(st, parsed.path, query)
    except _read.BadRequest as exc:
        return send(400, {"error": str(exc), "kind": "BadRequest"})
    except _read.NotFound:
        return send(404, {"error": "no such Fluid surface",
                          "path": parsed.path})
    except _objects.Unresolved as exc:
        return send(404, exc.payload)
    except Exception as exc:                              # noqa: BLE001
        return send(500, {"error": str(exc),
                          "kind": type(exc).__name__})
    return send(200, result)
