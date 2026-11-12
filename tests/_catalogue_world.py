"""A MARS catalogue as Workstream A serves it (`modelCatalogue` per backend,
docs/model-selection-contract.md section 1), and a real posting / delegate /
dispatch world over it. Shared by the requirement and selection tests."""

from __future__ import annotations

import time

import pytest

from mentis.web import dispatch as D
from tests._loop import a_conversation, say

ALL = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def model(mid, efforts=("low", "medium", "high"), *, status="listed",
          aliases=(), alias_of=None, group=None, effort_in_id=False,
          verified=True, locality="remote"):
    return {"id": mid, "displayName": None, "aliases": list(aliases),
            "aliasOf": alias_of, "status": status, "statusAt": None,
            "statusWhy": "MARS saw set_model fail" if status == "refused" else None,
            "efforts": list(efforts) if efforts is not None else None,
            "effortsVerified": bool(verified and efforts is not None),
            "effortInId": effort_in_id, "defaultEffort": None,
            "contextWindow": None, "locality": locality,
            "capabilities": {"tools": "unknown"}, "quotaGroup": group,
            "providerSaid": None}


def backend(rid, models, *, default=None, available=True, capabilities=(),
            lacks=None, efforts=ALL, routing_models=()):
    return {"id": rid, "kind": "acp", "available": available,
            "reason": None if available else "MARS lists it unavailable",
            "models": [m["id"] for m in models], "efforts": list(efforts),
            "effectiveDefaultModel": default,
            "routingModels": list(routing_models),
            "modelCatalogue": {"complete": True, "why": None,
                               "source": "configOptions",
                               "readAt": time.time(), "models": list(models)},
            "capabilities": list(capabilities), "lacks": dict(lacks or {}),
            "supports": {"mcp": ["stdio"]}}


def claude(**kw):
    return backend("claude", [
        model("claude-haiku-4-5-20251001", ("low", "medium")),
        model("claude-sonnet-5", ("low", "medium", "high")),
        model("claude-opus-5", ("low", "medium", "high", "xhigh", "max")),
        model("opus", None, alias_of="claude-opus-5")],
        default="claude-sonnet-5",
        capabilities=("build_ui", "drive_browser"), **kw)


def codex(**kw):
    return backend("codex", [
        model("gpt-6-luna", ("minimal", "low")),
        model("gpt-6.1-terra", ("medium", "high")),
        model("gpt-6.1-sol", ("high", "xhigh"))],
        default="gpt-6.1-terra",
        lacks={"drive_browser": "its sandbox denied Playwright (EACCES)"}, **kw)


def antigravity(**kw):
    """Effort in the id; nothing the legacy table names."""
    return backend("antigravity", [
        model("gemini-4-argon-low", None, effort_in_id=True, group="Gemini"),
        model("gemini-4-argon-high", None, effort_in_id=True, group="Gemini"),
        model("claude-opus-5-5-high", None, effort_in_id=True,
              group="Claude and GPT")],
        default="gemini-4-argon-low", efforts=("low", "medium", "high"), **kw)


def catalogue():
    return [claude(), codex()]


def real_catalogue(**available):
    """The catalogue MARS `model-discovery` read for real on 2026-11-11
    (C:/Work/Mentis-workspace/model-selection/discovery-real.json), trimmed to
    what selection reads: claude (default `opus`, the bare selectors and the
    legacy ids), codex (default gpt-5.6-sol, lacks drive_browser), antigravity
    (no default, effort in the id), kimi (efforts unknown), local (Ollama, one
    model reported tools-unsupported) and gemini (unavailable). `available`
    overrides a runtime's availability by id (`local=True`)."""
    import copy
    import json
    import os
    path = os.path.join(os.path.dirname(__file__), "fixtures",
                        "catalogue_real_2026-11-11.json")
    with open(path, encoding="utf-8") as f:
        got = json.load(f)
    for b in got:
        if b["id"] in available:
            b["available"] = bool(available[b["id"]])
            b["reason"] = None if b["available"] else "unavailable (test)"
    return copy.deepcopy(got)


@pytest.fixture()
def cat_real(world, monkeypatch):
    """Real posting, delegate and dispatch over `catalogue()`; every run
    answers "done". Grants are kept; `backends` may be changed by a test."""
    import mentis.web as web
    st = world["state"]
    svc = st.agents
    svc.execution._backends = catalogue()
    grants = []

    def perform(spec):
        grants.append(svc.authority.grant_for(svc.authority.grant_of(spec.run_id),
                                              st.path))
        now = time.time()
        from mentis.execution import RunResult
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done", started_at=now,
                         finished_at=now)

    svc.execution.script = {b: perform for b in ("claude", "codex", "antigravity")}
    monkeypatch.setattr(web, "dispatch_soon", lambda s, **kw: D.dispatch(st, **kw))
    return {"grants": grants, "ex": svc.execution, "perform": perform}


@pytest.fixture()
def cat_carrying(world, cat_real):
    """A real run of the steward carrying an owner's request; @Bob to hand to."""
    cv = world["cv"]
    cid = a_conversation(world)
    got = say(world, cid, "do the work", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "carry it"}])
    assert "error" not in got, got
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    return {"cid": cid, "grant": cat_real["grants"][-1], "bob": bob,
            "parent": got["expectations"][0]}


def delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def run(world, out):
    spec = out["dispatch"]
    return D.dispatch(world["state"], conversation=out["conversation"],
                      turn=spec.get("turn") or out["turn"],
                      participant=spec["participant"], work=spec["work"],
                      persona=spec.get("persona"), runtime=spec.get("runtime"),
                      model=spec.get("model"), effort=spec.get("effort"),
                      requires=spec.get("requires") or (),
                      expectation=out["expectation"])


def latest_start(cv, expectation):
    got = [a for a in cv.history(caused_by=expectation)
           if a["act"] == "execution-started"]
    assert got, "the run did not start"
    return max(got, key=lambda a: a["at"])


def reply_of(cv, expectation):
    start = latest_start(cv, expectation)["id"]
    return next(a["turn"] for a in cv.history(caused_by=start)
                if a["act"] == "result-returned")


def routing_of(cv, expectation):
    return (cv._act(expectation)["detail"] or {}).get("routing")
