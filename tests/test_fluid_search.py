"""Conversation-bounded Fluid search and its visibility/paging contract."""

import pytest

from mentis.fluid import route
from mentis.fluid.read import BadRequest, PAGE_MAX
from mentis.web import _State, fixture

SEARCH = "/fluid/api/search"
COLLECTION = "/fluid/api/collections/conversation"


def _text(value):
    return [{"type": "text", "text": value}]


def _world(tmp_path):
    built = fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    owner = built["who"]["@brian"]
    first = st.cv.open_conversation("First", attributed_to=owner)
    second = st.cv.open_conversation("Second", attributed_to=owner)
    return st, owner, first, second


def test_search_reuses_conversation_visibility(tmp_path):
    st, owner, first, second = _world(tmp_path)
    home = st.cv.say(first, owner, _text("shared needle at home"))
    elsewhere = st.cv.say(second, owner, _text("shared needle included"))
    hidden = st.cv.say(second, owner, _text("shared needle hidden"))
    st.cv.link_into(elsewhere, first, by=owner)
    st.cv.link_into(hidden, first, by=owner)
    st.cv.unlink(hidden, first, by=owner)

    visible = route(st, COLLECTION, {"id": [first], "shape": ["posts"]})
    visible_ids = {item["id"] for item in visible["items"]}
    got = route(st, SEARCH, {"conversation": [first], "q": ["shared needle"]})

    assert {hit["post"] for hit in got["hits"]} == {home, elsewhere}
    assert {hit["post"] for hit in got["hits"]} <= visible_ids
    assert hidden not in visible_ids


def test_search_is_bounded_to_the_named_conversation(tmp_path):
    st, owner, first, second = _world(tmp_path)
    wanted = st.cv.say(first, owner, _text("same phrase here"))
    other = st.cv.say(second, owner, _text("same phrase elsewhere"))

    got = route(st, SEARCH, {"conversation": [first], "q": ["same phrase"]})

    assert [hit["post"] for hit in got["hits"]] == [wanted]
    assert other not in {hit["post"] for hit in got["hits"]}


def test_search_limit_and_before_page_older_hits(tmp_path):
    st, owner, first, _second = _world(tmp_path)
    made = [st.cv.say(first, owner, _text(f"paged needle {n}"))
            for n in range(5)]

    newest = route(st, SEARCH, {"conversation": [first], "q": ["needle"],
                                "limit": ["2"]})
    older = route(st, SEARCH, {"conversation": [first], "q": ["needle"],
                               "limit": ["2"],
                               "before": [newest["hits"][-1]["post"]]})

    assert [h["post"] for h in newest["hits"]] == list(reversed(made[-2:]))
    assert newest["more"] is True
    assert [h["post"] for h in older["hits"]] == list(reversed(made[1:3]))
    assert older["more"] is True
    assert all("needle" in h["snippet"] for h in newest["hits"] + older["hits"])


def test_search_bounds_large_limit(tmp_path):
    st, owner, first, _second = _world(tmp_path)
    for n in range(PAGE_MAX + 5):
        st.cv.say(first, owner, _text(f"bounded needle {n}"))

    got = route(st, SEARCH, {"conversation": [first], "q": ["needle"],
                             "limit": [str(PAGE_MAX + 1000)]})

    assert len(got["hits"]) == PAGE_MAX
    assert got["more"] is True


@pytest.mark.parametrize("query, message", [
    ({"q": ["needle"]}, "name the conversation"),
    ({"conversation": ["not-an-id"], "q": ["needle"]},
     "not a conversation"),
    ({"conversation": ["CONVERSATION"], "q": ["  "]},
     "name what to search for"),
    ({"conversation": ["CONVERSATION"], "q": ["x" * 501]},
     "search text is at most 500 characters"),
    ({"conversation": ["CONVERSATION"], "q": ["needle"], "limit": ["no"]},
     "limit is a number"),
    ({"conversation": ["CONVERSATION"], "q": ["needle"], "limit": ["0"]},
     "limit is at least 1"),
    ({"conversation": ["CONVERSATION"], "q": ["needle"],
      "before": ["bad cursor"]}, "not a paging cursor"),
])
def test_search_refuses_bad_input(tmp_path, query, message):
    st, _owner, first, _second = _world(tmp_path)
    query = {key: [first if value[0] == "CONVERSATION" else value[0]]
             for key, value in query.items()}
    with pytest.raises(BadRequest, match=message):
        route(st, SEARCH, query)
