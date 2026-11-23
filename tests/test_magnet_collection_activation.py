"""Manual collection eligibility and retained file-only batches on the real private door."""
import copy
import hashlib
import json

import pytest

from mentis.magnet import activation as X, checked, collection, schema
from tests.test_magnet_activation import (
    MAGNET, artifact_of, ask_commit, ask_preflight, asked_body,
    built, record_size, world,
)
from tests.test_magnet_collection_history import file_row


def batch(w, count=1, *, unsupported=False, status="ok"):
    art = json.loads(artifact_of(w))
    source, row = file_row()
    row["value"].update(size=2, shortened=False, omitted_bytes=0, next_offset=None)
    sources, pages = [], []
    for i in range(count):
        selected = {**source, "path": f"selected/{i}.txt"}
        result = copy.deepcopy(row)
        result["value"]["path"] = selected["path"]
        sources.append(selected)
        pages.append({"source": selected, "key": schema.source_key(selected),
                      "summary": None, "status": status,
                      "results": [result] if status in ("ok", "partial") else []})
    if unsupported:
        source = {"kind": "web", "url": "https://example.org/"}
        sources.append(source)
        pages.append({"source": source, "key": schema.source_key(source),
                      "summary": None, "status": "unavailable", "results": []})
    config = art["definition"]["value"]
    config["sources"] = sources
    raw = json.dumps(config)
    art["definition"] = {"sha256": hashlib.sha256(raw.encode()).hexdigest(), "raw": raw,
                         "value": checked(MAGNET, config)}
    art["page"]["sources"] = pages
    w.define(raw)
    return art


@pytest.mark.parametrize("count,unsupported", [(1, False), (20, False), (1, True)])
def test_file_only_preflight_commit_replay_and_retention(world, count, unsupported):
    art = batch(world, count, unsupported=unsupported)
    before = record_size(world)
    ready = ask_preflight(world, asked_body(world))
    assert ready["state"] == "ready", ready
    assert ready["definition"] == art["definition"]
    assert record_size(world) == before
    raw = json.dumps(art).encode()
    answer = ask_commit(world, raw)
    assert answer["state"] == "committed", answer
    result = answer["body"]
    assert result["state"] == ("partial" if unsupported else "complete")
    assert result["page"]["sources"] == count + int(unsupported)
    assert result["page"]["results"] == count
    # The output Conversation is created without becoming a configured source.
    assert result["conversation_created"] is True
    retained = collection.read(world.state, MAGNET)
    assert retained["page"] == art["page"]
    assert retained["config"]["sources"] == art["definition"]["value"]["sources"]
    assert all(s["kind"] != "conversation" for s in retained["config"]["sources"])
    assert collection.history(world.state, MAGNET)["batches"] == [retained["activation"]]
    after = record_size(world)
    assert ask_commit(world, raw)["state"] == "replay"
    assert ask_preflight(world, asked_body(world))["state"] == "replay"
    assert record_size(world) == after


@pytest.mark.parametrize("count", [0, 21])
def test_file_source_count_stays_bounded_at_preflight(world, count):
    art = batch(world)
    config = art["definition"]["value"]
    source = config["sources"][0]
    config["sources"] = [{**source, "path": f"{i}.txt"} for i in range(count)]
    world.define(config)
    before = record_size(world)
    answer = ask_preflight(world, asked_body(world))
    assert (answer["state"], answer["status"], answer["body"]["kind"]) == ("refused", 409, "Unreadable")
    assert record_size(world) == before


@pytest.mark.parametrize("path", [None, "../other.txt", "/root.txt", "*.txt", "folder/"])
def test_file_only_preflight_requires_exact_selection(world, path):
    art = batch(world)
    config = art["definition"]["value"]
    source = config["sources"][0]
    if path is None:
        source.pop("path")
    else:
        source["path"] = path
    world.define(config)
    before = record_size(world)
    answer = ask_preflight(world, asked_body(world))
    assert (answer["state"], answer["status"]) == ("refused", 422)
    assert answer["body"]["reason"] == {"code": "file-choice-required", "message": X.FILE_CHOICE,
                                         "retryable": False}
    assert record_size(world) == before


@pytest.mark.parametrize("status,code,http", [
    ("unavailable", "no-readable-source", 422), ("ok", "no-readable-source", 422),
    ("busy", "sources-busy", 503),
])
def test_file_only_without_useful_results_never_falls_back(world, status, code, http):
    art = batch(world, status=status)
    art["page"]["sources"][0]["results"] = []
    assert ask_preflight(world, asked_body(world))["state"] == "ready"
    before = record_size(world)
    answer = ask_commit(world, json.dumps(art).encode())
    assert (answer["state"], answer["status"]) == ("refused", http)
    assert answer["body"]["reason"]["code"] == code
    assert record_size(world) == before


def test_only_unsupported_sources_still_refuse(world):
    art = batch(world, unsupported=True)
    config = art["definition"]["value"]
    config["sources"] = config["sources"][-1:]
    world.define(config)
    before = record_size(world)
    answer = ask_preflight(world, asked_body(world))
    assert (answer["state"], answer["status"]) == ("refused", 422)
    assert answer["body"]["reason"]["code"] == "no-readable-source"
    assert record_size(world) == before


@pytest.mark.parametrize("change", ["extra-source", "different-source", "different-result-path"])
def test_file_batch_rejects_unconfigured_source(world, change):
    art = batch(world)
    page = art["page"]["sources"][0]
    if change == "extra-source":
        art["page"]["sources"].append(copy.deepcopy(page))
    elif change == "different-source":
        page["source"] = {**page["source"], "path": "not-selected.txt"}
        page["key"] = schema.source_key(page["source"])
    else:
        page["results"][0]["value"]["path"] = "not-selected.txt"
    before = record_size(world)
    answer = ask_commit(world, json.dumps(art).encode())
    assert (answer["state"], answer["status"]) == ("internal-protocol-error", 502)
    assert record_size(world) == before
