"""Round 2: O4 (hand-started CLI authority) and O5 (session identity).

Against a real HTTP server (`tests.test_manual_session.world`). Requirements
already pinned by WS-I tests are named in docs/modernization/CONTRACT.md
"Round 2 — A"; these pin what was missing.
"""

from __future__ import annotations

from mentis import web
from mentis.operational import session_grants
from mentis.worker import SESSION_SCOPE, permitted
from tests.test_manual_session import _post, world  # noqa: F401
from tests.test_session_contribution import _start

OWNER = {"X-Mentis-Client": "1"}


def _owner_request(world, text="owner's work"):
    cv = world["st"].cv
    cid = cv.open_conversation("Owner's", attributed_to=world["owner"])
    cv.join(world["owner"], cid)
    turn = cv.say(cid, world["owner"], [{"type": "text", "text": text}])
    exp = cv.expect(turn, of=None, kind="result", by=world["owner"])
    return cid, exp


# -- O4 -----------------------------------------------------------------------

def test_a_session_keeps_its_legitimate_work_with_no_request(world, monkeypatch):
    """Reads, contributing attributed findings, opening a Conversation and
    recording a request hold with no request; carrying what it recorded holds."""
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    grant, op = _start(world, "claude", host="ALPHA")
    for name, args in (("orient", {}), ("recall", {"query": "anything"})):
        status, got = op(name, **args)
        assert status == 200, (name, got)
    status, got = op("contribute", kind="finding", text="the cache is stale",
                     evidence=["log line 3"])
    assert status == 200, got
    status, opened = op("open_conversation", name="Mine")
    assert status == 200
    status, req = op("record_request", conversation=opened["conversation"],
                     text="fix the cache", authorized_by="the owner asked in chat")
    assert status == 200, req
    status, summoned = op("summon_participant", alias="Helper",
                          conversation=opened["conversation"], under=req["expectation"])
    assert status == 200, summoned
    status, out = op("record_outcome", expectation=req["expectation"], result="done",
                     outcome="fixed")
    assert status == 200 and out["claim"], out


def test_no_coordination_merely_because_a_session_exists(world):
    _, op = _start(world, "claude", host="ALPHA")
    status, said = op("summon_participant", alias="Helper")
    assert status == 403 and said["refusal"]["boundary"] == "coordination"
    # and nothing a session holds grants it authority
    assert not [o for o in permitted(SESSION_SCOPE) if "grant" in o]


def test_the_owner_grants_a_session_a_request_and_revokes_it(world, monkeypatch):
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    cv, url = world["st"].cv, world["url"]
    grant, op = _start(world, "claude", host="ALPHA")
    cid, exp = _owner_request(world)
    # before the grant: not the session's to carry or close
    status, said = op("summon_participant", alias="Helper", under=exp)
    assert status == 403 and said["refusal"]["boundary"] == "ownership"
    status, said = op("record_outcome", expectation=exp, result="done", outcome="x")
    assert status == 403
    # nobody but the owner grants, and only to a CLI participant
    try:
        session_grants.grant(cv, actor=grant["participant"], participant=grant["participant"],
                             request=exp, because="me")
        raise AssertionError("granted by a non-owner")
    except ValueError:
        pass
    agent = cv.resolve_participant("@Nadia")
    status, said = _post(url + "/api/session-grants",
                         {"participant": agent, "request": exp, "because": "x"}, OWNER)
    assert status == 400
    status, said = _post(url + "/api/session-grants",
                         {"participant": grant["participant"], "request": exp}, OWNER)
    assert status == 400                                     # the owner's words are required
    # the owner's grant
    status, got = _post(url + "/api/session-grants",
                        {"participant": grant["participant"], "request": exp,
                         "because": "carry this from your terminal"}, OWNER)
    assert status == 200, got
    act = cv._act(got["act"])
    assert act["actor"] == world["owner"] and act["act"] == session_grants.GRANTED
    assert set(act["about"]) == {exp, grant["participant"]}
    status, summoned = op("summon_participant", alias="Helper", under=exp)
    assert status == 200, summoned
    # another session of the same participant carries it too; another runtime's does not
    _, op2 = _start(world, "claude", host="ALPHA")
    status, _ = op2("summon_participant", alias="Helper2", under=exp)
    assert status == 200
    _, other = _start(world, "codex", host="ALPHA")
    status, said = other("summon_participant", alias="Helper3", under=exp)
    assert status == 403
    # revoked: refused again
    status, _ = _post(url + "/api/session-grants", {"revoke": got["act"], "because": "done"}, OWNER)
    assert status == 200
    status, said = op("summon_participant", alias="Helper4", under=exp)
    assert status == 403 and said["refusal"]["boundary"] == "ownership"
    assert session_grants.standing(cv, exp) == []


def test_a_granted_request_is_closed_and_claimed_by_the_session(world):
    cv, url = world["st"].cv, world["url"]
    grant, op = _start(world, "claude", host="ALPHA")
    cid, exp = _owner_request(world)
    status, got = _post(url + "/api/session-grants",
                        {"participant": grant["participant"], "request": exp,
                         "because": "yours"}, OWNER)
    assert status == 200
    status, out = op("record_outcome", expectation=exp, result="done", outcome="did it")
    assert status == 200, out
    claim = cv._act(out["claim"])
    assert claim["actor"] == grant["participant"]
    assert claim["execution"] == grant["execution"]


def test_the_grant_route_records_what_it_observed_and_never_grants_the_caller(world):
    """Review M3: the owner route is trusted by locality, not authenticated.
    Each grant/revoke records what the server observed of the request (as
    every owner write does), a request carrying a worker grant is refused at
    the door, and a request that identifies its calling session cannot grant
    that session (route level, `presented` reaching `_routes`)."""
    from mentis.worker import CAPABILITY_HEADER
    cv, url, st = world["st"].cv, world["url"], world["st"]
    grant, op = _start(world, "claude", host="ALPHA")
    cid, exp = _owner_request(world)
    body = {"participant": grant["participant"], "request": exp, "because": "carry it"}
    # a session presenting its own grant is refused at the door (no grant recorded)
    status, said = _post(url + "/api/session-grants", body, {**OWNER,
                                                             CAPABILITY_HEADER: grant["grant"]})
    assert status == 403, said
    assert session_grants.standing(cv, exp) == []
    # ... and at the route itself, should the door ever pass it
    try:
        web._routes(st, "/api/session-grants", {}, body, "POST", grant["grant"])
        raise AssertionError("a session granted itself a request")
    except web._BadRequest as exc:
        assert "its own request" in str(exc)
    assert session_grants.standing(cv, exp) == []
    # the owner's client presents nothing: recorded as an unattributed local request
    status, got = _post(url + "/api/session-grants", body, OWNER)
    assert status == 200, got
    act = cv._act(got["act"])
    assert act["actor"] == world["owner"]
    assert act["detail"]["written_by"] == "unattributed-local-request"
    status, rev = _post(url + "/api/session-grants", {"revoke": got["act"], "because": "x"},
                        OWNER)
    assert status == 200
    assert cv._act(rev["act"])["detail"]["written_by"] == "unattributed-local-request"


# -- O5 -----------------------------------------------------------------------

def test_two_sessions_on_one_host_are_told_apart_on_every_act(world):
    cv = world["st"].cv
    a, op_a = _start(world, "claude", host="SAME")
    b, op_b = _start(world, "claude", host="SAME")
    assert a["participant"] == b["participant"] and a["execution"] != b["execution"]
    for op in (op_a, op_b):
        status, opened = op("open_conversation", name="Twin")
        assert status == 200
        status, _ = op("record_request", conversation=opened["conversation"], text="w")
        assert status == 200
        status, _ = op("contribute", kind="observation", text="seen")
        assert status == 200
    mine = [x for x in cv.corpus.operational(actor=a["participant"])]
    bad = [(x["act"], x["execution"], x["runtime"]) for x in mine
           if x["execution"] not in (a["execution"], b["execution"])]
    assert mine and not bad, bad
    assert {x["execution"] for x in mine} == {a["execution"], b["execution"]}
    assert all(x["runtime"] == "claude" for x in mine)


def test_historical_manual_session_work_is_untouched_and_still_carried(world):
    """Records of the pooled @ManualSession stay as written; a new session is
    its own participant and still continues work @ManualSession recorded."""
    from mentis.worker import SESSION_PARTICIPANT
    cv = world["st"].cv
    old = cv.resolve_participant(SESSION_PARTICIPANT)
    if not old:
        old = cv.create_participant(SESSION_PARTICIPANT, about="hand-started sessions")
    cid = cv.open_conversation("Old", attributed_to=old)
    cv.join(old, cid)
    turn = cv.say(cid, old, [{"type": "text", "text": "old work"}])
    exp = cv.expect(turn, of=old, kind="result", by=old, detail={"manual_session": True})
    before = dict(cv._act(exp))
    cv.record_act(actor=old, act="manual-session-started", execution="old-exec",
                  runtime="claude", because="historical", detail={"scope": SESSION_SCOPE})
    grant, op = _start(world, "claude", host="NEW")
    assert grant["participant"] != old and grant["alias"] != SESSION_PARTICIPANT
    status, out = op("record_outcome", expectation=exp, result="done", outcome="finished")
    assert status == 200, out
    assert cv._act(exp) == before
    assert cv._act(out["outcome_act"])["actor"] == grant["participant"]
