"""Durable Perspective identities and owner product reads/writes.

Topics and ordinary contributions are the record; immutable artifacts retain exact
wording. Nothing here runs work, collects, adopts material, or changes a definition.
"""
from __future__ import annotations

import base64
import json

from mentis import artifacts
from mentis.conversation import anchors, posting
from mentis.conversation.versions import Refused
from mentis.fluid.inspect import brain_key

from . import MAGNET_ID, read as definition

ACT = "magnet-perspective-event"
DOOR = "magnet-perspective"
FORMAT = "mentis.magnet-perspective"
DISCLOSURE = ("Selected evidence is recorded. This Magnet's answers are grounded in its own "
              "collection: a run carrying one of its exchanges reads that Magnet's recorded "
              "collection batches, the posts of its own Conversation and the references the owner "
              "selected, and every other Brain record or acquired source is refused at the door "
              "(mentis.magnet.scope). A Perspective answer and an evolving summary are grounded in "
              "the collected rows and nothing else; no authorization widens them. The owner may "
              "authorize one conversation exchange to reach a named outside source, and an answer "
              "that reached one says so in its provenance.")
# THE OWNER'S CORRECTION ent-d85254fe5e1b IS NOW ENFORCED, which is the only
# reason this was shut. A Magnet's configured sources set its collection scope,
# and a dispatched run carrying one of its exchanges is confined to that scope
# at the one door: `mentis.magnet.scope` decides what it may read,
# `worker.permitted` narrows what it may call, and `worker._magnet_confined`
# refuses every target outside it. Flipped in the same commit as
# `tests/test_magnet_scope.py`, which proves the refusals, and as the revised
# oracles in `tests/test_magnet_boundary_contract.py` that used to pin it shut.
# This is still a product availability gate and not itself a security
# boundary: the boundary is the door's.
GROUNDED_ANSWERS_ENABLED = True
PAGE_MAX = 100
TEXT_MAX = 65536

#: THE STANDING PERSPECTIVE: the evolving summary and an answered question are
#: ONE mechanism (plan adm-43ecee5872e9 §3 Part F). A Magnet's evolving summary
#: is not a second synthesis engine beside Perspectives; it is a Perspective
#: that is never retired, asking the one question a collection always answers,
#: re-answered whenever a collection brings rows the last answer did not read.
#: Its earlier answers become the superseded history the panel already renders.
STANDING_QUESTION = "What is the state of what this Magnet has gathered?"
STANDING_NAME = "What this Magnet has gathered"


def refuse(code, words, **detail):
    raise Refused({"refused": True, "code": code, "error": words, **detail})


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def text(value, label, *, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > TEXT_MAX:
        refuse("invalid-text", f"{label} must be text of at most {TEXT_MAX} characters")
    return value


def home(st, mid):
    if not isinstance(mid, str) or not MAGNET_ID.fullmatch(mid):
        refuse("invalid-magnet", "that is not a Magnet id")
    config = definition(st.corpus.root, mid)
    if not config:
        refuse("missing-magnet", "this Magnet has no definition")
    cid = config.get("conversation")
    if not cid or not st.cv._is_kind(cid, "conversation"):
        refuse("conversation-required", "Open the Magnet's own Conversation before creating a Perspective")
    return cid


def _rows(st, mid, topic=None, *, event=None, after=0, through=None, limit=101,
          newest=False, post=None):
    # SQL bounds rows before JSON decoding. No arbitrary history is loaded into
    # Python and no mutable Topic label participates in identity or pagination.
    where = ["act = ?", "json_extract(detail, '$.magnet') = ?", "seq > ?"]
    args = [ACT, mid, after]
    for clause, value in (("json_extract(detail, '$.perspective') = ?", topic),
                          ("json_extract(detail, '$.event') = ?", event),
                          ("seq <= ?", through), ("turn = ?", post)):
        if value is not None:
            where.append(clause)
            args.append(value)
    sql = ("SELECT seq, turn, detail FROM operational WHERE " + " AND ".join(where)
           + (" ORDER BY seq DESC" if newest else " ORDER BY seq") + " LIMIT ?")
    rows = st.corpus._store._rows(sql, (*args, limit))
    return [{"seq": r["seq"], "post": r["turn"], **json.loads(r["detail"])} for r in rows]


def _last(st, mid, topic=None, event=None, post=None):
    rows = _rows(st, mid, topic, event=event, post=post, newest=True, limit=1)
    return rows[0] if rows else None


def _topic(st, mid, topic):
    cid = home(st, mid)
    if not isinstance(topic, str) or st.cv.conversation_of_topic(topic) != cid:
        refuse("wrong-perspective", "this Perspective is not in this Magnet's own Conversation")
    row = _last(st, mid, topic, "created")
    if row is None:
        refuse("wrong-perspective", "this Topic is not a recorded Perspective of this Magnet")
    return row


def selected(st, mid):
    row = _last(st, mid, event="selected")
    return row["data"]["selected"] if row else None


def standing(st, mid):
    """This Magnet's standing Perspective -- the evolving summary -- or None.

    The FIRST one its record holds, so a Magnet has exactly one however many
    times creation is attempted: the record is append-only, and a second
    `created` event carrying `standing` never displaces the first.
    """
    rows = _rows(st, mid, event="created", limit=PAGE_MAX)
    for row in rows:
        if row["data"].get("standing") is True:
            return row["perspective"]
    return None


def state(st, mid, topic, *, detail=False):
    created = _topic(st, mid, topic)
    life = _last(st, mid, topic, "retired")
    resumed = _last(st, mid, topic, "resumed")
    q = _last(st, mid, topic, "question")
    renamed = _last(st, mid, topic, "rename")
    return {**({"current_question": {"text": q["data"]["text"],
                    "revision": q["snapshot"]["ref"]} if q else None} if detail else {}),
            "perspective": topic, "name": (renamed or created)["data"]["name"],
            "retired": bool(life and (not resumed or life["seq"] > resumed["seq"])),
            "question": q["snapshot"] if q else None,
            "events": _count(st, mid, topic)}


def _count(st, mid, topic):
    return st.corpus._store._rows(
        "SELECT count(*) AS n FROM operational WHERE act=? AND "
        "json_extract(detail,'$.magnet')=? AND json_extract(detail,'$.perspective')=?",
        (ACT, mid, topic))[0]["n"]


def hold(st, mid, value, by, *, name="record"):
    raw = encoded(value)
    got = artifacts.hold(st.corpus, st.cv, raw, act=artifacts.SUBMITTED,
                         actor=by, source=f"magnet-perspective:{mid}", door=DOOR,
                         claimed_name=f"{mid}-{name}.json", claimed_media_type="application/json")
    return {"ref": got["admission"], "digest": got["digest"], "size": len(raw),
            "media_type": "application/json"}


def event(st, mid, topic, verb, data, by, *, snapshot=None, written_by=None):
    cid = home(st, mid)
    st.cv.ensure_writable(cid, topic)
    snapshot = snapshot or hold(st, mid, {"format": FORMAT, "version": 1, "kind": "event",
        "brain": brain_key(st.corpus), "magnet": mid, "perspective": topic,
        "event": verb, "data": data}, by)
    label = data.get("text") or data.get("name") or data.get("reason") or verb
    out, later = posting.post(st.cv, st.corpus, cid, {
        "author": by, "action": posting.RECORD_ONLY,
        "parts": [{"type": "text", "text": f"Perspective {verb}: {label}"},
                  {"type": "file", "ref": snapshot["ref"], "media_type": "application/json",
                   "alt": f"Perspective {verb}"}],
        "topics": [topic] if topic else []}, agents=st.agents,
        written_by=lambda: written_by, _record_only=True)
    if out.get("error") or later:
        refuse("record-refused", out.get("error", "a Perspective event cannot dispatch work"))
    st.cv.record_act(actor=by, act=ACT, conversation=cid, turn=out["turn"],
        about=[topic] if topic else [], detail={"magnet": mid, "perspective": topic,
            "event": verb, "snapshot": snapshot, "data": data})
    return _last(st, mid, post=out["turn"])


def _question(st, mid, topic, words, reason, by, written_by):
    text(words, "question")
    snap = hold(st, mid, {"format": FORMAT, "version": 1, "kind": "question",
        "brain": brain_key(st.corpus), "magnet": mid, "perspective": topic,
        "text": words, "reason": reason}, by, name="question")
    row = event(st, mid, topic, "question", {"text": words, "reason": reason}, by,
                snapshot=snap, written_by=written_by)
    return {"perspective": topic, "question": snap, "event": row}


def _create(st, mid, body, by, written_by, parent=None):
    name = text(body.get("name"), "name")
    text(body.get("question"), "question")
    # ONE STANDING PERSPECTIVE PER MAGNET, whatever asks for it and however
    # often. Creation is idempotent in the record itself, not only in the
    # operation key: a client that lost its acknowledgement, a second surface,
    # or a Magnet that predates this part all converge on the same Topic
    # rather than growing a second evolving summary.
    if body.get("standing"):
        already = standing(st, mid)
        if already:
            q = _last(st, mid, already, "question")
            return {"perspective": already, "question": q["snapshot"] if q else None,
                    "event": _last(st, mid, already), "standing": True, "existing": True}
    topic = st.cv.open_topic(home(st, mid), name, about=f"Perspective of Magnet {mid}",
                             attributed_to=by, written_by=written_by)
    event(st, mid, topic, "created", {"name": name, "parent": parent,
        "reason": body.get("reason"),
        **({"standing": True} if body.get("standing") else {})}, by, written_by=written_by)
    out = _question(st, mid, topic, body["question"], body.get("reason"), by, written_by)
    return {**out, **({"standing": True} if body.get("standing") else {})}


def _limit(value):
    try:
        if isinstance(value, bool) or str(int(value)) != str(value):
            raise ValueError()
        value = int(value)
    except (ValueError, TypeError):
        refuse("invalid-limit", "limit is an integer from 1 to 100")
    if not 1 <= value <= PAGE_MAX:
        refuse("invalid-limit", "limit is an integer from 1 to 100")
    return value


def _cursor(st, mid, topic, cursor, event_name=None):
    scope = [brain_key(st.corpus), mid, topic, event_name]
    top = _last(st, mid, topic, event_name)
    high = top["seq"] if top else 0
    if not cursor:
        return 0, high
    try:
        if len(cursor) > 2048 or not cursor.startswith("mp1."):
            raise ValueError()
        got = json.loads(base64.urlsafe_b64decode(cursor[4:] + "=" * (-len(cursor[4:]) % 4)))
        if got[0] != scope or len(got) != 3:
            raise ValueError()
        after, through = got[1:]
        if (type(after) is not int or type(through) is not int
                or not 0 <= after <= through <= high):
            raise ValueError()
        return after, through
    except (ValueError, TypeError, IndexError, KeyError):
        refuse("invalid-cursor", "this history cursor does not belong to this Brain, Magnet and Perspective")


def _next(st, mid, topic, row, through, event_name=None):
    return "mp1." + base64.urlsafe_b64encode(encoded([
        [brain_key(st.corpus), mid, topic, event_name], row["seq"], through])).decode().rstrip("=")


def history(st, mid, topic, *, limit=20, cursor=None):
    _topic(st, mid, topic)
    limit = _limit(limit)
    after, through = _cursor(st, mid, topic, cursor)
    rows = _rows(st, mid, topic, after=after, through=through, limit=limit + 1)
    return {"magnet": mid, "perspective": topic, "events": rows[:limit],
            "next": _next(st, mid, topic, rows[limit - 1], through) if len(rows) > limit else None,
            "through": through, "brain": brain_key(st.corpus), "disclosure": DISCLOSURE}


def listing(st, mid, *, limit=20, cursor=None):
    home(st, mid)
    limit = _limit(limit)
    after, through = _cursor(st, mid, None, cursor, "created")
    rows = _rows(st, mid, event="created", after=after, through=through, limit=limit + 1)
    return {"magnet": mid, "perspectives": [state(st, mid, r["perspective"]) for r in rows[:limit]],
            "selected": selected(st, mid), "brain": brain_key(st.corpus), "disclosure": DISCLOSURE,
            "grounded_answers": GROUNDED_ANSWERS_ENABLED, "standing": standing(st, mid),
            "next": _next(st, mid, None, rows[limit - 1], through, "created") if len(rows) > limit else None}


FIELDS = {
    "create": {"name", "question", "reason", "standing"}, "selected": {"perspective"},
    "rename": {"name"},
    # The grounded answer written from this Magnet's own collected rows. `text`
    # is an owner's new question, optional: without one the Perspective's
    # saved current question is re-answered over the rows that arrived since.
    "answer": {"text", "reason"},
    "question": {"text", "reason"}, "challenge": {"text", "reason"},
    "retire": {"reason"}, "resume": {"reason"}, "branch": {"name", "question", "reason"},
    "prepare": {"question", "batches", "selections", "priors", "declared_context", "continuation"},
    "bind": {"intent", "request"},
    "reconcile": {"intent", "execution", "declared_context", "purpose"},
    "finalize": {"intent", "execution", "answer"},
}


def require_grounded():
    """The product gate. Open since the configured-source scope is enforced
    (`mentis.magnet.scope`); its refusal is kept, with its existing code, for
    a build where the gate is shut again."""
    if not GROUNDED_ANSWERS_ENABLED:
        refuse("grounded-answers-blocked", "Grounded Perspective answers are unavailable: existing "
               "execution controls do not enforce the configured-source access boundary. Completed "
               "fixture work is preserved; broader agent reach is not Magnet collection scope.")


def command(st, mid, topic, verb, body, *, written_by=None):
    """One owner write, durable and idempotent. Never dispatches."""
    from mentis.conversation.owner import _owner
    by = _owner(st.cv)
    if not by:
        refuse("owner-required", "this record names no owner")
    if body.get("brain") != brain_key(st.corpus):
        refuse("wrong-brain", "this intent belongs to another Brain instance")
    if verb not in FIELDS or set(body) - (FIELDS[verb] | {"brain", "op"}):
        refuse("invalid-fields", "this Perspective operation carries unsupported fields")
    if verb in ("prepare", "finalize", "reconcile", "answer"):
        require_grounded()
    op = body.get("op")
    if not isinstance(op, str) or not op.strip() or len(op) > 160:
        refuse("operation-required", "op is a nonempty operation key of at most 160 characters")
    if "reason" in body and body["reason"] is not None:
        text(body["reason"], "reason", empty=True)
    request = {"route": DOOR, "magnet": mid, "perspective": topic, "verb": verb, "body": body}

    def save():
        cid = home(st, mid)
        st.cv.ensure_writable(cid, topic)
        if verb == "create":
            out = _create(st, mid, body, by, written_by)
        elif verb == "selected":
            chosen = body.get("perspective")
            if chosen is not None and state(st, mid, chosen)["retired"]:
                refuse("retired", "Resume this Perspective before selecting it")
            row = event(st, mid, chosen, "selected", {"selected": chosen}, by, written_by=written_by)
            out = {"selected": chosen, "event": row}
        else:
            current = state(st, mid, topic)
            if verb == "question":
                out = _question(st, mid, topic, body.get("text"), body.get("reason"), by, written_by)
            elif verb == "rename":
                row = event(st, mid, topic, "rename", {"name": text(body.get("name"), "name")},
                            by, written_by=written_by)
                out = {"perspective": topic, "event": row}
            elif verb == "branch":
                out = _create(st, mid, body, by, written_by, parent=topic)
            elif verb in ("challenge", "retire", "resume"):
                if verb == "challenge":
                    text(body.get("text"), "challenge")
                row = event(st, mid, topic, {"challenge": "challenged", "retire": "retired",
                    "resume": "resumed"}[verb], {k: v for k, v in body.items() if k in ("text", "reason")},
                    by, written_by=written_by)
                if verb == "retire" and selected(st, mid) == topic:
                    event(st, mid, None, "selected", {"selected": None}, by, written_by=written_by)
                out = {"perspective": topic, "event": row}
            else:
                from . import perspectives_work as work
                if verb in ("prepare", "answer") and current["retired"]:
                    refuse("retired", "Resume this Perspective before preparing new work")
                out = getattr(work, verb)(st, mid, topic, body, by, written_by)
        return {**out, "brain": brain_key(st.corpus)}

    return anchors.keyed(st.cv, by, "perspective:" + op, request, save)


def route_read(st, mid, bits, one):
    if not bits:
        return listing(st, mid, limit=one("limit", "20"), cursor=one("cursor"))
    topic = bits[0]
    if len(bits) == 1:
        return {"magnet": mid, **state(st, mid, topic, detail=True), "selected": selected(st, mid),
                "brain": brain_key(st.corpus), "disclosure": DISCLOSURE,
                "grounded_answers": GROUNDED_ANSWERS_ENABLED, "standing": standing(st, mid)}
    if len(bits) == 2 and bits[1] == "history":
        return history(st, mid, topic, limit=one("limit", "20"), cursor=one("cursor"))
    if len(bits) == 3 and bits[1] == "intents":
        from .perspectives_work import intent_read
        return intent_read(st, mid, topic, bits[2])
    refuse("unknown-route", "there is no such Perspective read")
