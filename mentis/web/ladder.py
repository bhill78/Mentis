"""Fluid's ladder reads. Status and provenance belong to the shared read model.

This adapter builds cards, filters and counts from those facts. It never
stores a status, and a challenge is counted separately from standing.
"""
from __future__ import annotations

from mentis.conversation import knowing_of, placements_now
from mentis.conversation.ladder_writes import adoptable, requests
from mentis.conversation.register import kind_definitions


class _Reads:
    """What one request reads once and every item in it shares: the acts by
    the entry they are about, and the delivery records. Measured on
    INTEGRATION (the live Brain's copy): reading the whole act history twice
    per item, and every delivery record once per item, made /api/ladder/adopted
    take 41 s and starved the Learning read the page makes beside it."""

    def __init__(self, cv):
        self.cv = cv
        self._acts = None
        self._deliveries = None

    def acts_about(self, eid):
        if self._acts is None:
            self._acts, self._all = {}, self.cv.history()
            for a in self._all:
                for about in dict.fromkeys(a.get("about") or ()):
                    self._acts.setdefault(about, []).append(a)
        return self._acts.get(eid, [])

    def deliveries(self):
        if self._deliveries is None:
            self._deliveries = self.cv._c.deliveries()
        return self._deliveries

    def acts(self, name):
        """Every act of this name, oldest first."""
        if self._acts is None:
            self.acts_about(None)
        return sorted((a for a in self._all if a["act"] == name),
                      key=lambda a: a["at"])


def _history(cv, eid, reads=None):
    acts = (reads or _Reads(cv)).acts_about(eid)
    return [{"at": a["at"], "act": a["act"], "by": a["actor"],
             "by_alias": cv.alias(a["actor"]) if a.get("actor") else None,
             "because": a.get("because")} for a in acts]


def _item(corpus, cv, entry, reads=None):
    from mentis.conversation import ladder as read
    eid = entry["id"]
    kind = (entry.get("definition") or {}).get("name")
    fields = entry.get("body") or {}
    outcomes = read.outcomes_of(corpus, eid)
    challenges = read.challenges_of(corpus, eid)
    return {"id": eid, "kind": kind, "text": fields.get("text", ""),
            "fields": fields, "limits": fields.get("limits"),
            "status": read.adoption_status(corpus, eid),
            "challenged": sum(c["resolution"] == "open" for c in challenges),
            "recorded_by": read.recorded_by(corpus, cv, eid),
            "recorded_at": entry.get("recorded_at"),
            "basis": read.basis_of(corpus, eid),
            "outcomes": {"count": len(outcomes), "latest": outcomes[:3]},
            "delivered_to": len(read.delivered_to(cv, eid, deliveries=(reads.deliveries() if reads else None))),
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


def routes(st, path, query, body, method, presented=None):
    if path == "/api/ladder/vocabulary":
        from tools.ladder_vocabulary import plan, apply, migrate
        from mentis.wakecheck import _owner
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
    if method != "GET":
        return {"error": "ladder reads use GET; act through /api/entries/<id>/<act>"}
    if path.startswith("/api/ladder/items/"):
        eid = path[len("/api/ladder/items/"):]
        got = corpus.read([eid])
        if not got:
            return {"error": "the record holds no such entry", "entry": eid}
        reads = _Reads(cv)
        item = _item(corpus, cv, got[0], reads)
        attribution = item["recorded_by"] or {}
        return {**item, "lineage": read.lineage(corpus, eid),
                "outcomes": read.outcomes_of(corpus, eid),
                "challenges": read.challenges_of(corpus, eid),
                "delivered": read.delivered_to(cv, eid, deliveries=reads.deliveries()),
                "cited_by": read.cited_by(corpus, eid),
                "usage": read.usage(corpus, cv, eid), "history": _history(cv, eid, reads),
                "originating": {k: attribution.get(k) for k in
                                ("conversation", "conversation_name", "turn", "number")},
                "adoption": {**_adoption(corpus, cv, eid),
                    "adopted": _adopted(cv, eid, reads) if corpus.stands(eid)["stands"] else None}}
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
