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

#: What production IS on this machine, whatever a configuration file calls it. An environment
#: that touches any of these must have the role `production`, so no file can relabel
#: DAY-TO-DAY as a test environment and get the ungated commands.
PRODUCTION_PORTS = (8760, 18760)
#: characters that would change the meaning of a generated cmd or PowerShell line
UNSAFE_IN_PATH = set('%"\'&^`$;|<>\n\r')


def production_roots() -> list[str]:
    local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return [os.path.normcase(os.path.abspath(os.path.join(local, "Mentis"))),
            os.path.normcase(os.path.abspath(os.path.join(local, "mars")))]


def _under(path: str, root: str) -> bool:
    p = os.path.normcase(os.path.abspath(path))
    return p == root or p.startswith(root + os.sep)


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
        self._validate()

    def _validate(self) -> None:
        for value in (str(self.root), str(self.python), str(self.releases), str(self.repo),
                      str(self.mars_local_python or "")):
            if UNSAFE_IN_PATH & set(value):
                raise Refused(f"{self.path}: {value!r} is not safe in a generated command line")
        for value in (str(self.root), str(self.releases)):
            if any(_under(value, root) for root in production_roots()):
                raise Refused(f"{self.path}: {value} is inside DAY-TO-DAY's own folders; this tool's "
                              f"state and releases live outside them")
        for name, e in self.envs.items():
            for key in ("port", "private_port"):
                port = e.get(key)
                if type(port) is not int or not 1 <= port <= 65535:
                    raise Refused(f"{self.path}: {name}.{key} is not a port number (an integer): {port!r}")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
                raise Refused(f"{self.path}: environment name {name!r} is not lower-case letters, digits and -")
            for var in list(e.get("env") or {}) + list(e.get("unset") or []):
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,60}", str(var)):
                    raise Refused(f"{self.path}: {name}: {var!r} is not an environment variable name")
            if UNSAFE_IN_PATH & set(str(e.get("label", ""))) or not str(e.get("label", "")).strip():
                raise Refused(f"{self.path}: {name}: its label is empty or not safe to write")
        roles = [e.get("role") for e in self.envs.values()]
        if roles.count("production") != 1 or "test" not in roles or set(roles) - {"production", "test"}:
            raise Refused(f"{self.path}: exactly one environment is `production` and the rest are `test`")
        seen: dict[str, str] = {}
        for name, e in self.envs.items():
            paths = {k: e.get(k) for k in ("brain", "workspace", "run_dir", "mars_data", "backends",
                                           "start_script")}
            paths.update({f"env.{k}": v for k, v in (e.get("env") or {}).items()})
            paths["its state folder"] = str(self.state(name))
            for key, value in paths.items():
                if value and UNSAFE_IN_PATH & set(str(value)):
                    raise Refused(f"{self.path}: {name}.{key} holds a character that is not safe in a "
                                  f"generated command line: {value!r}")
            touches = (e["port"] in PRODUCTION_PORTS or e["private_port"] in PRODUCTION_PORTS or any(
                _under(str(v), root) for v in paths.values() if v for root in production_roots()))
            if touches and e["role"] != "production":
                raise Refused(f"{self.path}: {name} uses DAY-TO-DAY's ports or folders, so it is "
                              f"production whatever this file calls it; nothing was done")
            if e["role"] != "production":
                if e.get("agents") and not e.get("mars_data"):
                    raise Refused(f"{self.path}: {name} has agents on but no MARS data folder of its own")
            # every path an environment writes to, or keeps state in, is its alone
            for key, value in paths.items():
                if value:
                    k = os.path.normcase(os.path.abspath(str(value)))
                    if k in seen and seen[k] != name:
                        raise Refused(f"{self.path}: {name} and {seen[k]} share {value} ({key})")
                    for other, owner in list(seen.items()):
                        if owner != name and not other.isdigit() and (
                                _under(k, other) or _under(other, k)):
                            raise Refused(f"{self.path}: {name}.{key} ({value}) and a path of "
                                          f"{owner} ({other}) are inside one another")
                    seen[k] = name
            for port in (e["port"], e["private_port"]):
                if str(port) in seen and seen[str(port)] != name:
                    raise Refused(f"{self.path}: {name} and {seen[str(port)]} share port {port}")
                seen[str(port)] = name

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
                if doc and doc.get("id") == d.name:
                    out.append(doc)
        return sorted(out, key=lambda r: r["created_at"])

    def index(self) -> dict:
        """{release id: sha256 of its RELEASE.json}, kept OUTSIDE every release folder, so a
        manifest edited inside one no longer matches what was recorded when it was built."""
        return read_json(self.releases / "INDEX.json", {})

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


_PACKAGES = r"""
import hashlib, importlib.metadata as md, json, os, sys
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()
def binaries(top):
    return {n: sha(os.path.join(top, n)) for n in sorted(os.listdir(top))
            if n.lower().endswith(('.exe', '.dll', '.pyd'))}
out = {'version': sys.version, 'executable': sha(sys.executable),
       'base': binaries(getattr(sys, 'base_prefix', sys.prefix)), 'dists': {}}
dlls = os.path.join(getattr(sys, 'base_prefix', sys.prefix), 'DLLs')
if os.path.isdir(dlls):
    out['dlls'] = binaries(dlls)
for d in md.distributions():
    files = {}
    for f in d.files or ():
        if '__pycache__' in f.parts or f.suffix == '.pyc':
            continue
        p = d.locate_file(f)
        try:
            files[str(f).replace(os.sep, '/')] = sha(p)
        except OSError:
            files[str(f).replace(os.sep, '/')] = None
    out['dists'][f"{d.metadata['Name']}=={d.version}"] = files
print(hashlib.sha256(json.dumps(out, sort_keys=True).encode('utf-8')).hexdigest())
"""

_PACKAGES_SEEN: dict = {}


def packages_digest(python: str) -> str:
    """The shared interpreter and what is installed in it, BY CONTENT: the configured
    executable, the base interpreter's binaries, and every file each installed distribution
    lists (not its RECORD's word for them; compiled caches left out). A release is only the
    tested thing while this is what it was tested with. Read once per run of this tool."""
    if python not in _PACKAGES_SEEN:
        _PACKAGES_SEEN[python] = run([python, "-I", "-c", _PACKAGES], timeout=600).stdout.strip()
    return _PACKAGES_SEEN[python]


def expected_packages(cfg: "Config", rid: str):
    """The runtime digest release `rid` must run on: what TEST verified it with, else what it
    was built with. None when neither was ever recorded."""
    verified = [s for s in cfg.acceptance(rid).get("served_in", [])
                if s["role"] == "test" and s.get("verified") and s.get("python_packages")]
    if verified:
        return verified[-1]["python_packages"]
    return (cfg.release(rid).get("runtime") or {}).get("packages_sha256")


def promotion_blockers(cfg: "Config", rid: str, seen: dict | None = None) -> list[str]:
    """Everything that stands between release `rid` and production, in words. `status` and
    `promote` both read THIS, so status never says ready when promote would refuse."""
    out = []
    acc = cfg.acceptance(rid)
    verified = [s for s in acc.get("served_in", []) if s["role"] == "test" and s.get("verified")]
    if not verified:
        return [f"release {rid} was never served and verified in a test environment"]
    first = verified[0]["at"]
    gates = gate_state(acc)
    for gate in GATES:
        if gates[gate] != "pass":
            out.append(f"{gate} is {gates[gate]}")
            continue
        last = [r for r in acc["records"] if r["gate"] == gate][-1]
        if last["at"] < first:
            out.append(f"{gate} was recorded before the release was ever verified in TEST")
    problems = verify_release(cfg, rid)
    if problems:
        out.append(f"the release folder is not intact: {problems[:2]}")
    tested_with = verified[-1].get("python_packages")
    if not tested_with:
        out.append("TEST's verification of this release did not record the Python and packages it "
                   "ran on: deploy it to TEST again")
    elif tested_with != packages_digest(cfg.python):
        out.append("the shared Python or its installed packages changed since TEST verified this "
                   "release: what would be promoted is no longer what was tested")
    tests = [n for n, e in cfg.envs.items() if e["role"] == "test"]
    looks = seen if seen is not None else {t: observe(cfg, t) for t in tests}
    serving = [t for t in tests if (looks.get(t) or {}).get("serves_release") == rid
               and (looks[t].get("launched_from_release_folder"))]
    if not serving:
        why = "; ".join(f"{t}: {(looks.get(t) or {}).get('why_no_release') or (looks.get(t) or {}).get('serves_release') or 'down'}"
                        for t in tests)
        out.append(f"no test environment is serving {rid} from its release folder now ({why})")
    # production's side: what `switch` would refuse on that can be known without touching it
    prod_name = next(n for n, e in cfg.envs.items() if e["role"] == "production")
    prod = cfg.env(prod_name)
    prod_look = looks.get(prod_name) if prod_name in looks else observe(cfg, prod_name)
    if (prod_look or {}).get("up") and not prod_look.get("serves_release"):
        out.append(f"{prod_name} is serving something no recorded release matches "
                   f"({prod_look.get('why_no_release')}), so a failed promotion would have nothing "
                   f"verified to go back to")
    if prod.get("start_script"):
        why = _start_script_problem(prod["start_script"])
        if why:
            out.append(why)
    if not os.path.isfile(os.path.join(prod["brain"], "corpus.db")):
        out.append(f"{prod_name} has no Brain at {prod['brain']}")
    # NOTHING HERE RUNS THE CANDIDATE AGAINST PRODUCTION. Whether the release would migrate
    # production's Brain is read from the two manifests (`_schema_step`); the migration is only
    # ever planned on the real Brain inside `switch`, after the owner's words and the gates.
    step = _schema_step(cfg, rid, (prod_look or {}).get("serves_release"))
    if step["known"] and step["backwards"]:
        out.append(f"the release reads Brain schema {step['to']}, older than the {step['from']} "
                   f"{prod_name} is on: it could not open that Brain")
    return out


def _schema_step(cfg: "Config", rid: str, serving: str | None) -> dict:
    """What going from the release an environment serves to release `rid` means for its Brain,
    from the two RELEASE.json manifests alone. No Brain is opened and no release code runs."""
    to = cfg.release(rid)["migration"]
    if not serving:
        return {"known": False, "to": to["schema_target"]}
    cur = cfg.release(serving)["migration"]
    new = [m for m in ((cfg.release(rid)["components"].get("backend") or {}).get("migrations") or [])
           if m not in ((cfg.release(serving)["components"].get("backend") or {}).get("migrations") or [])]
    return {"known": True, "from": cur["schema_target"], "to": to["schema_target"],
            "migrates": to["schema_target"] != cur["schema_target"] or bool(new),
            "new_migrations": new,
            "breaking": to["min_reader_after"] > cur["min_reader_after"],
            "backwards": to["schema_target"] < cur["min_reader_after"]}


def promotion_needs(cfg: "Config", rid: str) -> list[str]:
    """What a promotion of `rid` would additionally have to be TOLD, in words: the flags that
    are the owner's to give. Not blockers, and never silently assumed."""
    out = []
    prod_name = next(n for n, e in cfg.envs.items() if e["role"] == "production")
    prod = cfg.env(prod_name)
    if _answering(prod):
        runs = _open_runs(prod)
        if runs is None:
            out.append(f"--interrupt-runs (whether runs are in flight on {prod_name} could not be read)")
        elif runs:
            out.append(f"--interrupt-runs ({runs} run(s) are in flight on {prod_name} now)")
    serving = observe(cfg, prod_name).get("serves_release") if _answering(prod) else \
        (cfg.serving(prod_name).get("current") or {}).get("release")
    step = _schema_step(cfg, rid, serving)
    if not step["known"]:
        out.append("possibly --migrate (what production serves is not a recorded release, so whether "
                   "its Brain would be migrated is not known until the promotion plans it)")
    elif step["migrates"]:
        out.append(f"--migrate (the release would migrate the production Brain from schema "
                   f"{step['from']} to {step['to']}"
                   + (", after which the release it serves now could not open it" if step["breaking"] else "")
                   + ")")
    return out


def _start_script_problem(path) -> str | None:
    p = pathlib.Path(path)
    if not p.is_file():
        return f"{p} (the start-after-reboot script) does not exist"
    try:
        text = p.read_text("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return f"{p} (the start-after-reboot script) cannot be read: {exc}"
    n1 = len(re.findall(r"(?m)^\$Launcher\s*=.*$", text))
    n2 = len(re.findall(r"(?m)^\$WorkingDirectory\s*=.*$", text))
    if n1 != 1 or n2 != 1:
        return (f"{p} does not have exactly one $Launcher and one $WorkingDirectory line "
                f"({n1}, {n2}), so it could not be repointed")
    return None


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
            "runtime": {"python": cfg.python, "packages_sha256": packages_digest(cfg.python),
                        "note": "the interpreter and its installed packages are shared by every "
                                "environment and are not inside the release. This is their digest "
                                "at build time; TEST records the digest it verifies the release on, "
                                "and production is refused unless it matches that"},
            "migration": {"schema_target": schema["schema_target"],
                          "min_reader_after": schema["min_reader_after"],
                          "note": "deploy runs `mentis.migrate --plan` against the environment's Brain "
                                  "and says what it would apply before applying anything"},
            "files": tree_files(stage),
        }
        write_json(stage / "RELEASE.json", doc)
        _make_readonly(stage)
        # the index first: a folder under a release's name always has its digest on record
        index = cfg.index()
        index[rid] = sha_file(stage / "RELEASE.json")
        write_json(cfg.releases / "INDEX.json", index)
        try:
            os.rename(stage, cfg.release_dir(rid))
        except OSError:
            index.pop(rid, None)
            write_json(cfg.releases / "INDEX.json", index)
            raise
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
    top = cfg.release_dir(rid)
    manifest = top / "RELEASE.json"
    if not manifest.is_file():
        return [f"{manifest} does not exist"]
    recorded = cfg.index().get(rid)
    if not recorded:
        return [f"release {rid} is not in {cfg.releases / 'INDEX.json'}: it was not built by this tool here"]
    if sha_file(manifest) != recorded:
        return ["RELEASE.json is not the manifest recorded when the release was built"]
    doc = cfg.release(rid)
    if doc.get("id") != rid:
        return [f"the folder is named {rid} and its manifest says {doc.get('id')}"]
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

    # which release is that? EVERY observation has to agree; anything that does not is the
    # reason no release is named, never a footnote under a release that is named anyway.
    env_agents = bool(env.get("agents", False))
    packages = packages_digest(cfg.python)
    out["python_packages"] = packages
    blocking = [n for n in out["notes"]]
    if now_tree.get("code_changed_since_start") is not False:
        blocking.append("whether the backend's code changed since the process started is not known to be no")
    if not served_index or served_index != comp["frontend"]["disk_index_sha256"]:
        blocking.append("the page served could not be matched to the dist folder on disk")
    if env_agents and not comp["mars"]["sha256"]:
        blocking.append("agents are on but no MARS process runs under this backend")
    if not env_agents and comp["mars"]["sha256"]:
        blocking.append("agents are off but a MARS process runs under this backend")
    matches, reasons = {}, {}
    for r in cfg.all_releases():
        c = r["components"]
        same = {
            "backend": c["backend"]["digest"] == comp["backend"]["digest"],
            "frontend": c["frontend"]["digest"] == comp["frontend"]["digest"]
                        and c["frontend"]["index_sha256"] == served_index
                        and (c["frontend"].get("build_identity") or {}).get("commit")
                        == (comp["frontend"].get("build_identity") or {}).get("commit"),
            "front": c["front"]["sha256"] == comp["front"]["sha256"],
            "route_table": c["route_table"]["sha256"] == comp["route_table"]["sha256"],
            "mars": (c["mars"]["sha256"] == comp["mars"]["sha256"]) if env_agents else True,
            # TEST is where a release's runtime is established, so nothing is required of it
            # there; production must be on what TEST last verified the release with
            "python_packages": (env["role"] != "production"
                                or expected_packages(cfg, r["id"]) in (None, packages)),
        }
        matches[r["id"]] = same
    whole = [rid for rid, same in matches.items() if all(same.values())]
    reported = out.get("reports_release")
    if reported and whole and reported not in whole:
        blocking.append(f"the server reports release {reported}, and its content is {whole[-1]}")
    if reported in whole:
        whole = [reported]
    out["serves_release"] = whole[-1] if whole and not blocking else None
    if not out["serves_release"]:
        out["why_no_release"] = "; ".join(blocking) if blocking else "its components match no one release"
        out["component_releases"] = {k: [rid for rid, same in matches.items() if same[k]]
                                     for k in ("backend", "frontend", "front", "route_table", "mars",
                                               "python_packages")}
    else:
        rdir = cfg.release_dir(out["serves_release"])
        out["launched_from_release_folder"] = (
            reported == out["serves_release"]
            and all(_under(str(p), os.path.normcase(os.path.abspath(str(rdir))))
                    for p in (code_root, dist, comp["front"]["from"] or "nowhere",
                              comp["route_table"]["from"] or "nowhere",
                              *([comp["mars"]["from"] or "nowhere"] if env_agents else []))))
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
            blockers = promotion_blockers(cfg, rid, seen)
            report["candidate"] = {
                "release": rid, "description": releases[rid]["description"],
                "gates": gate_state(cfg.acceptance(rid)),
                # never an unconditional "ready": the production Brain's own migration plan is
                # made only at promotion, after the owner's words, and can still refuse
                "checks_passed": not blockers, "waiting_on": blockers,
                "still_decided_at_promotion": [
                    "the owner's approval of this promotion",
                    "the migration plan of the production Brain, which is made only then and can refuse"],
                "promotion_would_need": promotion_needs(cfg, rid) if not blockers else []}
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
            print(f"    serves NO recorded release: {s.get('why_no_release')}")
            for k, ids in (s.get("component_releases") or {}).items():
                print(f"        {k}: {', '.join(ids) if ids else 'matches no release'}")
        c = s["components"]
        print(f"    backend   {str(c['backend']['digest'])[:12]}  started at commit "
              f"{str(c['backend']['commit_at_start'])[:12]}  pid {c['backend']['pid']}")
        bi = c["frontend"].get("build_identity") or {}
        print(f"    interface {str(c['frontend']['digest'])[:12]}  built from {str(bi.get('commit'))[:12]}")
        print(f"    front     {str(c['front']['sha256'])[:12]}    mars {str(c['mars']['sha256'])[:12]}"
              f"    python+packages {s.get('python_packages', '')[:12]}")
        print(f"    brain     {s['brain']}")
        print(f"    rollback  {s['can_roll_back_to'] or 'no earlier release recorded for this environment'}")
        for n in s["notes"]:
            print(f"    NOTE: {n}")
    cand = report["candidate"]
    if cand:
        print(f"CANDIDATE under test: {cand['release']}: {cand['description']}")
        print("    " + "   ".join(f"{g}: {v}" for g, v in cand["gates"].items()))
        if cand["checks_passed"]:
            print("    EVERY CHECK THAT CAN BE MADE WITHOUT TOUCHING PRODUCTION HAS PASSED.")
            print("    Still decided at promotion, and able to refuse it:")
            for item in cand["still_decided_at_promotion"]:
                print(f"        {item}")
            for need in cand["promotion_would_need"]:
                print(f"        and the promotion would need {need}")
        else:
            print("    NOT READY:")
            for w in cand["waiting_on"]:
                print(f"        {w}")
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
        # AGENTS OFF, EXPLICITLY. An empty MENTIS_MARS_COMMAND falls back to `mars` on PATH,
        # which may be another environment's. What runs instead is a copy of agents_off.py in
        # the environment's own folder: it says agents are off and exits, so MARS is never reached, no
        # runtime is listed, and every dispatch fails and is recorded as failed. Nothing that
        # later appears on disk can turn it into a MARS.
        off = cfg.state(env["name"]) / "agents_off.py"
        off.parent.mkdir(parents=True, exist_ok=True)
        off.write_bytes((HERE / "agents_off.py").read_bytes())
        lines += [f'set MENTIS_MARS_COMMAND="{cfg.python}" -I "{off}"', 'set "MARS_BACKENDS_FILE="']
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


def _still(pid, start_time) -> bool:
    """Whether `pid` is STILL the process the launcher recorded: a pid can be reused."""
    facts = process_facts(pid)
    return bool(facts) and str(facts["start_time"]) == str(start_time)


def _kill_recorded(recorded: dict) -> bool:
    """Kill the recorded process and its tree, only if it is still that process NOW. The tree
    is the server's own (its MARS and the workers it started)."""
    if not _still(recorded["pid"], recorded["start_time"]):
        return False
    run(["taskkill", "/PID", recorded["pid"], "/T", "/F"], check=False)
    return True


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
    launcher = pathlib.Path(launch["front"]["executable"]).with_name("mentis-launch.exe")
    front, py = launch["front"], launch["python"]
    if _still(front["pid"], front["start_time"]):
        r = run([launcher, "stop", "--run-dir", run_dir, "--front"], check=False, timeout=90)
        said.append(f"front stop exit {r.returncode}")
        deadline = time.time() + 45
        while time.time() < deadline and _still(front["pid"], front["start_time"]):
            time.sleep(1)
        if _kill_recorded(front):
            said.append("front did not exit on its own and was killed")
    if _kill_recorded(py):
        said.append(f"backend tree {py['pid']} stopped")
    deadline = time.time() + 30
    while time.time() < deadline and (port_owner(env["port"]) or port_owner(env["private_port"])):
        time.sleep(1)
    if port_owner(env["port"]) or port_owner(env["private_port"]):
        raise Failed(f"{env['name']}: a port is still held after stopping the recorded processes")
    (run_dir / "launch.json").replace(run_dir / "launch.stopped.json")
    return said


def detached_start(command_line: str, cwd) -> str:
    """The PowerShell that starts `command_line` outside this process tree and any job it is in,
    so it outlives the session that ran this; it prints Win32_Process.Create's return value.

    WITH ITS WINDOW HIDDEN (ShowWindow = 0, as docs/cutover/launch-common.ps1 always did). A
    process WMI creates has no console to inherit, so without this `cmd.exe` is given a new,
    visible one: a terminal window over whatever the owner is doing, taking the keyboard focus,
    for as long as the launcher takes to bring the server up. Hidden, the console is still a
    real one, so everything the launcher starts has it to inherit and opens none of its own."""
    return ("$s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }; "
            "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ "
            f"CommandLine = '{command_line}'; CurrentDirectory = '{cwd}'; ProcessStartupInformation = $s }}; "
            "$r.ReturnValue")


def start_env(cfg: Config, env: dict, rid: str, wait=300) -> None:
    problems = verify_release(cfg, rid)
    if problems:
        raise Refused(f"release {rid} is not intact: {problems[:3]}")
    expected = expected_packages(cfg, rid)
    if env["role"] == "production" and not expected:
        raise Refused(f"nothing records the Python and packages release {rid} was verified on, so it "
                      f"cannot be shown to be the tested thing: deploy it to TEST first")
    if env["role"] == "production" and expected != packages_digest(cfg.python):
        raise Refused(f"the shared Python or its installed packages are not what TEST last verified "
                      f"release {rid} on: it would not be the tested thing. Deploy it to TEST again "
                      f"(that verifies it on the Python as it is now), then promote")
    for port in (env["port"], env["private_port"]):
        if port_owner(port):
            raise Refused(f"port {port} is already held (pid {port_owner(port)})")
    if not os.path.isfile(os.path.join(env["brain"], "corpus.db")):
        raise Refused(f"{env['name']} has no Brain at {env['brain']}")
    for d in (env["workspace"], env["run_dir"], env.get("mars_data")):
        if d:
            os.makedirs(d, exist_ok=True)
    cmd = _launch_cmd(cfg, env, rid)
    out = ps(detached_start(f'cmd.exe /d /c "{cmd}"', cfg.release_dir(rid) / "code"))
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


def _verified_on(cfg: Config, name: str, rid: str) -> None:
    """What answers IS release `rid`, from its folder, on this environment's Brain: or Failed."""
    seen = observe(cfg, name)
    if seen.get("serves_release") != rid or not seen.get("launched_from_release_folder"):
        raise Failed(f"what answers is not {rid} from its release folder: "
                     f"{seen.get('why_no_release') or seen.get('serves_release')}")


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
    """`mentis.spine.migrations.plan`: `migrations` is the pending list, empty when none."""
    return bool(planned["plan"].get("migrations"))


def switch(cfg: Config, name: str, rid: str, *, why: str, approved: str | None,
           interrupt_runs: bool, migrate: bool) -> dict:
    """Stop `name`, start it on release `rid`, verify what answers IS that release, record it.
    A start that does not verify goes back to the release that was OBSERVED before the stop."""
    env = cfg.env(name)
    cfg.release(rid)
    problems = verify_release(cfg, rid)
    if problems:
        raise Refused(f"release {rid} is not intact: {problems[:3]}")
    if env["role"] == "production" and not (approved or "").strip():
        raise Refused(f"{name} is production: --owner-approved carries the owner's own words for this change")
    serving = cfg.serving(name)
    was_up = _answering(env)
    # what to go back to is what was actually running, not what a file remembers
    before = observe(cfg, name).get("serves_release") if was_up else \
        (serving.get("current") or {}).get("release")
    if was_up and not before and env["role"] == "production":
        raise Refused(f"{name} is serving something no recorded release matches, so there would be "
                      f"nothing verified to go back to: record what it serves as a release first")
    if was_up:
        runs = _open_runs(env)
        if runs is None and not interrupt_runs:
            raise Refused(f"{name}: could not read whether runs are in flight; --interrupt-runs goes on anyway")
        if runs and not interrupt_runs:
            raise Refused(f"{name}: {runs} run(s) are in flight and a restart ends them; --interrupt-runs goes on anyway")
    planned = _migrate_plan(cfg, env, rid) if os.path.isfile(os.path.join(env["brain"], "corpus.db")) else None
    if planned and planned["exit"] != 0:
        raise Refused(f"release {rid} cannot plan a migration of {name}'s Brain (exit {planned['exit']}): "
                      f"{planned['plan'].get('raw') or planned['stderr']}")
    if planned and planned["plan"].get("problems"):
        raise Refused(f"{name}'s Brain has problems release {rid} will not migrate over: "
                      f"{planned['plan']['problems']}")
    needs = bool(planned and _needs_migration(planned))
    if needs and not migrate:
        raise Refused(f"release {rid} would migrate {name}'s Brain ({json.dumps(planned['plan'])[:400]}): "
                      f"pass --migrate to allow it. A migrated Brain may not open under the previous release")
    script_backup = None
    t0 = time.time()
    said = stop_env(cfg, env) if (was_up or read_json(pathlib.Path(env["run_dir"]) / "launch.json")) else []
    migrated = False
    try:
        if needs:
            breaking = ["--allow-breaking"] if planned["plan"].get("breaking") else []
            run([cfg.python, "-B", "-X", "utf8", "-m", "mentis.migrate", env["brain"], "--apply",
                 *breaking], cwd=cfg.release_dir(rid) / "code")
            migrated = True
        start_env(cfg, env, rid)
        _verified_on(cfg, name, rid)
        # the start-after-reboot script and the records are part of the switch: all of it
        # happens or the environment goes back to what it was running
        gap = round(time.time() - t0, 1)
        stamp = now()
        entry = {"release": rid, "since": stamp, "why": why, "approved": approved,
                 "previous": before, "migrated": migrated, "gap_seconds": gap}
        acc = cfg.acceptance(rid)
        acc.setdefault("served_in", []).append({
            "environment": name, "role": env["role"], "at": stamp, "verified": True,
            "python_packages": packages_digest(cfg.python)})
        history = list(serving.get("history", []))
        if before and before not in {h["release"] for h in history}:
            # what was observed serving before this tool first switched the environment is part
            # of its history: it is what a rollback goes back to
            history.append({"release": before, "since": None, "previous": None,
                            "why": "observed serving, by content, before this switch"})
        new_serving = {**serving, "current": entry, "history": [*history, entry]}
        script_backup = _repoint_start_script(cfg, env, rid)
        try:
            write_json(cfg.state(name) / "serving.json", new_serving)
            cfg.save_acceptance(rid, acc)
        except OSError as exc:
            raise Failed(f"the records could not be written: {exc}") from exc
    except BaseException as exc:                                # noqa: BLE001
        # ANY failure after the stop, of any kind, an interruption included: nothing
        # half-switched is left standing
        undone = []
        if script_backup:
            try:
                shutil.copy2(script_backup, env["start_script"])
            except OSError as exc_s:
                undone.append(f"THE START SCRIPT COULD NOT BE PUT BACK ({exc_s}): {env['start_script']} "
                              f"now starts {rid}; its previous text is {script_backup}")
        try:
            write_json(cfg.state(name) / "serving.json", serving)
        except OSError as exc_r:
            undone.append(f"serving.json could not be put back ({exc_r})")
        back = "nothing to go back to"
        try:
            stop_env(cfg, env)
        except Exception as exc2:                               # noqa: BLE001
            back = (f"COULD NOT STOP THE FAILED START ({type(exc2).__name__}: {exc2}): {name} may be "
                    f"running {rid} unverified")
        else:
            if before and not migrated:
                try:
                    start_env(cfg, env, before)
                    _verified_on(cfg, name, before)
                    back = f"went back to {before}, verified"
                except Exception as exc3:                       # noqa: BLE001
                    back = f"going back to {before} failed too: {exc3}. {name} may be DOWN"
            elif before:
                back = (f"the Brain was migrated, so {before} was NOT started over it: {name} is DOWN "
                        f"and needs a forward fix")
        raise Failed(f"{name} did not come up on {rid}: {type(exc).__name__}: {exc}. {back}"
                     + ("".join(f". {u}" for u in undone))) from exc
    return {"environment": name, "now_serves": rid, "was": before, "gap_seconds": gap,
            "migrated": migrated, "stop": said}


def _repoint_start_script(cfg: Config, env: dict, rid: str):
    """The owner's start-after-reboot script must start what is now served, not what was.
    Exactly one `$Launcher` and one `$WorkingDirectory` line, or nothing is written and the
    switch fails. Returns the kept copy of the script as it was, or None when there is none."""
    if not env.get("start_script"):
        return None
    path = pathlib.Path(env["start_script"])
    if not path.is_file():
        raise Failed(f"{path} (the start script) does not exist")
    text = path.read_text("utf-8-sig")
    cmd = cfg.state(env["name"]) / "launch.cmd"
    new, n1 = re.subn(r"(?m)^\$Launcher\s*=.*$", lambda _m: f"$Launcher = '{cmd}'", text)
    new, n2 = re.subn(r"(?m)^\$WorkingDirectory\s*=.*$",
                      lambda _m: f"$WorkingDirectory = '{cfg.release_dir(rid) / 'code'}'", new)
    if n1 != 1 or n2 != 1:
        raise Failed(f"{path} does not have exactly one $Launcher and one $WorkingDirectory line "
                     f"({n1}, {n2}): it was not changed")
    if new == text:
        return None
    backup = path.with_name(path.name + f".before-{rid}-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new, "utf-8")
    os.replace(tmp, path)
    return str(backup)


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
    cfg.release(a.release)
    blockers = promotion_blockers(cfg, a.release)
    if blockers:
        raise Refused(f"release {a.release} is not ready: " + "; ".join(blockers))
    print(json.dumps(switch(cfg, name, a.release, why="promoted from TEST", approved=a.owner_approved,
                            interrupt_runs=a.interrupt_runs, migrate=a.migrate), indent=1))
    return 0


def cmd_rollback(cfg: Config, a) -> int:
    env = cfg.env(a.environment)
    serving = cfg.serving(a.environment)
    recorded = (serving.get("current") or {}).get("release")
    # what it is rolling back FROM is what is actually running, when anything is
    current = observe(cfg, a.environment).get("serves_release") if _answering(env) else recorded
    if _answering(env) and not current:
        raise Refused(f"{a.environment} is serving something no recorded release matches, so what a "
                      f"rollback would be going back from is not known; look at `status` first")
    target = a.to or next((h["release"] for h in reversed(serving.get("history", []))
                           if h["release"] != current), None)
    if not target:
        raise Refused(f"{a.environment} has no earlier release recorded to go back to")
    if target == current:
        raise Refused(f"{a.environment} is already serving {target}")
    served_here = {h["release"] for h in serving.get("history", [])}
    if target not in served_here:
        raise Refused(f"{target} was never served and verified by {a.environment}: a rollback only goes "
                      f"back to a release this environment has run. A release it has not run goes "
                      f"through " + ("promote, with its gates" if env["role"] == "production" else "deploy"))
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
    if env["role"] == "production" and not (a.owner_approved or "").strip():
        raise Refused(f"{a.environment} is production: --owner-approved carries the owner's own words")
    rid = (cfg.serving(a.environment).get("current") or {}).get("release")
    if not rid:
        raise Refused(f"{a.environment} has no release recorded: "
                      + ("it is still started the older way, by its own start script, until its first promotion"
                         if env["role"] == "production" else "deploy one"))
    if _answering(env):
        print(f"{env['label']} already answers at http://127.0.0.1:{env['port']}")
        return 0
    try:
        start_env(cfg, env, rid)
        _verified_on(cfg, a.environment, rid)
    except Refused:
        raise                                                   # refused before anything started
    except BaseException as exc:                                # noqa: BLE001
        try:
            left = "; it was stopped again: " + ", ".join(stop_env(cfg, env))
        except Exception as exc2:                               # noqa: BLE001
            left = f"; and it could NOT be stopped again: {exc2}"
        raise Failed(f"{type(exc).__name__}: {exc}{left}") from exc
    print(f"{env['label']} on http://127.0.0.1:{env['port']} serving {rid}, verified")
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
    if not any(s["role"] == "test" and s.get("verified") for s in acc.get("served_in", [])):
        raise Refused(f"release {a.release} has not been served and verified in TEST yet: a gate is "
                      f"recorded about the release as TEST ran it, so deploy it there first")
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
    sa = sub.add_parser("start")
    sa.add_argument("environment")
    sa.add_argument("--owner-approved")
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
