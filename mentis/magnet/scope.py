"""What a Magnet-scoped execution may read, and the owner's per-exchange widening.

THE OWNER'S CORRECTION THIS IMPLEMENTS (`ent-d85254fe5e1b`, Turn #277):

    A Magnet's configured sources determine its collection scope. A Perspective
    must not silently use unrelated Brain records or acquired files merely
    because its agent can technically access them.

That is the only reason grounded answers were off (`perspectives.
GROUNDED_ANSWERS_ENABLED`), and this module is the enforcement the correction
asked for. It decides two things and nothing else:

  * WHICH OPERATIONS a Magnet-scoped execution may call at all (`narrowed`,
    read by `mentis.worker.permitted` -- the one door's own table). A read that
    cannot be confined to one Magnet -- a Brain-wide `find`, `recall`,
    `governed`, `work_overview`, `brief` -- is not narrowed, it is refused:
    there is no honest way to point it at one Magnet's collection. `delegate`
    is refused for the same reason: a child's grant is minted from its own
    request, so delegating would be a way out of this confinement.
  * WHICH TARGET each remaining read may name (`why_not`): that Magnet's own
    recorded collection batches, the posts of its own Conversation, the
    references the owner explicitly selected for this exchange, and -- for a
    conversation exchange only -- the acquired collections the Magnet's
    definition configures. Nothing else.

ONE DOOR, NO SIDE ROUTE (AGENTS.md). Nothing here is reachable except through
`/api/worker` -> `mentis.worker.permitted` / `_result` / `_operation`. It reads
the grant on the dispatched execution and the record; it never reads a worker's
claim about itself. A Magnet-scoped grant is deliberately NOT mirrored to the
Rust front (`mentis.mirror.mirrored`), so the front forwards it rather than
answering a moved read under the ordinary worker set: a grant Rust does not
hold is forwarded, never refused or served, and no Rust check is carried into a
Python write.

THE TWO HALVES ARE DIFFERENT, AND MUST NOT BE CONFLATED (amendment
`adm-c38044ee5157` section 3):

  * SYNTHESIS IS NEVER WIDENED. A Perspective answer and an evolving summary
    are grounded in the Magnet's collected rows and nothing else. A synthesis
    execution carries `magnet-synthesis:<id>`, whose operation set holds no
    source read at all, and `authorization` refuses to read one for it while
    `outside` returns nothing for it. Two independent refusals, so a forged
    grant field or a stray authorization act still opens nothing.
  * A CONVERSATION EXCHANGE MAY BE AUTHORIZED WIDER, ONCE. The owner's own
    explicit act on that one asking Turn (`AUTHORIZED`) names what it opens --
    the runtime's own web search, or one more declared collection -- and opens
    only that. It is keyed to the asking Turn, so the next exchange, which is a
    different Turn, is unauthorized again; it is refused if an execution wrote
    it; and it rides the grant on that one execution through the same door.

WHAT THIS CANNOT ENFORCE, SAID PLAINLY. "The runtime's own web search" is the
runtime's tool, not a Mentis read: Mentis records that the owner opened it and
tells the run so, and cannot police it at this door. Everything Mentis itself
serves is enforced here.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import MAGNET_ID

#: The kinds of Magnet-scoped execution, and the scope string each carries.
CONVERSATION = "conversation"
SYNTHESIS = "synthesis"
PREFIX = {"magnet:": CONVERSATION, "magnet-synthesis:": SYNTHESIS}

#: The owner's per-exchange authorization, and what it may open.
AUTHORIZED = "magnet-exchange-authorized"
RUNTIME_SEARCH = "runtime-web-search"
COLLECTION = "collection"
OPEN_KINDS = (RUNTIME_SEARCH, COLLECTION)
#: At most this many things in one authorization: it names what it opens.
OPENS_MOST = 4

#: What an answer actually reached outside the collection, recorded at the door
#: on the authorized widening path only. An ordinary read inside the Magnet's
#: own scope records nothing: reads stay reads.
OUTSIDE_READ = "magnet-outside-source-read"

#: WHAT A MAGNET-SCOPED EXECUTION MAY CALL, whichever kind it is. An allowlist,
#: so a new operation is refused until somebody decides it can be confined.
#: Intersected with what the request itself granted, so this widens nothing.
MAY_CALL = (
    # Reads that name one target, confined by `why_not`, or that read no
    # record content at all.
    "orient", "resolve", "history", "kinds", "capabilities", "check_rendering",
    # The Magnet's own collected material and the owner's explicit selections.
    "read_artifact",
    # Answering the owner, and asking them, in this one exchange.
    "respond", "request_decision", "request_input", "answer",
    "react", "anchor", "record_discovered_work", "return_artifact",
    # Shared resources: names and leases, no record content.
    "claim_resource", "release_resource", "resources",
)

#: THE SOURCE READS, WHICH ONLY A CONVERSATION EXCHANGE HOLDS. A synthesis run
#: is grounded in the collected rows, so it reads no live collection -- not even
#: a configured one -- and this is why no authorization can reach it: the
#: operations are not in its set to begin with.
OUTSIDE_READS = ("sources", "source_history", "source_links", "read_source",
                 "search_sources")

SYNTHESIS_NEVER = (
    "a Magnet's synthesis -- a Perspective answer or an evolving summary -- is "
    "grounded in the Magnet's collected rows and nothing else. No "
    "authorization widens it, and no code path gives a synthesis execution the "
    "wider grant (amendment adm-c38044ee5157 section 3)")


class Refused(ValueError):
    """An authorization that cannot be recorded as what it claims to be."""


@dataclass(frozen=True)
class Confinement:
    """A grant's scope read as a Magnet confinement. `magnet` is None when the
    scope says Magnet and its id is unreadable, which refuses everything: a
    malformed confinement fails closed rather than falling through to the
    ordinary worker set."""

    kind: str
    magnet: str | None


def scope_name(mid: str, *, synthesis: bool = False) -> str:
    """The scope string a Magnet-scoped execution is dispatched with."""
    return ("magnet-synthesis:" if synthesis else "magnet:") + mid


def parsed(scope) -> Confinement | None:
    """This grant's confinement, or None if it is not a Magnet-scoped one."""
    if not isinstance(scope, str):
        return None
    for prefix, kind in PREFIX.items():
        if scope.startswith(prefix):
            mid = scope[len(prefix):]
            return Confinement(kind, mid if MAGNET_ID.fullmatch(mid) else None)
    return None


def narrowed(confined: Confinement, ordinary) -> tuple[str, ...]:
    """What this confinement leaves of the operations the request granted.

    An intersection, never a union: a Magnet-scoped run holds nothing its
    request did not already grant, and nothing outside `MAY_CALL`.
    """
    may = MAY_CALL + (OUTSIDE_READS if confined.kind == CONVERSATION else ())
    return tuple(name for name in ordinary if name in may)


# -- what this execution may read, read from the record -----------------------


@dataclass(frozen=True)
class Reach:
    """What one Magnet-scoped execution may read. Composed from the grant and
    the record only: no argument of the call takes part in deciding it."""

    kind: str
    magnet: str | None
    conversation: str | None
    turn: str | None
    #: Collections the Magnet's definition configures as sources.
    collections: frozenset
    #: What the owner opened for this one exchange, as recorded.
    opens: tuple
    #: Refs the owner explicitly selected in this exchange's `magnet_context`.
    selected: frozenset

    @property
    def outside(self) -> frozenset:
        """Collections beyond the configured ones this exchange may read.

        Empty for a synthesis execution, always and structurally.
        """
        if self.kind != CONVERSATION:
            return frozenset()
        return frozenset(o["collection"] for o in self.opens
                         if o.get("kind") == COLLECTION and o.get("collection"))

    @property
    def readable_collections(self) -> frozenset:
        return self.collections | self.outside


def _definition(corpus, mid):
    from . import Unreadable, read as definition
    try:
        return definition(corpus.root, mid)
    except Unreadable:
        return None


def _selected_refs(context) -> frozenset:
    """Every identity the owner explicitly selected in this exchange."""
    out = set()
    selector = (context or {}).get("selector") or {}
    perspective = selector.get("perspective") or {}
    for key in ("question_ref",):
        if isinstance(perspective.get(key), str):
            out.add(perspective[key])
    for r in selector.get("references") or ():
        if not isinstance(r, dict):
            continue
        for key in ("ref", "version"):
            if isinstance(r.get(key), str):
                out.add(r[key])
    return frozenset(out)


def _context(cv, expectation):
    """The frozen managed context of this exchange, as the record holds it.

    Read straight off the `agent-request-routed` act rather than revalidated:
    this is a read gate and must not raise a send-time refusal, and the frozen
    snapshot is what the exchange actually was.
    """
    from mentis.fluid.message_context import ROUTED
    if not expectation:
        return None, None
    act = cv._act(expectation)
    turn = cv.asked_on(act) if act else None
    if not turn:
        return None, None
    rows = cv._c.operational(act=ROUTED, turn=turn, limit=1)
    context = (rows[0].get("detail") or {}).get("managed_context") if rows else None
    return turn, context if isinstance(context, dict) else None


def reach(surface, confined: Confinement, grant: dict) -> Reach:
    """What this execution may read. Fails closed on anything unreadable."""
    cv, corpus = surface.cv, surface.corpus
    mid = confined.magnet
    if mid is None:
        return Reach(confined.kind, None, None, None, frozenset(), (), frozenset())
    turn, context = _context(cv, (grant or {}).get("expectation"))
    config = _definition(corpus, mid) or {}
    cid = config.get("conversation")
    # THE CONTEXT MUST BE THIS MAGNET'S, AND THE EXCHANGE MUST BE IN ITS OWN
    # CONVERSATION. Where the two disagree, nothing is readable: a confinement
    # whose basis cannot be confirmed refuses rather than guessing.
    if context is not None and context.get("magnet") != mid:
        return Reach(confined.kind, mid, None, turn, frozenset(), (), frozenset())
    if context is not None and context.get("conversation") not in (None, cid):
        cid = None
    collections = frozenset(
        s["collection"] for s in (config.get("sources") or ())
        if isinstance(s, dict) and isinstance(s.get("collection"), str))
    return Reach(confined.kind, mid, cid, turn, collections,
                 authorization(cv, confined, turn), _selected_refs(context))


# -- the owner's per-exchange authorization -----------------------------------


def _opens(value) -> tuple:
    """What an authorization opens, validated. Raises `Refused`."""
    if not isinstance(value, list) or not value or len(value) > OPENS_MOST:
        raise Refused(f"an authorization names between 1 and {OPENS_MOST} "
                      f"things to open")
    out = []
    for one in value:
        if not isinstance(one, dict) or one.get("kind") not in OPEN_KINDS:
            raise Refused(f"each opened thing names a kind: {list(OPEN_KINDS)}")
        if one["kind"] == COLLECTION:
            col = one.get("collection")
            if not isinstance(col, str) or not col.strip():
                raise Refused("opening a collection names that collection")
            if set(one) - {"kind", "collection"}:
                raise Refused("an opened collection carries no other field")
            out.append({"kind": COLLECTION, "collection": col.strip()})
        else:
            if set(one) - {"kind"}:
                raise Refused("an opened runtime search carries no other field")
            out.append({"kind": RUNTIME_SEARCH})
    if len({(o["kind"], o.get("collection")) for o in out}) != len(out):
        raise Refused("an authorization opens each thing once")
    return tuple(out)


def authorize(st, mid: str, *, turn: str, opens, by: str, op: str,
              reason: str | None = None, written_by=None) -> dict:
    """Record the owner's authorization of ONE exchange to reach wider.

    The owner's own explicit act, and never an agent's: `by` must be the
    recorded owner, the act is written on the asking Turn of that one exchange,
    and a synthesis exchange is refused outright. Nothing here changes a grant;
    the door reads this act for that exchange's execution and nothing else.
    """
    from mentis.conversation import anchors
    from mentis.conversation.owner import _owner
    from . import read as definition
    if not MAGNET_ID.fullmatch(mid or ""):
        raise Refused("that is not a Magnet id")
    owner = _owner(st.cv)
    if not owner or by != owner:
        raise Refused("only the recorded owner authorizes an exchange to reach "
                      "outside this Magnet's collection scope")
    config = definition(st.corpus.root, mid)
    cid = (config or {}).get("conversation")
    if not cid:
        raise Refused("this Magnet has no Conversation to authorize an "
                      "exchange in")
    rows = st.corpus.read([turn]) if isinstance(turn, str) else []
    if not rows or st.cv.conversation_of(turn) != cid:
        raise Refused("authorize the asking Turn of an exchange in this "
                      "Magnet's own Conversation")
    if rows[0].get("attributed_to") != owner:
        raise Refused("an exchange is authorized on the owner's own asking "
                      "Turn")
    opened = _opens(opens)
    if not isinstance(op, str) or not op.strip() or len(op) > 160:
        raise Refused("op is a nonempty operation key of at most 160 characters")
    request = {"route": "magnet-exchange-authorization", "magnet": mid,
               "turn": turn, "opens": [dict(o) for o in opened]}

    def save():
        act = st.cv.record_act(
            actor=owner, act=AUTHORIZED, conversation=cid, turn=turn,
            because=reason or None,
            detail={"magnet": mid, "turn": turn,
                    "opens": [dict(o) for o in opened], "exchange": turn})
        return {"magnet": mid, "turn": turn, "act": act,
                "opens": [dict(o) for o in opened]}

    return anchors.keyed(st.cv, owner, "magnet-authorize:" + op, request, save)


def authorization(cv, confined: Confinement, turn) -> tuple:
    """What the owner opened for this one exchange, as the record holds it.

    SYNTHESIS IS NEVER WIDENED: nothing is read for a synthesis confinement,
    whatever the record happens to hold. An act an EXECUTION wrote is not the
    owner's own and opens nothing. An act on another Turn is another exchange's
    and opens nothing here.
    """
    if confined.kind != CONVERSATION or not confined.magnet or not turn:
        return ()
    from mentis.conversation.owner import _owner
    owner = _owner(cv)
    rows = cv._c.operational(act=AUTHORIZED, turn=turn,
                             detail_is={"magnet": confined.magnet},
                             newest_first=True, limit=4)
    for row in rows:
        detail = row.get("detail") or {}
        if row.get("execution") or not owner or row.get("actor") != owner:
            continue
        if detail.get("turn") != turn or detail.get("magnet") != confined.magnet:
            continue
        try:
            return _opens(detail.get("opens"))
        except Refused:
            continue
    return ()


def note_outside_read(surface, grant: dict, reach_: Reach, what: dict) -> None:
    """Record that this answer reached an authorized source outside the Magnet's
    collection, once per execution and target.

    ONLY ON THE AUTHORIZED WIDENING PATH. A read inside the Magnet's own scope
    records nothing, so reads stay reads except where the owner explicitly
    opened something and the record should show what the answer reached.
    """
    cv = surface.cv
    detail = {"magnet": reach_.magnet, "turn": reach_.turn, **what}
    execution = (grant or {}).get("instance")
    if execution and cv._c.operational(act=OUTSIDE_READ, execution=execution,
                                       detail_is=detail, limit=1):
        return
    cv.record_act(actor=(grant or {}).get("participant"), act=OUTSIDE_READ,
                  conversation=reach_.conversation, turn=reach_.turn,
                  execution=execution, runtime=(grant or {}).get("runtime"),
                  caused_by=(grant or {}).get("expectation"), detail=detail)


def provenance(cv, mid: str, *, turn: str, synthesis: bool = False) -> dict:
    """WHAT AN ANSWER TO THIS EXCHANGE WAS ALLOWED TO REACH, AND WHAT IT DID.

    The published provenance Part F renders and the client shows, so
    grounded-in-the-collection and explored-outside can never be mistaken for
    each other (`docs/magnets/part-b-perspectives-api.md`). `explored_outside`
    is the field to render: it is true only when an authorized read of
    something outside the Magnet's collection actually happened.
    """
    confined = Confinement(SYNTHESIS if synthesis else CONVERSATION, mid)
    opens = authorization(cv, confined, turn)
    rows = ([] if synthesis else
            cv._c.operational(act=OUTSIDE_READ, turn=turn,
                              detail_is={"magnet": mid}, limit=50))
    reached = []
    for row in rows:
        detail = {k: v for k, v in (row.get("detail") or {}).items()
                  if k not in ("magnet", "turn")}
        if detail and detail not in reached:
            reached.append(detail)
    return {"grounded_in": "collection",
            "outside_authorized": [dict(o) for o in opens],
            "outside_reads": reached,
            "explored_outside": bool(reached)}


# -- the per-target gate, applied at the one door -----------------------------


def _outside_scope(reach_: Reach, what: str) -> str:
    where = reach_.conversation or "its own Conversation"
    return (f"{what} is outside Magnet {reach_.magnet}'s collection scope. "
            f"This execution reads that Magnet's own recorded collection "
            f"batches, the posts of its own Conversation ({where}), and the "
            f"references the owner selected for this exchange -- nothing else. "
            f"A Magnet's configured sources set its collection scope, and "
            f"being able to reach a record is not permission to use it (owner "
            f"correction ent-d85254fe5e1b). Report what you could not read "
            f"rather than answering from anything else.")


def _collection_outside(reach_: Reach, col) -> str:
    configured = ", ".join(sorted(reach_.collections)) or "none"
    return (f"collection {col!r} is not a configured source of Magnet "
            f"{reach_.magnet} (configured: {configured}), and the owner "
            f"authorized no other collection for this exchange. An "
            f"authorization is the owner's own act on one exchange, it names "
            f"what it opens, and it does not carry into the next exchange.")


def _unconfirmed(reach_: Reach) -> str:
    return (f"this execution is confined to one Magnet's collection scope and "
            f"that confinement cannot be confirmed from the record "
            f"(magnet {reach_.magnet}, conversation {reach_.conversation}), so "
            f"nothing is readable under it. Report it rather than reading "
            f"anything.")


def _acquired_collection(corpus, ref):
    """`(True, collection)` for an acquired object, `(False, None)` otherwise."""
    from mentis.sources import Refused as SourceRefused, observation, reading
    try:
        entry = reading._bulk_admission(corpus, ref)
    except SourceRefused:
        return False, None
    except Exception:                                         # noqa: BLE001
        return True, None
    try:
        return True, (observation(entry) or {}).get("collection")
    except Exception:                                         # noqa: BLE001
        return True, None


def _own_material(corpus, mid, ref) -> bool:
    """Whether this artifact is this Magnet's own held material: a recorded
    collection batch, or a Perspective's immutable wording or answer package."""
    from mentis import artifacts
    try:
        got = artifacts.describe(corpus, ref, verify=False)
    except Exception:                                         # noqa: BLE001
        return False
    return (got.get("door") in ("magnet-extract", "magnet-perspective")
            and got.get("source") in (f"magnet:{mid}",
                                      f"magnet-perspective:{mid}"))


def _entry_in_scope(surface, reach_: Reach, ref: str) -> bool:
    cv = surface.cv
    if ref == reach_.conversation or ref in reach_.selected:
        return True
    try:
        if cv._is_kind(ref, "conversation"):
            return False
        if cv.conversation_of(ref) == reach_.conversation:
            return True
        if cv.conversation_of_topic(ref) == reach_.conversation:
            return True
        return ref in (cv.participants(reach_.conversation) or ())
    except Exception:                                         # noqa: BLE001
        return False


def _artifact_in_scope(surface, reach_: Reach, grant, ref: str):
    """`(ok, outside)`: whether this artifact is readable, and what outside
    source it came from when it is readable only by authorization."""
    from mentis import artifacts
    corpus = surface.corpus
    if ref in reach_.selected or _own_material(corpus, reach_.magnet, ref):
        return True, None
    acquired, col = _acquired_collection(corpus, ref)
    if acquired:
        if col and col in reach_.collections:
            return True, None
        if col and col in reach_.outside:
            return True, {"what": "artifact", "collection": col, "ref": ref}
        return False, None
    reason, _ = artifacts.in_conversation(
        corpus, surface.cv, reach_.conversation, ref,
        reader=(grant or {}).get("expectation"))
    return (reason is not None), None


def _collection_named(args) -> str | None:
    got = args.get("collection")
    return got.strip() if isinstance(got, str) and got.strip() else None


def why_not(surface, confined: Confinement, grant: dict, name: str,
            args: dict) -> str | None:
    """Why this Magnet-scoped execution may not read what it named, or None.

    Narrowing only. Every answer here is a refusal or silence: nothing in this
    function admits a read the ordinary rules would have refused.
    """
    args = args if isinstance(args, dict) else {}
    reach_ = reach(surface, confined, grant)
    if reach_.magnet is None or reach_.conversation is None:
        return _unconfirmed(reach_)
    if name in ("kinds", "capabilities", "check_rendering",
                "claim_resource", "release_resource", "resources"):
        return None
    if name == "orient":
        asked = args.get("conversation")
        if isinstance(asked, str) and asked.strip() == reach_.conversation:
            return None
        return (f"orient names this Magnet's own Conversation "
                f"({reach_.conversation}). A Magnet-scoped execution is not "
                f"told what else this Brain holds.")
    if name == "resolve":
        ref = args.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            return None            # the read says what it needs, and reads nothing
        ref = ref.strip()
        if ref == reach_.magnet:
            return None            # a Magnet id names no record
        if ref.startswith("adm-"):
            ok, outside = _artifact_in_scope(surface, reach_, grant, ref)
            if not ok:
                return _outside_scope(reach_, repr(ref))
            if outside:
                note_outside_read(surface, grant, reach_, outside)
            return None
        return None if _entry_in_scope(surface, reach_, ref) else _outside_scope(
            reach_, repr(ref))
    if name == "history":
        if args.get("set"):
            return (f"a response set is not part of Magnet "
                    f"{reach_.magnet}'s collection scope. "
                    + _outside_scope(reach_, "that set"))
        if args.get("participant"):
            return (f"a Participant's history crosses Conversations. "
                    + _outside_scope(reach_, "that Participant's history"))
        turn = args.get("turn")
        asked = args.get("conversation")
        if isinstance(turn, str) and turn.strip():
            return (None if _entry_in_scope(surface, reach_, turn.strip())
                    else _outside_scope(reach_, repr(turn.strip())))
        if isinstance(asked, str) and asked.strip():
            return (None if asked.strip() == reach_.conversation
                    else _outside_scope(reach_, repr(asked.strip())))
        return (f"history names this Magnet's own Conversation "
                f"({reach_.conversation}) or one of its posts.")
    if name == "read_artifact":
        ref = args.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            return None
        ok, outside = _artifact_in_scope(surface, reach_, grant, ref.strip())
        if not ok:
            return _outside_scope(reach_, repr(ref.strip()))
        if outside:
            note_outside_read(surface, grant, reach_, outside)
        return None
    if name in OUTSIDE_READS:
        if confined.kind != CONVERSATION:
            return SYNTHESIS_NEVER
        col = _collection_named(args)
        if col is None and name == "read_source":
            ref = args.get("ref")
            if isinstance(ref, str) and ref.strip():
                acquired, col = _acquired_collection(surface.corpus,
                                                     ref.strip())
                if not acquired or not col:
                    return _outside_scope(reach_, repr(ref.strip()))
        if col is None:
            return (f"{name} names one of Magnet {reach_.magnet}'s configured "
                    f"source collections: a Magnet-scoped execution does not "
                    f"read across this Brain's acquired material. "
                    f"Configured: "
                    f"{', '.join(sorted(reach_.collections)) or 'none'}.")
        if col in reach_.collections:
            return None
        if col in reach_.outside:
            note_outside_read(surface, grant, reach_,
                              {"what": name, "collection": col})
            return None
        return _collection_outside(reach_, col)
    # FAILS CLOSED. An operation `narrowed` admits and this does not know is
    # refused rather than served: a new read is confined deliberately or not
    # at all.
    return (f"{name!r} has no Magnet-scoped reading: this execution is "
            f"confined to Magnet {reach_.magnet}'s collection scope, and "
            f"nothing decides what {name!r} would read inside it.")
