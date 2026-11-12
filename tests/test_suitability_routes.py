"""Suitability and result evidence use the existing owner and worker doors."""
import pytest

from mentis import suitability as S
from mentis.worker import CAPABILITY_HEADER, permitted, TRANSIENT_SCOPE
from tests.test_owner_auth import server, call  # noqa: F401
from tests.test_suitability import body


def agent(server, scope="worker"):
    st = server["st"]
    who = st.cv.create_participant("@SuitabilityAgent", about="test agent")
    st.agents.authority.authorise_for("suitability-run", {
        "scope": scope, "participant": who, "runtime": "codex"})
    token = st.agents.authority._grant("suitability-run", st.path)
    return {CAPABILITY_HEADER: token}, who


def op(server, headers, name="propose_suitability", **args):
    return call(server["port"], "POST", "/api/worker", {
        "corpus": server["st"].path, "op": name, "args": args}, headers)


def test_proposal_uses_agent_identity_and_cannot_establish(server):
    headers, who = agent(server)
    got = op(server, headers, **body(proposed_by="owner", establish=True))
    assert got["status"] == 200, got
    assert got["json"]["stands"] is False
    cv = server["st"].cv
    assert S.proposals(cv)[0]["proposed_by"] == who
    assert len(S.standing(cv)) == 7
    assert cv._act(got["json"]["act"])["execution"] == "suitability-run"
    assert op(server, headers, "establish_suitability", **body())["status"] == 403


def test_proposal_evidence_checked_before_writing(server):
    headers, _ = agent(server)
    got = op(server, headers, **body(evidence=["opr-no-such"]))
    assert got["status"] == 403
    assert not S.proposals(server["st"].cv)


@pytest.mark.parametrize("scope", ["worker", "organising", "intake", "manual-session", "unknown"])
def test_proposal_authority_is_ordinary_agent_authority(scope):
    assert "propose_suitability" in permitted(scope)
    assert "establish_suitability" not in permitted(scope)
    assert "result_verdict" not in permitted(scope)
    assert "propose_suitability" not in permitted(TRANSIENT_SCOPE)
