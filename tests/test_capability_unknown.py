"""Unknown is not unsupported (#1268, owner 2026-10-29).

MARS reports, per backend, what is known: `capabilities` (measured or declared)
and `lacks` (with what showed it). Everything else is unknown. Selection keeps
work off a runtime known to lack a requirement, or one nobody has established
a non-triable requirement for; among the rest it prefers what is confirmed --
after capacity and review independence -- and says when it chose without
confirmation. The run is told too. Requirements nothing can declare stay
refused.
"""

from __future__ import annotations

import time

import pytest

from mentis.api.errors import RuntimeNotPresent, Unsupported
from mentis.core.service import MentisService
from mentis.execution import FakeExecution

UI = ["build_ui", "drive_browser"]


def _b(rid, caps=(), lacks=None, mcp=("stdio",)):
    return {"id": rid, "kind": "acp", "available": True, "reason": None,
            "models": [], "efforts": [], "supports": {"mcp": list(mcp)},
            "capabilities": list(caps), "lacks": dict(lacks or {})}


# As MARS measured on 2026-10-29 (MARS registry.MEASURED).
MEASURED = [
    _b("claude", caps=UI),
    _b("codex", lacks={"drive_browser": "its sandbox denied Playwright (EACCES)"}),
    _b("gemini", caps=["build_ui"]),
    _b("kimi-k3"),
]


def _svc(tmp_path, backends):
    return MentisService(str(tmp_path / "i"), execution=FakeExecution(backends))


def _hold(rid):
    now = time.time()
    return {rid: {"until": now + 600, "why": f"{rid}: rate_limited",
                  "model": None, "since": now - 60, "basis": "act-1"}}


def test_three_verdicts(tmp_path):
    svc = _svc(tmp_path, MEASURED)
    v = lambda rid, n: svc.eligibility(rid, [n])[n]["verdict"]     # noqa: E731
    assert v("claude", "drive_browser") == "supported"
    assert v("codex", "drive_browser") == "unsupported"
    assert "EACCES" in svc.eligibility("codex", ["drive_browser"])[
        "drive_browser"]["evidence"]
    assert v("gemini", "drive_browser") == "unknown"
    assert v("kimi-k3", "build_ui") == "unknown"
    # a name nothing can declare is not unknown: nothing can have it
    assert v("claude", "teleportation") == "unsupported"
    # the MCP transport list answers call_mentis_tools both ways
    svc2 = _svc(tmp_path, [_b("a"), _b("b", mcp=("http",))])
    assert svc2.eligibility("a", ["call_mentis_tools"])[
        "call_mentis_tools"]["verdict"] == "supported"
    assert svc2.eligibility("b", ["call_mentis_tools"])[
        "call_mentis_tools"]["verdict"] == "unsupported"


def test_confirmed_runtimes_are_preferred_and_the_lacking_excluded(tmp_path):
    svc = _svc(tmp_path, MEASURED)
    sel = svc.execution_select(requires=UI)
    assert sel.runtime == "claude"
    because = " · ".join(sel.because)
    assert "cannot be given this work: codex (drive_browser)" in because
    assert "confirmed on ['claude'], preferred over" in because
    assert "unconfirmed" not in sel.inputs


def test_nothing_confirmed_is_not_a_refusal_and_says_so(tmp_path):
    """#1268: every runtime reported both capabilities unknown, and every
    browser review was refused before anything ran."""
    svc = _svc(tmp_path, [_b("claude"), _b("codex"), _b("gemini")])
    sel = svc.execution_select(requires=UI)
    assert sel.runtime in ("claude", "codex", "gemini")
    assert "unconfirmed_capabilities" in sel.dimensions_used
    assert sel.inputs["unconfirmed"][sel.runtime] == sorted(UI)
    assert any("NOT established" in d for d in sel.inputs["disclosed"])


def test_the_confirmed_runtime_out_of_quota_does_not_refuse_the_work(tmp_path):
    """Found by independent review: preferring the confirmed runtime before
    the capacity gate refused browser work whenever claude was held."""
    svc = _svc(tmp_path, MEASURED)
    sel = svc.execution_select(requires=UI, holds=_hold("claude"))
    assert sel.runtime in ("gemini", "kimi-k3")
    assert "claude" in sel.excluded
    assert sel.inputs["unconfirmed"][sel.runtime]


def test_review_independence_comes_before_confirmation(tmp_path):
    """The two #1268 requests: builders on claude, a browser review. The
    review goes to a different runtime not known to lack anything, and the
    record says the capability is not established there -- not a self-review
    presented as unavoidable."""
    svc = _svc(tmp_path, MEASURED)
    sel = svc.execution_select(requires=UI, avoid="claude")
    assert sel.runtime in ("gemini", "kimi-k3")
    because = " · ".join(sel.because)
    assert "avoided so the review runs on a different runtime" in because
    assert "NOT established" in because
    # with no other runtime possible, the author's own is used and said so
    only = _svc(tmp_path, [_b("claude", caps=UI),
                           _b("codex", lacks={"drive_browser": "x"})])
    sel = only.execution_select(requires=UI, avoid="claude")
    assert sel.runtime == "claude"


def test_known_to_lack_everywhere_is_still_refused_with_the_evidence(tmp_path):
    svc = _svc(tmp_path, [
        _b("codex", lacks={"drive_browser": "sandbox denied Playwright"}),
        _b("other", lacks={"drive_browser": "no browser on this host"})])
    with pytest.raises(Unsupported) as got:
        svc.execution_select(requires=["drive_browser"])
    assert "sandbox denied Playwright" in str(got.value)
    assert "no browser on this host" in str(got.value)


def test_an_unknown_outside_the_triable_set_still_excludes(tmp_path):
    """Only build_ui and drive_browser may be tried unestablished: work kept
    on local compute must not reach a hosted runtime because nothing said."""
    svc = _svc(tmp_path, MEASURED)
    with pytest.raises(Unsupported, match="reach_local_models"):
        svc.execution_select(requires=["reach_local_models"])
    local = _svc(tmp_path, [_b("claude"), _b("local", caps=["reach_local_models"])])
    assert local.execution_select(requires=["reach_local_models"]).runtime == "local"


def test_a_named_runtime_is_refused_only_for_what_blocks_it(tmp_path):
    svc = _svc(tmp_path, MEASURED)
    with pytest.raises(Unsupported, match="cannot be given this work.*EACCES"):
        svc.execution_select(runtime="codex", requires=UI)
    sel = svc.execution_select(runtime="kimi-k3", requires=UI)
    assert sel.runtime == "kimi-k3"
    assert sel.inputs["unconfirmed"] == {"kimi-k3": sorted(UI)}
    assert "NOT established" in " · ".join(sel.because)
    sel = svc.execution_select(runtime="claude", requires=UI)
    assert "unconfirmed" not in sel.inputs


def test_a_declared_default_yields_only_to_a_confirmed_runtime_with_quota(tmp_path):
    svc = _svc(tmp_path, MEASURED)
    assert "cannot be given work requiring ['drive_browser']" in \
        svc.execution_usable("codex", UI)
    assert svc.execution_usable("claude", UI) is None
    # unknown here, confirmed and available on claude: the preference yields
    assert "['claude'] are confirmed" in svc.execution_usable("kimi-k3", UI)
    # claude held for quota is no alternative: the default binds
    assert svc.execution_usable("kimi-k3", UI, holds=_hold("claude")) is None
    # nothing confirmed anywhere: it binds
    none = _svc(tmp_path, [_b("kimi-k3"), _b("gemini")])
    assert none.execution_usable("kimi-k3", UI) is None


def test_the_runtimes_listing_shows_what_mars_knows(tmp_path):
    from mentis.api.types import Capability
    got = {r.kind: r for r in _svc(tmp_path, MEASURED).runtimes_discover()}
    assert got["claude"].supports(Capability.DRIVE_BROWSER)
    assert not got["codex"].supports(Capability.DRIVE_BROWSER)
    assert any("lacks drive_browser: its sandbox denied" in n
               for n in got["codex"].notes)
    assert not got["kimi-k3"].supports(Capability.BUILD_UI)


def test_an_older_mars_without_the_fields_is_all_unknown(tmp_path):
    old = [{"id": "claude", "kind": "acp", "available": True, "reason": None,
            "models": [], "efforts": [], "supports": {"mcp": ["stdio"]}}]
    sel = _svc(tmp_path, old).execution_select(requires=UI)
    assert sel.runtime == "claude"
    assert "unconfirmed_capabilities" in sel.dimensions_used


@pytest.fixture()
def told(world):
    from mentis.execution import RunResult
    from tests._loop import script_every_backend
    prompts = []

    def perform(spec):
        prompts.append((spec.backend, spec.prompt))
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done",
                         started_at=now, finished_at=now)
    script_every_backend(world["state"].agents, perform)
    return prompts


from tests._loop import a_conversation, say, world  # noqa: E402,F401


def test_a_dispatched_run_chosen_without_confirmation_is_told(world, told):
    from mentis.web import dispatch as D
    cid = a_conversation(world)
    out = say(world, cid, "check the page in a browser",
              action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "check it",
                         "requires": UI}])
    assert "error" not in out, out
    exp = out["expectations"][0]
    spec = next(s for s in world["sent"] if s.get("expectation") == exp)
    D.dispatch(world["state"], **spec)
    assert told, "nothing ran"
    backend, prompt = told[-1]
    assert "whether this runtime" in prompt and "has not been established" in prompt
    started = [a for a in world["cv"].history(caused_by=exp)
               if a["act"] == "execution-started"][-1]
    assert "NOT established" in started["detail"]["selection_because"]
