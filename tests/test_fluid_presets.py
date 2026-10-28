from mentis.fluid import arrangements as A


def zones(node):
    if node["type"] == "zone":
        return [node]
    return [zone for kid in node["kids"] for zone in zones(kid)]


def sources(layout):
    found = []
    for zone in zones(layout["tree"]):
        feed = zone.get("slot", {}).get("feed")
        if feed:
            found.append(feed["source"])
    for page in layout.get("pages", []):
        found.extend(sources({"tree": page["tree"]}))
    for item in layout.get("focus", {}).get("floats", []):
        feed = item["zone"].get("slot", {}).get("feed")
        if feed:
            found.append(feed["source"])
    return found


def test_presets_keep_ids_defaults_and_validate():
    presets = A.presets()
    assert [preset["id"] for preset in presets] == [
        "preset-triage", "preset-focus", "preset-oversight", "preset-showcase"
    ]
    assert A.PRESET_IDS == tuple(preset["id"] for preset in presets)
    assert A.NEW_DEFAULTS == {
        "home": "preset-triage",
        "conversation": "preset-focus",
        "unnamed": "preset-focus",
    }
    for preset in presets:
        assert A.check(preset["home"]) == preset["home"]
        assert A.check(preset["conversation"]) == preset["conversation"]


def test_presets_have_distinct_section_registry_purposes():
    by_id = {preset["id"]: preset for preset in A.presets()}
    assert by_id["preset-focus"]["name"] == "Focus layout"
    assert set(sources(by_id["preset-triage"]["conversation"])) >= {
        "actions", "followups"
    }
    assert "contents" in sources(by_id["preset-focus"]["conversation"])
    assert set(sources(by_id["preset-oversight"]["conversation"])) >= {
        "contents", "activity", "needs-you"
    }
    assert [page["title"] for page in by_id["preset-oversight"]["conversation"]["pages"]] == ["Files"]
    assert "contents" in sources(by_id["preset-showcase"]["conversation"])
    assert [page["title"] for page in by_id["preset-showcase"]["conversation"]["pages"]] == ["Media"]


def test_preset_section_floats_use_room_fractions():
    floats = [
        item
        for preset in A.presets()
        for item in preset["conversation"].get("focus", {}).get("floats", [])
    ]
    assert floats
    assert all(0 <= item[axis] <= 1 for item in floats for axis in ("x", "y"))
    assert all(0 < item[axis] <= 1 for item in floats for axis in ("w", "h"))
