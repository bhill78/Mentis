"""Build `Mentis-Setup-<version>-<commit12>.exe` from this checkout's HEAD.

    python tools/build_windows_installer.py [--out DIR] [--cache DIR] [--makensis EXE] [--commit REV]
    python tools/build_windows_installer.py --check     what must hold, no build
    python tools/build_windows_installer.py --relock    rewrite requirements.lock

Run it from the repository's virtual environment; it needs Git, Node and network
(or a filled --cache), and the target needs none of them.

WHAT IS BUILT. In order, in `<out>/work-<commit12>/`:

1. HEAD (or --commit) is cloned, so what is built is a commit: uncommitted changes
   in this checkout are not in it, and the result says if there were any.
2. `builds` in tools/installer/manifest.json run in that clone (Fluid).
3. The stage, which is one release: `runtime\\` is python.org's embeddable Python (tools/installer/
   lock.json, checked by hash) with the wheels of tools/installer/requirements.lock
   pre-installed, so the target never runs pip; its ._pth puts `app\\` on the path
   and makes it ignore PYTHONPATH, PYTHONHOME and the registry. `app\\` is the
   manifest's `payload`, laid out as a checkout is, because the server finds Fluid
   and the bridge finds the code relative to `mentis\\`.
4. The stage is run: it imports what the server needs, and the render check reads
   the built Fluid. Its code is compiled, because a release is locked read-only once
   installed and could not write its own __pycache__ then. Its BUILD.json says which
   Brain schema it reads, for update and rollback to plan with.
5. NSIS (tools/installer/mentis.nsi) packs the stage. The exe is also the package
   `mentis.cmd update` takes, and it unpacks into `releases\\<version>+<commit12>`.

PAYLOAD AND LAUNCH ARE DECLARED, IN ONE PLACE: tools/installer/manifest.json.
Nothing here or in the launcher names what is carried or started. `problems()` is
everything about a source tree that would make the build, or the install, fail. It
runs first here and alone in tests/test_windows_installer.py.

Prints one JSON object. Exit 0 built, 1 refused or failed. docs/windows-installer.md
says how to build and prove it.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
INSTALLER = pathlib.PurePosixPath("tools/installer")
PLATFORM = ("--platform", "win_amd64", "--python-version", "3.12",
            "--implementation", "cp", "--only-binary=:all:")
PTH = "python312._pth"
#: paths relative to runtime\; `import site` reads Lib\site-packages
PTH_LINES = ("python312.zip", ".", r"Lib\site-packages", r"..\app", "import site")
#: third-party modules mentis imports -> the project in pyproject.toml that gives them
IMPORT_PROJECTS = {"regex": "regex", "pypdf": "pypdf", "psutil": "psutil",
                   "quickjs": "quickjs-ng", "acp": "agent-client-protocol"}
#: standard modules python.org leaves out of the embeddable package
NOT_IN_EMBEDDABLE = {"tkinter", "idlelib", "turtle", "turtledemo", "ensurepip", "venv"}
#: run by the built stage, before it is packed
SELFTEST = (
    "import sqlite3, ssl, ctypes, zlib, json, psutil, regex, pypdf, quickjs, acp\n"
    "import launcher, updater, mentis.migrate, mentis.readonly\n"
    "import mentis.web, mentis.bootstrap.new_brain\n"
    "from mentis.conversation import render_check\n"
    "got = render_check.check('# check')\n"
    "assert got.get('checked') is True, got\n"
    "print(render_check.BUNDLE)\n")
#: what update and rollback must know of a release to plan against a Brain
SCHEMA = (
    "import json\n"
    "from mentis.spine import migrations as m\n"
    "ms = m.migrations()\n"
    "print(json.dumps({'schema_target': m.target(), 'migrations': [x.id for x in ms],\n"
    "                  'min_reader_after': max(x.min_reader for x in ms)}))\n")


class Refused(Exception):
    pass


def _run(args, cwd=REPO, env=None) -> str:
    print("> " + " ".join(str(a) for a in args), file=sys.stderr, flush=True)
    r = subprocess.run([str(a) for a in args], cwd=cwd, env=env, text=True,
                       capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Refused(f"{args[0]} {args[1] if len(args) > 1 else ''} exited "
                      f"{r.returncode}\n{((r.stderr or '') + (r.stdout or ''))[-3000:]}")
    return r.stdout


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(repo: pathlib.Path, name: str) -> dict:
    return json.loads((repo / INSTALLER / name).read_text("utf-8"))


def _pins(repo: pathlib.Path) -> dict:
    """{project: version} of pyproject's dependencies."""
    deps = tomllib.loads((repo / "pyproject.toml").read_text("utf-8"))["project"]["dependencies"]
    out = {}
    for dep in deps:
        m = re.fullmatch(r"([A-Za-z0-9._-]+)==([^\s;]+)\s*(;.*)?", dep)
        out[_norm(m[1]) if m else dep] = m[2] if m else None
    return out


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked(repo: pathlib.Path) -> dict:
    """{project: version} of requirements.lock."""
    text = (repo / INSTALLER / "requirements.lock").read_text("utf-8")
    return {_norm(m[1]): m[2] for m in re.finditer(r"(?m)^([A-Za-z0-9._-]+)==(\S+)", text)}


def _imports(repo: pathlib.Path):
    """(module root, file) for every absolute import under mentis/, lazy ones too."""
    for f in sorted((repo / "mentis").rglob("*.py")):
        for node in ast.walk(ast.parse(f.read_text("utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                yield name, f


def _update_problems(repo: pathlib.Path, man: dict) -> list:
    """What `mentis.cmd update` and `rollback` take from the tree and the manifest."""
    out = []
    for module, what in (("mentis/migrate.py", "applies a Brain migration"),
                         ("mentis/brain/__main__.py", "verifies and backs up the Brain"),
                         ("mentis/readonly.py", "locks a release"),
                         ("mentis/spine/brainlock.py", "says who has the Brain open")):
        if not (repo / module).is_file():
            out.append(f"update and rollback need {module}, which {what}; it is gone")
    migrations = repo / "mentis/spine/migrations.py"
    if migrations.is_file():
        text = migrations.read_text("utf-8")
        for name in ("def status_of(", "def migrations(", "def target("):
            if name not in text:
                out.append(f"update plans with mentis.spine.migrations {name[4:-1]}, which is gone")
    web = "".join(f.read_text("utf-8") for f in sorted((repo / "mentis/web").glob("*.py"))) \
        if (repo / "mentis/web").is_dir() else ""
    for key in ("identity", "working"):
        if not man.get(key):
            out.append(f"manifest.json: `{key}` is what update asks the running server")
    if not man.get("health"):
        out.append("manifest.json: `health` is how update knows the new release is healthy")
    for url in [man.get("identity"), man.get("working"), *man.get("health", [])]:
        path = "/" + str(url).split("/", 3)[3] if url and str(url).count("/") >= 3 else None
        if path and path != "/" and f'"{path}"' not in web:
            out.append(f"manifest.json names {path}, which mentis.web does not answer")
    if '"release"' not in web:
        out.append("update reads `release` from /api/server, and mentis.web no longer gives it")
    return out


def problems(repo: pathlib.Path = REPO) -> list:
    """Everything about this source tree that would stop a build from main being
    installable. Empty means it should build; only a real build proves it does."""
    repo = pathlib.Path(repo)
    out = []
    man, lock = load(repo, "manifest.json"), load(repo, "lock.json")
    if man.get("format") != 1:
        out.append("manifest.json: not format 1")
    builds = man.get("builds", {})
    for row in man.get("payload", []):
        src, to = row.get("from", ""), row.get("to", "")
        parts = pathlib.PurePosixPath(to).parts
        if not parts or parts[0] != "app" or ".." in parts:
            out.append(f"payload {src}: `to` must be under app/, not {to!r}")
        built = row.get("built_by")
        if built:
            if built not in builds:
                out.append(f"payload {src}: no build named {built!r}")
            elif not (repo / builds[built]["cwd"] / "package.json").is_file():
                out.append(f"build {built}: nothing to build at {builds[built]['cwd']}")
        elif not (repo / src).exists():
            out.append(f"payload {src}: not in this tree")
    carried = {pathlib.PurePosixPath(r.get("from", "")) for r in man.get("payload", [])}
    for must in ("mentis", INSTALLER / "launcher.py", INSTALLER / "updater.py", INSTALLER / "manifest.json"):
        if pathlib.PurePosixPath(must) not in carried:
            out.append(f"payload: must carry {must}")
    nsi = repo / INSTALLER / "mentis.nsi"
    if not nsi.is_file():
        out.append("tools/installer/mentis.nsi is missing")
    else:
        text = nsi.read_text("utf-8")
        for needed, what in (("/EXTRACT=", "`mentis.cmd update` unpacks the exe with it"),
                             ("arrive", "the exe hands over to the release's own launcher with it"),
                             ("/NOFULLBACKUP", "the exe can no longer decline the full backup"),
                             ("--backup-question", "the wizard can no longer ask about the full backup"),
                             ('/remove:d', "an uninstall cannot delete a release still locked read-only")):
            if needed not in text:
                out.append(f"mentis.nsi has no {needed}: {what}")
    if not (repo / "mentis/bootstrap/__main__.py").is_file():
        out.append("the launcher's setup runs `python -m mentis.bootstrap`, which is gone")
    out.extend(_update_problems(repo, man))

    def carries(path: pathlib.PurePosixPath) -> bool:
        return any(path == c or c in path.parents for c in carried)

    # what is started must be there, and take these arguments
    ports = man.get("ports", {})
    known = {"python", "root", "release", "brain", "workspace", "mars", *ports}
    if not man.get("launch"):
        out.append("manifest.json: `launch` is empty; nothing would start")
    if "port" not in ports:
        out.append("manifest.json: `ports` must name `port`, the one people open")
    for row in man.get("launch", []):
        for text in [*row.get("command", []), row.get("ready", "")]:
            for used in re.findall(r"\{(\w+)\}", text):
                if used not in known:
                    out.append(f"launch {row.get('name')}: unknown {{{used}}}")
        cmd = row.get("command", [])
        if "-m" in cmd:
            module = cmd[cmd.index("-m") + 1]
            base = repo / pathlib.PurePosixPath(*module.split("."))
            if not ((base / "__main__.py").is_file() or base.with_suffix(".py").is_file()):
                out.append(f"launch {row.get('name')}: {module} is not in this tree")
            flags = {a for a in cmd if a.startswith("--")}
            if module == "mentis.web":
                entry = (base / "__init__.py").read_text("utf-8")
                for flag in flags:
                    if f'"{flag}"' not in entry:
                        out.append(f"launch {row.get('name')}: mentis.web takes no {flag}")

    # what the server imports must be in the install
    pins, locked = _pins(repo), _locked(repo)
    for project, version in pins.items():
        if version is None:
            out.append(f"pyproject dependency not pinned exactly: {project}")
        elif locked.get(project) != version:
            out.append(f"requirements.lock has {project}=={locked.get(project)}, pyproject "
                       f"{version}: run tools/build_windows_installer.py --relock")
    for name, f in _imports(repo):
        root = name.split(".")[0]
        where = f.relative_to(repo).as_posix()
        if root == "mentis":
            continue
        if root in NOT_IN_EMBEDDABLE:
            out.append(f"{where} imports {root}, which the embeddable Python does not have")
        elif root in sys.stdlib_module_names:
            continue
        elif root == "tools":
            path = pathlib.PurePosixPath(*name.split(".")).with_suffix(".py")
            if not carries(path):
                out.append(f"{where} imports {name}; add {path} to the payload")
        elif _norm(IMPORT_PROJECTS.get(root, root)) not in locked:
            out.append(f"{where} imports {root}, which no locked project gives: add it to "
                       "pyproject, IMPORT_PROJECTS and --relock")
    for name in ("python", "nsis"):
        pin = lock.get(name, {})
        if not re.fullmatch(r"[0-9a-f]{64}", str(pin.get("sha256"))) or not pin.get("url"):
            out.append(f"lock.json: {name} is not pinned by url and sha256")
    return out


# -- fetching ---------------------------------------------------------------------

def fetch(pin: dict, cache: pathlib.Path) -> pathlib.Path:
    """The pinned zip in `cache`, checked. A mismatch is refused and not kept."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / pin["url"].rsplit("/", 1)[1]
    if path.is_file() and sha256(path) == pin["sha256"]:
        return path
    part = path.with_name(path.name + ".partial")
    print(f"> fetch {pin['url']}", file=sys.stderr, flush=True)
    with urllib.request.urlopen(pin["url"], timeout=120) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    got = sha256(part)
    if got != pin["sha256"] or part.stat().st_size != pin["size"]:
        part.unlink()
        raise Refused(f"{path.name} is not what lock.json pins: sha256 {got}")
    os.replace(part, path)
    return path


def unpack(zip_path: pathlib.Path, dest: pathlib.Path) -> None:
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = pathlib.PurePosixPath(info.filename).parts
            if ".." in parts or info.filename.startswith("/") or ":" in info.filename:
                raise Refused(f"{zip_path.name}: unsafe entry {info.filename!r}")
        z.extractall(dest)


def makensis(lock: dict, cache: pathlib.Path) -> pathlib.Path:
    pin = lock["nsis"]
    home = cache / f"nsis-{pin['version']}-{pin['sha256'][:12]}"
    exe = home / pathlib.PurePosixPath(pin["makensis"])
    if not exe.is_file():
        tmp = home.with_name(home.name + ".partial")
        if tmp.exists():
            shutil.rmtree(tmp)
        unpack(fetch(pin, cache), tmp)
        os.replace(tmp, home)
    return exe


# -- the stage --------------------------------------------------------------------

def _pip(*args) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "PYTHON"))}
    _run([sys.executable, "-m", "pip", *args, "--disable-pip-version-check",
          "--no-input", "-q"], env=env)


def relock(repo: pathlib.Path = REPO) -> dict:
    """Rewrite requirements.lock: pyproject's dependencies and what they need, for
    CPython 3.12 on win_amd64, at the versions this environment tests with."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "PYTHON"))}
        frozen = subprocess.run([sys.executable, "-m", "pip", "freeze"], env=env,
                                capture_output=True, text=True, check=True).stdout
        (tmp / "c.txt").write_text(frozen, "utf-8")
        deps = tomllib.loads((repo / "pyproject.toml").read_text("utf-8"))["project"]["dependencies"]
        _pip("install", "--dry-run", "--ignore-installed", "--report", str(tmp / "r.json"),
             *PLATFORM, "--target", str(tmp / "x"), "-c", str(tmp / "c.txt"), *deps)
        report = json.loads((tmp / "r.json").read_text("utf-8"))
    rows = sorted((_norm(i["metadata"]["name"]), i["metadata"]["version"],
                   i["download_info"]["archive_info"]["hashes"]["sha256"])
                  for i in report["install"])
    text = ("# Generated by tools/build_windows_installer.py --relock: what the install\n"
            "# carries, for CPython 3.12 on win_amd64. Do not edit by hand.\n"
            + "".join(f"{n}=={v} \\\n    --hash=sha256:{h}\n" for n, v, h in rows))
    path = repo / INSTALLER / "requirements.lock"
    path.write_bytes(text.encode("utf-8"))
    return {"requirements_lock": str(path), "projects": len(rows)}


def runtime(lock: dict, stage: pathlib.Path, src: pathlib.Path, cache: pathlib.Path) -> None:
    rt = stage / "runtime"
    unpack(fetch(lock["python"], cache), rt)
    for stale in rt.glob("*._pth"):
        stale.unlink()
    (rt / PTH).write_bytes(("\r\n".join(PTH_LINES) + "\r\n").encode("ascii"))
    req = src / INSTALLER / "requirements.lock"
    wheels = stage.parent / "wheels"
    _pip("download", "--no-deps", "--require-hashes", *PLATFORM, "-d", wheels, "-r", req)
    _pip("install", "--no-index", "--find-links", wheels, "--no-compile", "--no-deps",
         "--require-hashes", *PLATFORM, "--target", rt / "Lib" / "site-packages", "-r", req)
    for left in ("bin", "Scripts"):
        shutil.rmtree(rt / "Lib" / "site-packages" / left, ignore_errors=True)


def copy_payload(man: dict, src: pathlib.Path, stage: pathlib.Path) -> None:
    for row in man["payload"]:
        origin, to = src / row["from"], stage / pathlib.PurePosixPath(row["to"])
        if origin.is_dir():
            shutil.copytree(origin, to, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif origin.is_file():
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, to)
        else:
            raise Refused(f"payload {row['from']}: not in the built tree")
        for name in row.get("must_hold", ()):
            if not (to / name).is_file():
                raise Refused(f"payload {row['from']}: the build made no {name}")


def scrubbed_env() -> dict:
    """What a machine without Python, Node or Git gives a process."""
    root = os.environ.get("SystemRoot", r"C:\Windows")
    keep = ("SystemRoot", "SystemDrive", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
            "TEMP", "TMP", "ComSpec", "HOMEDRIVE", "HOMEPATH", "USERNAME", "PATHEXT")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PATH"] = rf"{root}\System32;{root}"
    return env


def selftest(stage: pathlib.Path) -> str:
    with tempfile.TemporaryDirectory() as cwd:
        r = subprocess.run([stage / "runtime" / "python.exe", "-I", "-B", "-X", "utf8", "-c", SELFTEST],
                           cwd=cwd, env=scrubbed_env(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if r.returncode:
        raise Refused(f"the built stage does not run:\n{r.stderr[-3000:]}")
    return r.stdout.strip()


#: the root's `mentis.cmd`: runs the release `state\current` names. Not in a release.
MENTIS_CMD = (
    b'@echo off\r\n'
    b'setlocal\r\n'
    b'set "MENTIS_RELEASE="\r\n'
    b'set /p MENTIS_RELEASE=<"%~dp0state\\current"\r\n'
    b'if not exist "%~dp0releases\\%MENTIS_RELEASE%\\runtime\\python.exe" goto gone\r\n'
    b'"%~dp0releases\\%MENTIS_RELEASE%\\runtime\\python.exe" -I -X utf8 '
    b'"%~dp0releases\\%MENTIS_RELEASE%\\app\\launcher.py" %*\r\n'
    b'exit /b %errorlevel%\r\n'
    b':gone\r\n'
    b'echo mentis: the release named in state\\current, "%MENTIS_RELEASE%", is not here. '
    b'Run a Mentis setup exe over this folder. 1>&2\r\n'
    b'exit /b 1\r\n')


def compile_stage(stage: pathlib.Path) -> None:
    """A release is locked once installed, so it could not write __pycache__ then, and
    every start would compile everything again. unchecked-hash: no file time matters."""
    with tempfile.TemporaryDirectory() as cwd:
        r = subprocess.run([stage / "runtime" / "python.exe", "-I", "-X", "utf8", "-m", "compileall", "-q",
                            "--invalidation-mode", "unchecked-hash",
                            stage / "app", stage / "runtime" / "Lib" / "site-packages"],
                           cwd=cwd, env=scrubbed_env(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if r.returncode:
        raise Refused(f"the stage does not compile:\n{(r.stdout + r.stderr)[-3000:]}")


def schema_facts(stage: pathlib.Path) -> dict:
    with tempfile.TemporaryDirectory() as cwd:
        r = subprocess.run([stage / "runtime" / "python.exe", "-I", "-B", "-X", "utf8", "-c", SCHEMA],
                           cwd=cwd, env=scrubbed_env(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if r.returncode:
        raise Refused(f"the stage cannot say its Brain schema:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout)


def stamp(stage: pathlib.Path, build_facts: dict) -> int:
    (stage / "app" / "BUILD.json").write_text(
        json.dumps({**build_facts, **schema_facts(stage)}, indent=1), "utf-8")
    (stage / "app" / "FILES.json").unlink(missing_ok=True)
    files = {p.relative_to(stage).as_posix(): sha256(p)
             for p in sorted(stage.rglob("*")) if p.is_file()}
    (stage / "app" / "FILES.json").write_text(json.dumps(files, indent=0), "utf-8")
    return len(files)


def pack(stage: pathlib.Path, nsi: pathlib.Path, nsis: pathlib.Path, exe: pathlib.Path,
         *, fast: bool = False) -> dict:
    """The setup exe of one stamped stage. `fast` is for the proof's throwaway variants."""
    facts = json.loads((stage / "app" / "BUILD.json").read_text("utf-8"))
    version, sha = facts["version"], facts["commit"]
    cmd = stage.parent / "mentis.cmd"
    cmd.write_bytes(MENTIS_CMD)
    _run([nsis, "/V2", "/INPUTCHARSET", "UTF8", *(["/XSetCompressor /FINAL zlib"] if fast else []),
          f"/DVERSION={version}", f"/DFILE_VERSION={version}.0", f"/DCOMMIT={sha[:12]}",
          f"/DSTAGE={stage}", f"/DCMD_FILE={cmd}", f"/DOUTFILE={exe}", nsi])
    digest = sha256(exe)
    (exe.with_name(exe.name + ".sha256")).write_bytes(f"{digest}  {exe.name}\n".encode("ascii"))
    return {"installer": str(exe), "installer_sha256": digest, "installer_bytes": exe.stat().st_size}


# -- the build --------------------------------------------------------------------

def build(out: pathlib.Path, cache: pathlib.Path, nsis=None, commit: str = "HEAD") -> dict:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise Refused("npm is not on PATH; Fluid is built with Node")
    sha = _run(["git", "rev-parse", f"{commit}^{{commit}}"]).strip()
    dirty = bool(_run(["git", "status", "--porcelain"]).strip())
    out = out.resolve()
    work = out / f"work-{sha[:12]}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    src, stage = work / "src", work / "stage"
    _run(["git", "clone", "-q", "--no-hardlinks", REPO, src])
    _run(["git", "-C", src, "checkout", "-q", "--detach", sha])
    if not (src / INSTALLER / "manifest.json").is_file():
        raise Refused(f"commit {sha[:12]} has no {INSTALLER}/manifest.json")
    version = tomllib.loads((src / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise Refused(f"pyproject's version {version} is not x.y.z")
    found = problems(src)
    if found:
        raise Refused(f"commit {sha[:12]} would not install:\n- " + "\n- ".join(found))
    man = load(src, "manifest.json")
    when = _run(["git", "-C", src, "log", "-1", "--format=%ct"]).strip()
    env = {**os.environ, "SOURCE_DATE_EPOCH": when}
    for name, spec in man["builds"].items():
        for step in spec["steps"]:
            step = [npm if step[0] == "npm" else step[0], *step[1:]]
            _run(step, cwd=src / spec["cwd"], env=env)
    stage.mkdir()
    runtime(load(src, "lock.json"), stage, src, cache)
    copy_payload(man, src, stage)
    for row in man["payload"]:
        for name in row.get("must_hold", ()):
            if name == "build-identity.json":
                said = json.loads((stage / pathlib.PurePosixPath(row["to"]) / name).read_text("utf-8"))
                if said.get("commit") != sha or said.get("dirty") is not False:
                    raise Refused(f"the Fluid build says it is {said}, not a clean {sha}")
    bundle = selftest(stage)
    compile_stage(stage)
    count = stamp(stage, {"product": man["product"], "version": version, "commit": sha})

    nsis = pathlib.Path(nsis) if nsis else makensis(load(src, "lock.json"), cache)
    packed = pack(stage, src / INSTALLER / "mentis.nsi", nsis, out / f"Mentis-Setup-{version}-{sha[:12]}.exe")
    return {"ok": True, "version": version, "commit": sha, "checkout_had_uncommitted": dirty,
            **packed, "stage": str(stage), "nsi": str(src / INSTALLER / "mentis.nsi"),
            "files": count, "render_check_bundle": bundle,
            "python": load(src, "lock.json")["python"]["version"],
            "nsis": str(nsis)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_windows_installer", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(REPO / "dist" / "installer"))
    ap.add_argument("--cache", default=str(pathlib.Path(tempfile.gettempdir()) / "mentis-installer-cache"),
                    help="where the pinned Python and NSIS zips are kept")
    ap.add_argument("--makensis", help="an NSIS to use instead of the pinned one")
    ap.add_argument("--commit", default="HEAD", help="the commit to build (default HEAD)")
    ap.add_argument("--check", action="store_true", help="only say what would stop an install")
    ap.add_argument("--relock", action="store_true", help="rewrite requirements.lock")
    a = ap.parse_args(argv)
    if a.check:
        found = problems(REPO)
        print(json.dumps({"ok": not found, "problems": found}, indent=1))
        return 1 if found else 0
    if sys.platform != "win32":
        print("error: the Windows installer is built on Windows", file=sys.stderr)
        return 1
    try:
        got = relock() if a.relock else build(pathlib.Path(a.out), pathlib.Path(a.cache), a.makensis, a.commit)
    except Refused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(got, indent=1))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
