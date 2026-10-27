"""The bundled runtime: the Python a Windows release carries in `runtime\\`.

    python -m mentis.release.runtime build --out DIR [--cache DIR] [--wheels BUNDLE]
                                           [--lock requirements.lock]

THE RUNTIME (installer plan adm-06dbd34701bf, 1.2). python.org's embeddable
Python, pinned by `runtime.lock` beside this file (url, size, sha256), with
the wheels requirements.lock names pre-installed into `Lib\\site-packages` on
the build machine, so the target never runs pip, venv or the network.

- The zip is fetched into a cache and checked against the lock's sha256 and
  size before anything is unpacked. A mismatch is refused and the download
  deleted; a cached file that no longer matches is fetched again.
- The wheels come from a Stage 1 wheel bundle (`--wheels`, offline: verified
  whole as a `wheel-bundle` for `win_amd64` and for exactly this
  requirements.lock) or else from PyPI, `--require-hashes --only-binary=:all:
  --platform win_amd64 --python-version 3.12`. Either way every wheel's
  filename tags are checked to fit CPython 3.12 on win_amd64 before pip
  installs them, `--no-index` from that folder, with the lock's hashes.
- `python312._pth` replaces the embeddable one. It lists `python312.zip`,
  `.`, `Lib\\site-packages` and `..` -- the release root, so `mentis` imports
  with no .pth file and from any working directory -- and ends with `import
  site`. The ._pth makes the interpreter ignore PYTHONPATH, PYTHONHOME and
  the registry, so no Python on the machine can leak in.

THE RESULT. `<out>/runtime/` and `<out>/runtime.files.json`:
`{"runtime": {"kind": "embedded", "python": "3.12.10", "path": "runtime"},
"files": {"runtime/<relpath>": sha256}}` -- the `runtime` field RELEASE.json
carries, and the entries its `files` map gains. Paths are `/`-separated and
relative to the release root, as `build.verify` reads a release directory.
The tree is built as `runtime.partial` and renamed, so a half-built runtime
never carries the final name, and an existing one is never built over.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from mentis.release import build

HERE = pathlib.Path(__file__).resolve().parent
LOCKFILE = HERE / "runtime.lock"
PLATFORM = "win_amd64"
PTH = "python312._pth"
#: the ._pth's lines, in order; paths relative to runtime\
PTH_LINES = ("python312.zip", ".", r"Lib\site-packages", "..", "import site")
SITE = ("Lib", "site-packages")
FILES = "runtime.files.json"
#: what the built runtime must import, beside mentis, before it is kept
IMPORTS = ("regex", "pypdf", "psutil", "quickjs", "sqlite3", "ssl", "ctypes",
           "zlib")


class RuntimeRefused(build.BuildError):
    pass


def load_lock(path=LOCKFILE) -> dict:
    lock = json.loads(pathlib.Path(path).read_text("utf-8"))
    ok = (lock.get("format") == 1 and lock.get("kind") == "embedded"
          and lock.get("platform") == PLATFORM
          and re.fullmatch(r"3\.12\.\d+", str(lock.get("python")))
          and re.fullmatch(r"[0-9a-f]{64}", str(lock.get("sha256")))
          and isinstance(lock.get("size"), int)
          and str(lock.get("url")) == "https://www.python.org/ftp/python/"
          f"{lock['python']}/python-{lock['python']}-embed-amd64.zip")
    if not ok:
        raise RuntimeRefused(f"{path} is not a runtime lock for python.org's "
                             "embeddable 3.12 amd64 package")
    return lock


# -- the embeddable zip ---------------------------------------------------------

def check_download(path: pathlib.Path, lock: dict) -> None:
    size = path.stat().st_size
    digest = build.sha256_file(path)
    if size != lock["size"] or digest != lock["sha256"]:
        raise RuntimeRefused(
            f"{path.name} is not the pinned Python {lock['python']}: sha256 "
            f"{digest} ({size} bytes), the lock says {lock['sha256']} "
            f"({lock['size']} bytes)")


def fetch(lock: dict, cache: pathlib.Path) -> pathlib.Path:
    """The pinned zip in `cache`, checked. Refused on a hash mismatch, and
    the mismatching download is not kept."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / lock["url"].rsplit("/", 1)[1]
    if path.is_file():
        try:
            check_download(path, lock)
            return path
        except RuntimeRefused:
            path.unlink()                    # fetched again below
    part = path.with_name(path.name + ".partial")
    with urllib.request.urlopen(lock["url"], timeout=120) as r, \
            open(part, "wb") as f:
        shutil.copyfileobj(r, f, build.CHUNK)
    try:
        check_download(part, lock)
    except RuntimeRefused:
        part.unlink()
        raise
    os.replace(part, path)
    return path


def unpack(zip_path: pathlib.Path, dest: pathlib.Path) -> None:
    """Every entry extracted to exactly itself inside `dest`, or refused."""
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if not build._safe(info.filename):
                raise RuntimeRefused(f"{zip_path.name}: unsafe entry "
                                     f"{info.filename!r}")
            target = dest.joinpath(*info.filename.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, build.CHUNK)


def pth_text() -> str:
    return "\r\n".join(PTH_LINES) + "\r\n"


def write_pth(runtime: pathlib.Path) -> None:
    """The one ._pth: the embeddable package ships its own (without
    site-packages or the release root), replaced here."""
    stale = [p for p in runtime.glob("*._pth") if p.name != PTH]
    if stale:
        raise RuntimeRefused(f"unexpected ._pth files: {[p.name for p in stale]}")
    (runtime / PTH).write_bytes(pth_text().encode("ascii"))


# -- the wheels ---------------------------------------------------------------------

_WHEEL = re.compile(r"^(?P<name>[^-]+)-(?P<ver>[^-]+)(?:-\d[^-]*)?"
                    r"-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$")


def wheel_fits(filename: str) -> bool:
    """Whether a wheel installs into CPython 3.12 on win_amd64."""
    m = _WHEEL.match(filename)
    if not m:
        return False
    plats = m["plat"].split(".")
    abis = m["abi"].split(".")
    pys = m["py"].split(".")
    if not any(p in (PLATFORM, "any") for p in plats):
        return False
    if "cp312" in abis:
        return "cp312" in pys
    if "abi3" in abis:
        return any(re.fullmatch(r"cp3(\d+)", p) and int(p[3:]) <= 12
                   for p in pys)
    if "none" in abis:
        return any(p in ("py3", "py312", "cp312") for p in pys)
    return False


def check_wheels(folder: pathlib.Path, lock_bytes: bytes) -> list:
    """Every wheel in `folder` fits, and each locked project has exactly
    one. RuntimeRefused if not. Hashes are pip's to check (--require-hashes)."""
    names = sorted(p.name for p in folder.glob("*.whl"))
    wrong = [n for n in names if not wheel_fits(n)]
    if wrong:
        raise RuntimeRefused(f"wheels not for CPython 3.12 on {PLATFORM}: "
                             f"{wrong}")
    want = build.pins(lock_bytes.decode("utf-8"))
    have = {}
    for n in names:
        m = _WHEEL.match(n)
        have.setdefault(build._norm(m["name"]), []).append(m["ver"])
    for proj, ver in want.items():
        if have.get(proj) != [ver]:
            raise RuntimeRefused(f"{proj}=={ver}: the wheels hold "
                                 f"{have.get(proj) or 'none'}")
    extra = sorted(set(have) - set(want))
    if extra:
        raise RuntimeRefused(f"wheels requirements.lock does not name: {extra}")
    return names


def wheels_from_bundle(bundle, lock_bytes: bytes, into: pathlib.Path) -> None:
    bundle = pathlib.Path(bundle).resolve()
    v = build.verify(bundle)
    if not v["ok"] or v["kind"] != "wheel-bundle":
        raise RuntimeRefused(f"{bundle.name} does not verify as a wheel "
                             "bundle: " + json.dumps(v["problems"])[:800])
    with zipfile.ZipFile(bundle) as z:
        man = json.loads(z.read(build.WHEELS))
        if man.get("platform") != PLATFORM:
            raise RuntimeRefused(f"{bundle.name} is for {man.get('platform')}"
                                 f", not {PLATFORM}")
        if man.get("requirements_lock_sha256") != hashlib.sha256(
                lock_bytes).hexdigest():
            raise RuntimeRefused(f"{bundle.name} was made for a different "
                                 "requirements.lock")
        into.mkdir(parents=True, exist_ok=True)
        for name in man["wheels"]:
            (into / name).write_bytes(z.read(f"wheels/{name}"))


def _pip(*args) -> None:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PIP_", "PYTHON"))}
    build._run([sys.executable, "-I", "-m", "pip", *args,
                "--disable-pip-version-check", "--no-input", "-q"], env=env)


_TARGET = ("--only-binary=:all:", "--no-deps", "--require-hashes",
           "--platform", PLATFORM, "--python-version", "3.12",
           "--implementation", "cp", "--abi", "cp312", "--abi", "abi3",
           "--abi", "none")


def wheels_from_pypi(lock_path: pathlib.Path, into: pathlib.Path) -> None:
    _pip("download", "--no-cache-dir", *_TARGET, "-d", str(into),
         "-r", str(lock_path))


def install_wheels(runtime: pathlib.Path, wheels: pathlib.Path,
                   lock_path: pathlib.Path) -> None:
    site = runtime.joinpath(*SITE)
    site.mkdir(parents=True, exist_ok=True)
    _pip("install", "--no-index", "--find-links", str(wheels), "--no-compile",
         *_TARGET, "--target", str(site), "-r", str(lock_path))
    for left in ("bin", "Scripts"):            # pip --target's script folder
        if (site / left).exists():
            raise RuntimeRefused(f"a wheel installed scripts into {left}\\; "
                                 "the runtime carries none")


# -- the tree -----------------------------------------------------------------------

def hashes(runtime: pathlib.Path) -> dict:
    """{"runtime/<relpath>": sha256} for every file, as `build.verify` reads
    a release directory (which skips __pycache__)."""
    out = {}
    for root, dirs, names in os.walk(runtime):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        here = pathlib.Path(root)
        for n in sorted(names):
            rel = (here / n).relative_to(runtime.parent).as_posix()
            if not build._safe(rel):
                raise RuntimeRefused(f"unsafe path in the runtime: {rel}")
            out[rel] = build.sha256_file(here / n)
    return dict(sorted(out.items()))


def selftest(runtime: pathlib.Path) -> str:
    """The built runtime imports its wheels and the stdlib modules Mentis
    needs, isolated, from a neutral folder. Returns its version line."""
    code = ("import sys; " + "; ".join(f"import {m}" for m in IMPORTS)
            + "; print(sys.version.split()[0], sys.prefix)")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    with tempfile.TemporaryDirectory() as cwd:
        out = subprocess.run([str(runtime / "python.exe"), "-I", "-c", code],
                             cwd=cwd, env=env, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeRefused("the built runtime does not import "
                             f"{', '.join(IMPORTS)}: {out.stderr.strip()[-2000:]}")
    return out.stdout.strip()


def build_runtime(out, cache=None, wheels=None, lock_path=None,
                  runtime_lock=LOCKFILE, test=True) -> dict:
    out = pathlib.Path(out).resolve()
    final = out / "runtime"
    if final.exists() or (out / FILES).exists():
        raise RuntimeRefused(f"{final} exists; a runtime is never built over")
    lock = load_lock(runtime_lock)
    lock_path = pathlib.Path(lock_path or build.REPO / build.LOCK)
    lock_bytes = lock_path.read_bytes()
    cache = pathlib.Path(cache or pathlib.Path(tempfile.gettempdir())
                         / "mentis-runtime-cache")
    zip_path = fetch(lock, cache)
    part = out / "runtime.partial"
    if part.exists():
        shutil.rmtree(part)
    part.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="mentis-runtime-") as tmp:
        dl = pathlib.Path(tmp) / "wheels"
        if wheels:
            wheels_from_bundle(wheels, lock_bytes, dl)
        else:
            wheels_from_pypi(lock_path, dl)
        source = "bundle" if wheels else "pypi"
        wheel_names = check_wheels(dl, lock_bytes)
        unpack(zip_path, part)
        write_pth(part)
        install_wheels(part, dl, lock_path)
    selfcheck = selftest(part) if test else None
    os.replace(part, final)
    result = {"runtime": {"kind": "embedded", "python": lock["python"],
                          "path": "runtime"},
              "files": hashes(final)}
    (out / FILES).write_bytes(build._json(result))
    return {"runtime_dir": str(final), "files_json": str(out / FILES),
            "python_zip": str(zip_path), "python_sha256": lock["sha256"],
            "wheels": wheel_names, "wheel_source": source,
            "requirements_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
            "selftest": selfcheck, "file_count": len(result["files"]),
            "runtime": result["runtime"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mentis.release.runtime",
                                 description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", help="build runtime\\ and its hash list")
    p.add_argument("--out", required=True, help="the folder runtime\\ goes in")
    p.add_argument("--cache", help="where the embeddable zip is kept")
    p.add_argument("--wheels", help="a win_amd64 wheel bundle (offline)")
    p.add_argument("--lock", help="requirements.lock (default: the repo's)")
    a = ap.parse_args(argv)
    try:
        out = build_runtime(a.out, a.cache, a.wheels, a.lock)
    except build.BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
