import pytest

from mentis.fluid import arrangements as A


def zone(zid, *, item=None):
    z = {"type": "zone", "id": zid, "show": "objects"}
    if item:
        z["slot"] = {"follow": False, "show": "objects", "items": [item], "present": "focus"}
    return z


def layout(focus):
    return {"format": A.FORMAT, "version": A.VERSION, "tree": zone("stage"), "focus": focus}


def test_focus_is_checked_and_round_trips():
    raw = layout({
        "primary": "card",
        "column": {**zone("card"), "slot": {"follow": True, "show": "objects", "items": [], "present": "cards"}},
        "floats": [{"id": "f1", "zone": zone("aside"), "x": -20, "y": 4, "w": 320, "h": 220,
                    "origin": {"near": "stage", "side": "right", "share": .7}}],
        "previous": ["conv", "stage"],
    })
    assert A.check(raw) == raw


def test_focus_rejects_collisions_limits_and_missing_primary():
    with pytest.raises(A.Refused, match="share the id"):
        A.check(layout({"floats": [{"id": "f1", "zone": zone("stage"), "x": 0, "y": 0, "w": 1, "h": 1}]}))
    with pytest.raises(A.Refused, match="at most 12"):
        A.check(layout({"floats": [{"id": f"f{i}", "zone": zone(f"z{i}"), "x": 0, "y": 0, "w": 1, "h": 1} for i in range(13)]}))
    with pytest.raises(A.Refused, match="content"):
        A.check(layout({"primary": "missing"}))
    with pytest.raises(A.Refused, match="at most 20"):
        A.check(layout({"previous": ["conv"] * 21}))


def test_named_shape_keeps_workspace_floats_only_and_empties_them():
    raw = layout({
        "primary": "workspace-float",
        "floats": [
            {"id": "f1", "zone": {**zone("workspace-float"), "slot": {"follow": True, "pin": "abc", "show": "objects", "items": ["live:p:k"], "present": "cards"}}, "x": 1, "y": 2, "w": 300, "h": 200},
            {"id": "f2", "zone": {**zone("object-float", item="live:p:k"), "show": "object"}, "x": 3, "y": 4, "w": 220, "h": 120},
        ],
    })
    shaped = A.shape_of(A.check(raw))
    assert [f["id"] for f in shaped["focus"]["floats"]] == ["f1"]
    assert shaped["focus"]["floats"][0]["zone"]["slot"]["items"] == []
    assert "pin" not in shaped["focus"]["floats"][0]["zone"]["slot"]
    assert shaped["focus"]["primary"] == "workspace-float"


def test_page_focus_is_checked_against_its_own_tree_and_round_trips():
    raw = layout(None)
    raw.pop("focus")
    raw["pages"] = [
        {"id": "research", "title": "Research", "tree": zone("page-one"),
         "focus": {
             "primary": "page-float",
             "column": zone("page-column"),
             "floats": [{"id": "pf1", "zone": zone("page-float"),
                         "x": 10, "y": 20, "w": 300, "h": 200}],
             "previous": ["conv", "page-one"],
         }},
        {"id": "notes", "title": "Notes", "tree": zone("page-two"),
         "focus": {"primary": "page-two"}},
    ]
    assert A.check(raw) == raw

    wrong_page = {**raw, "pages": [{**raw["pages"][0],
                                      "focus": {"primary": "page-two"}},
                                     raw["pages"][1]]}
    with pytest.raises(A.Refused, match=r"pages\[0\]\.focus\.primary:.*content"):
        A.check(wrong_page)


@pytest.mark.parametrize("focus, path", [
    ({"floats": [{"id": "page-one", "zone": zone("new"),
                   "x": 0, "y": 0, "w": 1, "h": 1}]},
     r"pages\[0\]\.focus\.floats\[0\]"),
    ({"column": {"type": "split", "dir": "row", "sizes": [.5, .5],
                  "kids": [zone("a"), zone("b")] }},
     r"pages\[0\]\.focus\.column"),
    ({"previous": ["conv"] * 21}, r"pages\[0\]\.focus\.previous"),
])
def test_page_focus_refusals_name_the_page_path(focus, path):
    raw = layout(None)
    raw.pop("focus")
    raw["pages"] = [{"id": "research", "title": "Research",
                     "tree": zone("page-one"), "focus": focus}]
    with pytest.raises(A.Refused, match=path):
        A.check(raw)


def test_named_shape_shapes_each_kept_pages_focus_and_drops_object_pages():
    raw = layout(None)
    raw.pop("focus")
    raw["pages"] = [
        {"id": "research", "title": "Research",
         "tree": zone("page-tree", item="live:p:tree"),
         "focus": {
             "primary": "section-float",
             "column": zone("page-column", item="live:p:column"),
             "floats": [
                 {"id": "pf1", "zone": zone("section-float", item="live:p:section"),
                  "x": 1, "y": 2, "w": 300, "h": 200},
                 {"id": "pf2", "zone": {**zone("object-float", item="live:p:object"),
                                           "show": "object"},
                  "x": 3, "y": 4, "w": 220, "h": 120},
             ],
         }},
        {"id": "object-page", "title": "One object", "object": "live:p:object",
         "tree": zone("object-page-tree")},
    ]
    shaped = A.shape_of(A.check(raw))
    assert [p["id"] for p in shaped["pages"]] == ["research"]
    page = shaped["pages"][0]
    assert page["tree"]["slot"]["items"] == []
    assert page["focus"]["column"]["slot"]["items"] == []
    assert [f["id"] for f in page["focus"]["floats"]] == ["pf1"]
    assert page["focus"]["floats"][0]["zone"]["slot"]["items"] == []
    assert page["focus"]["primary"] == "section-float"
