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
    prod_brain = pathlib.Path(cfg.env("prod")["brain"])
    prod_brain.mkdir(parents=True, exist_ok=True)
    (prod_brain / "corpus.db").write_bytes(b"")
    monkeypatch.setattr(me, "_migrate_plan", lambda c, env, r: {
        "exit": 0, "plan": {"migrations": [], "problems": [], "breaking": []}, "stderr": ""})
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
    me.write_json(cfg.state("prod") / "serving.json", {"environment": "prod", "current": None,
                                                       "history": [{"release": rid}]})
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_rollback(cfg, _Args(environment="prod", to=rid))
    other = _release(cfg, "never-served-here")
    with pytest.raises(me.Refused, match="never served and verified by prod"):
        me.cmd_rollback(cfg, _Args(environment="prod", to=other, owner_approved="yes"))
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


# -- second review round -------------------------------------------------------------

def test_names_that_reach_a_generated_command_are_validated(tmp_path, monkeypatch):
    root = tmp_path / "env"
    doc = _doc(root)
    doc["environments"]["te st&x"] = doc["environments"].pop("test")
    with pytest.raises(me.Refused, match="environment name"):
        _cfg(tmp_path, monkeypatch, doc=doc)
    doc = _doc(root)
    doc["environments"]["test"]["env"] = {"A=B&calc": "x"}
    with pytest.raises(me.Refused, match="not an environment variable name"):
        _cfg(tmp_path, monkeypatch, doc=doc)
    doc = _doc(root)
    doc["environments"]["test"]["unset"] = ["X Y"]
    with pytest.raises(me.Refused, match="not an environment variable name"):
        _cfg(tmp_path, monkeypatch, doc=doc)
    doc = _doc(root, mars_local_python="C:/py'; calc; '.exe")
    with pytest.raises(me.Refused, match="not safe in a generated command line"):
        _cfg(tmp_path, monkeypatch, doc=doc)
    local = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    doc = _doc(local / "Mentis" / "env-state")
    with pytest.raises(me.Refused, match="production|inside DAY-TO-DAY"):
        _cfg(tmp_path, monkeypatch, doc=doc)


def test_production_never_starts_a_release_whose_runtime_was_never_recorded(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    top = cfg.release_dir(rid)
    doc = json.loads((top / "RELEASE.json").read_text("utf-8"))
    doc["runtime"] = {}
    (top / "RELEASE.json").write_text(json.dumps(doc), "utf-8")
    me.write_json(cfg.releases / "INDEX.json", {rid: me.sha_file(top / "RELEASE.json")})
    assert me.expected_packages(cfg, rid) is None
    with pytest.raises(me.Refused, match="deploy it to TEST first"):
        me.start_env(cfg, cfg.env("prod"), rid)
    _served_in_test(cfg, rid, packages="pk-other")
    assert me.expected_packages(cfg, rid) == "pk-other"
    with pytest.raises(me.Refused, match="not what TEST last verified"):
        me.start_env(cfg, cfg.env("prod"), rid)
    acc = cfg.acceptance(rid)
    acc["served_in"][0].pop("python_packages")
    cfg.save_acceptance(rid, acc)
    _record(cfg, rid, review="pass", browser="pass", owner="pass")
    assert any("did not record the Python and packages" in b for b in me.promotion_blockers(cfg, rid))


def test_a_start_that_does_not_verify_is_stopped_again(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    rid = _release(cfg)
    me.write_json(cfg.state("test") / "serving.json", {"environment": "test",
                                                       "current": {"release": rid}, "history": []})
    did = []
    monkeypatch.setattr(me, "_answering", lambda env: False)
    monkeypatch.setattr(me, "start_env", lambda c, env, r: did.append("start"))
    monkeypatch.setattr(me, "stop_env", lambda c, env: did.append("stop") or ["stopped"])

    def not_it(c, name, r):
        raise me.Failed("what answers is not it")
    monkeypatch.setattr(me, "_verified_on", not_it)
    with pytest.raises(me.Failed, match="it was stopped again"):
        me.cmd_start(cfg, _Args(environment="test"))
    assert did == ["start", "stop"]


def test_rollback_goes_back_from_what_is_observed(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    old, new = _release(cfg, "old"), _release(cfg, "new")
    # the file remembers `old`, but `new` is what is running: the target must be `old`
    me.write_json(cfg.state("test") / "serving.json", {
        "environment": "test", "current": {"release": old}, "history": [{"release": old}]})
    monkeypatch.setattr(me, "_answering", lambda env: True)
    monkeypatch.setattr(me, "observe", lambda c, name: {"serves_release": new})
    went = []
    monkeypatch.setattr(me, "switch", lambda c, name, rid, **kw: went.append(rid) or {})
    me.cmd_rollback(cfg, _Args(environment="test"))
    assert went == [old]
    monkeypatch.setattr(me, "observe", lambda c, name: {"serves_release": None})
    with pytest.raises(me.Refused, match="no recorded release matches"):
        me.cmd_rollback(cfg, _Args(environment="test"))


def test_a_switch_whose_records_cannot_be_written_puts_the_script_and_release_back(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    old, new = _release(cfg, "old"), _release(cfg, "new")
    _served_in_test(cfg, new)
    script = tmp_path / "start.ps1"
    original = "$Launcher = 'legacy.cmd'\n$WorkingDirectory = 'legacy'\n"
    script.write_text(original, "utf-8")
    doc = _doc(tmp_path / "env")
    doc["environments"]["prod"]["start_script"] = str(script)
    cfg = _cfg(tmp_path, monkeypatch, doc=doc)
    started = []
    monkeypatch.setattr(me, "_answering", lambda env: True)
    monkeypatch.setattr(me, "observe", lambda c, name: {"serves_release": old})
    monkeypatch.setattr(me, "_open_runs", lambda env: 0)
    monkeypatch.setattr(me, "stop_env", lambda c, env: ["stopped"])
    monkeypatch.setattr(me, "start_env", lambda c, env, rid: started.append(rid))
    monkeypatch.setattr(me, "_verified_on", lambda c, name, rid: None)
    real = me.write_json

    def failing(path, doc_):
        if pathlib.Path(path).name == "serving.json" and (doc_.get("current") or {}).get("release") == new:
            raise OSError("disk full")
        return real(path, doc_)
    monkeypatch.setattr(me, "write_json", failing)
    with pytest.raises(me.Failed, match="records could not be written.*went back to old, verified"):
        me.switch(cfg, "prod", new, why="t", approved="yes", interrupt_runs=False, migrate=False)
    assert started == [new, old]
    assert script.read_text("utf-8") == original
    assert (cfg.serving("prod").get("current") or {}).get("release") != new


def test_release_folder_containment_is_by_path_not_prefix(tmp_path):
    root = os.path.normcase(os.path.abspath(str(tmp_path / "releases" / "r1")))
    assert me._under(str(tmp_path / "releases" / "r1" / "code"), root)
    assert not me._under(str(tmp_path / "releases" / "r1-evil" / "code"), root)


def test_ports_are_integers_and_stateful_paths_are_not_shared(tmp_path, monkeypatch):
    root = tmp_path / "env"
    for bad in ("8760", 8760.0, True, 0, 70000):
        doc = _doc(root)
        doc["environments"]["test"]["port"] = bad
        with pytest.raises(me.Refused, match="not a port number"):
            _cfg(tmp_path, monkeypatch, doc=doc)
    for key in ("workspace", "backends"):
        doc = _doc(root)
        doc["environments"]["prod"]["backends"] = str(root / "prod" / "backends.json")
        doc["environments"]["test"][key] = doc["environments"]["prod"][key]
        with pytest.raises(me.Refused, match="share"):
            _cfg(tmp_path, monkeypatch, doc=doc)
    doc = _doc(root)
    doc["environments"]["test"]["env"] = {"MENTIS_SOURCE_CACHE": str(root / "prod" / "ws" / "cache")}
    with pytest.raises(me.Refused, match="inside one another"):
        _cfg(tmp_path, monkeypatch, doc=doc)


def test_readiness_never_runs_the_candidate_against_the_production_brain(tmp_path, monkeypatch):
    """Whether a release would migrate production is read from the two manifests; the planner
    is only ever run on the real Brain inside `switch`."""
    cfg = _cfg(tmp_path, monkeypatch, serving_test="new")
    old = _release(cfg, "old", schema=2, min_reader=2)
    new = _release(cfg, "new", schema=3, min_reader=3)
    _served_in_test(cfg, new)
    _record(cfg, new, review="pass", browser="pass", owner="pass")
    ran = []
    monkeypatch.setattr(me, "_migrate_plan", lambda c, env, r: ran.append(r) or {})
    monkeypatch.setattr(me, "run", lambda *a, **k: ran.append(a) or None)
    monkeypatch.setattr(me, "_answering", lambda env: True)
    monkeypatch.setattr(me, "_open_runs", lambda env: 2)
    looks = {"test": {"serves_release": new, "launched_from_release_folder": True},
             "prod": {"up": True, "serves_release": old}}
    monkeypatch.setattr(me, "observe", lambda c, name: looks[name])
    assert me.promotion_blockers(cfg, new, looks) == []
    needs = me.promotion_needs(cfg, new)
    assert any("--interrupt-runs (2 run(s)" in n for n in needs)
    assert any("--migrate" in n and "from schema 2 to 3" in n and "could not open it" in n for n in needs)
    assert ran == []
    db = pathlib.Path(cfg.env("prod")["brain"]) / "corpus.db"
    db.unlink()
    assert any("has no Brain" in b for b in me.promotion_blockers(cfg, new, looks))
    db.write_bytes(b"")
    older = _release(cfg, "older", schema=1, min_reader=1)
    _served_in_test(cfg, older)
    _record(cfg, older, review="pass", browser="pass", owner="pass")
    looks["test"]["serves_release"] = older
    assert any("could not open that Brain" in b for b in me.promotion_blockers(cfg, older, looks))
    looks["prod"] = {"up": True, "serves_release": None, "why_no_release": "drift"}
    assert any("nothing verified to go back to" in b for b in me.promotion_blockers(cfg, older, looks))
    assert ran == []


def test_an_environments_state_folder_is_its_alone(tmp_path, monkeypatch):
    root = tmp_path / "env"
    doc = _doc(root)
    doc["environments"]["test"]["workspace"] = str(root / "prod" / "ws2")
    with pytest.raises(me.Refused, match="inside one another"):
        _cfg(tmp_path, monkeypatch, doc=doc)


def test_any_error_after_the_launch_goes_back_and_says_if_the_script_could_not(tmp_path, monkeypatch):
    doc = _doc(tmp_path / "env")
    cfg = _cfg(tmp_path, monkeypatch, doc=doc)
    old, new = _release(cfg, "old"), _release(cfg, "new")
    _served_in_test(cfg, new)
    started = []
    monkeypatch.setattr(me, "_answering", lambda env: True)
    monkeypatch.setattr(me, "observe", lambda c, name: {"serves_release": old})
    monkeypatch.setattr(me, "_open_runs", lambda env: 0)
    monkeypatch.setattr(me, "stop_env", lambda c, env: ["stopped"])
    monkeypatch.setattr(me, "start_env", lambda c, env, rid: started.append(rid))
    monkeypatch.setattr(me, "_verified_on", lambda c, name, rid: None)

    def boom(c, env, rid):
        raise UnicodeDecodeError("utf-8", b"x", 0, 1, "not text")
    monkeypatch.setattr(me, "_repoint_start_script", boom)
    with pytest.raises(me.Failed, match="UnicodeDecodeError.*went back to old, verified"):
        me.switch(cfg, "prod", new, why="t", approved="yes", interrupt_runs=False, migrate=False)
    assert started == [new, old]
