"""Unknown is not unsupported (#1268, owner 2026-10-29).

MARS reports, per backend, what is known: `capabilities` (measured or declared)
and `lacks` (with what showed it). Everything else is unknown. Selection
excludes only what is known to be missing, prefers what is confirmed, and says
when it chose without confirmation; a named runtime is refused only for what it
is known to lack. Requirements nothing can declare stay refused.
"""

from __future__ import annotations

import pytest

from mentis.api.errors import Unsupported
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
    _b("codex", caps=["build_ui"],
       lacks={"drive_browser": "its sandbox denied Playwright (EACCES)"}),
    _b("gemini", caps=["build_ui"]),
    _b("kimi-k3"),
]


def _svc(tmp_path, backends):
    return MentisService(str(tmp_path / "i"), execution=FakeExecution(backends))


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
    assert "codex (drive_browser)" in because        # known to lack, said
    assert "confirmed on ['claude']" in because


def test_nothing_confirmed_is_not_a_refusal_and_says_so(tmp_path):
    """#1268: every runtime reported both capabilities unknown, and every
    browser review was refused before anything ran."""
    svc = _svc(tmp_path, [_b("claude"), _b("codex"), _b("gemini")])
    sel = svc.execution_select(requires=UI)
    assert sel.runtime in ("claude", "codex", "gemini")
    assert "unconfirmed_capabilities" in sel.dimensions_used
    assert sel.inputs["unconfirmed"][sel.runtime] == sorted(UI)
    assert any("NOT established" in d for d in sel.inputs["disclosed"])


def test_known_to_lack_everywhere_is_still_refused_with_the_evidence(tmp_path):
    svc = _svc(tmp_path, [
        _b("codex", lacks={"drive_browser": "sandbox denied Playwright"}),
        _b("other", lacks={"drive_browser": "no browser on this host"})])
    with pytest.raises(Unsupported) as got:
        svc.execution_select(requires=["drive_browser"])
    assert "sandbox denied Playwright" in str(got.value)
    assert "no browser on this host" in str(got.value)


def test_a_named_runtime_is_refused_only_for_what_it_lacks(tmp_path):
    svc = _svc(tmp_path, MEASURED)
    with pytest.raises(Unsupported, match="known to lack.*EACCES"):
        svc.execution_select(runtime="codex", requires=UI)
    sel = svc.execution_select(runtime="kimi-k3", requires=UI)
    assert sel.runtime == "kimi-k3"
    assert sel.inputs["unconfirmed"] == {"kimi-k3": sorted(UI)}
    assert "NOT established" in " · ".join(sel.because)
    sel = svc.execution_select(runtime="claude", requires=UI)
    assert "unconfirmed" not in sel.inputs


def test_review_avoidance_keeps_to_confirmed_runtimes_and_says_so(tmp_path):
    """The two #1268 requests: builders on claude, a browser review. Only
    claude is confirmed for both; it is not swapped for a runtime nobody has
    established can do the review, and the lost independence is said."""
    svc = _svc(tmp_path, MEASURED)
    sel = svc.execution_select(requires=UI, avoid="claude")
    assert sel.runtime == "claude"
    assert "independence by runtime was not achievable" in " · ".join(sel.because)


def test_a_declared_default_yields_to_confirmed_and_binds_when_none_is(tmp_path):
    svc = _svc(tmp_path, MEASURED)
    assert "known to lack ['drive_browser']" in svc.execution_usable("codex", UI)
    assert svc.execution_usable("claude", UI) is None
    # unknown here, confirmed on claude: the preference yields
    assert "['claude'] are confirmed" in svc.execution_usable("kimi-k3", UI)
    # nothing confirmed anywhere: it binds
    none = _svc(tmp_path, [_b("kimi-k3"), _b("gemini")])
    assert none.execution_usable("kimi-k3", UI) is None


def test_an_older_mars_without_the_fields_is_all_unknown(tmp_path):
    old = [{"id": "claude", "kind": "acp", "available": True, "reason": None,
            "models": [], "efforts": [], "supports": {"mcp": ["stdio"]}}]
    sel = _svc(tmp_path, old).execution_select(requires=UI)
    assert sel.runtime == "claude"
    assert "unconfirmed_capabilities" in sel.dimensions_used
