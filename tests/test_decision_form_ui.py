"""Fluid's direct path from a run permission to its exact decision form."""

from pathlib import Path


ROOT = Path(__file__).parents[1] / "apps" / "fluid-web" / "src"


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_every_waiting_permission_has_its_own_answer_action():
    panel = source("fluid/runs/RunPanel.tsx")
    assert "permissions.map((perm)" in panel
    assert "key={perm.form}" in panel
    assert "perm.post!, perm.decision" in panel


def test_answer_invalidates_then_targets_the_exact_decision():
    panel = source("fluid/runs/RunPanel.tsx")
    decisions = source("experimental/decisions.ts")
    nav = source("fluid/nav.ts")
    post = source("fluid/conversation/Decisions.tsx")

    assert panel.index("invalidateDecisions(perm.post!)") < panel.index(
        "onOpenPost(perm.conversation!, perm.post!, perm.decision)")
    assert "export function invalidateDecisions(post: string)" in decisions
    assert "decision?: string | null" in nav and "decision: options?.decision ?? null" in nav
    assert "focus={decision}" in post


def test_targeting_one_form_keeps_the_other_forms_drawn():
    forms = source("experimental/types/decision.tsx")
    assert "groups.sort" in forms and "x.id === focus" in forms
    assert "groups.map((g)" in forms
    assert "groupsOf(read, only)" in forms
