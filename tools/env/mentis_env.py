"""Two environments, immutable releases, one way to say what is served.

    python tools/env/mentis_env.py status                       what each environment ACTUALLY serves
    python tools/env/mentis_env.py build --commit C --describe "plain words"
    python tools/env/mentis_env.py releases | verify ID
    python tools/env/mentis_env.py deploy test ID                candidate -> TEST
    python tools/env/mentis_env.py record ID review|browser|owner --result pass|fail --by WHO --evidence TEXT
    python tools/env/mentis_env.py record ID tests --result pass|fail --by WHO --evidence TEXT
    python tools/env/mentis_env.py production ID --owner-approved "the owner's words"  THE WHOLE LIFECYCLE
    python tools/env/mentis_env.py promote ID --owner-approved "the owner's words"     promotion alone, same checks
    python tools/env/mentis_env.py lifecycle ID                  the eight conditions, from evidence
    python tools/env/mentis_env.py build-binaries --component mars|front --commit C
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
a `test` environment with review, tests, browser and owner acceptance recorded as passed,
every source commit on its REMOTE main, and every artifact shown to be built from its commit
("the deployment contract", below). A promotion never interrupts a run.

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
GATES = ("review", "tests", "browser", "owner")
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
        #: the repositories a production release's commits must be on the remote main of
        said = doc.get("sources") or {}
        self.sources = {"mentis": {"repo": str(self.repo), "remote": "origin", "branch": "main",
                                   **(said.get("mentis") or {})}}
        if said.get("mars"):
            self.sources["mars"] = {"remote": "origin", "branch": "main", **said["mars"]}
        #: a rehearsal's own state beside the real releases: same artifacts, separate records
        self._releases = pathlib.Path(doc["releases"]) if doc.get("releases") else None
        self._validate()

    def _validate(self) -> None:
        for value in (str(self.root), str(self.python), str(self.releases), str(self.repo),
                      str(self.mars_local_python or ""),
                      *(str(v) for src in self.sources.values() for v in src.values())):
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


def gates_standing(acc: dict) -> dict:
    """`gate_state`, except that a pass recorded before TEST first verified the release is not
    a pass: it was said about something TEST had not run."""
    out = gate_state(acc)
    verified = [s for s in acc.get("served_in", []) if s["role"] == "test" and s.get("verified")]
    for gate, result in out.items():
        if result == "pass":
            last = [r for r in acc["records"] if r["gate"] == gate][-1]
            if not verified or last["at"] < verified[0]["at"]:
                out[gate] = "recorded before TEST verified the release"
    return out


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


def promotion_blockers(cfg: "Config", rid: str, seen: dict | None = None, *,
                       main_ahead_ok: str | None = None, emergency: str | None = None,
                       before_integration: bool = False) -> list[str]:
    """Everything that stands between release `rid` and production, in words. `status` and
    `promote` both read THIS, so status never says ready when promote would refuse.

    `main_ahead_ok` is the stated reason for running a commit that main has since moved past.
    `emergency` is the owner's words for an emergency exception: it waives ONLY that a source
    commit is not yet on its remote main, never an artifact, a gate or TEST.
    `before_integration` is `production` asking whether everything ELSE holds, so that nothing
    is pushed to main for a release that could not be promoted anyway."""
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
    # the contract: source on the remote main, artifacts from their commits
    for f in contract_findings(cfg, rid):
        if f["kind"] == "main" and ((emergency or "").strip() or before_integration):
            continue
        if f["kind"] == "ahead" and ((main_ahead_ok or "").strip() or (emergency or "").strip()):
            continue
        out.append(f["text"])
    # an emergency exception is a debt: nothing ordinary is promoted over it until main has it
    cur = cfg.serving(prod_name).get("current") or {}
    if cur.get("emergency") and cur.get("release") != rid and not (emergency or "").strip():
        try:
            owed = [f["text"] for f in contract_findings(cfg, cur["release"]) if f["kind"] == "main"]
        except Refused:
            owed = [f"release {cur['release']} is no longer on record"]
        if owed:
            out.append(f"{prod_name} is on {cur['release']} under an emergency exception whose source is "
                       f"still not on its remote main ({owed[0]}): reconcile main first")
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


# -- the deployment contract ---------------------------------------------------------
#
# "Deploy to DAY-TO-DAY" is the whole lifecycle (owner, 2026-11-19), and it is not complete
# until every one of these holds for the release production runs:
#
#   1 committed        2 integrated into main        3 main pushed, confirmed on the remote
#   4 artifacts built from those exact commits       5 tests and independent review passed
#   6 verified on TEST 7 promoted without interrupting work   8 production health and identity verified
#
# Everything below READS: the remote itself (`git ls-remote`, never a remembered
# `origin/main`), the commit's own tree, the release folder, the records. A label is never
# the evidence. TEST takes candidates from any branch; only production requires 2 and 3.

STAGES = ("committed", "integrated into main", "main pushed and confirmed on the remote",
          "artifacts built from those exact commits", "tests and independent review passed",
          "verified on TEST", "promoted to production without interrupting work",
          "production health and release identity verified")

#: how each binary is built from its source, and which components of a release it is
BINARIES = {
    "mars": {"source": "mars", "dir": "rust", "package": "mars", "files": {"mars": "mars.exe"}},
    "front": {"source": "mentis", "dir": ".", "package": "mentis-server",
              "files": {"front": "mentis-server.exe", "launcher": "mentis-launch.exe"}},
}
COMPONENT_SOURCE = {"front": "mentis", "launcher": "mentis", "mars": "mars"}

_REMOTE_SEEN: dict = {}


def _gitr(repo, *args, timeout=600) -> subprocess.CompletedProcess:
    return run(["git", "-C", repo, *args], check=False, timeout=timeout)


def remote_head(src: dict) -> str | None:
    """The commit the REMOTE's main is at now, asked of the remote. None when it cannot be read."""
    r = _gitr(src["repo"], "ls-remote", src["remote"], f"refs/heads/{src['branch']}", timeout=120)
    words = r.stdout.split()
    if r.returncode != 0 or not words or not re.fullmatch(r"[0-9a-f]{40}", words[0]):
        return None
    head = words[0]
    if _gitr(src["repo"], "cat-file", "-e", head + "^{commit}").returncode != 0:
        _gitr(src["repo"], "fetch", "--quiet", src["remote"], src["branch"])
    return head


def on_remote_main(src: dict | None, commit) -> dict:
    """Whether `commit` is on the remote's main: {'on_main': True | False | None (not known),
    'head', 'ahead' (what main has that the commit does not), 'why'}. Read once per run."""
    if not src:
        return {"on_main": None, "why": "no repository is configured for this source (`sources` in the environments file)"}
    where = f"{src['remote']}/{src['branch']} of {src['repo']}"
    if not commit or not re.fullmatch(r"[0-9a-f]{40}", str(commit)):
        return {"on_main": None, "why": f"no exact source commit is recorded ({commit!r})"}
    key = (os.path.normcase(str(src["repo"])), src["remote"], src["branch"], commit)
    if key in _REMOTE_SEEN:
        return _REMOTE_SEEN[key]
    head = remote_head(src)
    if not head:
        out = {"on_main": None, "why": f"{where} could not be read from the remote"}
    elif _gitr(src["repo"], "cat-file", "-e", commit + "^{commit}").returncode != 0:
        out = {"on_main": False, "head": head, "why": f"commit {commit[:12]} is not in {src['repo']}"}
    elif _gitr(src["repo"], "cat-file", "-e", head + "^{commit}").returncode != 0:
        out = {"on_main": None, "head": head, "why": f"{where} is at {head[:12]}, which could not be fetched"}
    else:
        r = _gitr(src["repo"], "merge-base", "--is-ancestor", commit, head)
        if r.returncode == 0:
            ahead = _gitr(src["repo"], "log", "--format=%h %s", f"{commit}..{head}").stdout.strip().splitlines()
            out = {"on_main": True, "head": head, "ahead": ahead}
        elif r.returncode == 1:
            out = {"on_main": False, "head": head,
                   "why": f"commit {commit[:12]} is not on {where} (the remote's main is at {head[:12]})"}
        else:
            out = {"on_main": None, "head": head, "why": f"git could not compare {commit[:12]} with {where}"}
    _REMOTE_SEEN[key] = out
    return out


def binaries(cfg: "Config") -> dict:
    """{sha256: where that binary came from}, kept beside the releases and written only by
    `build-binaries` (built here from one commit) and `attest-binary` (the owner's words)."""
    return read_json(cfg.releases / "BINARIES.json", {})


def code_matches_commit(cfg: "Config", rid: str) -> list[str]:
    """The release's `code/` against `git archive` of its commit, file by file. Only the built
    interface and BUILD.json may be there beyond the commit, and nothing may be missing."""
    rel = cfg.release(rid)
    commit = (rel.get("source") or {}).get("commit")
    repo = cfg.sources["mentis"]["repo"]
    if not commit or not re.fullmatch(r"[0-9a-f]{40}", str(commit)):
        return [f"the release records no exact source commit ({commit!r})"]
    r = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit], capture_output=True)
    if r.returncode != 0:
        return [f"commit {commit[:12]} could not be read from {repo}"]

    def ours(rel_path: str) -> bool:
        return not (rel_path == "code/BUILD.json" or rel_path.startswith("code/apps/fluid-web/dist/"))
    want = {}
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
        for m in t:
            if m.isfile() and ours("code/" + m.name):
                want["code/" + m.name] = hashlib.sha256(t.extractfile(m).read()).hexdigest()
    have = {k: v for k, v in (rel.get("files") or {}).items() if k.startswith("code/") and ours(k)}
    out = []
    for path in sorted(set(want) | set(have)):
        if want.get(path) != have.get(path):
            out.append(f"{path} is " + ("not in the commit" if path not in want else
                                        "missing from the release" if path not in have else
                                        "not the commit's content"))
    return [f"the release's code is not commit {commit[:12]}: {out[:3]}"
            + (f" and {len(out) - 3} more" if len(out) > 3 else "")] if out else []


def frontend_matches_commit(cfg: "Config", rid: str) -> list[str]:
    """The interface was built here from the release's commit, clean; or it is byte-for-byte
    the interface an intact release built from a commit whose apps/fluid-web is the same tree."""
    rel = cfg.release(rid)
    commit = (rel.get("source") or {}).get("commit")
    fe = (rel.get("components") or {}).get("frontend") or {}

    def built_clean(r: dict) -> bool:
        f = (r.get("components") or {}).get("frontend") or {}
        bi = f.get("build_identity") or {}
        return f.get("how") == "built" and bi.get("commit") == (r.get("source") or {}).get("commit") \
            and bi.get("dirty") is False
    if fe.get("how") == "built":
        return [] if built_clean(rel) else [
            "the interface's own build identity does not say it was built from a clean tree at "
            f"the release's commit ({(fe.get('build_identity') or {}).get('commit')!r})"]
    repo = cfg.sources["mentis"]["repo"]
    mine = _gitr(repo, "rev-parse", f"{commit}:apps/fluid-web").stdout.strip()
    for other in cfg.all_releases():
        of = (other.get("components") or {}).get("frontend") or {}
        if other["id"] == rid or of.get("digest") != fe.get("digest") or not built_clean(other):
            continue
        theirs = _gitr(repo, "rev-parse", f"{other['source']['commit']}:apps/fluid-web").stdout.strip()
        if mine and mine == theirs and not verify_release(cfg, other["id"]):
            return []
    return ["the interface was adopted (--dist-from), and no intact release built those bytes from "
            "a commit whose apps/fluid-web is the same tree as this release's"]


def contract_findings(cfg: "Config", rid: str) -> list[dict]:
    """Everything the contract requires of release `rid`'s SOURCE and ARTIFACTS that does not
    hold, each {'kind', 'text'}:

      main      a source commit is not on its remote main (or that could not be established)
      ahead     the remote main has commits the release does not
      artifact  an artifact is not shown to be built from its commit

    Only `main` and `ahead` can be waived, and only by an explicit emergency exception."""
    rel = cfg.release(rid)
    comps = rel.get("components") or {}
    commit = (rel.get("source") or {}).get("commit")
    out = []

    def source(label: str, name: str, c) -> None:
        got = on_remote_main(cfg.sources.get(name), c)
        if got["on_main"] is not True:
            out.append({"kind": "main", "text": f"{label}: {got['why']}"})
        elif got["ahead"] and (label == "the release's source" or name != "mentis"):
            # for Mentis the release's own commit is what is compared (its front is allowed to be
            # older, by the crates/ rule below); every other repository is compared by its binary
            out.append({"kind": "ahead", "text":
                        f"{name}: {cfg.sources[name]['remote']}/{cfg.sources[name]['branch']} has {len(got['ahead'])} "
                        f"commit(s) this release does not ({'; '.join(got['ahead'][:3])}"
                        + (" ..." if len(got["ahead"]) > 3 else "") + "): it was verified without them. "
                        "Build a release from main as it is and verify that on TEST, or say that this "
                        "older commit is the one to run with --main-ahead-ok"})
    source("the release's source", "mentis", commit)
    out += [{"kind": "artifact", "text": t} for t in code_matches_commit(cfg, rid)]
    out += [{"kind": "artifact", "text": t} for t in frontend_matches_commit(cfg, rid)]
    known = binaries(cfg)
    for comp, name in COMPONENT_SOURCE.items():
        sha = (comps.get(comp) or {}).get("sha256")
        entry = known.get(str(sha).lower()) if sha else None
        if not entry or entry.get("component") != comp:
            out.append({"kind": "artifact", "text":
                        f"{comp} ({str(sha)[:12]}) is not a binary this tool built from a commit "
                        f"(`build-binaries`), and the owner has not attested where it came from"})
            # with no commit known for it, nothing shows it to be on any main either
            out.append({"kind": "main", "text": f"{comp} ({str(sha)[:12]}): no source commit is known for "
                                                f"it, so it is not shown to be on any remote main"})
            continue
        source(f"{comp} (built from {str(entry.get('commit'))[:12]})", name, entry.get("commit"))
        if name == "mentis" and commit and entry.get("commit"):
            repo = cfg.sources["mentis"]["repo"]
            t1 = _gitr(repo, "rev-parse", f"{entry['commit']}:crates").stdout.strip()
            t2 = _gitr(repo, "rev-parse", f"{commit}:crates").stdout.strip()
            if not (t1 and t1 == t2) and not (comps.get("front") or {}).get("differs_ok"):
                out.append({"kind": "artifact", "text":
                            f"{comp} was built from {entry['commit'][:12]}, and crates/ at the release's "
                            f"commit is different, with no reason recorded for keeping the older one"})
    return out


def lifecycle_log(cfg: "Config", rid: str, stage: str, result: str, detail=None) -> None:
    """One line of what was attempted for a release and how it ended, appended and never rewritten."""
    path = cfg.root / "lifecycle" / f"{rid}.json"
    doc = read_json(path, {"release": rid, "events": []})
    doc["events"].append({"at": now(), "stage": stage, "result": result, "detail": detail})
    write_json(path, doc)


def lifecycle(cfg: "Config", rid: str, seen: dict | None = None) -> dict:
    """The eight stages for release `rid`, each established from evidence NOW: {'stages':
    [{'n', 'stage', 'done': True | False, 'evidence' | 'missing'}], 'complete', 'incomplete'}.
    Nothing here is remembered as done: a stage holds only while its evidence does."""
    rel = cfg.release(rid)
    acc = cfg.acceptance(rid)
    gates = gates_standing(acc)
    findings = contract_findings(cfg, rid)
    commit = (rel.get("source") or {}).get("commit")
    by = {k: [f["text"] for f in findings if f["kind"] == k] for k in ("main", "ahead", "artifact")}
    intact = verify_release(cfg, rid)
    prod_name = next(n for n, e in cfg.envs.items() if e["role"] == "production")
    cur = cfg.serving(prod_name).get("current") or {}
    served = [s for s in acc.get("served_in", []) if s["role"] == "test" and s.get("verified")]
    stages = []

    def stage(done: bool, evidence: str, missing) -> None:
        n = len(stages) + 1
        stages.append({"n": n, "stage": STAGES[n - 1], "done": bool(done),
                       **({"evidence": evidence} if done else {"missing": missing})})
    code = code_matches_commit(cfg, rid)
    stage(not code and not intact, f"the release's code is commit {str(commit)[:12]}, file for file",
          code or [f"the release folder is not intact: {intact[:2]}"])
    local = []
    for label, name, c in [("the release's source", "mentis", commit)] + [
            (comp, n, (binaries(cfg).get(str((rel["components"].get(comp) or {}).get("sha256")).lower()) or {}).get("commit"))
            for comp, n in COMPONENT_SOURCE.items()]:
        src = cfg.sources.get(name)
        ok = bool(src and c) and (
            _gitr(src["repo"], "merge-base", "--is-ancestor", str(c), f"refs/heads/{src['branch']}").returncode == 0
            or on_remote_main(src, c)["on_main"] is True)
        if not ok:
            local.append(f"{label}: {str(c)[:12] if c else 'no commit recorded'} is not on {name}'s main")
    stage(not local, "every source commit is on its repository's main", local)
    stage(not by["main"], "every source commit is on its remote main, asked of the remote now", by["main"])
    stage(not by["artifact"] and not intact,
          "code, interface and binaries are each shown to be built from their commits",
          by["artifact"] or [f"the release folder is not intact: {intact[:2]}"])
    need = [f"{g} is {gates[g]}" for g in ("tests", "review") if gates[g] != "pass"]
    stage(not need, "tests and independent review are recorded as passed", need)
    need = ([] if served else ["never served and verified in a test environment"]) + [
        f"{g} is {gates[g]}" for g in ("browser", "owner") if gates[g] != "pass"]
    stage(not need, f"served and verified in TEST ({served[-1]['at'] if served else ''}); browser and owner accepted", need)
    need = []
    if cur.get("release") != rid:
        need.append(f"{prod_name} is recorded as serving {cur.get('release')}")
    elif cur.get("runs_interrupted") is not False:
        need.append(f"the switch ended run(s) that were in flight: {cur.get('runs_ended_by_restart') or 'not listed'}"
                    if cur.get("runs_interrupted") else
                    "it could not be established from the record that the switch ended no run"
                    + (f" (open, unheld and too recently started to exclude: {cur['runs_not_excluded']})"
                       if cur.get("runs_not_excluded") else ""))
    stage(not need, f"promoted {cur.get('since')}, no run interrupted", need)
    look = (seen or {}).get(prod_name) or observe(cfg, prod_name)
    need = []
    if not look.get("up"):
        need.append(f"{prod_name} is not answering")
    elif look.get("serves_release") != rid:
        need.append(f"{prod_name} serves {look.get('serves_release') or 'no recorded release'}"
                    + (f" ({look.get('why_no_release')})" if look.get("why_no_release") else ""))
    elif not look.get("launched_from_release_folder") or look.get("notes"):
        need.append(f"{prod_name} is not running cleanly from the release folder: {look.get('notes')}")
    stage(not need, f"{prod_name} answers and its running content is this release, component by component", need)
    incomplete = [s["n"] for s in stages if not s["done"]]
    out = {"release": rid, "stages": stages, "complete": not incomplete, "incomplete": incomplete,
           "main_ahead": by["ahead"], "events": read_json(cfg.root / "lifecycle" / f"{rid}.json", {}).get("events", [])}
    if cur.get("release") == rid and cur.get("emergency"):
        out["emergency"] = {**cur["emergency"], "reconciled": not by["main"]}
    return out


def print_lifecycle(doc: dict) -> None:
    print(f"RELEASE LIFECYCLE {doc['release']}: "
          + ("COMPLETE: all eight conditions hold" if doc["complete"] else
             f"INCOMPLETE: {len(doc['incomplete'])} of 8 conditions do not hold "
             f"({', '.join(str(n) for n in doc['incomplete'])})"))
    for s in doc["stages"]:
        print(f"    {s['n']}. [{'done' if s['done'] else 'NOT DONE'}] {s['stage']}")
        for line in ([s["evidence"]] if s["done"] else s["missing"]):
            print(f"           {line}")
    for line in doc.get("main_ahead") or []:
        print(f"    NOTE: {line}")
    if doc.get("emergency"):
        e = doc["emergency"]
        print("    EMERGENCY EXCEPTION " + ("(since reconciled with main)" if e["reconciled"] else
                                            "IN FORCE: main reconciliation is still owed") + f": {e.get('words')}")


def cmd_lifecycle(cfg: "Config", a) -> int:
    doc = lifecycle(cfg, a.release)
    if a.json:
        print(json.dumps(doc, indent=1))
    else:
        print_lifecycle(doc)
    return 0 if doc["complete"] else 3


def can_integrate(cfg: "Config", name: str, commit: str) -> bool:
    """Whether `commit` still has to be pushed to its remote main (False: it is there already).
    Refuses, having changed nothing, when that could not be a fast-forward."""
    src = cfg.sources.get(name)
    was = on_remote_main(src, commit)
    where = f"{src['remote']}/{src['branch']} of {src['repo']}" if src else name
    if was["on_main"] is True:
        return False
    if was["on_main"] is None:
        raise Refused(f"{name}: {was['why']}")
    head = was["head"]
    if _gitr(src["repo"], "merge-base", "--is-ancestor", head, commit).returncode != 0:
        raise Refused(
            f"{where} is at {head[:12]}, which is not an ancestor of {commit[:12]}: main has advanced "
            f"since this candidate branched. Nothing was pushed. Merge with ordinary Git, build a "
            f"release from the merged commit and verify THAT on TEST: the merged code is not what "
            f"was tested")
    return True


def integrate(cfg: "Config", name: str, commit: str, pushed=None) -> dict:
    """Put exactly `commit` on its remote main, and only as a FAST-FORWARD: the remote's main
    must already be an ancestor of it. No merge is made and nothing else is pushed. When main
    has moved on, integrating means a merge, which makes a new commit nobody has tested: that
    is ordinary Git work followed by a new release and a new verification, never done here."""
    src = cfg.sources.get(name)
    where = f"{src['remote']}/{src['branch']} of {src['repo']}" if src else name
    if not can_integrate(cfg, name, commit):
        return {"source": name, "commit": commit, "already_on_remote_main": True}
    r = _gitr(src["repo"], "push", src["remote"], f"{commit}:refs/heads/{src['branch']}")
    if r.returncode != 0:
        raise Refused(f"the push to {where} was refused, nothing changed: {(r.stderr or r.stdout).strip()[-400:]}")
    if pushed:
        pushed({"source": name, "commit": commit, "pushed_to": where})   # on the record before anything else can fail
    _REMOTE_SEEN.clear()
    now_ = on_remote_main(src, commit)
    if now_["on_main"] is not True:
        raise Failed(f"{commit[:12]} WAS pushed to {where}, but the remote could not be read back to "
                     f"confirm it: {now_.get('why')}")
    # the local main follows only where that touches nobody's checkout: a main that is checked
    # out somewhere is that worktree's to move (`git merge --ff-only`), never this tool's
    branch = src["branch"]
    held = None
    for block in _gitr(src["repo"], "worktree", "list", "--porcelain").stdout.split("\n\n"):
        if f"branch refs/heads/{branch}" in block.splitlines():
            held = block.splitlines()[0].removeprefix("worktree ").strip()
    local = "left as it was"
    if held:
        local = f"left as it was: {branch} is checked out in {held}, which is that worktree's to fast-forward"
    elif _gitr(src["repo"], "merge-base", "--is-ancestor", f"refs/heads/{branch}", commit).returncode == 0:
        if _gitr(src["repo"], "branch", "-f", branch, commit).returncode == 0:
            local = "fast-forwarded"
    return {"source": name, "commit": commit, "pushed_to": where, "remote_main_now": now_["head"],
            "local_main": local}


def cmd_production(cfg: "Config", a) -> int:
    """The whole lifecycle for one release, in order, stopping at the first condition that does
    not hold and saying which: integrate and push (fast-forward only), confirm the remote,
    check artifacts, gates and TEST, promote without interrupting anything, verify production.
    It ends 0 only when all eight conditions hold."""
    rid = a.release
    cfg.release(rid)
    if not (a.owner_approved or "").strip():
        raise Refused("production: --owner-approved carries the owner's own words for this deployment")
    prod = next(n for n, e in cfg.envs.items() if e["role"] == "production")
    try:
        problems = verify_release(cfg, rid)
        if problems:
            raise Refused(f"release {rid} is not intact: {problems[:3]}")
        rel = cfg.release(rid)
        known = binaries(cfg)
        wanted = [("mentis", rel["source"]["commit"])]
        for comp, name in COMPONENT_SOURCE.items():
            entry = known.get(str((rel["components"].get(comp) or {}).get("sha256")).lower())
            if entry and entry.get("commit") and (name, entry["commit"]) not in wanted:
                wanted.append((name, entry["commit"]))
        # everything else first: nothing is pushed to main for a release that could not be
        # promoted anyway (an artifact, a gate, TEST), or while production has work in flight
        early = promotion_blockers(cfg, rid, main_ahead_ok=a.main_ahead_ok, before_integration=True)
        if early:
            raise Refused(f"release {rid} is not ready, and nothing was pushed: " + "; ".join(early))
        prod_env = cfg.env(prod)
        if _answering(prod_env):
            runs = _open_runs(prod_env)
            if runs is None or runs:
                raise Refused(f"{prod}: " + ("could not read whether runs are in flight" if runs is None
                                             else f"{runs} run(s) are in flight and a restart ends them")
                              + ". Nothing was pushed or stopped: wait for the work to finish")
        # every repository is checked before anything is pushed to any of them, and each push
        # is on the record the moment it happens: a later failure cannot hide an earlier push
        for name, commit in wanted:
            can_integrate(cfg, name, commit)
        done, sent = [], []

        def pushed_now(what: dict) -> None:
            sent.append(what)
            lifecycle_log(cfg, rid, "integrate and push", "pushed, confirmation pending", what)
        for name, commit in wanted:
            try:
                done.append(integrate(cfg, name, commit, pushed_now))
            except (Refused, Failed) as exc:
                pushed = sent
                lifecycle_log(cfg, rid, "integrate and push", "PARTIAL" if pushed else "refused",
                              {"completed": done, "failed": {"source": name, "commit": commit, "why": str(exc)}})
                if pushed:
                    raise Failed("INTEGRATION IS PARTIAL: " + "; ".join(
                        f"{d['commit'][:12]} WAS pushed to {d['pushed_to']}" for d in pushed)
                        + f"; then {name} failed: {exc}. Nothing was switched") from exc
                raise
            lifecycle_log(cfg, rid, "integrate and push", "done", done[-1])
        blockers = promotion_blockers(cfg, rid, main_ahead_ok=a.main_ahead_ok)
        if blockers:
            raise Refused(f"release {rid} is not ready: " + "; ".join(blockers))
        lifecycle_log(cfg, rid, "checks before promotion", "passed", None)
        result = switch(cfg, prod, rid, why="promoted from TEST (full lifecycle)", approved=a.owner_approved,
                        interrupt_runs=False, migrate=a.migrate,
                        extra={"main_ahead_ok": a.main_ahead_ok} if a.main_ahead_ok else None)
        lifecycle_log(cfg, rid, "promote", "done", result)
    except Refused as exc:
        lifecycle_log(cfg, rid, "production", "refused, nothing was switched", str(exc))
        print_lifecycle(lifecycle(cfg, rid))
        raise
    except Failed as exc:
        lifecycle_log(cfg, rid, "production", "FAILED", str(exc))
        print_lifecycle(lifecycle(cfg, rid))
        raise
    _REMOTE_SEEN.clear()
    doc = lifecycle(cfg, rid)
    lifecycle_log(cfg, rid, "confirm", "complete" if doc["complete"] else "INCOMPLETE", doc["incomplete"])
    print(json.dumps(result, indent=1))
    print_lifecycle(doc)
    if not doc["complete"]:
        raise Failed(f"{prod} now serves {rid}, but the deployment is NOT complete: conditions "
                     f"{doc['incomplete']} do not hold (above)")
    return 0


def cmd_build_binaries(cfg: "Config", a) -> int:
    """Build one component's binaries from exactly one commit of its repository and record,
    beside the releases, which commit each resulting file is. `git archive` of the commit,
    `cargo build --release --locked`: no working tree is involved."""
    spec = BINARIES[a.component]
    src = cfg.sources.get(spec["source"])
    if not src:
        raise Refused(f"no repository is configured for {spec['source']} (`sources` in the environments file)")
    r = _gitr(src["repo"], "rev-parse", f"{a.commit}^{{commit}}")
    if r.returncode != 0:
        raise Refused(f"{a.commit} is not a commit in {src['repo']}")
    commit = r.stdout.strip()
    out = cfg.root / "binaries" / f"{a.component}-{commit[:12]}"
    if out.exists():
        raise Refused(f"{out} already exists: {a.component} was already built from {commit[:12]}")
    cargo = shutil.which("cargo")
    if not cargo:
        raise Refused("cargo is not on PATH")
    work = cfg.root / "build" / f"{a.component}-{commit[:12]}"
    if work.exists():
        _rm_tree(work)
    (work / "src").mkdir(parents=True)
    try:
        tar = subprocess.run(["git", "-C", str(src["repo"]), "archive", "--format=tar", commit],
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(work / "src", filter="data")
        env = {**os.environ, "CARGO_TARGET_DIR": str(work / "target")}
        run([cargo, "build", "--release", "--locked", "-p", spec["package"]],
            cwd=work / "src" / spec["dir"], env=env, timeout=7200)
        stage = out.with_name(out.name + ".staging")
        if stage.exists():
            _rm_tree(stage)
        stage.mkdir(parents=True)
        entries = {}
        for comp, name in spec["files"].items():
            shutil.copy2(work / "target" / "release" / name, stage / name)
            entries[sha_file(stage / name)] = {
                "component": comp, "file": name, "repository": str(src["repo"]), "commit": commit,
                "how": f"built by this tool: git archive {commit}; cargo build --release --locked -p {spec['package']}",
                "cargo": run([cargo, "--version"]).stdout.strip(), "at": now()}
        write_json(stage / "PROVENANCE.json", {"commit": commit, "source_commit": commit, "files": entries})
        known = binaries(cfg)
        known.update(entries)
        write_json(cfg.releases / "BINARIES.json", known)
        os.rename(stage, out)
    finally:
        if work.exists():
            _rm_tree(work)
    print(json.dumps({"built": str(out), "commit": commit,
                      "files": {v["file"]: k for k, v in entries.items()}}, indent=1))
    return 0


def cmd_attest_binary(cfg: "Config", a) -> int:
    """Record, in the owner's own words, which commit an EXISTING binary was built from. It is
    kept as an attestation and every report says so: it is not a build this tool made."""
    if not (a.owner_approved or "").strip():
        raise Refused("attest-binary: --owner-approved carries the owner's own words")
    if a.component not in COMPONENT_SOURCE:
        raise Refused(f"component is one of {', '.join(COMPONENT_SOURCE)}")
    src = cfg.sources.get(COMPONENT_SOURCE[a.component])
    if not src:
        raise Refused(f"no repository is configured for {COMPONENT_SOURCE[a.component]}")
    r = _gitr(src["repo"], "rev-parse", f"{a.commit}^{{commit}}")
    if r.returncode != 0:
        raise Refused(f"{a.commit} is not a commit in {src['repo']}")
    if not os.path.isfile(a.file):
        raise Refused(f"{a.file} does not exist")
    sha = sha_file(a.file)
    known = binaries(cfg)
    if sha in known:
        raise Refused(f"{sha[:12]} is already recorded: {known[sha]['how']}")
    known[sha] = {"component": a.component, "file": os.path.basename(a.file), "repository": str(src["repo"]),
                  "commit": r.stdout.strip(), "at": now(),
                  "how": "ATTESTED by the owner, not built by this tool", "attested": a.owner_approved}
    write_json(cfg.releases / "BINARIES.json", known)
    print(json.dumps({sha: known[sha]}, indent=1))
    return 0


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
        known = binaries(cfg)
        named = {}
        for comp, name in (("front", "mentis-server.exe"), ("launcher", "mentis-launch.exe"), ("mars", "mars.exe")):
            entry = known.get(sha_file(bindir / name))
            if not entry or entry.get("component") != comp:
                raise Refused(
                    f"{name} ({sha_file(bindir / name)[:12]}) is not a binary this tool knows the source "
                    f"commit of: a release names the exact commit of everything in it. Build it with "
                    f"`build-binaries --component {'mars' if comp == 'mars' else 'front'} --commit C` and "
                    f"pass --front-from / --mars-from, or have the owner attest it (`attest-binary`)")
            named[comp] = entry
        front_src = named["front"]["commit"]
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
                      "crates_same_as_commit": same, "differs_ok": a.front_differs_ok or None,
                      "how": named["front"]["how"]},
            "launcher": {"sha256": sha_file(bindir / "mentis-launch.exe"),
                         "source_commit": named["launcher"]["commit"], "how": named["launcher"]["how"]},
            "mars": {"sha256": sha_file(bindir / "mars.exe"), "commit": named["mars"]["commit"],
                     "version": mars_prov.get("version"), "how": named["mars"]["how"]},
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
    report = {"observed_at": now(), "environments": seen, "candidate": None, "production_lifecycle": None}
    prod = [s for s in seen.values() if s["role"] == "production"]
    prod_release = prod[0].get("serves_release") if prod else None
    if prod_release:
        report["production_lifecycle"] = lifecycle(cfg, prod_release, seen)
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
        if s["role"] == "production" and rid:
            life = report["production_lifecycle"]
            print("    release lifecycle: " + ("COMPLETE (all eight conditions hold)" if life["complete"] else
                  f"INCOMPLETE, conditions {', '.join(str(n) for n in life['incomplete'])} do not hold "
                  f"(`lifecycle {rid}` says which and why)"))
            if (life.get("emergency") or {}).get("reconciled") is False:
                print("    EMERGENCY EXCEPTION IN FORCE: its source is still not on the remote main")
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
    rows = _open_rows(env)
    return None if rows is None else sum(1 for r in rows if r.get("held_here"))


def _open_rows(env: dict):
    """The record's open runs as the server lists them, or None when it could not say. An
    answer that carries `why_not` is the server saying it could not ask: that is not zero."""
    try:
        got = http_json(f"http://127.0.0.1:{env['port']}/api/working")
    except Exception:                                           # noqa: BLE001
        return None
    if not isinstance(got, dict) or got.get("why_not") or not isinstance(got.get("open"), list):
        return None
    return got["open"]


def _unheld(env: dict):
    """{run id: when it started} for runs the record calls open and no process holds, or None
    when not known. A run that a restart ended is exactly this afterwards: open, held by nobody."""
    rows = _open_rows(env)
    return None if rows is None else {str(r.get("run")): r.get("started_at") for r in rows
                                      if not r.get("held_here")}


def _server_started(env: dict):
    """When the server process answering for `env` started (epoch seconds), or None."""
    try:
        at = (http_json(f"http://127.0.0.1:{env['port']}/api/server").get("process") or {}).get("started_at")
    except Exception:                                           # noqa: BLE001
        return None
    return at if isinstance(at, (int, float)) else None


def ended_by_restart(before: dict | None, after: dict | None, server_started):
    """What a restart did to runs, from the record read just before the stop and again after
    the start: (ended, not_excluded), or (None, None) when either could not be read.

    `ended`: open and unheld now, and not unheld before: they were held, or began, and the
    restart ended them.

    `not_excluded`: unheld before AND after, and started while the stopped server process was
    alive (or at no readable time, or that process's start is not known). A dispatch records
    its run as started BEFORE the process takes hold of it, so such a run may have been taken
    hold of after it was read and then killed, and nothing read from outside the server can say
    it was not. Only a run that started BEFORE that server process existed is excluded: nothing
    in that process can have been about to hold it."""
    if before is None or after is None:
        return None, None
    ended = sorted(r for r in after if r not in before)
    unsure = []
    for r in after:
        if r in before:
            at = before[r] if before[r] is not None else after[r]
            if not isinstance(at, (int, float)) or not isinstance(server_started, (int, float)) \
                    or at >= server_started:
                unsure.append(r)
    return ended, sorted(unsure)


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
           interrupt_runs: bool, migrate: bool, extra: dict | None = None) -> dict:
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
    runs = 0
    if was_up:
        runs = _open_runs(env)
        if (runs is None or runs) and not interrupt_runs:
            raise Refused(f"{name}: " + ("could not read whether runs are in flight" if runs is None else
                                         f"{runs} run(s) are in flight and a restart ends them")
                          + ". Nothing was stopped: wait for the work to finish. Interrupting it needs "
                            "--interrupt-runs AND --owner-approved with the owner's words for that")
        if (runs is None or runs) and not (approved or "").strip():
            raise Refused(f"{name}: --interrupt-runs would end "
                          + ("work that could not be counted" if runs is None else f"{runs} run(s)")
                          + ". That needs explicit authorization: --owner-approved with the owner's "
                            "words for interrupting them. Nothing was stopped")
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
    if was_up and not interrupt_runs:
        # planning took time: ask again at the last moment before anything is stopped. This
        # narrows the window to the instant between this answer and the stop; closing it
        # entirely needs the server itself to refuse new work while it drains, which it cannot yet
        runs = _open_runs(env)
        if runs is None or runs:
            raise Refused(f"{name}: " + ("could not read whether runs are in flight" if runs is None else
                                         f"{runs} run(s) started while this was being prepared")
                          + ". Nothing was stopped: wait for the work to finish")
    # what the record already calls open and unheld, so that what the restart itself ends can
    # be told apart afterwards
    unheld_before = _unheld(env) if was_up else {}
    server_started = _server_started(env) if was_up else None
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
        # WHAT THE RESTART ACTUALLY ENDED, read back from the record: a run that began in the
        # instant between the last count and the stop is open and held by nobody now. "No run
        # was interrupted" is said only when this could be read and found none
        if was_up:
            ended, unsure = ended_by_restart(unheld_before, _unheld(env), server_started)
        elif said and said != ["nothing was running"]:
            # it was not answering, so nothing could be read from it, and yet processes of its
            # were alive and were stopped: what they held is not known
            ended, unsure = None, None
        else:
            # nothing of it was running: no run could have been ended, whatever an old record holds
            ended, unsure = [], []
        entry = {"release": rid, "since": stamp, "why": why, "approved": approved,
                 "previous": before, "migrated": migrated, "gap_seconds": gap,
                 "runs_in_flight": runs, "runs_ended_by_restart": ended,
                 "runs_not_excluded": unsure,
                 # True: something was ended (or it was explicitly told to). False ONLY when the
                 # record was read back, nothing was ended, and nothing young was left in doubt.
                 # Otherwise None: not known, which is never reported as "no run interrupted"
                 "runs_interrupted": True if (interrupt_runs and (runs is None or runs)) or ended
                 else (False if ended is not None and not unsure else None),
                 **(extra or {})}
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
            "migrated": migrated, "stop": said, "runs_ended_by_restart": ended}


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
                            approved=a.owner_approved, interrupt_runs=a.interrupt_runs,
                            migrate=a.migrate), indent=1))
    return 0


def cmd_promote(cfg: Config, a) -> int:
    name = a.environment or next(n for n, e in cfg.envs.items() if e["role"] == "production")
    env = cfg.env(name)
    if env["role"] != "production":
        raise Refused(f"{name} is not production: use deploy")
    cfg.release(a.release)
    if a.interrupt_runs:
        raise Refused("a promotion never interrupts runs: wait until production has none in flight")
    main_ahead_ok, emergency = getattr(a, "main_ahead_ok", None), getattr(a, "emergency", None)
    blockers = promotion_blockers(cfg, a.release, main_ahead_ok=main_ahead_ok, emergency=emergency)
    if blockers:
        lifecycle_log(cfg, a.release, "promote", "refused, nothing was switched", blockers)
        raise Refused(f"release {a.release} is not ready: " + "; ".join(blockers))
    extra = {}
    if (main_ahead_ok or "").strip():
        extra["main_ahead_ok"] = main_ahead_ok
    if (emergency or "").strip():
        # AN EXPLICIT EXCEPTION, on the record with what it waived; `status`, `lifecycle` and the
        # next promotion all keep saying so until the source is on its remote main
        extra["emergency"] = {"words": emergency, "at": now(), "waived": [
            f["text"] for f in contract_findings(cfg, a.release) if f["kind"] in ("main", "ahead")]}
    result = switch(cfg, name, a.release, why="promoted from TEST" + (" (EMERGENCY EXCEPTION)" if extra.get("emergency") else ""),
                    approved=a.owner_approved, interrupt_runs=False, migrate=a.migrate, extra=extra or None)
    lifecycle_log(cfg, a.release, "promote", "done", result)
    print(json.dumps(result, indent=1))
    _REMOTE_SEEN.clear()
    doc = lifecycle(cfg, a.release)
    print_lifecycle(doc)
    if not doc["complete"]:
        raise Failed(f"{name} now serves {a.release}, but the deployment is NOT complete: conditions "
                     f"{doc['incomplete']} do not hold (above)")
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
    if len((a.by or "").strip()) < 2 or len((a.evidence or "").strip()) < 8:
        raise Refused("a gate is recorded by somebody, about something: --by names who (for `review`, "
                      "a reviewer other than the author; for `owner`, the owner), and --evidence says "
                      "what was run or read and where its output is. Neither can be blank")
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
    p.add_argument("--main-ahead-ok", help="why a commit that main has moved past is the one to run")
    p.add_argument("--emergency", help="the owner's words for an emergency exception: the source "
                                       "is not on its remote main yet, and main is reconciled after")
    pr = sub.add_parser("production")
    pr.add_argument("release")
    pr.add_argument("--owner-approved")
    pr.add_argument("--migrate", action="store_true")
    pr.add_argument("--main-ahead-ok")
    lc = sub.add_parser("lifecycle")
    lc.add_argument("release")
    lc.add_argument("--json", action="store_true")
    bb = sub.add_parser("build-binaries")
    bb.add_argument("--component", required=True, choices=sorted(BINARIES))
    bb.add_argument("--commit", required=True)
    ab = sub.add_parser("attest-binary")
    ab.add_argument("file")
    ab.add_argument("--component", required=True)
    ab.add_argument("--commit", required=True)
    ab.add_argument("--owner-approved")
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
                "record": cmd_record, "snapshot": cmd_snapshot, "production": cmd_production,
                "lifecycle": cmd_lifecycle, "build-binaries": cmd_build_binaries,
                "attest-binary": cmd_attest_binary}[a.cmd](cfg, a)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except Failed as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
