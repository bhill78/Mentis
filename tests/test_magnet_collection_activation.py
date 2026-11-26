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


@pytest.mark.parametrize("count", [21])
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


def test_a_magnet_with_no_configured_source_refuses_and_collects_nothing(world):
    """NO SOURCE IS NOT A SOURCE. A definition naming none is perfectly readable --
    a Magnet exists around an idea before it collects anything -- and Collect on it
    is refused outright rather than reading anything in their place."""
    art = batch(world)
    config = art["definition"]["value"]
    config["sources"] = []
    world.define(config)
    assert checked(MAGNET, {**config, "id": MAGNET})["sources"] == [], "it reads, and reads as none"
    before = record_size(world)
    answer = ask_preflight(world, asked_body(world))
    assert (answer["state"], answer["status"]) == ("refused", 422), answer
    assert answer["body"]["reason"]["code"] == "no-readable-source"
    assert record_size(world) == before, "nothing is recorded"
    # And a commit for such a definition cannot slip past: preflight refuses it, so
    # a page for it means the two halves disagree, which writes nothing either.
    art["definition"]["raw"] = json.dumps(config)
    art["definition"]["sha256"] = hashlib.sha256(art["definition"]["raw"].encode()).hexdigest()
    art["definition"]["value"] = checked(MAGNET, config)
    art["page"]["sources"] = []
    answer = ask_commit(world, json.dumps(art).encode())
    assert (answer["state"], answer["status"]) == ("internal-protocol-error", 502), answer
    assert record_size(world) == before


@pytest.mark.parametrize("path", ["../other.txt", "/root.txt", "*.txt", "a//b.txt", "a/./b.txt",
                                   "C:/x.txt", "x\\y.txt", " x.txt", "x.txt ", "/", "x?", "x[1]"])
def test_file_preflight_still_requires_a_readable_choice(world, path):
    """WHAT IS STILL REFUSED. A path that names nothing readable -- a traversal, a wildcard, a
    separator, a drive letter, an empty component -- is refused with the same code as before, in the
    widened words. Only the exact-file-ONLY part of the refusal was lifted."""
    art = batch(world)
    config = art["definition"]["value"]
    config["sources"][0]["path"] = path
    world.define(config)
    before = record_size(world)
    answer = ask_preflight(world, asked_body(world))
    assert (answer["state"], answer["status"]) == ("refused", 422)
    assert answer["body"]["reason"] == {"code": "file-choice-required", "message": X.FILE_CHOICE,
                                         "retryable": False}
    assert "prefix" in X.FILE_CHOICE and "whole collection" in X.FILE_CHOICE
    assert record_size(world) == before


def test_an_empty_path_is_the_schema_s_refusal_not_a_whole_collection(world):
    """THE WHOLE COLLECTION IS SAID BY OMITTING `path`, never by an empty one: the schema has always
    refused a blank key, so an empty path is a definition that cannot be read at all, and widening
    the gate must not quietly turn it into "everything"."""
    art = batch(world)
    config = art["definition"]["value"]
    config["sources"][0]["path"] = ""
    assert X.file_choice(config["sources"][0]) is None
    world.define(config)
    before = record_size(world)
    answer = ask_preflight(world, asked_body(world))
    assert (answer["state"], answer["status"], answer["body"]["kind"]) == ("refused", 409, "Unreadable")
    assert record_size(world) == before


@pytest.mark.parametrize("path,named", [(None, ("whole", None)), ("docs/", ("prefix", "docs/")),
                                        ("a/b/c.md", ("exact", "a/b/c.md")),
                                        ("café/é.md", ("exact", "café/é.md")),
                                        (".git/commits/" + "4f" * 20, ("exact", ".git/commits/" + "4f" * 20))])
def test_a_path_a_prefix_or_the_whole_collection_is_runnable(world, path, named):
    """THE LIFTED REFUSAL. `file` has always taken a required `collection` and an OPTIONAL `path`
    (`schema.SOURCE_KINDS`), so naming no path, or a prefix, was already a valid definition and only
    this gate refused it. Each of the three now reaches `ready`."""
    art = batch(world)
    config = art["definition"]["value"]
    source = config["sources"][0]
    if path is None:
        source.pop("path")
    else:
        source["path"] = path
    assert X.file_choice(source) == named
    assert X.runnable_files(config)
    world.define(config)
    before = record_size(world)
    answer = ask_preflight(world, asked_body(world))
    assert answer["state"] == "ready", answer
    assert record_size(world) == before, "a preflight still records nothing"


def test_the_other_cannot_run_refusals_are_untouched():
    """EVERY OTHER REFUSAL STAYS. Part C lifted `file-choice-required`'s exact-file-only half and
    nothing else: the unsupported activation, synthesis, pipeline, ai, output, destination and
    notification refusals, and `no-readable-source`, are the same words they were.

    `collection-not-supported` now admits `scheduled` as well as `one-time`. That is Part D2's
    change in this same file, not Part C's; its words are unchanged."""
    assert set(X._CANNOT_RUN) == {
        "schema-version-not-supported", "activation-not-supported", "collection-not-supported",
        "synthesis-not-supported", "notifications-not-supported", "pipeline-not-supported",
        "extract-mode-not-supported", "ai-not-supported", "output-not-supported",
        "destination-not-supported", "no-readable-source"}
    # THE SHARED CONFORMANCE FIXTURES ARE THE WORDS, and they did not move: every refusal Part C
    # kept is byte for byte the one `tests/fixtures/magnet-conformance/activation/refusals.json`
    # holds, which Rust's door is held to as well. `file-choice-required` is not among them -- it
    # never was -- so no fixture half had to move with this part.
    from tests.test_magnet_activation import REFUSALS
    assert "file-choice-required" not in REFUSALS
    for code, words in X._CANNOT_RUN.items():
        assert REFUSALS[code]["body"]["reason"]["message"] == words, code
        assert REFUSALS[code]["body"]["error"] == words, code
        assert REFUSALS[code]["status"] == 422, code
    # A `file` source is still the only non-conversation kind that reads at all.
    for kind, source in [("brain", {"kind": "brain", "brain": "ent-aaaaaaaaaaaa"}),
                         ("web", {"kind": "web", "url": "https://example.org/"}),
                         ("database", {"kind": "database", "collection": "col-x", "table": "t"})]:
        assert X._cannot_run_code({**_RUNNABLE, "sources": [source]}) == "no-readable-source", kind
    for source in ({"kind": "file", "collection": "col-x"},
                   {"kind": "file", "collection": "col-x", "path": "docs/"},
                   {"kind": "file", "collection": "col-x", "path": "a.md"},
                   {"kind": "conversation", "conversation": "ent-aaaaaaaaaaaa"}):
        assert X._cannot_run_code({**_RUNNABLE, "sources": [source]}) is None, source


#: A definition every other `_cannot_run_code` line passes, so only its sources decide.
_RUNNABLE = {"activation": {"mode": "manual"}, "collection": {"mode": "one-time"},
             "synthesis": {"mode": "manual"},
             "notifications": {"newItems": False, "changes": False, "failures": False},
             "processing": {"operations": [{"op": "extract"}]}}


@pytest.mark.parametrize("source,objects,outside", [
    ({"kind": "file", "collection": "col-test"},
     ["a.md", "deep/er/b.md", ".git/commits/" + "4f" * 20], ["../escape.md", "a//b.md", ""]),
    ({"kind": "file", "collection": "col-test", "path": "docs/"},
     ["docs/a.md", "docs/sub/b.md"], ["notes/a.md", "docs2/a.md", "docs/../a.md"]),
    ({"kind": "file", "collection": "col-test", "path": "exact.txt"},
     ["exact.txt"], ["other.txt", "exact.txt/more"]),
])
def test_a_committed_row_must_lie_inside_what_its_source_named(world, source, objects, outside):
    """THE WIDENING DOES NOT WIDEN WHAT A BATCH MAY CLAIM. A whole-collection source admits any
    object key the same rule would accept as a path; a prefix source admits only what is under it;
    an exact source admits exactly its own path, as it always did. Anything else is the two halves
    disagreeing, and writes nothing."""
    art = batch(world)
    config = art["definition"]["value"]
    config["sources"] = [source]
    raw = json.dumps(config)
    art["definition"] = {"sha256": hashlib.sha256(raw.encode()).hexdigest(), "raw": raw,
                         "value": checked(MAGNET, config)}
    page = art["page"]["sources"][0]
    page["source"], page["key"] = source, schema.source_key(source)
    template = copy.deepcopy(page["results"][0])
    world.define(raw)
    assert ask_preflight(world, asked_body(world))["state"] == "ready"
    for inside in objects:
        row = copy.deepcopy(template)
        row["value"]["path"], row["value"]["collection"] = inside, source["collection"]
        X._verified_file(row, source, ValueError("inside what the source named"))
    for beyond in outside:
        row = copy.deepcopy(template)
        row["value"]["path"], row["value"]["collection"] = beyond, source["collection"]
        with pytest.raises(ValueError):
            X._verified_file(row, source, ValueError("outside what the source named"))
    # And through the real door: a batch whose rows lie outside the source is refused, unrecorded.
    page["results"] = [{**copy.deepcopy(template),
                        "value": {**copy.deepcopy(template)["value"], "path": outside[0],
                                  "collection": source["collection"]}}]
    before = record_size(world)
    answer = ask_commit(world, json.dumps(art).encode())
    assert (answer["state"], answer["status"]) == ("internal-protocol-error", 502), answer
    assert record_size(world) == before


def test_a_collection_scoped_batch_of_many_rows_commits_and_retains_every_citation(world):
    """One collection-scoped source, many rows, each with its own Admission and citation: the whole
    batch commits once and is retained exactly as Rust produced it. The row shape is the same shape
    an exact held file has always had -- a collection-scoped row is a row like any other."""
    art = batch(world)
    config = art["definition"]["value"]
    source = {"kind": "file", "collection": "col-test"}
    config["sources"] = [source]
    raw = json.dumps(config)
    art["definition"] = {"sha256": hashlib.sha256(raw.encode()).hexdigest(), "raw": raw,
                         "value": checked(MAGNET, config)}
    page = art["page"]["sources"][0]
    page["source"], page["key"] = source, schema.source_key(source)
    template = copy.deepcopy(page["results"][0])
    rows = []
    for i in range(12):
        ref, digest = f"adm-{i:012x}", f"{i:064x}"
        row = copy.deepcopy(template)
        row.update(id=ref, version=ref)
        row["value"].update(ref=ref, digest=digest, path=f"docs/{i:03d}.md",
                            citation=f"{ref}@{digest[:12]}[0:{row['value']['end']}]")
        rows.append(row)
    page["results"] = rows
    world.define(raw)
    assert ask_preflight(world, asked_body(world))["state"] == "ready"
    answer = ask_commit(world, json.dumps(art).encode())
    assert answer["state"] == "committed", answer
    assert answer["body"]["state"] == "complete"
    assert answer["body"]["page"]["results"] == 12
    retained = collection.read(world.state, MAGNET)
    assert retained["page"] == art["page"]
    kept = retained["page"]["sources"][0]["results"]
    assert [r["value"]["citation"] for r in kept] == [r["value"]["citation"] for r in rows]
    assert len({r["value"]["ref"] for r in kept}) == 12, "each row cites its own Admission"


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
