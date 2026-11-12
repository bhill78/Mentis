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


def owner(server):
    server["cred"].set_passphrase("suitability owner fixture passphrase")
    token, _ = server["cred"].issue(kind="bearer")
    return {"Authorization": f"Bearer {token}"}


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


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/suitability"), ("POST", "/api/suitability"),
    ("POST", "/api/suitability/opr-x/establish"),
    ("POST", "/api/suitability/opr-x/decline"),
    ("POST", "/api/suitability/opr-x/supersede"),
    ("GET", "/api/evidence/models"),
    ("GET", "/api/requests/opr-x/verdict"),
    ("POST", "/api/requests/opr-x/verdict")])
def test_owner_routes_refuse_anonymous_and_agent_grants(server, method, path):
    port = server["port"]
    assert call(port, method, path, body() if method == "POST" else None)["status"] == 401
    headers, _ = agent(server)
    assert call(port, method, path, body() if method == "POST" else None, headers)["status"] == 403


def test_owner_establish_decline_supersede_and_history(server):
    port, cv = server["port"], server["st"].cv
    auth = owner(server)
    agent_headers, who = agent(server)
    p = op(server, agent_headers, **body())["json"]["act"]
    got = call(port, "POST", f"/api/suitability/{p}/establish", {}, auth)
    assert got["status"] == 200, got
    e = got["json"]["act"]
    assert cv._act(e)["actor"] == server["who"]["@brian"]
    assert S.standing(cv)[-1]["proposed_by"] == who
    assert not S.proposals(cv)
    assert call(port, "POST", f"/api/suitability/{p}/establish", {}, auth)["status"] == 400
    old = S.LEGACY_STANDING[0]["id"]
    got = call(port, "POST", "/api/suitability", body(supersedes=old), auth)
    assert got["status"] == 200, got
    assert old not in {s["id"] for s in S.standing(cv)}
    assert call(port, "POST", f"/api/suitability/{e}/supersede", {"why": "new evidence"}, auth)["status"] == 200
    p2 = op(server, agent_headers, **body())["json"]["act"]
    assert call(port, "POST", f"/api/suitability/{p2}/decline", {"why": "not established"}, auth)["status"] == 200
    view = call(port, "GET", "/api/suitability", headers=auth)["json"]
    assert not view["proposals"]
    assert len(view["history"]) == 6
    assert call(port, "GET", "/api/suitability", headers=auth, client=False)["status"] == 403


def test_owner_statement_validation_is_atomic(server):
    port, cv, auth = server["port"], server["st"].cv, owner(server)
    for b in (body(evidence=["opr-missing"]), body(supersedes="opr-missing"), body(open="yes")):
        assert call(port, "POST", "/api/suitability", b, auth)["status"] == 400
    assert not S.history(cv)
