"""Fluid's commands (stage F2): writing a post, and addressing one.

THE SAME OPERATIONS PRODUCTION USES. A post is written by
`mentis.conversation.posting.post` and an existing post is addressed by
`posting.address` -- the functions production's turns and address routes call
-- so what is recorded, owed, refused and dispatched is identical whichever
door it came through. Nothing here calls production's HTTP routes, and nothing
here adds a rule of its own to what the operation decides. What this door adds
is only what a door is for: where the post goes is named in the body
(`conversation`), and the answer is shaped for the Fluid store -- the new
post's id, its home and number, the expectations it created, and the change
cursor after it committed.

THE ONE THING THE BODY MUST CARRY THAT PRODUCTION PUTS IN ITS PATH is the
conversation. Everything else is production's body, field for field: `parts`
(text, references, and attachments staged through `/api/artifacts`),
`addressed_to`, `action`, `dispatch`, `topics`, `governed` (Use...),
`replies_to`, `requires`, `because`, `chose` and `op`.

A REPLY IS WRITTEN INTO THE CONVERSATION THE COMPOSER IS IN, wherever its
parent lives: `say` already allows that, and since F3 an anchored reply may be
said in any Conversation its Turn is in -- its home, or one it is included in
now (`anchors.check_parts`).

F3: MEMBERSHIP AND NAMING, through the domain's own operations
(`Conversations.open_conversation`, `rename_conversation`, `include`,
`group`), which production's readers read back:

  POST /fluid/api/conversations              open one; no name: provisional
  POST /fluid/api/conversations/<id>/name    rename it
  POST /fluid/api/conversations/<id>/members include posts, end inclusions
  POST /fluid/api/conversations/group        open one holding these posts

F4a: ARRANGEMENTS, beside the record and never in it
(`mentis.fluid.arrangements`):

  POST /fluid/api/arrangements/<key>         keep the Home's or a
                                             Conversation's layout
  POST /fluid/api/layouts                    keep a named layout
  POST /fluid/api/layouts/<id>/delete        delete one
  POST /fluid/api/layouts/defaults           a place kind's default
  POST /fluid/api/settings                   the brain-wide settings
                                             (`mentis.fluid.settings`)

THE UNIVERSAL MAGNET'S CONFIGURATIONS (Surface Tension P2), the only writers
of an arrangement's `magnets` (`mentis.fluid.arrangements`):

  POST /fluid/api/arrangements/<key>/magnets                    magnet.create
  POST /fluid/api/arrangements/<key>/magnets/<id>/reconfigure   magnet.reconfigure
  POST /fluid/api/arrangements/<key>/magnets/<id>/remove
                                             magnet.removeIfUnreferenced

A Magnet declined by the arrangement as it stands (a missing config, a zone
still showing it, the bound) is 422 with its `reason`
({code, message, retryable}).

THE TOOLBAR'S ACTS ON A POST, through the operations Classic's toolbar
reaches (see "the toolbar's acts on a post" below):

  POST /fluid/api/posts/<id>/reactions       react, to it or a passage
  POST /fluid/api/posts/<id>/comments        an anchored reply
  POST /fluid/api/posts/<id>/deep-dives      open a deep dive from it
  POST /fluid/api/posts/<id>/edit            its next version
  POST /fluid/api/posts/<id>/delete          production's Delete
  POST /fluid/api/posts/<id>/topics          file it under a Topic
  POST /fluid/api/posts/<id>/unfile          end a filing
  POST /fluid/api/posts/<id>/move            file it under one Topic only
  POST /fluid/api/reactions/<id>/withdraw    the reactor's own Delete

A FILLED-IN BLOCK'S TWO HAND-OVERS (forms build P4, `mentis.web.inputs`):

  POST /fluid/api/response-sets/<id>/ready      Done: mark it ready, and
                                                resume work that declared it
                                                waits for it
  POST /fluid/api/response-sets/<id>/send-back  hand its answers to the
                                                post's author, to act on now

SAVING WHAT IS FILLED IN (forms build P3, `mentis.conversation.responses`):

  POST /fluid/api/response-sets                 open a block's set {post,
                                                block, part?, mode?}
  POST /fluid/api/response-sets/<id>/answers    answer a field {field, value,
                                                replaces?, note?,
                                                conversation?}
  POST /fluid/api/response-sets/<id>/own-words  keep own words {text,
                                                replaces?, conversation?}
  POST /fluid/api/response-sets/<id>/show       show the same answers in
                                                another Conversation
                                                {conversation}
  POST /fluid/api/response-sets/<id>/start-new  start new answers from the
                                                form {copy?, conversation?}
  POST /fluid/api/response-sets/<id>/move       move answers to the form's
                                                current version {confirm?}
  POST /fluid/api/interpretations/<id>/confirm  {replaces?: the field's
                                                answers the owner saw;
                                                refused with the current
                                                ones if they changed}
  POST /fluid/api/interpretations/<id>/change   {value | changed_to,
                                                replaces?}
  POST /fluid/api/interpretations/<id>/decline  {reason?}

THESE ROUTES ACT AS THE BRAIN'S OWNER, and nobody else. They are the
screen's, and the screen is the owner's: every write above, Done and Send
back included, is recorded as by the owner, and any `author` in the body is
ignored -- a body cannot name who it is by, since this server has no session
to check it against (the wider HTTP authentication problem is recorded as
opr-baf53d5e8b50). Refused (422) where the record names no owner. An agent
fills in, proposes and hands over through its MCP tools (`answer`,
`mentis.worker`), which carry its own identity. Each REQUIRES `op`, the
client's operation key: a save the screen may retry has to be one occurrence
however often it is sent. Each is checked by the response model's own rules
(the block's fill rules, a deleted source, who may write), with the Brain's
owner given to them.

ANSWERED IN HTTP TERMS, where production answers everything 200: a refusal is
422 with the operation's own words (`refused: true` beside them), a malformed
request 400. A replayed operation key is 200 with `replayed: true`, and writes
nothing again.
"""
from __future__ import annotations

import json

from mentis.conversation import posting

from . import read as _read

#: The commands this door answers. Any other POST under /fluid/api is 405.
POSTS = "posts"
ADDRESS = "address"
CONVERSATIONS = "conversations"
NAME = "name"
MEMBERS = "members"
GROUP = "group"
ARRANGEMENTS = "arrangements"
LAYOUTS = "layouts"
DEFAULTS = "defaults"
DELETE = "delete"
SETTINGS = "settings"
MAGNET_CREATE = "magnet-create"
#: `arrangements/<key>/magnets/<id>/<verb>`, by the command each is.
MAGNET_ACTS = {"reconfigure": "magnet-reconfigure",
               "remove": "magnet-remove"}
REACTIONS = "reactions"
WITHDRAW = "withdraw"
RESPONSE_SETS = "response-sets"
INTERPRETATIONS = "interpretations"
#: `work/<request>/workflow`: the owner changes the Workflow a request is
#: governed by (`workflow_change`).
WORK = "work"
WORKFLOW_CHANGE = "work-workflow"
SET_OPEN = "set-open"
#: A response set's acts, `response-sets/<id>/<verb>`.
SET_ACTS = {"ready": "set-ready", "send-back": "set-send-back",
            "answers": "set-answer", "own-words": "set-words",
            "show": "set-show", "start-new": "set-start", "move": "set-move"}
#: What the person whose words they are does with an interpretation.
INTERPRETATION_ACTS = {"confirm": "interpretation-confirm",
                       "change": "interpretation-change",
                       "decline": "interpretation-decline"}
#: The toolbar's acts on a post, `posts/<id>/<verb>`, by the command each is.
POST_ACTS = {"reactions": "post-react", "comments": "post-comment",
             "deep-dives": "post-deep-dive", "edit": "post-edit",
             "delete": "post-delete", "topics": "post-topics",
             "unfile": "post-unfile", "move": "post-move"}


def command_of(rest: str) -> tuple[str, str | None] | None:
    """Which command a path under /fluid/api/ names, or None."""
    if rest in (POSTS, CONVERSATIONS, LAYOUTS, SETTINGS):
        return rest, None
    if rest == RESPONSE_SETS:
        return SET_OPEN, None
    head, _, tail = rest.partition("/")
    tid, _, verb = tail.partition("/")
    if head == POSTS and tid and verb in POST_ACTS:
        return POST_ACTS[verb], tid
    if head == RESPONSE_SETS and tid and verb in SET_ACTS:
        return SET_ACTS[verb], tid
    if head == INTERPRETATIONS and tid and verb in INTERPRETATION_ACTS:
        return INTERPRETATION_ACTS[verb], tid
    if head == REACTIONS and tid and verb == WITHDRAW:
        return WITHDRAW, tid
    if head == WORK and tid and verb == "workflow":
        return WORKFLOW_CHANGE, tid
    if head == ARRANGEMENTS and tid and not verb:
        return ARRANGEMENTS, tid
    if head == ARRANGEMENTS and tid and verb == "magnets":
        return MAGNET_CREATE, tid
    parts = verb.split("/")
    if head == ARRANGEMENTS and tid and len(parts) == 3 \
            and parts[0] == "magnets" and parts[1] and parts[2] in MAGNET_ACTS:
        return MAGNET_ACTS[parts[2]], f"{tid}/{parts[1]}"
    if head == LAYOUTS and tid == DEFAULTS and not verb:
        return DEFAULTS, None
    if head == LAYOUTS and tid and verb == DELETE:
        return DELETE, tid
    if head == POSTS and tid and verb == ADDRESS and "/" not in tid:
        return ADDRESS, tid
    if head == CONVERSATIONS and tid == GROUP and not verb:
        return GROUP, None
    if head == CONVERSATIONS and tid and verb in (NAME, MEMBERS) \
            and "/" not in verb:
        return verb, tid
    return None


def write_post(st, body: dict, *, written_by) -> tuple[int, dict, list]:
    """Write a post into the conversation the body names, through the shared
    operation. Returns (status, answer, dispatches to start)."""
    cv, corpus = st.cv, st.corpus
    cid = body.get("conversation")
    if not isinstance(cid, str) or not cid.strip():
        return 400, {"error": "name the conversation this post is written "
                              "into: \"conversation\": \"<id>\"",
                     "kind": "BadRequest"}, []
    if not corpus.read([cid]) or not cv._is_kind(cid, "conversation"):
        return 400, {"error": f"{cid} is not a conversation in this record",
                     "kind": "BadRequest", "conversation": cid}, []
    # A rename's version is not a conversation of its own: refused, naming
    # the one it is a version of, as every conversation door refuses it.
    refusal = cv.version_refusal(cid)
    if refusal:
        return 422, {**refusal, "refused": True}, []
    author = body.get("author")
    if not isinstance(author, str) or not author.strip():
        return 400, {"error": "this writes to the record, so it needs to say "
                              "who it is by: name the Participant in "
                              "\"author\"", "kind": "BadRequest"}, []
    operation = {k: v for k, v in body.items() if k != "conversation"}
    out, later = posting.post(cv, corpus, cid, operation, agents=st.agents,
                              written_by=written_by)
    if "error" in out:
        return 422, {**out, "refused": True}, []
    return 200, _posted(st, cid, out), later


def _posted(st, cid, out) -> dict:
    """What the Fluid store needs of a written post, and the operation's own
    answer whole beside it."""
    corpus = st.corpus
    return {
        "post": out.get("turn"),
        "home": cid,
        "home_name": st.cv.conversation_name(cid),
        "number": out.get("number"),
        "action": out.get("action"),
        "expectations": list(out.get("expectations") or []),
        "dispatched": out.get("dispatched", 0),
        "replayed": bool(out.get("replayed")),
        # AFTER THE COMMIT: a change feed read from here on has seen this
        # post, so the store knows when it has caught up with its own write.
        "cursor": _read.change_cursor(corpus.advance()),
        "operation": out,
    }


def address_post(st, tid: str, body: dict) -> tuple[int, dict, list]:
    """Address an existing post through the shared operation."""
    from mentis.web import _attributed
    by, refusal = _attributed(body, "by", corpus=st.corpus)
    if refusal:
        return 422, {**refusal, "refused": True}, []
    out, later = posting.address(st.cv, st.corpus, tid, body, by=by,
                                 agents=st.agents)
    if "error" in out:
        return 422, {**out, "refused": True}, []
    return 200, {**out, "post": tid,
                 "cursor": _read.change_cursor(st.corpus.advance())}, later


# -- the toolbar's acts on a post ---------------------------------------------
#
# React, comment and deep dive are made on an ANCHOR -- the whole version, or
# a passage of one of its text parts -- found or created from the gesture, as
# Classic's toolbar does (`ui/src/surfaces/Interact.tsx`): production's
# `anchors.create_anchor`, then `anchors.react`, an anchored reply through
# `posting.post`, or `anchors.deep_dive`. The two steps are ONE TRANSACTION
# here, so a refused reaction, comment or dive leaves no anchor behind
# (Classic's two requests leave the anchor, which asserts nothing).
#
# Edit and delete are `versions.edit` and `versions.delete`, with what
# production's `/api/entries/<id>/edit` and `/delete` ask first. Filing is
# production's `/api/turns/<id>/topics`, `/unfile` and `/move`: that
# composition lives in the route branch itself and nowhere else, so the
# command hands the same body to the same branch in-process
# (`web._routes`) rather than copy it -- its refusals, records and answer are
# the route's own.
#
# EACH BODY IS PRODUCTION'S, FIELD FOR FIELD, including who it is by:
# `author` for the anchored acts, `attributed_to` for edit and delete, `by`
# for filing. What a command adds is only where it is aimed (the post in its
# path, and `passage` or `version` for the place in it) and the change cursor
# after the commit.

class _Undone(Exception):
    """Raised inside a transaction to end it writing nothing, carrying the
    answer the refusal is."""

    def __init__(self, answer):
        super().__init__("undone")
        self.answer = answer


def _not_a_post(tid):
    return 404, {"error": f"{tid} is not a post in this record",
                 "kind": "NotFound", "post": tid}, []


def _refused(out) -> tuple[int, dict, list]:
    return 422, {**out, "refused": True}, []


def _done(st, out, **more) -> tuple[int, dict, list]:
    return 200, {**out, **more,
                 "cursor": _read.change_cursor(st.corpus.advance())}, []


def _the_post(st, tid):
    from . import anchored as annotations
    try:
        return annotations.post_of(st.corpus, tid)
    except _read.NotFound:
        return None


def _place(st, tid, post, body):
    """The anchor request a gesture on this post names, as Classic's toolbar
    sends it: the whole version (`type: version`), or a passage of one of its
    text parts (`passage`: part, start, end, unit, expected_excerpt). The
    version is the one the body names, or the post's current one -- what
    Classic reads as `turn.revision.current`. Returns (request, None) or
    (None, the 400)."""
    from mentis.conversation.versions import presented
    version = body.get("version")
    if version is None:
        now = presented(st.corpus, post)
        version = ((now or {}).get("revision") or {}).get("current", tid)
    elif not isinstance(version, str) or not version.strip():
        return None, _bad("\"version\" is the id of the version acted on")
    elif st.corpus.read([version]) and st.corpus.history(version)[0] != tid:
        return None, _bad(f"{version} is not a version of {tid}")
    passage = body.get("passage")
    if passage is None:
        return {"version": version, "type": "version"}, None
    if not isinstance(passage, dict):
        return None, _bad("\"passage\" is {part, start, end, unit, "
                          "expected_excerpt}")
    return {"version": version, "type": "text-range",
            **{k: passage.get(k) for k in ("part", "start", "end", "unit",
                                          "expected_excerpt")}}, None


def _anchored(st, tid, body, act, *, written_by) -> tuple[int, dict, list]:
    """Find or create the anchor, then `act(anchor, by, wrote)`, in one
    transaction; a refusal anywhere writes nothing."""
    from mentis.conversation import anchors
    from mentis.conversation.versions import Refused
    from mentis.web import _attributed
    post = _the_post(st, tid)
    if post is None:
        return _not_a_post(tid)
    by, refusal = _attributed(body, "author", corpus=st.corpus)
    if refusal:
        return _refused(refusal)
    request, bad = _place(st, tid, post, body)
    if bad:
        return bad
    try:
        with st.corpus.atomic():
            wrote = written_by()
            view = anchors.create_anchor(st.cv, request, by=by,
                                         written_by=wrote)
            out = act(view, by, wrote)
    except Refused as refused:
        return _refused(refused.refusal)
    except _Undone as undone:
        return undone.answer
    # `on` is the post acted on; `post` is too, unless the act wrote one (a
    # comment), when it is the comment.
    return _done(st, {"post": tid, **out}, on=tid, anchor=view["anchor"],
                 anchor_view=view)


def react(st, tid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/posts/<id>/reactions` {author, token, passage?,
    version?, changes?, because?, op?}: `anchors.react`. A change of one's
    own reaction names it in `changes`, as Classic's does."""
    from mentis.conversation import anchors
    return _anchored(st, tid, body, lambda view, by, wrote: anchors.react(
        st.cv, view["anchor"], body, by=by, written_by=wrote),
        written_by=written_by)


def deep_dive(st, tid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/posts/<id>/deep-dives` {author, why, name?,
    passage?, version?, op?}: `anchors.deep_dive`."""
    from mentis.conversation import anchors
    return _anchored(st, tid, body, lambda view, by, wrote: anchors.deep_dive(
        st.cv, view["anchor"], body, by=by, written_by=wrote),
        written_by=written_by)


def comment(st, tid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/posts/<id>/comments` {author, text, passage?,
    version?, conversation?, op?}: an anchored reply, as Classic writes one
    -- `record-only`, replying to the post, its parts the anchor and the
    words -- through `posting.post`. Said in `conversation` when it is given
    (one the post is in), and otherwise in the post's home."""
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        return _bad("a comment says something: \"text\"")
    later = []

    def say(view, by, wrote):
        status, out, then = write_post(st, {
            "conversation": body.get("conversation") or view["conversation"],
            "author": by, "action": "record-only", "replies_to": tid,
            "parts": [{"type": "anchor", "ref": view["anchor"]},
                      {"type": "text", "text": text}],
            **({"op": body["op"]} if "op" in body else {})},
            written_by=lambda: wrote)
        if status != 200:
            raise _Undone((status, out, []))
        later.extend(then)
        return {k: v for k, v in out.items() if k != "cursor"}
    # The anchor and the reply are one transaction, so the reply's own
    # `cursor` is read inside it; the answer's is read after the commit.
    status, out, _ = _anchored(st, tid, body, say, written_by=written_by)
    return status, out, later if status == 200 else []


def edit_post(st, tid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/posts/<id>/edit` {attributed_to, text, because?}:
    `versions.edit`, the next version of the post -- only its author may
    write one -- answered as production's `/api/entries/<id>/edit` is."""
    from mentis.conversation import versions
    from mentis.web import _attributed
    if _the_post(st, tid) is None:
        return _not_a_post(tid)
    corpus = st.corpus
    by, refusal = _attributed(body, corpus=corpus)
    if refusal:
        return _refused(refusal)
    because = body.get("because", "")
    try:
        got = versions.edit(st.cv, tid, by=by, text=body.get("text"),
                            because=because or None, written_by=written_by())
    except versions.Refused as refused:
        return _refused(refused.refusal)
    except ValueError as exc:
        return _refused({"error": str(exc), "entry": tid})
    return _done(st, {**got, "standing": corpus.stands(got["edited"]),
                      "version_standing": corpus.stands(got["version"]),
                      "versions": versions.history_view(
                          corpus, tid, alias=st.cv.alias)}, post=tid)


def _delete(st, eid, body, *, written_by):
    from mentis.conversation import versions
    from mentis.web import _attributed
    by, refusal = _attributed(body, corpus=st.corpus)
    if refusal:
        return None, _refused(refusal)
    try:
        return versions.delete(
            st.cv, eid, by=by,
            because=(body.get("because", "") or "").strip() or None,
            written_by=written_by()), None
    except versions.Refused as refused:
        return None, _refused(refused.refusal)


def delete_post(st, tid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/posts/<id>/delete` {attributed_to, because?}:
    `versions.delete`, production's Delete -- the post's line ends in a
    deletion record and nothing is erased. A comment is a post: removing
    one's own comment is this."""
    if _the_post(st, tid) is None:
        return _not_a_post(tid)
    got, refused = _delete(st, tid, body, written_by=written_by)
    return refused or _done(st, got, post=tid)


def withdraw_reaction(st, rid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/reactions/<id>/withdraw` {attributed_to, because?}:
    the reactor's own Delete of their reaction, which is what production
    calls a withdrawal (`versions.delete`). Anybody else's Delete is not a
    withdrawal, so this door refuses it rather than write one in its name."""
    from mentis.conversation import anchors
    got = st.corpus.read([rid]) if rid else []
    if not got or (got[0].get("definition") or {}).get("name") \
            != anchors.REACTION or not anchors.is_occurrence(st.corpus, rid):
        return 404, {"error": f"{rid} is not a reaction in this record",
                     "kind": "NotFound", "reaction": rid}, []
    by = body.get("attributed_to")
    if isinstance(by, str) and by.strip() \
            and by.strip() != got[0]["attributed_to"]:
        return _refused({"error": "only the actor who reacted can withdraw "
                                  "that reaction", "reaction": rid,
                         "by": got[0]["attributed_to"]})
    out, refused = _delete(st, rid, body, written_by=written_by)
    return refused or _done(st, out, reaction=rid,
                            post=anchors.anchor_turn(
                                st.corpus, got[0]["body"].get("about")))


def filing(st, tid, verb, body) -> tuple[int, dict, list]:
    """`POST /fluid/api/posts/<id>/topics` {by, topic | name},
    `/unfile` {by, topic, because?} and `/move` {by, topic}: production's
    `/api/turns/<id>/<verb>`, the same branch, in-process."""
    import mentis.web as _web
    if _the_post(st, tid) is None:
        return _not_a_post(tid)
    try:
        out = _web._routes(st, f"/api/turns/{tid}/{verb}", {}, body, "POST")
    except PermissionError as exc:
        return 403, {"error": str(exc), "kind": "PermissionError"}, []
    if out is None:
        return _not_a_post(tid)
    if "error" in out:
        return _refused(out)
    return _done(st, out, post=tid)


# -- F4a: arrangements, beside the record -------------------------------------

def save_arrangement(st, key, body) -> tuple[int, dict, list]:
    """`POST /fluid/api/arrangements/<key>` {layout, op?}: keep the Home's
    or a Conversation's arrangement (`mentis.fluid.arrangements`). Writes
    nothing to the record. A malformed one is 400; an operation key kept
    for a different arrangement is 422."""
    from mentis.fluid import arrangement_key
    from . import arrangements
    try:
        key = arrangement_key(st, key)
        out = arrangements.save(st.corpus.root, key, body)
    except _read.BadRequest as exc:
        return _bad(str(exc))
    except arrangements.Conflict as exc:
        return 422, {"error": str(exc), "refused": True, "key": key,
                     "reason": exc.reason}, []
    except arrangements.Declined as exc:
        return 422, {"error": str(exc), "refused": True, "key": key,
                     "reason": exc.reason}, []
    except arrangements.Refused as exc:
        return _bad(str(exc))
    except arrangements.Unreadable as exc:
        return 409, {"error": str(exc), "kind": "Unreadable",
                     "reason": {"code": "unreadable", "message": str(exc),
                                "retryable": False}}, []
    return 200, out, []


def magnet_command(st, which, tid, body) -> tuple[int, dict, list]:
    """The Magnet operations (`mentis.fluid.arrangements`): create,
    reconfigure, removeIfUnreferenced. Nothing to the record; a malformed
    request is 400, one the arrangement declines 422 with its reason, an
    unreadable stored arrangement 409 and left as it is."""
    from mentis.fluid import arrangement_key
    from . import arrangements
    key, _, mid = tid.partition("/")
    try:
        key = arrangement_key(st, key)
        root = st.corpus.root
        if which == MAGNET_CREATE:
            out = arrangements.create_magnet(root, key, body)
        elif which == MAGNET_ACTS["reconfigure"]:
            out = arrangements.reconfigure_magnet(root, key, mid, body)
        else:
            out = arrangements.remove_magnet(root, key, mid, body)
    except _read.BadRequest as exc:
        return _bad(str(exc))
    except arrangements.Conflict as exc:
        return 422, {"error": str(exc), "refused": True, "key": key,
                     "reason": exc.reason}, []
    except arrangements.Declined as exc:
        return 422, {"error": str(exc), "refused": True, "key": key,
                     "reason": exc.reason}, []
    except arrangements.Refused as exc:
        return _bad(str(exc))
    except arrangements.Unreadable as exc:
        return 409, {"error": str(exc), "kind": "Unreadable"}, []
    return 200, out, []


def settings_command(st, body) -> tuple[int, dict, list]:
    """`POST /fluid/api/settings` {makeRoom, op?} (`mentis.fluid.settings`)."""
    from . import settings
    try:
        return 200, settings.save(st.corpus.root, body), []
    except settings.Refused as exc:
        return _bad(str(exc))
    except settings.Unreadable as exc:
        return 409, {"error": str(exc), "kind": "Unreadable"}, []


def layouts_command(st, which, tid, body) -> tuple[int, dict, list]:
    """Named layouts and defaults, beside the record:
    `POST /fluid/api/layouts` {id, name, layout} keeps one,
    `POST /fluid/api/layouts/<id>/delete` deletes one,
    `POST /fluid/api/layouts/defaults` {place, layout} names a default.
    Each answers the library as it now stands."""
    from . import arrangements
    root = st.corpus.root
    try:
        if which == LAYOUTS:
            return 200, arrangements.save_layout(root, body), []
        if which == DELETE:
            return 200, arrangements.delete_layout(root, tid), []
        return 200, arrangements.set_default(root, body), []
    except arrangements.Refused as exc:
        return _bad(str(exc))
    except LookupError as exc:
        return 404, {"error": str(exc).strip("'\""), "kind": "NotFound"}, []
    except arrangements.Unreadable as exc:
        return 409, {"error": str(exc), "kind": "Unreadable"}, []


# -- F3: membership and naming ------------------------------------------------

def _bad(error) -> tuple[int, dict, list]:
    return 400, {"error": error, "kind": "BadRequest"}, []


def _author(st, body):
    """(who, None), or (None, the answer): absent or not a string is
    malformed (400), as F2's posts are; one the record does not hold, or
    that is not a Participant, is refused (422) -- whoever opens, renames or
    includes takes part, so it is somebody."""
    from mentis.web import _attributed
    author = body.get("author")
    if not isinstance(author, str) or not author.strip():
        return None, _bad("this writes to the record, so it needs to say who "
                          "it is by: name the Participant in \"author\"")
    by, refusal = _attributed(body, "author", corpus=st.corpus)
    if refusal:
        return None, (422, {**refusal, "refused": True}, [])
    if not st.cv._is_kind(by, "participant"):
        return None, (422, {"error": f"{by} is not a Participant in this "
                                     "record", "author": by,
                            "refused": True}, [])
    return by, None


def _ids_field(body, key, *, required=False):
    """A list of entry ids from the body, or the 400 saying it is not one."""
    got = body.get(key)
    if got is None and not required:
        return [], None
    if not isinstance(got, list) or not all(
            isinstance(x, str) and x.strip() for x in got):
        return None, _bad(f"\"{key}\" is a list of post ids")
    if required and not got:
        return None, _bad(f"\"{key}\" names at least one post")
    return [x.strip() for x in got], None


def _name_field(body, *, required=False):
    name = body.get("name")
    if name is None and not required:
        return None, None
    if not isinstance(name, str) or (required and not name.strip()):
        return None, _bad("\"name\" is the conversation's name, as text")
    return name.strip() or None, None


def _command(st, by, body, request, fn, *, status=200):
    """Run one F3 command under the author's operation key: the same key and
    request is answered with what it first came to (200, `replayed`) and
    writes nothing again (`anchors.keyed`). A refusal is 422 and keeps no
    key. The cursor is read after the commit, so a feed read from it has
    seen this."""
    from mentis.conversation import anchors
    from mentis.conversation.versions import Refused
    try:
        out = anchors.keyed(st.cv, by, body.get("op"), request, fn)
    except Refused as refused:
        return 422, {**refused.refusal, "refused": True}, []
    return (200 if out.get("replayed") else status), {
        **out, "cursor": _read.change_cursor(st.corpus.advance())}, []


def _conversation_projection(st, cid):
    """The conversation exactly as Fluid's entity read projects it now."""
    rows = _read.conversations(st.corpus, st.cv, [cid],
                                agents=st.agents)["conversations"]
    return rows[0] if rows and "error" not in rows[0] else None


def _project_conversation(answer, st, cid):
    """Add canonical state after the command committed.  The command's
    historical fields remain additive-compatible for older clients."""
    status, out, later = answer
    if status < 300:
        out["projection"] = _conversation_projection(st, cid)
    return status, out, later


def open_conversation(st, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations` {author, name?, op?}: open one. With
    no name it is opened under a provisional one ("Unnamed <when>")."""
    by, bad = _author(st, body)
    if bad:
        return bad
    name, bad = _name_field(body)
    if bad:
        return bad
    cv = st.cv

    def fn():
        wrote = written_by()
        cid = cv.open_conversation(name, about="", attributed_to=by,
                                   written_by=wrote, provisional=name is None)
        # Whoever opened it takes part in it, as production's door has it.
        cv.join(by, cid, attributed_to=by, written_by=wrote)
        return {"conversation": cid, "name": cv.conversation_name(cid),
                "provisional": name is None}
    answer = _command(st, by, body, {"route": "fluid-conversation-open",
                                     "name": name}, fn, status=201)
    return _project_conversation(answer, st, answer[1].get("conversation"))


def rename_conversation(st, cid, body, *,
                        written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations/<id>/name` {author, name, op?}."""
    by, bad = _author(st, body)
    if bad:
        return bad
    name, bad = _name_field(body, required=True)
    if bad:
        return bad

    def fn():
        got = st.cv.rename_conversation(cid, name, by=by,
                                        written_by=written_by())
        return {"conversation": cid, "name": got["name"],
                "provisional": False, "was": got["was"],
                "version": got["version"]}
    return _project_conversation(_command(
        st, by, body, {"route": "fluid-conversation-name",
                       "conversation": cid, "name": name}, fn), st, cid)


def members(st, cid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations/<id>/members` {author, add?, end?,
    op?}: include posts here and end inclusions here. Refused per item
    (`refused`); refused whole only when nothing could be done."""
    by, bad = _author(st, body)
    if bad:
        return bad
    add, bad = _ids_field(body, "add")
    if bad:
        return bad
    end, bad = _ids_field(body, "end")
    if bad:
        return bad
    if not add and not end:
        return _bad("name posts to include (\"add\") or to end (\"end\")")
    both = sorted(set(add) & set(end))
    if both:
        return _bad(f"{both[0]} is named both to add and to end")

    def fn():
        return st.cv.include(cid, by=by, add=add, end=end,
                             written_by=written_by())
    answer = _project_conversation(_command(
        st, by, body, {"route": "fluid-conversation-members",
                       "conversation": cid, "add": add, "end": end}, fn),
        st, cid)
    status, out, later = answer
    if status < 300:
        changed = list(dict.fromkeys(
            [x.get("post") for x in out.get("added", []) + out.get("ended", [])
             if x.get("post")]))
        out["posts"] = (_read.posts(st.corpus, changed, st.cv)["posts"]
                        if changed else [])
    return status, out, later


def group(st, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations/group` {author, posts, name?, op?}:
    open a Conversation holding these posts, all or nothing."""
    by, bad = _author(st, body)
    if bad:
        return bad
    posts, bad = _ids_field(body, "posts", required=True)
    if bad:
        return bad
    name, bad = _name_field(body)
    if bad:
        return bad

    def fn():
        return st.cv.group(posts, by=by, name=name, written_by=written_by())
    answer = _command(st, by, body, {"route": "fluid-conversation-group",
                                     "posts": posts, "name": name}, fn,
                      status=201)
    return _project_conversation(answer, st, answer[1].get("conversation"))


def _as_owner(st):
    """(the Brain's owner, None), or (None, the 422): the forms routes act
    as the owner and never as an `author` the body names (see the module
    docstring)."""
    from mentis.conversation.owner import _owner
    owner = _owner(st.cv)
    if owner is None:
        return None, (422, {"error": "this record names no owner, and these "
                                     "routes act only as the owner, so "
                                     "nothing was written", "refused": True},
                      [])
    return owner, None


def change_workflow(st, eid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/work/<request>/workflow` {workflow, because,
    evidence: [ref, ...], op?}: the owner changes the Workflow governing an
    active request (`workflow_change`), as the owner; a body's `author` is
    ignored. The same checks as a carrier's `change_workflow`, less the
    scope check -- the owner decides the scope. Nothing is dispatched: the
    request's next run is composed with the new Workflow."""
    from mentis.conversation import workflow_change as wc
    from mentis.conversation.versions import Refused
    by, bad = _as_owner(st)
    if bad:
        return bad
    evidence = body.get("evidence")
    if not isinstance(evidence, list) or not all(
            isinstance(x, str) for x in evidence):
        return _bad("evidence is a list of ent-/opr- references")
    workflow, because = body.get("workflow"), body.get("because")
    if not isinstance(workflow, str) or not isinstance(because, str):
        return _bad("workflow and because are strings")

    def fn():
        try:
            change = wc.check(st.cv, eid, workflow, because=because,
                              evidence=evidence, role=wc.OWNER)
        except wc.Refused as refused:
            raise Refused({"error": str(refused)})
        act = wc.record(st.cv, change, by=by)
        return {"ok": True, "act": act, "expectation": eid,
                "from": change["from"], "to": change["to"]}
    return _command(st, by, body, {"route": "fluid-workflow-change",
                                   "expectation": eid, "workflow": workflow,
                                   "because": because,
                                   "evidence": list(evidence)}, fn)


def set_ready(st, sid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets/<id>/ready` {seen?, op?}: Done
    (`inputs.mark_ready`), as the owner; a body's `author` is ignored.
    `seen` is the answer ids the owner was looking at; refused when the set
    has changed since."""
    from mentis.conversation.versions import Refused
    from mentis.web import inputs
    by, bad = _as_owner(st)
    if bad:
        return bad
    seen, bad = _ids_field(body, "seen")
    if bad:
        return bad
    try:
        out = inputs.mark_ready(st, sid, by=by,
                                seen=seen if body.get("seen") is not None else None,
                                written_by=written_by(), op=body.get("op"))
    except Refused as refused:
        return _refused(refused.refusal)
    return _done(st, out)


def set_send_back(st, sid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets/<id>/send-back` {op?}: hand the
    answers as they stand to the post's author (`inputs.send_back`), as the
    owner; a body's `author` is ignored. Its dispatch is started by the
    door, after the commit."""
    from mentis.conversation.versions import Refused
    from mentis.web import inputs
    by, bad = _as_owner(st)
    if bad:
        return bad
    try:
        out, later = inputs.send_back(st, sid, by=by, written_by=written_by(),
                                      op=body.get("op"))
    except Refused as refused:
        return _refused(refused.refusal)
    status, answer, _ = _done(st, out)
    return status, answer, later


# -- saving what is filled in (P3) --------------------------------------------

def _saving(st, body, fn, *, written_by) -> tuple[int, dict, list]:
    """One P3 write: by the owner (never a body's `author`), its required
    operation key, the owner the rules are given, and the refusal in the
    model's own words."""
    from mentis.conversation.versions import Refused
    op = body.get("op")
    if not isinstance(op, str) or not op.strip():
        return _bad("name this write's operation key in \"op\": a save the "
                    "screen may send again is one occurrence however often "
                    "it arrives")
    by, bad = _as_owner(st)
    if bad:
        return bad
    try:
        out = fn(by=by, op=op, owner=by, written_by=written_by())
    except Refused as refused:
        return _refused(refused.refusal)
    return _done(st, out)


def _optional_ids(body, key):
    """`replaces`: absent, one id, or a list of ids."""
    got = body.get(key)
    if got is None:
        return None, None
    if isinstance(got, str):
        got = [got]
    if not isinstance(got, list) or not all(isinstance(x, str) and x.strip()
                                            for x in got):
        return None, _bad(f"\"{key}\" is an entry id or a list of them")
    return [x.strip() for x in got], None


def _optional_text(body, key):
    got = body.get(key)
    if got is not None and not isinstance(got, str):
        return None, _bad(f"\"{key}\" is text")
    return got, None


def open_set(st, _none, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets` {post, block, part?, mode?,
    op}: find or open the block's response set."""
    from mentis.conversation import responses
    post, block = body.get("post"), body.get("block")
    if not isinstance(post, str) or not post.strip() \
            or not isinstance(block, str) or not block.strip():
        return _bad("name the block: its \"post\" and its \"block\" (name=)")
    part = body.get("part", 0)
    if not isinstance(part, int) or isinstance(part, bool):
        return _bad("\"part\" is the text part's index")
    mode = body.get("mode", "shared")

    def fn(*, by, op, owner, written_by):
        return responses.open_set(st.cv, post.strip(), block=block.strip(),
                                  part=part, mode=mode, by=by,
                                  written_by=written_by, op=op)
    return _saving(st, body, fn, written_by=written_by)


def set_answer(st, sid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets/<id>/answers` {field, value,
    replaces?, note?, conversation?, op}."""
    from mentis.conversation import responses
    if not isinstance(body.get("field"), str) or not body["field"].strip():
        return _bad("name the \"field\" this answers")
    if "value" not in body:
        return _bad("say the field's \"value\"")
    replaces, bad = _optional_ids(body, "replaces")
    if bad:
        return bad
    note, bad = _optional_text(body, "note")
    if bad:
        return bad
    where, bad = _optional_text(body, "conversation")
    if bad:
        return bad

    def fn(*, by, op, owner, written_by):
        return responses.answer(st.cv, sid, field=body["field"],
                                value=body["value"], replaces=replaces or (),
                                note=note, by=by, owner=owner,
                                conversation=where, written_by=written_by,
                                op=op)
    return _saving(st, body, fn, written_by=written_by)


def set_words(st, sid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets/<id>/own-words` {text,
    replaces?, conversation?, op}: kept exactly as sent."""
    from mentis.conversation import responses
    if not isinstance(body.get("text"), str):
        return _bad("\"text\" is the words, as written")
    replaces, bad = _optional_ids(body, "replaces")
    if bad:
        return bad
    where, bad = _optional_text(body, "conversation")
    if bad:
        return bad

    def fn(*, by, op, owner, written_by):
        return responses.write_words(st.cv, sid, text=body["text"],
                                     replaces=replaces or (), by=by,
                                     owner=owner, conversation=where,
                                     written_by=written_by, op=op)
    return _saving(st, body, fn, written_by=written_by)


def set_show(st, sid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets/<id>/show` {conversation, op}:
    show the same answers there."""
    from mentis.conversation import responses
    where = body.get("conversation")
    if not isinstance(where, str) or not where.strip():
        return _bad("name the \"conversation\" to show these answers in")

    def fn(*, by, op, owner, written_by):
        return responses.show(st.cv, sid, conversation=where.strip(), by=by,
                              written_by=written_by, op=op)
    return _saving(st, body, fn, written_by=written_by)


def set_start(st, sid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets/<id>/start-new` {copy?,
    conversation?, op}: a separate set on the same block. `copy` is true
    (every answered field) or the fields whose answers are copied."""
    from mentis.conversation import responses
    copy = body.get("copy", [])
    if copy is not True and (not isinstance(copy, list) or not all(
            isinstance(x, str) and x for x in copy)):
        return _bad("\"copy\" is true, or a list of the fields to copy")
    where, bad = _optional_text(body, "conversation")
    if bad:
        return bad

    def fn(*, by, op, owner, written_by):
        return responses.start_new(st.cv, sid, by=by, copy=copy,
                                   conversation=where, owner=owner,
                                   written_by=written_by, op=op)
    return _saving(st, body, fn, written_by=written_by)


def set_move(st, sid, body, *, written_by) -> tuple[int, dict, list]:
    """`POST /fluid/api/response-sets/<id>/move` {confirm?, op}: one
    click when every field kept its id and kind; otherwise a preview
    (`moved: false`) until it is sent again with `confirm: true`."""
    from mentis.conversation import responses
    confirm = body.get("confirm", False)
    if not isinstance(confirm, bool):
        return _bad("\"confirm\" is true or false")

    def fn(*, by, op, owner, written_by):
        return responses.move(st.cv, sid, by=by, confirm=confirm, owner=owner,
                              written_by=written_by, op=op)
    return _saving(st, body, fn, written_by=written_by)


def _interpretation_reply(outcome):
    def command(st, iid, body, *, written_by) -> tuple[int, dict, list]:
        from mentis.conversation import responses
        replaces, bad = _optional_ids(body, "replaces")
        if bad:
            return bad
        reason, bad = _optional_text(body, "reason")
        if bad:
            return bad
        changed_to = body.get("changed_to")
        if changed_to is not None and not isinstance(changed_to, dict):
            return _bad("\"changed_to\" is the changed proposal, an object")

        def fn(*, by, op, owner, written_by):
            return responses.reply(st.cv, iid, outcome=outcome, by=by,
                                   value=body.get("value"),
                                   changed_to=changed_to, replaces=replaces,
                                   reason=reason, owner=owner,
                                   written_by=written_by, op=op)
        return _saving(st, body, fn, written_by=written_by)
    command.__doc__ = (f"`POST /fluid/api/interpretations/<id>/...`: the "
                       f"interpretation {outcome} by the person whose words "
                       f"it read.")
    return command


#: The toolbar's commands that take (st, id, body, written_by=).
_ACTS = {WORKFLOW_CHANGE: change_workflow, "set-ready": set_ready, "set-send-back": set_send_back,
         SET_OPEN: open_set, "set-answer": set_answer, "set-words": set_words,
         "set-show": set_show, "set-start": set_start, "set-move": set_move,
         "interpretation-confirm": _interpretation_reply("confirmed"),
         "interpretation-change": _interpretation_reply("changed"),
         "interpretation-decline": _interpretation_reply("declined"),
         "post-react": react, "post-comment": comment,
         "post-deep-dive": deep_dive, "post-edit": edit_post,
         "post-delete": delete_post, WITHDRAW: withdraw_reaction}


def handle_post(handler, parsed, length: int) -> None:
    """Answer one POST under `/fluid/api/` on the production handler.

    THE SAME DOORS AS PRODUCTION'S JSON POSTS, in the same order: the Host
    check and the framing checks have already run (`do_POST`); then the body
    is read whole by its Content-Length (production sets no other limit on a
    JSON body, and neither does this), `X-Mentis-Client` is required, a worker
    grant is refused, and a body is JSON by its declared type. A path that
    names no command is 405, before anything is read, as in F0.
    """
    from mentis.worker import CAPABILITY_HEADER
    from . import PREFIX
    rest = parsed.path[len(PREFIX):].rstrip("/")
    which = command_of(rest)
    if which is None:
        return handler._send(405, {"error": "the Fluid API answers GET, and "
                                            "POST only at /fluid/api/posts, "
                                            "/fluid/api/posts/<id>/address, "
                                            "/reactions, /comments, "
                                            "/deep-dives, /edit, /delete, "
                                            "/topics, /unfile or /move, "
                                            "/fluid/api/reactions/<id>/"
                                            "withdraw, "
                                            "/fluid/api/response-sets, "
                                            "/fluid/api/response-sets/<id>/"
                                            "ready, /send-back, /answers, "
                                            "/own-words, /show, /start-new "
                                            "or /move, "
                                            "/fluid/api/interpretations/<id>/"
                                            "confirm, /change or /decline, "
                                            "/fluid/api/conversations, "
                                            "/fluid/api/conversations/group, "
                                            "/fluid/api/conversations/"
                                            "<id>/name or /members, "
                                            "/fluid/api/arrangements/<key>, "
                                            "/fluid/api/arrangements/<key>/"
                                            "magnets, /magnets/<id>/"
                                            "reconfigure or /remove, "
                                            "/fluid/api/settings, "
                                            "/fluid/api/work/<id>/workflow, "
                                            "and /fluid/api/layouts, "
                                            "/layouts/defaults or "
                                            "/layouts/<id>/delete",
                                   "kind": "PermissionError"})
    raw = handler._read_body(length)
    if handler._missing_client(parsed.path, "POST"):
        return
    if handler.headers.get(CAPABILITY_HEADER):
        return handler._send(403, {"error": "a worker grant authorises "
                                            "/api/worker and nothing else",
                                   "kind": "PermissionError",
                                   "asked_for": parsed.path})
    ctype = (handler.headers.get("Content-Type") or "").split(";")[0].strip()
    if raw and ctype.lower() != "application/json":
        return handler._send(415, {"error": "a JSON route takes "
                                            "Content-Type: application/json",
                                   "kind": "PermissionError"})
    try:
        body = json.loads(raw or b"{}")
    except ValueError as exc:
        return handler._send(400, {"error": f"the body is not JSON: {exc}",
                                   "kind": "BadRequest"})
    if not isinstance(body, dict):
        return handler._send(400, {"error": "the body is a JSON object",
                                   "kind": "BadRequest"})
    st = handler.state
    import mentis.web as _web
    # Nothing presenting a grant reaches here, so what the server observes of
    # this request is what production records for any request presenting none.
    writer = lambda: _web._observed_writer(st, None)          # noqa: E731
    try:
        if which[0] == POSTS:
            status, out, later = write_post(st, body, written_by=writer)
        elif which[0] == ADDRESS:
            status, out, later = address_post(st, which[1], body)
        elif which[0] == CONVERSATIONS:
            status, out, later = open_conversation(st, body,
                                                   written_by=writer)
        elif which[0] == NAME:
            status, out, later = rename_conversation(st, which[1], body,
                                                     written_by=writer)
        elif which[0] == MEMBERS:
            status, out, later = members(st, which[1], body,
                                         written_by=writer)
        elif which[0] == ARRANGEMENTS:
            status, out, later = save_arrangement(st, which[1], body)
        elif which[0] == MAGNET_CREATE or which[0] in MAGNET_ACTS.values():
            status, out, later = magnet_command(st, which[0], which[1], body)
        elif which[0] == SETTINGS:
            status, out, later = settings_command(st, body)
        elif which[0] in _ACTS:
            status, out, later = _ACTS[which[0]](st, which[1], body,
                                                 written_by=writer)
        elif which[0] in ("post-topics", "post-unfile", "post-move"):
            status, out, later = filing(st, which[1],
                                        which[0][len("post-"):], body)
        elif which[0] in (LAYOUTS, DEFAULTS, DELETE):
            status, out, later = layouts_command(st, which[0], which[1],
                                                 body)
        else:
            status, out, later = group(st, body, written_by=writer)
    except Exception as exc:                              # noqa: BLE001
        # As production answers a POST that raised: 400, with what it was.
        return handler._send(400, {"error": str(exc),
                                   "kind": type(exc).__name__})
    # STARTED ONLY ONCE ALL OF IT IS DURABLE, by production's own starter,
    # looked up when it is used so a test that replaces it replaces it here.
    for kw in later:
        _web.dispatch_soon(st, **kw)
    return handler._send(status, out)
