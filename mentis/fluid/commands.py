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
  POST /fluid/api/conversations/<id>/archive    list it under Archived
  POST /fluid/api/conversations/<id>/unarchive  list it as active again
  POST /fluid/api/conversations/<id>/trash      list it in Trash (refused
                                                while work is in flight)
  POST /fluid/api/conversations/<id>/restore    take it out of Trash

Archive, Trash and their reverses are acts on the Conversation
(`Conversations.change_conversation_state`): nothing is rewritten or deleted,
and there is no permanent deletion.

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

and a definition's own (`mentis.magnet`), wherever it is placed:

  POST /fluid/api/magnets/lift                                  magnet.lift
  POST /fluid/api/magnets/<id>/delete                           magnet.delete
  POST /fluid/api/magnets/<id>/conversation                     its Conversation
  POST /fluid/api/magnets/<id>/activate                         the Rust front's;
                                             Python alone never records one
                                             (`mentis.magnet.activation`)
  POST /fluid/api/magnets/<id>/authorize                        the owner opens
                                             ONE exchange to a named source
                                             outside this Magnet's collection
                                             (`mentis.magnet.scope.authorize`)

WHERE AN AGENT REQUEST STARTED SAYS WHERE IT GOES, and its result with it:

  POST /fluid/api/requests   `posts`' body, with `from` for `conversation`

A WORKSPACE'S MANIFEST, beside the record (`mentis.fluid.workspace_manifest`),
each with its required `op`:

  POST /fluid/api/workspaces                    make one
  POST /fluid/api/workspaces/<id>/rename        {name}
  POST /fluid/api/workspaces/<id>/objects       {object}: add one
  POST /fluid/api/workspaces/<id>/objects/<oid>/remove
  POST /fluid/api/workspaces/<id>/reorder       {order}
  POST /fluid/api/workspaces/<id>/delete

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
import re

from mentis.conversation import posting
from mentis.magnet import schema as S

from . import _checks as W
from . import read as _read

#: The commands this door answers. Any other POST under /fluid/api is 405.
POSTS = "posts"
REQUESTS = "requests"
ADDRESS = "address"
CONVERSATIONS = "conversations"
NAME = "name"
MEMBERS = "members"
#: where a Conversation is listed (`Conversations.change_conversation_state`)
STATE_VERBS = ("archive", "unarchive", "trash", "restore")
#: permanent deletion (`conversation.erasure`), from Trash, owner only
CONVERSATION_DELETE = "conversation-delete"
#: the owner's Finish cleanup on a deleted Conversation's tombstone
CONVERSATION_CLEANUP = "conversation-cleanup"
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
#: A definition's own, whatever arrangements name it: `magnets/<id>/<verb>`.
MAGNETS = "magnets"
MAGNET_DEFINITION_ACTS = {"delete": "magnet-delete",
                          "conversation": "magnet-conversation"}
MAGNET_LIFT = "magnet-lift"
MAGNET_ACTIVATE = "magnet-activate"
#: `magnets/<id>/authorize` (Part B): the owner's own act opening ONE exchange
#: in this Magnet's Conversation to a named source outside its collection. The
#: door for `mentis.magnet.scope.authorize` and nothing else.
MAGNET_AUTHORIZE = "magnet-authorize"
#: `magnets/propose`: one sentence in, a proposal out (Part G1). Reads only.
MAGNET_PROPOSE = "magnet-propose"
WORKSPACES = "workspaces"
#: A workspace's own acts, `workspaces/<id>/<verb>`.
WORKSPACE_ACTS = {"rename": "workspace-rename", "objects": "workspace-add",
                  "reorder": "workspace-reorder", "delete": "workspace-delete"}
#: `workspaces/<id>/objects/<oid>/remove`.
WORKSPACE_REMOVE = "workspace-remove"
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
    bits = rest.split("/")
    if len(bits) >= 3 and bits[0] == MAGNETS and bits[1] and bits[2] == "perspectives":
        if (len(bits) == 3 or (len(bits) == 4 and bits[3] == "selected")
                or (len(bits) == 5 and bits[3] and bits[4] in (
                    "question", "rename", "challenge", "retire", "resume", "branch", "prepare",
                    "bind", "reconcile", "finalize", "answer"))):
            return "magnet-perspective", "/".join(bits[1:])
    if rest in (POSTS, REQUESTS, CONVERSATIONS, LAYOUTS, SETTINGS, WORKSPACES):
        return rest, None
    if rest == RESPONSE_SETS:
        return SET_OPEN, None
    if rest == f"{MAGNETS}/lift":
        return MAGNET_LIFT, None
    if rest == f"{MAGNETS}/propose":
        return MAGNET_PROPOSE, None
    head, _, tail = rest.partition("/")
    tid, _, verb = tail.partition("/")
    if head == MAGNETS and tid and verb in MAGNET_DEFINITION_ACTS:
        return MAGNET_DEFINITION_ACTS[verb], tid
    if head == MAGNETS and tid and verb == "activate":
        return MAGNET_ACTIVATE, tid
    if head == MAGNETS and tid and verb == "authorize":
        return MAGNET_AUTHORIZE, tid
    if head == WORKSPACES and tid and verb in WORKSPACE_ACTS:
        return WORKSPACE_ACTS[verb], tid
    if head == WORKSPACES and tid:
        bits = verb.split("/")
        if len(bits) == 3 and bits[0] == "objects" and bits[1] \
                and bits[2] == "remove":
            return WORKSPACE_REMOVE, f"{tid}/{bits[1]}"
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
    if head == CONVERSATIONS and tid and verb in STATE_VERBS:
        return verb, tid
    if head == CONVERSATIONS and tid and verb == "delete":
        return CONVERSATION_DELETE, tid
    if head == CONVERSATIONS and tid and verb == "cleanup":
        return CONVERSATION_CLEANUP, tid
    return None


def write_post(st, body: dict, *, written_by, _request=False) -> tuple[int, dict, list]:
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
                              written_by=written_by, _managed=_request)
    if "error" in out:
        return out.get("status", 422), {**out, "refused": True}, []
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
        return out.get("status", 422), {**out, "refused": True}, []
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
    # A CONVERSATION IN TRASH OR DELETED is not writable: 409, said so
    # (`conversation.erasure.ConversationNotWritable`)
    from mentis.conversation.erasure import status_of
    return status_of(out, 422), {**out, "refused": True}, []


from mentis.conversation.erasure import NOT_WRITABLE  # noqa: E402


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
    from . import message_context as MC
    from mentis.conversation.versions import Refused
    try:
        if MC.association(st.cv, st.cv.conversation_of(tid)):
            MC.gate(body)
    except Refused as exc:
        return _refused(exc.refusal)
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
    """`POST /fluid/api/arrangements/<key>` {layout, op?}: keep the Home's,
    a workspace's or a Conversation's arrangement
    (`mentis.fluid.arrangements`). Writes nothing to the record. A malformed
    one is 400; an operation key kept for a different arrangement is 422."""
    from mentis.fluid import arrangement_key
    from . import arrangements
    from . import workspace_manifest as wm
    try:
        key = arrangement_key(st, key)
        out = arrangements.save(st.corpus.root, key, body)
    except (wm.NotFound, wm.Gone) as exc:
        return workspace_refused(exc)
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
    from . import workspace_manifest as wm
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
    except (wm.NotFound, wm.Gone) as exc:
        return workspace_refused(exc)
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


# -- one sentence becomes a proposal (Part G1) -----------------------------------
#
# WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT. The owner says one sentence --
# "follow what the ACP work is doing" -- and gets back a proposal in ordinary
# words: these sources, this much of them, this often. It is INERT: this command
# reads the record and writes nothing at all, so a proposal that is never
# accepted leaves no trace. Acceptance is the existing doors, in order, from one
# press: `arrangements/<key>/magnets` (a new Magnet's seed) or
# `.../magnets/<id>/reconfigure` (an existing one), then `magnets/<id>/activate`
# for the first collection, then one more `reconfigure` carrying the cadence.
# No new accept command exists, because the ones that apply a configuration
# already do (`docs/magnets/part-b-collection-api.md`, "The proposal").
#
# NOTHING HERE DECIDES WHAT READS. What reads is asked of the code that reads
# it: `mentis.sources.registry.descriptors()` says which connectors are
# available, and `mentis.magnet.activation` says whether a definition carrying a
# candidate source could run. So as Part C widens what a `file` source may read
# and Part W makes the web connectors available, the proposal picks them up with
# no change here, and it can never propose a kind that does not read.
#
# `WEB_KINDS` names three connector ids, which is as far as that goes: it says
# which scope option a SENTENCE can fill in for each (a feed address, a query,
# a page address), because only a person's words can say that. Whether any of
# them may be proposed is still the registry's answer and the connector's own
# `checked_options`, asked at the moment the proposal is made.

#: What a proposal asks for, at most: `mentis.magnet.schema.MAX_CRITERIA` is
#: where the sentence is kept, so that is what one may be.
MAX_SENTENCE = 2000
#: How many sources one proposal may name. Well under the schema's 20: a
#: proposal is an opening suggestion, not an exhaustive sweep of the Brain.
PROPOSE_MOST = 5
#: The cadences a sentence may ask for, in the order they are looked for, each
#: an ISO 8601 duration `mentis.magnet.schema._when` accepts. The last is the
#: default: "follow this" means come back without being asked, and six hours is
#: often enough to be useful and seldom enough to be unremarkable.
CADENCES = ((("every hour", "hourly", "each hour"), "PT1H", "Every hour"),
            (("every day", "daily", "each day", "once a day"), "P1D", "Every day"),
            (("every week", "weekly", "each week"), "P1W", "Every week"),
            ((), "PT6H", "Every six hours"))
#: Words a sentence opens with that say nothing about what to follow.
_OPENERS = ("i want to follow", "i want to track", "i want to watch",
            "i would like to follow", "keep an eye on", "keep track of",
            "keep up with", "follow", "track", "watch", "monitor",
            "collect", "gather", "tell me about", "show me", "stay on top of")
#: Words too common to match a Conversation or a collection by.
_NOISE = frozenset((
    "a", "an", "and", "any", "anything", "are", "as", "at", "about", "all",
    "be", "but", "by", "down", "everything", "for", "from", "going", "happens",
    "has", "have", "how", "in", "into", "is", "it", "its", "me", "my", "new",
    "of", "on", "or", "our", "out", "over", "please", "something", "that",
    "the", "their", "them", "then", "there", "these", "this", "those", "to",
    "up", "what", "whatever", "when", "where", "which", "who", "with",
    "work", "working"))


def _sentence_words(sentence: str) -> list[str]:
    """The sentence's own words, lowercased, with the noise taken out."""
    return [w for w in re.findall(r"[0-9a-z]+", sentence.lower())
            if len(w) > 2 and w not in _NOISE]


#: What is left of a sentence after the opener and the cadence are both cut,
#: when that remainder names nothing but one address: the whole string, with
#: no other word around it.
_URL_ONLY = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://\S+$")


def _url_only_host(said: str) -> str | None:
    """The host of `said`, when `said` is nothing but one address (never
    None for a sentence with any other word in it)."""
    if not _URL_ONLY.fullmatch(said):
        return None
    from urllib.parse import urlparse
    return urlparse(said).hostname or None


def proposed_name(sentence: str) -> str:
    """A NAME DERIVED, NEVER DEMANDED (#815, amendment §4). What the owner
    actually typed, with the words that only address the machine removed, cut
    to what a Magnet may be called. A sentence that is nothing but an opener
    still gets a name, because a Magnet always has one."""
    said = " ".join(sentence.split())
    low = said.lower()
    for opener in _OPENERS:
        if low.startswith(opener + " "):
            said = said[len(opener) + 1:].lstrip()
            break
    # The cadence is shown on its own line, so it is not also the name: a
    # Magnet is called what it follows, not how often it looks.
    low = said.lower()
    for asked, _when, _words in CADENCES:
        hit = next((a for a in asked if low.endswith(" " + a)
                    or low.endswith(", " + a)), None)
        if hit:
            said = said[:len(said) - len(hit)].rstrip(" ,")
            break
    said = said.strip(" .,:;!?-–—\"'").strip()
    if not said:
        said = " ".join(sentence.split()).strip(" .,:;!?-–—\"'") or "New Magnet"
    # A URL-ONLY SUBJECT IS NAMED FOR ITS HOST, not the address: "follow
    # https://feeds.bbci.co.uk/news/world/rss.xml every day" is called
    # "feeds.bbci.co.uk", not the scheme and path nobody would read as a name.
    host = _url_only_host(said)
    if host:
        return host[:S.MAX_NAME]
    if len(said) > S.MAX_NAME:
        cut = said[:S.MAX_NAME].rsplit(" ", 1)[0]
        said = (cut or said[:S.MAX_NAME]).rstrip(" .,:;-–—")
    return said[:1].upper() + said[1:]


def proposed_cadence(sentence: str) -> tuple[str, str]:
    """The cadence the sentence asks for, and that cadence in ordinary words.

    THE CADENCE IS PART OF THE PROPOSAL (amendment §4), so periodic refresh is
    on from the start rather than being something to go and switch on. It is
    checked here by the schema's own rule, so an unsupported one cannot be
    proposed."""
    low = " ".join(sentence.lower().split())
    for asked, when, words in CADENCES:
        if any(a in low for a in asked):
            S._when(when, "collection.schedule")
            return when, words
    when, words = CADENCES[-1][1], CADENCES[-1][2]
    S._when(when, "collection.schedule")
    return when, words


def runnable_definition(sources, types, criteria, *, mid="mag-proposal") -> dict:
    """The definition a FIRST COLLECTION runs from, checked by the schema.

    Exactly the facets `mentis.magnet.activation` requires of a definition it
    will run, so what is proposed is what can be collected. The cadence is not
    in here: it is applied after the first collection, by its own reconfigure,
    because this build's manual activation is the thing that runs that first
    collection (see the contract document's "Why the cadence lands last")."""
    selection = {}
    if criteria:
        selection["criteria"] = criteria
    if types:
        selection["informationTypes"] = list(types)
    return S.magnet_config({
        "id": mid, "sources": list(sources), "selection": selection,
        "collection": {"mode": "one-time"}, "synthesis": {"mode": "manual"},
        "notifications": {"newItems": False, "changes": False,
                          "failures": False},
        "presentation": {"renderer": "disc"},
        "activation": {"mode": "manual"},
        "processing": {"operations": [{"op": "extract"}]},
        "ai": {"mode": "none"}, "outputs": ["records"],
        "destinations": [{"kind": "magnet-conversation"}]}, "proposal")


def reads_here(source) -> bool:
    """Whether a definition carrying just this source could actually collect.

    ASKED OF THE CODE THAT READS, NOT OF A LIST. `_cannot_run_code` is the
    activation contract's own first-failing-line check and `runnable_files` its
    own file rule, so this answer moves when they move -- which is how Part C's
    widened file reads become proposable with no change here.

    SEAM: both are `mentis.magnet.activation`'s, and the first is private to
    that module. A public name for "could this definition run" belongs there;
    Part C holds that file in this round, so this reaches for it rather than
    adding one. Named for its owner or the integrator."""
    from mentis.magnet import activation as ACT
    try:
        value = runnable_definition([source], ("post",), None)
    except S.Refused:
        return False
    return ACT._cannot_run_code(value) is None and ACT.runnable_files(value)


def _scored(words, text) -> int:
    """How much of the sentence a candidate's own name actually says."""
    if not words:
        return 0
    have = set(re.findall(r"[0-9a-z]+", (text or "").lower()))
    return sum(1 for w in set(words) if w in have)


def _conversation_candidates(st, words) -> list[dict]:
    """Conversations in this Brain, best match to the sentence first."""
    from . import read as _r
    try:
        rows = (_r.conversation_list(st.corpus, st.cv, 40, state="active",
                                     agents=getattr(st, "agents", None))
                or {}).get("conversations") or []
    except Exception:                                         # noqa: BLE001
        return []
    out = []
    for row in rows:
        cid, name = row.get("id"), row.get("name") or ""
        if not isinstance(cid, str) or not W._TURN.fullmatch(cid):
            continue
        source = {"kind": "conversation", "conversation": cid}
        if not reads_here(source):
            continue
        out.append({"source": source, "title": name or cid,
                    "says": "Conversation · posts and their attachments",
                    "score": _scored(words, name)})
    out.sort(key=lambda c: -c["score"])
    return out


def _collection_candidates(st, words) -> tuple[list[dict], list[dict]]:
    """Declared source collections a Magnet could read, and the ones it cannot.

    WHICH CONNECTORS ARE AVAILABLE IS THE REGISTRY'S ANSWER, read now: a
    collection whose connector `descriptors()` reports unavailable is never
    proposed, and is reported with the registry's own words for why not."""
    from mentis.sources import declarations
    from mentis.sources import reading as _reading
    from mentis.sources.registry import descriptors
    known = {d["id"]: d for d in descriptors()}
    out, refused = [], []
    try:
        declared = declarations(st.corpus)
    except Exception:                                         # noqa: BLE001
        return [], []
    for decl in declared:
        cid, connector = decl.get("collection"), decl.get("connector")
        said = known.get(connector) or {}
        label = said.get("label") or connector
        name = decl.get("name") or cid
        if not said.get("available"):
            refused.append({"title": name, "kind": connector,
                            "why": said.get("why_not")
                            or f"the {label} connector is not available yet"})
            continue
        # A path is asked for only while the activation contract asks for one:
        # a collection-scoped read (Part C) makes the path-less source runnable
        # and this stops looking for an exact file.
        source = {"kind": "file", "collection": cid}
        path = None
        if not reads_here(source):
            try:
                found = _reading.objects(st.corpus, cid, state="present",
                                         limit=40).get("objects") or []
            except Exception:                                 # noqa: BLE001
                found = []
            for obj in found:
                if obj.get("text") is not True or not obj.get("path"):
                    continue
                if reads_here({"kind": "file", "collection": cid,
                               "path": obj["path"]}):
                    path = obj["path"]
                    break
            if path is None:
                refused.append({"title": name, "kind": connector,
                                "why": "nothing in this collection is held as "
                                       "plain text that a Magnet can read yet"})
                continue
            source = {"kind": "file", "collection": cid, "path": path}
        out.append({"source": source,
                    "title": f"{name} · {path}" if path else name,
                    "says": f"{label} · held by Mentis, read from the record",
                    "score": _scored(words, f"{name} {path or ''}")})
    out.sort(key=lambda c: -c["score"])
    return out, refused


#: THE COLLECTION A SENTENCE CAN ASK FOR, AND THE OPTION IT FILLS IN. Each is
#: a connector id `mentis.sources.registry` knows, with the one scope option a
#: sentence can say anything about. Nothing here decides availability or
#: validity: the registry says whether the connector is available, the
#: connector's own `checked_options` says whether these options are a scope it
#: would take, and `reads_here` says whether a Magnet could read the result. A
#: kind failing any of the three is not proposed.
WEB_KINDS = {"rss-atom": "feeds", "web-search": "queries", "web": "urls"}
#: Any address at all, so an address this build cannot read is REFUSED rather
#: than quietly turned into a web search for its own text.
_ANY_ADDRESS = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S+")
#: What marks a named address as a feed rather than a page. A feed address is
#: conventional, not discoverable without fetching, and this proposes nothing
#: it has to fetch to decide.
_FEEDISH = ("/rss", "/feed", "/atom", "rss.xml", "atom.xml", "feed.xml",
            ".rss", ".atom", "/rss/", "/feed/", "format=rss", "alt=rss")
#: Trailing punctuation a sentence puts after an address, which is the
#: sentence's and not the address's.
_AFTER_ADDRESS = ".,;:!?)]}>\"'"


def _web_draft(sentence: str, subject: str):
    """`(connector, options)` the sentence asks for, or None.

    WHAT THE SENTENCE NAMES DECIDES, and nothing else: an https feed address
    asks for that feed, an https page address asks for that page, and a
    sentence that names no address at all asks for a search for its subject.
    An address of any other scheme asks for something this build cannot read,
    which is None -- not a search for the text of the address."""
    found = _ANY_ADDRESS.search(sentence)
    if found:
        url = found.group(0).rstrip(_AFTER_ADDRESS)
        low = url.lower()
        if not low.startswith("https://"):
            return None
        if any(mark in low for mark in _FEEDISH):
            return "rss-atom", {"feeds": [url]}
        return "web", {"urls": [url]}
    if not subject:
        return None
    return "web-search", {"queries": [subject]}


def _proposed_collection(st, sentence: str, subject: str) -> dict | None:
    """A COLLECTION THIS BRAIN DOES NOT HOLD YET, proposed from the sentence.

    The owner's second correction: the proposal ranked collections that
    already exist, so a sentence about the world with no history here could
    only fall back to internal posts. This offers to declare one -- and is
    inert exactly as the rest of the proposal is. Nothing is declared,
    fetched, bound or recorded by asking: what is returned is a draft for the
    door that already declares a collection (`sources/plan` then
    `sources/sweep`, `mentis.web.sources`), which the press takes.

    EVERY CHECK IS THE CODE'S OWN, not a list here. The registry says which
    connectors are available and what scope fields each has; the connector
    says whether these options are a scope it would take, which is where an
    address's transport, length and credential rules live
    (`mentis.sources.fetch`); and `reads_here` says whether a Magnet could
    read the collection that results. A kind that fails any of them is not
    proposed, so this can never show a draft the declaring door would refuse.

    The pure check of a connector's option values is `Sources.checked_options`
    on the registry, beside `check_options` (which checks the field NAMES
    only); the value check otherwise happens inside `preview_new`, which
    fetches."""
    from mentis.sources.registry import Sources, descriptors
    drafted = _web_draft(sentence, subject)
    if drafted is None:
        return None
    connector, asked = drafted
    said = next((d for d in descriptors() if d.get("id") == connector), None)
    if not said or not said.get("available"):
        return None
    fields = {f.get("name") for f in (said.get("scope_fields") or [])
              if f.get("option")}
    if not set(asked) <= fields:
        return None
    try:
        options = Sources(st.corpus, st.cv).checked_options(connector, dict(asked))
    except Exception:                                         # noqa: BLE001
        return None
    # The source the press will carry, which must be one this build collects.
    # Asked of the activation contract with a collection id of the shape a
    # declaration answers with (`lifecycle.declare`: `col-` and 12 hex).
    source = {"kind": "file", "collection": "col-000000000000"}
    if not reads_here(source):
        return None
    label = said.get("label") or connector
    name = f"{label} · {subject}" if subject else label
    return {"connector": connector, "name": name[:S.MAX_CRITERIA],
            "options": options, "title": name[:S.MAX_CRITERIA],
            "says": f"{label} · {said.get('summary') or ''}".strip(" ·"),
            # The one field a declaration alone can answer with.
            "source": {"kind": "file", "collection": None}}


def _listed(titles) -> str:
    titles = list(titles)
    if not titles:
        return ""
    if len(titles) == 1:
        return titles[0]
    return f"{', '.join(titles[:-1])} and {titles[-1]}"


#: What is collected from a Conversation unless the sentence narrows it.
PROPOSED_TYPES = ("post", "file", "image", "attachment")
#: Said when nothing in the Brain matches, which is an answer and not a fault:
#: a Magnet may be created with no sources at all (#521 §4), so one is proposed
#: with none rather than with a source nobody asked for.
NOTHING_MATCHES = ("Nothing in this Brain matches that yet, so this Magnet "
                   "starts with no sources. You can talk to it straight away, "
                   "and add a source whenever one exists.")


def magnet_proposal(st, body) -> tuple[int, dict, list]:
    """`POST /fluid/api/magnets/propose` {sentence, magnet?}: one sentence in,
    a proposal out. READS ONLY -- nothing is written, and the proposal is inert
    until the owner accepts it through the existing doors.

    The answer is `{proposal: {sentence, name, sources, selection, cadence,
    words, change, seed, unavailable, declare}}`, every part of it already
    checked by `mentis.magnet.schema`, so an unsupported mode is never
    proposed. `docs/magnets/part-b-collection-api.md` is the contract.

    `declare` is a COLLECTION THIS BRAIN DOES NOT HOLD YET, proposed from the
    sentence itself (`_proposed_collection`), beside the existing collections
    and Conversations that already matched. It is the last `listed` row and it
    is NOT in `sources`, because the collection it will read does not exist
    until the press declares it: so `listed` is `sources` and then, where
    there is one, this."""
    sentence = body.get("sentence")
    if not isinstance(sentence, str) or not sentence.strip():
        return _bad("say in one sentence what you want this Magnet to follow")
    sentence = " ".join(sentence.split())
    if len(sentence) > MAX_SENTENCE:
        return _bad(f"a sentence of at most {MAX_SENTENCE} characters")
    mid = body.get("magnet")
    if mid is not None and (not isinstance(mid, str)
                            or not S.MAGNET_ID.fullmatch(mid)):
        return _bad("\"magnet\" names an existing Magnet, or is left out")
    words = _sentence_words(sentence)
    try:
        collections, unavailable = _collection_candidates(st, words)
        candidates = _conversation_candidates(st, words) + collections
        # Best match first, and ONLY what the sentence actually says. A
        # candidate the sentence does not name is never proposed, however
        # little else there is: an empty proposal is an answer (#521 §4), and
        # a source nobody asked for is not.
        candidates.sort(key=lambda c: -c["score"])
        chosen = [c for c in candidates if c["score"]][:PROPOSE_MOST]
        sources = [c["source"] for c in chosen]
        types = PROPOSED_TYPES if any(s["kind"] == "conversation"
                                      for s in sources) else ()
        when, cadence_words = proposed_cadence(sentence)
        name = proposed_name(sentence)
        value = runnable_definition(sources, types, sentence,
                                    mid=mid or "mag-proposal")
        # The cadence, checked as the facet it will be applied as.
        cadence = S.facet("collection", {"mode": "scheduled", "schedule": when},
                          "proposal.collection")
        if not S._identity({"name": name}, "proposal.identity").get("name"):
            return _bad("that sentence gives no name a Magnet can carry")
        # AND WHAT THE SENTENCE ASKS FOR THAT THIS BRAIN HAS NOT GOT. Derived
        # after the name, because the name is the subject the sentence is
        # about, and that is what a search would be for.
        declare = _proposed_collection(st, sentence, name)
    except S.Refused as exc:
        return _bad(str(exc))
    change = {k: value[k] for k in
              ("sources", "selection", "collection", "synthesis",
               "notifications", "activation", "processing", "ai", "outputs",
               "destinations") if k in value}
    change["identity"] = {"name": name}
    return 200, {"proposal": {
        "sentence": sentence,
        "name": name,
        "sources": list(value["sources"]),
        "selection": dict(value["selection"]),
        "cadence": dict(cadence),
        "words": {
            "sources": _listed([c["title"] for c in chosen]
                               + ([declare["title"]] if declare else []))
            or NOTHING_MATCHES,
            "collect": ("Posts, files, images and attachments"
                        if types else "Everything these sources hold"),
            "cadence": cadence_words,
        },
        "listed": [{"title": c["title"], "says": c["says"]} for c in chosen]
        + ([{"title": declare["title"], "says": declare["says"]}]
           if declare else []),
        # What a press applies, in the order it applies it. `seed` creates a
        # Magnet that does not exist yet; `change` reconfigures one that does.
        # Both carry the same checked definition.
        "change": change,
        "seed": {k: v for k, v in value.items() if k != "id"},
        "unavailable": unavailable,
        # A collection to declare at the press, or None. Inert: nothing here
        # has declared, fetched or recorded anything.
        "declare": declare,
    }}, []


def magnet_definition_command(st, which, mid, body,
                              *, written_by) -> tuple[int, dict, list]:
    """A definition's own acts (`mentis.magnet`), wherever it is placed:
    `magnets/lift` keeps what arrangements embed as definitions, and writes
    nothing to them; `magnets/<id>/delete` ends one nothing refers to, 422
    while something does; `magnets/<id>/conversation` {author, name?, op?} opens
    its own Conversation through `open_conversation`, under the authority any
    other has, once: asked again it answers the one it has."""
    from . import arrangements
    import mentis.magnet as magnet
    root = st.corpus.root
    try:
        if which == MAGNET_LIFT:
            return 200, arrangements.lift_all(root), []
        if which == MAGNET_DEFINITION_ACTS["delete"]:
            return 200, arrangements.delete_definition(root, mid), []
        with magnet.asking_for_conversation(root, mid):
            arrangements.lift_all(root)
            config = magnet.read(root, mid)
            if config is None:
                raise arrangements.Declined("state", magnet.MISSING)
            # The record decides, whatever the file names: a request's claim, or
            # this route's own, may be ahead of the file or differ from it.
            claimed = _claimed(st, "magnet", mid)
            if claimed:
                _tell_the_file(st, ("magnet", mid), claimed)
                return 200, {"magnet": mid, "created": False,
                             "conversation": claimed}, []
            if config.get("conversation"):
                return 200, {"magnet": mid, "created": False,
                             "conversation": config["conversation"]}, []
            # This route has one Conversation to create for the lifetime of
            # the Magnet.  Keep that record write under a stable internal key,
            # committed with the claim, so a failed definition-file replacement
            # can be retried without committing a second Conversation, and an
            # outcome under the key from before claims is claimed, not repeated.
            with st.corpus.atomic():
                status, out, later = _open_under_magnet_key(
                    st, mid, body, written_by=written_by)
                if status >= 300 or not out.get("conversation"):
                    return status, out, later
                _claim(st, _author(st, body)[0], "magnet", mid,
                       out["conversation"])
            kept = magnet.set_conversation(root, mid, out["conversation"])
            return status, {**out, "magnet": mid, "created": True,
                            "conversation": kept["conversation"]}, later
    except arrangements.Declined as exc:
        return 422, {"error": str(exc), "refused": True, "magnet": mid,
                     "reason": exc.reason}, []
    except arrangements.Refused as exc:
        return _bad(str(exc))
    except arrangements.Unreadable as exc:
        return 409, {"error": str(exc), "kind": "Unreadable"}, []


#: Everything `magnets/<id>/authorize` takes. Anything else is malformed: a
#: body cannot name who an owner write is by, and this door accepts no option.
AUTHORIZE_FIELDS = {"brain", "op", "turn", "opens", "reason"}


def magnet_authorize(st, mid, body, *, brain) -> tuple[int, dict, list]:
    """`POST /fluid/api/magnets/<id>/authorize` {brain, op, turn, opens, reason?}:
    THE OWNER OPENS ONE EXCHANGE, to what it names (Part B).

    The door `mentis.magnet.scope.authorize` was written for and did not have,
    so until now no client could create an authorization and every exchange was
    unauthorized -- which left the owner's correction ("allowing conversations
    to explore additional sources when explicitly authorized", amendment
    adm-c38044ee5157 section 3) undelivered.

    IT ADDS WHAT A DOOR ADDS, AND NOTHING ELSE. The confirmed Brain, the
    operation key a screen may retry under, and HTTP words for a refusal.
    Every rule stays `scope.authorize`'s: the recorded owner and nobody else,
    the owner's own asking Turn in this Magnet's own Conversation, 1..4 things
    named, one act, no persistence beyond that one exchange. The owner is read
    from the Brain, as on every other write on this door; `author` in the body
    is not accepted, rather than ignored, because here it would look like
    authority. This route never dispatches and changes no grant: the one door
    (`/api/worker`) reads the act for that exchange's execution.
    """
    from mentis.conversation.versions import Refused
    from mentis.fluid.inspect import brain_key
    from mentis.magnet import Unreadable, scope
    from mentis.operational.work_overview import owner_of
    try:
        key = brain_key(st.corpus)
    except OSError as exc:
        return 409, {"error": str(exc), "kind": "BrainUnconfirmed"}, []
    if not brain or not key or brain != key or body.get("brain") != key:
        return 409, {"error": "confirm this serving Brain before authorizing an "
                              "exchange to reach outside this Magnet's collection",
                     "kind": "BrainUnconfirmed" if not brain else "BrainChanged",
                     "refused": True}, []
    extra = sorted(set(body) - AUTHORIZE_FIELDS)
    if extra:
        return _bad(f"an authorization takes {sorted(AUTHORIZE_FIELDS)} and "
                    f"nothing else; the owner is read from this Brain, never "
                    f"from the body: {extra}")
    op = body.get("op")
    if not isinstance(op, str) or not op.strip() or len(op) > 160:
        return _bad("an authorization needs \"op\", the client's operation key: "
                    "a nonempty string of at most 160 characters")
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _bad("\"reason\" is the owner's own words, or absent")
    owner = owner_of(st.cv)
    if not owner:
        return 422, {"error": "this record names no owner, so nothing here can "
                              "be the owner's own act", "refused": True,
                     "code": "owner-required", "magnet": mid}, []
    try:
        out = scope.authorize(st, mid, turn=body.get("turn"),
                              opens=body.get("opens"), by=owner, op=op.strip(),
                              reason=reason)
    except scope.Refused as exc:
        return 422, {"error": str(exc), "code": "authorization-refused",
                     "refused": True, "magnet": mid}, []
    except Refused as exc:
        return exc.refusal.get("status", 422), {**exc.refusal, "refused": True}, []
    except Unreadable as exc:
        return 409, {"error": str(exc), "kind": "Unreadable"}, []
    return 200, {**out, "brain": key}, []


# -- a workspace's manifest, beside the record ----------------------------------
#
# Over `workspace_manifest`, which decides everything here. A door adds what a door
# is for: an operation key it cannot go without, as a save the screen may retry, and
# a refusal in HTTP terms. It writes nothing to the record, and it makes no
# Conversation: only a request does (`agent_request`).

SEEDS = ("magnet", "conversation")


def workspace_refused(exc) -> tuple[int, dict, list]:
    """How a workspace door says why not, whichever door it is: as `agent_request`
    answers a workspace that isn't there, deleted or unreadable."""
    from . import workspace_manifest as wm
    said = str(exc).strip("'\"")
    if isinstance(exc, wm.Conflict):
        return 422, {"error": said, "kind": "Conflict", "refused": True}, []
    if isinstance(exc, wm.NotFound):
        return 404, {"error": said, "kind": "NotFound"}, []
    if isinstance(exc, wm.Gone):
        return 410, {"error": said, "kind": "Gone"}, []
    if isinstance(exc, wm.Unreadable):
        return 409, {"error": said, "kind": "Unreadable"}, []
    return _bad(said)


def _seed_missing(st, kind, ref) -> tuple[int, dict, list] | None:
    """Why this Magnet or Conversation can't be what a workspace starts from, or None.
    It has only to be there: nothing is asked of what it owns, nothing is made, and
    so a Magnet known only by the copy an arrangement embeds is not lifted."""
    from . import arrangements
    import mentis.magnet as magnet
    corpus, cv = st.corpus, st.cv
    if kind == "magnet":
        root = corpus.root
        if magnet.exists(root, ref) or arrangements.references(root, ref):
            return None
        return 422, {"error": magnet.MISSING, "refused": True, "magnet": ref}, []
    if not corpus.read([ref]) or not cv._is_kind(ref, "conversation"):
        return 400, {"error": f"{ref} is not a conversation in this record",
                     "kind": "BadRequest", "conversation": ref}, []
    refusal = cv.version_refusal(ref)
    return (422, {**refusal, "refused": True}, []) if refusal else None


def _new_workspace(st, body, op) -> tuple[int, dict, list]:
    """`POST /fluid/api/workspaces` {name?, objects?, from?, op}. Blank with neither
    `objects` nor `from`. `from`, `{"magnet": id}` or `{"conversation": id}`, is one
    curated object first, whose provenance says only that: a time would make a retry
    a different request. Whether what it started from is there is asked last, of a
    request `create` would make: the request is answered for itself first, and a retry
    by its key, whatever has since become of what it started from. Not under the
    manifest's lock, which no read of the record is taken under."""
    from . import workspace_manifest as wm
    root = st.corpus.root
    fields = {k: v for k, v in body.items() if k != "from"}
    origin = None
    if body.get("from") is not None:
        origin, bad = _one_named(body, "from", SEEDS)
        if bad:
            return bad
        kind, ref = origin
        objects = body.get("objects", [])
        if isinstance(objects, list):
            fields["objects"] = [{"kind": kind, "ref": ref, "provenance": {
                "source": {"kind": kind, "ref": ref}}}, *objects]
    if origin and wm.would_make(root, fields):
        missing = _seed_missing(st, *origin)
        if missing:
            return missing
    out = wm.create(root, fields)
    return (200 if out["replayed"] else 201), out, []


def workspace_command(st, which, tid, body) -> tuple[int, dict, list]:
    """A workspace's doors. An operation key used for a different request is 422, a
    workspace that isn't there 404, a deleted one 410, an unreadable one 409 and left
    as it is, and anything else refused, a key that no longer fits included, 400."""
    from . import workspace_manifest as wm
    op = body.get("op")
    if not isinstance(op, str) or not op.strip():
        return _bad("name this write's operation key in \"op\": a change the "
                    "screen may send again is one occurrence however often it "
                    "arrives")
    root = st.corpus.root
    wid, _, oid = (tid or "").partition("/")
    try:
        if which == WORKSPACES:
            return _new_workspace(st, body, op)
        if which == WORKSPACE_ACTS["rename"]:
            out = wm.rename(root, wid, body)
        elif which == WORKSPACE_ACTS["objects"]:
            out = wm.add_object(root, wid, body)
        elif which == WORKSPACE_REMOVE:
            out = wm.remove_object(root, wid, oid, body)
        elif which == WORKSPACE_ACTS["reorder"]:
            out = wm.reorder(root, wid, body)
        else:
            out = wm.delete(root, wid, body)
    except (wm.Conflict, wm.NotFound, wm.Gone, wm.Refused,
            wm.Unreadable) as exc:
        return workspace_refused(exc)
    return 200, out, []


# -- where an agent request goes ------------------------------------------------
#
# A request is an ordinary post: `write_post`, so `posting.post`, is what records
# it, owes it and dispatches it, and an agent's result is said in the Conversation
# its request is in. All this door adds is which Conversation that is:
#
#   from a workspace          the workspace's own Conversation
#   from a Magnet             that Magnet's own Conversation
#   from a Conversation       that Conversation
#   from a workspace, with `destination`, a Conversation or a Magnet: that instead
#
# Nothing here reads what a workspace holds: its Magnets are not candidates, so
# none is primary, however many there are. A workspace's or Magnet's Conversation
# is created by the first request that goes to it, through `open_conversation`.
#
# THE RECORD DECIDES AND THE FILES FOLLOW, because two stores cannot commit as one.
# One transaction holds all of it that matters: the Conversation, the act claiming
# it for this workspace or Magnet (`CONVERSATION_CLAIMED`), the request, what it
# owes, its operation key, and what it has yet to start (`REQUEST_ROUTED`). Only
# then, in this order, is the file told and the run started. So wherever a process
# ends, the next request finds:
#
#   before the commit     nothing, and makes it all
#   before the file       the claim, so no second Conversation; the file is told
#   before the start      an expectation nothing ran; a retry of this key starts it
#   after the start       a recorded start or end; nothing starts it again
#
# The file only ever repeats a commit, so it cannot name a Conversation the record
# lacks by this door. The claim is asked first, so whatever a file says otherwise
# (a restored Brain, a stale or edited copy, even of a Conversation that exists), the
# record is believed and the file corrected. Only with no claim does a file's
# Conversation count, if the record holds it: a Magnet's from before claims. A file
# that cannot be written refuses nothing either: the request stands, and the claim
# keeps answering until the file can be told.
#
# AN OPERATION KEY IS REQUIRED: without one a retry is not the same request, and
# the crash it follows would duplicate the work. A retry is answered from where the
# request first went, not routed afresh, so it holds if the workspace has since
# been deleted; it writes nothing new, and only what the record says never ran is
# started. Starting that goes through the same `dispatch_soon`, under the authority
# the request recorded. It is the requester asking again, and nothing asks for them.
#
# A REQUEST FROM A WORKSPACE MAY SELECT ITS OBJECTS, and what it first selected is
# what the work was asked with: a retry that selects otherwise is refused, like any
# other request under that key. The act keeps the selection as `selection`, in order,
# and only when one was made, so a request that made none reads as it always did.
# It keeps digests and not `wob-` ids, because `history` shows an act's detail to
# whoever can read its Conversation, an object's id is a hash of its ref, and under a
# `destination` the act names no workspace at all. Each digest covers the workspace
# too, so it says nothing without that workspace's id. Who already has the id and a
# ref can still test whether that ref was selected: that is all it answers.
# `digest` stays what it was, because `_routed_from` recomputes it for the W asked
# about, and that is a different question from which of W's objects were selected.

ORIGINS = ("workspace", "magnet", "conversation")
DESTINATIONS = ("conversation", "magnet")
CONVERSATION_CLAIMED = "own-conversation-claimed"
REQUEST_ROUTED = "agent-request-routed"


def selection_digest(wid, oid) -> str:
    """What the record keeps of workspace `wid`'s object `oid` being selected."""
    from mentis.conversation import anchors
    return anchors.digest({"workspace": wid, "object": oid})


def _selected(body, origin):
    """(the ids `objects` selects, in order, or None for none selected, None), or
    (None, the 400). Null is not leaving it out: read as everything, it would be
    a selection that broadened. An empty list selects nothing."""
    from . import workspace_manifest as wm
    if "objects" not in body:
        return None, None
    if origin[0] != "workspace":
        return None, _bad("only a request from a workspace selects \"objects\": "
                          "one from a Magnet or a Conversation has none")
    got = body["objects"]
    if not isinstance(got, list) or len(got) > wm.MAX_OBJECTS:
        return None, _bad(f"\"objects\" is a list of at most {wm.MAX_OBJECTS} "
                          "of this workspace's object ids")
    if not all(isinstance(o, str) and wm._OBJECT_ID.fullmatch(o) for o in got):
        return None, _bad("\"objects\" names objects by their wob- ids")
    if len(set(got)) != len(got):
        return None, _bad("\"objects\" names the same object twice")
    return got, None


def _one_named(body, field, kinds):
    """(kind, ref) from `{"<kind>": "<ref>"}`, or (None, the 400)."""
    got = body.get(field)
    if isinstance(got, dict) and len(got) == 1:
        (kind, ref), = got.items()
        if kind in kinds and isinstance(ref, str) and ref.strip():
            return (kind, ref.strip()), None
    return None, _bad(f"\"{field}\" names one of {list(kinds)}: "
                      f"{{\"{kinds[0]}\": \"<id>\"}}")


def _claimed(st, kind, ref) -> str | None:
    """The Conversation the record holds as this workspace's or Magnet's own, asked
    before its file is believed. A scan, as `act` has no index, as the key's own
    lookup is on every request. The first claim stands."""
    got = st.corpus.operational(act=CONVERSATION_CLAIMED, detail_is={kind: ref},
                                limit=1)
    return got[0]["conversation"] if got else None


def _claim(st, by, kind, ref, cid) -> None:
    """Inside the transaction that opened or first activated `cid`. An opening
    replayed by its key may be claimed already."""
    if not _claimed(st, kind, ref):
        st.cv.record_act(actor=by, act=CONVERSATION_CLAIMED, conversation=cid,
                         detail={kind: ref})


def _magnet_config(st, mid) -> dict:
    from . import arrangements
    import mentis.magnet as magnet
    root = st.corpus.root
    config = magnet.read(root, mid)
    if config is None:
        arrangements.lift_all(root)
        config = magnet.read(root, mid)
    if config is None:
        raise arrangements.Declined("state", magnet.MISSING)
    return config


def _magnet_key_request(mid) -> dict:
    """What the Magnet's stable key, `magnet-conversation:<id>`, is recorded as asking."""
    return {"route": "fluid-magnet-conversation", "magnet": mid}


def _magnet_conversation_name(st, mid) -> str:
    """What a Magnet's own Conversation is called when nobody names it: as the Magnet is
    drawn (the Conversation it alone reads, else the name on its zone), else what its
    lone operation is called, said as a Magnet's so it can't be taken for its source.
    With none of those, its id. Reads only, and a name never refuses anything: what
    can't be read, or can't be written to the record, is passed over."""
    import mentis.magnet as magnet
    from . import arrangements
    root = st.corpus.root
    try:
        config = magnet.read(root, mid) or {}
    except magnet.Unreadable:
        config = {}
    sources = config.get("sources") or []
    operations = (config.get("processing") or {}).get("operations") or []
    told = [st.cv.conversation_name(sources[0]["conversation"])
            if len(sources) == 1 and sources[0]["kind"] == "conversation" else None,
            arrangements.zone_name(root, mid),
            operations[0].get("name") if len(operations) == 1 else None]
    for name in told:
        if isinstance(name, str) and name.strip():
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                continue
            return f"{name.strip()} (Magnet)"
    return f"Magnet {mid}"


def _open_under_magnet_key(st, mid, body, *, written_by) -> tuple[int, dict, list]:
    """Open a Magnet's one Conversation under its stable key, whoever asks and by
    whichever door, or answer the one already there (`replayed`). The client's `op`
    is not used, and a name left out or blank is the Magnet's own. The key's request
    doesn't hold the name, so naming it changes nothing about the one claim."""
    said = body.get("name")
    named = ({"name": _magnet_conversation_name(st, mid)}
             if said is None or (isinstance(said, str) and not said.strip()) else {})
    return open_conversation(
        st, {**body, **named, "op": f"magnet-conversation:{mid}"},
        written_by=written_by, operation_request=_magnet_key_request(mid),
        operation_across_actors=True)


def _own_conversation(st, by, kind, ref, wrote) -> tuple[str, bool]:
    """(the Conversation this workspace or Magnet has, whether this created it),
    inside the request's transaction. With no claim and no usable file, a Magnet's
    key may still hold one from before claims: that is claimed, not repeated."""
    from . import workspace_manifest as wm
    corpus = st.corpus
    if kind == "workspace":
        manifest = wm.held(corpus.root, ref)
        named, name = manifest.get("conversation"), manifest["name"]
    else:
        named, name = _magnet_config(st, ref).get("conversation"), None
    return _own_from(st, by, kind, ref, named, name, wrote)


def _own_from(st, by, kind, ref, named, name, wrote,
              claim_named=False) -> tuple[str, bool]:
    """`_own_conversation`, given what its file names, for a door that has already
    said what it reads of that file (`mentis.magnet.activation`). `claim_named` is
    that door's: what the file names becomes the claim, in its transaction."""
    corpus, cv = st.corpus, st.cv
    cid = _claimed(st, kind, ref)
    if cid:
        return cid, False
    if named and corpus.read([named]) and cv._is_kind(named, "conversation"):
        if claim_named:
            _claim(st, by, kind, ref, named)
        return named, False
    body = {"author": by, **({"name": name} if name else {})}
    if kind == "magnet":
        status, out, _ = _open_under_magnet_key(st, ref, body,
                                                written_by=lambda: wrote)
    else:
        status, out, _ = open_conversation(st, body, written_by=lambda: wrote)
    if status >= 300:
        raise _Undone((status, out, []))
    _claim(st, by, kind, ref, out["conversation"])
    return out["conversation"], not out.get("replayed")


def _tell_the_file(st, own, cid) -> None:
    """Let the file say what the record does, after the commit. The request already
    stands, so a file that cannot take it refuses nothing: `_claimed` still answers,
    and the next request tries again."""
    from . import workspace_manifest as wm
    import mentis.magnet as magnet
    root = st.corpus.root
    kind, ref = own
    try:
        if kind == "workspace":
            if wm.held(root, ref).get("conversation") != cid:
                wm.set_conversation(root, ref, cid)
        elif _magnet_config(st, ref).get("conversation") != cid:
            magnet.correct_conversation(root, ref, cid)
    except (OSError, ValueError, LookupError, RuntimeError):
        pass


def _never_started(st, start) -> bool:
    """Whether the record says nothing ever became of this start: no run, no end, no
    recorded failure, no answer, and the same carrier. Continuing work that did fail
    is somebody's act, not a retry's."""
    cv, expectation = st.cv, start.get("expectation")
    if not expectation:
        return False
    from mentis.operational.owner_stop import parked_over
    if parked_over(cv, expectation):
        return False
    state = cv.expectation_state(expectation)
    if (state["response_present"] or state["withdrawn"] or state["lapsed"]
            or state["failures"] or state["live_execution"]
            or state["expected_of"] != start.get("participant")):
        return False
    return not any(a["act"] == "execution-started"
                   for a in cv._own_acts(expectation))


def _hand_on(st, start) -> None:
    """Start one, once in this process, under the door's lock. It is noted before it
    is started: `dispatch_soon` then records what becomes of it."""
    import mentis.web as _web
    expectation = start.get("expectation")
    st.requests_started.add(expectation)
    try:
        _web.dispatch_soon(st, **start)
    except Exception:
        st.requests_started.discard(expectation)
        raise


def _answered(st, answer, rule, cid, created) -> tuple[int, dict, list]:
    """The post's answer, with its route and a cursor read after the commit."""
    status, out, _ = answer
    return status, {**out, "cursor": _read.change_cursor(st.corpus.advance()),
                    "route": {"rule": rule, "conversation": cid,
                              "created": created}}, []


def _retried(st, prior, operation, digest, selection,
             *, written_by, defer_dispatch=False) -> tuple[int, dict, list]:
    """The same key again: to where it first went, whatever has happened since. The
    file is told, and whatever the record says never started is started."""
    detail, cid = prior["detail"], prior["conversation"]
    if detail["digest"] != digest or detail.get("selection") != selection:
        return 422, {"error": "this operation key was already used for a "
                              "different request; nothing was written. A new "
                              "occurrence uses a new key",
                     "op": detail["op"], "first": prior["id"],
                     "refused": True}, []
    answer = write_post(st, {**operation, "conversation": cid},
                        written_by=written_by, _request=True)
    if answer[0] != 200:
        return answer
    if detail.get("own"):
        _tell_the_file(st, detail["own"], _claimed(st, *detail["own"]) or cid)
    if defer_dispatch:
        # Send back has the posting operation's replay semantics: a receipt
        # starts nothing twice, including while its first start is queued.
        return _answered(st, answer, detail["rule"], cid, False)
    for start in detail["starts"]:
        if (start.get("expectation") not in st.requests_started
                and _never_started(st, start)):
            from . import message_context as MC
            from mentis.conversation.versions import Refused
            try:
                MC.accepted(st.cv, start.get("expectation"))
            except Refused:
                continue  # replay returns its original receipt, never executes edited work
            _hand_on(st, start)
    return _answered(st, answer, detail["rule"], cid, False)


def _first_time(st, operation, by, op, digest, selection, rule, kind, ref,
                *, written_by, managed=None, submitted_digest=None,
                origin=None, destination=None, definition=None,
                check_definition=None, defer_dispatch=False,
                after_post=None, authorization=None) -> tuple[int, dict, list]:
    """Everything the record holds of this request, committed as one, then the file,
    then the runs: see above."""
    from contextlib import nullcontext
    import mentis.magnet as magnet
    corpus = st.corpus
    own = (kind, ref) if kind in ("workspace", "magnet") else None
    created = False
    with (magnet.asking_for_conversation(corpus.root, ref) if kind == "magnet" and not managed
          else nullcontext()):
        try:
            with corpus.atomic():
                wrote = written_by()
                from . import message_context as MC
                if managed:
                    question, references = MC._selections(st.cv, managed["magnet"],
                        _claimed(st, "magnet", managed["magnet"]) or
                        managed.get("conversation"), managed["selector"])
                    if question != managed["question"] or references != managed["references"]:
                        MC.refuse("stale-selection", "a selected object changed before commit", status=409)
                fence = MC.activate(st.cv, by) if managed else None
                if own and kind == "magnet" and definition is not None:
                    name = (definition.definition.get("identity") or {}).get("name") or ref
                    cid, created = _own_from(st, by, kind, ref,
                        definition.conversation, f"{name} (Magnet)", wrote, claim_named=True)
                elif own:
                    cid, created = _own_conversation(st, by, kind, ref, wrote)
                else:
                    cid = ref
                answer = write_post(st, {**operation, "conversation": cid},
                                    written_by=lambda: wrote, _request=True)
                if answer[0] != 200:
                    raise _Undone(answer)
                starts = answer[2]
                # The key already answered on another door: that door's, and
                # nothing of it is this door's to start.
                if not answer[1].get("replayed"):
                    if authorization is not None:
                        from mentis.magnet import scope
                        # The Turn comes ONLY from this write, never the client.
                        # A refusal rolls back the post and every request with it;
                        # dispatch cannot start until this transaction commits.
                        scope.authorize(st, managed["magnet"],
                            turn=answer[1]["post"], opens=authorization["opens"],
                            by=by, op="request:" + MC.digest({"op": op}))
                    st.cv.record_act(
                        actor=by, act=REQUEST_ROUTED, conversation=cid,
                        turn=answer[1]["post"],
                        detail={"op": op, "digest": digest, "rule": rule,
                                "own": own, "starts": starts,
                                **({"submitted_digest": submitted_digest,
                                    "managed_context_version": MC.VERSION,
                                    "managed_context": MC.bind(managed,
                                        turn=answer[1]["post"], conversation=cid,
                                        writer=wrote, op=op, origin=origin,
                                        destination=destination, fence=fence,
                                        authored_parts=corpus.read([answer[1]["post"]])[0]["body"]["parts"])} if managed else {}),
                                **({} if selection is None
                                   else {"selection": selection})})
                    if after_post is not None:
                        after_post(answer[1]["operation"])
                if check_definition is not None:
                    # B detects a writer bypassing its boundary on hold exit.
                    # Exit that inner hold BEFORE this transaction commits;
                    # the outer public boundary stays held through commit.
                    check_definition()
        except _Undone as undone:
            return undone.answer
        if own:
            _tell_the_file(st, own, cid)
    if not defer_dispatch:
        for start in starts:
            _hand_on(st, start)
    status, out, _ = _answered(st, answer, rule, cid, created)
    return status, out, starts if defer_dispatch else []


def agent_request(st, body, *, written_by, brain=None,
                  _input_handover=None, _defer_dispatch=False,
                  _after_post=None) -> tuple[int, dict, list]:
    """`POST /fluid/api/requests` {from, destination?, objects?, author, parts,
    action, dispatch, ..., op}: `posts`' body, with `from` where it was started, one
    of `{"workspace": id}`, `{"magnet": id}` or `{"conversation": id}`, in place of
    `conversation`, and an operation key it cannot go without. A request from a
    workspace may name a `destination`, `{"conversation": id}` or `{"magnet": id}`,
    which overrides that workspace's own Conversation and creates nothing for it,
    and may select `objects`, an ordered list of `wob-` ids it holds, which routes
    nothing: left out, the work may read all it holds. The answer is `posts`', with `route` {rule, conversation, created}. It starts
    its own dispatches, under the lock, so a retry cannot start them again.
    The internal input adapter can supply a server-built handover, record its
    receipt inside the transaction, and return starts to its door after commit.
    None of these call arguments is taken from the public request body."""
    from mentis.conversation import anchors
    from mentis.conversation.versions import Refused as ContextRefused
    from mentis.magnet import snapshot as SNAP
    from mentis.magnet import scope
    from . import _checks as W
    from . import arrangements
    from . import workspace_manifest as wm
    if "conversation" in body:
        return _bad("a request says where it was started, in \"from\", and may "
                    "name a \"destination\": not \"conversation\"")
    origin, bad = _one_named(body, "from", ORIGINS)
    if bad:
        return bad
    objects, bad = _selected(body, origin)
    if bad:
        return bad
    destination = None
    if body.get("destination") is not None:
        if origin[0] != "workspace":
            return _bad("only a request from a workspace names a "
                        "\"destination\": one from a Magnet or a Conversation "
                        "goes to that Conversation")
        destination, bad = _one_named(body, "destination", DESTINATIONS)
        if bad:
            return bad
    by, bad = _author(st, body)
    if bad:
        return bad
    op = body.get("op")
    if not isinstance(op, str) or not op.strip():
        return _bad("a request needs an operation key, \"op\": it is what makes "
                    "a retry the same request")
    operation = {**{k: v for k, v in body.items()
                    if k not in ("from", "destination", "objects", "magnet_authorization")},
                 "author": by}
    digest = anchors.digest({"from": origin, "destination": destination})
    selection = (None if objects is None
                 else [selection_digest(origin[1], o) for o in objects])
    root = st.corpus.root
    try:
        with W.asking(root, "requests"):
            from . import message_context as MC
            from mentis.fluid.inspect import brain_key
            from mentis.operational.work_overview import owner_of
            mid = MC.route(st.cv, origin, destination)
            authorization = body.get("magnet_authorization")
            if "magnet_authorization" in body:
                if (not mid or not isinstance(authorization, dict)
                        or set(authorization) != {"opens"}):
                    return _bad('magnet_authorization names only "opens" on a managed Magnet request')
                if body.get("action") not in ("ask-mentis", "ask-participant"):
                    return _bad("authorize an asking exchange, not a record-only post")
            prior = st.corpus.operational(actor=by, act=REQUEST_ROUTED,
                                          detail_is={"op": op}, limit=1)
            managed = mid or (prior and prior[0]["detail"].get("managed_context"))
            if managed:
                if not brain or brain != brain_key(st.corpus):
                    return 409, {"error": "confirm this serving Brain before sending",
                                 "kind": "BrainUnconfirmed" if not brain else "BrainChanged",
                                 "refused": True}, []
                if by != owner_of(st.cv):
                    return 403, {"error": "managed requests are authored by the recorded owner", "refused": True}, []
                submitted_digest = MC.digest(body if _input_handover is None else
                    {"body": body, "input_handover": _input_handover})
                if prior:
                    prior_detail = prior[0]["detail"]
                    if (prior_detail.get("managed_context") is not None
                            or "managed_context_version" in prior_detail):
                        if prior_detail.get("submitted_digest") != submitted_digest:
                            return 409, {"error": "this operation key was used for different managed intent",
                                         "refused": True, "code": "conflicting-replay"}, []
                    else:
                        MC.gate(body)
                        if (prior_detail.get("digest") != digest
                                or prior_detail.get("selection") != selection
                                or body.get("magnet_context") is not None):
                            return 409, {"error": "this operation key was used for different managed intent",
                                         "refused": True, "code": "conflicting-replay"}, []
                        # A genuine pre-cutover receipt uses its original key
                        # identity, never a fabricated v1 binding. Positive
                        # routed/fence evidence and the retained gate still
                        # have to pass before this legacy replay is answered.
                        MC.accepted(st.cv, turn=prior[0].get("turn"))
            if prior:
                return _retried(st, prior[0], operation, digest, selection,
                                written_by=written_by, defer_dispatch=_defer_dispatch)
            if origin[0] == "workspace":
                holds = {o["id"] for o in wm.held(root, origin[1])["objects"]}
                absent = [o for o in objects or () if o not in holds]
                if absent:
                    return 422, {"error": f"{origin[1]} does not hold every object "
                                          "this selects; nothing was written",
                                 "objects": absent, "refused": True}, []
            kind, ref = destination or origin
            if mid:
                from contextlib import ExitStack
                import mentis.magnet as magnet
                with magnet.asking_for_conversation(root, mid), magnet.boundary(root):
                    arrangements.lift_all(root)
                    with ExitStack() as hold:
                        definition = hold.enter_context(SNAP.holding(root, mid))
                        context = MC.prepare(st, mid, body, definition, brain,
                            destination_conversation=ref if kind == "conversation" else None,
                            input_handover=_input_handover)
                        if authorization is not None:
                            if context["selector"].get("perspective"):
                                raise scope.Refused(scope.SYNTHESIS_NEVER)
                            if not definition.conversation:
                                raise scope.Refused("Create this Magnet's Conversation before authorizing an exchange")
                        return _first_time(st, operation, by, op, digest, selection,
                            "destination" if destination else origin[0], kind, ref,
                            written_by=written_by, managed=context,
                            submitted_digest=submitted_digest, origin=origin,
                            destination=destination, definition=definition,
                            defer_dispatch=_defer_dispatch,
                            after_post=_after_post,
                            authorization=authorization,
                            check_definition=hold.close)
            return _first_time(st, operation, by, op, digest, selection,
                               "destination" if destination else origin[0],
                               kind, ref, written_by=written_by)
    except ContextRefused as exc:
        return exc.refusal.get("status", 422), exc.refusal, []
    except scope.Refused as exc:
        return 422, {"error": str(exc), "refused": True,
                     "code": "authorization-refused"}, []
    except (SNAP.Stale, SNAP.NotSerialized) as exc:
        return 409, {"error": str(exc), "refused": True, "code": "definition-not-serialized"}, []
    except SNAP.NotCanonical as exc:
        return 422, {"error": str(exc), "refused": True, "code": "definition-not-canonical"}, []
    except wm.NotFound as exc:
        return 404, {"error": str(exc).strip("'\""), "kind": "NotFound"}, []
    except wm.Gone as exc:
        return 410, {"error": str(exc).strip("'\""), "kind": "Gone"}, []
    except arrangements.Declined as exc:
        return 422, {"error": str(exc), "refused": True, "reason": exc.reason}, []
    except arrangements.Refused as exc:
        return _bad(str(exc))
    except arrangements.Unreadable as exc:
        return 409, {"error": str(exc), "kind": "Unreadable"}, []


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


def _command(st, by, body, request, fn, *, status=200,
             operation_across_actors=False):
    """Run one F3 command under the author's operation key: the same key and
    request is answered with what it first came to (200, `replayed`) and
    writes nothing again (`anchors.keyed`). A refusal is 422 and keeps no
    key. The cursor is read after the commit, so a feed read from it has
    seen this."""
    from mentis.conversation import anchors
    from mentis.conversation.versions import Refused
    try:
        out = anchors.keyed(st.cv, by, body.get("op"), request, fn,
                            across_actors=operation_across_actors)
    except Refused as refused:
        return _refused(refused.refusal)
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


def open_conversation(st, body, *, written_by,
                      operation_request=None,
                      operation_across_actors=False) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations` {author, name?, op?}: open one. With
    no name it is opened under a provisional one ("Unnamed <when>")."""
    by, bad = _author(st, body)
    if bad:
        return bad
    name, bad = _name_field(body)
    if bad:
        return bad
    op = body.get("op")
    if (operation_request is None and isinstance(op, str)
            and op.startswith("magnet-conversation:")):
        return _bad('the "magnet-conversation:" operation-key prefix is '
                    "reserved for the Magnet conversation route")
    if (operation_request is None and isinstance(op, str)
            and op[:4].lower() == "wsp-"):
        return _bad('"wsp-" names a workspace, so it is not a Conversation\'s '
                    "key")
    cv = st.cv

    def fn():
        wrote = written_by()
        cid = cv.open_conversation(name, about="", attributed_to=by,
                                   written_by=wrote, provisional=name is None)
        # Whoever opened it takes part in it, as production's door has it.
        cv.join(by, cid, attributed_to=by, written_by=wrote)
        return {"conversation": cid, "name": cv.conversation_name(cid),
                "provisional": name is None}
    request = operation_request or {"route": "fluid-conversation-open",
                                    "name": name}
    answer = _command(st, by, body, request, fn, status=201,
                      operation_across_actors=operation_across_actors)
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


def dispatching_now(st) -> set:
    """The requests this process is dispatching now: handed on and not yet
    finished (`dispatch.dispatch_soon`), and those noted as started by this
    door before their dispatch thread was asked for (`_hand_on`)."""
    from mentis.web.dispatch import _DISPATCHING_LOCK
    # THE LOOKUP, THE EMPTY CHECK AND THE COPY IN ONE CRITICAL SECTION: a
    # hand-off between a test made outside the lock and the copy is missed
    with _DISPATCHING_LOCK:
        held = getattr(st, "dispatching", None)
        now = set(held) if held else set()
    return now | set(getattr(st, "requests_started", ()) or ())


def in_flight(st, cid) -> dict:
    """What only this door observes of the work in one Conversation: the runs
    this process holds there (`read._live`, the row's `working`). What the
    record says is in flight -- runs and work waiting on the owner -- the
    domain reads itself (`Conversations.work_in_flight`); this only adds."""
    running = len(_read._live(st.cv, getattr(st, "agents", None)).get(cid)
                  or [])
    return {"running": running, "waiting": 0}


def conversation_state(st, cid, change, body) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations/<id>/<archive|unarchive|trash|restore>`
    {author, because?, op?}: where the Conversation is listed. The same door
    and author check as a rename; Trash is refused while work is in flight
    (422, `code` "work-in-flight", with `running` and `waiting`)."""
    by, bad = _author(st, body)
    if bad:
        return bad
    because = body.get("because")
    if because is not None and not isinstance(because, str):
        return _bad('"because" is words')

    # TRASH'S CHECK, READ BEFORE THE OPERATION KEY'S WRITE TRANSACTION: under
    # it the walk would hold the writer lock (`trash_check`). Re-checked
    # cheaply inside; if the record moved there, it is read again HERE,
    # outside the writer, a few times.
    from mentis.conversation import STATE_CHECK_TRIES
    answer = None
    for _attempt in range(STATE_CHECK_TRIES if change == "trash" else 1):
        checked = None
        if change == "trash":
            try:
                checked = st.cv.trash_check(
                    cid, dispatching=dispatching_now(st))
            except Exception:                             # noqa: BLE001
                checked = None  # not a conversation: the change says so

        def fn(checked=checked):
            got = st.cv.change_conversation_state(
                cid, change, by=by, because=because,
                in_flight=in_flight(st, cid) if change == "trash" else None,
                checked=checked)
            return {"conversation": cid, "state": got["state"],
                    "was": got["was"], "act": got["act"]}
        answer = _command(st, by, body, {"route": f"fluid-conversation-{change}",
                                         "conversation": cid}, fn)
        if not (answer[0] == 422 and answer[1].get("code") == "record-moved"):
            break
    return _project_conversation(answer, st, cid)


def delete_conversation(st, cid, body) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations/<id>/delete` {author, token}: PERMANENT
    DELETION (`conversation.erasure.delete`). The owner only (a worker grant
    never reaches here); from Trash; Trash's work check must pass; `token`
    must be the impact read now (`GET .../deletion-impact`), else 409
    `impact-changed`. A retry of a deletion already done with the same token
    answers what it did."""
    from mentis.conversation import erasure
    from mentis.conversation.versions import Refused
    by, bad = _author(st, body)
    if bad:
        return bad
    token = body.get("token")
    if not isinstance(token, str) or not token:
        return _bad('"token" is the impact token from deletion-impact')
    if st.cv.conversation_state(cid) == "deleted":
        tomb = erasure.tombstone(st.cv, cid)
        act = st.corpus.operational(id=tomb["act"])
        same = act and ((act[0]["detail"].get("authorized") or {}).get(
            "impact_token") == token)
        if same:
            # A REPLAY FINISHES WHAT IS NOT FINISHED (review finding 7): a
            # deletion whose physical cleanup is not `completed` -- a crash
            # between commit and cleanup, a held snapshot, a locked file --
            # gets one more attempt here, recorded, and says what it found
            physical = erasure.cleanup_status(st.cv, cid)
            if physical.get("status") != "completed":
                physical = erasure.cleanup(st.cv, cid, by=by)
                tomb = erasure.tombstone(st.cv, cid)
            return 200, {"conversation": cid, "deleted": True,
                         "replayed": True, "physical_cleanup": physical,
                         "tombstone": tomb}, []
        return 409, {"error": "This conversation was already permanently "
                              "deleted.", "code": "conversation-deleted",
                     "conversation": cid, "refused": True}, []
    for _attempt in range(3):
        try:
            got = erasure.delete(
                st.cv, cid, by=by, token=token, route="fluid",
                in_flight=in_flight(st, cid),
                dispatching=dispatching_now(st), cleanup_later=True)
        except Refused as refused:
            code = refused.refusal.get("code")
            if code == "record-moved":
                continue
            status = {"impact-changed": 409, "not-in-trash": 409,
                      "owner-only": 403, "work-in-flight": 422}.get(code, 422)
            return status, {**refused.refusal, "refused": True}, []
        return 200, {**got, "cursor": _read.change_cursor(
            st.corpus.advance())}, []
    return 409, {"error": "the record kept changing while the deletion was "
                          "being checked; try again", "code": "record-moved",
                 "conversation": cid, "refused": True}, []


def cleanup_conversation(st, cid, body) -> tuple[int, dict, list]:
    """`POST /fluid/api/conversations/<id>/cleanup` {author}: the owner's
    Finish cleanup -- one more PHYSICAL cleanup attempt for a permanently
    deleted Conversation, verified and recorded
    (`conversation.erasure.cleanup`). The deletion itself is never touched.
    Owner only; 409 `not-deleted` for a Conversation that is not deleted."""
    from mentis.conversation import erasure
    from mentis.operational.work_overview import owner_of
    by, bad = _author(st, body)
    if bad:
        return bad
    if by != owner_of(st.cv):
        return 403, {"error": "only the owner can finish a deletion's "
                              "cleanup", "code": "owner-only",
                     "conversation": cid, "refused": True}, []
    if st.cv.conversation_state(cid) != "deleted":
        return 409, {"error": "this conversation has not been permanently "
                              "deleted", "code": "not-deleted",
                     "conversation": cid, "refused": True}, []
    got = erasure.cleanup(st.cv, cid, by=by)
    return 200, {"conversation": cid, "deleted": True,
                 "physical_cleanup": got,
                 "cursor": _read.change_cursor(st.corpus.advance())}, []


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


def set_send_back(st, sid, body, *, written_by, brain=None) -> tuple[int, dict, list]:
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
                                      op=body.get("op"), brain=brain, intent=body)
    except Refused as refused:
        status, answer, later = _refused(refused.refusal)
        return refused.refusal.get("status", status), answer, later
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


def _door_refused(handler, parsed, has_body) -> bool:
    """The client header, a worker grant and the declared type, in that order. True
    if one refused, and answered."""
    from mentis.worker import CAPABILITY_HEADER
    if handler._missing_client(parsed.path, "POST"):
        return True
    if handler.headers.get(CAPABILITY_HEADER):
        handler._send(403, {"error": "a worker grant authorises "
                                     "/api/worker and nothing else",
                            "kind": "PermissionError",
                            "asked_for": parsed.path})
        return True
    ctype = (handler.headers.get("Content-Type") or "").split(";")[0].strip()
    if has_body and ctype.lower() != "application/json":
        handler._send(415, {"error": "a JSON route takes "
                                     "Content-Type: application/json",
                            "kind": "PermissionError"})
        return True
    return False


def _activate(handler, parsed, segment, length) -> None:
    """A Magnet's activation on Python's own door: Python alone, or the front's rule
    rolled back. Its door runs before the body is read, and a body past the limit is
    never read. The length was read by value (`_Handler._declared_length`), so no
    failure of `int()` reaches here."""
    from mentis.magnet import activation
    if _door_refused(handler, parsed, length > 0):
        return None
    if length > activation.PUBLIC_BODY_MOST:
        # In the contract's words, which this interpreter's table doesn't have yet.
        return handler._send(413, activation.PUBLIC_BODY_TOO_LARGE,
                             reason="Content Too Large")
    status, out = activation.public(handler.state, segment,
                                    handler._read_body(length))
    return handler._send(status, out)


def handle_post(handler, parsed, length: int) -> None:
    """Answer one POST under `/fluid/api/` on the production handler.

    THE SAME DOORS AS PRODUCTION'S JSON POSTS, in the same order: the Host
    check and the framing checks have already run (`do_POST`); then the body
    is read whole by its Content-Length (production sets no other limit on a
    JSON body, and neither does this), `X-Mentis-Client` is required, a worker
    grant is refused, and a body is JSON by its declared type. A path that
    names no command is 405, before anything is read, as in F0.
    """
    from . import PREFIX
    rest = parsed.path[len(PREFIX):].rstrip("/")
    which = command_of(rest)
    if which is None:
        return handler._send(405, {"error": "the Fluid API answers GET, and "
                                            "POST only at /fluid/api/posts, "
                                            "/fluid/api/requests, "
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
                                            "<id>/name, /members, "
                                            "/archive, /unarchive, /trash, "
                                            "/restore, /delete or /cleanup, "
                                            "/fluid/api/arrangements/<key>, "
                                            "/fluid/api/arrangements/<key>/"
                                            "magnets, /magnets/<id>/"
                                            "reconfigure or /remove, "
                                            "/fluid/api/magnets/lift, "
                                            "/fluid/api/magnets/propose, "
                                            "/fluid/api/magnets/<id>/delete, "
                                            "/conversation, /activate or "
                                            "/authorize, "
                                            "/fluid/api/magnets/<id>/perspectives, "
                                            "/perspectives/selected, "
                                            "/perspectives/<topic>/question, /rename, "
                                            "/challenge, /retire, /resume, /branch, "
                                            "/prepare, /bind, /reconcile, /finalize "
                                            "or /answer, "
                                            "/fluid/api/workspaces, "
                                            "/fluid/api/workspaces/<id>/rename, "
                                            "/objects, /objects/<oid>/remove, "
                                            "/reorder or /delete, "
                                            "/fluid/api/settings, "
                                            "/fluid/api/work/<id>/workflow, "
                                            "and /fluid/api/layouts, "
                                            "/layouts/defaults or "
                                            "/layouts/<id>/delete",
                                   "kind": "PermissionError"})
    if which[0] == MAGNET_ACTIVATE:
        return _activate(handler, parsed, which[1], length)
    if which[0] == "magnet-perspective":
        # These new owner writes require a confirmed Brain, while retaining
        # the handler's existing owner-session and wrong-Brain checks.
        from mentis.web import BRAIN_HEADER
        if not handler.headers.get(BRAIN_HEADER):
            return handler._send(409, {"error": "confirm this Brain before a Perspective write",
                                       "kind": "BrainUnconfirmed"})
    if which[0] == MAGNET_AUTHORIZE:
        from mentis.web import BRAIN_HEADER
        if not handler.headers.get(BRAIN_HEADER):
            return handler._send(409, {
                "error": "confirm this Brain before authorizing an exchange",
                "kind": "BrainUnconfirmed"})
    raw = handler._read_body(length)
    if _door_refused(handler, parsed, bool(raw)):
        return
    if which[0] == REQUESTS:
        from . import message_context as MC
        from mentis.conversation.versions import Refused
        try:
            MC.check_raw_selector(raw)
        except Refused as exc:
            return handler._send(exc.refusal.get("status", 422), exc.refusal)
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
        elif which[0] == REQUESTS:
            from mentis.web import BRAIN_HEADER
            status, out, later = agent_request(st, body, written_by=writer,
                                               brain=handler.headers.get(BRAIN_HEADER))
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
        elif which[0] in STATE_VERBS:
            status, out, later = conversation_state(st, which[1], which[0],
                                                    body)
        elif which[0] == CONVERSATION_DELETE:
            status, out, later = delete_conversation(st, which[1], body)
        elif which[0] == CONVERSATION_CLEANUP:
            status, out, later = cleanup_conversation(st, which[1], body)
        elif which[0] == ARRANGEMENTS:
            status, out, later = save_arrangement(st, which[1], body)
        elif which[0] == MAGNET_PROPOSE:
            status, out, later = magnet_proposal(st, body)
        elif which[0] == MAGNET_CREATE or which[0] in MAGNET_ACTS.values():
            status, out, later = magnet_command(st, which[0], which[1], body)
        elif which[0] == MAGNET_LIFT \
                or which[0] in MAGNET_DEFINITION_ACTS.values():
            status, out, later = magnet_definition_command(
                st, which[0], which[1], body, written_by=writer)
        elif which[0] == MAGNET_AUTHORIZE:
            from mentis.web import BRAIN_HEADER
            status, out, later = magnet_authorize(
                st, which[1], body, brain=handler.headers.get(BRAIN_HEADER))
        elif which[0] in (WORKSPACES, WORKSPACE_REMOVE) \
                or which[0] in WORKSPACE_ACTS.values():
            status, out, later = workspace_command(st, which[0], which[1], body)
        elif which[0] == SETTINGS:
            status, out, later = settings_command(st, body)
        elif which[0] == "set-send-back":
            from mentis.web import BRAIN_HEADER
            status, out, later = set_send_back(st, which[1], body,
                written_by=writer, brain=handler.headers.get(BRAIN_HEADER))
        elif which[0] in _ACTS:
            status, out, later = _ACTS[which[0]](st, which[1], body,
                                                 written_by=writer)
        elif which[0] == "magnet-perspective":
            from mentis.magnet import perspectives
            from mentis.conversation.versions import Refused
            bits = which[1].split("/")
            mid = bits[0]
            topic = bits[2] if len(bits) == 4 else None
            verb = bits[3] if len(bits) == 4 else ("selected" if len(bits) == 3 else "create")
            try:
                out = perspectives.command(st, mid, topic, verb, body, written_by=writer())
                status = 422 if out.get("refused") else 200
                later = []
            except Refused as exc:
                status, out, later = (409 if exc.refusal.get("code") == "wrong-brain" else 422), exc.refusal, []
        elif which[0] in ("post-topics", "post-unfile", "post-move"):
            status, out, later = filing(st, which[1],
                                        which[0][len("post-"):], body)
        elif which[0] in (LAYOUTS, DEFAULTS, DELETE):
            status, out, later = layouts_command(st, which[0], which[1],
                                                 body)
        else:
            status, out, later = group(st, body, written_by=writer)
    except PermissionError as exc:
        # A destination file held outside the presentation lock is a server
        # filesystem failure, not a malformed client request.
        return handler._send(500, {"error": str(exc),
                                   "kind": "PermissionError"})
    except Exception as exc:                              # noqa: BLE001
        refusal = getattr(exc, "refusal", None)
        if isinstance(refusal, dict) and refusal.get("code") in NOT_WRITABLE:
            return handler._send(409, {**refusal, "refused": True})
        # As production answers a POST that raised: 400, with what it was.
        return handler._send(400, {"error": str(exc),
                                   "kind": type(exc).__name__})
    if (isinstance(out, dict) and out.get("code") in NOT_WRITABLE
            and status < 300):
        status = 409
    # STARTED ONLY ONCE ALL OF IT IS DURABLE, by production's own starter,
    # looked up when it is used so a test that replaces it replaces it here.
    for kw in later:
        _web.dispatch_soon(st, **kw)
    return handler._send(status, out)
