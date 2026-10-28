"""The conversation-wide Fluid object index, including reply objects."""

from mentis.fluid import objects, route
from mentis.web import _State, fixture


def test_conversation_objects_include_replies_and_page_by_root(tmp_path,
                                                               monkeypatch):
    built = fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    owner = built["who"]["@brian"]
    conversation = st.cv.open_conversation("Object index", attributed_to=owner)
    first = st.cv.say(conversation, owner,
                      [{"type": "text", "text": "opening"}])
    reply = st.cv.say(conversation, owner,
                      [{"type": "text", "text": "reply"}],
                      replies_to=first)
    second = st.cv.say(conversation, owner,
                       [{"type": "text", "text": "another root"}])

    def listings(_corpus, ids, **_kwargs):
        return [{
            "post": post, "number": {first: 1, reply: 2, second: 3}[post],
            "home": conversation, "objects": [{
                "key": "object", "part": 0, "kind": "block",
                "type": "chart", "title": f"Chart {post}", "parent": None,
                "address": {"live": f"live:{post}:object",
                            "exact": f"exact:{post}:0:object"},
                "is": {"chip": "chart"},
            }],
        } for post in ids]

    monkeypatch.setattr(objects, "_many", listings)
    got = route(st, "/fluid/api/objects", {
        "conversation": [conversation], "limit": ["1"]})

    # The newest root is its own first page.  Paging once reaches the older
    # root and includes the reply below it in the same page.
    assert [o["post"] for o in got["objects"]] == [second]
    older = route(st, "/fluid/api/objects", {
        "conversation": [conversation], "limit": ["1"],
        "before": [got["before"]]})
    assert [o["post"] for o in older["objects"]] == [first, reply]
    assert older["objects"][1]["reply_to_number"] == 1
    assert older["objects"][1]["address"] == f"live:{reply}:object"
    assert older["objects"][1]["exact"] == f"exact:{reply}:0:object"
    assert older["objects"][1]["preview"]["type"] == "chart"
