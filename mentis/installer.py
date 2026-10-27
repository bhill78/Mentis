"""Install Mentis from its package: `python3.12 mentis-<v>.zip install`.

    python3.12 mentis-<v>.zip install [--brain PATH | --new-brain]
        [--owner @alias] [--port N] [--wheels BUNDLE] [--no-start]
        [--allow-breaking] [--json] [--progress jsonl]

WHAT INSTALL DOES, IN ORDER, and re-running it is safe at every step:

  1. VERIFY the package: its sidecar hash, the RELEASE.json contract, every
     file against its hash (`mentis.release.build.verify`), and that this
     interpreter is the Python the release needs.
  2. STAGE the release into `<root>/releases/<semver>+<commit12>/`: unpacked
     into `<name>.partial` and verified, given its own `.venv` with the
     dependencies of `requirements.lock` installed `--require-hashes` (from
     PyPI, or offline from a wheel bundle with `--wheels`, itself verified
     first), self-tested in that venv, verified again as a release
     directory, renamed into place (a rename Windows refuses for a moment is
     retried briefly), self-tested again there and LOCKED read-only
     (`mentis.readonly`). A release directory that already exists is
     verified, self-tested and reused, never written over.
  3. HAND OVER to the release's own interpreter (`<release>/.venv`), so
     everything after this runs the installed code with its dependencies --
     the package zip itself runs on a bare Python 3.12.
  4. THE BRAIN. `--new-brain` (the default when there is none) creates one at
     `<root>/brains/default` and bootstraps it for `--owner`. `--brain PATH`
     ADOPTS an existing Brain: a backup first (`mentis brain backup`,
     verified usable), then -- only where the Brain needs it -- `mentis
     brain reconcile` for a harmless pre-ledger open, and `mentis migrate
     --apply`. A Brain this release cannot use (NEEDS_ATTENTION, needing a
     newer Mentis, or a corpus.db that is no database) is refused with
     nothing changed, and so is a BACKUP (a folder holding BACKUP.json, or
     in the backup layout, `brains/backups/<corpus>/<stamp>-<kind>`; I4):
     serving it would invalidate it. `--new-brain` where
     `<root>/brains/default` already exists in ANY form -- a Brain, an
     empty folder, a file, a link -- is refused (`brain_exists`, I5) and it
     is never reused, bootstrapped into or touched: to use what is there,
     name it with `--brain`, which adopts it as above. With neither flag,
     a Brain at `<root>/brains/default` is adopted.
     An adopted Brain is the owner's and is written nothing beyond what
     adoption requires -- its backup, its migration, and ONE act: after
     both, `brain-forked` by the owner, detail {"fork_id": a new uuid4
     hex, "heads": the stream heads it forked at, "adopted_at": a hash of
     this machine's id and the Brain's absolute path, "install":
     install.json's id or null}, which gives this copy its own fork
     identity (design adm-6cebfabd6e9c, O1; a Brain without one is
     identified by its corpus_id). Adopting again a Brain whose last
     `brain-forked` act was written at the same `adopted_at` -- a re-run
     after an install that stopped before install.json -- writes no second
     one; a copy adopted at another path, or on another machine, gets its
     own. Its owner is the one it records (`--owner` naming
     anyone else, or given for a Brain that records no owner, is refused
     before anything changes), a baseline it carries is validated with
     `mentis.bootstrap --check`, and one it lacks is not written -- install
     says how its owner adds it. Everything about the Brain is read before
     anything is written, on connections that leave no file behind: a
     refusal leaves its folder byte-identical.
  5. THE BRAIN'S HEALTH before anything serves it: `mentis brain verify`,
     and `rebuild-derived` when the only finding is a missing derived index.
  6. `install.json` is written (atomic replace), then the launcher
     `<root>/bin/mentis(.cmd)`.
  7. START the server (unless `--no-start`) and check its health
     (`mentis.health.check`). An unhealthy server is stopped again and the
     install says so; install.json and the Brain are kept.

BUNDLED MODE (a `-win64` package; installer plan adm-06dbd34701bf, S2). A
package whose RELEASE.json has a `runtime` block carries its own Python in
`runtime/` -- python.org's embeddable 3.12 with the locked wheels already in
it, every file hashed with the rest. Staging makes no venv, runs no pip and
writes no .pth: the release root is on that Python's path through its
`python312._pth`. Steps 3-7 run with `runtime/python.exe`
(`install_state.venv_python` answers it), and the Python that ran the zip
(the installer's bootstrap copy) is used for nothing after step 2. A package
without `runtime` installs as before, into a venv (development, and Linux
and macOS).

An install root that already runs a different release is refused: that is
`mentis update`'s job. A root with an unfinished update or a decision waiting
(`state/update.journal.json`, `state/needs-attention.json`) is refused too,
and so is a re-run naming a new `--port` while this install's server runs on
install.json's port: `mentis stop` first.

A ROOT HOLDING A MENTIS FROM BEFORE STAGE 1 IS REFUSED (S6), with nothing
written: where there is no install.json but there is a `brain/` folder, a
`restart-*` folder, or a `releases/` folder holding anything but Stage 1
release folders (`<semver>+<commit12>`, and the `.partial` of one, which an
interrupted first install leaves). That is the layout `tools/release.py`
made, and on the owner's machine it is this OS's default root
(`mentis.home`), holding the live Brain.

THE PORT. `--port`, else install.json's, else the first free port from
FALLBACK_PORT (8761) upward. A new install never takes DEFAULT_PORT (8760),
the port the Mentis from before this installer serves on, even when asked
(I8). The one chosen is recorded in install.json, with the install's `id`
(a uuid4, made once and kept by every re-run and update), which the
server's `/api/server` reports beside its home (I3).

REPAIR (`--repair`, I6). Over an install, from a package of its current
release's VERSION: that release is staged again from the package even when
its folder is there but damaged or incomplete -- the new copy verified and
self-tested first, then the server stopped, the damaged copy set aside as
`releases/<name>.damaged-<stamp>` (recorded in install.json's
`set_aside`), never deleted -- and the server started again. The same
version from another commit replaces the current release the same way and
becomes current (the one it replaces becomes previous). The Brain is the
one install.json names and is never written: no bootstrap, no adoption, no
derived-index rebuild. Another version is `mentis update`'s.

THE RESULT (I1/I2, `mentis.progress`): `--json` prints one final object with
"outcome", "reason" and "message" whatever happened, an unexpected exception
included.

PROGRESS. `--progress jsonl` writes one JSON line per step on stdout
(`mentis.progress`: {"step", "state", "message"}) and the words a person
reads on stderr; with `--json` the result is one more line. The steps:
verify, stage, brain, backup, migrate, check, save, start, health.

THE RELEASE RUNTIME, shared with the updater and `mentis.cli`:
`stage_release`, `start_server`, `stop_ours`, `write_launcher`. These are
the only implementations: `mentis.updater`'s `stage`, `start_release` and
`stop_brain` call them (with the updater's journal hooks) and turn their
refusals and failures into its own StepFailed. Each imports what needs
dependencies (psutil) inside the function, so this module imports from the
package zip on a bare Python.

Exit status: 0 installed (and healthy), 1 installed but unhealthy, 2 refused
(nothing changed), 3 failed (said where; nothing deleted but a `.partial`,
which the next run discards) -- an unexpected exception included.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

from mentis import home, install_state, progress

#: the port the Mentis from before this installer serves on: never given to
#: a new install, asked for or not (I8)
DEFAULT_PORT = 8760
#: where the search for a new install's free port starts, and how many
#: ports it tries
FALLBACK_PORT = 8761
FALLBACK_SPAN = 100
PARTIAL = ".partial"
#: in a release's venv: one relative line naming the release directory
RELEASE_PTH = "mentis-release.pth"
#: how long a refused `<name>.partial` -> `<name>` rename is retried
RENAME_WAIT_S = 10.0
#: how long `stop_ours(free_wait_s=...)` callers usually wait for the Brain's
#: open lock to be let go after its server stopped
OPEN_WAIT_S = 15
#: the self-test: every module the runtime needs imports in the release venv
_SELFTEST = (
    "import json, sys\n"
    "import psutil, regex, pypdf\n"
    "import mentis.web, mentis.cli, mentis.health, mentis.installer\n"
    "import mentis.migrate, mentis.backups, mentis.brain.__main__\n"
    "from mentis import home\n"
    "from mentis.spine import migrations as m\n"
    "print(json.dumps({'release': home.release(), 'target': m.target(),\n"
    "                  'ids': [x.id for x in m.migrations()],\n"
    "                  'python': list(sys.version_info[:2])}))\n")


class _Said(RuntimeError):
    """An outcome said in words, with the short machine word of I2
    (`reason`) and any fields the result carries beside it (`extra`)."""
    REASON = "unknown"

    def __init__(self, message: str, reason: str | None = None, **extra):
        super().__init__(message)
        self.reason = reason or self.REASON
        self.extra = extra


class InstallRefused(_Said):
    """Declined before anything changed; said in words."""
    REASON = "refused"


class InstallFailed(_Said):
    """A step failed. Said where; nothing was deleted but a `.partial`."""
    REASON = "failed"


def _say(msg: str = "") -> None:
    progress.say(msg)


def _base_python() -> str:
    """The interpreter a release's venv is made from: this one, or the one
    this one's venv was made from."""
    return getattr(sys, "_base_executable", None) or sys.executable


def _env() -> dict:
    """What a release's own Python runs in: its code is found through
    RELEASE_PTH, never PYTHONPATH or another PYTHONHOME."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(cmd, *, cwd=None, timeout=1800) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], cwd=cwd, env=_env(),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def _tail(run) -> str:
    return (run.stderr or run.stdout or "").strip()[-2000:]


# -- the package ------------------------------------------------------------------

def package_facts(package) -> dict:
    """RELEASE.json of a package zip, and the release directory name it
    makes. Reads only; `verify_package` is the check."""
    package = pathlib.Path(package)
    with zipfile.ZipFile(package) as z:
        rel = json.loads(z.read("RELEASE.json"))
    return {**rel, "name": f"{rel['version']}+{rel['commit'][:12]}"}


def _python_fits(spec: str) -> bool:
    """`>=3.12,<3.13`-style specs, the only kind the contract writes."""
    have = sys.version_info[:2]
    for part in (p.strip() for p in spec.split(",") if p.strip()):
        for op in (">=", "<=", "==", "<", ">"):
            if part.startswith(op):
                want = tuple(int(x) for x in part[len(op):].split(".")[:2])
                ok = {">=": have >= want, "<=": have <= want,
                      "==": have == want, "<": have < want,
                      ">": have > want}[op]
                if not ok:
                    return False
                break
        else:
            return False
    return True


def verify_package(package) -> dict:
    """The package checked whole: hash, contract, every file, the Python.
    InstallRefused when anything is wrong."""
    from mentis.release import build
    package = pathlib.Path(package).resolve()
    if not package.is_file():
        raise InstallRefused(f"no package at {package}")
    v = build.verify(package)
    if not v["ok"] or v["kind"] != "package":
        raise InstallRefused(f"{package.name} does not verify: "
                             + json.dumps(v["problems"])[:1500])
    facts = package_facts(package)
    if not _python_fits(facts["python"]):
        raise InstallRefused(
            f"Mentis {facts['version']} needs Python {facts['python']}; this "
            f"is {sys.version.split()[0]} ({sys.executable})")
    if facts.get("runtime") and sys.platform != "win32":
        raise InstallRefused(
            f"{package.name} carries a Python for 64-bit Windows "
            f"({facts['runtime'].get('kind')} {facts['runtime'].get('python')})"
            "; this is not Windows. Use the package without -win64")
    return facts


# -- staging a release -----------------------------------------------------------

def _check_wheels(bundle, lock_bytes: bytes) -> pathlib.Path:
    """A wheel bundle verified whole, as a `wheel-bundle`, and made for
    exactly this requirements.lock. InstallRefused if not."""
    import hashlib
    from mentis.release import build
    bundle = pathlib.Path(bundle).resolve()
    v = build.verify(bundle)
    if not v["ok"] or v["kind"] != "wheel-bundle":
        raise InstallRefused(f"{bundle.name} does not verify as a wheel "
                             "bundle: " + json.dumps(v["problems"])[:800])
    with zipfile.ZipFile(bundle) as z:
        man = json.loads(z.read("WHEELS.json"))
    if man.get("requirements_lock_sha256") != hashlib.sha256(
            lock_bytes).hexdigest():
        raise InstallRefused(f"{bundle.name} was made for a different "
                             "requirements.lock than this package's")
    return bundle


def _unpack_wheels(bundle, into: pathlib.Path) -> pathlib.Path:
    with zipfile.ZipFile(bundle) as z:
        for name in z.namelist():
            if name.startswith("wheels/") and name.endswith(".whl"):
                z.extract(name, into)
    return into / "wheels"


def _make_venv(rel: pathlib.Path, wheels_dir=None) -> None:
    """The release's own `.venv`, with requirements.lock installed by hash,
    binary only, from PyPI or offline from `wheels_dir`."""
    venv = rel / ".venv"
    run = _run([_base_python(), "-m", "venv", "--without-pip", venv])
    if run.returncode:
        raise InstallFailed(f"could not make the venv: {_tail(run)}")
    py = install_state.venv_python(rel)
    extra = (["--no-index", "--find-links", str(wheels_dir)]
             if wheels_dir is not None else [])
    run = _run([_base_python(), "-m", "pip", "--python", py, "install",
                "--disable-pip-version-check", "--no-input", "-q",
                "--require-hashes", "--no-deps", "--only-binary=:all:",
                *extra, "-r", rel / "requirements.lock"])
    if run.returncode:
        raise InstallFailed("the dependencies did not install from "
                            f"requirements.lock: {_tail(run)}")


def _write_pth(rel: pathlib.Path) -> None:
    """The release's code is found through a .pth, RELATIVE to site-packages,
    so the venv imports exactly this release from any working directory --
    and still does once `<name>.partial` is renamed to `<name>`."""
    py = install_state.venv_python(rel)
    site = _run([py, "-I", "-c",
                 "import sysconfig; print(sysconfig.get_paths()['purelib'])"])
    if site.returncode:
        raise InstallFailed(f"the venv's python does not run: {_tail(site)}")
    purelib = pathlib.Path(site.stdout.strip())
    purelib.mkdir(parents=True, exist_ok=True)
    (purelib / RELEASE_PTH).write_text(os.path.relpath(rel, purelib) + "\n",
                                       encoding="utf-8")


def selftest(rel: pathlib.Path, facts: dict | None = None) -> dict:
    """Import everything the runtime needs in the release's own venv, from a
    neutral directory, and check it is THIS release: its version, commit,
    schema target, migrations and path. InstallFailed if not."""
    py = install_state.venv_python(rel)
    with tempfile.TemporaryDirectory(prefix="mentis-selftest-") as cwd:
        run = _run([py, "-I", "-c", _SELFTEST], cwd=cwd, timeout=300)
    if run.returncode:
        raise InstallFailed(f"{rel.name} failed its self-test: {_tail(run)}")
    out = json.loads(run.stdout.strip().splitlines()[-1])
    r = out.get("release") or {}
    if facts and (r.get("version") != facts["version"]
                  or r.get("commit") != facts["commit"]
                  or out.get("target") != facts["schema_target"]
                  or out.get("ids") != list(facts.get("migrations") or [])):
        raise InstallFailed(f"the release's self-test reports {out}, not "
                            f"{facts['version']} {facts['commit'][:12]} "
                            f"schema {facts['schema_target']}")
    if not r.get("path") or not os.path.samefile(r["path"], rel):
        raise InstallFailed(f"the venv imports {r.get('path')}, not {rel}")
    return out


def release_problems(rel: pathlib.Path) -> list:
    """Why `rel` is not a complete release (empty when it is): every file
    against its RELEASE.json, verified as a `release-dir`, and its own
    Python."""
    from mentis.release import build
    v = build.verify(rel)
    why = [] if v["ok"] and v.get("kind") == "release-dir" else (
        v.get("problems") or [f"verified as {v.get('kind')}"])[:5]
    py = install_state.venv_python(rel)
    if not py.exists():
        why.append(f"it has no {py.relative_to(rel).as_posix()}")
    return why


def _verify_dir(rel: pathlib.Path) -> None:
    why = release_problems(rel)
    if why:
        raise InstallFailed(f"{rel} does not verify as a release: "
                            + json.dumps(why, default=str)[:1500])


def _discard(path: pathlib.Path) -> None:
    from mentis import readonly
    if path.exists():
        try:
            readonly.unlock(path)
        except Exception:                                     # noqa: BLE001
            pass
        shutil.rmtree(path)


def _rename_into_place(partial: pathlib.Path, dest: pathlib.Path) -> None:
    """`<name>.partial` -> `<name>`. Windows refuses the rename for a moment
    while something (a scanner, the indexer) holds a handle in the freshly
    built venv: retried for RENAME_WAIT_S, then InstallFailed, the
    `.partial` kept for the next run to discard (ent-1335ae9a7512)."""
    end = time.monotonic() + RENAME_WAIT_S
    while True:
        try:
            os.rename(partial, dest)
            return
        except PermissionError as exc:
            if time.monotonic() >= end:
                raise InstallFailed(
                    f"{partial.name} could not be renamed to {dest.name} "
                    f"within {RENAME_WAIT_S:g}s ({exc}); something holds a "
                    "file in it. Run the same command again") from None
            time.sleep(0.25)


#: what a damaged release set aside by `install --repair` is renamed to:
#: `<name>.damaged-<UTC stamp>`, beside it in releases/
DAMAGED = ".damaged-"


def set_aside_name(name: str) -> str:
    return f"{name}{DAMAGED}{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"


def stage_release(where, package, *, wheels=None, report=_say,
                  creating=None, at=None, make_venv=None,
                  self_test=None, replace_damaged=None) -> dict:
    """Make `<root>/releases/<name>` from a package, or check and reuse the
    one that is there. {"name", "path", "created", "facts", "set_aside"}.
    See the module docstring. Touches no Brain. The one staging of releases:
    install and `mentis update` (`updater.stage`) both run it.

    An existing release is reused only when it is complete
    (`release_problems`) and passes its self-test, and is locked if it was
    left unlocked. Otherwise it is left as it is and InstallFailed -- unless
    `replace_damaged` is given (`install --repair`, I6): then the release is
    staged again from the package into `<name>.partial` exactly as a new one
    is, and only once that has verified and passed its self-test is
    `replace_damaged(partial)` called (it stops the server, which may be
    running from the damaged copy) and the damaged copy renamed aside to
    `<name>.damaged-<stamp>` (`set_aside`), never deleted. A new one is
    unpacked into `<name>.partial`, verified, given its venv, its bytecode
    compiled and recorded (BYTECODE.json, `build.bytecode_manifest`),
    self-tested, verified again, renamed into place (`_rename_into_place`),
    self-tested again where it now is, and locked. A release that fails a
    self-test is discarded.

    The updater's hooks: `creating()` is called before anything is made (so
    a journal can say the release is its own), `at(label)` at
    "staging:renamed", and `make_venv(rel, wheels_dir)` /
    `self_test(rel, facts)` replace `_make_venv` / `selftest`."""
    from mentis import readonly
    lay = where if isinstance(where, home.Layout) else home.Layout(where)
    make_venv = make_venv or _make_venv
    self_test = self_test or selftest
    facts = verify_package(package)
    name = facts["name"]
    dest = lay.release(name)
    damaged = None
    if dest.exists():
        report(f"Release {name} is already staged; checking it.")
        why = release_problems(dest)
        if not why:
            try:
                self_test(dest, facts)
            except Exception as exc:                          # noqa: BLE001
                if replace_damaged is None:
                    raise
                why = [f"its self-test failed: {exc}"]
        if why and replace_damaged is None:
            # only ever the install's current release (every other caller
            # stages a damaged copy again): Repair is the way
            raise InstallFailed(
                f"{dest} exists but is not a complete release ({why}); it was "
                "left as it is. Repairing Mentis (`install --repair` from "
                "this package) stages it again",
                "damaged", problems=why)
        if not why:
            if not readonly.is_locked(dest):
                # left by a staging that never finished: checked above, so it
                # is locked now, as staging would have
                report(f"Release {name} was not read-only; locking it.")
                readonly.lock(dest)
            if not readonly.is_locked(dest):
                raise InstallFailed(f"{dest} could not be locked read-only")
            return {"name": name, "path": str(dest), "created": False,
                    "facts": facts, "set_aside": None}
        damaged = why
        report(f"Release {name} is damaged ({json.dumps(why, default=str)[:600]}"
               "); staging it again from the package. The damaged copy is "
               "set aside, not deleted, once the new one has verified.")
    bundled = bool(facts.get("runtime"))
    bundle = None
    if wheels and bundled:
        report("This package carries its own Python and dependencies; the "
               "wheel bundle is not needed and was not used.")
    elif wheels:
        with zipfile.ZipFile(package) as z:
            bundle = _check_wheels(wheels, z.read("requirements.lock"))
    if creating is not None:
        creating()
    partial = dest.with_name(dest.name + PARTIAL)
    # never verified, never named in install.json: only ever a staging's
    _discard(partial)
    lay.releases.mkdir(parents=True, exist_ok=True)
    report(f"Unpacking {pathlib.Path(package).name} into releases/{name}.")
    with zipfile.ZipFile(package) as z:
        z.extractall(partial)      # every name was checked safe by verify
    _verify_dir_files(partial)
    if bundled:
        # S2: no venv, no pip, no .pth -- the runtime's own ._pth puts the
        # release root on its path
        py = install_state.venv_python(partial)
        if not py.is_file():
            raise InstallFailed(f"the package declares a bundled Python but "
                                f"has no {py.relative_to(partial).as_posix()}")
        report(f"It carries its own Python ({facts['runtime'].get('python')}"
               ", with its locked dependencies); nothing is downloaded or "
               "installed.")
        compile_with = [py, "-I"]
        compiled = [partial / "mentis",
                    partial / install_state.RUNTIME_DIR / "Lib" / "site-packages"]
    else:
        report("Creating its Python environment and installing its locked "
               "dependencies" + (" from the wheel bundle." if wheels else "."))
        with tempfile.TemporaryDirectory(prefix="mentis-wheels-") as tmp:
            make_venv(partial, _unpack_wheels(bundle, pathlib.Path(tmp))
                      if bundle else None)
        _write_pth(partial)
        compile_with, compiled = [_base_python()], [partial / "mentis"]
    # the release is read-only once locked, so its bytecode is made now, and
    # recorded: Python runs it in place of the source, so it is verified
    # like every other file (D4)
    from mentis.release import build
    # only what is there (a runtime need not carry site-packages), and in
    # UTF-8: compileall names folders, and a profile path may not fit the
    # console's code page
    compiled = [str(c) for c in compiled if pathlib.Path(c).is_dir()]
    run = _run([*compile_with, "-X", "utf8", "-m", "compileall", "-q",
                *compiled])
    if run.returncode:
        _discard(partial)
        raise InstallFailed(f"the release's code did not compile: {_tail(run)}")
    _replace(partial / build.BYTECODE,
             (json.dumps(build.bytecode_manifest(partial), indent=1,
                         sort_keys=True) + "\n").encode("utf-8"))
    report("Self-testing the release in its own environment.")
    try:
        self_test(partial, facts)
    except BaseException:
        _discard(partial)
        raise
    _verify_dir(partial)
    aside = None
    if damaged is not None:
        replace_damaged(partial)
        aside = lay.releases / set_aside_name(name)
        try:
            readonly.unlock(dest)
        except Exception:                                     # noqa: BLE001
            pass
        try:
            os.rename(dest, aside)
        except OSError as exc:
            raise InstallFailed(
                f"the damaged {dest.name} could not be set aside ({exc}); "
                "something still holds a file in it. Nothing was replaced; "
                "run the same command again", "busy") from None
        report(f"The damaged copy is kept as releases/{aside.name}.")
    _rename_into_place(partial, dest)
    if at is not None:
        at("staging:renamed")
    try:
        self_test(dest, facts)
    except BaseException:
        _discard(dest)
        raise
    readonly.lock(dest)
    if not readonly.is_locked(dest):
        raise InstallFailed(f"{dest} could not be locked read-only")
    report(f"Release {name} is staged, verified and locked read-only.")
    return {"name": name, "path": str(dest), "created": True, "facts": facts,
            "set_aside": str(aside) if aside else None}


def _verify_dir_files(partial: pathlib.Path) -> None:
    """The unpacked files against RELEASE.json, before anything is built on
    them (it has no venv yet, so `release_problems` would say so)."""
    from mentis.release import build
    v = build.verify(partial)
    if not v["ok"]:
        raise InstallFailed("the unpacked release does not match its "
                            "package: " + json.dumps(v["problems"])[:1500])


# -- servers -------------------------------------------------------------------------

def _inside(path, root) -> bool:
    if not path:
        return False
    p = os.path.normcase(os.path.realpath(str(path)))
    r = os.path.normcase(os.path.realpath(str(root)))
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)


def ours(lay: home.Layout, who: dict | None, brain) -> bool:
    """Whether this server is one this install runs: code under this root's
    releases/ AND serving this Brain. Only such a server is ever stopped."""
    return bool(who and who.get("code") and who.get("corpus")
                and _inside(who["code"], lay.releases)
                and os.path.normcase(os.path.realpath(who["corpus"]))
                == os.path.normcase(os.path.realpath(str(brain))))


def _serving_port(brain) -> int | None:
    """The port the Brain's own serving file says its server last took."""
    from mentis.spine import brainlock
    if not os.path.isdir(str(brain)):
        return None
    info = brainlock.serving(str(brain)) or {}
    return int(info["port"]) if info.get("port") else None


def stop_ours(where, *, port: int | None = None, brain=None,
              wait_s: float = 30, free_wait_s: float | None = None) -> dict:
    """Stop the server this install runs for its Brain: on its port, and on
    the port the Brain's serving file names if that differs. Graceful first,
    hard after (`mentis.servers.stop_server`). {"was_running", "stopped",
    "how", "why", "port"}. The one stopping of servers: `mentis stop`,
    install and `mentis update` (`updater.stop_brain`) all run it.

    A server that is not ours is never stopped: InstallRefused for anything
    else holding the port, and for a server serving this Brain from code
    outside this root's releases/. With `free_wait_s`, the Brain's open lock
    must then be let go within that many seconds (a worker, a command or a
    migration may still hold it): InstallFailed if it is not, and nothing
    was changed."""
    from mentis import servers
    from mentis.spine import brainlock
    lay = where if isinstance(where, home.Layout) else home.Layout(where)
    st = install_state.load(lay, required=port is None or brain is None)
    port = int(port or st["port"])
    brain = str(brain or st["brain"])
    out = {"was_running": False, "stopped": True, "how": None, "why": None,
           "port": port}
    for p in sorted({port, _serving_port(brain) or port}):
        who = servers.identity(p, timeout=5)
        if who is None:
            ports = servers.listening() if p == port else None
            if ports is not None and p in ports:
                raise InstallRefused(f":{p} is held by pid {ports[p]}, which "
                                     "is not a Mentis server; left alone")
            continue
        if p != port and not (who.get("corpus") and _same_path(
                who["corpus"], brain)):
            continue        # the serving file is stale: another Brain's now
        if not ours(lay, who, brain):
            raise InstallRefused(
                f"the server on :{p} (pid {who['pid']}, code {who['code']}, "
                f"Brain {who.get('corpus')}) is not this install's; left alone")
        got = servers.stop_server(who, wait_s)
        out = {"was_running": True, **got, "port": p}
        if not got["stopped"]:
            return out
    if free_wait_s is not None and os.path.isdir(brain):
        end = time.monotonic() + free_wait_s
        while brainlock.is_open(brain):
            if time.monotonic() > end:
                raise InstallFailed(
                    f"something still has the Brain at {brain} open (a worker "
                    "or a command); it was not changed")
            time.sleep(0.5)
    return out


def start_server(where, name: str | None = None, *, brain=None,
                 port: int | None = None, wait_s: float = 120) -> dict:
    """Start release `name` (default: install.json's current) serving the
    Brain on the port, detached, logging to `<root>/install-logs/`. Returns
    its identity once it answers from that release, for that Brain, and owns
    the port -- at once when it already does. The one starting of servers:
    `mentis start`, install and `mentis update` (`updater.start_release`) all
    run it. InstallRefused if the port is taken; InstallFailed if it does not
    come up (the log's tail is in the message)."""
    from mentis import servers
    lay = where if isinstance(where, home.Layout) else home.Layout(where)
    st = install_state.load(lay, required=not (name and brain and port))
    name = name or st["current"]
    brain = os.path.abspath(str(brain or st["brain"]))
    port = int(port or st["port"])
    rel = lay.release(name)
    py = install_state.venv_python(rel)
    if not py.is_file():
        raise InstallFailed(f"release {name} has no Python at {py}")
    who = servers.identity(port, timeout=2)
    if (who and _inside(who.get("code"), rel) and who.get("corpus")
            and _same_path(who["corpus"], brain)):
        return who                         # already this release, this Brain
    ports = servers.listening()
    if ports is None:
        raise InstallRefused("cannot tell which ports are in use; not started")
    if port in ports:
        who = servers.identity(port)
        raise InstallRefused(
            f":{port} is already in use by pid {ports[port]}"
            + (f" ({who['code']})" if who else ""))
    lay.logs.mkdir(parents=True, exist_ok=True)
    log_path = lay.logs / f"server-{name}.log"
    # the directory a dispatched agent works in: the install's own, never
    # the read-only release
    workspace = lay.root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    # -X utf8: its output goes to a log file, where `-I` (which ignores
    # PYTHONIOENCODING) would leave Windows' ANSI code page, and the first
    # line it prints names the Brain -- a profile path that code page may
    # not hold stops the server before it serves
    cmd = [str(py), "-I", "-X", "utf8", "-m", "mentis.web", brain,
           "--port", str(port), "--workspace", str(workspace)]
    repo = (st or {}).get("repository")
    if repo:
        cmd += ["--repository", repo]
    # A hidden console, not none: see tools/release.py launch.
    flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
             if sys.platform == "win32" else 0)
    with open(log_path, "ab") as log:
        log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting "
                  f"{name} on :{port}\n".encode("utf-8"))
        log.flush()
        proc = subprocess.Popen(
            cmd, cwd=str(rel), env=_env(), stdout=log,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
            start_new_session=sys.platform != "win32")
    end = time.time() + wait_s
    while time.time() < end:
        who = servers.identity(port, timeout=2)
        owner = (servers.listening() or {}).get(port)
        # OURS: answering from this release, for this Brain, and owning the
        # port. Not the pid started: a venv's python.exe on Windows runs the
        # server as a child.
        if (who and owner == who["pid"] and _inside(who.get("code"), rel)
                and who.get("corpus") and _same_path(who["corpus"], brain)):
            return {**who, "log": str(log_path), "launched_pid": proc.pid}
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    if proc.poll() is None:
        proc.kill()
    text = log_path.read_text("utf-8", errors="replace")
    tail = text[text.rfind("\n--- "):][-1500:]
    raise InstallFailed(f"release {name} did not come up on :{port} "
                        f"(exit {proc.poll()}); {log_path}:\n{tail}")


# -- the launcher ---------------------------------------------------------------------

_LAUNCH_PY = '''"""The Mentis launcher: run `mentis.cli` from install.json's current release.

Written by the installer; stdlib only. Reads `<root>/state/install.json` on
every run, so an update switches what runs by rewriting that file alone.
"""
import json, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "state" / "install.json"
try:
    current = json.loads(STATE.read_text(encoding="utf-8"))["current"]
except (OSError, ValueError, KeyError) as exc:
    sys.exit(f"mentis: cannot read {STATE}: {exc}")
rel = ROOT / "releases" / current
try:
    runtime = json.loads((rel / "RELEASE.json").read_text(
        encoding="utf-8")).get("runtime")
except (OSError, ValueError, AttributeError):
    runtime = None
if isinstance(runtime, dict) and runtime.get("path") == "runtime":
    py = rel / "runtime" / "python.exe"          # bundled: its own Python
else:
    py = rel / ".venv" / ("Scripts/python.exe" if os.name == "nt"
                          else "bin/python")
if not py.is_file():
    sys.exit(f"mentis: the current release {current} has no Python at {py}")
env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
env["MENTIS_HOME"] = str(ROOT)
cmd = [str(py), "-I", "-m", "mentis.cli", *sys.argv[1:]]
if os.name == "nt":
    sys.exit(subprocess.call(cmd, env=env))
os.execve(str(py), cmd, env)
'''


#: the Windows launcher is ONE line of exactly this many bytes before its
#: CRLF, whatever release it names (see `launcher_text`)
LAUNCHER_LINE = 400


def launcher_text(lay: home.Layout, release: str) -> str:
    """What `bin/mentis(.cmd)` holds for `release` (a release directory
    name). It runs `mentis-launch.py` -- which reads install.json and runs
    `mentis.cli` from the CURRENT release -- with that release's own Python
    (`install_state.venv_python`: bundled `runtime/python.exe`, or its
    venv's), named RELATIVE to the launcher's own folder, never the Python
    that ran the installer, so no profile path is written into it (S3).

    The Windows file is a single line padded with spaces to LAUNCHER_LINE
    bytes and nothing after it. cmd.exe reads a batch file a line at a time
    and resumes at a byte offset after each command, so a `mentis update`
    run through this file rewrites the file it is running: with every
    version the same length, the offset cmd.exe resumes at is the end of the
    new file too, and nothing of it runs twice or half. The exit status is
    that of its one command."""
    rel = lay.release(release)
    py = install_state.venv_python(rel).relative_to(lay.root)
    if sys.platform == "win32":
        line = ('@"%~dp0..\\' + "\\".join(py.parts)
                + '" -I "%~dp0mentis-launch.py" %*')
        if len(line) > LAUNCHER_LINE:
            raise InstallFailed(f"the release name {release!r} is too long "
                                "for the launcher")
        return line.ljust(LAUNCHER_LINE) + "\r\n"
    return ('#!/bin/sh\nhere="$(dirname "$0")"\nexec "$here/../'
            + "/".join(py.parts) + '" -I "$here/mentis-launch.py" "$@"\n')


def _replace(path: pathlib.Path, data: bytes) -> None:
    """Write by atomic replace: a reader sees the old file or the new one."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_launcher(where, release: str | None = None) -> pathlib.Path:
    """`<root>/bin/mentis(.cmd)` and the `mentis-launch.py` it runs, for
    `release` (default: install.json's current), written in UTF-8 by atomic
    replace. Written by install, and rewritten whenever install.json's
    current changes -- the updater's switch, switch back, rollback and resume
    all go through `updater._set_install` -- so the launcher always names a
    Python that is there (S3)."""
    lay = where if isinstance(where, home.Layout) else home.Layout(where)
    release = release or install_state.load(lay, required=True)["current"]
    text = launcher_text(lay, release)
    lay.bin.mkdir(parents=True, exist_ok=True)
    _replace(lay.bin / "mentis-launch.py", _LAUNCH_PY.encode("utf-8"))
    _replace(lay.launcher, text.encode("utf-8"))
    if sys.platform != "win32":
        os.chmod(lay.launcher, 0o755)
    return lay.launcher


def launcher_problems(lay: home.Layout, release: str) -> list:
    """Why `bin/` does not hold the launcher `write_launcher` writes for
    `release` (empty when it does): each of its two files missing or not
    byte for byte what it should be. Damage like a release's own files
    (D16); `install --repair` writes them again."""
    try:
        want = {lay.launcher: launcher_text(lay, release).encode("utf-8"),
                lay.bin / "mentis-launch.py": _LAUNCH_PY.encode("utf-8")}
    except (InstallFailed, ValueError) as exc:
        return [{"problem": "launcher", "detail": str(exc)}]
    why = []
    for path, data in want.items():
        rel = path.relative_to(lay.root).as_posix()
        try:
            if path.read_bytes() != data:
                why.append({"problem": "changed", "path": rel})
        except FileNotFoundError:
            why.append({"problem": "missing", "path": rel})
        except OSError as exc:
            why.append({"problem": "unreadable", "path": rel,
                        "detail": str(exc)})
    return why


# -- install, part one: from the package, on a bare Python ----------------------------

def _package_path() -> pathlib.Path | None:
    """The zip this code runs from, when it runs from one."""
    here = pathlib.Path(__file__).resolve()
    for p in here.parents:
        if p.is_file() and zipfile.is_zipfile(p):
            return p
    return None


def _refuse_unfinished(lay: home.Layout) -> None:
    if lay.needs_attention.exists():
        raise InstallRefused(
            f"a decision is waiting ({lay.needs_attention}); nothing is "
            "installed over it. Run `mentis status`", "needs_attention")
    if lay.journal.exists():
        raise InstallRefused(
            f"an update is unfinished ({lay.journal}); run `mentis update "
            "--resume` first", "update_pending")


def _stage1_release_dir(name: str) -> bool:
    """A release folder this installer makes: `<name>`, the `.partial` of
    one, or a damaged one `install --repair` set aside."""
    return home.is_release_name(name) or (
        name.endswith(PARTIAL) and home.is_release_name(name[:-len(PARTIAL)])
    ) or (DAMAGED in name and home.is_release_name(name.split(DAMAGED)[0]))


def legacy_home(lay: home.Layout) -> list[str]:
    """What makes `lay.root` the home of a Mentis from before Stage 1 (the
    `tools/release.py` deployment), in words; empty when nothing does. Asked
    only where there is no install.json. Reads only."""
    root = lay.root
    if not root.is_dir():
        return []
    why = []
    if (root / "corpus.db").exists():
        # the folder is itself a Brain (D16): installing would write releases/,
        # bin/ and state/ into it
        why.append(f"{root / 'corpus.db'} (the folder is itself a Brain)")
    if (root / "brain").is_dir():
        why.append(f"{root / 'brain'} (an older Mentis's Brain)")
    restarts = sorted(p.name for p in root.glob("restart-*") if p.is_dir())
    if restarts:
        why.append(f"{len(restarts)} restart-* folder(s), e.g. "
                   f"{root / restarts[0]}")
    if lay.releases.is_dir():
        other = sorted(p.name for p in lay.releases.iterdir()
                       if not _stage1_release_dir(p.name))
        if other:
            why.append(f"{lay.releases} holding {', '.join(other[:3])}"
                       + (" ..." if len(other) > 3 else "")
                       + ", which are not Stage 1 releases")
    return why


def _refuse_legacy(lay: home.Layout) -> None:
    why = legacy_home(lay)
    if why:
        raise InstallRefused(
            f"{lay.root} holds a Mentis from before this installer, or a "
            "Brain (" + "; ".join(why) + "), and no state/install.json. "
            "Nothing was written. Installing here would share that folder; "
            f"set {home.ENV} to another folder to install beside it",
            "legacy_home", home=str(lay.root))


def _bindable(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(listening: dict | None = None) -> int:
    """The port a new install takes when it is given none: the first free
    port from FALLBACK_PORT upward, NEVER DEFAULT_PORT (I8): that is the port
    the Mentis from before this installer serves on, and a new install
    taking it while that one is down would leave two servers racing for one
    port. `listening`: `servers.listening()`'s answer (asked when not
    given). InstallRefused when it cannot be told or none is free."""
    if listening is None:
        from mentis import servers
        listening = servers.listening()
    if listening is None:
        raise InstallRefused("cannot tell which ports are in use, so no port "
                             "was chosen; give --port", "port")
    for p in range(FALLBACK_PORT, FALLBACK_PORT + FALLBACK_SPAN):
        if p not in listening and _bindable(p):
            return p
    raise InstallRefused(f"no free port from {FALLBACK_PORT} to "
                         f"{FALLBACK_PORT + FALLBACK_SPAN - 1}; give --port",
                         "port")


def _version_of(name: str) -> str:
    return name.split("+", 1)[0]


def _refuse_brain_early(lay: home.Layout, a, st) -> None:
    """The Brain refusals that need nothing but the standard library, made
    before anything is staged: `--new-brain` over anything at all (I5) and
    `--brain` naming a backup (I4). `_brain_choice` makes them again, in the
    release's own Python, before the Brain is touched."""
    from mentis.brain import inspect
    if getattr(a, "new_brain", False):
        target = st["brain"] if st else str(lay.default_brain)
        if st or os.path.lexists(target):
            raise InstallRefused(_brain_exists_words(target, st),
                                 "brain_exists", brain=target)
    if getattr(a, "brain", None) and not st:
        why = inspect.backup_reason(a.brain)
        if why:
            raise InstallRefused(_backup_words(os.path.abspath(a.brain), why),
                                 "backup", brain=os.path.abspath(a.brain))


def _brain_exists_words(target: str, st) -> str:
    if st:
        return (f"this install already has its Brain, {target}; --new-brain "
                "makes no other and touches nothing. Nothing was changed")
    return (f"{target} already exists, so no new Brain was made there and it "
            "was not touched. Nothing was changed. To use what is there, "
            "choose it as an existing Brain (--brain)")


def _backup_words(brain: str, why: str) -> str:
    return (f"{brain} is a backup of a Brain ({why}), not a Brain to serve: "
            "serving it would change it, and it would no longer restore. "
            "Nothing was changed. Choose the Brain itself, or restore the "
            "backup first (`mentis brain restore-plan`)")


def _stopper(lay: home.Layout):
    """For `install --repair`: stop this install's server with the NEW copy
    of the release (`<name>.partial`, verified and self-tested), since the
    copy it may be running from is the damaged one and this Python (the
    bootstrap) has no psutil."""
    def stop(partial: pathlib.Path) -> None:
        py = install_state.venv_python(partial)
        run = subprocess.run(
            [str(py), "-I", "-m", "mentis.cli", "stop", "--json"],
            env={**_env(), home.ENV: str(lay.root)}, cwd=str(lay.root),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
        if run.returncode != 0:
            raise InstallFailed(
                "Mentis could not be stopped before the damaged release was "
                f"set aside (exit {run.returncode}): {_tail(run)}; nothing "
                "was replaced", "not_stopped")
    return stop


def _served_from(port, rel: pathlib.Path) -> bool:
    """Whether the server answering on `port` runs from release folder
    `rel`, by its own `/api/server` answer (standard library only). False
    when nothing answers."""
    import urllib.request
    if not port:
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/api/server",
                                    timeout=3) as r:
            who = json.loads(r.read().decode("utf-8"))
    except Exception:                                         # noqa: BLE001
        return False
    if not isinstance(who, dict):
        return False
    paths = [(who.get("release") or {}).get("path"),
             (who.get("code") or {}).get("repository")]
    return any(isinstance(p, str) and p and (_same_path(p, rel)
                                             or _inside(p, rel))
               for p in paths)


def _restager(lay: home.Layout, st: dict | None):
    """For a damaged release that is NOT the current one (N2: an update,
    rollback or downgrade to its version, and a fresh install over one a
    refused install left): stage it again from the package, as a repair
    does. Nothing serves it, normally; if this install's server does, it is
    stopped first by the new copy, as a repair stops it."""
    stop = _stopper(lay)

    def restage(partial: pathlib.Path) -> None:
        rel = partial.with_name(partial.name[:-len(PARTIAL)])
        if st and _served_from(st.get("port"), rel):
            stop(partial)
    return restage


def _record_set_aside(lay: home.Layout, staged: dict) -> None:
    """A damaged copy staging set aside, recorded in install.json's
    `set_aside` so `remove-program-files` takes it too."""
    if staged.get("set_aside") and lay.install_json.is_file():
        st = install_state.load(lay, required=False) or {}
        install_state.update(lay, set_aside=list(st.get("set_aside") or []) + [
            pathlib.Path(staged["set_aside"]).name])


def _undo_fresh_staging(lay: home.Layout, staged: dict | None) -> list:
    """A first install that ended without install.json (refused or failed
    after staging, ent-e66ea79fe0ce): nothing records the release it staged,
    so nothing would ever remove it. It is removed, with a damaged copy set
    aside for it, and `releases/` if that leaves it empty. What was removed."""
    gone = []
    if lay.install_json.exists() or not staged:
        return gone
    partial = lay.releases / (staged["name"] + PARTIAL)
    for p in (staged.get("path"), staged.get("set_aside"), partial):
        if p and pathlib.Path(p).exists():
            try:
                _discard(pathlib.Path(p))
                gone.append(pathlib.Path(p).name)
            except OSError as exc:
                _say(f"{p} could not be removed ({exc}).")
    with contextlib.suppress(OSError):
        lay.releases.rmdir()               # only when nothing else is there
    if gone:
        _say("Nothing was installed, so the release staged for it was "
             f"removed again: {', '.join(gone)}.")
    return gone


def install(a) -> tuple[int, dict]:
    lay = home.Layout()
    package = pathlib.Path(a.package).resolve() if a.package else _package_path()
    if package is None:
        raise InstallRefused("no package: run `python3.12 <package.zip> "
                             "install`, or give --package", "no_package")
    progress.emit("verify", progress.RUNNING, "Checking the package's files")
    _refuse_unfinished(lay)
    st = install_state.load(lay, required=False)
    if a.repair:
        if st is None:
            raise InstallRefused(f"nothing is installed at {lay.root}, so there "
                                 "is nothing to repair", "not_installed")
        if a.new_brain:
            raise InstallRefused("--repair never makes a Brain; it repairs the "
                                 "install that serves " + st["brain"], "usage")
    elif st is None:
        _refuse_legacy(lay)
    _refuse_brain_early(lay, a, st)
    if st is None and a.port == DEFAULT_PORT:
        raise InstallRefused(
            f"port {DEFAULT_PORT} is the port the Mentis from before this "
            "installer serves on; a new install never takes it. Give another "
            "--port, or none", "port")
    facts = verify_package(package)
    _say(f"Mentis {facts['version']} (commit {facts['commit'][:12]}), "
         f"package verified: every file matches its recorded hash.")
    _say(f"Install root: {lay.root}")
    if st and st["current"] != facts["name"]:
        if not (a.repair and _version_of(st["current"]) == facts["version"]):
            raise InstallRefused(
                f"{lay.root} already runs {st['current']}; installing "
                f"{facts['name']} over it is an update: run `mentis update "
                f"{package}`", "update")
        _say(f"Repair: {facts['name']} is the same version as "
             f"{st['current']} from another commit; it replaces it.")
    progress.emit("verify", progress.DONE,
                  f"Mentis {facts['version']}: every file matches")
    progress.emit("stage", progress.RUNNING, "Setting up Mentis's files")
    # a repair stops the server first; a first install restages a damaged
    # copy an earlier, refused one left (nothing serves it); re-running an
    # install over a damaged current release says to repair it
    staged = stage_release(lay, package, wheels=a.wheels,
                           replace_damaged=(_stopper(lay) if a.repair
                                            else _restager(lay, st)
                                            if st is None else None))
    if st is None:
        try:
            got = _install_from(lay, a, staged)
        finally:
            _undo_fresh_staging(lay, staged)
        _record_set_aside(lay, staged)
        return got
    _record_set_aside(lay, staged)
    return _install_from(lay, a, staged)


def _install_from(lay: home.Layout, a, staged: dict) -> tuple[int, dict]:
    """Install, part one's end: the rest runs in the staged release's own
    Python (`_setup`)."""
    progress.emit("stage", progress.DONE, f"Release {staged['name']} is ready")
    py = install_state.venv_python(staged["path"])
    fd, result_file = tempfile.mkstemp(prefix="mentis-install-",
                                       suffix=".json")
    os.close(fd)
    cmd = [str(py), "-I", "-m", "mentis.installer", "_setup",
           "--release", staged["name"], "--result-file", result_file,
           *progress.argv()]
    for flag in ("brain", "owner", "port"):
        if getattr(a, flag) is not None:
            cmd += [f"--{flag}", str(getattr(a, flag))]
    for flag in ("new_brain", "no_start", "allow_breaking", "repair"):
        if getattr(a, flag):
            cmd.append("--" + flag.replace("_", "-"))
    env = {**_env(), home.ENV: str(lay.root)}
    _say("Continuing with the release's own Python.")
    try:
        code = subprocess.call(cmd, env=env)
        try:
            doc = json.loads(pathlib.Path(result_file).read_text("utf-8"))
        except (OSError, ValueError):
            doc = None
    finally:
        with contextlib.suppress(OSError):
            os.remove(result_file)
    if not (isinstance(doc, dict) and doc.get("outcome") in progress.EXIT):
        return 3, progress.outcome_doc(
            progress.FAILED_OUTCOME, "crashed",
            f"the release's own setup ended with exit {code} and gave no "
            "result; see the words above", release=staged["name"])
    if staged.get("set_aside"):
        doc["set_aside"] = staged["set_aside"]
    return progress.EXIT[doc["outcome"]], doc


def update(a) -> tuple[int, dict | None]:
    """`<package.zip> update [--resume] [--yes] [--json] [--progress jsonl]`:
    `mentis update`, run WITHOUT the current release's code (D12) -- which
    may be the damaged thing -- by the package's own installer on the
    bootstrap Python. The package's release is verified and staged (or a
    complete one reused) and the transaction then runs in ITS Python
    (`mentis.updater update <package> --staged-here`). `--resume` stages
    nothing: it runs `mentis.updater update --resume` in whichever release
    the unfinished update names -- its new one, else its old one -- whose
    files verify. The updater prints the final result itself (I2); None is
    returned for it, unless it ended without one."""
    lay = home.Layout()
    progress.emit("verify", progress.RUNNING, "Checking the package's files")
    st = install_state.load(lay, required=False)
    if st is None:
        raise InstallRefused(f"nothing is installed at {lay.root}, so there "
                             "is nothing to update; install first",
                             "not_installed")
    tail = [*progress.argv()] + (["--json"] if a.json else [])
    if a.resume:
        j = install_state.read_json(lay.journal)
        if j is None:
            progress.emit("verify", progress.DONE, "No unfinished update")
            return 0, progress.outcome_doc(
                progress.OK, "nothing_to_resume",
                "There is no unfinished update.", running=None,
                previous_restored=False, update=None)
        names = [(j.get(k) or {}).get("release") for k in ("to", "from")]

        def whole(n) -> bool:
            return bool(n and home.is_release_name(n)
                        and lay.release(n).is_dir()
                        and not release_problems(lay.release(n)))
        # N3: a release of the update's that is damaged or gone is staged
        # again from this package when the package is that release, so the
        # resume can switch back to it, or start it
        package = (pathlib.Path(a.package).resolve() if a.package
                   else _package_path())
        facts = verify_package(package) if package else None
        mine = facts["name"] if facts else None
        if mine in names and not whole(mine):
            _say(f"{mine} is damaged or missing; staging it again from "
                 f"{package.name} before resuming.")
            progress.emit("stage", progress.RUNNING,
                          f"Setting up Mentis {facts['version']} again")
            staged = stage_release(lay, package, wheels=a.wheels,
                                   replace_damaged=_restager(lay, st))
            _record_set_aside(lay, staged)
            progress.emit("stage", progress.DONE,
                          f"Release {staged['name']} is ready")
        runs = next((n for n in names if whole(n)), None)
        if runs is None:
            have = (f"these setup files are Mentis {facts['name']}, which is "
                    "neither" if facts else "no setup files were found")
            raise InstallFailed(
                f"neither release the unfinished update names "
                f"({', '.join(n for n in names if n)}) is whole, and {have}, "
                "so it cannot be finished from here. Nothing was deleted: "
                "the Brain and its backup are kept. Setup files for either "
                "release can stage it again; then finish the update",
                "damaged")
        progress.emit("verify", progress.DONE, f"Resuming with {runs}")
        cmd = [str(install_state.venv_python(lay.release(runs))), "-I", "-m",
               "mentis.updater", "update", "--resume", *tail]
    else:
        package = (pathlib.Path(a.package).resolve() if a.package
                   else _package_path())
        if package is None:
            raise InstallRefused("no package: run `<package.zip> update`",
                                 "no_package")
        _refuse_unfinished(lay)
        facts = verify_package(package)
        if facts["name"] == st["current"]:
            raise InstallRefused(f"{facts['name']} is already the current "
                                 "release; nothing to update",
                                 "already_current")
        progress.emit("verify", progress.DONE,
                      f"Mentis {facts['version']}: every file matches")
        progress.emit("stage", progress.RUNNING, "Preparing the new release")
        # N2: a damaged copy of it (kept by an undone update, or the
        # previous release) is staged again from this package, not refused
        staged = stage_release(lay, package, wheels=a.wheels,
                               replace_damaged=_restager(lay, st))
        _record_set_aside(lay, staged)
        progress.emit("stage", progress.DONE,
                      f"Release {staged['name']} is ready")
        cmd = [str(install_state.venv_python(staged["path"])), "-I", "-m",
               "mentis.updater", "update", str(package), *tail]
        if a.yes:
            cmd.append("--yes")
        if staged["created"]:
            cmd.append("--staged-here")
        if a.wheels:
            cmd += ["--wheels", str(pathlib.Path(a.wheels).resolve())]
    _say("Continuing with the new release's own Python.")
    code = subprocess.call(cmd, env={**_env(), home.ENV: str(lay.root)})
    if code in progress.OUTCOME_OF and code != 1:
        return code, None
    return 3, progress.outcome_doc(
        progress.FAILED_OUTCOME, "crashed",
        f"the update ended with exit {code} and gave no result; see the "
        "words above", running=None, previous_restored=False, update=None)


# -- install, part two: in the release's venv -------------------------------------

def _same_path(a, b) -> bool:
    return (os.path.normcase(os.path.realpath(str(a)))
            == os.path.normcase(os.path.realpath(str(b))))


def _status(brain: str):
    """`migrations.status_of`, which reads on a connection of its own and
    leaves no file behind. A corpus.db that is not a SQLite database is
    refused (ent-ffced1253a38), before anything is written."""
    import sqlite3
    from mentis.spine import migrations
    try:
        return migrations.status_of(brain)
    except sqlite3.DatabaseError as exc:
        raise InstallRefused(
            f"{os.path.join(brain, 'corpus.db')} is not a Mentis Brain: it "
            f"cannot be read as a database ({exc}); nothing was changed"
        ) from None


def _writable(brain: str) -> bool:
    """Whether this release can serve the Brain as it is: no adoption, no
    migration. Reads only."""
    return _status(brain).writable


def _brain_choice(lay, a, st) -> tuple[str, str]:
    """(path, "new" | "adopt" | "existing"); "existing" is install.json's.

    `--new-brain` makes a Brain only where nothing at all is: anything at
    the target -- a Brain at any schema, an empty folder, a file, a link --
    is refused (`brain_exists`, I5), never reused, bootstrapped into or
    touched. A backup is never adopted (`backup`, I4)."""
    from mentis.brain import inspect
    if getattr(a, "new_brain", False):
        target = st["brain"] if st else str(lay.default_brain)
        if st or os.path.lexists(target):
            raise InstallRefused(_brain_exists_words(target, st),
                                 "brain_exists", brain=target)
        return target, "new"
    if st:
        if a.brain and not _same_path(a.brain, st["brain"]):
            raise InstallRefused(f"this install serves the Brain {st['brain']}"
                                 f", not {os.path.abspath(a.brain)}",
                                 "other_brain", brain=st["brain"])
        return st["brain"], "existing"
    brain = os.path.abspath(a.brain) if a.brain else str(lay.default_brain)
    why = inspect.backup_reason(brain)
    if why:
        raise InstallRefused(_backup_words(brain, why), "backup", brain=brain)
    if os.path.isfile(os.path.join(brain, "corpus.db")):
        # adopted -- backup first, its owner read -- never served as it is
        return brain, "adopt"
    if a.brain:
        raise InstallRefused(f"no Brain at {brain} to adopt; use "
                             "--new-brain to create one", "not_a_brain",
                             brain=brain)
    if os.path.lexists(brain):
        raise InstallRefused(_brain_exists_words(brain, None), "brain_exists",
                             brain=brain)
    return brain, "new"


def _refuse_moving_a_running_server(lay, st, port: int) -> None:
    """A re-run that names a new port while this install's server runs on
    install.json's port would write a port nothing serves and leave the
    running server out of reach of `mentis stop`. Refused before anything is
    written."""
    from mentis import servers
    old = st["port"]
    who = servers.identity(old, timeout=3)
    if who and ours(lay, who, st["brain"]):
        raise InstallRefused(
            f"this install's server is running on :{old} (pid {who['pid']}); "
            f"moving it to :{port} is not done under a running server. "
            "Nothing was changed. Run `mentis stop`, then re-run install "
            f"with --port {port}")


def _adoptable(brain: str):
    """The Brain's state, read first; a Brain this release cannot use is
    refused here, before its owner is read or anything is written."""
    from mentis.spine import migrations
    st = _status(brain)
    _say(f"The Brain: {st.explain(brain)}.")
    if st.state in (migrations.NEEDS_ATTENTION, migrations.NEEDS_NEWER):
        raise InstallRefused(
            "this release cannot adopt that Brain; nothing was changed. "
            f"{st.explain(brain)}")
    return st


def _adopt(brain: str, allow_breaking: bool, st) -> dict:
    """Backup, then reconcile and migrate where the Brain needs it. `st` is
    `_adoptable`'s answer."""
    from mentis.spine import backup, migrations
    progress.emit("backup", progress.RUNNING, "Backing up your Brain")
    _say("Taking a backup of it before anything changes.")
    bk = backup.backup(brain)
    check = backup.verify_backup(bk["backup"], brain=brain)
    if not check["usable"]:
        raise InstallFailed(f"the backup {bk['backup']} did not verify: "
                            + "; ".join(check["problems"]))
    _say(f"  backup {bk['id']} at {bk['backup']}: verified usable.")
    progress.emit("backup", progress.DONE, f"Backed up to {bk['backup']}")
    progress.emit("migrate", progress.RUNNING, "Bringing the Brain up to date")
    done = {"backup": bk["backup"], "reconciled": False, "migrated": []}
    if st.legacy_open:
        _say("A release older than the schema ledger opened this Brain since "
             "its last migration; recording that (`mentis brain reconcile`).")
        migrations.reconcile(brain)
        done["reconciled"] = True
        st = migrations.status_of(brain)
    if st.state in (migrations.UNADOPTED, migrations.NEEDS_MIGRATE):
        plan = migrations.plan(brain)
        _say("Migrating it: " + ", ".join(
            f"{m['id']} ({m['kind']})" for m in plan["migrations"]) + ".")
        out = migrations.apply(brain, allow_breaking=allow_breaking)
        done["migrated"] = out["applied"]
        _say(f"  now at schema version {out['to_version']}, in one "
             "transaction.")
    else:
        _say("It needs no migration.")
    progress.emit("migrate", progress.DONE,
                  f"Migrated: {', '.join(done['migrated'])}"
                  if done["migrated"] else "No migration was needed")
    return done


#: The act that gives an adopted Brain its own fork identity (O1). Its
#: reader is `mentis.exchange.identity`.
BRAIN_FORKED = "brain-forked"


def _machine_id() -> str:
    """This machine's own identity, which no copy of a Brain carries: the
    OS's machine id (Windows' MachineGuid, /etc/machine-id, macOS's
    IOPlatformUUID), else the host name and hardware address."""
    try:
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            with contextlib.suppress(OSError):
                got = pathlib.Path(p).read_text().strip()
                if got:
                    return got
        if sys.platform == "darwin":
            out = subprocess.run(["ioreg", "-rd1", "-c",
                                  "IOPlatformExpertDevice"],
                                 capture_output=True, text=True, timeout=10)
            import re
            m = re.search(r'"IOPlatformUUID" = "([^"]+)"', out.stdout)
            if m:
                return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    import socket
    return f"{socket.gethostname()}/{uuid.getnode():012x}"


def adoption_key(brain: str) -> str:
    """WHERE a Brain is adopted: this machine and the Brain's absolute path,
    hashed -- neither is copied with the Brain, and the act holds neither
    in the clear. A re-run over the same Brain finds the same key; a copy
    adopted at another path, or at the same path on another machine, does
    not (review ent-cca01f8347bb, Finding 2)."""
    import hashlib
    where = os.path.normcase(os.path.realpath(os.path.abspath(brain)))
    return hashlib.sha256(
        f"{_machine_id()}\x1e{where}".encode("utf-8")).hexdigest()


def record_fork(brain: str, install: str | None = None) -> dict:
    """The one act adoption writes, after the backup and the migration:
    `brain-forked` by the owner, with a new fork id, the heads it forked at,
    where it was adopted (`adopted_at`, `adoption_key`) and the install that
    adopted it (install.json's `id`, None before the first install.json).
    Nothing is written when the newest `brain-forked` act was written at
    this same `adopted_at` -- the same adoption, run again (an install that
    stopped before install.json, whose id it never kept, so the install is
    recorded and not compared). Anything else is a copy, however little
    was written since: it gets its own fork id.

    By the owner Participant the baseline identifies (the first row of the
    Kind about "the owner", as `wakecheck._owner` reads it); a Brain that
    records none is the direct human act, `human`."""
    from mentis.bootstrap.baseline import OWNER_ABOUT
    from mentis.spine import migrations
    from mentis.spine.store import Store
    where = adoption_key(brain)
    store = Store(brain, access="write")
    try:
        with store.write():
            conn = store._conn
            heads = migrations._heads(conn)
            last = store.operational(act=BRAIN_FORKED, newest_first=True,
                                     limit=1)
            if last:
                was = last[0].get("detail") or {}
                if was.get("adopted_at") == where:
                    _say("It already has its own fork identity "
                         f"({was.get('fork_id')}), adopted here, at this "
                         "path: no second one.")
                    return {"act": None, "fork_id": was.get("fork_id"),
                            "written": False}
            row = conn.execute(
                "SELECT id FROM entry WHERE def_name = 'participant' "
                "AND family = 'entry' AND link_relation IS NULL "
                "AND json_extract(body, '$.about') = ? ORDER BY seq LIMIT 1",
                (OWNER_ABOUT,)).fetchone()
            owner = row[0] if row else "human"
            fork_id = uuid.uuid4().hex
            act = f"opr-{uuid.uuid4().hex[:12]}"
            store.append_operational({
                "id": act, "at": time.time(), "actor": owner,
                "act": BRAIN_FORKED,
                "because": "adopted by install: this copy's own fork identity",
                "detail": {"fork_id": fork_id, "heads": heads,
                           "adopted_at": where, "install": install}})
    finally:
        store.close()
    _say(f"Recorded its own fork identity ({fork_id}), the one write "
         "adoption adds.")
    return {"act": act, "fork_id": fork_id, "written": True}


def _bootstrap(brain: str, owner: str, *, check: bool = False) -> dict:
    run = _run([sys.executable, "-I", "-m", "mentis.bootstrap", brain,
                "--owner", owner] + (["--check"] if check else []))
    if run.returncode:
        raise InstallFailed(f"bootstrap failed: {_tail(run)}")
    try:
        return json.loads(run.stdout)
    except ValueError:
        return {}


def _same_alias(a, b) -> bool:
    return str(a or "").lstrip("@").casefold() == str(b or "").lstrip("@").casefold()


def _brain_owner(brain: str) -> dict:
    """The owner aliases and the applied baseline version of an existing
    Brain, before anything is changed. Read as `migrations.status_of` reads
    (which has run first): a plain SQLite connection of its own, query-only,
    so no file is made -- not even the `.mentis.lock` opening the corpus
    would add (adm-60de2c0f3021 F1) -- and nothing opens Conversations,
    which may write vocabulary. The same rows `entries_of_kind` and
    `operational(act=, detail_is=)` give."""
    import sqlite3
    from mentis.bootstrap import baseline
    conn = sqlite3.connect(os.path.join(brain, "corpus.db"))
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT body FROM entry WHERE def_name = 'participant' "
            "AND family = 'entry' AND link_relation IS NULL "
            "ORDER BY seq").fetchall()
        acts = conn.execute(
            "SELECT detail FROM operational WHERE act = ? "
            "AND json_extract(detail, '$.step') = ?",
            (baseline.APPLIED, baseline.STEP)).fetchall()
    except sqlite3.DatabaseError as exc:
        raise InstallRefused(f"the Brain at {brain} cannot be read ({exc}); "
                             "nothing was changed") from None
    finally:
        conn.close()
    owners = []
    for (body,) in rows:
        b = json.loads(body)
        if isinstance(b, dict) and b.get("about") == baseline.OWNER_ABOUT \
                and b.get("alias"):
            owners.append(b["alias"])
    versions = []
    for (detail,) in acts:
        d = json.loads(detail)
        if isinstance(d, dict) and isinstance(d.get("version"), int):
            versions.append(d["version"])
    return {"owners": owners, "baseline": max(versions, default=None)}


def _adopted_owner(brain: str, asked) -> dict:
    """Who owns a Brain about to be adopted. An existing Brain's owner is the
    one it records; `--owner` naming anyone else is refused before anything
    is changed, and so is `--owner` for a Brain that records no owner:
    bootstrap cannot add an owner without writing a baseline, which install
    never writes into an existing Brain (adm-60de2c0f3021 F2)."""
    found = _brain_owner(brain)
    owners = found["owners"]
    if asked and not owners:
        raise InstallRefused(
            f"this Brain records no owner; --owner {asked} was not applied, "
            f"and nothing was changed. Install never writes an owner into an "
            f"existing Brain: leave --owner out to adopt {brain} as it is; "
            "its owner can add one afterwards with `python -m "
            f"mentis.bootstrap \"{brain}\" --owner {asked} --check`, then "
            "the same without --check")
    if asked and not any(_same_alias(asked, o) for o in owners):
        raise InstallRefused(
            f"{brain} is owned by {', '.join(owners)}, not {asked}; nothing "
            "was changed. Give that owner's --owner, or leave --owner out")
    found["owner"] = next((o for o in owners if _same_alias(asked, o)),
                          owners[0] if owners else None)
    return found


def _settle_adopted_baseline(brain: str, found: dict, asked) -> dict:
    """An adopted Brain is the owner's: install writes it nothing beyond what
    adoption required. A baseline it already carries is VALIDATED (bootstrap
    `--check`, which writes nothing), and a newer one is left to the owner to
    propose; a Brain with none is not given one by guessing."""
    owner = found["owner"]
    if found["baseline"] is None:
        if owner:
            _say("It has no Brain baseline; install does not write one into "
                 "an existing Brain. To add it, its owner runs `python -m "
                 f"mentis.bootstrap \"{brain}\" --owner {owner} --check`, "
                 "then the same without --check.")
        else:
            _say("It records no owner and has no Brain baseline; install "
                 "writes neither into an existing Brain. To add them, the "
                 "person it belongs to runs `python -m mentis.bootstrap "
                 f"\"{brain}\" --owner @alias --check`, then the same without "
                 "--check.")
        return {"bootstrap": "skipped"}
    report = _bootstrap(brain, owner, check=True).get("baseline") or {}
    action = report.get("action")
    if action == "unchanged":
        _say(f"Its baseline (version {report.get('applied_version')}) is "
             f"in place and resolves, for owner {owner}: unchanged.")
    else:
        _say(f"Its baseline (version {found['baseline']}) resolves; this "
             f"release ships version {report.get('version')}, which its owner "
             f"proposes with `python -m mentis.bootstrap \"{brain}\" --owner "
             f"{owner}`. Install leaves it as it is.")
    return {"bootstrap": action}


def setup(a) -> tuple[int, dict]:
    from mentis import health
    lay = home.Layout()
    st = install_state.load(lay, required=False)
    name = a.release
    rel = lay.release(name)
    facts = home.release(rel)
    if facts is None:
        raise InstallFailed(f"{rel} is not a release")
    progress.emit("brain", progress.RUNNING, "Reading the Brain")
    if a.repair and st is None:
        raise InstallRefused(f"nothing is installed at {lay.root}, so there "
                             "is nothing to repair", "not_installed")
    brain, how = _brain_choice(lay, a, st)
    port = a.port or (st or {}).get("port")
    if not st and port == DEFAULT_PORT:
        raise InstallRefused(
            f"port {DEFAULT_PORT} is the port the Mentis from before this "
            "installer serves on; a new install never takes it. Give another "
            "--port, or none", "port")
    if not port:
        port = choose_port()
        _say(f"This install uses :{port}.")
    if st and port != st["port"]:
        _refuse_moving_a_running_server(lay, st, port)
    owner = a.owner or (st or {}).get("owner_alias")
    done: dict = {"brain": brain, "how": how}
    if how == "new":
        if not owner:
            raise InstallRefused("a new Brain needs its owner: give "
                                 "--owner @alias", "owner")
        _say(f"Creating a new Brain at {brain} for {owner}.")
        _bootstrap(brain, owner)
    elif how == "adopt":
        _say(f"Adopting the existing Brain at {brain}.")
        # read in this order, and nothing written until all three pass:
        # the Brain's state (status_of), then its owner and baseline
        status = _adoptable(brain)
        found = _adopted_owner(brain, owner)
        done.update(_adopt(brain, a.allow_breaking, status))
        done["fork"] = record_fork(brain, (st or {}).get("id"))
        done.update(_settle_adopted_baseline(brain, found, owner))
        owner = found["owner"]
    elif a.repair:
        _say(f"Repairing: the Brain {brain} is left exactly as it is.")
    else:
        _say(f"Using the Brain this install already serves: {brain}.")
    progress.emit("brain", progress.DONE, f"The Brain: {brain}")
    progress.emit("check", progress.RUNNING, "Checking the Brain")
    _say("Checking the Brain before it is served.")
    # a repair writes nothing to the Brain, not even a derived index
    pre = health.check(port, rel, brain, server=False, repair=not a.repair)
    _say(health.render(pre))
    if not pre["ok"]:
        raise InstallFailed("the Brain is not healthy; install.json was not "
                            "written. See the rows above", "brain_unhealthy")
    progress.emit("check", progress.DONE, "The Brain is whole")
    progress.emit("save", progress.RUNNING, "Recording the install")
    keep = {k: v for k, v in (st or {}).items()
            if k not in install_state.FIELDS}
    # I3: which install this is, made once and kept by every re-run, repair
    # and update; the server reports it with its home
    keep["id"] = keep.get("id") or str(uuid.uuid4())
    previous = (st or {}).get("previous")
    if st and st["current"] != name:
        previous = st["current"]          # a repair from another commit
    state = install_state.save({**keep, "current": name,
                                "previous": previous,
                                "brain": brain, "port": port,
                                "owner_alias": owner}, lay)
    launcher = write_launcher(lay, name)
    _say(f"Wrote {lay.install_json} and the launcher {launcher}.")
    progress.emit("save", progress.DONE, f"Recorded in {lay.install_json}")
    result = {"installed": name, "root": str(lay.root), "state": state,
              "id": state["id"], "port": port, "repair": bool(a.repair),
              "launcher": str(launcher), **done, "started": None,
              "health": None}
    code = 0
    if not a.no_start:
        from mentis import servers
        progress.emit("start", progress.RUNNING, "Starting Mentis")
        who = servers.identity(port, timeout=3)
        if who and ours(lay, who, brain) and _inside(who["code"], rel):
            _say(f"Release {name} is already serving on :{port}.")
        else:
            if who and ours(lay, who, brain):
                stop_ours(lay, port=port, brain=brain,
                          free_wait_s=OPEN_WAIT_S)
            _say(f"Starting Mentis on http://127.0.0.1:{port} ...")
            who = start_server(lay, name, brain=brain, port=port)
        result["started"] = who
        progress.emit("start", progress.DONE,
                      f"Mentis is running on http://127.0.0.1:{port}")
        progress.emit("health", progress.RUNNING, "Checking Mentis's health")
        h = health.check(port, rel, brain)
        result["health"] = h
        _say("Health check:")
        _say(health.render(h))
        if h["ok"]:
            message = (f"Mentis {facts['version']} is installed and healthy "
                       f"at http://127.0.0.1:{port}.")
            _say(message)
            progress.emit("health", progress.DONE, "Mentis is healthy")
            outcome, reason = progress.OK, "healthy"
        else:
            stop_ours(lay, port=port, brain=brain)
            message = ("Mentis is installed, but its server was not healthy "
                       "and has been stopped. install.json, the release and "
                       "the Brain are kept.")
            _say(message)
            progress.emit("health", progress.FAILED,
                          "Mentis is installed but not healthy; it was "
                          "stopped")
            outcome, reason, code = progress.UNHEALTHY, "unhealthy", 1
    else:
        message = f"Mentis {facts['version']} is installed (not started)."
        _say(message)
        outcome, reason = progress.OK, "not_started"
    if a.repair and code == 0:
        message = f"Repaired. {message}"
        reason = "repaired"
    return code, progress.outcome_doc(outcome, reason, message, **result)


# -- uninstall: removing the program files -----------------------------------------

#: what `remove-program-files` removes, inside the home; nothing else
PROGRAM_FILES = ("releases", "bin", "state")


def _listening(port) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1):
            return True
    except (OSError, TypeError, ValueError):
        return False


def _rmtree_writable(path: pathlib.Path) -> None:
    import stat

    def again(func, p, *_):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=again)
    else:
        shutil.rmtree(path, onerror=again)


#: what install and update write in `bin/` and `state/`, by name; a
#: temporary file of an atomic write starts with one of these (after an
#: optional ".") and ends ".tmp"
_MADE = {"bin": ("mentis-launch.py", "mentis.cmd", "mentis"),
         "state": ("install.json", "update.lock", "update.journal.json",
                   "needs-attention.json")}
#: a Brain or a backup: anything under a target holding one is refused
_PRECIOUS = ("corpus.db", "BACKUP.json")


def _is_link(p: pathlib.Path) -> bool:
    """A symbolic link or a Windows junction (which `is_symlink` misses)."""
    try:
        return p.is_symlink() or bool(
            getattr(os.path, "isjunction", lambda _p: False)(p))
    except OSError:
        return False


def _made_here(where: str, name: str) -> bool:
    for made in _MADE[where]:
        if name == made or (name.endswith(".tmp")
                            and name.lstrip(".").startswith(made + ".")):
            return True
    return False


def _release_made(rel: pathlib.Path, st: dict) -> bool:
    """Whether install made this folder in releases/: a release whose own
    RELEASE.json names it (version and commit), the `.partial` of one (only
    ever a staging's), or a damaged release `install --repair` set aside
    and recorded in install.json's `set_aside`."""
    name = rel.name
    if name.endswith(PARTIAL):
        return home.is_release_name(name[:-len(PARTIAL)])
    if DAMAGED in name:
        return (home.is_release_name(name.split(DAMAGED)[0])
                and name in (st.get("set_aside") or []))
    if not home.is_release_name(name):
        return False
    try:
        doc = json.loads((rel / home.RELEASE_FILE).read_text("utf-8"))
        return f"{doc['version']}+{doc['commit'][:12]}" == name
    except (OSError, ValueError, KeyError, TypeError):
        return False


def remove_program_files(lay: home.Layout) -> dict:
    """The uninstaller's optional "also remove Mentis program files" (D11):
    in the home's `releases/`, `bin/` and `state/`, exactly what install
    state and RELEASE.json say install made -- each release whose
    RELEASE.json names it (unlocked first), its `.partial`, a damaged release
    set aside by a repair that install.json records, the launcher files in
    `bin/` and install's own files in `state/` -- and then each of the three
    folders if nothing else is left in it. Anything else is left where it is
    and listed (`left`). Never `brains/`, `backups/` or the logs.

    REFUSED, with nothing removed (InstallRefused): an install.json that is
    unreadable or not a well-formed one (an absolute Brain path among its
    fields); an unfinished update or a waiting decision; anything listening
    on its port; the Brain it names inside a target; any `corpus.db` or
    `BACKUP.json` (a Brain or a backup) anywhere under a target; and any
    link or junction at or under a target -- never followed, and never
    reported removed when it is not. Without install.json nothing is
    removed: the home is not this installer's (S6).

    Standard library only: the uninstaller runs it with the bootstrap Python
    and the payload zip, since the release's own Python is among what goes.
    """
    from mentis import readonly
    root = lay.root
    out = {"root": str(root), "installed": False, "removed": [],
           "removed_items": [], "left": [],
           "kept": ["brains", "backups", "install-logs"]}
    if not root.is_absolute():
        raise InstallRefused(f"the home {root} is not an absolute path; "
                             "nothing was removed", "home_invalid")
    try:
        st = install_state.load(lay, required=False)
    except install_state.InstallStateError as exc:
        raise InstallRefused(f"{exc}; it is not a well-formed install.json, "
                             "so nothing was removed", "install_state_invalid"
                             ) from None
    out["installed"] = st is not None
    if st is None:
        # Not a home this installer made (S6: an older Mentis keeps its own
        # releases/ here with no install.json): none of it is ours to remove.
        return out
    for f in (lay.journal, lay.needs_attention):
        if f.exists():
            raise InstallRefused(f"{f} is there: an update is unfinished or "
                                 "waiting for a decision. Nothing was removed",
                                 "update_pending")
    if _listening(st["port"]):
        raise InstallRefused(f"something is listening on :{st['port']}; stop "
                             "Mentis first. Nothing was removed", "running")
    targets = [lay.root / n for n in PROGRAM_FILES]
    b = pathlib.Path(st["brain"])
    for t in targets:
        if _same_path(b, t) or _inside(b, t):
            raise InstallRefused(f"the Brain {b} is inside {t}; nothing "
                                 "was removed", "brain_inside", brain=str(b))
    out["brain"] = str(b)
    # everything is looked at before anything is removed
    for t in targets:
        if _is_link(t):
            raise InstallRefused(f"{t} is a link or junction; it is not "
                                 "followed and nothing was removed", "link",
                                 path=str(t))
        if not t.exists():
            continue
        for here, dirs, names in os.walk(t, followlinks=False):
            for d in list(dirs):
                if _is_link(pathlib.Path(here) / d):
                    raise InstallRefused(
                        f"{pathlib.Path(here) / d} is a link or junction; it "
                        "is not followed and nothing was removed", "link",
                        path=str(pathlib.Path(here) / d))
            for n in names:
                p = pathlib.Path(here) / n
                if _is_link(p):
                    raise InstallRefused(f"{p} is a link; nothing was removed",
                                         "link", path=str(p))
                if n in _PRECIOUS:
                    raise InstallRefused(
                        f"{p} is there: a Brain or a backup under {t.name}/. "
                        "Nothing was removed; move it out first",
                        "brain_inside", path=str(p))
    for t in targets:
        if not t.is_dir():
            continue
        for item in sorted(t.iterdir()):
            rel = item.relative_to(root).as_posix()
            ours = (_release_made(item, st) if t.name == "releases"
                    else item.is_file() and _made_here(t.name, item.name))
            if not ours:
                out["left"].append(rel)
                continue
            if item.is_dir():
                try:
                    readonly.unlock(item)
                except Exception:                             # noqa: BLE001
                    pass
                _rmtree_writable(item)
            else:
                os.chmod(item, 0o600)
                item.unlink()
            out["removed_items"].append(rel)
        if not any(t.iterdir()):
            t.rmdir()
            out["removed"].append(t.name)
    return out


# -- the command -------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python3.12 <package.zip>",
        description="Install Mentis from this package.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("install", help="install, or re-run an install safely")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--brain", help="adopt the existing Brain at this path")
    g.add_argument("--new-brain", action="store_true",
                   help="create a new Brain at <root>/brains/default")
    p.add_argument("--owner", help="the owner's @alias (needed for a new "
                                   "Brain)")
    p.add_argument("--port", type=int, help=f"default {DEFAULT_PORT}")
    p.add_argument("--wheels", help="install dependencies offline from this "
                                    "wheel bundle")
    p.add_argument("--no-start", action="store_true")
    p.add_argument("--allow-breaking", action="store_true",
                   help="let adoption run a migration that raises min_reader")
    p.add_argument("--repair", action="store_true",
                   help="stage this install's release again from this "
                        "package, even over a damaged copy; never touches "
                        "the Brain")
    p.add_argument("--json", action="store_true",
                   help="also print the result as JSON")
    p.add_argument("--progress", choices=progress.MODES,
                   help="one JSON line per step on stdout; words on stderr")
    p.add_argument("--package", help=argparse.SUPPRESS)
    sub.add_parser("version", help="what this package is")
    u = sub.add_parser("update", help="update this install to this "
                       "package's release, without running the current "
                       "release's code (it may be damaged)")
    u.add_argument("--resume", action="store_true",
                   help="finish or undo an unfinished update")
    u.add_argument("--yes", action="store_true")
    u.add_argument("--wheels", help="for a package without its own Python")
    u.add_argument("--json", action="store_true")
    u.add_argument("--progress", choices=progress.MODES)
    u.add_argument("--package", help=argparse.SUPPRESS)
    r = sub.add_parser("remove-program-files",
                       help="remove what install made in releases/, bin/ "
                            "and state/ (never a Brain or a backup); for the "
                            "uninstaller")
    r.add_argument("--json", action="store_true")
    s = sub.add_parser("_setup")          # run by the release's own Python
    s.add_argument("--release", required=True)
    s.add_argument("--python", help=argparse.SUPPRESS)   # no longer used
    s.add_argument("--progress", choices=progress.MODES)
    s.add_argument("--brain")
    s.add_argument("--new-brain", action="store_true")
    s.add_argument("--owner")
    s.add_argument("--port", type=int)
    s.add_argument("--no-start", action="store_true")
    s.add_argument("--allow-breaking", action="store_true")
    s.add_argument("--repair", action="store_true")
    s.add_argument("--json", action="store_true")
    #: where the result goes for the part-one process to print (I2: the
    #: final JSON is printed once, by the process the caller started)
    s.add_argument("--result-file")
    return ap


def _refused_kinds() -> tuple:
    """The Brain's own refusals, which install reports as refusals (exit 2)."""
    try:
        from mentis.spine import backup, brainlock, migrations
        return (migrations.MigrationRefused, migrations.BrainMissing,
                brainlock.BrainBusy, backup.BackupRefused)
    except ImportError:
        return ()


def _outcome_of(exc: BaseException) -> dict:
    """An exception as the result I2 asks for."""
    if isinstance(exc, InstallRefused):
        return progress.outcome_doc(progress.REFUSED, exc.reason, str(exc),
                                    **exc.extra)
    if isinstance(exc, InstallFailed):
        return progress.outcome_doc(progress.FAILED_OUTCOME, exc.reason,
                                    str(exc), **exc.extra)
    if isinstance(exc, install_state.InstallStateError):
        return progress.outcome_doc(progress.FAILED_OUTCOME,
                                    "install_state_invalid", str(exc))
    kinds = _refused_kinds()
    if kinds and isinstance(exc, kinds):
        return progress.outcome_doc(progress.REFUSED,
                                    type(exc).__name__.lower(), str(exc))
    return progress.outcome_doc(progress.FAILED_OUTCOME, "unexpected",
                                f"{type(exc).__name__}: {exc}")


def _emit(a, doc: dict) -> None:
    """The final result: into `--result-file` for the process that started
    this one, else printed with `--json`."""
    target = getattr(a, "result_file", None)
    if target:
        pathlib.Path(target).write_text(
            json.dumps(doc, default=str, ensure_ascii=True), "utf-8")
    elif getattr(a, "json", False):
        progress.result(doc)


def main(argv=None) -> int:
    a = _parser().parse_args(argv)
    progress.configure(getattr(a, "progress", None))
    try:
        if a.cmd == "version":
            pkg = _package_path()
            facts = package_facts(pkg) if pkg else home.release()
            print(json.dumps(facts and {k: facts[k] for k in (
                "version", "commit") if k in facts}))
            return 0
        if a.cmd == "install":
            code, doc = install(a)
        elif a.cmd == "update":
            code, doc = update(a)
            if doc is None:
                return code          # the updater printed its own result
        elif a.cmd == "remove-program-files":
            out = remove_program_files(home.Layout())
            doc = progress.outcome_doc(
                progress.OK, "removed" if out["removed_items"] else "nothing",
                "Removed: " + (", ".join(out["removed_items"]) or "nothing")
                + (f". Left in place: {', '.join(out['left'])}"
                   if out["left"] else ""), **out)
            code = 0
            if not a.json:
                print(doc["message"])
        else:
            code, doc = setup(a)
    except Exception as exc:                                  # noqa: BLE001
        doc = _outcome_of(exc)
        code = progress.EXIT[doc["outcome"]]
        word = "refused" if code == 2 else "failed"
        what = "install" if a.cmd in ("install", "_setup") else a.cmd
        progress.fail(f"{word.capitalize()}: {doc['message']}", what)
        print(f"{what} {word}: {doc['message']}", file=sys.stderr)
        if doc["reason"] == "unexpected":
            import traceback
            traceback.print_exc(file=sys.stderr)
    _emit(a, doc)
    return code


if __name__ == "__main__":
    progress.utf8_streams()
    raise SystemExit(main())
