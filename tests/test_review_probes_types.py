"""Reviewer's probes for unsupported input shapes the builder's suite omits."""
from __future__ import annotations

import pytest

from tests._loop import a_conversation, say, world, _written  # noqa: F401


@pytest.mark.parametrize("settings", [
    {"consent": ["all"]},
    {"consent": True},
    {"consent": 1},
    {"consent": {"mode": "all", "workspaces": "C:\\"}},
    {"consent": {"mode": None}},
    {"follow_up": ["unrestricted"]},
    {"follow_up": True},
    {"follow_up": "unlimited"},
    {"follow_up": {"depth": 1.5}},
    {"consent": "all", "coordinate": False, "surprise": 1},
])
def test_unsupported_shapes_refuse_and_write_nothing(world, settings):
    cid = a_conversation(world)
    before = _written(world)
    out = say(world, cid, "carry this", action="ask-mentis", ask_mentis=settings)
    assert "error" in out, out
    assert _written(world) == before and not world["sent"]


def test_non_string_workspace_entries_are_dropped_on_both_paths(world):
    """Characterises the shared validator: a malformed entry is skipped, and
    `mode: all` survives. Pre-existing (`consent._workspaces`), identical on
    the named-request path, and listed as deferred in proposal ent-84bcc33c26bb.
    """
    cv = world["cv"]
    cid = a_conversation(world)
    from mentis.operational import consent as C

    intake = say(world, cid, "carry this", action="ask-mentis", ask_mentis={
        "consent": {"mode": "all", "workspaces": [None, 7, "  "]}})
    assert "error" not in intake, intake
    assert cv._act(intake["expectation"])["detail"]["consent"] == {
        "mode": "all", "workspaces": [], "categories": list(C.DEFAULT_CATEGORIES)}

    named = say(world, cid, "do this", dispatch=[{
        "participant": world["steward"], "work": "do this",
        "consent": {"mode": "all", "workspaces": [None, 7, "  "]}}])
    assert "error" not in named, named
    exp = named["expectations"][0]
    assert cv._act(exp)["detail"]["consent"] == {
        "mode": "all", "workspaces": [], "categories": list(C.DEFAULT_CATEGORIES)}


def test_explicit_json_null_is_absent_not_an_empty_selection(world):
    cid = a_conversation(world)
    out = say(world, cid, "carry this", action="ask-mentis", ask_mentis=None)
    assert "error" not in out and out["assigned"]
    detail = world["cv"]._act(out["expectation"])["detail"] or {}
    assert not ({"consent", "coordinate", "follow_up"} & set(detail))
    assert world["cv"].authority_of(out["expectation"])["operations"]


def test_no_declared_owner_refuses_selections_but_not_plain_intake(world, monkeypatch):
    cid = a_conversation(world)
    import mentis.conversation.owner as owner_mod
    monkeypatch.setattr(owner_mod, "_owner", lambda cv: None)
    before = _written(world)
    refused = say(world, cid, "carry this", action="ask-mentis",
                  ask_mentis={"coordinate": False})
    assert "only the owner" in refused["error"]
    assert _written(world) == before and not world["sent"]
    plain = say(world, cid, "carry this", action="ask-mentis")
    assert "error" not in plain and plain["assigned"]
