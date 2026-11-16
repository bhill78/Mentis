"""tools/env/mentis_env.py: the rules that keep production gated and releases immutable.

These run without any server: they exercise the refusals and the identity arithmetic. The
start / stop / verify path is proved by the rehearsal (tools/env/rehearsal_setup.py).
"""

import json
import pathlib
import stat
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "env"))
import mentis_env as me  # noqa: E402


def _cfg(tmp_path, monkeypatch, serving_test=None):
    root = tmp_path / "env"
    doc = {"format": 1, "root": str(root), "python": sys.executable, "environments": {
        "prod": {"role": "production", "label": "PROD", "port": 1, "private_port": 2,
                 "brain": str(root / "prod" / "brain"), "workspace": str(root / "prod" / "ws"),
                 "run_dir": str(root / "prod" / "run"), "agents": False},
        "test": {"role": "test", "label": "TEST", "port": 3, "private_port": 4,
                 "brain": str(root / "test" / "brain"), "workspace": str(root / "test" / "ws"),
                 "run_dir": str(root / "test" / "run"), "agents": False}}}
    path = tmp_path / "environments.json"
    path.write_text(json.dumps(doc), "utf-8")
    cfg = me.Config(path)
    monkeypatch.setattr(me, "observe", lambda c, name: {
        "serves_release": serving_test if name == "test" else None, "notes": []})
    return cfg


def _release(cfg, rid="r1", schema=2, min_reader=2):
    top = cfg.release_dir(rid)
    (top / "code").mkdir(parents=True)
    (top / "code" / "a.py").write_text("x = 1\n", "utf-8")
    doc = {"id": rid, "created_at": "2026-01-01 00:00:00", "description": "d",
           "source": {"commit": "c" * 40},
           "migration": {"schema_target": schema, "min_reader_after": min_reader},
           "components": {}, "files": me.tree_files(top)}
    (top / "RELEASE.json").write_text(json.dumps(doc), "utf-8")
    return rid


class _Args:
    def __init__(self, **kw):
        self.environment = None
        self.owner_approved = None
        self.interrupt_runs = False
        self.migrate = False
        self.to = None
        self.__dict__.update(kw)


def _record(cfg, rid, **results):
    acc = cfg.acceptance(rid)
    for gate, result in results.items():
        acc["records"].append({"gate": gate, "result": result, "by": "t", "evidence": "e", "at": "now"})
    cfg.save_acceptance(rid, acc)


def test_a_gate_nobody_recorded_is_missing_and_the_latest_record_decides():
    acc = {"records": [{"gate": "review", "result": "pass"}, {"gate": "review", "result": "fail"},
                       {"gate": "browser", "result": "fail"}, {"gate": "browser", "result": "pass"}]}
    assert me.gate_state(acc) == {"review": "fail", "browser": "pass", "owner": "missing"}


def test_promote_refuses_until_every_gate_passed(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, serving_test="r1")
    rid = _release(cfg)
    with pytest.raises(me.Refused, match="review is missing"):
        me.cmd_promote(cfg, _Args(release=rid, owner_approved="yes"))
    _record(cfg, rid, review="pass", browser="pass", owner="pass", **{})
    _record(cfg, rid, review="fail")
    with pytest.raises(me.Refused, match="review is fail"):
        me.cmd_promote(cfg, _Args(release=rid, owner_approved="yes"))


def test_promote_needs_the_release_verified_in_test_and_serving_there_now(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, serving_test="something-else")
    rid = _release(cfg)
    _record(cfg, rid, review="pass", browser="pass", owner="pass")
    with pytest.raises(me.Refused, match="never served and verified in a test environment"):
        me.cmd_promote(cfg, _Args(release=rid, owner_approved="yes"))
    acc = cfg.acceptance(rid)
    acc["served_in"].append({"environment": "test", "role": "test", "verified": True})
    cfg.save_acceptance(rid, acc)
    with pytest.raises(me.Refused, match="no test environment is serving"):
        me.cmd_promote(cfg, _Args(release=rid, owner_approved="yes"))


def test_production_changes_need_the_owners_words(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, serving_test="r1")
    rid = _release(cfg)
    _record(cfg, rid, review="pass", browser="pass", owner="pass")
    acc = cfg.acceptance(rid)
    acc["served_in"].append({"environment": "test", "role": "test", "verified": True})
    cfg.save_acceptance(rid, acc)
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_promote(cfg, _Args(release=rid))
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_stop(cfg, _Args(environment="prod"))
    with pytest.raises(me.Refused, match="through `promote`"):
        me.cmd_deploy(cfg, _Args(environment="prod", release=rid))


def test_a_changed_release_folder_is_not_intact(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    assert me.verify_release(cfg, rid) == []
    (cfg.release_dir(rid) / "code" / "a.py").write_text("x = 2\n", "utf-8")
    (cfg.release_dir(rid) / "code" / "b.py").write_text("", "utf-8")
    assert me.verify_release(cfg, rid) == ["code/a.py is changed", "code/b.py was added"]
    with pytest.raises(me.Refused, match="not intact"):
        me.switch(cfg, "test", rid, why="t", approved=None, interrupt_runs=False, migrate=False)


def test_rollback_refuses_a_release_that_cannot_read_the_migrated_brain(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    old = _release(cfg, "old", schema=1, min_reader=1)
    new = _release(cfg, "new", schema=2, min_reader=2)
    me.write_json(cfg.state("test") / "serving.json", {
        "environment": "test", "current": {"release": new},
        "history": [{"release": old}, {"release": new}]})
    with pytest.raises(me.Refused, match="Fix forward"):
        me.cmd_rollback(cfg, _Args(environment="test"))
    me.write_json(cfg.state("test") / "serving.json", {"environment": "test",
                                                       "current": {"release": new}, "history": []})
    with pytest.raises(me.Refused, match="no earlier release"):
        me.cmd_rollback(cfg, _Args(environment="test"))


def test_digests_ignore_pycache_and_follow_content(tmp_path):
    (tmp_path / "mentis" / "__pycache__").mkdir(parents=True)
    (tmp_path / "mentis" / "a.py").write_text("x = 1\n", "utf-8")
    (tmp_path / "mentis" / "note.txt").write_text("n", "utf-8")
    first = me.backend_digest(tmp_path)
    (tmp_path / "mentis" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    (tmp_path / "mentis" / "note.txt").write_text("changed", "utf-8")
    assert me.backend_digest(tmp_path) == first
    (tmp_path / "mentis" / "a.py").write_text("x = 2\n", "utf-8")
    assert me.backend_digest(tmp_path) != first


def test_agents_off_names_a_command_that_does_not_exist_never_an_empty_one(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    env = {**cfg.env("test"), "env": {"MENTIS_SOURCE_BINDINGS": "X:\\b.json"}, "unset": ["MENTIS_OWNER_TOKEN"]}
    text = me._launch_cmd(cfg, env, rid).read_text("utf-8")
    assert 'set "MENTIS_SOURCE_BINDINGS=X:\\b.json"' in text and 'set "MENTIS_OWNER_TOKEN="' in text
    line = next(l for l in text.splitlines() if l.startswith("set MENTIS_MARS_COMMAND"))
    assert "no-mars.exe" in line and not (cfg.state("test") / "agents-off" / "no-mars.exe").exists()
    on = me._launch_cmd(cfg, {**env, "agents": True, "backends": "X:\\backends.json",
                              "mars_data": "X:\\mars"}, rid).read_text("utf-8")
    assert '--data-dir "X:\\mars" stdio' in on and "no-mars.exe" not in on


def test_snapshot_refuses_when_the_target_has_a_brain_or_is_production(tmp_path, monkeypatch):
    import snapshot
    cfg = _cfg(tmp_path, monkeypatch)
    a = _Args(source="test", target="prod", owner_authorized="yes")
    with pytest.raises(me.Refused, match="never written into production"):
        snapshot.populate(cfg, a, me)
    pathlib.Path(cfg.env("test")["brain"]).mkdir(parents=True)
    with pytest.raises(me.Refused, match="already has a Brain"):
        snapshot.populate(cfg, _Args(source="prod", target="test", owner_authorized="yes"), me)
    assert stat.S_ISDIR(pathlib.Path(cfg.env("test")["brain"]).stat().st_mode)
