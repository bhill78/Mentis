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


def request(server):
    cv = server["st"].cv
    return cv.record_act(actor=server["who"]["@brian"], act="expectation-recorded",
                         detail={"expects": "result"})


def test_owner_result_verdict_is_append_only_and_readable(server):
    port, cv, auth = server["port"], server["st"].cv, owner(server)
    exp = request(server)
    result = cv.record_act(actor="agent", act="result-returned", caused_by=exp)
    path = f"/api/requests/{exp}/verdict"
    assert call(port, "GET", path, headers=auth)["json"]["verdict"] is None
    for value in ("accepted", "rejected"):
        got = call(port, "POST", path, {"verdict": value, "why": "inspected", "result": result}, auth)
        assert got["status"] == 200, got
        a = cv._act(got["json"]["act"])
        assert a["actor"] == server["who"]["@brian"]
        assert a["about"] == [exp] and a["detail"]["result"] == result
    view = call(port, "GET", path, headers=auth)["json"]
    assert view["verdict"]["detail"]["verdict"] == "rejected"
    assert len(view["history"]) == 2


@pytest.mark.parametrize("payload", [
    {"verdict": "pass", "why": "x"}, {"verdict": "accepted", "why": ""},
    {"verdict": "accepted", "why": "x", "result": "opr-missing"}])
def test_result_verdict_validates_payload(server, payload):
    auth, exp = owner(server), request(server)
    got = call(server["port"], "POST", f"/api/requests/{exp}/verdict", payload, auth)
    assert got["status"] == 400
    assert not server["st"].cv.history(act="result-verdict")


def test_result_verdict_refuses_an_unrelated_result(server):
    auth, exp, other = owner(server), request(server), request(server)
    r = server["st"].cv.record_act(actor="agent", act="result-returned", caused_by=other)
    got = call(server["port"], "POST", f"/api/requests/{exp}/verdict",
               {"verdict": "accepted", "why": "x", "result": r}, auth)
    assert got["status"] == 400


def test_owner_evidence_report_counts_recorded_request_facts(server):
    port, cv, auth = server["port"], server["st"].cv, owner(server)
    exp = request(server)
    s = cv.record_act(actor="agent", act="execution-started", runtime="codex",
                      execution="report-run", caused_by=exp,
                      detail={"effective_model": "future-model"})
    cv.record_act(actor="agent", act="result-returned", execution="report-run",
                  caused_by=s, detail={"terminal": "reported_done"})
    path = f"/api/evidence/models?expectation={exp}"
    got = call(port, "GET", path, headers=auth)
    assert got["status"] == 200, got
    assert got["json"]["attempts"] == 1
    assert got["json"]["models"][0]["model"] == "future-model"
    assert got["json"]["models"][0]["levels"]["none"] == 1
    assert call(port, "POST", f"/api/requests/{exp}/verdict",
                {"verdict": "rejected", "why": "wrong result"}, auth)["status"] == 200
    got = call(port, "GET", path, headers=auth)["json"]["models"][0]
    assert got["levels"]["owner_rejected"] == 1
    assert got["failures"]["substantive"] == 1
