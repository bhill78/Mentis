"""tools/env/mentis_env.py: the rules that keep production gated and releases immutable.

These run without any server: they exercise the refusals and the identity arithmetic. The
start / stop / verify path is proved by the rehearsal (tools/env/rehearsal_setup.py).
"""

import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "env"))
import mentis_env as me  # noqa: E402


def _doc(root, **over):
    def env(name, role, port):
        return {"role": role, "label": name.upper(), "port": port, "private_port": port + 1,
                "brain": str(root / name / "brain"), "workspace": str(root / name / "ws"),
                "run_dir": str(root / name / "run"), "agents": False}
    doc = {"format": 1, "root": str(root), "python": sys.executable,
           "environments": {"prod": env("prod", "production", 11), "test": env("test", "test", 13)}}
    doc.update(over)
    return doc


def _cfg(tmp_path, monkeypatch, serving_test=None, doc=None):
    root = tmp_path / "env"
    path = tmp_path / "environments.json"
    path.write_text(json.dumps(doc or _doc(root)), "utf-8")
    monkeypatch.setattr(me, "packages_digest", lambda python: "pk1")
    cfg = me.Config(path)
    monkeypatch.setattr(me, "observe", lambda c, name: {
        "serves_release": serving_test if name == "test" else None,
        "launched_from_release_folder": True, "notes": []})
    return cfg


def _release(cfg, rid="r1", schema=2, min_reader=2):
    top = cfg.release_dir(rid)
    (top / "code").mkdir(parents=True)
    (top / "code" / "a.py").write_text("x = 1\n", "utf-8")
    doc = {"id": rid, "created_at": "2026-01-01 00:00:00", "description": "d",
           "source": {"commit": "c" * 40}, "runtime": {"packages_sha256": "pk1"},
           "migration": {"schema_target": schema, "min_reader_after": min_reader},
           "components": {}, "files": me.tree_files(top)}
    (top / "RELEASE.json").write_text(json.dumps(doc), "utf-8")
    index = cfg.index()
    index[rid] = me.sha_file(top / "RELEASE.json")
    me.write_json(cfg.releases / "INDEX.json", index)
    return rid


class _Args:
    def __init__(self, **kw):
        self.environment = None
        self.owner_approved = None
        self.interrupt_runs = False
        self.migrate = False
        self.to = None
        self.__dict__.update(kw)


def _served_in_test(cfg, rid, at="2026-01-01 00:00:00", packages="pk1"):
    acc = cfg.acceptance(rid)
    acc["served_in"].append({"environment": "test", "role": "test", "verified": True, "at": at,
                             "python_packages": packages})
    cfg.save_acceptance(rid, acc)


def _record(cfg, rid, at="2026-01-02 00:00:00", **results):
    acc = cfg.acceptance(rid)
    for gate, result in results.items():
        acc["records"].append({"gate": gate, "result": result, "by": "t", "evidence": "e", "at": at})
    cfg.save_acceptance(rid, acc)


# -- gates ---------------------------------------------------------------------------

def test_a_gate_nobody_recorded_is_missing_and_the_latest_record_decides():
    acc = {"records": [{"gate": "review", "result": "pass"}, {"gate": "review", "result": "fail"},
                       {"gate": "browser", "result": "fail"}, {"gate": "browser", "result": "pass"}]}
    assert me.gate_state(acc) == {"review": "fail", "browser": "pass", "owner": "missing"}


def test_promote_refuses_until_every_gate_passed_after_test_verified_it(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, serving_test="r1")
    rid = _release(cfg)
    with pytest.raises(me.Refused, match="never served and verified in a test environment"):
        me.cmd_promote(cfg, _Args(release=rid, owner_approved="yes"))
    _served_in_test(cfg, rid)
    with pytest.raises(me.Refused, match="review is missing.*browser is missing.*owner is missing"):
        me.cmd_promote(cfg, _Args(release=rid, owner_approved="yes"))
    _record(cfg, rid, review="pass", browser="pass", owner="pass")
    _record(cfg, rid, review="fail")
    with pytest.raises(me.Refused, match="review is fail"):
        me.cmd_promote(cfg, _Args(release=rid, owner_approved="yes"))


def test_a_gate_passed_before_test_ever_ran_the_release_does_not_count(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, serving_test="r1")
    rid = _release(cfg)
    _served_in_test(cfg, rid, at="2026-01-05 00:00:00")
    _record(cfg, rid, at="2026-01-02 00:00:00", review="pass", browser="pass", owner="pass")
    blockers = me.promotion_blockers(cfg, rid)
    assert len(blockers) == 3 and all("before the release was ever verified in TEST" in b for b in blockers)


def test_record_refuses_a_release_test_has_not_served(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    with pytest.raises(me.Refused, match="deploy it there first"):
        me.cmd_record(cfg, _Args(release=rid, gate="review", result="pass", by="x", evidence="e"))


def test_ready_is_what_promote_checks(tmp_path, monkeypatch):
    """status and promote read one function: TEST serving something else, a changed Python,
    or a touched release folder each make a fully-passed release not ready."""
    cfg = _cfg(tmp_path, monkeypatch, serving_test="r1")
    rid = _release(cfg)
    _served_in_test(cfg, rid)
    _record(cfg, rid, review="pass", browser="pass", owner="pass")
    assert me.promotion_blockers(cfg, rid) == []
    assert any("no test environment is serving" in b for b in me.promotion_blockers(
        cfg, rid, {"test": {"serves_release": "other", "launched_from_release_folder": True}}))
    assert any("no test environment is serving" in b for b in me.promotion_blockers(
        cfg, rid, {"test": {"serves_release": rid, "launched_from_release_folder": False}}))
    monkeypatch.setattr(me, "packages_digest", lambda python: "pk2")
    assert any("packages changed since TEST verified" in b for b in me.promotion_blockers(cfg, rid))
    monkeypatch.setattr(me, "packages_digest", lambda python: "pk1")
    os.chmod(cfg.release_dir(rid) / "code" / "a.py", 0o666)
    (cfg.release_dir(rid) / "code" / "a.py").write_text("x = 2\n", "utf-8")
    assert any("not intact" in b for b in me.promotion_blockers(cfg, rid))


# -- production ----------------------------------------------------------------------

def test_production_changes_need_the_owners_words(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, serving_test="r1")
    rid = _release(cfg)
    _served_in_test(cfg, rid)
    _record(cfg, rid, review="pass", browser="pass", owner="pass")
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_promote(cfg, _Args(release=rid))
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_stop(cfg, _Args(environment="prod"))
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_start(cfg, _Args(environment="prod"))
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_rollback(cfg, _Args(environment="prod", to=rid))
    with pytest.raises(me.Refused, match="through `promote`"):
        me.cmd_deploy(cfg, _Args(environment="prod", release=rid))


def test_a_file_cannot_relabel_production_as_test(tmp_path, monkeypatch):
    root = tmp_path / "env"
    local = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    for change in ({"port": 8760}, {"private_port": 18760},
                   {"brain": str(local / "Mentis" / "Mark-IV" / "brain")},
                   {"run_dir": str(local / "Mentis" / "run" / "8760")},
                   {"env": {"MARS_DATA_DIR": str(local / "mars")}}):
        doc = _doc(root)
        doc["environments"]["test"].update(change)
        with pytest.raises(me.Refused, match="production whatever this file calls it"):
            _cfg(tmp_path, monkeypatch, doc=doc)


def test_the_configuration_is_one_production_and_disjoint(tmp_path, monkeypatch):
    root = tmp_path / "env"
    doc = _doc(root)
    doc["environments"]["test"]["role"] = "production"
    with pytest.raises(me.Refused, match="exactly one environment is `production`"):
        _cfg(tmp_path, monkeypatch, doc=doc)
    doc = _doc(root)
    doc["environments"]["test"]["brain"] = doc["environments"]["prod"]["brain"]
    with pytest.raises(me.Refused, match="share"):
        _cfg(tmp_path, monkeypatch, doc=doc)
    doc = _doc(root)
    doc["environments"]["test"]["port"] = doc["environments"]["prod"]["port"]
    with pytest.raises(me.Refused, match="share port"):
        _cfg(tmp_path, monkeypatch, doc=doc)
    for bad in ("C:\\a%PATH%\\brain", "C:\\a'b\\brain", "C:\\a&b\\brain", "C:\\a$(x)\\brain"):
        doc = _doc(root)
        doc["environments"]["test"]["brain"] = bad
        with pytest.raises(me.Refused, match="not safe in a generated command line"):
            _cfg(tmp_path, monkeypatch, doc=doc)


# -- releases ------------------------------------------------------------------------

def test_a_changed_release_folder_or_manifest_is_not_intact(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    assert me.verify_release(cfg, rid) == []
    top = cfg.release_dir(rid)
    (top / "code" / "b.py").write_text("", "utf-8")
    assert me.verify_release(cfg, rid) == ["code/b.py was added"]
    with pytest.raises(me.Refused, match="not intact"):
        me.switch(cfg, "test", rid, why="t", approved=None, interrupt_runs=False, migrate=False)
    # the manifest edited to bless the added file no longer matches the index outside the folder
    doc = json.loads((top / "RELEASE.json").read_text("utf-8"))
    doc["files"] = me.tree_files(top)
    doc["files"].pop("RELEASE.json", None)
    (top / "RELEASE.json").write_text(json.dumps(doc), "utf-8")
    assert me.verify_release(cfg, rid) == ["RELEASE.json is not the manifest recorded when the release was built"]
    # a copy of a release under another name is not that release
    other = _release(cfg, "r2")
    os.replace(cfg.release_dir(other), cfg.release_dir("r3"))
    assert "not in" in me.verify_release(cfg, "r3")[0]


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


def test_a_pending_migration_is_read_from_the_real_plan_shape():
    """mentis.spine.migrations.plan: `migrations` is the pending list."""
    import inspect
    from mentis.spine import migrations
    assert '"migrations": [' in inspect.getsource(migrations.plan)
    assert me._needs_migration({"plan": {"migrations": [{"id": "0003"}], "breaking": []}})
    assert not me._needs_migration({"plan": {"migrations": [], "breaking": []}})


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


# -- processes and scripts -----------------------------------------------------------

def test_a_reused_pid_is_never_killed(tmp_path, monkeypatch):
    killed = []
    monkeypatch.setattr(me, "run", lambda args, **kw: killed.append(args))
    monkeypatch.setattr(me, "process_facts", lambda pid: {"pid": pid, "start_time": "222"})
    assert me._kill_recorded({"pid": 7, "start_time": "111"}) is False and killed == []
    assert me._kill_recorded({"pid": 7, "start_time": "222"}) is True
    assert killed == [["taskkill", "/PID", 7, "/T", "/F"]]
    monkeypatch.setattr(me, "process_facts", lambda pid: None)
    assert me._kill_recorded({"pid": 7, "start_time": "222"}) is False


def test_the_start_script_changes_exactly_or_not_at_all(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    script = tmp_path / "start.ps1"
    env = {**cfg.env("prod"), "start_script": str(script)}
    script.write_text("$Port = 1\n$Launcher = 'old.cmd'\n$WorkingDirectory = 'old'\n", "utf-8")
    backup = me._repoint_start_script(cfg, env, rid)
    text = script.read_text("utf-8")
    assert str(cfg.state("prod") / "launch.cmd") in text and str(cfg.release_dir(rid) / "code") in text
    assert pathlib.Path(backup).read_text("utf-8").count("old") == 2
    for broken in ("$Port = 1\n", "$Launcher = 'a'\n$Launcher = 'b'\n$WorkingDirectory = 'c'\n"):
        script.write_text(broken, "utf-8")
        with pytest.raises(me.Failed, match="was not changed"):
            me._repoint_start_script(cfg, env, rid)
        assert script.read_text("utf-8") == broken


def test_agents_off_runs_a_program_that_says_so_never_an_empty_command(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    env = {**cfg.env("test"), "env": {"MENTIS_SOURCE_BINDINGS": "X:\\b.json"}, "unset": ["MENTIS_OWNER_TOKEN"]}
    text = me._launch_cmd(cfg, env, rid).read_text("utf-8")
    assert 'set "MENTIS_SOURCE_BINDINGS=X:\\b.json"' in text and 'set "MENTIS_OWNER_TOKEN="' in text
    line = next(l for l in text.splitlines() if l.startswith("set MENTIS_MARS_COMMAND"))
    assert "agents_off.py" in line and "mars.exe" not in line and line.strip() != "set MENTIS_MARS_COMMAND="
    off = cfg.state("test") / "agents_off.py"
    assert str(off) in line and "raise SystemExit(3)" in off.read_text("utf-8")
    on = me._launch_cmd(cfg, {**env, "agents": True, "backends": "X:\\backends.json",
                              "mars_data": "X:\\mars"}, rid).read_text("utf-8")
    assert '--data-dir "X:\\mars" stdio' in on and "agents_off.py" not in on


def test_snapshot_refuses_when_the_target_has_a_brain_or_is_production(tmp_path, monkeypatch):
    import snapshot
    cfg = _cfg(tmp_path, monkeypatch)
    a = _Args(source="test", target="prod", owner_authorized="yes")
    with pytest.raises(me.Refused, match="never written into production"):
        snapshot.populate(cfg, a, me)
    pathlib.Path(cfg.env("test")["brain"]).mkdir(parents=True)
    with pytest.raises(me.Refused, match="already has a Brain"):
        snapshot.populate(cfg, _Args(source="prod", target="test", owner_authorized="yes"), me)
