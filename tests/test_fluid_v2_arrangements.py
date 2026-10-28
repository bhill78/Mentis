import pytest
from mentis.fluid import arrangements as A


def zone(zid, *, item=None, feed=None):
    z = {"type": "zone", "id": zid, "show": "objects"}
    slot = {"follow": True, "show": "objects", "items": [], "present": "cards"}
    if item is not None:
        slot["items"] = [item] if isinstance(item, str) else list(item)
    if feed is not None:
        slot["follow"] = False
        slot["feed"] = feed
    z["slot"] = slot
    return z


def layout(version=2, tree=None, focus=None, pages=None):
    l = {"format": A.FORMAT, "version": version, "tree": tree or zone("stage")}
    if focus is not None:
        l["focus"] = focus
    if pages is not None:
        l["pages"] = pages
    return l


def test_v1_round_trips_unchanged():
    raw_v1 = {
        "format": A.FORMAT,
        "version": 1,
        "tree": {
            "type": "split",
            "dir": "row",
            "sizes": [0.5, 0.5],
            "kids": [
                {"type": "zone", "id": "z1", "show": "objects", "slot": {
                    "follow": True, "show": "objects", "items": ["live:p1:k1"], "present": "cards"
                }},
                {"type": "zone", "id": "z2", "show": "objects", "slot": {
                    "follow": False, "show": "objects", "items": ["needs-you:req-1"], "present": "focus"
                }},
            ],
        },
    }
    checked = A.check(raw_v1)
    assert checked["version"] == 1
    assert checked == raw_v1


def test_v2_round_trips_with_feed_brain_ref_and_minimized():
    raw_v2 = layout(
        version=2,
        tree={
            "type": "split",
            "dir": "row",
            "sizes": [0.5, 0.5],
            "kids": [
                zone("z1", item="brain:ent-123456789abc"),
                zone("z2", feed={"source": "actions", "options": {"tab": "in-flight", "filter": "mine"}}),
            ],
        },
        focus={
            "primary": "stage-side",
            "column": zone("stage-side"),
            "minimized": {
                "from": "float",
                "rect": {"x": 100, "y": 80, "w": 400, "h": 300},
                "near": {"near": "z1", "side": "right", "share": 0.5},
                "at": 1700000000000,
            },
        },
        pages=[
            {
                "id": "p1",
                "title": "Page 1",
                "tree": zone("pz1", item="brain:adm-abcdef012345"),
                "focus": {
                    "minimized": {
                        "from": "column",
                        "at": 1700000001000,
                    },
                },
            }
        ],
    )
    checked = A.check(raw_v2)
    assert checked["version"] == 2
    assert checked == raw_v2


def test_set_aside_round_trips_and_named_shapes_do_not_copy_it():
    raw = layout(
        tree=zone("stage"),
        pages=[{"id": "p1", "title": "Page 1", "tree": zone("page-stage"),
                "setAside": [zone("page-aside", item="live:p1:kept")]}],
    )
    raw["setAside"] = [zone("aside", item="live:p2:kept")]
    checked = A.check(raw)
    assert checked == raw
    shaped = A.shape_of(checked)
    assert "setAside" not in shaped
    assert "setAside" not in shaped["pages"][0]


def test_fractional_section_float_geometry_is_valid():
    raw = layout(focus={"floats": [{
        "id": "float-one", "zone": zone("floating-section"),
        "x": 0.62, "y": 0.08, "w": 0.34, "h": 0.42,
    }]})
    assert A.check(raw) == raw


def test_unknown_version_is_refused():
    for bad_version in (0, 3, -1, None, "2", 1.5):
        with pytest.raises(A.Refused, match="arrangement version .* is not 1 or 2"):
            A.check(layout(version=bad_version))


def test_bad_feed_is_refused():
    # Feed not a dict
    with pytest.raises(A.Refused, match=r"slot\.feed: source and options only"):
        A.check(layout(tree=zone("z1", feed="actions")))

    # Feed with invalid keys
    with pytest.raises(A.Refused, match=r"slot\.feed: source and options only"):
        A.check(layout(tree=zone("z1", feed={"source": "actions", "extra": 1})))

    # Missing or invalid source
    with pytest.raises(A.Refused, match=r"feed\.source"):
        A.check(layout(tree=zone("z1", feed={"source": "NOT_VALID_UPPERCASE"})))
    with pytest.raises(A.Refused, match=r"feed\.source"):
        A.check(layout(tree=zone("z1", feed={"options": {}})))

    # Bad options (non-scalar or too many)
    with pytest.raises(A.Refused, match=r"feed.*options"):
        A.check(layout(tree=zone("z1", feed={"source": "actions", "options": "not-a-dict"})))
    with pytest.raises(A.Refused, match=r"feed.*options"):
        A.check(layout(tree=zone("z1", feed={"source": "actions", "options": {"nested": {"a": 1}}})))

    # Feed with follow: True
    bad_follow = zone("z1")
    bad_follow["slot"]["feed"] = {"source": "actions"}
    bad_follow["slot"]["follow"] = True
    with pytest.raises(A.Refused, match=r"slot\.follow: false when a feed is present"):
        A.check(layout(tree=bad_follow))

    # Feed with pin
    bad_pin = zone("z1", feed={"source": "actions"})
    bad_pin["slot"]["pin"] = "post-123"
    with pytest.raises(A.Refused, match=r"slot\.pin: only a zone that follows is held on a post"):
        A.check(layout(tree=bad_pin))


def test_bad_minimized_is_refused():
    # Not a dict
    with pytest.raises(A.Refused, match=r"focus\.minimized: from, rect, near and at only"):
        A.check(layout(focus={"minimized": "bad"}))

    # Extra keys
    with pytest.raises(A.Refused, match=r"focus\.minimized: from, rect, near and at only"):
        A.check(layout(focus={"minimized": {"from": "column", "at": 1000, "bogus": True}}))

    # Bad 'from'
    with pytest.raises(A.Refused, match=r"minimized\.from: column, leaf or float"):
        A.check(layout(focus={"minimized": {"from": "window", "at": 1000}}))

    # Bad 'at'
    with pytest.raises(A.Refused, match=r"minimized\.at"):
        A.check(layout(focus={"minimized": {"from": "leaf", "at": "not-a-number"}}))

    # Bad rect
    with pytest.raises(A.Refused, match=r"minimized\.rect"):
        A.check(layout(focus={"minimized": {"from": "float", "at": 1000, "rect": {"x": 0, "y": 0, "w": 0, "h": 100}}}))  # w < 1
    with pytest.raises(A.Refused, match=r"minimized\.rect"):
        A.check(layout(focus={"minimized": {"from": "float", "at": 1000, "rect": {"x": 0, "y": 0, "w": 100}}}))  # missing h

    # Bad near
    with pytest.raises(A.Refused, match=r"near\.side"):
        A.check(layout(focus={"minimized": {"from": "leaf", "at": 1000, "near": {"near": "stage", "side": "middle"}}}))


def test_brain_references_saved_and_shaped():
    # Valid brain refs
    for ref in ("brain:ent-123", "brain:adm-abcdef012345", "brain:opr-999", "brain:turn-abc.1"):
        raw = layout(tree=zone("z1", item=ref))
        checked = A.check(raw)
        assert checked["tree"]["slot"]["items"] == [ref]

    # Invalid brain ref
    with pytest.raises(A.Refused):
        A.check(layout(tree=zone("z1", item="brain:")))
    with pytest.raises(A.Refused):
        A.check(layout(tree=zone("z1", item="brain:has spaces")))

    # shape_of empties kept items including brain refs
    raw = layout(
        tree=zone("z1", item="brain:ent-123"),
        pages=[
            {"id": "p1", "title": "Custom Page", "tree": zone("pz1", item="brain:adm-123456")},
            {"id": "p2", "title": "Object Page", "object": "brain:ent-999", "tree": zone("pz2")},
        ],
    )
    shaped = A.shape_of(A.check(raw))
    assert shaped["tree"]["slot"]["items"] == []
    # Object page is dropped, custom page is emptied
    assert [p["id"] for p in shaped["pages"]] == ["p1"]
    assert shaped["pages"][0]["tree"]["slot"]["items"] == []
