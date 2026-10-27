"""What is attached to a post: its anchors, and what points at them.

READ BY THE SAME FUNCTIONS PRODUCTION'S TURN READ USES. `GET /api/turns`
draws each Turn's `anchors` from `anchors.anchors_on`; this module draws a
post's from the same function, and adds beside each anchor its whole reaction
history (`anchors.interactions`), which says whose each reaction is -- what a
toolbar needs to know which reaction is the reader's own to change or
withdraw. Nothing here decides anything of its own.

  GET /fluid/api/posts/<id>/anchors          one post's
  GET /fluid/api/anchors?posts=<id>,<id>     several posts', in one read

ADDITIVE. `read.posts` keeps its shape; a client that never asks for anchors
reads exactly what it read before.

THE CHANGE FEED NAMES `anchors:<post>` (`changes_of`) whenever what this
read answers for that post may have changed: an anchor made in it, a reaction
recorded, changed or withdrawn, an anchored reply said, edited or deleted, a
deep dive opened from it, or the post itself edited or deleted (an anchor's
view says whether its version is current, and withholds a deleted Turn's
words). Where, never what: the client reads the anchors again.
"""
from __future__ import annotations

from mentis.conversation import CONTRIBUTION
from mentis.conversation import anchors as _anchors

from . import read as _read

#: The change feed's key for one post's annotations.
KEY = "anchors:"

#: Acts whose Turn is the post the anchor is in.
ON_THE_POST = ("anchor-created", "reaction-recorded", "reaction-changed")
#: Acts on a Turn that may move an anchor read: its own (version current,
#: deleted), or, when it is an anchored reply, the post it answers.
ON_A_TURN = ("turn-said", "turn-edited", "turn-deleted")


def _kind(e) -> str | None:
    return (e.get("definition") or {}).get("name")


def post_of(corpus, pid) -> dict:
    """The post this id names -- a Turn's own id, not a later version's.
    Raises `read.NotFound`."""
    got = corpus.read([pid]) if isinstance(pid, str) and pid else []
    if (not got or got[0].get("family") != "entry" or got[0].get("link")
            or _kind(got[0]) != CONTRIBUTION
            or corpus.history(pid)[0] != pid):
        raise _read.NotFound(pid)
    return got[0]


def of_post(cv, pid) -> dict:
    """One post's anchors as production's turn read draws them, each with its
    reaction history beside it (`history`)."""
    post_of(cv.corpus, pid)
    out = _anchors.anchors_on(cv, pid)
    for a in out:
        a["history"] = _anchors.interactions(cv, a["anchor"])["reactions"]
    return {"post": pid, "anchors": out}


def of_posts(cv, ids) -> dict:
    """Several posts' anchors, by post id; one the record does not hold as a
    post is listed under `missing`, never guessed at."""
    posts, missing = {}, []
    for pid in ids:
        try:
            posts[pid] = of_post(cv, pid)["anchors"]
        except _read.NotFound:
            missing.append(pid)
    return {"posts": posts, "missing": missing}


def _anchored_reply_of(corpus, turn) -> str | None:
    """The post an anchored reply answers, or None for any other Turn."""
    got = corpus.read([turn])
    if not got:
        return None
    for p in _anchors.anchor_parts((got[0].get("body") or {}).get("parts")):
        ref = p.get("ref")
        if isinstance(ref, str):
            return _anchors.anchor_turn(corpus, ref)
    return None


def changes_of(corpus, acts) -> set[str]:
    """`anchors:<post>` for every post whose anchors may read differently
    after these acts (the change feed's, in full). Asks the record only of
    the acts that can move an anchor."""
    posts = set()
    for a in acts:
        act, turn = a.get("act"), a.get("turn")
        detail = a.get("detail") or {}
        if act in ON_THE_POST and turn:
            posts.add(turn)
        elif act == "conversation-opened" and detail.get("opened_from"):
            posts.add(_anchors.anchor_turn(corpus, detail["opened_from"]))
        elif act == "material-deleted":
            # A reaction withdrawn, or deleted by somebody else.
            about = a.get("about") or []
            got = corpus.read(about[:1]) if about else []
            if got and _kind(got[0]) == _anchors.REACTION:
                aid = (got[0].get("body") or {}).get("about")
                if isinstance(aid, str):
                    posts.add(_anchors.anchor_turn(corpus, aid))
        elif act in ON_A_TURN and turn:
            if act != "turn-said" and corpus.links(
                    relation=_anchors.ANCHORS_IN, to=turn):
                posts.add(turn)
            posts.add(_anchored_reply_of(corpus, turn))
    return {KEY + p for p in posts if p}
