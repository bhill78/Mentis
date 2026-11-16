"""The summary batch tool's own decisions: what is carried between Brains, what
a check refuses or flags, and what an import will not send."""
import importlib.util
import json
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "brain_summaries", pathlib.Path(__file__).resolve().parents[1] / "tools" / "brain_summaries.py")
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)


def item(eid, words, **kw):
    return {"id": eid, "kind": "lesson", "words": words, "of": tool.digest(words), "fields": {}, **kw}


def run(argv):
    return tool.main(argv)


def write(path, value):
    path.write_text(json.dumps(value), "utf-8")
    return str(path)


def test_reuse_needs_the_same_id_and_the_same_words(tmp_path):
    here = [item("ent-a", "the same words"), item("ent-b", "words that changed here"),
            item("ent-c", "a record the other Brain never had")]
    library = [{"id": "ent-a", "summary": "Same.", "of": tool.digest("the same words")},
               {"id": "ent-b", "summary": "For other words.", "of": tool.digest("the words it had there")},
               {"id": "ent-z", "summary": "A record this Brain does not have.", "of": "x"}]
    out, rest = tmp_path / "out.json", tmp_path / "rest.json"
    assert run(["reuse", "--missing", write(tmp_path / "m.json", here),
                "--library", write(tmp_path / "l.json", library),
                "--out", str(out), "--rest", str(rest)]) == 0
    assert [r["id"] for r in json.loads(out.read_text("utf-8"))] == ["ent-a"]
    assert [r["id"] for r in json.loads(rest.read_text("utf-8"))] == ["ent-b", "ent-c"]


def test_flags_what_the_record_does_not_hold_and_a_lost_limit():
    rec = item("ent-a", "The cache may be stale after a deploy on DAY-TO-DAY; seen 3 times.")
    assert tool.flags_of(rec, "The cache may be stale after a deploy on DAY-TO-DAY.") == ([], [])
    hard, soft = tool.flags_of(rec, "The cache is stale after every deploy on MARS, seen 14 times.")
    assert hard == []
    assert any("MARS" in s for s in soft) and any("14" in s for s in soft)
    assert any("limit or uncertainty" in s for s in soft)
    assert tool.flags_of(rec, "x" * 201)[0] == ["over 200 characters"]
    assert tool.flags_of(rec, "one\ntwo")[0] == ["more than one line"]
    assert tool.flags_of(rec, "  ")[0] == ["no summary"]
    # a name the record gives outside its words is not invented
    named = item("ent-p", "You judge candidates.", name="Independent Reviewer")
    assert tool.flags_of(named, "Independent Reviewer: judges candidates.") == ([], [])


def test_check_refuses_hard_failures_and_unreviewed_flags(tmp_path):
    here = [item("ent-a", "Background tests die with the run."),
            item("ent-b", "The fix may not hold; unverified.")]
    m = write(tmp_path / "m.json", here)
    report = tmp_path / "report.json"
    good = [{"id": "ent-a", "summary": "Background tests die with the run."},
            {"id": "ent-b", "summary": "The fix may not hold and is unverified."}]
    assert run(["check", "--missing", m, "--file", write(tmp_path / "s.json", good),
                "--report", str(report)]) == 0
    got = json.loads(report.read_text("utf-8"))
    assert (got["hard_failures"], got["unreviewed_flags"], got["without_a_summary"]) == (0, 0, [])

    bad = [{"id": "ent-a", "summary": "Background tests die with the run."},
           {"id": "ent-b", "summary": "The fix holds."},
           {"id": "ent-zz", "summary": "A record that is not here."},
           {"id": "ent-a", "summary": "Named twice."}]
    s = write(tmp_path / "bad.json", bad)
    assert run(["check", "--missing", m, "--file", s, "--report", str(report)]) == 1
    got = json.loads(report.read_text("utf-8"))
    assert got["hard_failures"] == 2 and got["unreviewed_flags"] == 1

    # a reader clears a flag only for the exact summary they read
    reviewed = [{"id": "ent-b", "summary": "The fix holds, say the tests.", "verdict": "ok", "by": "a reader"}]
    assert run(["check", "--missing", m, "--file", s, "--report", str(report),
                "--reviewed", write(tmp_path / "r.json", reviewed)]) == 1
    assert json.loads(report.read_text("utf-8"))["unreviewed_flags"] == 1
    reviewed[0]["summary"] = "The fix holds."
    run(["check", "--missing", m, "--file", s, "--report", str(report),
         "--reviewed", write(tmp_path / "r.json", reviewed)])
    assert json.loads(report.read_text("utf-8"))["unreviewed_flags"] == 0

    wrong_words = [{"id": "ent-a", "summary": "Background tests die with the run.", "of": "0" * 64}]
    assert run(["check", "--missing", m, "--file", write(tmp_path / "w.json", wrong_words),
                "--report", str(report)]) == 1
    assert "different words" in json.loads(report.read_text("utf-8"))["rows"][0]["hard"][0]


def test_import_sends_only_what_passed_and_is_still_wanted(tmp_path, monkeypatch):
    here = [item("ent-a", "alpha words"), item("ent-b", "beta words"), item("ent-c", "gamma words")]
    m = write(tmp_path / "m.json", here)
    summaries = [{"id": "ent-a", "summary": "Alpha words."}, {"id": "ent-b", "summary": "Beta words."},
                 {"id": "ent-c", "summary": "Gamma words."}]
    s = write(tmp_path / "s.json", summaries)
    report = tmp_path / "report.json"
    assert run(["check", "--missing", m, "--file", s, "--report", str(report)]) == 0
    # since the check: ent-b got a kept summary, and ent-c is a record with other words
    monkeypatch.setattr(tool, "missing_of", lambda server: [here[0], item("ent-c", "gamma words, changed")])
    monkeypatch.setattr(tool, "owner_of", lambda server: "ent-owner")
    sent = []

    def call(server, path, body=None):
        sent.append((path, body))
        return {"kept": [i["id"] for i in body["items"]], "refused": []}
    monkeypatch.setattr(tool, "call", call)
    assert run(["import", "--server", "http://x", "--missing", m, "--file", s,
                "--report", str(report), "--model", "test-model"]) == 0
    assert len(sent) == 1
    path, body = sent[0]
    assert path == "/api/ladder/summaries" and body["model"] == "test-model"
    assert body["items"] == [{"id": "ent-a", "summary": "Alpha words."}]

    # a report with failures imports nothing at all
    report.write_text(json.dumps({"hard_failures": 1, "unreviewed_flags": 0, "rows": []}), "utf-8")
    with pytest.raises(SystemExit, match="nothing is imported"):
        run(["import", "--server", "http://x", "--missing", m, "--file", s,
             "--report", str(report), "--model", "test-model"])
