"""The package builder: one commit in, one byte-reproducible package out.

THE PACKAGE (Stage 1 shared contract). `mentis-<semver>+<commit12>.zip`, a
Python zipapp -- `python3.12 <zip> <command>` runs its `__main__.py` -- holding
`mentis/**` (the commit's tracked files), `ui/dist/**` (built from the commit),
`requirements.lock`, `RELEASE.json`, `INSTALL.md` and `__main__.py`. Beside it,
`<zip>.sha256` holds the zip's hash in `sha256sum` form.

`RELEASE.json`: `format` 1, `version`, `commit`, `source_date` (the commit
time, ISO 8601 UTC), `python`, `schema_target`, `reads_schema` {min, max},
`min_reader_after`, `migrations` [ids], `breaking`, `files` {relpath: sha256}
for every file but itself, and -- only in a `win64` package -- `runtime`.
The schema facts are read from the COMMIT's
`mentis.spine.migrations`, imported in a separate interpreter from the
checkout, never from the code running this builder:
- `schema_target`: the version the release migrates a Brain to;
- `reads_schema`: `min` the lowest version it can migrate from, `max` its
  target. A newer Brain is still opened when that Brain's own min_reader is
  at most `max`; that is decided per Brain at open, not here;
- `min_reader_after`: the min_reader a Brain has once this release migrated
  it, the highest any of its migrations declares;
- `breaking`: whether any migration in its list is of kind "breaking".

THE WINDOWS PACKAGE (`--target win64`; installer plan adm-06dbd34701bf, S1).
`mentis-<semver>+<commit12>-win64.zip`: the same package, plus `runtime/`,
the Python it runs with on a Windows PC that has none -- python.org's
embeddable 3.12 for amd64 with every requirements.lock wheel installed into
it, built by `mentis.release.runtime` from the commit's own lock -- every
runtime file in `files` with the rest, and RELEASE.json gaining
`"runtime": {"kind": "embedded", "python": "3.12.x", "path": "runtime"}`.
A package with `runtime` is installed in bundled mode (`mentis.installer`).
`bootstrap --out DIR` unpacks the same pinned embeddable Python, unchanged,
into `DIR/python`: the copy the desktop installer ships beside the zip to
run it, since a zip cannot run itself.

THE SAME COMMIT GIVES THE SAME BYTES. Built from a fresh clone at the commit
with line-ending conversion off (so Windows and POSIX checkouts agree);
entries sorted; every timestamp, permission and creator field fixed, the time
being the commit's; entries STORED, because deflate output depends on which
zlib the platform has; the UI stamp's `built_at` is the commit time
(SOURCE_DATE_EPOCH). `requirements.lock` is the commit's own tracked file --
generated once by `lock`, which needs the network, then reviewed and committed
-- so nothing is resolved at build time.

THE CLEAN-CHECKOUT CHECK. The commit must exist in the repository and be
reachable from one of its branches or tags -- a stash, or any other commit no
branch or tag holds, is uncommitted work however it is named; the build
checkout must still be exactly the commit after `npm ci` and the UI build (no
tracked file changed, nothing untracked and unignored); and the UI's stamp
must name the commit and say not dirty. Uncommitted work in the source
repository is never packaged, and the result says whether there was any.

WHEEL BUNDLES (optional, for offline installs). `wheels` downloads, with
`--require-hashes`, every wheel requirements.lock needs on a platform tag, into
`mentis-<semver>+<commit12>-wheels-<tag>.zip` with `WHEELS.json` listing them
by hash, plus its own `.sha256`. Any tag can be fetched from any machine.

VERIFY. A package: its sidecar hash, the RELEASE.json contract (every field
of the right type, and the mandatory entries present), and every entry
against `files` -- each changed, missing and extra file is named. Every entry
name must extract to exactly itself inside the release folder on any OS:
directory entries, `.`/`..`/empty segments, `:`, `\\`, a trailing dot or space
and Windows reserved names are `unsafe-path`; two names that differ only by
case or Unicode normalisation (the same after NFC and casefold) are
`duplicate`. A release directory (an unpacked package): the same,
ignoring its `.venv/`, and with every file under a `__pycache__/` checked
against the release's BYTECODE.json (`bytecode_manifest`): the bytecode
staging compiled, which Python runs in place of the source, so a changed,
missing or planted `.pyc` is damage like any other file. A package built
since bytecode is checked says so in RELEASE.json (`"bytecode":
"BYTECODE.json"`); a release from before that (1.0.0-rc.1) had no manifest
and makes its `.pyc` as it runs, so its `__pycache__/` files are not judged,
as its own installer did not judge them -- otherwise every such release
would read as damaged, and an update could neither stop it after asking it
about running work nor switch back to it. That is decided by its VERSION
(before BYTECODE_SINCE) as well as the missing mark and manifest, so a
later release with either removed is damaged (N4); and a folder named as a
release (`<version>+<commit12>`) must hold that release, so the version
cannot be edited without the folder no longer being the one install.json
names. RELEASE.json itself is not anchored: someone who rewrites it whole,
hashes included, is not caught here. A wheel bundle: every wheel against
WHEELS.json.

The kind is decided by the content (a zip holding WHEELS.json is a wheel
bundle), so `ok` alone does not say a package was checked: a caller that
needs a package MUST also require `kind == "package"`, as `wheels` does.
"""

from __future__ import annotations

import argparse
import datetime
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
import tempfile
import unicodedata
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[2]
FORMAT = 1
PYTHON = ">=3.12,<3.13"
RELEASE = "RELEASE.json"
LOCK = "requirements.lock"
WHEELS = "WHEELS.json"
#: https://semver.org/#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string
SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?")
#: the default offline bundles; any pip platform tag may be asked for
PLATFORMS = ("win_amd64", "macosx_11_0_arm64", "macosx_10_13_x86_64",
             "manylinux_2_17_x86_64", "manylinux_2_17_aarch64")
#: package targets that carry their own Python (`runtime/`)
TARGETS = ("win64",)
RUNTIME_DIR = "runtime"
#: what a release directory holds beside the package's files
DIR_IGNORED = (".venv",)
#: in a release directory: the hash of every `__pycache__` file staging made
BYTECODE = "BYTECODE.json"
#: the first version whose releases record their bytecode: a release of an
#: earlier version (1.0.0-rc.1) is the only kind whose `.pyc` go unjudged
BYTECODE_SINCE = "1.0.0-rc.2"
PYCACHE = "__pycache__"
CHUNK = 1 << 20


class BuildError(RuntimeError):
    pass


def _run(cmd, cwd=None, env=None) -> str:
    try:
        out = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError as e:
        raise BuildError(f"{cmd[0]} is not installed or not on PATH") from e
    if out.returncode:
        raise BuildError(f"{' '.join(map(str, cmd))} failed ({out.returncode}):"
                         f"\n{(out.stderr or out.stdout).strip()[-4000:]}")
    return out.stdout.strip()


def _git(cwd, *args) -> str:
    return _run(["git", "-C", str(cwd), *args])


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _json(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False)
            + "\n").encode("utf-8")


# -- the reproducible zip ------------------------------------------------------

def _zip_time(epoch: int) -> tuple:
    t = datetime.datetime.fromtimestamp(max(epoch, 315532800),
                                        datetime.timezone.utc)
    return (t.year, t.month, t.day, t.hour, t.minute, t.second)


def write_zip(path: pathlib.Path, files: dict, epoch: int) -> str:
    """`files` {relpath: bytes}. Written beside, then renamed into place, so
    a half-written zip never carries the final name. Returns its sha256."""
    when = _zip_time(epoch)
    tmp = path.with_name(path.name + ".partial")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, when)
            info.create_system = 3                          # same on every OS
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, files[name])
    os.replace(tmp, path)
    digest = sha256_file(path)
    path.with_name(path.name + ".sha256").write_bytes(
        f"{digest}  {path.name}\n".encode("ascii"))
    return digest


# -- the checkout ---------------------------------------------------------------

def resolve(repo, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", ref + "^{commit}")


def assert_reachable(repo, sha: str) -> None:
    """Only committed work is packaged: a commit some branch or tag holds.
    A stash (`refs/stash` and its reflog) or a dangling commit is refused."""
    held = _git(repo, "for-each-ref", "--contains", sha, "--format=%(refname)",
                "refs/heads", "refs/remotes", "refs/tags")
    if not held:
        raise BuildError(f"{sha} is on no branch or tag (a stash or a "
                         "dangling commit); only committed work is packaged")


def checkout(repo, sha: str, dest: pathlib.Path) -> None:
    """A fresh clone at `sha`, with no line-ending conversion."""
    _run(["git", "clone", "-q", "--no-checkout", "--shared",
          "-c", "core.autocrlf=false", "-c", "core.eol=lf",
          str(pathlib.Path(repo).resolve()), str(dest)])
    _git(dest, "checkout", "-q", "--detach", sha)


def assert_clean(tree: pathlib.Path, sha: str) -> None:
    head = _git(tree, "rev-parse", "HEAD")
    if head != sha:
        raise BuildError(f"the build checkout is at {head}, not {sha}")
    dirt = _git(tree, "status", "--porcelain", "--untracked-files=all")
    if dirt:
        raise BuildError("the build checkout no longer matches the commit "
                         f"after building; nothing packaged:\n{dirt}")


def build_ui(tree: pathlib.Path, epoch: int) -> None:
    ui = tree / "ui"
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise BuildError("npm is not installed or not on PATH")
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch)}
    env.pop("MENTIS_API", None)
    _run([npm, "ci", "--no-audit", "--no-fund"], cwd=ui, env=env)
    _run([npm, "run", "build"], cwd=ui, env=env)


def check_stamp(dist: pathlib.Path, sha: str, epoch: int) -> dict:
    p = dist / "build-identity.json"
    try:
        stamp = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise BuildError(f"{p} is missing or unreadable: {e}") from e
    if stamp.get("commit") != sha or stamp.get("dirty") is not False:
        raise BuildError(f"the UI was built from {stamp.get('commit')} "
                         f"(dirty={stamp.get('dirty')}), not clean {sha}")
    if stamp.get("built_at") != epoch:
        # A commit from before build-identity.mjs read SOURCE_DATE_EPOCH.
        stamp["built_at"] = epoch
        p.write_text(json.dumps(stamp, indent=2), "utf-8")
    return stamp


# -- what goes in ------------------------------------------------------------------

def schema_facts(tree: pathlib.Path) -> dict:
    """Read from the tree's own mentis.spine.migrations, in its own
    interpreter, so the facts are the commit's and not this builder's."""
    code = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from mentis.spine import migrations as m\n"
        "ms = m.migrations()\n"
        "print(json.dumps({\n"
        " 'schema_target': m.target(ms),\n"
        " 'reads_schema': {'min': min((x.from_version for x in ms), default=0),"
        " 'max': m.target(ms)},\n"
        " 'min_reader_after': max((x.min_reader for x in ms), default=0),\n"
        " 'migrations': [x.id for x in ms],\n"
        " 'breaking': any(x.kind == 'breaking' for x in ms)}))\n")
    out = _run([sys.executable, "-I", "-B", "-c", code, str(tree)])
    return json.loads(out.splitlines()[-1])


_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = _PIN.match(line.strip())
        if m:
            out[_norm(m.group(1))] = m.group(2)
    return out


def check_lock(tree: pathlib.Path) -> bytes:
    lock = tree / LOCK
    if not lock.is_file():
        raise BuildError(f"the commit has no {LOCK}; run `python -m "
                         "mentis.release lock`, review and commit it")
    text = lock.read_text("utf-8")
    locked = pins(text)
    for line in (tree / "requirements.txt").read_text("utf-8").splitlines():
        req = line.split("#", 1)[0].strip()
        if not req:
            continue
        m = _PIN.match(req)
        if not m:
            raise BuildError(f"requirements.txt: {req!r} is not pinned with "
                             f"==; pin it and re-run `lock`")
        name, version = _norm(m.group(1)), m.group(2)
        if locked.get(name) != version:
            raise BuildError(f"requirements.txt pins {name}=={version}; "
                             f"{LOCK} has {locked.get(name)}. Re-run `lock`")
    for block in re.split(r"\n(?=\S)", text):
        if _PIN.match(block.strip()) and "--hash=sha256:" not in block:
            raise BuildError(f"{LOCK}: {block.split()[0]} carries no hash")
    return lock.read_bytes()


def install_md(version: str, sha: str, target: str | None = None) -> bytes:
    if target == "win64":
        return f"""# Mentis {version} for 64-bit Windows

Built from commit {sha}. Carries its own Python 3.12 and every dependency in
`runtime/`: the PC it is installed on needs nothing else.

    python.exe -I {package_name(version, sha, target)} install --new-brain --owner @you

`python.exe` is the embeddable Python 3.12 shipped beside this package (the
desktop installer's `payload\\bootstrap\\python`); once installed, Mentis runs
with the copy in `runtime/` and the system's Python is never looked up.

Check the package first: its hash is in the `.sha256` file beside it, and
every file inside, `runtime/` included, is listed with its hash in
RELEASE.json.
""".encode("utf-8")
    return f"""# Mentis {version}

Built from commit {sha}. Needs Python 3.12 and nothing else.

    python3.12 mentis-{version}+{sha[:12]}.zip --help

Check the package first: its hash is in the `.sha256` file beside it, and
every file inside is listed with its hash in RELEASE.json.

Dependencies install from requirements.lock with `pip --require-hashes`, or
offline from the wheel bundle for your platform,
`mentis-{version}+{sha[:12]}-wheels-<platform>.zip`.
""".encode("utf-8")


def runtime_files(built: dict) -> tuple[dict, dict]:
    """The runtime `mentis.release.runtime.build_runtime` made, as package
    entries {"runtime/<relpath>": bytes}, and the RELEASE.json `runtime`
    block. Each file is checked against the hash list the runtime builder
    wrote, so what is packed is what it built and tested."""
    rt_dir = pathlib.Path(built["runtime_dir"])
    listed = json.loads(pathlib.Path(built["files_json"]).read_text("utf-8"))
    files = {}
    for root, dirs, names in os.walk(rt_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(names):
            p = pathlib.Path(root) / n
            files[p.relative_to(rt_dir.parent).as_posix()] = p.read_bytes()
    got = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
    if got != listed["files"]:
        raise BuildError("the runtime changed after it was built: "
                         + json.dumps(_compare(listed["files"], got))[:800])
    if not all(k.startswith(RUNTIME_DIR + "/") for k in files):
        raise BuildError("the runtime builder made files outside runtime/")
    return files, listed["runtime"]


def collect(tree: pathlib.Path, sha: str, version: str, epoch: int,
            runtime: dict | None = None, target: str | None = None) -> dict:
    """{relpath: bytes} for every file of the package, RELEASE.json last.
    `runtime`: `runtime_files`' answer, for a `target` that carries one."""
    files = {}
    for rel in _git(tree, "ls-files", "-z", "--", "mentis").split("\0"):
        if rel:
            files[rel] = (tree / rel).read_bytes()
    dist = tree / "ui" / "dist"
    for f in sorted(dist.rglob("*")):
        if f.is_file():
            files["ui/dist/" + f.relative_to(dist).as_posix()] = f.read_bytes()
    if "ui/dist/index.html" not in files:
        raise BuildError("the UI build produced no index.html")
    files[LOCK] = check_lock(tree)
    files["INSTALL.md"] = install_md(version, sha, target)
    files["__main__.py"] = (tree / "mentis" / "release" /
                            "zipapp_main.py").read_bytes()
    block = {}
    if runtime is not None:
        rt_files, rt = runtime
        clash = sorted(set(rt_files) & set(files))
        if clash:
            raise BuildError(f"runtime files clash with the package: {clash}")
        files.update(rt_files)
        block = {"runtime": rt}
    when = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    files[RELEASE] = _json({
        "format": FORMAT, "version": version, "commit": sha,
        "source_date": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": PYTHON, **schema_facts(tree), **block, "bytecode": BYTECODE,
        "files": {k: hashlib.sha256(v).hexdigest()
                  for k, v in sorted(files.items())}})
    return files


def package_name(version: str, sha: str, target: str | None = None) -> str:
    """`mentis-<semver>+<commit12>.zip`, or `...-win64.zip` for a package
    that carries its own Windows Python."""
    return f"mentis-{version}+{sha[:12]}{'-' + target if target else ''}.zip"


def target_of(rel: dict) -> str | None:
    """The target a RELEASE.json was built for: "win64" when it carries a
    runtime, else None."""
    return "win64" if isinstance(rel.get("runtime"), dict) else None


def build(version: str, commit: str = "HEAD", repo=REPO, out=None,
          work=None, target: str | None = None, runtime_cache=None,
          runtime_wheels=None) -> dict:
    """Build the package of `commit`. `target` "win64" adds `runtime/`
    (see the module docstring); `runtime_cache` is where the pinned
    embeddable zip is kept, `runtime_wheels` a win_amd64 wheel bundle for an
    offline runtime build (default: PyPI, by hash)."""
    if not SEMVER.fullmatch(version):
        raise BuildError(f"{version!r} is not a SemVer version (x.y.z or "
                         "x.y.z-pre); the commit is added as build metadata")
    if target not in (None, *TARGETS):
        raise BuildError(f"no target {target!r}; known: {', '.join(TARGETS)}")
    repo = pathlib.Path(repo).resolve()
    sha = resolve(repo, commit)
    assert_reachable(repo, sha)
    epoch = int(_git(repo, "show", "-s", "--format=%ct", sha))
    out = pathlib.Path(out or repo / "dist").resolve()
    dest = out / package_name(version, sha, target)
    if dest.exists():
        raise BuildError(f"{dest} exists; a package is never rebuilt over")
    source_dirty = bool(_git(repo, "status", "--porcelain"))
    built_rt = None
    with tempfile.TemporaryDirectory(prefix="mentis-build-",
                                     dir=work) as tmp:
        tree = pathlib.Path(tmp) / "src"
        checkout(repo, sha, tree)
        build_ui(tree, epoch)
        assert_clean(tree, sha)
        stamp = check_stamp(tree / "ui" / "dist", sha, epoch)
        rt = None
        if target == "win64":
            from mentis.release import runtime
            check_lock(tree)
            built_rt = runtime.build_runtime(
                pathlib.Path(tmp) / "rt", cache=runtime_cache,
                wheels=runtime_wheels, lock_path=tree / LOCK)
            rt = runtime_files(built_rt)
        files = collect(tree, sha, version, epoch, rt, target)
        out.mkdir(parents=True, exist_ok=True)
        digest = write_zip(dest, files, epoch)
    got = {"package": str(dest), "sha256": digest, "commit": sha,
           "version": version, "target": target, "files": len(files),
           "ui_stamp": stamp,
           "source_repo_had_uncommitted_changes": source_dirty,
           "release": json.loads(files[RELEASE])}
    if built_rt is not None:
        got["runtime"] = {k: built_rt[k] for k in (
            "runtime", "python_sha256", "wheels", "wheel_source",
            "requirements_lock_sha256", "selftest", "file_count")}
    return got


def bootstrap(out, cache=None, runtime_lock=None) -> dict:
    """`<out>/python/`: the pinned embeddable Python (`runtime.lock`),
    checked and unpacked unchanged -- its own `._pth`, no site-packages --
    which runs a `-win64` package (`python.exe -I <zip> install ...`).
    Never built over."""
    from mentis.release import runtime
    out = pathlib.Path(out).resolve()
    dest = out / "python"
    if dest.exists():
        raise BuildError(f"{dest} exists; the bootstrap is never built over")
    lock = (runtime.load_lock() if runtime_lock is None
            else json.loads(pathlib.Path(runtime_lock).read_text("utf-8")))
    zip_path = runtime.fetch(lock, pathlib.Path(
        cache or pathlib.Path(tempfile.gettempdir()) / "mentis-runtime-cache"))
    part = out / "python.partial"
    if part.exists():
        shutil.rmtree(part)
    part.mkdir(parents=True)
    runtime.unpack(zip_path, part)
    os.replace(part, dest)
    files = {p.relative_to(out).as_posix(): sha256_file(p)
             for p in sorted(dest.rglob("*")) if p.is_file()}
    return {"bootstrap": str(dest), "python": lock["python"],
            "python_sha256": lock["sha256"], "files": files}


# -- verify -------------------------------------------------------------------

#: entries every package holds, beside at least one mentis/ file
MANDATORY = ("__main__.py", LOCK, "INSTALL.md", "ui/dist/index.html")
#: names Windows maps to a device, whatever extension follows
RESERVED = frozenset(
    ["con", "prn", "aux", "nul", "conin$", "conout$"]
    + [f"{d}{n}" for d in ("com", "lpt") for n in "0123456789\u00b9\u00b2\u00b3"])


def _iso(v) -> bool:
    if not (isinstance(v, str)
            and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", v)):
        return False
    try:
        datetime.datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _contract(rel, name: str | None) -> list:
    p = []
    for k in ("format", "version", "commit", "source_date", "python",
              "schema_target", "reads_schema", "min_reader_after",
              "migrations", "breaking", "files"):
        if k not in rel:
            p.append({"problem": "contract", "detail": f"RELEASE.json has no {k}"})
    if p:
        return p

    def bad(detail):
        p.append({"problem": "contract", "detail": detail})

    def count(v):
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0

    if type(rel["format"]) is not int or rel["format"] != FORMAT:
        bad(f"format {rel['format']!r}")
    named = isinstance(rel["version"], str) and SEMVER.fullmatch(rel["version"])
    if not named:
        bad("version is not SemVer")
    if not (isinstance(rel["commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", rel["commit"])):
        bad("commit is not a sha")
        named = False
    if not _iso(rel["source_date"]):
        bad("source_date is not an ISO 8601 UTC time (YYYY-MM-DDTHH:MM:SSZ)")
    if rel["python"] != PYTHON:
        bad(f"python {rel['python']!r}")
    for k in ("schema_target", "min_reader_after"):
        if not count(rel[k]):
            bad(f"{k} is not a schema version")
    rs = rel["reads_schema"]
    if not (isinstance(rs, dict) and set(rs) == {"min", "max"}
            and count(rs["min"]) and count(rs["max"]) and rs["min"] <= rs["max"]
            and rs["max"] == rel["schema_target"]):
        bad("reads_schema is not {min, max} with min <= max = schema_target")
    if not (isinstance(rel["migrations"], list)
            and all(isinstance(m, str) for m in rel["migrations"])):
        bad("migrations is not a list of ids")
    if not isinstance(rel["breaking"], bool):
        bad("breaking is not true or false")
    files = rel["files"]
    if not all(isinstance(k, str) and isinstance(v, str)
               and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in files.items()):
        bad("files is not {path: sha256}")
    for k in MANDATORY:
        if k not in files:
            bad(f"files has no {k}")
    if not any(isinstance(k, str) and k.startswith("mentis/") for k in files):
        bad("files has no mentis/ file")
    rt = rel.get("runtime")
    if "runtime" in rel:
        if not (isinstance(rt, dict) and rt.get("kind") == "embedded"
                and isinstance(rt.get("python"), str)
                and re.fullmatch(r"3\.12\.\d+", rt["python"])
                and rt.get("path") == RUNTIME_DIR):
            bad("runtime is not {kind: embedded, python: 3.12.x, path: "
                f"{RUNTIME_DIR}}}")
        elif f"{RUNTIME_DIR}/python.exe" not in files:
            bad(f"runtime is declared but files has no {RUNTIME_DIR}/python.exe")
    elif any(isinstance(k, str) and k.startswith(RUNTIME_DIR + "/")
             for k in files):
        bad(f"files has {RUNTIME_DIR}/ but RELEASE.json declares no runtime")
    want = package_name(rel["version"], rel["commit"], target_of(rel)) \
        if named else None
    if name is not None and named and name != want:
        p.append({"problem": "name", "detail": f"{name} is not {want}"})
    return p


def _compare(declared: dict, actual: dict) -> list:
    p = []
    for k in sorted(set(declared) | set(actual)):
        if k not in actual:
            p.append({"problem": "missing", "path": k})
        elif k not in declared:
            p.append({"problem": "extra", "path": k})
        elif declared[k] != actual[k]:
            p.append({"problem": "changed", "path": k})
    return p


def _sidecar(path: pathlib.Path) -> list:
    side = path.with_name(path.name + ".sha256")
    if not side.is_file():
        return [{"problem": "sidecar", "detail": f"no {side.name}"}]
    want = side.read_text("ascii", errors="replace").split()[:1]
    if want != [sha256_file(path)]:
        return [{"problem": "sidecar",
                 "detail": f"{path.name} does not match {side.name}"}]
    return []


def _safe(name: str) -> bool:
    """Whether `name` extracts to exactly itself, inside the folder, on
    Windows, macOS and Linux alike: relative, `/`-separated, every segment a
    plain file or folder name no OS rewrites or maps to a device."""
    if not name or name.startswith("/") or "\\" in name or ":" in name:
        return False
    for part in name.split("/"):
        if part in ("", ".", "..") or part[-1] in ". " \
                or any(ord(c) < 32 for c in part) \
                or part.split(".")[0].rstrip(" ").casefold() in RESERVED:
            return False
    return True


def _fold(name: str) -> str:
    """The name as a case-insensitive or normalising file system sees it:
    two entries with the same fold extract to one file (Windows folds case;
    macOS folds case and Unicode normalisation)."""
    return unicodedata.normalize("NFC", name).casefold()


def _read_zip(path: pathlib.Path) -> tuple[dict, list]:
    """{name: sha256} of every entry, and its problems. The builder writes
    no directory entries, so any is refused rather than skipped."""
    entries, folded, p = {}, set(), []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if not _safe(info.filename.removesuffix("/")
                         if info.is_dir() else info.filename):
                p.append({"problem": "unsafe-path", "path": info.filename})
                continue
            if info.is_dir():
                p.append({"problem": "unsafe-path", "path": info.filename,
                          "detail": "a directory entry"})
                continue
            key = _fold(info.filename)
            if info.filename in entries or key in folded:
                p.append({"problem": "duplicate", "path": info.filename})
            folded.add(key)
            h = hashlib.sha256()
            try:
                with z.open(info) as f:
                    while chunk := f.read(CHUNK):
                        h.update(chunk)
            except (zipfile.BadZipFile, OSError, EOFError):
                p.append({"problem": "corrupt", "path": info.filename})
                h.update(b"\0corrupt")      # never equals a declared hash
            entries[info.filename] = h.hexdigest()
    return entries, p


def _read_dir(path: pathlib.Path) -> dict:
    """{relpath: sha256} of every file in a release directory but its
    `.venv/` -- bytecode included: Python loads it, so it is checked
    (against BYTECODE.json, see `bytecode_manifest`)."""
    out = {}
    for root, dirs, names in os.walk(path):
        here = pathlib.Path(root)
        dirs[:] = sorted(d for d in dirs if not (
            here == path and d in DIR_IGNORED))
        for n in names:
            f = here / n
            out[f.relative_to(path).as_posix()] = sha256_file(f)
    return out


def _is_bytecode(relpath: str) -> bool:
    return PYCACHE in relpath.split("/")[:-1]


def bytecode_manifest(rel_dir) -> dict:
    """BYTECODE.json for a release directory whose bytecode was just made
    (install compiles it once, before the release is locked read-only):
    {"format": 1, "files": {relpath: sha256}} of every file under a
    `__pycache__/`. A release directory then verifies its bytecode against
    it exactly as its other files against RELEASE.json -- a changed, missing
    or EXTRA (planted) `.pyc` is damage -- since Python runs a `.pyc` in
    place of its source. The manifest is written by staging and, like
    RELEASE.json in a release directory, nothing outside it anchors it: it
    guards against accident and damage, not against someone able to rewrite
    both."""
    rel_dir = pathlib.Path(rel_dir)
    files = {k: v for k, v in _read_dir(rel_dir).items() if _is_bytecode(k)}
    return {"format": FORMAT, "files": dict(sorted(files.items()))}


def _load_bytecode(path: pathlib.Path) -> tuple[dict, list]:
    """BYTECODE.json's {relpath: sha256}, every one under a `__pycache__/`;
    {} when there is none (then any bytecode at all is extra)."""
    if not path.is_file():
        return {}, []
    try:
        doc = json.loads(path.read_text("utf-8"))
        files = doc["files"]
        if (doc.get("format") == FORMAT and isinstance(files, dict)
                and all(isinstance(k, str) and _is_bytecode(k)
                        and isinstance(v, str)
                        and re.fullmatch(r"[0-9a-f]{64}", v)
                        for k, v in files.items())):
            return files, []
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {}, [{"problem": "contract",
                 "detail": f"{BYTECODE} is not {{format: 1, files: "
                           "{__pycache__ path: sha256}}"}]


def _load_release(text) -> tuple[dict | None, list]:
    try:
        rel = json.loads(text)
        if isinstance(rel, dict) and isinstance(rel.get("files", {}), dict):
            return rel, []
    except ValueError:
        pass
    return None, [{"problem": "contract", "detail": "RELEASE.json unreadable"}]


def _version_key(v: str) -> tuple:
    """SemVer precedence (build metadata ignored); ValueError if not SemVer."""
    m = SEMVER.fullmatch(str(v).partition("+")[0])
    if not m:
        raise ValueError(f"{v!r} is not a SemVer version")
    nums = tuple(int(x) for x in m.groups()[:3])
    pre = m.group(4)
    if not pre:
        return nums + ((1,),)
    return nums + ((0,) + tuple((0, int(x), "") if x.isdigit() else (1, 0, x)
                                for x in pre.split(".")),)


def _before_bytecode(version) -> bool:
    """Whether a release of `version` was made before releases recorded
    their bytecode (BYTECODE_SINCE): only such a release's `.pyc` go
    unjudged. Anything that is not a version is not before it."""
    try:
        return _version_key(version) < _version_key(BYTECODE_SINCE)
    except (TypeError, ValueError):
        return False


#: `<version>+<commit12>`, the name staging gives a release folder
_RELEASE_DIR = re.compile(r"[^+\\/]+\+[0-9a-f]{12}")


def _dir_name(name: str, rel: dict | None) -> list:
    """A folder named as a release must be the release its RELEASE.json
    says: `<version>+<commit12>`. A staging's `.partial`, a set-aside
    `.damaged-` copy or any other folder is not judged by its name."""
    if rel is None or not _RELEASE_DIR.fullmatch(name):
        return []
    want = f"{rel.get('version')}+{str(rel.get('commit'))[:12]}"
    return [] if name == want else [
        {"problem": "name", "detail": f"the folder {name} holds {want}"}]


def verify(target) -> dict:
    """Check a package, release directory or wheel bundle. The result's
    `kind` says which it was taken for, from its content: callers that need
    a package must require `ok` AND `kind == "package"`."""
    path = pathlib.Path(target)
    p = []
    if path.is_dir():
        kind, actual = "release-dir", _read_dir(path)
        raw = (path / RELEASE).read_bytes() if (path / RELEASE).is_file() else None
    elif not zipfile.is_zipfile(path):
        return {"ok": False, "path": str(path), "kind": None, "problems": [
            {"problem": "unreadable", "detail": "not a directory or a zip"}]}
    else:
        p += _sidecar(path)
        actual, zp = _read_zip(path)
        p += zp
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            try:
                if WHEELS in names:
                    return _verify_bundle(path, z, actual, p)
                kind = "package"
                raw = z.read(RELEASE) if RELEASE in names else None
            except zipfile.BadZipFile:
                return {"ok": False, "path": str(path), "kind": None,
                        "problems": p}
    if raw is None:
        p.append({"problem": "missing", "path": RELEASE})
        return {"ok": False, "path": str(path), "kind": kind, "problems": p}
    actual.pop(RELEASE, None)
    rel, rp = _load_release(raw)
    if kind == "release-dir":
        actual.pop(BYTECODE, None)
        compiled = {k: actual.pop(k) for k in list(actual) if _is_bytecode(k)}
        # a release from before bytecode was checked (no mark, no manifest,
        # and a version before BYTECODE_SINCE) makes its own .pyc as it
        # runs: not judged (see VERIFY). A later one missing either is
        # damaged like any other (N4)
        if (rel or {}).get("bytecode") or (path / BYTECODE).exists() \
                or not _before_bytecode((rel or {}).get("version")):
            declared, bp = _load_bytecode(path / BYTECODE)
            p += bp + _compare(declared, compiled)
        p += _dir_name(path.name, rel)
    p += rp
    if rel is not None:
        p += _contract(rel, path.name if kind == "package" else None)
        p += _compare(rel.get("files", {}), actual)
    return {"ok": not p, "path": str(path), "kind": kind,
            "version": (rel or {}).get("version"),
            "commit": (rel or {}).get("commit"), "files": len(actual),
            "problems": p}


def _verify_bundle(path, z, actual, p) -> dict:
    try:
        man = json.loads(z.read(WHEELS))
        declared = {f"wheels/{k}": v for k, v in man["wheels"].items()}
    except (ValueError, KeyError, AttributeError, TypeError):
        man, declared = {}, {}
        p.append({"problem": "contract", "detail": "WHEELS.json unreadable"})
    actual.pop(WHEELS, None)
    p += _compare(declared, actual)
    expect = (f"mentis-{man.get('version')}+{str(man.get('commit'))[:12]}"
              f"-wheels-{man.get('platform')}.zip")
    if man and path.name != expect:
        p.append({"problem": "name", "detail": f"{path.name} is not {expect}"})
    return {"ok": not p, "path": str(path), "kind": "wheel-bundle",
            "platform": man.get("platform"), "version": man.get("version"),
            "files": len(actual), "problems": p}


# -- wheels and the lock ----------------------------------------------------------

def _platform_args(tag: str) -> list:
    m = re.fullmatch(r"manylinux_2_(\d+)_(\w+)", tag)
    tags = [tag]
    if m:   # what a wheel's filename may say for the same glibc floor
        tags += [f"manylinux2014_{m.group(2)}"] if m.group(1) == "17" else []
    return [a for t in tags for a in ("--platform", t)]


def bundle_name(version: str, sha: str, tag: str) -> str:
    return f"mentis-{version}+{sha[:12]}-wheels-{tag}.zip"


def wheels(package, platforms=PLATFORMS, out=None) -> list:
    package = pathlib.Path(package).resolve()
    v = verify(package)
    if not v["ok"] or v["kind"] != "package":
        raise BuildError(f"{package} does not verify: {v['problems']}")
    with zipfile.ZipFile(package) as z:
        lock = z.read(LOCK)
        rel = json.loads(z.read(RELEASE))
    out = pathlib.Path(out or package.parent)
    for tag in platforms:       # all refused before anything is downloaded
        there = out / bundle_name(rel["version"], rel["commit"], tag)
        if there.exists():
            raise BuildError(f"{there} exists; a bundle is never rebuilt over")
    made = []
    for tag in platforms:
        with tempfile.TemporaryDirectory(prefix="mentis-wheels-") as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / LOCK).write_bytes(lock)
            dl = tmp / "wheels"
            _run([sys.executable, "-m", "pip", "download", "-q",
                  "--disable-pip-version-check", "--no-cache-dir",
                  "--require-hashes", "--only-binary=:all:", "--no-deps",
                  "--python-version", "3.12", "--implementation", "cp",
                  "--abi", "cp312", "--abi", "abi3", "--abi", "none",
                  *_platform_args(tag), "-d", str(dl), "-r", str(tmp / LOCK)])
            files = {f"wheels/{f.name}": f.read_bytes()
                     for f in sorted(dl.glob("*.whl"))}
        man = {"format": FORMAT, "version": rel["version"],
               "commit": rel["commit"], "platform": tag, "python": PYTHON,
               "requirements_lock_sha256": hashlib.sha256(lock).hexdigest(),
               "wheels": {k[len("wheels/"):]: hashlib.sha256(b).hexdigest()
                          for k, b in files.items()}}
        files[WHEELS] = _json(man)
        name = bundle_name(rel["version"], rel["commit"], tag)
        epoch = int(datetime.datetime.strptime(
            rel["source_date"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp())
        digest = write_zip(out / name, files, epoch)
        made.append({"bundle": str(out / name), "sha256": digest,
                     "platform": tag, "wheels": sorted(man["wheels"])})
    return made


def _wheel_fits(filename: str) -> bool:
    """A distribution file a Python 3.12 install might pick, on any OS."""
    if not filename.endswith(".whl"):
        return filename.endswith((".tar.gz", ".zip"))
    py, abi = filename[:-4].split("-")[-3:-1]
    return any(t in ("py3", "cp312") for t in py.split(".")) or abi == "abi3"


def markers(text: str) -> dict:
    """{normalised name: PEP 508 marker} of each requirements.txt line that
    carries one (`name==v ; <marker>  # comment`)."""
    out = {}
    for line in text.splitlines():
        req = line.split("#", 1)[0].strip()
        m = _PIN.match(req)
        if m and ";" in req:
            marker = req.split(";", 1)[1].strip()
            if marker:
                out[_norm(m.group(1))] = marker
    return out


def lock(repo=REPO) -> pathlib.Path:
    """Resolve requirements.txt and write requirements.lock with the sha256
    of every file PyPI has for each pinned version that fits Python 3.12.
    A requirement's PEP 508 marker is carried onto its lock line as written,
    and a requirement whose marker leaves it out on THIS machine is still
    locked at its pin (pip's resolver here would drop both): the lock is for
    every platform. Needs the network; its output is reviewed and committed."""
    import urllib.request
    repo = pathlib.Path(repo)
    wanted = (repo / "requirements.txt").read_text("utf-8")
    marks = markers(wanted)
    with tempfile.TemporaryDirectory() as tmp:
        report = pathlib.Path(tmp) / "report.json"
        _run([sys.executable, "-m", "pip", "install", "-q", "--dry-run",
              "--ignore-installed", "--disable-pip-version-check",
              "--report", str(report), "-r", str(repo / "requirements.txt")])
        resolved = {_norm(i["metadata"]["name"]): i["metadata"]["version"]
                    for i in json.loads(report.read_text("utf-8"))["install"]}
    for name, version in pins("\n".join(
            ln.split("#", 1)[0] for ln in wanted.splitlines())).items():
        resolved.setdefault(name, version)
    lines = ["# Generated by `python -m mentis.release lock` from "
             "requirements.txt. Do not edit.",
             "# Install with: pip install --require-hashes -r requirements.lock"]
    for name, version in sorted(resolved.items()):
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        with urllib.request.urlopen(url, timeout=60) as r:
            urls = json.loads(r.read())["urls"]
        hashes = sorted(u["digests"]["sha256"] for u in urls
                        if _wheel_fits(u["filename"]))
        if not hashes:
            raise BuildError(f"PyPI has no file of {name}=={version} for 3.12")
        marker = f" ; {marks[name]}" if name in marks else ""
        lines.append(f"{name}=={version}{marker} \\")
        lines += [f"    --hash=sha256:{h} \\" for h in hashes[:-1]]
        lines.append(f"    --hash=sha256:{hashes[-1]}")
    path = repo / LOCK
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


# -- the command ----------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mentis.release",
                                 description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", help="build the package for a commit")
    p.add_argument("--version", required=True, help="SemVer, e.g. 1.0.0-rc.1")
    p.add_argument("--commit", default="HEAD")
    p.add_argument("--repo", default=str(REPO))
    p.add_argument("--out", help="where the package goes (default <repo>/dist)")
    p.add_argument("--target", choices=TARGETS,
                   help="win64: carry the bundled Windows Python in runtime/")
    p.add_argument("--runtime-cache",
                   help="with --target: where the embeddable zip is kept")
    p.add_argument("--runtime-wheels", metavar="BUNDLE",
                   help="with --target: a win_amd64 wheel bundle (offline)")
    p = sub.add_parser("bootstrap", help="unpack the pinned embeddable Python "
                       "that runs a -win64 package")
    p.add_argument("--out", required=True)
    p.add_argument("--cache")
    p = sub.add_parser("verify", help="check a package, release dir or bundle")
    p.add_argument("target")
    p = sub.add_parser("wheels", help="make offline wheel bundles")
    p.add_argument("package")
    p.add_argument("--platform", action="append",
                   help=f"pip platform tag (default: {', '.join(PLATFORMS)})")
    p.add_argument("--out")
    p = sub.add_parser("lock", help="regenerate requirements.lock (network)")
    p.add_argument("--repo", default=str(REPO))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            out = build(a.version, a.commit, a.repo, a.out, target=a.target,
                        runtime_cache=a.runtime_cache,
                        runtime_wheels=a.runtime_wheels)
            out.pop("release")
        elif a.cmd == "bootstrap":
            out = bootstrap(a.out, a.cache)
            out["files"] = len(out["files"])
        elif a.cmd == "verify":
            out = verify(a.target)
        elif a.cmd == "wheels":
            out = wheels(a.package, a.platform or PLATFORMS, a.out)
        else:
            out = {"lock": str(lock(a.repo))}
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1))
    return 0 if not (isinstance(out, dict) and out.get("ok") is False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
