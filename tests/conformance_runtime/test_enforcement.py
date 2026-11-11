"""Runtime-specific enforcement (program §11-12, group c), as Builder A's permission code
stands. These tests CONSUME that code (`mentis.web.permissions`); they do not change it.

What each runtime's permission/sandbox enforcement is, is MARS's to declare in the capability
contract (`permission_enforcement.kind`). What Mentis compiles into a runtime's own rules
must agree with that declaration: Mentis never hands a runtime rules it cannot enforce, and a
runtime whose enforcement is `none` is listed as such, never assumed safe.
"""

from __future__ import annotations

from mentis.core import runtime_contract as RC
from tests.conformance_runtime.profiles import PROFILES

CONSENT = {"mode": "task", "workspaces": [], "categories": ["test", "build", "run"],
           "tools": [], "source": "request", "granted_at": None}


def _kind(rid):
    return (RC.of_backend(PROFILES[rid]["backend"])["capabilities"]
            ["permission_enforcement"].get("kind"))


def test_compiled_rules_go_only_to_a_runtime_that_enforces_its_own_rules(tmp_path):
    from mentis.web import permissions as P
    for rid in PROFILES:
        rules = P.runtime_rules(CONSENT, workspace=str(tmp_path), runtime=rid)
        if rules is not None:
            assert "runtime-rules" in (_kind(rid) or ""), (
                f"{rid} is given compiled rules but MARS declares its enforcement "
                f"as {_kind(rid)!r}")
    assert P.runtime_rules(CONSENT, workspace=str(tmp_path), runtime="claude") is not None


def test_a_pre_turn_runtime_is_told_its_rules_up_front_and_others_are_not():
    """Antigravity cannot ask mid-run: what consent allows is told before the turn
    (`runtime_options`), and nothing is told to a runtime that asks (forwarded)."""
    assert _kind("antigravity") == "pre-turn"
    for rid in PROFILES:
        if _kind(rid) in ("forwarded", "forwarded+runtime-rules", "sandbox+client"):
            assert rid != "antigravity"


def test_runtimes_whose_enforcement_is_none_are_named():
    """`local` in full access neither asks nor is confined (MARS: enforced_by none): the
    owner's consent cannot be enforced there. Listed, so it is never assumed."""
    none = sorted(rid for rid in PROFILES if _kind(rid) == "none")
    assert none == ["local"]
