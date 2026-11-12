"""Local catalogue listing, truthful picker fields, and exact-id ACP dispatch."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

from mentis.api.errors import Unsupported
from mentis.api.types import Capability
from mentis.core.service import MentisService
from mentis.execution import FakeExecution
from mentis.execution.mars import MarsExecution
from mentis.web import _routes, _State, fixture
from tests._catalogue_world import backend, cat_real, model  # noqa: F401
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_models_capacity import CLAUDE, AGY


def local(*rows, complete=True, why=None):
    b = backend("local", list(rows))
    b["models"] = []  # The real local catalogue is additive, not the legacy list.
    b["modelCatalogue"].update(complete=complete, why=why, source="ollama /api/tags")
    return b


def service(tmp_path, b):
    return MentisService(str(tmp_path / "instances"), execution=FakeExecution([b]))


def test_catalogue_only_lists_exact_ids_aliases_and_known_metadata(tmp_path):
    row = model("hf.co/x/y:Q4_K_M", None, aliases=["as-reported"], locality="local")
    row.update(contextWindow=32768, displayName="Reported name", presence="installed")
    svc = service(tmp_path, local(row))
    [m] = svc.models_list("local")
    assert (m.slug, m.display_name, m.efforts, m.context_window, m.locality) == (
        "hf.co/x/y:Q4_K_M", "Reported name", (), 32768, "local")
    assert m.details["aliases"] == ["as-reported"]
    assert m.details["catalogue"] == "ollama /api/tags"
    [rt] = svc.runtimes_discover()
    assert rt.supports(Capability.LIST_MODELS) and rt.supports(Capability.REQUEST_MODEL)


def test_merges_by_exact_id_and_does_not_turn_aliases_into_rows(tmp_path):
    b = local(model("qwen2.5:0.5b", ["low"], aliases=["qwen"], locality="local"),
              model("hf.co/x/y:Q4_K_M", None))
    b["models"] = ["qwen2.5:0.5b", {"id": "legacy-only", "name": "Old"}]
    rows = service(tmp_path, b).models_list("local")
    assert [m.slug for m in rows] == ["qwen2.5:0.5b", "legacy-only", "hf.co/x/y:Q4_K_M"]
    assert rows[0].efforts == ("low",)
    assert rows[1].display_name == "Old"
    assert rows[1].efforts == rows[2].efforts == ()


def test_partial_catalogue_keeps_models_and_empty_catalogue_uses_mars_why(tmp_path):
    svc = service(tmp_path, local(model("qwen2.5:0.5b", None), complete=False,
                                  why="LM Studio connection refused"))
    assert svc.models_list("local")[0].slug == "qwen2.5:0.5b"
    svc = service(tmp_path / "empty", local(complete=False, why="both sources unread"))
    with pytest.raises(Unsupported, match="both sources unread"):
        svc.models_list("local")
    [rt] = svc.runtimes_discover()
    assert not rt.supports(Capability.LIST_MODELS)
    assert not rt.supports(Capability.REQUEST_MODEL)


def test_empty_catalogue_still_accepts_legacy_models(tmp_path):
    b = local(complete=False, why="new discovery unavailable")
    b["models"] = ["legacy"]
    svc = service(tmp_path, b)
    assert svc.models_list("local")[0].slug == "legacy"
    assert svc.runtimes_discover()[0].supports(Capability.LIST_MODELS)


def payload(tmp_path, backends):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    st.agents.execution = FakeExecution(backends)
    return _routes(st, "/api/execution", {}, None, "GET")["runtimes"]


@pytest.mark.parametrize("presence,state", [("loaded", "loaded"), ("installed", "installed"),
    ("unavailable", "unavailable"), ("loading", "unknown"), (None, "unknown")])
def test_execution_row_reports_presence_status_tools_and_partial_why(tmp_path, presence, state):
    m = model("qwen2.5:0.5b", None, locality="local", status="refused")
    m.update(presence=presence, contextWindow=32768)
    m["capabilities"]["tools"] = "unsupported"
    [rt] = payload(tmp_path, [local(m, complete=False, why="LM Studio unread")])
    assert rt["models_partial_why"] == "LM Studio unread"
    assert rt["models"] == [{"slug": "qwen2.5:0.5b", "name": "qwen2.5:0.5b",
        "efforts": [], "default_effort": None, "context_window": 32768, "locality": "local",
        "provider": None, "aliases": [], "catalogue": "ollama /api/tags",
        "state": state, "status": "refused", "status_why": "MARS saw set_model fail",
        "tools": "unsupported"}]


@pytest.mark.parametrize("tools,expected", [("supported", "supported"), (None, "unknown"),
                                           ("invented", "unknown")])
def test_tools_only_reports_known_values(tmp_path, tools, expected):
    m = model("local:model", None)
    m["capabilities"] = {"tools": tools}
    [rt] = payload(tmp_path, [local(m)])
    assert rt["models"][0]["tools"] == expected
    assert rt["models_partial_why"] is None


def test_hosted_legacy_rows_keep_all_prior_fields_with_additive_metadata(tmp_path):
    backends = [copy.deepcopy(CLAUDE), copy.deepcopy(AGY),
                {**copy.deepcopy(CLAUDE), "id": "codex"}]
    before = payload(tmp_path / "before", backends)
    for b in backends:
        b["modelCatalogue"] = {"complete": True, "why": None, "source": "new source",
            "models": [dict(model(mid, None), presence="unknown") for mid in b["models"]]}
    after = payload(tmp_path / "after", backends)
    for old, new in zip(before, after):
        assert {k: v for k, v in old.items() if k != "models"} == {k: v for k, v in new.items() if k != "models"}
        for om, nm in zip(old["models"], new["models"]):
            assert {k: v for k, v in om.items() if k not in ("state", "status", "status_why", "tools")} == {
                k: v for k, v in nm.items() if k not in ("state", "status", "status_why", "tools")}
    for rt in after:
        assert rt["models_partial_why"] is None
        for m in rt["models"]:
            assert m["state"] == m["tools"] == "unknown"
            assert m["status"] == "listed"


@pytest.mark.parametrize("mid,tools", [("qwen2.5:0.5b", "supported"),
                                       ("hf.co/x/y:Q4_K_M", "unsupported")])
def test_named_local_model_reaches_acp_options_unchanged(world, cat_real, tmp_path, mid, tools):
    row = model(mid, None, locality="local")
    row["capabilities"]["tools"] = tools
    svc = world["state"].agents
    svc.execution._backends = [local(row)]
    # Verify selection's owner disclosure, then dispatch via the real record/grant path.
    sel = svc.execution_select(runtime="local", model=mid)
    assert (sel.runtime, sel.model) == ("local", mid)
    if tools == "unsupported":
        assert any("cannot use tools" in d for d in sel.inputs["disclosed"])
    log = tmp_path / "wire.jsonl"
    stand_in = Path(__file__).with_name("fakes") / "mars_continuity_stand_in.py"
    wire = MarsExecution([sys.executable, str(stand_in), str(log), "old"])
    specs = []
    def perform(spec):
        specs.append(spec)
        return wire.perform(spec)
    svc.execution.script = {"local": perform}
    try:
        cid = a_conversation(world)
        got = say(world, cid, "reply OK", action="ask-participant", dispatch=[{
            "participant": world["steward"], "work": "reply OK", "runtime": "local", "model": mid}])
        assert "error" not in got, got
        assert len(specs) == 1
        assert specs[0].backend == "local" and specs[0].options["model"] == mid
        told = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        [opened] = [e for e in told if e["event"] == "new"]
        assert opened["meta"]["mars/backend"] == "local"
        assert opened["meta"]["mars/options"]["model"] == mid
    finally:
        wire.close()
