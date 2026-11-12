from copy import deepcopy

import pytest

from mentis import suitability as S
from mentis.conversation import Conversations
from mentis.web import fixture
from mentis import api


@pytest.fixture
def cv(tmp_path):
    path = str(tmp_path / "brain")
    fixture.build(path)
    corpus = api.open_corpus(path)
    yield Conversations(corpus)
    corpus.close()


def body(**kw):
    return {"pattern": "new-*", "runtimes": None, "reasoning_max": "deep",
            "open": True, "basis": "measured work", "evidence": [], **kw}


def test_legacy_exact_table_and_levels(cv):
    assert {s["pattern"] for s in S.LEGACY_STANDING} == {
        "claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5",
        "claude-fable-5", "gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol"}
    for s in S.standing(cv):
        got = S.verdict([s], "any", s["pattern"], [],
                        {"level": s["reasoning_max"], "open": s["open"]})
        assert got["verdict"] == "established" and got["by"] == "legacy"
    changed = S.standing(cv)
    changed[0]["evidence"].append("changed")
    assert not S.LEGACY_STANDING[0]["evidence"]


def test_proposals_never_stand_and_establishment_resolves_proposal(cv):
    p = cv.record_act(actor="agent", act=S.PROPOSED, detail=body())
    assert S.proposals(cv)[0]["id"] == p
    assert len(S.standing(cv)) == 7
    e = cv.record_act(actor="owner", act=S.ESTABLISHED,
                      about=[p], detail={**body(), "proposal": p})
    assert not S.proposals(cv)
    assert S.standing(cv)[-1]["id"] == e
    assert len(S.history(cv)) == 2


def test_supersession_decline_and_legacy_retirement(cv):
    old = S.LEGACY_STANDING[0]["id"]
    e = cv.record_act(actor="owner", act=S.ESTABLISHED,
                      detail=body(supersedes=old))
    assert old not in {s["id"] for s in S.standing(cv)}
    cv.record_act(actor="owner", act=S.SUPERSEDED, about=[e])
    assert e not in {s["id"] for s in S.standing(cv)}
    p = cv.record_act(actor="agent", act=S.PROPOSED, detail=body())
    cv.record_act(actor="owner", act=S.DECLINED, about=[p])
    assert not S.proposals(cv)
    assert len(S.history(cv)) == 4


def test_matching_direct_pattern_alias_runtime_and_case():
    legacy = deepcopy(S.LEGACY_STANDING[-1])
    pattern = {**body(pattern="gpt-*"), "id": "pattern", "source": "owner"}
    direct = {**body(pattern="gpt-6.1-sol", runtimes=["codex"]),
              "id": "direct", "source": "owner"}
    need = {"level": "deep", "open": True}
    assert S.verdict([legacy, pattern, direct], "codex", "alias", ["gpt-6.1-sol"], need)["by"] == "direct"
    assert S.verdict([legacy, pattern, direct], "other", "gpt-6.1-sol", [], need)["by"] == "pattern"
    assert S.verdict([pattern], "codex", "GPT-X", [], need)["verdict"] == "unknown"


def test_insufficiency_is_explicit_and_owner_overrides_legacy():
    need = {"level": "deep", "open": True}
    weak = {**body(reasoning_max="light", open=False), "id": "weak"}
    assert S.verdict([weak], "r", "new-x", [], need)["verdict"] == "unknown"
    assert S.verdict([{**weak, "insufficient": True}], "r", "new-x", [], need)["verdict"] == "insufficient"
    legacy = S.LEGACY_STANDING[-1]
    negative = {**body(pattern="gpt-*", insufficient=True), "id": "no"}
    assert S.verdict([legacy, negative], "r", legacy["pattern"], [], need)["statement"] == "no"


@pytest.mark.parametrize("kw", [{"pattern": " "}, {"reasoning_max": "frontier"},
                                {"runtimes": "codex"}, {"runtimes": [1]},
                                {"open": "yes"}, {"insufficient": 1},
                                {"evidence": "x"}, {"basis": ""},
                                {"supersedes": 1}])
def test_invalid_statements(kw):
    with pytest.raises(ValueError):
        S.validate(body(**kw))


def test_evidence_must_exist(cv):
    ref = cv.record_act(actor="agent", act="outcome-claimed")
    assert S.validate(body(evidence=[ref]), cv)["evidence"] == [ref]
    with pytest.raises(ValueError, match="does not exist"):
        S.validate(body(evidence=["opr-missing"]), cv)
