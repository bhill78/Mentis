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


def test_authorized_delegation(rig):
    _assert(S.delegation(rig))


def test_failure_is_failed_never_completed(rig):
    _assert(S.failure(rig))


def test_cancellation_is_cancelled_never_completed(rig):
    _assert(S.cancellation(rig))


def test_continuity_carries_the_prior_context(rig):
    _assert(S.continuity(rig))
