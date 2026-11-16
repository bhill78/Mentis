"""Two environments, immutable releases, one way to say what is served.

    python tools/env/mentis_env.py status                       what each environment ACTUALLY serves
    python tools/env/mentis_env.py build --commit C --describe "plain words"
    python tools/env/mentis_env.py releases | verify ID
    python tools/env/mentis_env.py deploy test ID                candidate -> TEST
    python tools/env/mentis_env.py record ID review|browser|owner --result pass|fail --by WHO --evidence TEXT
    python tools/env/mentis_env.py promote ID --owner-approved "the owner's words"     TEST-verified -> DAY-TO-DAY
    python tools/env/mentis_env.py rollback ENV [--owner-approved "..."]
    python tools/env/mentis_env.py start ENV | stop ENV
    python tools/env/mentis_env.py snapshot --owner-authorized "the owner's words"     production data -> TEST, once

    Build -> TEST -> Accept -> DAY-TO-DAY.

WHAT A RELEASE IS. One folder, `<root>/releases/<id>/`, never changed after it is made:

    code/                     `git archive` of one commit; `code/BUILD.json` makes the server
                              itself report the release (mentis/web/identity.py)
    code/apps/fluid-web/dist  the interface, built from that commit (or adopted bytes, said so)
    bin/                      mentis-launch.exe, mentis-server.exe, mars.exe, with provenance
    route-table.json
    RELEASE.json              the identity: commit, each component's digest, Brain schema, every
                              file's sha256

Promotion starts DAY-TO-DAY from the SAME folder TEST ran: nothing is rebuilt. Rollback starts
the environment's previous release folder: nothing is reconstructed and Git is not touched.

WHAT IS SERVED IS OBSERVED, NOT REMEMBERED. `status` asks each running server what it is
(`/api/server`, `/build-identity.json`, the page it serves), hashes what its processes run
from, and names the release whose components match BY CONTENT. A checkout's HEAD is never
the answer. `serving.json` only records what a deploy verified; status says when the two
disagree.

DATA IS NOT SOFTWARE. Nothing here but `snapshot` writes a Brain, and `snapshot` refuses when
TEST already has one: refreshing TEST's data is the owner's separate decision.

PRODUCTION IS GATED. Any change to an environment whose role is `production` needs
`--owner-approved`, and `promote` also needs the release to have been served and verified in
a `test` environment with review, browser and owner acceptance recorded as passed.

Exit: 0 done, 2 refused (nothing changed), 1 failed (said what state it left).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
GATES = ("review", "browser", "owner")
SCHEMA = ("import json,sys\nsys.path.insert(0, sys.argv[1])\n"
          "from mentis.spine import migrations as m\nms = m.migrations()\n"
          "print(json.dumps({'schema_target': m.target(), 'migrations': [x.id for x in ms],"
          "'min_reader_after': max(x.min_reader for x in ms)}))\n")


class Refused(Exception):
    """Nothing was changed."""


class Failed(Exception):
    """Something was changed and did not finish; the words say what is left."""


# -- small things -------------------------------------------------------------------

def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_files(top: pathlib.Path, only=None) -> dict:
    """{posix relative path: sha256} of every file under top (never __pycache__)."""
    out = {}
    for p in sorted(top.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            rel = p.relative_to(top).as_posix()
            if only is None or only(rel):
                out[rel] = sha_file(p)
    return out


def digest_of(files: dict) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(f"{rel}\0{files[rel]}\n".encode("utf-8"))
    return h.hexdigest()


def backend_digest(code: pathlib.Path) -> str:
    """The server's own code by content: mentis/**/*.py, identity.py's CODE_SCOPE."""
    return digest_of(tree_files(code / "mentis", only=lambda r: r.endswith(".py")))


def dist_digest(dist: pathlib.Path) -> str:
    return digest_of(tree_files(dist))


def read_json(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text("utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json(path, doc) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), "utf-8")
    os.replace(tmp, path)


def run(args, cwd=None, env=None, check=True, timeout=None) -> subprocess.CompletedProcess:
    r = subprocess.run([str(a) for a in args], cwd=cwd, env=env, text=True, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if check and r.returncode != 0:
        raise Failed(f"{' '.join(str(a) for a in args[:4])} ... exit {r.returncode}: "
                     f"{(r.stderr or r.stdout).strip()[-1500:]}")
    return r


def ps(script: str, check=True) -> str:
    r = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], check=check)
    return r.stdout.strip()


def http(url: str, timeout=15.0) -> bytes:
    req = urllib.request.Request(url, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_json(url: str, timeout=15.0):
    return json.loads(http(url, timeout).decode("utf-8"))


def port_owner(port: int):
    out = ps(f"(Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction "
             f"SilentlyContinue | Select-Object -First 1).OwningProcess", check=False)
    return int(out) if out.isdigit() else None


def process_facts(pid: int) -> dict | None:
    out = ps(f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}'; if ($p) {{ "
             f"$g = Get-Process -Id {int(pid)}; @{{ pid = $p.ProcessId; parent = $p.ParentProcessId; "
             f"exe = $p.ExecutablePath; start_time = [string]$g.StartTime.ToFileTimeUtc() }} | "
             f"ConvertTo-Json -Compress }}", check=False)
    return json.loads(out) if out.startswith("{") else None


def children(pid: int) -> list[dict]:
    out = ps(f"@(Get-CimInstance Win32_Process -Filter 'ParentProcessId={int(pid)}' | ForEach-Object "
             f"{{ @{{ pid = $_.ProcessId; exe = $_.ExecutablePath; name = $_.Name }} }}) | "
             f"ConvertTo-Json -Compress", check=False)
    if not out:
        return []
    got = json.loads(out)
    return got if isinstance(got, list) else [got]


# -- configuration ------------------------------------------------------------------

class Config:
    def __init__(self, path: pathlib.Path):
        doc = read_json(path)
        if not doc or doc.get("format") != 1:
            raise Refused(f"{path} is not an environments file this tool reads")
        self.path = path
        self.root = pathlib.Path(doc["root"])
        self.python = doc["python"]
        self.mars_local_python = doc.get("mars_local_python")
        self.envs = doc["environments"]
        self.repo = pathlib.Path(doc.get("repo") or REPO)
        #: a rehearsal's own state beside the real releases: same artifacts, separate records
        self._releases = pathlib.Path(doc["releases"]) if doc.get("releases") else None

    def env(self, name: str) -> dict:
        if name not in self.envs:
            raise Refused(f"no environment {name!r}: {', '.join(self.envs)}")
        return {**self.envs[name], "name": name}

    def state(self, name: str) -> pathlib.Path:
        return self.root / name

    @property
    def releases(self) -> pathlib.Path:
        return self._releases or self.root / "releases"

    def release_dir(self, rid: str) -> pathlib.Path:
        return self.releases / rid

    def release(self, rid: str) -> dict:
        doc = read_json(self.release_dir(rid) / "RELEASE.json")
        if not doc:
            raise Refused(f"no release {rid!r} under {self.releases}")
        return doc

    def all_releases(self) -> list[dict]:
        out = []
        if self.releases.is_dir():
            for d in sorted(self.releases.iterdir()):
                doc = read_json(d / "RELEASE.json")
                if doc:
                    out.append(doc)
        return sorted(out, key=lambda r: r["created_at"])

    def serving(self, name: str) -> dict:
        return read_json(self.state(name) / "serving.json", {"environment": name, "current": None,
                                                              "history": []})

    def acceptance(self, rid: str) -> dict:
        return read_json(self.root / "acceptance" / f"{rid}.json",
                         {"release": rid, "served_in": [], "records": []})

    def save_acceptance(self, rid: str, doc: dict) -> None:
        write_json(self.root / "acceptance" / f"{rid}.json", doc)


def gate_state(acc: dict) -> dict:
    """The LATEST record of each gate decides it; none recorded is `missing`, never passed."""
    out = {}
    for gate in GATES:
        recs = [r for r in acc.get("records", []) if r["gate"] == gate]
        out[gate] = recs[-1]["result"] if recs else "missing"
    return out


# -- build --------------------------------------------------------------------------

def _git(cfg: Config, *args, check=True) -> str:
    return run(["git", "-C", cfg.repo, *args], check=check).stdout.strip()


def _make_readonly(top: pathlib.Path) -> None:
    for p in top.rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IREAD)


def _rm_tree(top: pathlib.Path) -> None:
    def on_error(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(top, onerror=on_error)


def cmd_build(cfg: Config, a) -> int:
    commit = _git(cfg, "rev-parse", f"{a.commit}^{{commit}}")
    subject = _git(cfg, "log", "-1", "--format=%s", commit)
    commit_time = _git(cfg, "log", "-1", "--format=%ct", commit)
    if not a.describe.strip():
        raise Refused("--describe says in plain words what this release contains; it is required")
    prior = cfg.all_releases()
    front_from = pathlib.Path(a.front_from) if a.front_from else (
        cfg.release_dir(prior[-1]["id"]) / "bin" if prior else None)
    mars_from = pathlib.Path(a.mars_from) if a.mars_from else (
        cfg.release_dir(prior[-1]["id"]) / "bin" / "mars.exe" if prior else None)
    if not front_from or not mars_from:
        raise Refused("the first release names its binaries: --front-from DIR --mars-from FILE")
    for need in (front_from / "mentis-launch.exe", front_from / "mentis-server.exe", mars_from):
        if not need.is_file():
            raise Refused(f"{need} does not exist")

    cfg.releases.mkdir(parents=True, exist_ok=True)
    stage = cfg.releases / f".staging-{os.getpid()}"
    if stage.exists():
        _rm_tree(stage)
    code = stage / "code"
    code.mkdir(parents=True)
    try:
        # -- code: exactly the commit, no working tree involved
        tar = subprocess.run(["git", "-C", str(cfg.repo), "archive", "--format=tar", commit],
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(code, filter="data")

        # -- interface
        dist = code / "apps" / "fluid-web" / "dist"
        if a.dist_from:
            if not (a.dist_reason or "").strip():
                raise Refused("--dist-from adopts bytes this tool did not build: --dist-reason says why")
            shutil.copytree(a.dist_from, dist)
            dist_how = {"how": "adopted", "from": str(a.dist_from), "reason": a.dist_reason}
        else:
            work = cfg.root / "build" / commit[:12]
            if work.exists():
                run(["git", "-C", cfg.repo, "worktree", "remove", "--force", work], check=False)
            work.parent.mkdir(parents=True, exist_ok=True)
            run(["git", "-C", cfg.repo, "worktree", "add", "--detach", work, commit])
            try:
                web = work / "apps" / "fluid-web"
                npm = shutil.which("npm.cmd") or shutil.which("npm")
                env = {**os.environ, "SOURCE_DATE_EPOCH": commit_time}
                run([npm, "ci", "--no-audit", "--no-fund"], cwd=web, env=env, timeout=1800)
                run([npm, "run", "build"], cwd=web, env=env, timeout=1800)
                shutil.copytree(web / "dist", dist)
            finally:
                run(["git", "-C", cfg.repo, "worktree", "remove", "--force", work], check=False)
            dist_how = {"how": "built", "command": "npm ci && npm run build",
                        "node": run(["node", "--version"]).stdout.strip()}
        if not (dist / "index.html").is_file():
            raise Failed("the interface build holds no index.html")

        # -- binaries: reused bytes, with where they came from
        bindir = stage / "bin"
        bindir.mkdir()
        for name in ("mentis-launch.exe", "mentis-server.exe"):
            shutil.copy2(front_from / name, bindir / name)
        shutil.copy2(mars_from, bindir / "mars.exe")
        front_prov = (read_json(front_from / "PROVENANCE.json")
                      or read_json(front_from / "FRONT-PROVENANCE.json") or {})
        mars_prov = (read_json(mars_from.parent / "PROVENANCE.json")
                     or read_json(mars_from.parent / "MARS-PROVENANCE.json") or {})
        if (mars_from.parent / "FRONT-PROVENANCE.json").is_file() and not read_json(
                mars_from.parent / "PROVENANCE.json"):
            mars_prov = read_json(mars_from.parent / "MARS-PROVENANCE.json") or {}
        write_json(bindir / "FRONT-PROVENANCE.json", front_prov)
        write_json(bindir / "MARS-PROVENANCE.json", mars_prov)
        # the front is built from crates/: it is THIS commit's front only if crates/ is the same tree
        front_src = front_prov.get("source_commit")
        same = None
        if front_src:
            t1 = _git(cfg, "rev-parse", f"{front_src}:crates", check=False)
            t2 = _git(cfg, "rev-parse", f"{commit}:crates", check=False)
            same = bool(t1) and t1 == t2
        if same is not True and not (a.front_differs_ok or "").strip():
            raise Refused(
                f"the reused front was built from {front_src or 'an unrecorded commit'}, and crates/ at "
                f"{commit[:12]} is {'different' if same is False else 'not comparable'}: build the front "
                f"from this commit and pass --front-from, or say why the older front is right with "
                f"--front-differs-ok")

        shutil.copy2(code / "tools" / "release_modernize" / "route-table.json", stage / "route-table.json")

        schema = json.loads(run([cfg.python, "-B", "-X", "utf8", "-c", SCHEMA, code]).stdout)
        components = {
            "backend": {"commit": commit, "digest": backend_digest(code), **schema},
            "frontend": {"commit": commit, "digest": dist_digest(dist), **dist_how,
                         "build_identity": read_json(dist / "build-identity.json"),
                         "index_sha256": sha_file(dist / "index.html")},
            "front": {"sha256": sha_file(bindir / "mentis-server.exe"), "source_commit": front_src,
                      "crates_same_as_commit": same, "differs_ok": a.front_differs_ok or None},
            "launcher": {"sha256": sha_file(bindir / "mentis-launch.exe")},
            "mars": {"sha256": sha_file(bindir / "mars.exe"), "commit": mars_prov.get("commit"),
                     "version": mars_prov.get("version")},
            "route_table": {"sha256": sha_file(stage / "route-table.json")},
        }
        key = "|".join(str(components[c].get("digest") or components[c].get("sha256"))
                       for c in sorted(components))
        rid = (f"{time.strftime('%Y%m%d', time.localtime(int(commit_time)))}-{commit[:7]}-"
               f"{hashlib.sha256(key.encode()).hexdigest()[:8]}")
        if cfg.release_dir(rid).exists():
            raise Refused(f"release {rid} already exists: the same commit and the same components")
        write_json(code / "BUILD.json", {"version": rid, "release": rid, "commit": commit,
                                         "built_at": now(), **schema})
        run([cfg.python, "-m", "compileall", "-q", code / "mentis"], check=False)
        doc = {
            "format": 1, "id": rid, "created_at": now(), "description": a.describe.strip(),
            "source": {"repository": str(cfg.repo), "commit": commit, "subject": subject,
                       "commit_time": int(commit_time)},
            "components": components,
            "runtime": {"python": cfg.python, "note": "the interpreter and its installed packages are "
                        "shared by every environment and are not part of the release"},
            "migration": {"schema_target": schema["schema_target"],
                          "min_reader_after": schema["min_reader_after"],
                          "note": "deploy runs `mentis.migrate --plan` against the environment's Brain "
                                  "and says what it would apply before applying anything"},
            "files": tree_files(stage),
        }
        write_json(stage / "RELEASE.json", doc)
        _make_readonly(stage)
        os.rename(stage, cfg.release_dir(rid))
    except BaseException:
        if stage.exists():
            _rm_tree(stage)
        raise
    print(json.dumps({"built": rid, "path": str(cfg.release_dir(rid)), "commit": commit,
                      "description": doc["description"],
                      "frontend": components["frontend"]["digest"][:12],
                      "backend": components["backend"]["digest"][:12]}, indent=1))
    return 0


def verify_release(cfg: Config, rid: str) -> list[str]:
    doc = cfg.release(rid)
    top = cfg.release_dir(rid)
    have = tree_files(top)
    have.pop("RELEASE.json", None)
    problems = []
    for rel, want in doc["files"].items():
        if have.get(rel) != want:
            problems.append(f"{rel} is {'missing' if rel not in have else 'changed'}")
    for rel in have:
        if rel not in doc["files"]:
            problems.append(f"{rel} was added")
    return problems


def cmd_verify(cfg: Config, a) -> int:
    problems = verify_release(cfg, a.release)
    print(json.dumps({"release": a.release, "intact": not problems, "problems": problems[:20]}, indent=1))
    return 0 if not problems else 1


def cmd_releases(cfg: Config, a) -> int:
    for r in cfg.all_releases():
        gates = gate_state(cfg.acceptance(r["id"]))
        print(f"{r['id']}  {r['created_at']}  {r['description']}")
        print(f"    commit {r['source']['commit'][:12]}  schema {r['migration']['schema_target']}  "
              + "  ".join(f"{g}: {gates[g]}" for g in GATES))
    return 0


# -- observing an environment ---------------------------------------------------------

def observe(cfg: Config, name: str) -> dict:
    """What `name` is actually serving now, component by component, by content."""
    env = cfg.env(name)
    url = f"http://127.0.0.1:{env['port']}"
    out = {"environment": name, "label": env["label"], "role": env["role"], "url": url,
           "up": False, "components": {}, "notes": []}
    launch = read_json(pathlib.Path(env["run_dir"]) / "launch.json")
    try:
        server = http_json(url + "/api/server")
    except Exception as exc:                                    # noqa: BLE001
        out["why_down"] = f"{type(exc).__name__}: {exc}"
        return out
    out["up"] = True
    out["brain"] = server.get("corpus")
    out["reports_release"] = (server.get("release") or {}).get("release")
    if os.path.normcase(os.path.abspath(str(server.get("corpus")))) != os.path.normcase(
            os.path.abspath(env["brain"])):
        out["notes"].append(f"WRONG BRAIN: the server at {url} holds {server.get('corpus')}, and "
                            f"{name} is {env['brain']}")
    code_root = pathlib.Path((server.get("release") or {}).get("path")
                             or (server.get("code") or {}).get("root") or "")
    comp = out["components"]
    # backend: the code root the process says it runs from, by content, and whether it changed
    # under the process since it started
    now_tree = server.get("checkout_now") or {}
    comp["backend"] = {
        "from": str(code_root), "digest": backend_digest(code_root) if code_root.is_dir() else None,
        "commit_at_start": (server.get("code") or {}).get("commit"),
        "changed_since_start": now_tree.get("code_changed_since_start"),
        "pid": (server.get("process") or {}).get("pid"),
    }
    if now_tree.get("code_changed_since_start"):
        out["notes"].append("the backend's code on disk changed after the process started: the "
                            "process is not exactly what is on disk")
    # frontend: what the front serves from, by content, and the page it actually answers with
    dist_at = ((launch or {}).get("started_with") or {}).get("dist")
    dist = pathlib.Path(dist_at) if dist_at else HERE / "no-dist-known"
    served_index = None
    try:
        served_index = hashlib.sha256(http(url + "/quiet2")).hexdigest()
    except Exception:                                           # noqa: BLE001
        pass
    comp["frontend"] = {"from": str(dist), "digest": dist_digest(dist) if dist.is_dir() else None,
                        "disk_index_sha256": sha_file(dist / "index.html") if (dist / "index.html").is_file() else None,
                        "served_index_sha256": served_index}
    try:
        comp["frontend"]["build_identity"] = http_json(url + "/build-identity.json")
    except Exception:                                           # noqa: BLE001
        comp["frontend"]["build_identity"] = None
    if served_index and comp["frontend"]["disk_index_sha256"] and \
            served_index != comp["frontend"]["disk_index_sha256"]:
        out["notes"].append("the page served is not the index.html in the dist folder the front was started with")
    # the processes: the front and MARS by the executables they run
    front = (launch or {}).get("front") or {}
    front_alive = process_facts(front["pid"]) if front.get("pid") else None
    if front_alive and str(front_alive.get("start_time")) == str(front.get("start_time")):
        comp["front"] = {"from": front_alive["exe"], "sha256": sha_file(front_alive["exe"]), "pid": front["pid"]}
        owner = port_owner(env["port"])
        if owner != front["pid"]:
            out["notes"].append(f"port {env['port']} is held by pid {owner}, not the launcher's front {front['pid']}")
    else:
        comp["front"] = {"from": None, "sha256": None}
        out["notes"].append("launch.json names no living front process")
    started = (launch or {}).get("started_with") or {}
    table = started.get("route_table")
    comp["route_table"] = {"from": table, "sha256": sha_file(table) if table and os.path.isfile(table) else None}
    mars = None
    for kid in children(comp["backend"]["pid"] or 0):
        if "mars" in (kid.get("name") or "").lower() and kid.get("exe"):
            mars = kid
    comp["mars"] = ({"from": mars["exe"], "sha256": sha_file(mars["exe"]), "pid": mars["pid"]} if mars
                    else {"from": None, "sha256": None,
                          "note": "no MARS process under this backend (none started yet, or agents are off)"})

    # which release is that?
    matches = {}
    for r in cfg.all_releases():
        c = r["components"]
        same = {
            "backend": c["backend"]["digest"] == comp["backend"]["digest"],
            "frontend": c["frontend"]["digest"] == comp["frontend"]["digest"],
            "front": c["front"]["sha256"] == comp["front"]["sha256"],
            "route_table": c["route_table"]["sha256"] == comp["route_table"]["sha256"],
            "mars": (c["mars"]["sha256"] == comp["mars"]["sha256"]) if comp["mars"]["sha256"] else None,
        }
        matches[r["id"]] = same
    whole = [rid for rid, same in matches.items() if all(v is not False for v in same.values())]
    out["serves_release"] = whole[-1] if whole else None
    if not whole:
        out["component_releases"] = {k: [rid for rid, same in matches.items() if same[k]]
                                     for k in ("backend", "frontend", "front", "route_table", "mars")}
    if whole:
        rdir = cfg.release_dir(whole[-1])
        out["launched_from_release_folder"] = os.path.normcase(str(code_root)).startswith(
            os.path.normcase(str(rdir)))
    recorded = (cfg.serving(name).get("current") or {}).get("release")
    out["recorded_release"] = recorded
    if recorded and recorded != out["serves_release"]:
        out["notes"].append(f"serving.json says {recorded}, but what is running is "
                            f"{out['serves_release'] or 'no recorded release'}")
    return out


def cmd_status(cfg: Config, a) -> int:
    seen = {name: observe(cfg, name) for name in cfg.envs}
    releases = {r["id"]: r for r in cfg.all_releases()}
    report = {"observed_at": now(), "environments": seen, "candidate": None}
    prod = [s for s in seen.values() if s["role"] == "production"]
    prod_release = prod[0].get("serves_release") if prod else None
    for s in seen.values():
        rid = s.get("serves_release")
        hist = [h["release"] for h in cfg.serving(s["environment"]).get("history", [])]
        s["can_roll_back_to"] = next((h for h in reversed(hist) if h != rid and h in releases), None)
        if s["role"] == "test" and rid and rid != prod_release:
            gates = gate_state(cfg.acceptance(rid))
            report["candidate"] = {
                "release": rid, "description": releases[rid]["description"], "gates": gates,
                "ready_for_production": all(v == "pass" for v in gates.values()),
                "waiting_on": [g for g, v in gates.items() if v != "pass"]}
    if a.json:
        print(json.dumps(report, indent=1))
        return 0
    for s in seen.values():
        print(f"{s['label']}  {s['url']}  ({s['role']})")
        if not s["up"]:
            print(f"    NOT ANSWERING: {s.get('why_down')}")
            continue
        rid = s.get("serves_release")
        if rid:
            how = "" if s.get("launched_from_release_folder") else \
                "  [same content, started the older way, not from the release folder]"
            print(f"    serves release {rid}{how}")
            print(f"        {releases[rid]['description']}")
        else:
            print("    serves NO recorded release. By component:")
            for k, ids in (s.get("component_releases") or {}).items():
                print(f"        {k}: {', '.join(ids) if ids else 'matches no release'}")
        c = s["components"]
        print(f"    backend   {str(c['backend']['digest'])[:12]}  started at commit "
              f"{str(c['backend']['commit_at_start'])[:12]}  pid {c['backend']['pid']}")
        bi = c["frontend"].get("build_identity") or {}
        print(f"    interface {str(c['frontend']['digest'])[:12]}  built from {str(bi.get('commit'))[:12]}")
        print(f"    front     {str(c['front']['sha256'])[:12]}    mars {str(c['mars']['sha256'])[:12]}")
        print(f"    brain     {s['brain']}")
        print(f"    rollback  {s['can_roll_back_to'] or 'no earlier release recorded for this environment'}")
        for n in s["notes"]:
            print(f"    NOTE: {n}")
    cand = report["candidate"]
    if cand:
        print(f"CANDIDATE under test: {cand['release']}: {cand['description']}")
        print("    " + "   ".join(f"{g}: {v}" for g, v in cand["gates"].items()))
        print("    READY for DAY-TO-DAY (the owner's promotion approval is still its own step)"
              if cand["ready_for_production"]
              else f"    NOT READY: waiting on {', '.join(cand['waiting_on'])}")
    else:
        print("CANDIDATE under test: none (TEST serves what DAY-TO-DAY serves, or is down)")
    return 0


# -- starting and stopping ------------------------------------------------------------

def _launch_cmd(cfg: Config, env: dict, rid: str) -> pathlib.Path:
    rdir = cfg.release_dir(rid)
    run_dir = env["run_dir"]
    mars = f'"{rdir / "bin" / "mars.exe"}"'
    if env.get("mars_data"):
        mars += f' --data-dir "{env["mars_data"]}"'
    lines = ["@echo off", "chcp 65001 >nul", 'set "PYTHONIOENCODING=utf-8"']
    # an environment's own machine-wide state (source bindings, caches, MARS data): without
    # these a copy of a Brain shares its original's, because they are keyed by the Brain's id
    for var, value in (env.get("env") or {}).items():
        lines.append(f'set "{var}={value}"')
    for var in env.get("unset") or ():
        lines.append(f'set "{var}="')
    if env.get("agents", False):
        lines += [f'set "MARS_BACKENDS_FILE={env["backends"]}"',
                  f"set MENTIS_MARS_COMMAND={mars} stdio"]
        if cfg.mars_local_python:
            lines.append(f'set "MARS_LOCAL_PYTHON={cfg.mars_local_python}"')
    else:
        # AGENTS OFF. An empty MENTIS_MARS_COMMAND falls back to `mars` on PATH, which may be
        # another environment's; a command that does not exist is the only "no MARS" there is.
        # Every dispatch then fails and is recorded as failed, including what start-up recovers.
        off = cfg.state(env["name"]) / "agents-off" / "no-mars.exe"
        lines += [f'set MENTIS_MARS_COMMAND="{off}" stdio', 'set "MARS_BACKENDS_FILE="']
    lines += [
        f'if not exist "{run_dir}" mkdir "{run_dir}"',
        f'del /q "{run_dir}\\launcher.exit" 2>nul',
        f'cd /d "{rdir / "code"}"',
        f'"{rdir / "bin" / "mentis-launch.exe"}" "{env["brain"]}" --port {env["port"]} '
        f'--private-port {env["private_port"]} --workspace "{env["workspace"]}" '
        f'--python "{cfg.python}" --code "{rdir / "code"}" '
        f'--front "{rdir / "bin" / "mentis-server.exe"}" '
        f'--dist "{rdir / "code" / "apps" / "fluid-web" / "dist"}" --run-dir "{run_dir}" '
        f'--route-table "{rdir / "route-table.json"}" 1>>"{run_dir}\\launcher.log" 2>&1',
        f'echo %errorlevel% >"{run_dir}\\launcher.exit"', ""]
    path = cfg.state(env["name"]) / "launch.cmd"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(lines), "utf-8")
    return path


def _answering(env: dict) -> bool:
    try:
        http(f"http://127.0.0.1:{env['port']}/api/server", timeout=5)
        return True
    except Exception:                                           # noqa: BLE001
        return False


def _open_runs(env: dict):
    """How many runs THIS server holds (a process is inside them), or None when that could not
    be read. Runs the record calls open but nobody holds -- a copied Brain is full of its
    original's -- are history a restart cannot end, and are not counted."""
    try:
        got = http_json(f"http://127.0.0.1:{env['port']}/api/working")
        return sum(1 for r in got.get("open") or [] if r.get("held_here"))
    except Exception:                                           # noqa: BLE001
        return None


def stop_env(cfg: Config, env: dict) -> list[str]:
    """Stop exactly the processes this environment's launcher recorded, and nothing else."""
    said = []
    run_dir = pathlib.Path(env["run_dir"])
    launch = read_json(run_dir / "launch.json")
    if not launch:
        if port_owner(env["port"]) or port_owner(env["private_port"]):
            raise Refused(f"{env['name']}: its ports are held but {run_dir} has no launch.json, so this "
                          f"tool cannot tell whose processes those are and stops nothing")
        return ["nothing was running"]
    if os.path.normcase(os.path.abspath(launch["brain"])) != os.path.normcase(os.path.abspath(env["brain"])):
        raise Refused(f"{run_dir}\\launch.json is for Brain {launch['brain']}, not {env['name']}'s")
    serving = cfg.serving(env["name"]).get("current") or {}
    launcher = None
    if serving.get("release"):
        launcher = cfg.release_dir(serving["release"]) / "bin" / "mentis-launch.exe"
    if not launcher or not launcher.is_file():
        launcher = pathlib.Path(launch["front"]["executable"]).with_name("mentis-launch.exe")
    front = process_facts(launch["front"]["pid"])
    if front and str(front["start_time"]) == str(launch["front"]["start_time"]):
        r = run([launcher, "stop", "--run-dir", run_dir, "--front"], check=False, timeout=90)
        said.append(f"front stop exit {r.returncode}")
        deadline = time.time() + 45
        while time.time() < deadline and process_facts(launch["front"]["pid"]):
            time.sleep(1)
        if process_facts(launch["front"]["pid"]):
            run(["taskkill", "/PID", launch["front"]["pid"], "/T", "/F"], check=False)
            said.append("front did not exit on its own and was killed by pid")
    py = process_facts(launch["python"]["pid"])
    if py and str(py["start_time"]) == str(launch["python"]["start_time"]):
        run(["taskkill", "/PID", launch["python"]["pid"], "/T", "/F"], check=False)
        said.append(f"backend tree {launch['python']['pid']} stopped")
    deadline = time.time() + 30
    while time.time() < deadline and (port_owner(env["port"]) or port_owner(env["private_port"])):
        time.sleep(1)
    if port_owner(env["port"]) or port_owner(env["private_port"]):
        raise Failed(f"{env['name']}: a port is still held after stopping the recorded processes")
    (run_dir / "launch.json").replace(run_dir / "launch.stopped.json")
    return said


def start_env(cfg: Config, env: dict, rid: str, wait=300) -> None:
    problems = verify_release(cfg, rid)
    if problems:
        raise Refused(f"release {rid} is not intact: {problems[:3]}")
    for port in (env["port"], env["private_port"]):
        if port_owner(port):
            raise Refused(f"port {port} is already held (pid {port_owner(port)})")
    if not os.path.isfile(os.path.join(env["brain"], "corpus.db")):
        raise Refused(f"{env['name']} has no Brain at {env['brain']}")
    for d in (env["workspace"], env["run_dir"], env.get("mars_data")):
        if d:
            os.makedirs(d, exist_ok=True)
    cmd = _launch_cmd(cfg, env, rid)
    # outside this process tree and any job it is in, so it outlives the session that ran this
    out = ps("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ "
             f"CommandLine = 'cmd.exe /d /c \"{cmd}\"'; CurrentDirectory = '{cfg.release_dir(rid) / 'code'}' }}; "
             "$r.ReturnValue")
    if out.strip() != "0":
        raise Failed(f"Win32_Process.Create returned {out}")
    deadline = time.time() + wait
    while time.time() < deadline:
        # the launcher says it is done by writing launch.json, a moment AFTER the server answers
        if _answering(env) and (pathlib.Path(env["run_dir"]) / "launch.json").is_file():
            return
        exit_file = pathlib.Path(env["run_dir"]) / "launcher.exit"
        if exit_file.is_file() and exit_file.read_text().strip() not in ("", "0"):
            log = pathlib.Path(env["run_dir"]) / "launcher.log"
            tail = log.read_text("utf-8", "replace")[-800:] if log.is_file() else ""
            raise Failed(f"the launcher exited {exit_file.read_text().strip()}: {tail}")
        time.sleep(2)
    raise Failed(f"{env['name']} did not answer /api/server within {wait} s")


def _migrate_plan(cfg: Config, env: dict, rid: str) -> dict:
    code = cfg.release_dir(rid) / "code"
    r = run([cfg.python, "-B", "-X", "utf8", "-m", "mentis.migrate", env["brain"], "--plan"],
            cwd=code, check=False)
    text = (r.stdout or "").strip()
    try:
        plan = json.loads(text)
    except ValueError:
        plan = {"raw": (text or r.stderr.strip())[-600:]}
    return {"exit": r.returncode, "plan": plan, "stderr": r.stderr.strip()[-400:]}


def _needs_migration(planned: dict) -> bool:
    plan = planned["plan"]
    for key in ("pending", "to_apply", "would_apply", "apply"):
        if plan.get(key):
            return True
    return False


def switch(cfg: Config, name: str, rid: str, *, why: str, approved: str | None,
           interrupt_runs: bool, migrate: bool) -> dict:
    """Stop `name`, start it on release `rid`, verify what answers IS that release, record it.
    A start that does not verify goes back to the release it was on."""
    env = cfg.env(name)
    cfg.release(rid)
    problems = verify_release(cfg, rid)
    if problems:
        raise Refused(f"release {rid} is not intact: {problems[:3]}")
    if env["role"] == "production" and not (approved or "").strip():
        raise Refused(f"{name} is production: --owner-approved carries the owner's own words for this change")
    serving = cfg.serving(name)
    before = (serving.get("current") or {}).get("release")
    was_up = _answering(env)
    if was_up:
        runs = _open_runs(env)
        if runs is None and not interrupt_runs:
            raise Refused(f"{name}: could not read whether runs are open; --interrupt-runs goes on anyway")
        if runs and not interrupt_runs:
            raise Refused(f"{name}: {runs} run(s) are open and a restart ends them; --interrupt-runs goes on anyway")
    planned = _migrate_plan(cfg, env, rid) if os.path.isfile(os.path.join(env["brain"], "corpus.db")) else None
    if planned and planned["exit"] != 0:
        raise Refused(f"release {rid} cannot plan a migration of {name}'s Brain (exit {planned['exit']}): "
                      f"{planned['plan'].get('raw') or planned['stderr']}")
    needs = bool(planned and _needs_migration(planned))
    if needs and not migrate:
        raise Refused(f"release {rid} would migrate {name}'s Brain ({json.dumps(planned['plan'])[:400]}): "
                      f"pass --migrate to allow it. A migrated Brain may not open under the previous release")
    t0 = time.time()
    said = stop_env(cfg, env) if (was_up or read_json(pathlib.Path(env["run_dir"]) / "launch.json")) else []
    migrated = False
    try:
        if needs:
            run([cfg.python, "-B", "-X", "utf8", "-m", "mentis.migrate", env["brain"], "--apply"],
                cwd=cfg.release_dir(rid) / "code")
            migrated = True
        start_env(cfg, env, rid)
        seen = observe(cfg, name)
        if seen.get("serves_release") != rid or seen.get("reports_release") != rid:
            raise Failed(f"what answers is not {rid}: components match "
                         f"{seen.get('serves_release')}, the server reports {seen.get('reports_release')}")
        if any(n.startswith("WRONG BRAIN") for n in seen["notes"]):
            raise Failed(seen["notes"][0])
    except (Failed, Refused) as exc:
        back = "nothing to go back to"
        try:
            stop_env(cfg, env)
        except (Failed, Refused) as exc2:
            back = f"could not stop the failed start: {exc2}"
        else:
            if before and not migrated:
                try:
                    start_env(cfg, env, before)
                    back = f"went back to {before}, which answers"
                except (Failed, Refused) as exc3:
                    back = f"going back to {before} failed too: {exc3}"
            elif before:
                back = (f"the Brain was migrated, so {before} was NOT started over it: {name} is DOWN "
                        f"and needs a forward fix")
        raise Failed(f"{name} did not come up on {rid}: {exc}. {back}") from exc
    gap = round(time.time() - t0, 1)
    entry = {"release": rid, "since": now(), "why": why, "approved": approved, "previous": before,
             "migrated": migrated, "gap_seconds": gap}
    serving["current"] = entry
    serving.setdefault("history", []).append(entry)
    write_json(cfg.state(name) / "serving.json", serving)
    acc = cfg.acceptance(rid)
    acc.setdefault("served_in", []).append({"environment": name, "role": env["role"], "at": now(),
                                            "verified": True})
    cfg.save_acceptance(rid, acc)
    if env.get("start_script") and os.path.isfile(env["start_script"]):
        _repoint_start_script(cfg, env, rid)
    return {"environment": name, "now_serves": rid, "was": before, "gap_seconds": gap,
            "migrated": migrated, "stop": said}


def _repoint_start_script(cfg: Config, env: dict, rid: str) -> None:
    """The owner's start-after-reboot script must start what is now served, not what was."""
    path = pathlib.Path(env["start_script"])
    text = path.read_text("utf-8-sig")
    cmd = cfg.state(env["name"]) / "launch.cmd"
    new = re.sub(r"(?m)^\$Launcher\s*=.*$", lambda _m: f"$Launcher = '{cmd}'", text)
    new = re.sub(r"(?m)^\$WorkingDirectory\s*=.*$",
                 lambda _m: f"$WorkingDirectory = '{cfg.release_dir(rid) / 'code'}'", new)
    if new != text:
        shutil.copy2(path, path.with_name(path.name + f".before-{rid}"))
        path.write_text(new, "utf-8")


def cmd_deploy(cfg: Config, a) -> int:
    env = cfg.env(a.environment)
    if env["role"] == "production":
        raise Refused("production takes releases through `promote`, which checks the gates")
    print(json.dumps(switch(cfg, a.environment, a.release, why="candidate deployed for testing",
                            approved=None, interrupt_runs=a.interrupt_runs, migrate=a.migrate), indent=1))
    return 0


def cmd_promote(cfg: Config, a) -> int:
    name = a.environment or next(n for n, e in cfg.envs.items() if e["role"] == "production")
    env = cfg.env(name)
    if env["role"] != "production":
        raise Refused(f"{name} is not production: use deploy")
    acc = cfg.acceptance(a.release)
    gates = gate_state(acc)
    missing = [g for g in GATES if gates[g] != "pass"]
    if missing:
        raise Refused(f"release {a.release} is not ready: " + ", ".join(f"{g} is {gates[g]}" for g in missing))
    if not any(s["role"] == "test" and s.get("verified") for s in acc.get("served_in", [])):
        raise Refused(f"release {a.release} was never served and verified in a test environment")
    tests = [n for n, e in cfg.envs.items() if e["role"] == "test"]
    if not any(observe(cfg, t).get("serves_release") == a.release for t in tests):
        raise Refused(f"no test environment is serving {a.release} now: what is promoted is what is under test")
    print(json.dumps(switch(cfg, name, a.release, why="promoted from TEST", approved=a.owner_approved,
                            interrupt_runs=a.interrupt_runs, migrate=a.migrate), indent=1))
    return 0


def cmd_rollback(cfg: Config, a) -> int:
    env = cfg.env(a.environment)
    serving = cfg.serving(a.environment)
    current = (serving.get("current") or {}).get("release")
    target = a.to or next((h["release"] for h in reversed(serving.get("history", []))
                           if h["release"] != current), None)
    if not target:
        raise Refused(f"{a.environment} has no earlier release recorded to go back to")
    rel, cur = cfg.release(target), (cfg.release(current) if current else None)
    if cur and cur["migration"]["min_reader_after"] > rel["migration"]["schema_target"]:
        raise Refused(f"{target} reads Brain schema {rel['migration']['schema_target']}, and the Brain "
                      f"under {current} needs a reader of at least {cur['migration']['min_reader_after']}: "
                      f"going back would not open it. Fix forward")
    print(json.dumps(switch(cfg, a.environment, target, why=f"rolled back from {current}",
                            approved=a.owner_approved, interrupt_runs=a.interrupt_runs, migrate=False),
                     indent=1))
    return 0


def cmd_start(cfg: Config, a) -> int:
    env = cfg.env(a.environment)
    rid = (cfg.serving(a.environment).get("current") or {}).get("release")
    if not rid:
        raise Refused(f"{a.environment} has no release recorded: "
                      + ("it is still started the older way, by its own start script, until its first promotion"
                         if env["role"] == "production" else "deploy one"))
    if _answering(env):
        print(f"{env['label']} already answers at http://127.0.0.1:{env['port']}")
        return 0
    start_env(cfg, env, rid)
    print(f"{env['label']} on http://127.0.0.1:{env['port']} serving {rid}")
    return 0


def cmd_stop(cfg: Config, a) -> int:
    env = cfg.env(a.environment)
    if env["role"] == "production" and not (a.owner_approved or "").strip():
        raise Refused(f"{a.environment} is production: --owner-approved carries the owner's own words")
    print("\n".join(stop_env(cfg, env)))
    return 0


def cmd_record(cfg: Config, a) -> int:
    cfg.release(a.release)
    acc = cfg.acceptance(a.release)
    acc.setdefault("records", []).append({"gate": a.gate, "result": a.result, "by": a.by,
                                          "evidence": a.evidence, "at": now()})
    cfg.save_acceptance(a.release, acc)
    print(json.dumps({"release": a.release, "gates": gate_state(acc)}, indent=1))
    return 0


# -- TEST's data: once, from a supported backup ----------------------------------------

def cmd_snapshot(cfg: Config, a) -> int:
    from snapshot import populate                                # tools/env/snapshot.py
    return populate(cfg, a, sys.modules[__name__])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mentis_env", description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", default=str(HERE / "environments.json"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    b = sub.add_parser("build")
    b.add_argument("--commit", required=True)
    b.add_argument("--describe", required=True)
    b.add_argument("--front-from")
    b.add_argument("--mars-from")
    b.add_argument("--front-differs-ok")
    b.add_argument("--dist-from")
    b.add_argument("--dist-reason")
    sub.add_parser("releases")
    sub.add_parser("verify").add_argument("release")

    def switching(p, env=True):
        if env:
            p.add_argument("environment")
        p.add_argument("--interrupt-runs", action="store_true")
        p.add_argument("--owner-approved")

    d = sub.add_parser("deploy")
    switching(d)
    d.add_argument("release")
    d.add_argument("--migrate", action="store_true")
    p = sub.add_parser("promote")
    p.add_argument("release")
    p.add_argument("--environment")
    switching(p, env=False)
    p.add_argument("--migrate", action="store_true")
    r = sub.add_parser("rollback")
    switching(r)
    r.add_argument("--to")
    sub.add_parser("start").add_argument("environment")
    st = sub.add_parser("stop")
    st.add_argument("environment")
    st.add_argument("--owner-approved")
    rec = sub.add_parser("record")
    rec.add_argument("release")
    rec.add_argument("gate", choices=GATES)
    rec.add_argument("--result", required=True, choices=("pass", "fail"))
    rec.add_argument("--by", required=True)
    rec.add_argument("--evidence", required=True)
    sn = sub.add_parser("snapshot")
    sn.add_argument("--owner-authorized", required=True)
    sn.add_argument("--source", default=None)
    sn.add_argument("--target", default=None)
    a = ap.parse_args(argv)
    try:
        cfg = Config(pathlib.Path(a.config))
        sys.path.insert(0, str(HERE))
        return {"status": cmd_status, "build": cmd_build, "releases": cmd_releases,
                "verify": cmd_verify, "deploy": cmd_deploy, "promote": cmd_promote,
                "rollback": cmd_rollback, "start": cmd_start, "stop": cmd_stop,
                "record": cmd_record, "snapshot": cmd_snapshot}[a.cmd](cfg, a)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except Failed as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
