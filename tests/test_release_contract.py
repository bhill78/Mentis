"""The DAY-TO-DAY deployment contract (tools/env/mentis_env.py, "the deployment contract").

"Deploy to DAY-TO-DAY" is the whole lifecycle: committed, integrated into main, main pushed and
confirmed on the remote, artifacts built from those exact commits, tests and independent review
passed, verified on TEST, promoted without interrupting work, production verified.

These run against REAL Git repositories (a working clone and a bare remote, both made here), so
"on the remote main" is asked of a remote, not stubbed. Only starting and stopping servers is
replaced; the full path with real servers is the rehearsal.
"""

import io
import json
import pathlib
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "env"))
import mentis_env as me  # noqa: E402


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", *args], capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def _repo(tmp_path, name, files):
    """A working clone with one commit on main, pushed to its own bare remote."""
    remote, work = tmp_path / f"{name}-remote.git", tmp_path / name
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    git(work, "config", "core.autocrlf", "false")
    git(work, "remote", "add", "origin", str(remote))
    commit(work, files, "first")
    git(work, "push", "-q", "origin", "main")
    return work, remote


def commit(work, files, subject):
    for rel, text in files.items():
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", subject)
    return git(work, "rev-parse", "HEAD")


class World:
    """Two repositories with remotes, an environments file, and what the stubbed servers serve."""

    def __init__(self, tmp_path, monkeypatch):
        self.mentis, self.mentis_remote = _repo(tmp_path, "mentis", {
            "mentis/a.py": "x = 1\n", "apps/fluid-web/src.ts": "ui\n", "crates/front.rs": "fn main() {}\n",
            "tools/release_modernize/route-table.json": "{}\n"})
        self.mars, self.mars_remote = _repo(tmp_path, "mars", {"rust/mars.rs": "fn main() {}\n"})
        root = tmp_path / "env"

        def env(name, role, port):
            return {"role": role, "label": name.upper(), "port": port, "private_port": port + 1,
                    "brain": str(root / name / "brain"), "workspace": str(root / name / "ws"),
                    "run_dir": str(root / name / "run"), "agents": False}
        path = tmp_path / "environments.json"
        path.write_text(json.dumps({
            "format": 1, "root": str(root), "python": sys.executable, "repo": str(self.mentis),
            "sources": {"mars": {"repo": str(self.mars)}},
            "environments": {"prod": env("prod", "production", 11), "test": env("test", "test", 13)}}), "utf-8")
        monkeypatch.setattr(me, "packages_digest", lambda python: "pk1")
        me._REMOTE_SEEN.clear()
        self.cfg = me.Config(path)
        for name in ("prod", "test"):
            brain = pathlib.Path(self.cfg.env(name)["brain"])
            brain.mkdir(parents=True)
            (brain / "corpus.db").write_bytes(b"")
        self.serves = {"prod": None, "test": None}
        self.runs = {"prod": 0, "test": 0}
        self.started = []
        monkeypatch.setattr(me, "_migrate_plan", lambda c, e, r: {
            "exit": 0, "plan": {"migrations": [], "problems": [], "breaking": []}, "stderr": ""})
        def observe(c, name):
            e = c.env(name)
            return {"environment": name, "label": e["label"], "role": e["role"], "url": "http://x",
                    "up": self.is_up(name), "serves_release": self.serves[name], "brain": e["brain"],
                    "launched_from_release_folder": True, "notes": [],
                    "components": {"backend": {"digest": "b", "commit_at_start": "c", "pid": 1},
                                   "frontend": {"digest": "f"}, "front": {"sha256": "s"},
                                   "mars": {"sha256": "m"}}}
        monkeypatch.setattr(me, "observe", observe)
        monkeypatch.setattr(me, "_answering", lambda e: self.is_up(e["name"]))
        monkeypatch.setattr(me, "_open_runs", lambda e: self.runs[e["name"]])
        monkeypatch.setattr(me, "stop_env", lambda c, e: ["stopped"])
        monkeypatch.setattr(me, "_verified_on", lambda c, name, rid: None)

        def start(c, e, rid, wait=300):
            self.serves[e["name"]] = rid
            self.started.append((e["name"], rid))
        monkeypatch.setattr(me, "start_env", start)
        self.mars_commit = git(self.mars, "rev-parse", "HEAD")
        self.front_commit = git(self.mentis, "rev-parse", "HEAD")

    def is_up(self, name):
        """Production answers once something was started on it; TEST always does."""
        return name == "test" or self.serves[name] is not None

    def binary(self, component, content: bytes, commit, repo, how="built by this tool"):
        """What `build-binaries` records for a file it built from `commit`."""
        import hashlib
        sha = hashlib.sha256(content).hexdigest()
        known = me.binaries(self.cfg)
        known[sha] = {"component": component, "commit": commit, "repository": str(repo), "how": how}
        me.write_json(self.cfg.releases / "BINARIES.json", known)
        return content

    def release(self, commit, rid, *, dist="built", tamper=None, mars=b"mars-1", front=b"front-1",
                launcher=b"launch-1", register=True):
        """A release folder as `build` makes one: `git archive` of the commit, an interface, the
        three binaries, and a manifest recorded in the index."""
        cfg = self.cfg
        top = cfg.release_dir(rid)
        code = top / "code"
        code.mkdir(parents=True)
        tar = subprocess.run(["git", "-C", str(self.mentis), "archive", "--format=tar", commit],
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(code, filter="data")
        d = code / "apps" / "fluid-web" / "dist"
        d.mkdir(parents=True)
        (d / "index.html").write_text("<html>ui</html>", "utf-8")
        identity = {"commit": commit, "dirty": False}
        (d / "build-identity.json").write_text(json.dumps(identity), "utf-8")
        (code / "BUILD.json").write_text(json.dumps({"release": rid}), "utf-8")
        (top / "bin").mkdir()
        if register:
            self.binary("mars", mars, self.mars_commit, self.mars)
            self.binary("front", front, self.front_commit, self.mentis)
            self.binary("launcher", launcher, self.front_commit, self.mentis)
        (top / "bin" / "mars.exe").write_bytes(mars)
        (top / "bin" / "mentis-server.exe").write_bytes(front)
        (top / "bin" / "mentis-launch.exe").write_bytes(launcher)
        if tamper:
            tamper(code)
        doc = {"id": rid, "created_at": f"2026-01-01 00:00:{len(cfg.all_releases()):02d}", "description": "d",
               "source": {"commit": commit}, "runtime": {"packages_sha256": "pk1"},
               "migration": {"schema_target": 2, "min_reader_after": 2},
               "components": {
                   "frontend": {"digest": me.dist_digest(d), "how": dist,
                                "build_identity": identity if dist == "built" else None},
                   "front": {"sha256": me.sha_file(top / "bin" / "mentis-server.exe")},
                   "launcher": {"sha256": me.sha_file(top / "bin" / "mentis-launch.exe")},
                   "mars": {"sha256": me.sha_file(top / "bin" / "mars.exe")}},
               "files": me.tree_files(top)}
        (top / "RELEASE.json").write_text(json.dumps(doc), "utf-8")
        index = cfg.index()
        index[rid] = me.sha_file(top / "RELEASE.json")
        me.write_json(cfg.releases / "INDEX.json", index)
        return rid

    def accepted(self, rid, **over):
        """Served and verified in TEST, serving there now, every gate passed."""
        acc = self.cfg.acceptance(rid)
        if not acc["served_in"]:
            acc["served_in"].append({"environment": "test", "role": "test", "verified": True,
                                     "at": "2026-01-01 00:00:00", "python_packages": "pk1"})
        for gate in me.GATES:
            result = over.get(gate, "pass")
            if result:
                acc["records"].append({"gate": gate, "result": result, "by": "t", "evidence": "e",
                                       "at": me.now()})
        self.cfg.save_acceptance(rid, acc)
        self.serves["test"] = rid

    def remote_main(self, remote=None):
        return git(remote or self.mentis_remote, "rev-parse", "refs/heads/main")


class Args:
    def __init__(self, **kw):
        self.environment = None
        self.owner_approved = None
        self.interrupt_runs = False
        self.migrate = False
        self.to = None
        self.main_ahead_ok = None
        self.emergency = None
        self.json = False
        self.__dict__.update(kw)


@pytest.fixture
def w(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def head(w):
    return git(w.mentis, "rev-parse", "HEAD")


# -- 1. the source must be on the REMOTE main -----------------------------------------

def test_a_candidate_whose_source_is_only_on_a_branch_is_refused(w):
    git(w.mentis, "checkout", "-q", "-b", "candidate")
    c = commit(w.mentis, {"mentis/a.py": "x = 2\n"}, "candidate work")
    rid = w.release(c, "r-branch")
    w.accepted(rid)
    with pytest.raises(me.Refused, match=r"is not on origin/main"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.started == [], "nothing was switched"


def test_merged_locally_but_not_pushed_is_still_refused_because_the_remote_is_asked(w):
    c = commit(w.mentis, {"mentis/a.py": "x = 2\n"}, "on local main only")
    assert git(w.mentis, "rev-parse", "refs/heads/main") == c
    # even a local origin/main that claims it is no evidence: the remote itself is asked
    git(w.mentis, "update-ref", "refs/remotes/origin/main", c)
    rid = w.release(c, "r-unpushed")
    w.accepted(rid)
    with pytest.raises(me.Refused, match=r"is not on origin/main"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    life = me.lifecycle(w.cfg, rid)
    assert life["stages"][1]["done"] and not life["stages"][2]["done"], "integrated, not pushed"


def test_a_binary_built_from_a_commit_that_is_not_on_its_remote_main_is_refused(w):
    git(w.mars, "checkout", "-q", "-b", "fix")
    fix = commit(w.mars, {"rust/mars.rs": "fn main() { fixed() }\n"}, "a fix on a branch")
    w.mars_commit = fix
    rid = w.release(head(w), "r-mars-branch", mars=b"mars-fix")
    w.accepted(rid)
    with pytest.raises(me.Refused, match=r"mars \(built from .*is not on origin/main"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))


def test_an_unreachable_remote_is_not_known_and_not_known_refuses(w, monkeypatch):
    rid = w.release(head(w), "r1")
    w.accepted(rid)
    git(w.mentis, "remote", "set-url", "origin", str(w.mentis_remote) + "-gone")
    blockers = me.promotion_blockers(w.cfg, rid)
    assert any("could not be read from the remote" in b for b in blockers)


# -- 2. artifacts must be the commit's ------------------------------------------------

def test_code_that_is_not_the_commits_content_is_refused_even_with_a_consistent_manifest(w):
    def change(code):
        (code / "mentis" / "a.py").write_text("x = 'not what was committed'\n", "utf-8")
        (code / "mentis" / "extra.py").write_text("y = 1\n", "utf-8")
    rid = w.release(head(w), "r-tampered", tamper=change)
    w.accepted(rid)
    assert me.verify_release(w.cfg, rid) == [], "the folder matches its own manifest"
    blockers = me.promotion_blockers(w.cfg, rid)
    assert any("code is not commit" in b and "code/mentis/a.py is not the commit's content" in b
               and "code/mentis/extra.py is not in the commit" in b for b in blockers), blockers


def test_a_binary_nobody_built_from_a_commit_is_refused_whatever_it_is_called(w):
    rid = w.release(head(w), "r-unknown-bin", mars=b"some mars.exe", register=False)
    w.binary("front", b"front-1", w.front_commit, w.mentis)
    w.binary("launcher", b"launch-1", w.front_commit, w.mentis)
    w.accepted(rid)
    with pytest.raises(me.Refused, match="mars .* is not a binary this tool built from a commit"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    life = me.lifecycle(w.cfg, rid)
    assert not life["stages"][2]["done"] and not life["stages"][3]["done"],         "a binary of unknown source is neither on a remote main nor built from a commit"
    # and an emergency exception does not make an unidentified binary acceptable
    with pytest.raises(me.Refused, match="is not a binary this tool built from a commit"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes", emergency="now"))


def test_an_adopted_interface_counts_only_when_an_intact_release_built_the_same_tree(w):
    c = head(w)
    adopted = w.release(c, "r-adopted", dist="adopted")
    w.accepted(adopted)
    assert any("adopted" in b for b in me.promotion_blockers(w.cfg, adopted))
    w.release(c, "r-built", mars=b"mars-other")
    me._REMOTE_SEEN.clear()
    assert not any("adopted" in b for b in me.promotion_blockers(w.cfg, adopted))
    # the interface's source changed: the same bytes are no longer this commit's interface
    c2 = commit(w.mentis, {"apps/fluid-web/src.ts": "ui 2\n"}, "interface changed")
    git(w.mentis, "push", "-q", "origin", "main")
    later = w.release(c2, "r-adopted-later", dist="adopted")
    assert any("adopted" in f["text"] for f in me.contract_findings(w.cfg, later))


def test_a_front_older_than_the_commits_crates_needs_its_recorded_reason(w):
    c2 = commit(w.mentis, {"crates/front.rs": "fn main() { new() }\n"}, "front source changed")
    git(w.mentis, "push", "-q", "origin", "main")
    rid = w.release(c2, "r-old-front")
    assert any("crates/ at the release's commit is different" in f["text"]
               for f in me.contract_findings(w.cfg, rid))


# -- 3. gates -------------------------------------------------------------------------

@pytest.mark.parametrize("gate", ["review", "tests", "browser", "owner"])
@pytest.mark.parametrize("result", ["fail", None])
def test_a_missing_or_failed_gate_refuses(w, gate, result):
    rid = w.release(head(w), "r1")
    w.accepted(rid, **{gate: result})
    with pytest.raises(me.Refused, match=f"{gate} is {'fail' if result else 'missing'}"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.started == []


def test_never_verified_in_test_or_not_serving_there_now_refuses(w):
    rid = w.release(head(w), "r1")
    with pytest.raises(me.Refused, match="never served and verified in a test environment"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    w.accepted(rid)
    w.serves["test"] = "something-else"
    with pytest.raises(me.Refused, match="no test environment is serving"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))


# -- 4. active runs are never interrupted ----------------------------------------------

def test_a_promotion_waits_for_runs_and_cannot_be_told_to_interrupt_them(w):
    w.release(head(w), "before", mars=b"mars-0")
    rid = w.release(head(w), "r1")
    w.accepted(rid)
    w.serves["prod"] = "before"
    w.runs["prod"] = 2
    with pytest.raises(me.Refused, match="2 run.s. are in flight.*Nothing was stopped: wait"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    with pytest.raises(me.Refused, match="a promotion never interrupts runs"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes", interrupt_runs=True))
    with pytest.raises(me.Refused, match="2 run.s. are in flight"):
        me.cmd_production(w.cfg, Args(release=rid, owner_approved="yes"))
    w.runs["prod"] = None
    with pytest.raises(me.Refused, match="could not read whether runs are in flight"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.started == [] and w.serves["prod"] == "before"


def test_test_interrupts_runs_only_with_explicit_words(w, capsys):
    rid = w.release(head(w), "r1")
    w.serves["test"] = None
    w.runs["test"] = 1
    with pytest.raises(me.Refused, match="1 run.s. are in flight"):
        me.cmd_deploy(w.cfg, Args(environment="test", release=rid))
    with pytest.raises(me.Refused, match="needs explicit authorization"):
        me.cmd_deploy(w.cfg, Args(environment="test", release=rid, interrupt_runs=True))
    assert w.started == []
    me.cmd_deploy(w.cfg, Args(environment="test", release=rid, interrupt_runs=True,
                              owner_approved="the owner: end that run"))
    cur = w.cfg.serving("test")["current"]
    assert cur["runs_interrupted"] is True and cur["runs_in_flight"] == 1
    assert cur["approved"] == "the owner: end that run"


# -- 5 and 7. the full lifecycle, and the way back -------------------------------------

def test_the_full_lifecycle_integrates_pushes_promotes_and_confirms(w, capsys):
    """A candidate on a branch, tested from that branch: `production` puts exactly that commit
    on the remote main (fast-forward), promotes, and reports all eight conditions as holding."""
    old = w.release(head(w), "r-old")
    w.accepted(old)
    assert me.cmd_production(w.cfg, Args(release=old, owner_approved="deploy r-old")) == 0
    git(w.mentis, "checkout", "-q", "-b", "candidate")
    c = commit(w.mentis, {"mentis/a.py": "x = 2\n"}, "candidate work")
    assert w.remote_main() != c
    rid = w.release(c, "r-new")
    # TEST takes it from the branch: nothing about main is asked of a TEST deploy
    me.cmd_deploy(w.cfg, Args(environment="test", release=rid))
    w.accepted(rid)
    life = me.lifecycle(w.cfg, rid)
    assert life["incomplete"] == [2, 3, 7, 8], "tested on TEST; not integrated, pushed or promoted"
    capsys.readouterr()
    assert me.cmd_production(w.cfg, Args(release=rid, owner_approved="Deploy to DAY-TO-DAY")) == 0
    said = capsys.readouterr().out
    assert "COMPLETE: all eight conditions hold" in said
    assert w.remote_main() == c, "exactly the tested commit is now the remote main"
    assert git(w.mentis, "rev-parse", "refs/heads/main") == c, "and the local main, checked out nowhere, followed"
    assert w.serves["prod"] == rid
    cur = w.cfg.serving("prod")["current"]
    assert cur["approved"] == "Deploy to DAY-TO-DAY" and cur["runs_interrupted"] is False
    life = me.lifecycle(w.cfg, rid)
    stages = [e["stage"] for e in life["events"]]
    assert life["complete"] and stages[-3:] == ["checks before promotion", "promote", "confirm"]
    pushes = [e["detail"] for e in life["events"] if e["stage"] == "integrate and push"]
    assert [d["commit"] for d in pushes if d.get("pushed_to")] == [c], "one push, of exactly that commit"
    assert me.cmd_lifecycle(w.cfg, Args(release=rid)) == 0
    # the way back is the release production ran before, with the owner's words, and Git is untouched
    assert cur["previous"] == old
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_rollback(w.cfg, Args(environment="prod"))
    me.cmd_rollback(w.cfg, Args(environment="prod", owner_approved="go back"))
    assert w.serves["prod"] == old and w.remote_main() == c
    assert w.cfg.serving("prod")["current"]["why"] == f"rolled back from {rid}"
    assert me.lifecycle(w.cfg, rid)["incomplete"] == [7, 8], "and the rolled-back release says so"


def test_integration_pushes_nothing_for_a_release_that_could_not_be_promoted(w):
    git(w.mentis, "checkout", "-q", "-b", "candidate")
    c = commit(w.mentis, {"mentis/a.py": "x = 2\n"}, "candidate work")
    before = w.remote_main()
    bad = w.release(c, "r-bad", tamper=lambda code: (code / "mentis" / "a.py").write_text("x = 3\n", "utf-8"))
    w.accepted(bad)
    with pytest.raises(me.Refused, match="code is not commit"):
        me.cmd_production(w.cfg, Args(release=bad, owner_approved="yes"))
    assert w.remote_main() == before and w.started == []
    # nor for one a gate has not passed, nor while production has work in flight
    good = w.release(c, "r-good", mars=b"mars-g")
    w.accepted(good, tests="fail")
    with pytest.raises(me.Refused, match="nothing was pushed: tests is fail"):
        me.cmd_production(w.cfg, Args(release=good, owner_approved="yes"))
    w.accepted(good)
    w.release(head(w), "running", mars=b"mars-r")
    w.serves["prod"], w.runs["prod"] = "running", 1
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was pushed or stopped"):
        me.cmd_production(w.cfg, Args(release=good, owner_approved="yes"))
    assert w.remote_main() == before and w.started == []
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_production(w.cfg, Args(release=bad))


# -- 6. main advancing ------------------------------------------------------------------

def test_main_advancing_after_verification_is_said_and_needs_a_stated_reason(w, capsys):
    c = head(w)
    rid = w.release(c, "r1")
    w.accepted(rid)
    newer = commit(w.mentis, {"mentis/b.py": "later = 1\n"}, "someone else's later work")
    git(w.mentis, "push", "-q", "origin", "main")
    with pytest.raises(me.Refused, match=r"origin/main has 1 commit\(s\) this release does not .*someone else's later work"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.started == []
    assert me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes",
                                      main_ahead_ok="the later commit is docs only")) == 0
    assert w.cfg.serving("prod")["current"]["main_ahead_ok"] == "the later commit is docs only"
    assert w.remote_main() == newer, "main is not moved back, and the later work is not pulled in"
    assert (w.cfg.release_dir(rid) / "code" / "mentis" / "b.py").exists() is False
    assert "this release does not" in capsys.readouterr().out, "the report keeps saying main is ahead"


def test_a_candidate_that_main_has_moved_past_is_never_merged_here(w):
    git(w.mentis, "checkout", "-q", "-b", "candidate")
    c = commit(w.mentis, {"mentis/a.py": "x = 2\n"}, "candidate work")
    git(w.mentis, "checkout", "-q", "main")
    other = commit(w.mentis, {"mentis/b.py": "other = 1\n"}, "unrelated work lands on main")
    git(w.mentis, "push", "-q", "origin", "main")
    rid = w.release(c, "r-diverged")
    w.accepted(rid)
    with pytest.raises(me.Refused, match="main has advanced.*Nothing was pushed.*verify THAT on TEST"):
        me.cmd_production(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.remote_main() == other and w.started == []
    events = me.lifecycle(w.cfg, rid)["events"]
    assert events[-1]["result"] == "refused, nothing was switched"


# -- 8. an incomplete deployment is reported as incomplete --------------------------------

def test_an_emergency_exception_is_explicit_recorded_and_incomplete_until_main_has_it(w, capsys):
    git(w.mentis, "checkout", "-q", "-b", "hotfix")
    c = commit(w.mentis, {"mentis/a.py": "x = 'hotfix'\n"}, "hotfix")
    rid = w.release(c, "r-hotfix")
    w.accepted(rid)
    with pytest.raises(me.Refused, match="is not on origin/main"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    # it waives the source being on main, and nothing else
    w.accepted(rid, review="fail")
    with pytest.raises(me.Refused, match="review is fail"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes", emergency="production is down"))
    w.accepted(rid)
    capsys.readouterr()
    with pytest.raises(me.Failed, match=r"now serves r-hotfix, but the deployment is NOT complete: conditions \[2, 3\]"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes", emergency="production is down"))
    said = capsys.readouterr().out
    assert "INCOMPLETE: 2 of 8 conditions do not hold (2, 3)" in said
    assert "EMERGENCY EXCEPTION IN FORCE: main reconciliation is still owed: production is down" in said
    assert w.serves["prod"] == rid, "it IS serving; what it is not is complete"
    cur = w.cfg.serving("prod")["current"]
    assert cur["emergency"]["words"] == "production is down" and cur["emergency"]["waived"]
    assert me.cmd_lifecycle(w.cfg, Args(release=rid)) == 3
    # nothing ordinary is promoted over the debt
    git(w.mentis, "checkout", "-q", "main")
    nxt = w.release(git(w.mentis, "rev-parse", "main"), "r-next", mars=b"mars-2")
    w.accepted(nxt)
    with pytest.raises(me.Refused, match="under an emergency exception whose source is still not on its remote main"):
        me.cmd_promote(w.cfg, Args(release=nxt, owner_approved="yes"))
    # reconciled: the hotfix reaches the remote main, and the same release is then complete
    git(w.mentis, "merge", "-q", "--ff-only", "hotfix")
    git(w.mentis, "push", "-q", "origin", "main")
    me._REMOTE_SEEN.clear()
    w.serves["test"] = rid
    life = me.lifecycle(w.cfg, rid)
    assert life["complete"] and life["emergency"]["reconciled"] is True


def test_status_says_when_what_production_runs_is_not_a_complete_deployment(w, capsys):
    rid = w.release(head(w), "r1")
    w.accepted(rid)
    w.serves["prod"] = rid                       # running, but nothing records a promotion
    me.cmd_status(w.cfg, Args())
    said = capsys.readouterr().out
    assert "release lifecycle: INCOMPLETE, conditions 7 do not hold" in said


# -- binaries are identified by the commit they were built from ---------------------------

def test_build_binaries_archives_one_commit_and_records_what_each_file_is(w, monkeypatch, capsys):
    built = {}
    real_run = me.run

    def fake(args, cwd=None, env=None, check=True, timeout=None):
        args = [str(a) for a in args]
        if args[0] == "cargo" and args[1] == "build":
            assert args[2:] == ["--release", "--locked", "-p", "mars"]
            assert (pathlib.Path(cwd) / "mars.rs").read_text() == "fn main() {}\n", "the commit's own source"
            out = pathlib.Path(env["CARGO_TARGET_DIR"]) / "release"
            out.mkdir(parents=True)
            (out / "mars.exe").write_bytes(b"built mars")
            built["cwd"] = cwd
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "cargo":
            return subprocess.CompletedProcess(args, 0, "cargo 1.0", "")
        return real_run(args, cwd=cwd, env=env, check=check, timeout=timeout)
    monkeypatch.setattr(me, "run", fake)
    monkeypatch.setattr(me.shutil, "which", lambda name: "cargo")
    # uncommitted work in the checkout is not what gets built
    (w.mars / "rust" / "mars.rs").write_text("fn main() { uncommitted() }\n", "utf-8")
    assert me.cmd_build_binaries(w.cfg, Args(component="mars", commit="main")) == 0
    sha = me.hashlib.sha256(b"built mars").hexdigest()
    entry = me.binaries(w.cfg)[sha]
    assert entry["component"] == "mars" and entry["commit"] == w.mars_commit
    assert "git archive" in entry["how"] and not pathlib.Path(built["cwd"]).exists(), "the build tree is removed"
    with pytest.raises(me.Refused, match="already exists"):
        me.cmd_build_binaries(w.cfg, Args(component="mars", commit="main"))
    with pytest.raises(me.Refused, match="owner-approved"):
        me.cmd_attest_binary(w.cfg, Args(file=str(w.mars / "rust" / "mars.rs"), component="mars", commit="main"))
    me.cmd_attest_binary(w.cfg, Args(file=str(w.mars / "rust" / "mars.rs"), component="mars", commit="main",
                                     owner_approved="this is the mars DAY-TO-DAY runs"))
    assert any(e.get("attested") for e in me.binaries(w.cfg).values()), "kept as an attestation, said so"


# -- corrections from independent review ------------------------------------------------

def test_mars_main_advancing_after_verification_is_said_too(w):
    rid = w.release(head(w), "r1")
    w.accepted(rid)
    commit(w.mars, {"rust/mars.rs": "fn main() { later() }\n"}, "later MARS work")
    git(w.mars, "push", "-q", "origin", "main")
    with pytest.raises(me.Refused, match=r"mars: origin/main has 1 commit\(s\) this release does not .*later MARS work"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.started == []
    assert me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes",
                                      main_ahead_ok="the later MARS commit is not needed by this release")) == 0


def test_two_repositories_are_checked_before_either_is_pushed_and_a_partial_push_is_said(w, monkeypatch):
    git(w.mentis, "checkout", "-q", "-b", "candidate")
    c = commit(w.mentis, {"mentis/a.py": "x = 2\n"}, "candidate work")
    git(w.mars, "checkout", "-q", "-b", "fix")
    fix = commit(w.mars, {"rust/mars.rs": "fn main() { fix() }\n"}, "MARS fix on a branch")
    git(w.mars, "checkout", "-q", "main")
    other = commit(w.mars, {"rust/other.rs": "// unrelated\n"}, "MARS main moves on")
    git(w.mars, "push", "-q", "origin", "main")
    w.mars_commit = fix
    rid = w.release(c, "r-two", mars=b"mars-fix")
    w.accepted(rid)
    before = w.remote_main()
    with pytest.raises(me.Refused, match="main has advanced"):
        me.cmd_production(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.remote_main() == before, "Mentis was not pushed, because MARS could not be"
    assert w.remote_main(w.mars_remote) == other
    # a push that fails after an earlier one succeeded is reported as exactly that
    real = me.integrate

    def second_fails(cfg, name, commit_):
        if name == "mars":
            raise me.Refused("the push to mars was refused, nothing changed: remote said no")
        return real(cfg, name, commit_)
    # (a MARS fix that COULD be fast-forwarded, so the check before pushing passes)
    git(w.mars, "checkout", "-q", "-b", "fix2", "main")
    w.mars_commit = commit(w.mars, {"rust/mars.rs": "fn main() { fix2() }\n"}, "MARS fix on current main")
    rid = w.release(c, "r-two-b", mars=b"mars-fix2")
    w.accepted(rid)
    monkeypatch.setattr(me, "integrate", second_fails)
    with pytest.raises(me.Failed, match=r"INTEGRATION IS PARTIAL: .* WAS pushed to origin/main.*then mars failed.*Nothing was switched"):
        me.cmd_production(w.cfg, Args(release=rid, owner_approved="yes"))
    events = me.lifecycle(w.cfg, rid)["events"]
    assert [e["result"] for e in events if e["stage"] == "integrate and push"][-2:] == ["done", "PARTIAL"]
    assert w.remote_main() == c and w.started == []


def test_a_gate_is_not_recorded_on_nobodys_word_about_nothing(w):
    rid = w.release(head(w), "r1")
    w.accepted(rid, tests=None)
    for by, evidence in (("", "pytest: 40 passed"), ("codex", ""), ("  ", "   "), ("codex", "ok")):
        with pytest.raises(me.Refused, match="Neither can be blank"):
            me.cmd_record(w.cfg, Args(release=rid, gate="tests", result="pass", by=by, evidence=evidence))
    assert me.gate_state(w.cfg.acceptance(rid))["tests"] == "missing"
    me.cmd_record(w.cfg, Args(release=rid, gate="tests", result="pass", by="codex",
                              evidence="pytest tests/: 40 passed, log in evidence/run.log"))
    assert me.gate_state(w.cfg.acceptance(rid))["tests"] == "pass"


def test_a_run_that_starts_while_the_switch_is_prepared_stops_it(w, monkeypatch):
    w.release(head(w), "before", mars=b"mars-0")
    rid = w.release(head(w), "r1")
    w.accepted(rid)
    w.serves["prod"] = "before"
    asked = []

    def runs(env):
        asked.append(env["name"])
        return 0 if len(asked) < 2 else 1          # idle when first asked, busy at the last moment
    monkeypatch.setattr(me, "_open_runs", runs)
    with pytest.raises(me.Refused, match="1 run.s. started while this was being prepared.*Nothing was stopped"):
        me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes"))
    assert w.started == [] and w.serves["prod"] == "before"


def test_records_made_before_the_contract_are_incomplete_not_a_crash(w, capsys):
    """An older release: no tests gate, a promotion that recorded nothing about runs, binaries
    nobody registered. It reports as incomplete, and production can still be rolled back to it."""
    old = w.release(head(w), "r-old", register=False)
    new = w.release(head(w), "r-new", mars=b"mars-2")
    acc = w.cfg.acceptance(old)
    acc["served_in"].append({"environment": "test", "role": "test", "verified": True,
                             "at": "2026-01-01 00:00:00", "python_packages": "pk1"})
    acc["records"] = [{"gate": g, "result": "pass", "by": "t", "evidence": "e", "at": "2026-01-02 00:00:00"}
                      for g in ("review", "browser", "owner")]
    w.cfg.save_acceptance(old, acc)
    entry = {"release": old, "since": "2026-01-03 00:00:00", "why": "promoted from TEST", "approved": "yes",
             "previous": None, "migrated": False, "gap_seconds": 1.0}
    me.write_json(w.cfg.state("prod") / "serving.json",
                  {"environment": "prod", "current": entry, "history": [entry]})
    w.serves["prod"] = old
    life = me.lifecycle(w.cfg, old)
    assert life["incomplete"] == [2, 3, 4, 5, 7]
    me.cmd_status(w.cfg, Args())
    assert "INCOMPLETE, conditions 2, 3, 4, 5, 7" in capsys.readouterr().out
    w.accepted(new)
    assert me.cmd_production(w.cfg, Args(release=new, owner_approved="deploy")) == 0
    me.cmd_rollback(w.cfg, Args(environment="prod", owner_approved="go back"))
    assert w.serves["prod"] == old, "recovery to a release production already ran is still possible"
