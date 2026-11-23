"""Prepare, bind, reconcile and freeze after ordinary Composer/Work execution.

Manifests describe inputs. Existing grants alone decide artifact reach.
"""
from __future__ import annotations

import json

from mentis import artifacts
from mentis.conversation import anchors
from mentis.conversation import GOVERNING_PREFIXES, GOVERNING_SCOPES, WHOLE_BRAIN_SCOPE
from mentis.conversation.versions import Refused
from mentis.fluid.inspect import brain_key

from . import _path
from . import perspectives as P
from . import perspectives_evidence as E


def _package(st, mid, kind, **values):
    return {"format": P.FORMAT, "version": 1, "kind": kind,
            "brain": brain_key(st.corpus), "magnet": mid, **values}


def _question(st, mid, topic, ref):
    rows = st.corpus.operational(act=P.ACT, detail_is={"magnet": mid, "perspective": topic,
        "event": "question"}, detail_names=ref, limit=2)
    if not any(a["detail"]["snapshot"]["ref"] == ref for a in rows):
        P.refuse("wrong-question", "this is not an immutable question revision of this Perspective")
    desc = E.descriptor(st, ref)
    obj = E.native(st, mid, ref, E.bounded_read(st, desc, E.MAX_BYTES), "question")
    if obj.get("perspective") != topic:
        P.refuse("wrong-question", "the question belongs to a different Perspective")
    return desc, obj


def _record_package(st, mid, topic, continuation):
    events, deps, cursor, cost = [], [], None, 0
    # The product follows its own bounded durable-history read. Total bytes
    # are bounded too; no recall window or browser storage reconstructs this.
    while True:
        page = P.history(st, mid, topic, limit=100, cursor=cursor)
        for row in page["events"]:
            cost += len(P.encoded(row))
            if cost > E.MAX_BYTES:
                P.refuse("history-too-large", "this continuation's durable records exceed 8 MiB; "
                         "choose a narrower explicit inquiry or start a fresh inquiry")
            events.append(row)
            if continuation:
                deps.append(row["snapshot"])
                # Event snapshots retain metadata; immutable input packages
                # referenced by prior preparations/answers carry full closure.
                data = row["data"]
                for key in ("manifest", "answer"):
                    if isinstance(data.get(key), dict) and "ref" in data[key]:
                        deps.append(data[key])
        cursor = page["next"]
        if not cursor:
            break
    unique = {d["ref"]: d for d in deps}
    if len(unique) > E.MAX_REFS:
        P.refuse("reference-limit", "this continuation's complete durable history exceeds 32 Admissions; "
                 "choose a narrower explicit inquiry or start fresh")
    return _package(st, mid, "records", perspective=topic, through=page["through"],
                    continuation=continuation, events=events, dependencies=list(unique.values()))


def prepare(st, mid, topic, body, by, written_by):
    q, question = _question(st, mid, topic, body.get("question"))
    batches = E.refs(body.get("batches"), "batches")
    if not batches:
        P.refuse("batch-required", "select at least one retained collection batch")
    priors = E.refs(body.get("priors", []), "priors")
    declared = E.refs(body.get("declared_context", []), "declared_context")
    if type(body.get("continuation", False)) is not bool:
        P.refuse("invalid-continuation", "continuation is true or false")
    # Reserve the manifest node from the outset. Its exact bytes are added
    # before admitting the package; it never escapes the 32/8 MiB bound.
    closure = E.Closure(st, mid, reserve_refs=1)
    captured = {}
    for ref in batches:
        closure.add(ref)
        captured[ref] = E.batch(st, mid, closure.nodes[ref], closure.raw[ref])
    closure.add(q["ref"], q)
    originals = E.originals(captured, body.get("selections"))
    for ref in priors:
        closure.add(ref)
        prior = E.native(st, mid, ref, closure.raw[ref], "answer")
        # Reuse is a new qualification, not trust in an older passing receipt.
        prior_topic, intent = prior["perspective"], prior["intent"]
        check = reconcile(st, mid, prior_topic, {"intent": intent, "purpose": "reuse"}, by, written_by)
        if check["status"] != "qualified":
            P.refuse("prior-unqualified", "this earlier interpretation is not currently qualified for reuse",
                     ref=ref, reconciliation=check)
        originals.extend(prior.get("originals", []))
    for ref in declared:
        closure.add(ref)
    # Raw current definition, not a normalized projection; old batches also
    # retain their original raw definitions independently in their bytes.
    try:
        path = _path(st.corpus.root, mid)
        size = path.stat().st_size
        if size > E.MAX_BYTES - closure.bytes:
            P.refuse("byte-limit", "the raw definition does not fit the 8 MiB input package")
        with path.open("rb") as stream:
            raw_definition = stream.read(size)
        if len(raw_definition) != size:
            raise OSError("definition changed while read")
        raw_definition.decode("utf-8")
    except (OSError, UnicodeError):
        P.refuse("definition-unreadable", "the Magnet's exact current definition could not be frozen")
    if len(raw_definition) > E.MAX_BYTES - closure.bytes:
        P.refuse("byte-limit", "the raw definition does not fit the 8 MiB input package")
    # The raw bytes are held verbatim; format metadata belongs in the manifest.
    held_definition = artifacts.hold(st.corpus, st.cv, raw_definition, act=artifacts.SUBMITTED,
        actor=by, source=f"magnet-definition:{mid}", door="magnet-perspective-definition",
        claimed_name=f"{mid}-definition.json", claimed_media_type="application/json")
    definition = {"ref": held_definition["admission"], "digest": held_definition["digest"],
                  "size": len(raw_definition), "media_type": "application/json"}
    closure.add(definition["ref"], definition)
    records = P.hold(st, mid, _record_package(st, mid, topic, body.get("continuation", False)),
                     by, name="records")
    closure.add(records["ref"], records)
    originals = E.deduplicate(originals)
    manifest = _package(st, mid, "manifest", perspective=topic, question=q,
        definition=definition, batches=[closure.nodes[r] for r in batches],
        records=records, priors=[closure.nodes[r] for r in priors],
        declared_context=[closure.nodes[r] for r in declared],
        originals=originals, support="supported" if originals else "unsupported",
        omissions=[{"batch": ref, "page_state": obj["page"].get("state"),
                    "sources": [{"key": s["key"], "status": s.get("status"),
                                  "reason": s.get("reason"), "kept": s.get("kept")}
                                 for s in obj["page"]["sources"]]} for ref, obj in captured.items()],
        edges=closure.edges, direct=batches + [q["ref"], definition["ref"], records["ref"]] + priors + declared,
        dependencies=list(closure.nodes.values()))
    manifest_bytes = P.encoded(manifest)
    if closure.bytes + len(manifest_bytes) > E.MAX_BYTES:
        P.refuse("byte-limit", "the complete input package, including its manifest, exceeds 8 MiB "
                 "(8388608 bytes); narrow sources, types or dates and Collect a smaller batch",
                 size=closure.bytes + len(manifest_bytes), limit=E.MAX_BYTES,
                 batches=[closure.nodes[r] for r in batches])
    held_manifest = P.hold(st, mid, manifest, by, name="manifest")
    all_artifacts = list(closure.nodes.values()) + [held_manifest]
    row = P.event(st, mid, topic, "prepared", {"question": q, "manifest": held_manifest,
        "records": records, "artifacts": all_artifacts,
        "closure": {"count": len(all_artifacts), "bytes": closure.bytes + held_manifest["size"]},
        "text": question["text"]}, by, written_by=written_by)
    return _prepared(row, mid, topic)


def _prepared(row, mid, topic):
    d = row["data"]
    return {"intent": row["post"], "magnet": mid, "perspective": topic,
        "brain": row["snapshot_brain"] if "snapshot_brain" in row else None,
        "question": d["question"], "manifest": d["manifest"], "records": d["records"],
        "artifacts": d["artifacts"], "closure": d["closure"], "reach": "work",
        "request_op": "perspective-request:" + row["post"], "text": d["text"],
        "parts": [{"type": "file", "ref": a["ref"], "media_type": a["media_type"],
                   "alt": "Perspective evidence"} for a in d["artifacts"]], "disclosure": P.DISCLOSURE}


def intent(st, mid, topic, identity):
    P._topic(st, mid, topic)
    row = P._last(st, mid, topic, "prepared", post=identity)
    if not row:
        P.refuse("wrong-intent", "this is not a prepared immutable intent of this Perspective")
    # Verify the snapshot instead of trusting mutable definition/config state.
    d = row["snapshot"]
    snap = E.native(st, mid, d["ref"], E.bounded_read(st, E.descriptor(st, d["ref"]), E.MAX_BYTES), "event")
    if snap.get("data") != row["data"] or snap.get("perspective") != topic:
        P.refuse("intent-unreadable", "the durable intent record no longer verifies")
    row["snapshot_brain"] = snap["brain"]
    return row


def binding(st, mid, topic, identity):
    rows = st.corpus.operational(act=P.ACT,
        detail_is={"magnet": mid, "perspective": topic, "event": "bound"},
        detail_names=identity, newest_first=True, limit=2)
    return next((a["detail"]["data"] for a in rows
                 if a["detail"]["data"].get("intent") == identity), None)


def intent_read(st, mid, topic, identity):
    row = intent(st, mid, topic, identity)
    answers = st.corpus.operational(act=P.ACT,
        detail_is={"magnet": mid, "perspective": topic, "event": "answered"},
        detail_names=identity, limit=101)
    return {"prepared": _prepared(row, mid, topic), "binding": binding(st, mid, topic, identity),
            "answers": [a["detail"]["data"]["answer"] for a in answers
                        if a["detail"]["data"].get("intent") == identity]}


def bind(st, mid, topic, body, by, written_by):
    row = intent(st, mid, topic, body.get("intent"))
    prepared = _prepared(row, mid, topic)
    request = body.get("request")
    exp = st.cv._act(request) if isinstance(request, str) else None
    if not exp or exp["act"] != "expectation-recorded" or exp.get("conversation") != P.home(st, mid):
        P.refuse("wrong-request", "bind the actual recorded request in this Magnet's own Conversation")
    prior = binding(st, mid, topic, row["post"])
    if prior and prior["request"] != request:
        P.refuse("intent-already-bound", "this intent is already bound to its original request")
    turn = st.corpus.read([exp.get("turn")])
    if not turn or turn[0].get("attributed_to") != by or str(turn[0].get("written_by") or "").startswith("execution:"):
        P.refuse("wrong-request-author", "the actual asking Turn must be the owner's ordinary request")
    keyed = anchors.outcome_of(st.cv, by, prepared["request_op"])
    result = (keyed or {}).get("result", {})
    if result.get("turn", result.get("post")) != exp["turn"]:
        P.refuse("request-key-mismatch", "the request does not carry this intent's original send operation key")
    parts = turn[0].get("body", {}).get("parts", [])
    words = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
    if not words.startswith(prepared["text"]):
        P.refuse("question-mismatch", "the actual asking Turn does not begin with the frozen question")
    attached = {p.get("ref") for p in parts if p.get("type") == "file"}
    required = {a["ref"] for a in prepared["artifacts"]}
    if required - attached:
        P.refuse("attachments-missing", "attach every immutable input as an actual request file part",
                 missing=sorted(required - attached))
    if artifacts.reach_of(st.cv, request).get("reach") != "work":
        P.refuse("work-reach-required", "Perspective requests must use work reach")
    data = {"intent": row["post"], "request": request, "post": exp["turn"]}
    out = P.event(st, mid, topic, "bound", data, by, written_by=written_by)
    return {**data, "event": out}


def _latest_start(st, request):
    rows = st.corpus.operational(act="execution-started", caused_by=request, newest_first=True, limit=1)
    return rows[0] if rows else None


def _actual_grant(st, mid, topic, identity, request, start):
    """Actual delivered facts only. No call to compose/governing_now.

    This baseline's web.dispatch.governing_ids computes CURRENT governance;
    it is not a historical-delivery read. A persisted live receipt is exact.
    Otherwise use the recorded dispatch delivery only when its join is unique;
    ambiguous resumed delivery stays pending instead of guessing by time.
    """
    authority = st.agents.authority
    token = authority.grant_of(start["execution"])
    live = authority.grant_for(token, st.path) if token else None
    if (live and live.get("expectation") == request and live.get("run") == start["id"]
            and live.get("delivered")):
        return {"expectation": request, "delivered": live["delivered"], "run": start["id"]}, "live-grant"
    receipts = _receipt_rows(st, mid, topic, identity)
    for row in receipts:
        d = row["detail"]["data"]
        if d.get("run") == start["id"] and isinstance(d.get("grant"), dict):
            return d["grant"], "recorded-live-grant"
    offered = st.corpus.operational(act=artifacts.MADE_AVAILABLE, execution=start["execution"],
        caused_by=start["id"], limit=2)
    if not offered:
        return None, "delivery-not-known"
    # MADE_AVAILABLE is emitted after actual execution and records the exact
    # dispatch artifact offering. It proves empty governing artifact reach too.
    governing = {w["governing"] for a in offered for w in (a.get("detail") or {}).get("why", [])
                 if w.get("because") == "drawn-on-by-governed" and w.get("governing")}
    # Recover all governing ids from the actual delivery where the baseline
    # has an unambiguous request-tagged boundary. Never recompute them now.
    starts = st.corpus.operational(act="execution-started", caused_by=request,
                                  actor=start["actor"], limit=2)
    if len(starts) == 1:
        deliveries = [d for d in st.corpus.deliveries(participant=start["actor"])
                      if any(s.get("for_expectation") == request for s in d.get("behavioural_sources", []))]
        if len(deliveries) == 1:
            governing.update(s["source_id"] for s in deliveries[0]["behavioural_sources"]
                if s.get("for_expectation") == request and s.get("source_id")
                and s.get("supplied_as") == "governance"
                and not s.get("source_kind", "").endswith("orientation")
                and (s.get("scope") in GOVERNING_SCOPES or s.get("scope") == WHOLE_BRAIN_SCOPE
                     or s.get("scope", "").startswith(GOVERNING_PREFIXES)))
            return {"expectation": request, "delivered": sorted(governing), "run": start["id"]}, "recorded-dispatch"
    # The recorded offering is an authoritative delivered-artifact fact, even
    # when this baseline cannot join all governing ids to a resumed boundary.
    # Preserve and union those exact facts in available(), with current record
    # reach; do not claim the missing governing-delivery join complete.
    return None, "recorded-delivery-join-unavailable"


def _receipt_rows(st, mid, topic, identity):
    return st.corpus.operational(act=P.ACT,
        detail_is={"magnet": mid, "perspective": topic, "event": "reconciled"},
        detail_names=identity, newest_first=True, limit=100)


def _declared(st, mid, topic, identity, supplied):
    refs = list(supplied)
    # Explicit declarations persist as receipt versions, separately from the
    # original immutable manifest. They are never inferred from available().
    for row in _receipt_rows(st, mid, topic, identity):
        refs.extend(row["detail"]["data"].get("declared_context", []))
    return list(dict.fromkeys(refs))


def reconcile(st, mid, topic, body, by, written_by):
    if body.get("purpose") not in ("resume", "attach", "display", "reuse"):
        P.refuse("purpose-required", "reconcile for resume, attach, display or reuse")
    row = intent(st, mid, topic, body.get("intent"))
    bound = binding(st, mid, topic, row["post"])
    if not bound:
        P.refuse("request-not-bound", "bind the actual request before reconciling its delivered reach")
    request = bound["request"]
    start = _latest_start(st, request)
    execution = body.get("execution")
    if execution and (not start or start["execution"] != execution):
        P.refuse("late-execution", "this response is not from the request's latest execution")
    declared = _declared(st, mid, topic, row["post"],
                         E.refs(body.get("declared_context", []), "declared_context"))
    prepared = _prepared(row, mid, topic)
    required = {a["ref"] for a in prepared["artifacts"]} | set(declared)
    grant, source = _actual_grant(st, mid, topic, row["post"], request, start) if start else (None, "not-started")
    available, missing, extra, closure, errors = [], [], [], None, []
    status = "pending"
    if grant is not None:
        available = artifacts.available(st.corpus, st.cv, grant)
        # Exclude only this committed run's own produced outputs, never an
        # earlier return on a reused MARS session or prior run of this request.
        returns = st.corpus.operational(act=artifacts.RETURNED, execution=start["execution"],
                                        caused_by=request)
        order = st.corpus.operational_order([start["id"]] + [a["id"] for a in returns])
        outputs = {a["about"][0] for a in returns if a.get("about")
                   and order[a["id"]] > order[start["id"]]}
        reachable = {a["ref"] for a in available}
        missing = sorted(required - reachable)
        extra = [a for a in available if a["ref"] not in required and a["ref"] not in outputs]
        try:
            graph = E.Closure(st, mid)
            graph.add(prepared["manifest"]["ref"], prepared["manifest"])
            for ref in declared:
                graph.add(ref)
            closure = graph.summary()
        except Refused as exc:
            errors.append(exc.refusal)
        status = "qualified" if not missing and not extra and not errors else "unqualified"
    data = {"intent": row["post"], "request": request, "execution": start["execution"] if start else None,
        "run": start["id"] if start else None, "status": status, "source": source,
        "purpose": body["purpose"], "grant": grant, "declared_context": declared,
        "required_unavailable": missing, "reachable_not_declared": extra, "available": available,
        "closure": closure, "errors": errors, "disclosure": P.DISCLOSURE}
    snap = P.hold(st, mid, _package(st, mid, "receipt", perspective=topic, **data), by, name="receipt")
    P.event(st, mid, topic, "reconciled", data, by, snapshot=snap, written_by=written_by)
    return {"receipt": snap, **data}


def finalize(st, mid, topic, body, by, written_by):
    row = intent(st, mid, topic, body.get("intent"))
    bound = binding(st, mid, topic, row["post"])
    if not bound:
        P.refuse("request-not-bound", "bind this intent's actual request first")
    start = _latest_start(st, bound["request"])
    if not start or body.get("execution") != start["execution"]:
        P.refuse("late-execution", "a late answer cannot be frozen for a newer execution")
    answer = body.get("answer")
    turns = st.corpus.read([answer]) if isinstance(answer, str) else []
    if (not turns or not st.cv._is_kind(answer, "contribution")
            or st.cv.conversation_of(answer) != P.home(st, mid)
            or turns[0].get("attributed_to") != start["actor"]):
        P.refuse("wrong-answer", "select an actual answer by this request's producing execution")
    # Exact producing association, not merely a same-author reply or prose id.
    acts = st.corpus.operational(execution=start["execution"], turn=answer)
    ids = [a["id"] for a in acts] + [start["id"]]
    order = st.corpus.operational_order(ids)
    proven = any(order[a["id"]] > order[start["id"]]
                 and a.get("caused_by") in (bound["request"], start["id"])
                 and a["act"] in ("turn-said", "result-returned", "result-recovered") for a in acts)
    ends = st.corpus.operational(caused_by=start["id"], act=("result-returned", "result-recovered"))
    proven = proven or any((a.get("detail") or {}).get("reply_turn") == answer for a in ends)
    if not proven:
        P.refuse("answer-not-produced", "the record does not associate this answer with this committed run")
    check = reconcile(st, mid, topic, {"intent": row["post"], "execution": start["execution"],
        "purpose": "attach"}, by, written_by)
    if check["status"] != "qualified":
        # Keep the failed/pending receipt durable. The raw reply remains an
        # ordinary reply; no answer artifact or synthesized history is made.
        return {"answer": None, "receipt": check, "event": None, "refused": True,
                "code": "unqualified-answer", "error": "the ordinary reply is not qualified as a synthesis"}
    prepared = _prepared(row, mid, topic)
    desc = prepared["manifest"]
    graph = E.Closure(st, mid)
    graph.add(desc["ref"], desc)
    manifest = graph.objects[desc["ref"]]
    dependencies = [desc]
    dependencies.extend(E.descriptor(st, ref) for ref in check["declared_context"])
    snap = P.hold(st, mid, _package(st, mid, "answer", perspective=topic, intent=row["post"],
        request=bound["request"], request_post=bound["post"], answer=answer,
        execution=start["execution"], run=start["id"], manifest=desc,
        parts=turns[0]["body"]["parts"], originals=manifest["originals"], support=manifest["support"],
        receipt=check["receipt"], dependencies=dependencies), by, name="answer")
    out = P.event(st, mid, topic, "answered", {"intent": row["post"], "request": bound["request"],
        "answer": snap, "answer_post": answer, "manifest": desc, "execution": start["execution"],
        "run": start["id"]}, by, snapshot=snap, written_by=written_by)
    return {"answer": snap, "receipt": check, "event": out}
