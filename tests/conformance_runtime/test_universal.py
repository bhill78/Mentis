"""The universal Mentis requirements (program §11), per runtime. A runtime that fails one of
these is not conformant: it lost work, bypassed authority or misreported completion."""

from __future__ import annotations

import pytest

from tests.conformance_runtime import scenarios as S


def _assert(checks, groups=("universal",)):
    bad = [c for c in checks if c.group in groups and c.status != S.PASSED]
    assert not bad, "\n".join(f"{c.name}: {c.status}: {c.evidence}" for c in bad)


def test_assigned_work_tools_contribution_leases_refusals_and_claim(rig):
    _assert(S.main(rig))


def test_a_malformed_outcome_block_is_never_a_claim(rig):
    """Owner decision 9: unterminated, invalid-result and not-last blocks are unclaimed,
    with why, the reply kept as written. Offline every profile reproduces each case."""
    checks = S.malformed_outcome(rig)
    _assert(checks)
    if not rig.live:
        assert [c.status for c in checks] == [S.PASSED] * len(S.MALFORMED_REPLIES)


def test_authorized_delegation(rig):
    _assert(S.delegation(rig))


def test_failure_is_failed_never_completed(rig):
    _assert(S.failure(rig))


def test_cancellation_is_cancelled_never_completed(rig):
    _assert(S.cancellation(rig))


def test_continuity_carries_the_prior_context(rig):
    _assert(S.continuity(rig))


def test_consent_narrowing_halts_a_run_holding_compiled_rules(rig):
    """Group (c): what Builder A's consent code does to a live run when the owner narrows,
    observed per runtime."""
    _assert(S.consent_narrowing(rig), groups=("enforcement",))
