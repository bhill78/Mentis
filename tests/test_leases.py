"""Shared-resource leases (WS-L): `mentis.operational.leases` and the three ops.

WHAT MUST HOLD:
  * a claim is recorded and released by its holder; a re-claim renews;
  * exclusive vs exclusive and exclusive vs shared conflict, shared vs shared
    coexist, a nested path conflicts with a containing exclusive claim, and
    paths compare case-insensitively on Windows with either slash;
  * unrelated resources never block, and the same holder never blocks itself;
  * an expired lease, a released one and one whose run ended never block;
  * of two threads claiming one resource, exactly one wins;
  * a refusal carries holder, purpose, since, expiry and recovery;
  * every dispatched scope and the session scope hold the ops; Quick Ask not;
  * through real dispatch: the prompt names other live work's leases inside
    the run's workspace, and the run's own leases end when it ends.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from mentis.operational import leases as L
from mentis.web import _State, _surface, fixture
from mentis.worker import (NotPermitted, READ_ONLY, RESOURCES, SESSION_SCOPE,
                           TRANSIENT_SCOPE, _operate, permitted)

WIN = os.name == "nt"
WT = "C:\\Work\\Mentis-wt\\demo" if WIN else "/work/mentis-wt/demo"


@pytest.fixture()
def st(tmp_path):
    root = tmp_path / "corpus"
    built = fixture.build(str(root))
    state = _State(str(root), str(tmp_path))
    state.who = built["who"]
    return state


def _grant(st, who="@Nadia", exe="exe-a", scope="worker"):
    return {"participant": st.who[who], "instance": exe, "runtime": "claude",
            "scope": scope, "conversation": None, "expectation": None}


def op(st, grant, op_name, **args):
    return _operate(_surface(st), op_name, args, grant)


# -- names ----------------------------------------------------------------------

@pytest.mark.skipif(not WIN, reason="Windows path rules")
def test_windows_paths_compare_case_insensitively_with_either_slash():
    a = L.normalize("worktree", "C:/Work/Mentis-wt/Demo/")
    assert a == L.normalize("path", "c:\\work\\mentis-wt\\demo")
    assert a == L.normalize("path", "/c/Work/Mentis-wt/demo")
    assert L.overlaps("worktree", a, "path", L.normalize("path", "C:/work/mentis-wt/demo/src"))
    assert not L.overlaps("worktree", a, "path", L.normalize("path", "C:/work/mentis-wt/demo2"))


def test_names_are_checked():
    for kind, name in (("path", "relative/dir"), ("port", "eighty"), ("port", 70000),
                       ("disk", "x"), ("service", "")):
        with pytest.raises(L.LeaseError):
            L.normalize(kind, name)
    assert L.normalize("port", " 8790 ") == "8790"
    assert L.normalize("service", "Test  Server") == "test server"


# -- claim and release --------------------------------------------------------------

def test_claim_release_and_renew(st):
    g = _grant(st)
    got = op(st, g, "claim_resource", kind="worktree", name=WT, purpose="build WS-L")
    assert got["ok"] and got["mode"] == "exclusive" and got["ttl_s"] == L.TTL_DEFAULT
    act = st.cv._act(got["lease"])
    assert act["act"] == L.CLAIMED and act["actor"] == g["participant"]
    assert act["execution"] == "exe-a"
    listed = op(st, g, "resources")["leases"]
    assert [x["lease"] for x in listed] == [got["lease"]] and listed[0]["yours"]
    again = op(st, g, "claim_resource", kind="worktree", name=WT, ttl_s=99999)
    assert again["renewed"] == [got["lease"]] and again["ttl_s"] == L.TTL_MAX
    assert [x["lease"] for x in op(st, g, "resources")["leases"]] == [again["lease"]]
    out = op(st, g, "release_resource", kind="worktree", name=WT)
    assert out["released"] == [again["lease"]]
    assert st.cv._act(out["act"])["act"] == L.RELEASED
    assert op(st, g, "resources")["leases"] == []
    assert op(st, g, "release_resource", kind="worktree", name=WT)["released"] == []


def test_only_the_holder_releases(st):
    mine, theirs = _grant(st), _grant(st, "@Vera", "exe-b")
    lease = op(st, mine, "claim_resource", kind="port", name=8790)["lease"]
    with pytest.raises(NotPermitted, match="not by you"):
        op(st, theirs, "release_resource", lease=lease)
    with pytest.raises(NotPermitted, match="not by you"):
        op(st, _grant(st, "@Nadia", "exe-other"), "release_resource", kind="port", name=8790)
    assert op(st, mine, "release_resource", lease=lease)["released"] == [lease]


def test_a_session_releases_its_own_earlier_session_lease(st):
    first = _grant(st, scope=SESSION_SCOPE, exe="sess-1")
    lease = op(st, first, "claim_resource", kind="service", name="test server")["lease"]
    later = _grant(st, scope=SESSION_SCOPE, exe="sess-2")
    assert op(st, later, "release_resource", kind="service", name="Test Server")["released"] == [lease]


# -- conflicts -------------------------------------------------------------------------

@pytest.mark.parametrize("first,second,conflicts", [
    ("exclusive", "exclusive", True),
    ("exclusive", "shared", True),
    ("shared", "exclusive", True),
    ("shared", "shared", False),
])
def test_modes(st, first, second, conflicts):
    a, b = _grant(st), _grant(st, "@Vera", "exe-b")
    op(st, a, "claim_resource", kind="worktree", name=WT, mode=first)
    if conflicts:
        with pytest.raises(NotPermitted) as got:
            op(st, b, "claim_resource", kind="worktree", name=WT, mode=second)
        assert got.value.refusal["boundary"] == "resource"
    else:
        assert op(st, b, "claim_resource", kind="worktree", name=WT, mode=second)["ok"]
        assert len(op(st, b, "resources")["leases"]) == 2


def test_nested_paths_conflict_both_ways(st):
    a, b = _grant(st), _grant(st, "@Vera", "exe-b")
    sub = WT + ("\\src\\mentis" if WIN else "/src/mentis")
    op(st, a, "claim_resource", kind="worktree", name=WT)
    with pytest.raises(NotPermitted):
        op(st, b, "claim_resource", kind="path", name=sub, mode="shared")
    op(st, a, "release_resource", kind="worktree", name=WT)
    op(st, b, "claim_resource", kind="path", name=sub)
    with pytest.raises(NotPermitted):
        op(st, a, "claim_resource", kind="worktree", name=WT)
    # a sibling with the same prefix is not inside it
    assert op(st, a, "claim_resource", kind="worktree", name=WT + "2")["ok"]


def test_unrelated_resources_and_the_holder_itself_never_block(st):
    a, b = _grant(st), _grant(st, "@Vera", "exe-b")
    op(st, a, "claim_resource", kind="worktree", name=WT)
    op(st, a, "claim_resource", kind="port", name=8790)
    op(st, a, "claim_resource", kind="service", name="mars")
    other = WT.replace("demo", "other")
    for kind, name in (("worktree", other), ("port", 8791), ("service", "mentis"),
                       ("service", "8790")):
        assert op(st, b, "claim_resource", kind=kind, name=name)["ok"], (kind, name)
    # the holder's own nested claim is not a conflict with itself
    inner = WT + ("\\build" if WIN else "/build")
    assert op(st, a, "claim_resource", kind="path", name=inner)["ok"]


def test_the_same_participant_in_another_execution_is_another_holder(st):
    op(st, _grant(st, exe="exe-1"), "claim_resource", kind="port", name=5190)
    with pytest.raises(NotPermitted):
        op(st, _grant(st, exe="exe-2"), "claim_resource", kind="port", name=5190)


def test_the_refusal_says_who_what_since_until_and_what_to_do(st):
    a, b = _grant(st), _grant(st, "@Vera", "exe-b")
    held = op(st, a, "claim_resource", kind="port", name=8790, purpose="dev Brain server")
    with pytest.raises(NotPermitted) as got:
        op(st, b, "claim_resource", kind="port", name="8790", purpose="mine")
    r = got.value.refusal
    assert r["op"] == "claim_resource" and r["boundary"] == "resource"
    assert r["who"] == a["participant"]  # the lease detail keeps the raw holder
    assert r["holder"] == {"participant": a["participant"], "execution": "exe-a",
                           "run": None}
    assert r["purpose"] == "dev Brain server" and r["lease"] == held["lease"]
    assert r["expires"] - r["since"] == L.TTL_DEFAULT
    assert any("wait" in x for x in r["recovery"])
    assert any("another worktree" in x for x in r["recovery"])
    text = str(got.value)
    # WS-I's structured refusal: the words say why, what to do and who; the
    # boundary rides as a field.
    for part in ("dev Brain server", a["participant"], "UTC",
                 "What you can do instead"):
        assert part in text
    assert got.value.boundary == "resource"
    # nothing was recorded for the refused claim
    assert len(op(st, b, "resources")["leases"]) == 1


# -- ending -------------------------------------------------------------------------------

def test_an_expired_lease_never_blocks(st, monkeypatch):
    a, b = _grant(st), _grant(st, "@Vera", "exe-b")
    op(st, a, "claim_resource", kind="port", name=8790, ttl_s=60)
    with pytest.raises(NotPermitted):
        op(st, b, "claim_resource", kind="port", name=8790)
    later = time.time() + 61
    monkeypatch.setattr(L, "_clock", lambda: later)
    assert op(st, b, "claim_resource", kind="port", name=8790)["ok"]
    assert [x["holder"]["execution"] for x in op(st, b, "resources")["leases"]] == ["exe-b"]


def test_a_run_s_leases_end_with_it(st):
    cv, who = st.cv, st.who["@Nadia"]
    started = cv.record_act(actor=who, act=L.STARTED, execution="exe-a",
                            runtime="claude")
    lease = op(st, _grant(st), "claim_resource", kind="worktree", name=WT)["lease"]
    assert cv._act(lease)["detail"]["run"] == started
    assert L.end_run(cv, started) == [lease]
    ended = cv._c.operational(act=L.RELEASED)[-1]
    assert ended["about"] == [lease] and ended["detail"]["reason"] == "run-ended"
    assert op(st, _grant(st, "@Vera", "exe-b"), "claim_resource", kind="worktree", name=WT)["ok"]
    assert L.end_run(cv, started) == []          # idempotent: nothing more written


def test_a_lease_whose_run_ended_without_the_hook_does_not_block(st):
    cv, who = st.cv, st.who["@Nadia"]
    started = cv.record_act(actor=who, act=L.STARTED, execution="exe-a", runtime="claude")
    op(st, _grant(st), "claim_resource", kind="port", name=8790)
    # the server stopped: the run was recovered, the hook never ran
    from mentis.conversation import RESULT_RECOVERED
    cv.record_act(actor=who, act=RESULT_RECOVERED, execution="exe-a", caused_by=started)
    assert op(st, _grant(st, "@Vera", "exe-b"), "claim_resource", kind="port", name=8790)["ok"]


# -- concurrency ---------------------------------------------------------------------------

def test_two_threads_claiming_one_resource_exactly_one_wins(st):
    grants = [_grant(st, "@Nadia", "exe-a"), _grant(st, "@Vera", "exe-b"),
              _grant(st, "@Ada", "exe-c"), _grant(st, "@Mira", "exe-d")]
    barrier = threading.Barrier(len(grants))
    won, lost = [], []

    def claim(g):
        barrier.wait()
        try:
            won.append(op(st, g, "claim_resource", kind="worktree", name=WT))
        except NotPermitted as exc:
            lost.append(exc)

    threads = [threading.Thread(target=claim, args=(g,)) for g in grants]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert len(won) == 1 and len(lost) == len(grants) - 1
    assert len(st.cv._c.operational(act=L.CLAIMED)) == 1


# -- scopes and tools --------------------------------------------------------------------------

def test_every_dispatched_scope_and_the_session_hold_the_ops():
    for scope, ops in (("worker", None), ("organising", ()), ("organising", None),
                       ("intake", None), (SESSION_SCOPE, None), ("unrecognised", None)):
        assert set(RESOURCES) <= set(permitted(scope, ops)), scope
    assert not set(RESOURCES) & set(permitted(TRANSIENT_SCOPE))
    assert "resources" in READ_ONLY
    assert "claim_resource" not in READ_ONLY and "release_resource" not in READ_ONLY


def test_the_tools_tell_agents_to_claim_before_exclusive_use():
    from mentis.worker import ACT_TOOLS
    tools = {t["name"]: t for t in ACT_TOOLS}
    assert set(RESOURCES) <= set(tools)
    words = tools["claim_resource"]["description"]
    for part in ("worktree", "port", "test server", "refused", "holder"):
        assert part in words
    assert tools["claim_resource"]["inputSchema"]["required"] == ["kind", "name"]


def test_a_bad_argument_is_a_refusal_not_a_crash(st):
    with pytest.raises(NotPermitted, match="absolute path"):
        op(st, _grant(st), "claim_resource", kind="worktree", name="relative")
    with pytest.raises(NotPermitted, match="mode"):
        op(st, _grant(st), "claim_resource", kind="port", name=1, mode="mine")


# -- the prompt ---------------------------------------------------------------------------------

def test_prompt_lines_name_other_live_work_inside_the_workspace_only(st):
    cv = st.cv
    inner = WT + ("\\src" if WIN else "/src")
    L.claim(cv, participant=st.who["@Vera"], execution="exe-b", kind="path",
            name=inner, purpose="running the focused tests")
    L.claim(cv, participant=st.who["@Ada"], execution="exe-c", kind="port", name=8790)
    L.claim(cv, participant=st.who["@Mira"], execution="exe-d", kind="worktree",
            name=WT.replace("demo", "elsewhere"))
    mine = L.claim(cv, participant=st.who["@Nadia"], execution="exe-a",
                   kind="path", name=WT + ("\\docs" if WIN else "/docs"))
    text = L.prompt_lines(cv, workspace=WT, execution="exe-a")
    assert "Shared resources" in text and "running the focused tests" in text
    assert "claim_resource" in text
    assert "8790" not in text and "elsewhere" not in text
    assert mine["name"] not in text
    assert L.prompt_lines(cv, workspace=WT.replace("demo", "quiet"), execution="x") == ""
    assert L.prompt_lines(cv, workspace=None, execution="x") == ""


def test_the_projection_reads_only_what_changed(st):
    cv = st.cv
    proj = L._projection(cv)
    L.live(cv)
    before = proj.cursor
    L.claim(cv, participant=st.who["@Vera"], execution="exe-b", kind="port", name=1)
    L.live(cv)
    assert proj.cursor > before
    seen = []
    real = proj.store._rows
    proj.store._rows = lambda sql, args=(): seen.append(args) or real(sql, args)
    try:
        L.live(cv)
    finally:
        proj.store._rows = real
    assert seen and seen[-1][0] == proj.cursor


# -- through real dispatch ------------------------------------------------------------------------

from tests._loop import _coordinator, a_conversation, grant_of_run, world  # noqa: E402,F401
from tests._loop import script_every_backend  # noqa: E402


def test_dispatch_tells_the_run_and_ends_its_leases(world):
    """The prompt names another live holder's lease inside the run's workspace (the run is not
    refused), the run claims a port while it runs, and its end releases that lease."""
    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from tests.test_delegate_coordinate import _present
    state, cv = world["state"], world["cv"]
    svc = state.agents
    other = L.claim(cv, participant=world["who"]["@Vera"], execution="elsewhere",
                    kind="path", name=os.path.join(state.workspace, "build"),
                    purpose="a long build somebody else runs")
    seen = {}

    def perform(spec):
        grant = grant_of_run(svc, spec, state.path)
        seen["prompt"] = spec.prompt
        seen["lease"] = _operate(_surface(state), "claim_resource",
                                 {"kind": "port", "name": 8799, "purpose": "test server"},
                                 grant)["lease"]
        seen["held"] = [x["lease"] for x in L.live(cv)]
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done", started_at=now,
                         finished_at=now)

    script_every_backend(svc, perform)
    cid = a_conversation(world)
    _coach, _parent, grant = _coordinator(world, cid)
    builder = _present(world, cid, "@Builder")
    b = _operate(_surface(state), "delegate",
                 {"participant": builder, "work": "build it"}, grant)
    out = D.dispatch(state, conversation=b["conversation"], turn=b["turn"],
                     participant=builder, work=b["dispatch"]["work"],
                     expectation=b["expectation"])
    assert out["ok"], out
    assert "Shared resources" in seen["prompt"]
    assert "a long build somebody else runs" in seen["prompt"]
    assert seen["lease"] in seen["held"]
    held = [x["lease"] for x in L.live(cv)]
    assert seen["lease"] not in held and other["lease"] in held
    ended = [a for a in cv._c.operational(act=L.RELEASED)
             if seen["lease"] in a["about"]]
    assert len(ended) == 1 and ended[0]["detail"]["reason"] == "run-ended"
