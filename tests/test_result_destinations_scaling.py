"""B3: measure the real CurrentWork build and tail at historical Brain scale.

Synthetic append-only records only. Timings are evidence, not flaky CI gates;
query shape/count and affected-work invalidation are the regression checks.
"""
from __future__ import annotations

import json
import time

from mentis.conversation import text
from mentis.operational import current_work as cw
from mentis.operational import result_destinations as rd
from tests._loop import world  # noqa: F401


def test_batched_projection_at_realistic_scale_and_tail_invalidation(world, monkeypatch):
    cv, who = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Projection scaling", attributed_to=who)
    monkeypatch.setattr(cw, "_window", lambda *a: None)
    roots, children = [], []
    store = cv.corpus._store
    real_rows, real_structural = store._rows, rd.structural
    measured, active = {}, False

    def rows(sql, args=()):
        started = time.perf_counter()
        got = real_rows(sql, args)
        if active and "FROM operational" in sql:
            measured["operational_sql_seconds"] += time.perf_counter() - started
            if "instr(about" in sql and "act =" not in sql:
                measured["unindexed_about_scans"] += 1
            if "act IN" in sql and set(args) == {
                    "work-delegated", "expectation-assigned", "expectation-met"}:
                measured["relationship_batches"] += 1
            if "caused_by =" in sql or "caused_by IN" in sql:
                measured["indexed_parent_queries"] += 1
        return got

    def structural(ctx, root):
        nonlocal active
        started = time.perf_counter()
        active = True
        try:
            return real_structural(ctx, root)
        finally:
            active = False
            measured["projection_calls"] += 1
            measured["projection_seconds"] += time.perf_counter() - started

    monkeypatch.setattr(store, "_rows", rows)
    monkeypatch.setattr(rd, "structural", structural)

    def measure(label, action):
        measured.clear()
        measured.update(projection_calls=0, projection_seconds=0,
                        operational_sql_seconds=0, unindexed_about_scans=0,
                        relationship_batches=0, indexed_parent_queries=0)
        started = time.perf_counter()
        model = action()
        evidence = {"phase": label, "trunks": len(roots),
                    "children": len(children), "acts": store.operational_count(),
                    "build_or_update_seconds": time.perf_counter() - started,
                    **measured}
        print("SCALING " + json.dumps(evidence, sort_keys=True))
        assert measured["unindexed_about_scans"] == 0
        assert measured["relationship_batches"] == 1
        return model

    cw.forget()
    try:
        for count, acts in ((155, 3898), (2075, 84000)):
            with cv.corpus.atomic():
                for n in range(len(roots), count):
                    turn = cv.say(cid, who, [text(f"Design generation request {n}")])
                    root = cv.expect(turn, of=who, kind="result", by=who, conversation=cid)
                    roots.append(root)
                    for k in range(2):
                        child = cv.expect(turn, of=who, kind="result", by=who,
                                          conversation=cid, caused_by=root)
                        children.append(child)
                        cv.record_act(actor=who, act="work-delegated", caused_by=root,
                                      conversation=cid, about=[child], detail={})
                        start = cv.record_act(actor=who, act="execution-started",
                                              caused_by=child, conversation=cid,
                                              execution=f"scale-{n}-{k}", detail={})
                        cv.record_act(actor=who, act="result-returned", caused_by=start,
                                      conversation=cid, turn=turn,
                                      execution=f"scale-{n}-{k}",
                                      detail={"returned_artifacts": []})
                # Substantial unrelated operational history, with realistic
                # detail sizes; not 84k duplicate mock calls or an empty table.
                for n in range(acts - store.operational_count()):
                    cv.record_act(actor=who, act="record-consulted", conversation=cid,
                                  detail={"ref": f"ent-{n:012x}",
                                          "reason": "Historical routing evidence. " * 16})
            kept = cw.CurrentWork(cv, cid)
            model = measure("build", lambda: kept.current(wait=True))
            assert len(model.items) == count
            assert measured["projection_calls"] == count
            # All child membership is retained in the result dependencies.
            assert children[-1] in model.items[roots[-1]]["_result_index"]["deps"]
            # The actual walk/prefetch uses the existing causal-parent index.
            plan = real_rows("EXPLAIN QUERY PLAN SELECT * FROM operational WHERE caused_by = ?",
                             (roots[-1],))
            assert any("idx_operational_caused_by" in str(tuple(r)) for r in plan)

        # An earlier standalone result becomes a legacy follow-up only after
        # this append. Tail invalidation must see both the parent and source.
        with cv.corpus.atomic():
            turn = cv.say(cid, who, [text("Earlier source-only report")])
            follow = cv.expect(turn, of=who, kind="result", by=who, conversation=cid)
            cv.record_act(actor=who, act="outcome-claimed", caused_by=follow, turn=turn,
                          conversation=cid, detail={"reply_turn": turn, "results": [turn]})
        measure("new-result", lambda: kept.current(wait=True))
        before = kept.stats["projected"]
        builds = kept.stats["builds"]
        cv.record_act(actor=who, act="expectation-met", caused_by=follow,
                      detail={"carried_under": roots[-1]})
        model = measure("legacy-attachment-tail", lambda: kept.current(wait=True))
        assert kept.stats["builds"] == builds
        assert kept.stats["projected"] - before == 2
        assert {i["ref"] for g in model.items[roots[-1]]["_result_index"]["groups"]
                for i in g["items"]} == {turn}
        # Reconcile is a fresh-context rebuild; no stale relationship maps.
        assert measure("reconcile", kept.reconcile) == []
    finally:
        cw.forget()
