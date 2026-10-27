"""Focused contracts for Fluid's canonical commands and paged lists."""

from mentis.fluid import route
from mentis.fluid import commands
from mentis.conversation.register import governed
from mentis.web import _State, fixture


def _state(tmp_path):
    root = tmp_path / "brain"
    built = fixture.build(str(root))
    return _State(str(root)), built["who"]["@brian"]


def test_conversation_commands_return_canonical_projections(tmp_path):
    st, owner = _state(tmp_path)
    status, opened, _ = commands.open_conversation(
        st, {"author": owner, "op": "test-open"}, written_by=lambda: "test")
    assert status == 201
    assert opened["projection"] == commands._conversation_projection(
        st, opened["conversation"])
    assert opened["projection"]["created"] > 0
    assert opened["projection"]["participants"] == 1

    post = st.corpus.entries_of_kind("contribution")[0]["id"]
    status, changed, _ = commands.members(
        st, opened["conversation"],
        {"author": owner, "add": [post], "op": "test-member"},
        written_by=lambda: "test")
    assert status == 200
    assert changed["projection"]["included"] == 1
    projected = next(p for p in changed["posts"] if p["id"] == post)
    assert any(m["conversation"] == opened["conversation"]
               and m["via"] == "linked" for m in projected["memberships"])


def test_conversation_pages_have_cursor_limit_topics_and_search(tmp_path):
    st, owner = _state(tmp_path)
    made = []
    for n in range(7):
        made.append(st.cv.open_conversation(
            f"Paged needle {n}", attributed_to=owner))
    first = route(st, "/fluid/api/conversations",
                  {"activity": ["1"], "limit": ["3"],
                   "q": ["paged needle"]})
    assert len(first["conversations"]) <= 3
    assert first["next"]
    assert all("topics" in row for row in first["conversations"])
    second = route(st, "/fluid/api/conversations",
                   {"activity": ["1"], "limit": ["3"],
                    "cursor": [first["next"]], "q": ["paged needle"]})
    assert {r["id"] for r in first["conversations"]}.isdisjoint(
        {r["id"] for r in second["conversations"]})
    assert {r["id"] for r in first["conversations"] + second["conversations"]} <= set(made)


def test_governed_cursor_pages_without_changing_the_legacy_shape(tmp_path):
    st, owner = _state(tmp_path)
    for n in range(6):
        st.corpus.create_and_establish(
            kind="rule", body={"text": f"paging rule {n}"},
            attributed_to=owner)
    legacy = governed(st.brain, q="paging rule", limit=2)
    assert "next_cursor" not in legacy
    assert all(len(rows) <= 2 for rows in legacy["groups"].values())

    seen = []
    cursor = "start"
    while cursor:
        page = governed(st.brain, q="paging rule", limit=2, cursor=cursor)
        seen.extend(r["entry"] for rows in page["groups"].values() for r in rows)
        cursor = page["next_cursor"]
    assert len(seen) == 6
    assert len(seen) == len(set(seen))

