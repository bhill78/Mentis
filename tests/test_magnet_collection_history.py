"""Historical evidence is the original retained batch, never a live reconstruction."""
import copy
import hashlib
import json
import pathlib
import zipfile

import pytest

from mentis.magnet import activation as X, collection as C, schema
from mentis.fluid import read as fluid
from tests.test_magnet_activation import (
    MAGNET, World, artifact_of, define_from, ask_commit, ask_preflight, asked_body,
    built, world, record_size, send, JSON_HEADERS,
)

LEGACY = pathlib.Path(__file__).parent / "fixtures/magnet-conformance/legacy"


def test_authentic_prechange_brain_through_actual_collection_http(tmp_path):
    root = tmp_path / "legacy"
    with zipfile.ZipFile(LEGACY / "brain-12fecc01.zip") as archive:
        archive.extractall(root)
    receipt = json.loads((LEGACY / "receipt.json").read_text())
    assert receipt["baseline"] == "12fecc0172eaca0745fd0eeda3dba9a43d54df54"
    w = World(root)
    before = record_size(w)
    try:
        response = send(w.alone, f"/fluid/api/magnets/{MAGNET}/collection", JSON_HEADERS, b"", method="GET")
        assert response["status"] == 200, response
        got = json.loads(response["body"])
        assert got["activation"]["artifact"] == receipt["commit"]["body"]["artifact"]
        sources = got["page"]["sources"]
        assert len(sources) == 3
        assert [s["source"]["kind"] for s in sources] == ["conversation", "conversation", "file"]
        assert sources[-1]["source"] == {"kind": "file", "collection": "col-legacy"}
        assert sources[-1]["status"] == "unavailable" and sources[-1]["results"] == []
        assert all(s["key"] == schema.source_key(s["source"]) for s in sources)
        artifact = got["activation"]["artifact"]
        assert C.read(w.state, MAGNET, batch=artifact["ref"], digest=artifact["digest"]) == got
        assert C.history(w.state, MAGNET)["batches"] == [got["activation"]]
        assert ask_preflight(w, asked_body(w, op="new-collect"))["body"]["reason"]["message"] == X.FILE_CHOICE
        assert record_size(w) == before
    finally:
        w.stop()
        w.corpus.close()


def commit(w, op):
    raw = artifact_of(w, op=op)
    define_from(w, raw)
    return ask_commit(w, raw)["body"]


def test_history_snapshot_pagination_and_explicit_old_batch(world):
    first, second, third = [commit(world, str(i)) for i in range(3)]
    page = C.history(world.state, MAGNET, limit=1)
    assert page["batches"][0]["post"] == third["post"]
    commit(world, "appended-later")
    next_page = C.history(world.state, MAGNET, limit=1, cursor=page["next"])
    assert next_page["batches"][0]["post"] == second["post"]
    last = C.history(world.state, MAGNET, limit=1, cursor=next_page["next"])
    assert last["batches"][0]["post"] == first["post"] and last["next"] is None
    artifact = first["artifact"]
    assert C.read(world.state, MAGNET, batch=artifact["ref"], digest=artifact["digest"])["activation"]["post"] == first["post"]
    with pytest.raises(C.UnreadableCollection):
        C.read(world.state, MAGNET, batch=artifact["ref"], digest="0" * 64)
    with pytest.raises(fluid.NotFound):
        C.read(world.state, MAGNET, batch="adm-000000000000", digest=artifact["digest"])


@pytest.mark.parametrize("kwargs", [{"limit":0}, {"limit":21}, {"limit":True},
    {"cursor":"mc1.mag-other.10.5"}, {"cursor":"broken"}, {"cursor":"mc1."+MAGNET+".10.12"}])
def test_history_bad_parameters_refuse(world, kwargs):
    commit(world, "initial")
    with pytest.raises(fluid.BadRequest):
        C.history(world.state, MAGNET, **kwargs)


@pytest.mark.parametrize("path", [None, "", "../x", "/x", "x/", "x//y", "a/./b", "*.md", "x?", "x[1]", "C:/x", "x\\y"])
def test_exact_file_choice_is_new_execution_only(path):
    source = {"kind":"file", "collection":"col-test"}
    if path is not None:
        source["path"] = path
    assert not X.runnable_files({"sources":[source]})
    assert X.runnable_files({"sources":[{"kind":"file", "collection":"col-test", "path":"exact/café.txt"}]})


def file_row():
    ref, digest = "adm-0123456789ab", "a" * 64
    source = {"kind":"file", "collection":"col-test", "path":"exact.txt"}
    return source, {"kind":"file", "id":ref, "version":ref, "conversation":None,
        "author":None, "at":1.0, "via":"held-source", "value":{
        "ref":ref, "digest":digest, "collection":"col-test", "path":"exact.txt", "text":"é",
        "offset":0, "end":2, "size":5, "acquired_at":1.0, "shortened":True,
        "omitted_bytes":3, "next_offset":2, "citation":f"{ref}@{digest[:12]}[0:2]"}}


@pytest.mark.parametrize("key,value", [("ref","ent-wrong"), ("digest","bad"), ("path","other"),
    ("offset",1), ("end",1), ("size",1), ("acquired_at",2.0), ("shortened",False),
    ("omitted_bytes",0), ("next_offset",None), ("citation","live"), ("text","\x00")])
def test_file_shape_is_pinned(key, value):
    source, row = file_row()
    X._verified_file(row, source, ValueError("bad"))
    row["value"][key] = value
    with pytest.raises(ValueError):
        X._verified_file(row, source, ValueError("bad"))


@pytest.mark.parametrize("field", ["kind", "version", "conversation", "author", "at"])
def test_five_keeps_still_mandatory_for_new_files(world, field):
    art = json.loads(artifact_of(world))
    source, row = file_row()
    definition = art["definition"]["value"]
    definition["sources"].append(source)
    art["page"]["sources"].append({"source":source, "key":schema.source_key(source),
        "summary":None, "status":"partial", "results":[row]})
    bad = ValueError("bad")
    X._verified_page(MAGNET, definition, art["page"], bad)
    del row[field]
    with pytest.raises(ValueError):
        X._verified_page(MAGNET, definition, art["page"], bad)


@pytest.mark.parametrize("damage", ["digest", "operation", "definition-digest", "home"])
def test_historical_digest_operation_definition_and_home_checks_remain(world, damage):
    art = json.loads(artifact_of(world))
    if damage == "operation":
        art["operation"]["op"] = "other"
    elif damage == "definition-digest":
        art["definition"]["sha256"] = "0" * 64
    elif damage == "home":
        art["page"]["sources"][0]["results"][0]["conversation"] = "ent-other"
    raw = json.dumps(art).encode()
    with pytest.raises(X._Stop):
        X._verified(world.state, MAGNET, raw,
            "0" * 64 if damage == "digest" else hashlib.sha256(raw).hexdigest(), X.MEDIA_TYPE)
