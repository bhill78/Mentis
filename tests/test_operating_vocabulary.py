"""`tools/operating_vocabulary.py`: vocabulary revision `operating-model-1` on
a Brain made before it.

WHAT MUST HOLD:
  - `--check` reports what would change and writes nothing;
  - applying writes one new definition version per Kind, carrying everything
    the old one said (`knowing`, `standing_apt`, an owner's own label) and
    changing only the delta, so the Brain matches a new one's fields;
  - a second run writes nothing;
  - a definition it does not recognise is refused, and nothing is written for
    any Kind;
  - the day-to-day Brain's path is refused without `--live`.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

import mentis.api as api
from tests._brains import new_brain

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "operating_vocabulary.py"
spec = importlib.util.spec_from_file_location("operating_vocabulary", TOOL)
ov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ov)


def _old(body, kind):
    """The definition as it shipped before the revision."""
    old = json.loads(json.dumps(body))
    old.pop("kind")
    old["fields"] = list(ov.PRIOR_FIELDS[kind])
    form = old["form"]
    for name in ("tools", "inputs", "outputs", "limits", "projects",
                 "evidence", "interrupted"):
        form.pop(name, None)
    if kind == "discipline":
        form["requires"].pop("delivered_label")
        # An owner's own wording, which the revision must carry forward.
        form["verification"]["label"] = "How we check it"
    else:
        old["authoring"]["placeable"] = False
    return old


@pytest.fixture
def old_brain(tmp_path):
    """A Brain whose Discipline and Workflow are the pre-revision ones."""
    path = new_brain(tmp_path / "brain")
    c = api.open_corpus(path, access="write")
    api.brain(c)       # the vocabulary a new Brain gets
    for kind in ("discipline", "workflow"):
        props = _old(c.current_definition(kind)["body"], kind)
        fields = props.pop("fields")
        c.define_kind(kind, fields=fields, properties=props,
                      attributed_to="human")
    c.close()
    return path


def _definitions(path):
    c = api.open_corpus(path, access="read")
    try:
        return {k: c.current_definition(k) for k in ("discipline", "workflow")}
    finally:
        c.close()


def test_check_reports_and_writes_nothing(old_brain, capsys):
    before = _definitions(old_brain)
    assert ov.main([old_brain, "--check"]) == 0
    report = capsys.readouterr().out
    assert "CHECK (nothing written)" in report
    assert "REVISED  discipline" in report and "REVISED  workflow" in report
    assert "fields added: ['tools', 'inputs', 'outputs', 'limits']" in report
    assert "authoring placeable: False -> 'reference'" in report
    assert _definitions(old_brain) == before


def test_apply_carries_the_old_definition_forward(old_brain, capsys):
    before = _definitions(old_brain)
    assert ov.main([old_brain, "--attributed-to", "human"]) == 0
    assert "APPLIED (2 definition(s) written)" in capsys.readouterr().out
    after = _definitions(old_brain)
    for kind in ("discipline", "workflow"):
        was, now = before[kind]["body"], after[kind]["body"]
        assert after[kind]["definition"]["version"] == \
            before[kind]["definition"]["version"] + 1
        assert now["fields"] == ov.target(kind)["fields"]
        for prop in ("knowing", "standing_apt", "capturable", "truth_apt"):
            assert now[prop] == was[prop]
    d = after["discipline"]["body"]["form"]
    assert d["verification"]["label"] == "How we check it"
    assert d["tools"]["delivered_label"].startswith(
        "Tools it uses (named, not granted;")
    assert d["requires"]["delivered_label"] == "Requires (runtime capabilities)"
    assert d["limits"]["label"] == "Known limitations and dependencies"
    w = after["workflow"]["body"]
    assert w["authoring"]["placeable"] == "reference"
    assert w["form"]["evidence"]["label"] == "What supports completion"
    assert w["form"]["interrupted"]["label"] == (
        "If interrupted: what remains and how it continues")
    assert w["form"]["projects"]["label"] == "Projects it applies to"


def test_a_second_run_writes_nothing(old_brain, capsys):
    ov.main([old_brain, "--attributed-to", "human"])
    once = _definitions(old_brain)
    capsys.readouterr()
    assert ov.main([old_brain, "--attributed-to", "human", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["changes"] == [] and out["written"] == 0
    assert {u["name"] for u in out["unchanged"]} == {"discipline", "workflow"}
    assert _definitions(old_brain) == once


def test_a_new_brain_is_already_at_the_revision(tmp_path, capsys):
    path = new_brain(tmp_path / "fresh")
    c = api.open_corpus(path, access="write")
    api.brain(c)
    c.close()
    assert ov.main([path, "--check"]) == 0
    assert "Nothing to do" in capsys.readouterr().out


def test_an_unrecognised_definition_is_refused(old_brain, capsys):
    c = api.open_corpus(old_brain, access="write")
    props = dict(c.current_definition("workflow")["body"])
    props.pop("kind")
    fields = props.pop("fields") + ["owner_extra"]
    c.define_kind("workflow", fields=fields, properties=props,
                  attributed_to="human")
    c.close()
    before = _definitions(old_brain)
    assert ov.main([old_brain, "--attributed-to", "human"]) == 1
    report = capsys.readouterr().out
    assert "REFUSED  workflow" in report and "owner's decision" in report
    # Not even the Discipline, which it does recognise.
    assert _definitions(old_brain) == before


def test_the_live_brain_is_refused_without_saying_so(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    live = tmp_path / "Mentis" / "Mark-IV" / "brain"
    with pytest.raises(SystemExit):
        ov.main([str(live), "--check"])


def test_writing_needs_the_owner(old_brain):
    with pytest.raises(SystemExit):
        ov.main([old_brain])
