"""The simplified development governance sheet (docs/governance/simplify-2026-11-25.json)
is accepted by a real server: applied to a fixture Brain holding stand-ins for every
predecessor it names, each successor stands, every predecessor (the three consolidated
rules included) is ended, and the redelivered rule becomes conditional."""
from __future__ import annotations

import json
import pathlib

from tests.test_establish_governance import tool
from tests.test_manual_session import world  # noqa: F401

SHEET = pathlib.Path(__file__).resolve().parents[1] / "docs" / "governance" / "simplify-2026-11-25.json"


def test_the_simplify_sheet_applies_cleanly(world, tmp_path):
    st, owner = world["st"], world["owner"]
    cv, corpus = st.cv, st.corpus
    sheet = json.loads(SHEET.read_text(encoding="utf-8"))
    ids = {}

    def stand_in(old, kind, body):
        if old not in ids:
            e = corpus.create_and_establish(kind=kind, body=body, attributed_to=owner)
            try:
                cv.place(e, whole_brain=True, by=owner, because="fixture predecessor")
            except ValueError:      # a Kind placed only by reference
                cv.place(e, whole_brain=True, by=owner, because="fixture predecessor",
                         delivery="reference")
            ids[old] = e
        return ids[old]

    persona_ids = {}
    for it in sheet["items"]:
        if it.get("kind") == "persona":
            persona_ids[it["replaces"]] = stand_in(
                it["replaces"], "persona", {"name": it["body"]["name"], "about": "",
                                            "behaviour": "old words"})
        elif it.get("kind"):
            stand_in(it["replaces"], it["kind"], {"name": it["body"]["name"],
                                                   "text": "old words"})
    items = []
    for it in json.loads(json.dumps(sheet["items"])):
        kind = it.get("kind") or "rule"
        if kind == "rule":
            stand_in(it["replaces"], "rule", {"text": "old " + it["key"]})
            it["also_replaces"] = [stand_in(o, "rule", {"text": "old " + o})
                                   for o in it.get("also_replaces") or ()]
        elif kind != "persona":
            body = {"name": it["body"]["name"], "text": "old words"}
            stand_in(it["replaces"], kind, body)
        it["replaces"] = ids[it["replaces"]]
        if kind == "workflow":       # its Persona references, to the fixture's stand-ins
            text = json.dumps(it["body"])
            for real, fake in persona_ids.items():
                text = text.replace(real, fake)
            it["body"] = json.loads(text)
        if kind in ("workflow",) or it["key"] == "discipline":
            text = json.dumps(it["body"])
            for real, fake in ids.items():
                text = text.replace(real, fake)
            it["body"] = json.loads(text)
        items.append(it)
    redeliver = [{**r, "entry": stand_in(r["entry"], "rule", {"text": "close rounds"})}
                 for r in sheet["redeliver"]]
    path = tmp_path / "sheet.json"
    path.write_text(json.dumps({"items": items, "redeliver": redeliver}), encoding="utf-8")
    assert tool.main(["--server", world["url"], "--decisions", str(path), "--apply",
                      "--attributed-to", owner]) == 0
    for old in ids.values():
        if old == redeliver[0]["entry"]:
            assert corpus.stands(old)["stands"]
            continue
        got = corpus.stands(old)
        assert not got["stands"] and got["superseded_by"], (old, got)
        assert corpus.stands(got["superseded_by"][0])["stands"]
    got = cv.placement_delivery(redeliver[0]["entry"], cv.whole_brain())
    assert got["delivery"] == "conditional"
