"""Fluid's ladder reads. Status and provenance belong to the shared read model.

This adapter builds cards, filters and counts from those facts. It never
stores a status, and a challenge is counted separately from standing.
"""
from __future__ import annotations

from mentis import record_summaries as _summaries
from mentis.conversation import knowing_of, placements_now
from mentis.conversation.ladder_writes import adoptable, requests
from mentis.conversation.register import kind_definitions


class _Reads:
    """What one request reads once and every item in it shares: the acts by
    the entry they are about, and the delivery records. Measured on
    INTEGRATION (the live Brain's copy): reading the whole act history twice
    per item, and every delivery record once per item, made /api/ladder/adopted
    take 41 s and starved the Learning read the page makes beside it.

    NEVER THE WHOLE ACT HISTORY (2026-11-16, measured on TEST's copy of the
    live Brain: 84,000 acts decoded, 2.3 s, in every one of these reads). The
    acts about one entry are asked of the store by that entry
    (`operational(about=)`), the acts of one name by that name, and the
    delivery records are indexed by the material they delivered once."""

    def __init__(self, cv):
        self.cv = cv
        self._about = {}
        self._named = {}
        self._deliveries = None
        self._delivered = None
        self._aliases = {}

    def acts_about(self, eid):
        if eid not in self._about:
            self._about[eid] = self.cv._c.operational(about=eid)
        return self._about[eid]

    def deliveries(self):
        if self._deliveries is None:
            self._deliveries = self.cv._c.deliveries()
        return self._deliveries

    def delivered(self, eid):
        """The delivery records naming this entry, oldest first: each record
        once, however many of its sources name it (`ladder.delivered_to`)."""
        if self._delivered is None:
            index = {}
            for d in self.deliveries():
                for source in dict.fromkeys(
                        s.get("source_id") for s in d.get("behavioural_sources") or ()):
                    if source:
                        index.setdefault(source, []).append(d)
            self._delivered = index
        return self._delivered.get(eid, [])

    def alias(self, who):
        if who not in self._aliases:
            self._aliases[who] = self.cv.alias(who) if who else None
        return self._aliases[who]

    def acts(self, name):
        """Every act of this name, oldest first."""
        if name not in self._named:
            self._named[name] = sorted(self.cv._c.operational(act=name),
                                       key=lambda a: a["at"])
        return self._named[name]


def _history(cv, eid, reads=None):
    acts = (reads or _Reads(cv)).acts_about(eid)
    alias = (reads.alias if reads else cv.alias)
    return [{"at": a["at"], "act": a["act"], "by": a["actor"],
             "by_alias": alias(a["actor"]) if a.get("actor") else None,
             "because": a.get("because")} for a in acts]


def _item(corpus, cv, entry, reads=None):
    from mentis.conversation import ladder as read
    eid = entry["id"]
    kind = (entry.get("definition") or {}).get("name")
    fields = entry.get("body") or {}
    outcomes = read.outcomes_of(corpus, eid)
    challenges = read.challenges_of(corpus, eid)
    return {"id": eid, "kind": kind, "text": fields.get("text", ""),
            # THE WORDS A READER IS SHOWN: `text` where the Kind has one, else
            # its first stated field (a Persona's name, a Workflow's) -- so a
            # record whose Kind keeps its words elsewhere is not "no words".
            "said": _said(entry),
            "fields": fields, "limits": fields.get("limits"),
            "status": read.adoption_status(corpus, eid),
            "challenged": sum(c["resolution"] == "open" for c in challenges),
            "recorded_by": read.recorded_by(corpus, cv, eid),
            "recorded_at": entry.get("recorded_at"),
            "basis": read.basis_of(corpus, eid),
            "outcomes": {"count": len(outcomes), "latest": outcomes[:3]},
            "delivered_to": (len(reads.delivered(eid)) if reads
                             else len(read.delivered_to(cv, eid))),
            "cited_by": len(read.cited_by(corpus, eid)),
            "governs": knowing_of(corpus, kind) == "how",
            "adoptable": adoptable(corpus, entry)}


def _said(entry):
    """The principal statement of a body, as the For adoption card shows it."""
    body = (entry or {}).get("body") or {}
    text = body.get("text")
    return text if isinstance(text, str) and text.strip() else (
        said_of(body) or "")


def said_of(body):
    for v in (body or {}).values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _scope(cv, eid):
    """Where adopted material is placed, as the Adopted tab labels it; None
    for material placed nowhere (adopted knowledge is the Brain's position)."""
    places = placements_now(cv._c, eid)
    if not places:
        return None
    if any(cv.is_whole_brain(p) for p in places):
        return {"whole_brain": True, "places": places}
    names = [cv.conversation_name(p) or p for p in places]
    return {"label": "Placed in " + ", ".join(names), "places": places}


def _adoption(corpus, cv, eid):
    """The requests and declines on one item, in the contract's words."""
    from mentis.conversation import ladder as read
    reqs, declines = read._requests(corpus, eid)
    open_ids = {r["id"] for r in read._open_requests(reqs, declines)}
    # ADOPTION ANSWERS EVERY REQUEST, as `adoption_status` reads it: what
    # stands, or was replaced by what the owner adopted, is closed whether or
    # not any decline names its request.
    answered = read.adoption_status(corpus, eid) in (read.ADOPTED, read.SUPERSEDED, read.DELETED)
    asks = {((cv._act(a["expectation"]) or {}).get("detail") or {}).get("adoption_request"): a["expectation"]
            for a in cv.asks_about(eid, open_only=False)}
    def note_text(link):
        got = corpus.read([link["link"]["from"]])
        return ((got[0].get("body") or {}).get("text") if got else None)
    def closed_by(r):
        if r["id"] not in open_ids:
            return "declined"
        return "adopted" if answered else None
    return {
        "requests": [{"request": r["id"], "ask": asks.get(r["id"]),
                      "by": (r.get("body") or {}).get("requested_by") or r.get("attributed_to"),
                      "by_alias": cv.alias((r.get("body") or {}).get("requested_by") or r.get("attributed_to")),
                      **_migrated(cv, r),
                      "at": r.get("recorded_at"), "because": note_text(r),
                      "scope": (r.get("body") or {}).get("scope"),
                      "replaces": [{"id": e["id"], "text": _said(e), "since": e.get("recorded_at")}
                                   for ref in (r.get("body") or {}).get("replaces") or []
                                   for e in corpus.read([ref])],
                      "closed": closed_by(r) is not None,
                      "closed_by": closed_by(r)} for r in reqs],
        "declines": [{"by": d.get("attributed_to"), "by_alias": cv.alias(d.get("attributed_to")),
                      "at": d.get("recorded_at"), "because": note_text(d) or "",
                      "request": (d.get("body") or {}).get("request")} for d in declines]}


def _migrated(cv, link):
    """Who carried an old proposal over into a request, when somebody did:
    the request is its proposer's, and the migration is said beside it."""
    by = (link.get("body") or {}).get("migrated_by")
    return {"migrated_by": by, "migrated_by_alias": cv.alias(by)} if by else {}


def _adopted(cv, eid, reads=None):
    acts = [a for a in (reads or _Reads(cv)).acts_about(eid) if
            a["act"] in ("material-adopted", "material-established", "material-superseded", "material-revised")]
    if not acts:
        links = cv._c.read(cv._c.stands(eid)["established_by"])
        if not links:
            return None
        link = max(links, key=lambda e: e.get("recorded_at") or 0)
        return {"by": link.get("attributed_to"), "at": link.get("recorded_at"),
                "because": link["body"].get("reason")}
    a = acts[-1]
    return {"by": a["actor"], "at": a["at"], "because": a.get("because")}


#: how many delivery records and citing records one item's detail carries
#: unless asked for more; the totals are always said beside them
DELIVERED_SHOWN = 25
CITED_SHOWN = 100


def _where(cv, turn):
    """Where a Turn is, so a reader can go to it: its Conversation, that
    Conversation's name and the Turn's number. None where it is no Turn."""
    if not isinstance(turn, str) or not turn.startswith("ent-"):
        return None
    conv = cv.conversation_of(turn)
    if conv is None:
        return None
    return {"conversation": conv, "conversation_name": cv.conversation_name(conv),
            "turn": turn, "number": cv.turn_number(turn)}


def _successor(corpus, successor):
    """What took this entry's place (`stands()["superseded_by"]` names the
    successor itself): its id, Kind and words, and whether it is a deletion
    record -- the entry was ended, not reworded."""
    from mentis.conversation import ladder as read
    from mentis.conversation.versions import is_deletion
    got = corpus.read([successor])
    if got and is_deletion(got[0]):
        return {"id": successor, "kind": "deletion", "label": None, "deleted": True}
    kind, label = read._label(corpus, successor)
    return {"id": successor, "kind": kind, "label": label, "deleted": False}


def _name(entry):
    name = ((entry or {}).get("body") or {}).get("name")
    return name if isinstance(name, str) and name.strip() else None


def _summary(kept, entry, cv=None):
    """The one sentence a list row shows for this record, and where it came
    from (`mentis/record_summaries.py`): the kept one where there is one
    written for these words, else the record's own first sentence, shortened
    (`derived`). Presentation only: nothing else reads it."""
    words = _said(entry)
    row = _summaries.kept_for(kept, entry["id"], words)
    if row is None:
        return {"text": _summaries.derive(words, name=_name(entry)), "source": "derived"}
    out = {"text": row["summary"], "source": row.get("source"), "by": row.get("by"),
           "at": row.get("at"), "model": row.get("model"),
           "earlier": len(row.get("earlier") or ())}
    if cv is not None and isinstance(row.get("by"), str) and row["by"].startswith("ent-"):
        out["by_alias"] = cv.alias(row["by"])
    return out


def _listable(corpus):
    """Every record the browser lists now (what was replaced or deleted left
    out): `(entry, kind, status)`, in no particular order."""
    from mentis.conversation import ladder as read
    requested = {x["link"]["to"] for x in corpus.links(relation="proposes")}
    declined = {x["link"]["to"] for x in corpus.links(relation="declines")}
    for kind, d in kind_definitions(corpus).items():
        knowing = d.get("knowing")
        if knowing not in ("that", "how"):
            continue
        apt = d.get("standing_apt") is True
        for entry in corpus.entries_of_kind(kind):
            eid = entry["id"]
            if not apt and knowing != "that" and eid not in requested and eid not in declined:
                continue
            status = read.adoption_status(corpus, eid)
            if (not apt and status == read.ADOPTED) or status in _PAST:
                continue
            yield entry, kind, status


def _summary_writes(st, path, body, presented):
    """Keeping and correcting record summaries (`mentis/record_summaries.py`).

    THE OWNER'S, AND NOBODY ELSE'S. A summary is how the owner's own lists
    read, so only the owner keeps or corrects one, by hand or by running a
    batch; a worker grant is refused. Nothing is written to the record: no
    Entry, no act. What is kept says where it came from.

      POST /api/ladder/summaries/<id>   {attributed_to, summary}   written by hand
                                        {attributed_to, remove: true}   forgotten
      POST /api/ladder/summaries        {attributed_to, model, items: [{id, summary}]}
                                        a generated batch, each kept or refused by itself
    """
    from mentis.conversation.owner import _owner
    from mentis.web import _attributed
    if presented:
        return {"error": "summaries are kept on the owner's surface, not by a worker grant"}
    payload = body or {}
    by, refusal = _attributed(payload, corpus=st.corpus)
    if refusal:
        return refusal
    if by != _owner(st.cv):
        return {"error": "only the owner keeps or corrects a record's summary"}
    root, corpus = st.corpus.root, st.corpus
    if path != "/api/ladder/summaries":
        eid = path[len("/api/ladder/summaries/"):]
        got = corpus.read([eid])
        if not got:
            return {"error": "the record holds no such entry", "entry": eid}
        if payload.get("remove") is True:
            _summaries.remove(root, eid)
        else:
            try:
                _summaries.put(root, eid, payload.get("summary"), words=_said(got[0]),
                               source="written", by=by)
            except _summaries.Refused as exc:
                return {"error": str(exc)}
        return {"entry": eid, "summary": _summary(_summaries.read(root), got[0], st.cv)}
    items = payload.get("items")
    model = payload.get("model")
    if not isinstance(items, list) or not items or len(items) > _summaries.MAX_BATCH:
        return {"error": f"items is a list of 1..{_summaries.MAX_BATCH} summaries"}
    if not isinstance(model, str) or not model.strip():
        return {"error": "a generated batch says what wrote it (`model`)"}
    kept, refused = [], []
    for item in items:
        eid = item.get("id") if isinstance(item, dict) else None
        got = corpus.read([eid]) if isinstance(eid, str) else []
        if not got:
            refused.append({"id": eid, "why": "the record holds no such entry"})
            continue
        try:
            _summaries.put(root, eid, item.get("summary"), words=_said(got[0]),
                           source="generated", by=by, model=model.strip())
            kept.append(eid)
        except _summaries.Refused as exc:
            refused.append({"id": eid, "why": str(exc)})
    return {"kept": kept, "refused": refused}


def _summaries_missing(st, one):
    """`GET /api/ladder/summaries/missing`: the listed records that have no
    kept summary, with their own words, for whoever writes them -- a bounded
    page, and how many there are in all."""
    try:
        limit, offset = int(one("limit", 100)), int(one("offset", 0))
        if not 1 <= limit <= _summaries.MAX_BATCH or offset < 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"error": f"limit must be 1..{_summaries.MAX_BATCH}, offset nonnegative"}
    kept = _summaries.read(st.corpus.root)
    rows = [(entry, kind, status) for entry, kind, status in _listable(st.corpus)
            if _summaries.kept_for(kept, entry["id"], _said(entry)) is None]
    rows.sort(key=lambda r: (r[0].get("recorded_at") or 0, r[0]["id"]), reverse=True)
    return {"total": len(rows),
            "items": [{"id": e["id"], "kind": kind, "status": status,
                       "governs": knowing_of(st.corpus, kind) == "how",
                       "name": _name(e), "words": _said(e),
                       "fields": {k: v for k, v in (e.get("body") or {}).items()
                                  if isinstance(v, str) and v.strip() and k != "text"}}
                      for e, kind, status in rows[offset:offset + limit]]}


#: THE BROWSER'S VIEWS (Manage Brain in Quiet Chat): ways of looking at the
#: one Ladder, never categories of their own. `knowledge` is knowing `that`,
#: `governing` is knowing `how` (`governs`), `needs-you` is what asks the
#: owner now by Home's own rule, `all` is the first two together.
BROWSE_VIEWS = ("knowledge", "governing", "needs-you", "all")
#: no longer in effect because something took its place or it was deleted:
#: left out of a view unless asked for, so the list is what there is now
_PAST = ("superseded", "deleted")


def _asked_of_owner(cv, corpus):
    """The records the owner is asked about now, by the Needs you rule and
    nothing else (`home.asking_owner`, the list the bell shows): each open ask
    addressed to the owner that names material, or carries an adoption
    request, in that order. `{entry: ask}`; None where no owner is named."""
    from mentis.conversation.owner import _owner
    from mentis.fluid.home import asking_owner
    owner = _owner(cv)
    if owner is None:
        return None
    named = {}
    for _, ask in asking_owner(cv, owner):
        detail = (cv._act(ask) or {}).get("detail") or {}
        refs = list(detail.get("material") or ())
        request = detail.get("adoption_request")
        if request:
            link = (corpus.read([request]) or [None])[0]
            to = ((link or {}).get("link") or {}).get("to")
            if to:
                refs.append(to)
        for ref in refs:
            named.setdefault(ref, ask)
    return named


def _browse(st, one):
    """`GET /api/ladder/browse`: the Brain's records as ONE list, one status
    vocabulary (the Ladder's, `adoption_status`), newest first, paged.

    The page this replaces read two list models with two vocabularies and
    rebuilt standing in the browser, where a declined candidate read as
    Recorded and an unknown one as Recorded too. Here every row's `status` is
    what the record says now, and `governs` is its Kind's declaration.

    WHAT IS LISTED: material of every Kind that declares a knowing -- what the
    Learning and Adopted lists and the authoring sections listed between
    them. `view` narrows it (`BROWSE_VIEWS`); `kind`, `status`, `q`,
    `challenged` narrow it further; `past=1` adds what was replaced or
    deleted, which is otherwise counted (`past`) and left out.

    BOUNDED AND SAID: `limit` 1..200 rows from `offset`; `total` is how many
    match, so a short page is never mistaken for a short record. `kinds` are
    the Kinds present in the view with how many each holds -- the options of
    the filter come from the record, not from a list written into a page.
    Only the rows of the page are attributed (`recorded_by`)."""
    from mentis.conversation import ladder as read
    cv, corpus = st.cv, st.corpus
    view = one("view", "all")
    if view not in BROWSE_VIEWS:
        return {"error": "view is one of " + ", ".join(BROWSE_VIEWS)}
    try:
        limit, offset = int(one("limit", 50)), int(one("offset", 0))
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"error": "limit must be 1..200, offset nonnegative"}
    want_kind, want_status = one("kind"), one("status")
    words = (one("q", "") or "").lower().split()
    with_past = one("past") == "1" or want_status in _PAST
    asked = _asked_of_owner(cv, corpus) if view == "needs-you" else None
    if view == "needs-you" and asked is None:
        return {"items": [], "total": 0, "kinds": [], "past": 0, "unknown": True,
                "why": "the record names no owner"}
    requested = {x["link"]["to"] for x in corpus.links(relation="proposes")}
    declined = {x["link"]["to"] for x in corpus.links(relation="declines")}
    kept = _summaries.read(corpus.root)
    rows, kinds, past = [], {}, 0
    for kind, d in kind_definitions(corpus).items():
        knowing = d.get("knowing")
        if knowing not in ("that", "how"):
            continue
        governs = knowing == "how"
        if (view == "knowledge" and governs) or (view == "governing" and not governs):
            continue
        apt = d.get("standing_apt") is True
        for entry in corpus.entries_of_kind(kind):
            eid = entry["id"]
            if asked is not None and eid not in asked:
                continue
            if words:
                # found by its summary too -- the one a row would SHOW: a kept
                # row not written for these words is no summary here either
                shown = _summaries.kept_for(kept, eid, _said(entry))
                hay = (" ".join(str(v) for v in (entry.get("body") or {}).values())
                       + " " + eid + " " + kind + " "
                       + (shown["summary"] if shown else "")).lower()
                if not all(token in hay for token in words):
                    continue
            if not apt and knowing != "that" and eid not in requested and eid not in declined:
                continue
            status = read.adoption_status(corpus, eid)
            if not apt and status == read.ADOPTED:
                # the notes that hold the reason of a request or a decline
                # stand by their act and are not adoptable: never listed as
                # adopted material (the rule `/api/ladder/adopted` keeps)
                continue
            if status in _PAST and not with_past and asked is None:
                past += 1
                continue
            kinds[kind] = kinds.get(kind, 0) + 1
            if want_kind and want_kind != kind:
                continue
            if want_status and want_status != status:
                continue
            rows.append((entry.get("recorded_at") or 0, eid, entry, kind, governs, status, apt))
    if asked is not None:
        order = {eid: n for n, eid in enumerate(asked)}
        rows.sort(key=lambda r: order.get(r[1], len(order)))
    else:
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    if one("challenged") == "1":
        rows = [r for r in rows if read.open_challenges(corpus, r[1])]
    items = []
    for at, eid, entry, kind, governs, status, apt in rows[offset:offset + limit]:
        by = read.recorded_by(corpus, cv, eid) or {}
        summary = _summary(kept, entry)
        words = _said(entry)
        item = {"id": eid, "kind": kind, "status": status,
                # WHAT A ROW SAYS: one sentence a person can scan. The record's
                # own words follow, shortened: a list does not carry every
                # rule whole (one page was 110 KB), and the item read does.
                "summary": summary["text"], "summary_source": summary["source"],
                "text": words if len(words) <= 400 else words[:399].rstrip() + "…",
                "governs": governs, "adoptable": apt,
                "challenged": len(read.open_challenges(corpus, eid)),
                "recorded_at": at or None,
                "recorded_by": {k: by.get(k) for k in
                                ("participant", "alias", "conversation",
                                 "conversation_name", "turn", "number")}}
        if asked is not None:
            item["ask"] = asked.get(eid)
        items.append(item)
    return {"items": items, "total": len(rows), "past": past,
            "kinds": [{"kind": k, "count": n,
                       "governs": knowing_of(corpus, k) == "how"}
                      for k, n in sorted(kinds.items())]}


def routes(st, path, query, body, method, presented=None):
    if path == "/api/ladder/vocabulary":
        from tools.ladder_vocabulary import plan, apply, migrate
        from mentis.conversation.owner import _owner
        if method != "POST" or presented:
            return {"error": "vocabulary changes use the owner POST surface"}
        owner = _owner(st.cv)
        if not owner:
            return {"error": "the record names no owner"}
        payload = body or {}
        if payload.get("apply"):
            from mentis.web import _attributed
            by, refusal = _attributed(payload, corpus=st.corpus)
            if refusal:
                return refusal
            if by != owner:
                return {"error": "only the owner may apply ladder vocabulary changes"}
        try:
            with st.corpus.atomic():
                changes = plan(st.corpus)
                count = apply(st.corpus, changes, by=owner) if payload.get("apply") else 0
                migration = (migrate(st.cv, by=owner, conversation=payload.get("conversation"),
                                    dry_run=not payload.get("apply"))
                             if payload.get("migrate_proposed") else None)
            return {"changes": changes, "written": count, "dry_run": not payload.get("apply"),
                    "migration": migration}
        except ValueError as exc:
            return {"error": str(exc)}
    from mentis.conversation import ladder as read
    cv, corpus = st.cv, st.corpus
    one = lambda key, default=None: (query.get(key) or [default])[0]
    if method == "POST" and (path == "/api/ladder/summaries"
                             or path.startswith("/api/ladder/summaries/")):
        return _summary_writes(st, path, body, presented)
    if method == "GET" and path == "/api/ladder/summaries/missing":
        return _summaries_missing(st, one)
    if method != "GET":
        return {"error": "ladder reads use GET; act through /api/entries/<id>/<act>"}
    if path.startswith("/api/ladder/items/"):
        eid = path[len("/api/ladder/items/"):]
        got = corpus.read([eid])
        if not got:
            return {"error": "the record holds no such entry", "entry": eid}
        try:
            delivered_limit = int(one("delivered_limit", DELIVERED_SHOWN))
            if not 0 <= delivered_limit <= 500:
                raise ValueError
        except (TypeError, ValueError):
            return {"error": "delivered_limit must be 0..500"}
        reads = _Reads(cv)
        item = _item(corpus, cv, got[0], reads)
        attribution = item["recorded_by"] or {}
        # DELIVERED ONCE, NAMED ONCE, AND BOUNDED. The delivery records naming
        # this entry are read from the request's one index; a participant's
        # alias is read once however many runs it names; and the answer
        # carries the newest `delivered_limit` (one live rule: 1,755 rows,
        # 368 KB, to show a count). `delivered_total` and `usage` still count
        # every one.
        delivered = read.delivered_to(cv, eid, deliveries=reads.delivered(eid),
                                      alias=reads.alias)
        cited = read.cited_by(corpus, eid)
        shown = delivered[len(delivered) - delivered_limit:] if delivered_limit else []
        standing = corpus.stands(eid)
        adopted = _adopted(cv, eid, reads) if standing["stands"] else None
        if adopted:
            scope = _scope(cv, eid)
            adopted = {**adopted, "by_alias": reads.alias(adopted.get("by")),
                       "scope": scope,
                       "scope_label": (None if not scope else "whole Brain"
                                       if scope.get("whole_brain") else scope.get("label"))}
        from mentis.conversation.owner import _owner
        lineage = read.lineage(corpus, eid)
        for node in (*lineage["up"], *lineage["down"]):
            if node.get("kind") == "contribution":
                node["where"] = _where(cv, node["id"])
        return {**item, "lineage": lineage,
                "outcomes": [{**o, "where": _where(cv, o.get("in_context"))}
                             for o in read.outcomes_of(corpus, eid)],
                "basis": [{**b, "where": _where(cv, b["ref"])}
                          if b.get("kind") == "contribution" else b
                          for b in item["basis"]],
                "challenges": read.challenges_of(corpus, eid),
                "delivered": list(reversed(shown)),
                "delivered_total": len(delivered),
                # WHAT CITES IT, AS A READER CAN RECOGNISE IT: the citing
                # record's own words beside its id (a list of bare ids was
                # the "cannot be listed here yet" the old page apologised for)
                "cited_by": [{**c, "label": read._label(corpus, c["entry"])[1]}
                             for c in cited[-CITED_SHOWN:]],
                "cited_total": len(cited),
                "superseded_by": [_successor(corpus, ref)
                                  for ref in standing["superseded_by"]],
                "usage": read.usage(corpus, cv, eid, delivered=delivered, cited=cited),
                "history": _history(cv, eid, reads),
                "originating": {k: attribution.get(k) for k in
                                ("conversation", "conversation_name", "turn", "number")},
                "owner": _owner(cv),
                "summary": _summary(_summaries.read(corpus.root), got[0], cv),
                "adoption": {**_adoption(corpus, cv, eid), "adopted": adopted}}
    if path == "/api/ladder/browse":
        return _browse(st, one)
    if path == "/api/ladder/adoption":
        reads = _Reads(cv)
        cards = []
        for link in corpus.links(relation="proposes"):
            eid = link["link"]["to"]
            if read.adoption_status(corpus, eid) != "adoption_requested":
                continue
            if link["id"] not in {r["id"] for r in requests(corpus, eid, open_only=True)}:
                continue
            entry = corpus.read([eid])[0]
            item = _item(corpus, cv, entry, reads)
            b = link["body"]
            replaced = [e for ref in b.get("replaces") or [] for e in corpus.read([ref])]
            origin = read.recorded_by(corpus, cv, eid) or {}
            request_acts = [a for a in reads.acts("adoption-requested")
                            if (a.get("detail") or {}).get("request") == link["id"]]
            requested = request_acts[-1] if request_acts else {}
            asker = b.get("requested_by") or link.get("attributed_to")
            asked_by = {**(read.recorded_by(corpus, cv, link["link"]["from"]) or {}),
                        "participant": asker, "alias": cv.alias(asker),
                        "runtime": requested.get("runtime"),
                        "conversation": requested.get("conversation") or origin.get("conversation"),
                        "conversation_name": cv.conversation_name(
                            requested.get("conversation") or origin.get("conversation"))
                            if (requested.get("conversation") or origin.get("conversation")) else None,
                        "turn": requested.get("turn") or origin.get("turn"),
                        "number": cv.turn_number(requested.get("turn") or origin.get("turn"))
                            if (requested.get("turn") or origin.get("turn")) else None,
                        "execution": requested.get("execution"),
                        **_migrated(cv, link)}
            ask = next((a["id"] for a in reads.acts("expectation-recorded")
                        if (a.get("detail") or {}).get("adoption_request") == link["id"]), None)
            evidence = []
            for basis in item["basis"]:
                ref = basis.get("ref")
                held = corpus.read([ref])
                evidence.append({"id": ref, "kind": basis.get("kind"),
                    "relation": basis.get("relation"), "label": basis.get("label"),
                    "text": (held[0].get("body") or {}).get("text", "") if held else "",
                    **{k: basis[k] for k in ("cite", "artifact", "range", "excerpt") if k in basis}})
            cards.append({"request": link["id"], "ask": ask, "entry": eid,
                "kind": item["kind"], "governs": item["governs"],
                # WHETHER ADOPTING IT NAMES A CHECK THAT COULD PROVE IT WRONG,
                # from the Kind's current definition, so the card can ask.
                "expects_falsifier": bool(read._declared(corpus, item["kind"], "expects_falsifier")),
                # THE WORDS, as text the card can diff, and the whole bodies
                # beside them for Kinds with more than one field.
                "wording": {"proposed": _said({"body": b.get("wording") or entry["body"]}),
                            "current": _said(replaced[0]) if replaced else None,
                            "proposed_body": b.get("wording") or entry["body"],
                            "current_body": replaced[0]["body"] if replaced else None},
                "because": next((n.get("body", {}).get("text") for n in corpus.read([link["link"]["from"]])), None),
                "replaces": [{"id": e["id"], "text": _said(e),
                              "since": e.get("recorded_at")} for e in replaced],
                "scope": b.get("scope"), "limits": item["limits"], "evidence": evidence,
                "challenges": [c for ref in [eid, *[e["id"] for e in replaced]]
                               for c in read.challenges_of(corpus, ref)],
                "asked_by": asked_by,
                "asked_at": link.get("recorded_at"),
                **{k: origin.get(k) for k in ("conversation", "turn", "number")}})
        return {"requests": cards}
    if path not in ("/api/ladder/items", "/api/ladder/adopted"):
        return {"error": "no such ladder read"}
    try:
        limit = int(one("limit", 50))
        offset = int(one("offset", 0))
        since = float(one("since", 0))
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"error": "limit must be 1..1000, offset nonnegative, since an epoch number"}
    all_items = []
    reads = _Reads(cv)
    want = {k: one(k) for k in ("kind", "conversation", "agent", "runtime", "status")}
    words = (one("q", "") or "").lower().split()
    adopted_view = path.endswith("/adopted")
    for kind, d in kind_definitions(corpus).items():
        if want["kind"] and want["kind"] != kind:
            continue
        for entry in corpus.entries_of_kind(kind):
            eid = entry["id"]
            # THE CHEAP QUESTIONS FIRST, so a full item is built only for
            # entries that can still be listed.
            if (entry.get("recorded_at") or 0) < since:
                continue
            if words:
                hay = " ".join(str(v) for v in (entry.get("body") or {}).values()).lower()
                if not all(token in hay for token in words):
                    continue
            standing = corpus.stands(eid)["stands"]
            if adopted_view:
                # ADOPTED IS ADOPTABLE MATERIAL THAT STANDS (owner decision 2,
                # review B1). The notes holding a request's because, a decline's,
                # withdrawal's or objection's reason are established by their
                # act, and are notes -- not adoptable -- so they never appear;
                # adopted material later used as an objection still does.
                eligible = standing and adoptable(corpus, entry)
            else:
                eligible = ((d.get("knowing") == "that" and not standing)
                            or bool(requests(corpus, eid))
                            or bool(corpus.links(relation="declines", to=eid)))
            if not eligible:
                continue
            if any(want[k] for k in ("conversation", "agent", "runtime")):
                attribution = read.recorded_by(corpus, cv, eid) or {}
                if want["conversation"] and want["conversation"] not in (
                        attribution.get("conversation"), attribution.get("conversation_name")):
                    continue
                if want["runtime"] and want["runtime"] != attribution.get("runtime"):
                    continue
                # THE AGENT, as the filter row names one: a participant id, an
                # alias with or without its `@`, the runtime it ran on, or the
                # Persona it was wearing, by id or name.
                if want["agent"] and want["agent"].lstrip("@").lower() not in {
                        str(v).lstrip("@").lower() for v in (
                            attribution.get("participant"), attribution.get("alias"),
                            attribution.get("runtime"), attribution.get("persona"),
                            attribution.get("persona_name")) if v}:
                    continue
            item = _item(corpus, cv, entry, reads)
            if adopted_view:
                adopted = _adopted(cv, eid, reads) or {}
                item.update(adopted_by=adopted.get("by"),
                            adopted_by_alias=cv.alias(adopted["by"]) if adopted.get("by") else None,
                            adopted_at=adopted.get("at"),
                            because=adopted.get("because"), scope=_scope(cv, eid),
                            history=_history(cv, eid, reads), challenges=read.challenges_of(corpus, eid))
            all_items.append(item)
    all_items.sort(key=lambda i: i["recorded_at"] or 0, reverse=True)
    # THE COUNTS ARE THE CHIPS, so they are taken BEFORE the status and
    # challenged filters the chips themselves set: choosing "adoption
    # requested" must not turn its sibling chips to zero. Every other filter
    # (Kind, Conversation, Agent, recency, words) narrows them as it narrows
    # the list. `all` is what the first chip offers: everything they cover.
    counts = {k: sum(i["status"] == k for i in all_items) for k in
              ("recorded", "adoption_requested", "adopted", "declined")}
    counts.update(all=len(all_items),
                  challenged=sum(bool(i["challenged"]) for i in all_items),
                  delivered=sum(bool(i["delivered_to"]) for i in all_items),
                  without_basis=sum(not i["basis"] for i in all_items))
    if want["status"] == "without_basis":
        all_items = [i for i in all_items if not i["basis"]]
    elif want["status"]:
        all_items = [i for i in all_items if i["status"] == want["status"]]
    if one("challenged") == "1":
        all_items = [i for i in all_items if i["challenged"]]
    return {"items": all_items[offset:offset + limit], "total": len(all_items), "counts": counts}
