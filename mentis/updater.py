"""`mentis update`: move an installed Mentis to another release, safely.

    mentis update <package.zip | --from-repo PATH@COMMIT> [--version V]
                  [--wheels BUNDLE] [--yes] [--progress jsonl]
    mentis update --resume [--progress jsonl]
    mentis rollback [--yes] [--progress jsonl]

`--progress jsonl` (`mentis.progress`): one JSON line per step on stdout --
the step is the journal state in lower case ("verified" ... "healthy"),
`running` when it starts and `done` or `failed` when it ends -- then
{"step": "update", "state": "done" | "failed", "message": <outcome>}; the
words go to stderr. Without `--yes` the confirmation is still asked, on
stdin; a program passes `--yes`.

THE TRANSACTION (Stage 1 brief, "Update transaction"). Each state is written
to `<root>/state/update.journal.json` (atomic replace + fsync) once it is
reached:

  APPROVED   the plan was shown and confirmed (or --yes)
  VERIFIED   package hashes, the RELEASE.json contract, this Python
  STAGED     releases/<name>/ made, its own .venv, self-tested, read-only
             locked. The Brain is untouched.
  STOPPED    running work drained through /api/working, the server stopped
             (graceful, hard fallback), the Brain's open lock confirmed free
  BACKED_UP  `mentis brain backup`, then verify-backup says usable
  MIGRATED   `mentis migrate --apply` run by the NEW release: one
             transaction. COMMIT POINT C1.
  SWITCHED   install.json current=new, previous=old. COMMIT POINT C2.
  HEALTHY    `mentis brain verify` ok (rebuild-derived first when it lists
             missing indexes), the new server started, `mentis.health.check`
             ok: /api/server names the new release and the right Brain,
             /api/integrity intact, the core APIs answer 200
  COMMITTED  done; the journal is archived under install-logs/updates/ and removed

RECOVERY IS DERIVED FROM FACTS. The journal says what was intended; what
happened is read from the Brain's open lock, the Brain's ledger
(`brain_facts`), install.json and the server answering on the port:

  - the Brain's open lock held by something that is not a server answering
    for it (a `mentis migrate` the interrupted updater started may still be
    running from the new release): wait as `stop_brain` does, then refuse
    ("a migration or another opener is still running; try again"). Nothing
    is decided or discarded until it lets go.
  - after C1 and install.json not switched, whatever state the journal
    records: back to MIGRATED, so the switch (C2) is redone. A release is
    switched to only once it verifies whole.
  - before C1 (the Brain is not at the new schema): the update did not
    happen. The staged release is discarded if this update made it (the
    journal says so before anything is made), or if it is not in
    install.json and was never locked (a staging that did not finish); the
    old server is restarted if it was running. ABORTED.
  - after C1, before C2: the owner approved this update; continue forward.
  - after C2 and unhealthy, and the old release can read the Brain
    (version == old target, or min_reader <= old target): switch back to the
    install.json the update started from, start the old release, check its
    health. ROLLED_BACK; no record is lost.
  - after C2 and unhealthy, and the old release cannot read the Brain: stop
    the new server and stop at NEEDS_ATTENTION (`state/needs-attention.json`)
    with the Brain, the backup and both releases kept, and the restore-plan
    command printed. NEVER a restore.
  - a switch-back that fails: NEEDS_ATTENTION.

A pre-C1 interruption is treated as the brief treats a pre-C1 failure: the
update is undone, never pushed forward, because nothing the owner relies on
has changed yet; run the update again.

`plan(root, package)` says what an update would do and writes nothing. The
CLI prints it and asks for confirmation; a UI button can call the same
`plan` and then `update(..., yes=True)`.

THE OLD RELEASE IS CHECKED BEFORE IT IS TRUSTED (D6). Switching back to it,
restarting it after an abort, and resolving a NEEDS_ATTENTION all re-hash
its files first (`installer.release_problems`): a damaged old release is not
switched back to or started -- the update stops at NEEDS_ATTENTION instead,
or, before C1, ends with the old release not running -- and it is reported
healthy only after its files verified AND its health check passed. An update
FROM a damaged release still works (D12): the new release is verified whole
before anything is switched, and the old one's running work is not asked
after (its API is not trusted) before it is stopped.

FOR A PROGRAM (I1/I2). `--json` prints one final object, whatever happened:
{"outcome", "reason", "message", "running": <the release actually serving
this install's Brain on its port, or null>, "previous_restored": <true only
when the old release's files verified and it is healthy>, "update": <the
journal's id>}.

Exit status (I1, `mentis.progress`): 0 committed (or nothing to do, or a
decision resolved), 2 refused before anything changed, 3 the update did not
happen -- aborted or switched back, `previous_restored` saying whether the
old release is verified and healthy -- or failed in any other way, an
unexpected exception included, 4 NEEDS_ATTENTION: stopped, and a decision
or a resume is needed.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

from mentis import home, progress

FORMAT = 1
APPROVED, VERIFIED, STAGED, STOPPED, BACKED_UP = (
    "APPROVED", "VERIFIED", "STAGED", "STOPPED", "BACKED_UP")
MIGRATED, SWITCHED, HEALTHY, COMMITTED = (
    "MIGRATED", "SWITCHED", "HEALTHY", "COMMITTED")
#: the forward states, in order
STATES = (APPROVED, VERIFIED, STAGED, STOPPED, BACKED_UP, MIGRATED, SWITCHED,
          HEALTHY, COMMITTED)
#: intent: a switch back to the install the update started from is under way
ROLLING_BACK = "ROLLING_BACK"
#: outcomes
ABORTED, ROLLED_BACK, NEEDS_ATTENTION = (
    "ABORTED", "ROLLED_BACK", "NEEDS_ATTENTION")

#: the exit statuses of shared interface I1 (`mentis.progress.EXIT`): an
#: update that did not happen -- aborted, or switched back -- has FAILED (3);
#: 1 is only ever "installed but not healthy", which an update never ends in
EXIT_DONE, EXIT_REFUSED, EXIT_FAILED, EXIT_ATTENTION = 0, 2, 3, 4
EXIT_NOT_UPDATED = EXIT_FAILED

#: what the last transaction in this process ended in, for the final
#: `--json` result (I2): "reason", "message", "previous_restored"
_result: dict = {}


def _ended(reason: str, message: str, previous_restored: bool = False) -> None:
    _result.update(reason=reason, message=message,
                   previous_restored=bool(previous_restored))

#: what the server's API guard asks of an owner's JSON request
#: (`mentis.web.CLIENT_HEADER`; importing mentis.web here would be heavy)
CLIENT_HEADER = "X-Mentis-Client"
#: how long a server may take to answer after it is started
START_WAIT_S = 180
#: how long running work may take to finish before the server is stopped
DRAIN_WAIT_S = 600
#: how long the Brain's open lock may stay held (by something that is not a
#: server answering for it) before stopping, or recovering, is refused
OPEN_WAIT_S = 15
#: what recovery says when something still has the Brain open
STILL_OPEN = "a migration or another opener is still running; try again"

#: TESTS ONLY: called with a label at every journal state, on both sides
#: of each commit point ("state:<S>", "before:C1", "after:C1", "before:C2",
#: "after:C2") and inside staging ("staging:renamed": the release is in
#: place, not yet self-tested or locked), so a crash test can kill the
#: process exactly there.
_hook = None


def _at(label: str) -> None:
    if _hook is not None:
        _hook(label)


class UpdateRefused(RuntimeError):
    """Refused before anything changed."""


class StepFailed(RuntimeError):
    """A step of the transaction did not succeed; recovery decides what next."""


# -- small io -----------------------------------------------------------------

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def write_json(path, doc: dict) -> None:
    """Atomic replace + fsync: a reader sees the old file or the new one."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    if os.name != "nt":                     # a directory cannot be opened on Windows
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def read_json(path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return None
    return doc if isinstance(doc, dict) else None


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _same(a, b) -> bool:
    return (os.path.normcase(os.path.realpath(str(a)))
            == os.path.normcase(os.path.realpath(str(b))))


class _Log:
    """What the update says, to the person and to `<root>/install-logs/update.log`."""

    def __init__(self, root: pathlib.Path, out=print):
        L = home.Layout(root)
        self.path = L.logs / "update.log"
        self.installed = L.install_json.is_file()
        self.out = out

    def __call__(self, msg: str) -> None:
        self.out(msg)
        if not self.installed:
            return              # nothing is ever written where nothing is installed
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(f"{_now_iso()} {msg}\n")


# -- install.json (owned by mentis.install_state) ------------------------------

def _install(root) -> dict | None:
    from mentis import install_state
    return install_state.load(root)


def _set_install(root, doc: dict) -> None:
    """install.json, then the launcher for its current release (S3): every
    switch, switch back, rollback and resume changes `current` here and
    nowhere else. A launcher that cannot be rewritten is said and is not a
    failure: it still runs, through install.json, while the release it names
    is kept, and every release a journal names is kept."""
    from mentis import install_state, installer
    install_state.save(root, doc)
    try:
        installer.write_launcher(pathlib.Path(root), doc["current"])
    except Exception as exc:                                  # noqa: BLE001
        print(f"the launcher was not rewritten for {doc['current']}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)


# -- releases -----------------------------------------------------------------

def release_name(rel: dict) -> str:
    return f"{rel['version']}+{rel['commit'][:12]}"


def read_release(target) -> dict:
    """RELEASE.json of a package zip or a release directory."""
    p = pathlib.Path(target)
    if p.is_dir():
        doc = read_json(p / home.RELEASE_FILE)
        if doc is None:
            raise UpdateRefused(f"{p} has no {home.RELEASE_FILE}")
        return doc
    try:
        with zipfile.ZipFile(p) as z:
            return json.loads(z.read(home.RELEASE_FILE))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise UpdateRefused(f"{p} is not a Mentis package: "
                            f"{type(exc).__name__}: {exc}") from None


def _semver_key(v: str) -> tuple:
    core, _, pre = v.partition("+")[0].partition("-")
    nums = tuple(int(x) for x in core.split("."))
    if not pre:
        return nums + ((1,),)
    ids = tuple((0, int(x), "") if x.isdigit() else (1, 0, x)
                for x in pre.split("."))
    return nums + ((0,) + ids,)


def _py(rel_dir) -> pathlib.Path:
    """The release's own Python: bundled `runtime/python.exe`, or its venv's
    (`install_state.venv_python`)."""
    from mentis import install_state
    return install_state.venv_python(rel_dir)


def _env(rel_dir) -> dict:
    """The environment a release's own Python runs in. It runs isolated
    (`-I`); its code is found through `installer.RELEASE_PTH` (a venv) or
    its runtime's `._pth` (bundled), never PYTHONPATH."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONHOME", "PYTHONPATH")}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_release(rel_dir, *args, timeout=600) -> subprocess.CompletedProcess:
    return subprocess.run([str(_py(rel_dir)), "-I", *map(str, args)],
                          cwd=str(rel_dir), env=_env(rel_dir),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


# -- the Brain ----------------------------------------------------------------

def brain_facts(brain) -> dict:
    """What the Brain's ledger says, read-only: version, min_reader, state,
    problems. Any reader can tell these, whatever its own target."""
    from mentis.spine import migrations
    try:
        st = migrations.status_of(str(brain))
    except migrations.BrainMissing:
        return {"exists": False, "version": None, "min_reader": None,
                "state": None, "problems": ["no Brain there"],
                "legacy_open": False}
    return {"exists": True, "version": st.version,
            "min_reader": st.min_reader, "state": st.state,
            "problems": list(st.problems), "legacy_open": st.legacy_open}


def can_read(target: int, facts: dict) -> bool:
    """Whether a release whose schema target is `target` opens this Brain:
    the open gate of `mentis.spine.migrations.inspect`."""
    v, mr = facts.get("version"), facts.get("min_reader")
    if v is None or facts.get("problems"):
        return False
    return v == target or (v > target and (mr or 0) <= target)


# -- the plan -----------------------------------------------------------------

def plan(root, package) -> dict:
    """What updating the install at `root` to `package` (a zip, or a release
    directory) would do. Writes nothing. `ok` false with `problems` when it
    would be refused."""
    root = pathlib.Path(root)
    L = home.Layout(root)
    problems: list[str] = []
    out: dict = {"root": str(root), "package": str(package),
                 "problems": problems}
    if L.journal.exists():
        problems.append("an update is unfinished; run `mentis update "
                        "--resume` first")
    if L.needs_attention.exists():
        problems.append("a previous update needs attention (see "
                        f"{L.needs_attention}); resolve that first")
    inst = _install(root)
    if not inst or not inst.get("current"):
        problems.append(f"no installed Mentis at {root} (no current release "
                        "in install.json)")
        return {**out, "ok": False}
    try:
        to = read_release(package)
        to_name = release_name(to)
    except (UpdateRefused, KeyError, TypeError) as exc:
        problems.append(str(exc) or "the package's RELEASE.json is incomplete")
        return {**out, "ok": False}
    cur_name = inst["current"]
    cur = read_json(L.release(cur_name) / home.RELEASE_FILE) or {}
    brain = inst.get("brain") or str(L.default_brain)
    facts = brain_facts(brain)
    v, mr = facts["version"], facts["min_reader"] or 0
    target = int(to.get("schema_target", 0))
    old_target = cur.get("schema_target")
    pending = (list(to.get("migrations", []))[v:target]
               if v is not None and v < target else [])
    after = {"version": max(v or 0, target) if pending else v,
             "min_reader": (max(mr, int(to.get("min_reader_after") or 0))
                            if pending else facts["min_reader"]),
             "problems": []}
    rollback = (old_target is not None and can_read(int(old_target), after))
    breaking = bool(pending) and bool(to.get("breaking"))
    try:
        major = (_semver_key(to["version"])[0]
                 > _semver_key(cur.get("version", "0.0.0"))[0])
        cmp = (_semver_key(to["version"]) > _semver_key(cur["version"])) - (
            _semver_key(to["version"]) < _semver_key(cur["version"]))
    except (KeyError, ValueError):
        major, cmp = False, 1
    direction = ("upgrade" if cmp > 0 else "downgrade" if cmp < 0
                 else "same version, other commit")
    if to_name == cur_name:
        problems.append(f"{to_name} is already the current release")
    if not facts["exists"]:
        problems.append(f"no Brain at {brain}")
    elif v is None:
        problems.append(f"the Brain at {brain} has no schema ledger yet "
                        f"({facts['state']}); adopt it with `install --brain`")
    elif facts["problems"]:
        problems.append(f"the Brain at {brain} needs attention: "
                        + "; ".join(facts["problems"]))
    elif facts["legacy_open"]:
        problems.append("a release older than the schema ledger opened the "
                        "Brain; run `mentis brain reconcile` first")
    elif not can_read(target, after):
        problems.append(f"{to_name} cannot open this Brain (schema version "
                        f"{v}, needs a reader of at least {mr}; the release "
                        f"reads up to {target})")
    return {**out, "ok": not problems,
            "brain": brain, "port": inst.get("port"),
            "from": {"release": cur_name, "version": cur.get("version"),
                     "commit": cur.get("commit"),
                     "schema_target": old_target},
            "to": {"release": to_name, "version": to.get("version"),
                   "commit": to.get("commit"), "schema_target": target,
                   "min_reader_after": to.get("min_reader_after"),
                   "breaking": bool(to.get("breaking"))},
            "direction": direction,
            "brain_before": {"version": v, "min_reader": facts["min_reader"]},
            "brain_after": {"version": after["version"],
                            "min_reader": after["min_reader"]},
            "migrations": pending,
            "breaking": breaking, "major": major,
            "rollback_possible": rollback}


def describe(p: dict) -> str:
    """The plan in plain words, as the confirmation shows it."""
    if not p.get("to"):
        return "Cannot update:\n" + "\n".join(f"  - {x}" for x in p["problems"])
    f, t = p["from"], p["to"]
    lines = [f"Update Mentis {f['version']} ({f['release']}) -> "
             f"{t['version']} ({t['release']}), {p['direction']}",
             f"Brain: {p['brain']} (schema version "
             f"{p['brain_before']['version']})"]
    if p["migrations"]:
        lines.append(f"Brain migrations: {', '.join(p['migrations'])} "
                     f"(schema {p['brain_before']['version']} -> "
                     f"{p['brain_after']['version']}); a backup is taken first")
    else:
        lines.append("Brain migrations: none")
    if p["rollback_possible"]:
        lines.append("If the new release is not healthy, Mentis switches back "
                     f"to {f['version']} automatically; no records are lost.")
    else:
        lines.append(f"After this update {f['version']} can no longer open "
                     "the Brain. If the new release is not healthy, the update "
                     "stops and asks you (NEEDS ATTENTION); nothing is "
                     "restored automatically.")
    if p["breaking"] or p["major"]:
        lines.append("This is a BREAKING update.")
    lines.append("Steps: check the package, prepare the new release, finish "
                 "running work and stop Mentis, back up the Brain, migrate it, "
                 "switch, check health.")
    if p["problems"]:
        lines.append("Cannot update:")
        lines += [f"  - {x}" for x in p["problems"]]
    return "\n".join(lines)


# -- servers ------------------------------------------------------------------

def running(brain, port) -> dict | None:
    """The Mentis server serving this Brain on `port`, if one answers."""
    from mentis import servers
    who = servers.identity(int(port), timeout=3) if port else None
    if who and who.get("corpus") and _same(who["corpus"], brain):
        return who
    return None


def _drain(port, wait_s: float, say) -> None:
    """Wait until no run this server holds is still open."""
    end = time.time() + wait_s
    said = False
    while True:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/working",
                headers={CLIENT_HEADER: "1"})
            with urllib.request.urlopen(req, timeout=10) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return          # an older release: nothing to ask
            doc = {"why_not": f"HTTP {exc.code}"}
        except Exception as exc:                          # noqa: BLE001
            doc = {"why_not": f"{type(exc).__name__}: {exc}"}
        held = [r for r in doc.get("open") or [] if r.get("held_here")]
        if not held and not doc.get("why_not"):
            return
        if time.time() >= end:
            raise StepFailed(
                f"running work did not finish within {wait_s:g}s ("
                + (f"{len(held)} run(s) still open" if held else
                   f"could not ask: {doc.get('why_not')}")
                + "); Mentis was left running")
        if not said:
            say(f"waiting for {len(held)} running piece(s) of work to finish"
                if held else "waiting to learn what is running")
            said = True
        time.sleep(2)


@contextlib.contextmanager
def _as_step():
    """The release runtime is the installer's (`stage_release`,
    `start_server`, `stop_ours`); its refusals and failures are this
    transaction's StepFailed, for recovery to decide on."""
    from mentis import installer
    try:
        yield
    except (installer.InstallRefused, installer.InstallFailed) as exc:
        raise StepFailed(str(exc)) from None


def stop_brain(brain, port, root=None) -> str | None:
    """Stop this install's server serving this Brain, if any, and confirm
    the Brain's open lock is free (`installer.stop_ours`, waiting
    OPEN_WAIT_S). Returns how it stopped (None if nothing ran). `root`
    defaults to the install root (`home.root()`)."""
    from mentis import installer
    with _as_step():
        got = installer.stop_ours(root if root is not None else home.root(),
                                  port=port, brain=str(brain),
                                  free_wait_s=OPEN_WAIT_S)
    if got["was_running"] and not got["stopped"]:
        raise StepFailed(f"the server on :{got['port']} did not stop: "
                         f"{got['why']}")
    return got["how"]


def _served(brain, port) -> bool:
    """Whether a Mentis server answers for this Brain, on `port` or on the
    port it last said it serves on."""
    from mentis.spine import brainlock
    ports = {int(port)} if port else set()
    info = brainlock.serving(str(brain)) or {}
    if info.get("port"):
        ports.add(int(info["port"]))
    return any(running(brain, p) for p in sorted(ports))


def held_by_other(brain, port) -> bool:
    """Whether the Brain's open lock is held by something that is not a
    server answering for it: a `mentis migrate` an updater started and did
    not outlive, a worker, a command."""
    from mentis.spine import brainlock
    if not os.path.isdir(str(brain)):
        return False
    return brainlock.is_open(str(brain)) and not _served(brain, port)


def _await_openers(brain, port, say, wait_s: float | None = None) -> None:
    """Recovery's first fact: the Brain's open lock. Wait, as `stop_brain`
    does, for an opener that is not a server to let go; refuse when it does
    not. Nothing is read from the ledger or discarded while one holds it: a
    migration the interrupted update started may still be running from the
    new release, and its outcome is not known until it ends."""
    end = time.time() + (OPEN_WAIT_S if wait_s is None else wait_s)
    said = False
    while held_by_other(brain, port):
        if time.time() >= end:
            raise UpdateRefused(f"the Brain at {brain} is open: {STILL_OPEN}")
        if not said:
            say("something still has the Brain open; waiting for it to finish")
            said = True
        time.sleep(0.5)


def start_release(root, name: str, brain, port, wait_s: float = START_WAIT_S
                  ) -> dict:
    """Start release `name` serving `brain` on `port`, detached, and wait
    until it answers as that release, for that Brain, owning the port
    (`installer.start_server`; at once when it already does). Its output
    goes to `<root>/install-logs/server-<name>.log`. StepFailed when the
    port is taken or it does not come up."""
    from mentis import installer
    with _as_step():
        return installer.start_server(pathlib.Path(root), name,
                                      brain=str(brain), port=int(port),
                                      wait_s=wait_s)


def _inside(path, root) -> bool:
    if not path:
        return False
    p = os.path.normcase(os.path.realpath(str(path)))
    r = os.path.normcase(os.path.realpath(str(root)))
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)


def _health(port, name: str, brain) -> tuple[bool, list]:
    from mentis import health
    # the server's side only: `brain verify` (and rebuild-derived) was run
    # before the start by the release's own code, which alone knows the
    # indexes its migrations declare (`_verify_brain`)
    r = health.check(int(port), name, str(brain), server=True, brain=False,
                     repair=False)
    return bool(r.get("ok")), list(r.get("checks") or [])


# -- staging ------------------------------------------------------------------

def _make_venv(rel_dir: pathlib.Path, wheels_dir: pathlib.Path | None) -> None:
    """The release's own .venv, with requirements.lock installed by hash
    (`installer._make_venv`). A seam: the tests make a venv without pip."""
    from mentis import installer
    with _as_step():
        installer._make_venv(pathlib.Path(rel_dir), wheels_dir)


def _self_test(rel_dir: pathlib.Path, rel: dict) -> None:
    """`installer.selftest`: the release runs as the release it says it is
    (version, commit, schema target, migrations, path)."""
    from mentis import installer
    with _as_step():
        installer.selftest(pathlib.Path(rel_dir), rel)


def _discard(path: pathlib.Path) -> None:
    from mentis import installer
    installer._discard(pathlib.Path(path))


def _intact(rel_dir) -> list:
    """Why `rel_dir` is not a complete release (empty when it is):
    `installer.release_problems`."""
    from mentis import installer
    return installer.release_problems(pathlib.Path(rel_dir))


def stage(root, package, wheels=None, say=print, creating=None
          ) -> tuple[pathlib.Path, bool]:
    """Make `releases/<name>/` from a package, through the installer's one
    staging (`installer.stage_release`: the package verified, unpacked and
    re-verified, its own .venv, self-tested before and after the rename,
    read-only locked; a wheel bundle verified against the package's lock
    first; a refused rename retried briefly). Returns (dir, made): an
    existing complete release is reused (made False), and locked if it was
    left unlocked. `creating()`, when given, is called before anything is
    made, so the caller can record that this release is its own; a release
    that fails its self-test is discarded."""
    from mentis import installer
    lay = home.Layout(root)
    with _as_step():
        got = installer.stage_release(
            lay, package, wheels=wheels, report=say,
            creating=creating, at=_at,
            # looked up when called, so a test's replacement is used
            make_venv=lambda rel, wheels_dir: _make_venv(rel, wheels_dir),
            self_test=lambda rel, facts: _self_test(rel, facts),
            # N2: never the current release (the plan refuses that), so a
            # damaged copy of it is staged again rather than refused
            replace_damaged=installer._restager(lay, _install(root)))
        installer._record_set_aside(lay, got)
    if not got["created"]:
        say(f"release {got['name']} is already in place; reusing it")
    return pathlib.Path(got["path"]), got["created"]


# -- the journal --------------------------------------------------------------

def journal(root) -> dict | None:
    return read_json(home.Layout(root).journal)


#: what each forward state's step is, in words, for `--progress jsonl`
#: (the step id is the state, lower case)
STEP_WORDS = {APPROVED: "The update is approved",
              VERIFIED: "Checking the package's files",
              STAGED: "Preparing the new release",
              STOPPED: "Finishing running work and stopping Mentis",
              BACKED_UP: "Backing up your Brain",
              MIGRATED: "Bringing the Brain up to date",
              SWITCHED: "Switching to the new release",
              HEALTHY: "Checking Mentis's health",
              COMMITTED: "The update is finished"}


def _save(root, j: dict, state: str | None = None) -> None:
    if state is not None:
        j["state"] = state
        j.setdefault("history", []).append({"state": state, "at": _now_iso()})
    j["updated_at"] = _now_iso()
    write_json(home.Layout(root).journal, j)
    if state is not None:
        if state in STEP_WORDS:
            progress.emit(state.lower(), progress.DONE, STEP_WORDS[state])
        _at(f"state:{state}")


def _finish(root, j: dict, outcome: str, say) -> None:
    """Archive the journal under install-logs/updates/ and remove it."""
    L = home.Layout(root)
    progress.emit("update", progress.DONE if outcome.startswith(
        (COMMITTED, "RESOLVED")) else progress.FAILED, outcome)
    j["outcome"] = outcome
    j.setdefault("history", []).append({"state": outcome, "at": _now_iso()})
    write_json(L.logs / "updates" / f"{j['id']}.json", j)
    with contextlib.suppress(FileNotFoundError):
        os.remove(L.journal)
    if outcome != NEEDS_ATTENTION:
        with contextlib.suppress(FileNotFoundError):
            os.remove(L.needs_attention)


def _attention(root, j: dict, why: str, say) -> int:
    L = home.Layout(root)
    brain = j["brain"]
    backup = j.get("backup")
    cmd = (f'mentis brain restore-plan "{brain}" "{backup}"' if backup
           else None)
    doc = {"format": FORMAT, "at": _now_iso(), "update": j["id"], "why": why,
           "brain": brain, "backup": backup,
           "releases": {"from": j["from"]["release"], "to": j["to"]["release"]},
           "install": _install(root),
           "nothing_deleted": True,
           "what_to_do": [
               "Nothing was restored and nothing was deleted: the Brain, "
               "the backup taken before the update and both releases are "
               "all still here.",
               "Look at the server log under " + str(L.logs) + ".",
               ("To see what restoring the backup would do (it changes "
                "nothing): " + cmd) if cmd else "No backup was taken.",
               "After acting, run `mentis update --resume` to check again."],
           "restore_plan_command": cmd}
    write_json(L.needs_attention, doc)
    j["needs_attention"] = why
    _save(root, j, NEEDS_ATTENTION)
    say(f"NEEDS ATTENTION: {why}")
    for line in doc["what_to_do"]:
        say("  " + line)
    _ended("needs_attention", f"The update stopped and needs a decision: "
           f"{why}")
    return EXIT_ATTENTION


# -- the steps ----------------------------------------------------------------

def _step_verified(root, j, say) -> None:
    from mentis.release import build
    target = j["package"]
    got = build.verify(target)
    if not got["ok"]:
        raise StepFailed(f"the package did not verify: {got['problems'][:5]}")
    # a rollback goes to a release already in place; an update installs a
    # package (a wheel bundle, or a bare folder, is neither)
    want = "release-dir" if j.get("kind") == "rollback" else "package"
    if got.get("kind") != want:
        raise StepFailed(f"{target} is a {got.get('kind')}, not a {want}")
    if sys.version_info[:2] != (3, 12):
        raise StepFailed(f"Mentis needs Python 3.12; this is "
                         f"{sys.version.split()[0]}")
    rel = read_release(target)
    if release_name(rel) != j["to"]["release"]:
        raise StepFailed("the package changed since the update was approved")
    if j.get("wheels"):
        b = build.verify(j["wheels"])
        if not b["ok"] or b.get("kind") != "wheel-bundle":
            raise StepFailed(f"the wheel bundle did not verify "
                             f"({b.get('kind')}): "
                             f"{b.get('problems', [])[:5]}")
        with zipfile.ZipFile(j["wheels"]) as z:
            man = json.loads(z.read("WHEELS.json"))
        if pathlib.Path(target).is_dir():
            lock = (pathlib.Path(target) / "requirements.lock").read_bytes()
        else:
            with zipfile.ZipFile(target) as z:
                lock = z.read("requirements.lock")
        if man.get("requirements_lock_sha256") != hashlib.sha256(
                lock).hexdigest():
            raise StepFailed("the wheel bundle was made for another "
                             "requirements.lock")
    say(f"package verified: {got['files']} files match their hashes")


def _step_staged(root, j, say) -> None:
    L = home.Layout(root)
    target = pathlib.Path(j["package"])
    if target.is_dir() and _same(target, L.release(j["to"]["release"])):
        rel = read_release(target)
        if not _py(target).exists():
            raise StepFailed(f"{target} has no Python at {_py(target)}")
        _self_test(target, rel)
        from mentis import readonly
        if not readonly.is_locked(target):
            say(f"release {target.name} was not read-only; locking it")
            readonly.lock(target)
        made = False
    else:
        def creating():
            # recorded before anything is made, so a crash at any point of
            # staging leaves a journal that says the release is this
            # update's to discard
            j["created_release"] = True
            _save(root, j)
        _, made = stage(root, target, j.get("wheels"), say, creating)
    # staged just before the transaction by the package's own installer, it
    # stays this update's own though staging here only reused it
    j["created_release"] = made or bool(j.get("created_release"))
    say(f"release {j['to']['release']} is ready")


def _old_damage(root, j) -> list:
    """Why the release the update started from is not whole (empty when it
    is)."""
    try:
        return _intact(home.Layout(root).release(j["from"]["release"]))
    except Exception as exc:                                  # noqa: BLE001
        return [f"{type(exc).__name__}: {exc}"]


def _step_stopped(root, j, say) -> None:
    brain, port = j["brain"], j["port"]
    who = running(brain, port)
    if who and _old_damage(root, j):
        # D12: its files are damaged, so what its API says about running
        # work is not waited on; the new release is verified, and the
        # Brain's own open lock is still confirmed free before anything
        say("the release Mentis runs now is damaged; stopping it without "
            "asking it about running work")
    elif who:
        say("finishing running work before stopping Mentis")
        _drain(port, j.get("drain_wait_s", DRAIN_WAIT_S), say)
    how = stop_brain(brain, port, root)
    say(f"Mentis stopped ({how})" if how else "Mentis was not running")


def _step_backed_up(root, j, say) -> None:
    from mentis.spine import backup
    got = backup.backup(j["brain"])
    check = backup.verify_backup(got["backup"], brain=j["brain"])
    if not check["usable"]:
        raise StepFailed(f"the backup is not usable: {check['problems'][:5]}")
    j["backup"] = got["backup"]
    say(f"Brain backed up to {got['backup']} (checked usable)")


def _step_migrated(root, j, say) -> None:
    rel = home.Layout(root).release(j["to"]["release"])
    _at("before:C1")
    if j["migrations"]:
        args = ["-m", "mentis.migrate", j["brain"], "--apply"]
        if j.get("allow_breaking"):
            args.append("--allow-breaking")
        got = _run_release(rel, *args, timeout=3600)
        if got.returncode != 0:
            raise StepFailed("the migration did not apply and was rolled "
                             "back: " + (got.stderr or got.stdout)[-2000:])
    _at("after:C1")
    facts = brain_facts(j["brain"])
    if j["migrations"] and facts["version"] != j["to"]["schema_target"]:
        raise StepFailed(f"after migrating, the Brain is at version "
                         f"{facts['version']}, not "
                         f"{j['to']['schema_target']}")
    say(f"Brain migrated: {', '.join(j['migrations'])}" if j["migrations"]
        else "no Brain migration needed")


def _step_switched(root, j, say) -> None:
    # never switch to a release that is not whole: on a resume, staging
    # happened in another process, and something may have changed it since
    why = _intact(home.Layout(root).release(j["to"]["release"]))
    if why:
        raise StepFailed(f"{j['to']['release']} is not a complete release, so "
                         f"it was not switched to: {why}")
    inst = dict(_install(root) or j["install_before"])
    inst["current"] = j["to"]["release"]
    inst["previous"] = j["from"]["release"]
    # I3: an install made before ids (1.0.0-rc.1) gains one here, so the
    # new server can name its install; a switch back restores the old file
    inst["id"] = inst.get("id") or str(uuid.uuid4())
    _at("before:C2")
    _set_install(root, inst)
    _at("after:C2")
    say(f"switched to {j['to']['release']}")


def _verify_brain(root, j, name: str, say) -> None:
    """`mentis brain verify` by release `name`; rebuild-derived when the only
    problem is missing derived indexes. The server must be stopped."""
    rel = home.Layout(root).release(name)
    got = _run_release(rel, "-m", "mentis.brain", "verify", j["brain"])
    try:
        out = json.loads(got.stdout)
    except ValueError:
        raise StepFailed(f"brain verify did not answer: {got.stderr[-1000:]}")
    if not out["ok"] and out.get("missing_indexes") and len(
            out["problems"]) == 1:
        say("rebuilding missing derived indexes: "
            + ", ".join(out["missing_indexes"]))
        r = _run_release(rel, "-m", "mentis.brain", "rebuild-derived",
                         j["brain"])
        if r.returncode != 0:
            raise StepFailed(f"rebuild-derived failed: {r.stderr[-1000:]}")
        out = json.loads(_run_release(rel, "-m", "mentis.brain", "verify",
                                      j["brain"]).stdout)
    if not out["ok"]:
        raise StepFailed("brain verify: " + "; ".join(out["problems"]))


def _step_healthy(root, j, say) -> None:
    name, brain, port = j["to"]["release"], j["brain"], j["port"]
    who = running(brain, port)
    if who is None or not _inside(who.get("code"),
                                  home.Layout(root).release(name)):
        stop_brain(brain, port, root)
        _verify_brain(root, j, name, say)
        say(f"starting {name}")
        start_release(root, name, brain, port)
    ok, checks = _health(port, name, brain)
    j["health"] = checks
    if not ok:
        bad = [c for c in checks if not c.get("ok")]
        raise StepFailed("the new release is not healthy: "
                         + json.dumps(bad, default=str)[:1500])
    say(f"{name} is healthy")


_STEPS = {VERIFIED: _step_verified, STAGED: _step_staged,
          STOPPED: _step_stopped, BACKED_UP: _step_backed_up,
          MIGRATED: _step_migrated, SWITCHED: _step_switched,
          HEALTHY: _step_healthy}


def _drive(root, j: dict, say) -> int:
    """Run every step after the journal's state; on failure, recover."""
    while True:
        i = STATES.index(j["state"])
        nxt = STATES[i + 1]
        if nxt == COMMITTED:
            _save(root, j, COMMITTED)
            _finish(root, j, COMMITTED, say)
            msg = f"update committed: Mentis is now {j['to']['release']}"
            say(msg)
            _ended("committed", msg)
            return EXIT_DONE
        progress.emit(nxt.lower(), progress.RUNNING, STEP_WORDS[nxt])
        try:
            _STEPS[nxt](root, j, say)
        except Exception as exc:                          # noqa: BLE001
            # whatever a step raised, recovery decides from the facts; only
            # a crash (or ^C) leaves the journal for `--resume`
            say(f"step {nxt} failed: {type(exc).__name__}: {exc}")
            progress.emit(nxt.lower(), progress.FAILED,
                          f"{type(exc).__name__}: {exc}")
            return _recover_failure(root, j, str(exc), say)
        _save(root, j, nxt)


# -- recovery -----------------------------------------------------------------

def _migrated(j: dict, facts: dict) -> bool:
    """Whether C1 has happened, from the Brain's ledger (or, when the update
    has no migration, from the journal: there is no fact to read)."""
    if j["migrations"]:
        return facts.get("version") == j["to"]["schema_target"]
    return STATES.index(j["state"]) >= STATES.index(MIGRATED) \
        if j["state"] in STATES else True


def _switched(root, j) -> bool:
    inst = _install(root) or {}
    return inst.get("current") == j["to"]["release"]


def _abort(root, j: dict, why: str, say) -> int:
    """Before C1: the Brain is as it was. Discard what this update staged,
    restart the old release if it was running."""
    from mentis import readonly
    L = home.Layout(root)
    name = j["to"]["release"]
    inst = _install(root) or {}
    rel = L.release(name)
    may_migrate = (j["state"] not in STATES
                   or STATES.index(j["state"]) >= STATES.index(BACKED_UP))
    if may_migrate and held_by_other(j["brain"], j["port"]):
        # the migration may have started from the new release and still be
        # running from it: nothing of it is touched
        say(f"the Brain is still open, so {name} was kept: {STILL_OPEN}")
    elif _running_from(rel):
        # `<package.zip> update` runs this transaction in the new release's
        # own Python (D12): Windows refuses to delete what it has loaded,
        # and a delete that fails part-way would leave it broken. It is
        # whole and locked; the next update reuses it.
        say(f"kept the staged release {name}: this update runs from it")
    elif rel.exists() and name not in (inst.get("current"),
                                       inst.get("previous")) and (
            j.get("created_release") or not readonly.is_locked(rel)):
        # this update's own, or one a staging left unfinished (never locked)
        try:
            _discard(rel)
            say(f"discarded the staged release {name}")
        except OSError as exc:
            say(f"the staged release {name} could not be removed ({exc}); "
                "it is not used")
    with contextlib.suppress(OSError):
        _discard(L.releases / (name + ".partial"))
    old = j["from"]["release"]
    damage = _old_damage(root, j)
    restored = False
    if damage:
        # D6: never started, never called healthy
        say(f"{old} is damaged ({json.dumps(damage, default=str)[:600]}), so "
            "it was not started again. Updating again replaces it; so does "
            "repairing it from its own package (`install --repair`)")
    elif j.get("running_before"):
        try:
            if running(j["brain"], j["port"]) is None:
                start_release(root, old, j["brain"], j["port"])
                say(f"restarted {old}")
            restored, _ = _health(j["port"], old, j["brain"])
        except StepFailed as exc:
            return _attention(root, j, f"the update was undone (the Brain was "
                              f"not changed), but {old} did not start "
                              f"again: {exc}", say)
    else:
        # it was not running before, and is left so: its files verified
        restored = True
    j["why"] = why
    _finish(root, j, ABORTED, say)
    msg = (f"the update did not happen; {old} is unchanged and the Brain was "
           "not changed" + ("" if restored else
                            f", but {old} is not running and healthy"))
    say(msg)
    _ended("aborted", f"{msg}. Why: {why}", restored)
    return EXIT_FAILED


def _running_from(rel) -> bool:
    """Whether this process runs from release folder `rel`: its Python or
    this code is inside it."""
    return _inside(sys.executable, rel) or _inside(__file__, rel)


def _switch_back(root, j: dict, why: str, say) -> int:
    """After C2 and unhealthy, the old release able to read the Brain: put
    install.json back as the update found it and start the old release."""
    if j["state"] != ROLLING_BACK:
        j["why"] = why
        _save(root, j, ROLLING_BACK)
    name, brain, port = j["from"]["release"], j["brain"], j["port"]
    try:
        # D6: the old release's files are verified BEFORE anything is
        # switched back to it, and again before it is called healthy
        damage = _old_damage(root, j)
        if damage:
            raise StepFailed(f"{name} is damaged, so it was not switched back "
                             "to: " + json.dumps(damage, default=str)[:800])
        stop_brain(brain, port, root)
        _set_install(root, j["install_before"])
        _verify_brain(root, j, name, say)
        start_release(root, name, brain, port)
        ok, checks = _health(port, name, brain)
        if not ok:
            raise StepFailed("the old release is not healthy either: "
                             + json.dumps([c for c in checks
                                           if not c.get("ok")],
                                          default=str)[:1500])
        damage = _old_damage(root, j)
        if damage:
            raise StepFailed(f"{name} answered, but its files are damaged: "
                             + json.dumps(damage, default=str)[:800])
    except Exception as exc:                              # noqa: BLE001
        with contextlib.suppress(Exception):
            stop_brain(brain, port, root)
        return _attention(root, j, f"switching back to {name} failed: {exc} "
                          f"(after: {j.get('why')})", say)
    _finish(root, j, ROLLED_BACK, say)
    msg = (f"switched back to {name}: it is running and healthy, and no "
           f"records were lost. {j['to']['release']} is kept but not used.")
    say(msg)
    _ended("rolled_back", f"The update did not take: {j.get('why')}. {msg}",
           True)
    return EXIT_FAILED


def _recover_failure(root, j: dict, why: str, say) -> int:
    facts = brain_facts(j["brain"])
    if _switched(root, j) or _migrated(j, facts):
        if can_read(int(j["from"]["schema_target"]), facts):
            return _switch_back(root, j, why, say)
        with contextlib.suppress(Exception):
            stop_brain(j["brain"], j["port"], root)
        return _attention(root, j, f"{j['to']['release']} is not healthy and "
                          f"{j['from']['release']} cannot open the Brain at "
                          f"schema version {facts.get('version')}: {why}",
                          say)
    return _abort(root, j, why, say)


def recover(root, out=print) -> int:
    """Finish or undo an unfinished update, from the facts. Run by
    `mentis update --resume` and by the launcher on start."""
    root = pathlib.Path(root)
    say = _Log(root, out)
    with _update_lock(root):
        j = journal(root)
        if j is None:
            say("no unfinished update")
            _ended("nothing_to_resume", "There is no unfinished update.")
            return EXIT_DONE
        _result["update"] = j.get("id")
        try:
            return _recover(root, j, say)
        except UpdateRefused as exc:
            say(f"refused: {exc}")
            _ended("refused", f"Not resumed: {exc}")
            return EXIT_REFUSED


def _recover(root, j: dict, say) -> int:
    state = j["state"]
    say(f"resuming update {j['id']} ({j['from']['release']} -> "
        f"{j['to']['release']}), last recorded state {state}")
    if state == COMMITTED:
        _finish(root, j, COMMITTED, say)
        _ended("committed", f"update committed: Mentis is now "
               f"{j['to']['release']}")
        return EXIT_DONE
    if state == NEEDS_ATTENTION:
        inst = _install(root) or {}
        cur = inst.get("current")
        facts = brain_facts(j["brain"])
        rel_dir = home.Layout(root).release(cur) if cur else None
        rel = read_json(rel_dir / home.RELEASE_FILE) if cur else None
        who = running(j["brain"], j["port"])
        if (rel and who and _inside(who.get("code"), rel_dir)
                and can_read(int(rel["schema_target"]), facts)
                and not _intact(rel_dir)):
            ok, _ = _health(j["port"], cur, j["brain"])
            # D6: healthy only with its files verified, after as before
            if ok and not _intact(rel_dir):
                _finish(root, j, f"RESOLVED ({cur} healthy)", say)
                msg = f"resolved: {cur} is running and healthy"
                say(msg)
                _ended("resolved", msg,
                       cur == j["from"]["release"])
                return EXIT_DONE
        if who is None:
            # N3: nothing serves the Brain. With a release made whole again
            # since (staged again from a package), the recovery is tried
            # again from the facts; it ends where it can, or here again
            retry = _retry_attention(root, j, facts, say)
            if retry is not None:
                return retry
        say("still needs attention: " + str(j.get("needs_attention")))
        say(f"see {home.Layout(root).needs_attention}")
        _ended("needs_attention", "Still needs a decision: "
               + str(j.get("needs_attention")))
        return EXIT_ATTENTION
    # the first fact: whether something (a migration this update started,
    # say) still has the Brain open. Until it lets go, the ledger may not
    # yet say what will have happened; refused, and nothing is discarded
    _await_openers(j["brain"], j["port"], say)
    if state == ROLLING_BACK:
        return _switch_back(root, j, j.get("why") or "interrupted", say)
    facts = brain_facts(j["brain"])
    if _switched(root, j):
        if STATES.index(state) < STATES.index(SWITCHED):
            _save(root, j, SWITCHED)
        return _drive(root, j, say)
    if _migrated(j, facts):
        say("the Brain was already migrated (commit point C1 passed); "
            "continuing forward")
        # install.json does not name the new release, whatever the journal
        # says: the switch (C2) is redone from here
        if state != MIGRATED:
            _save(root, j, MIGRATED)
        try:
            stop_brain(j["brain"], j["port"], root)
        except StepFailed as exc:
            return _recover_failure(root, j, str(exc), say)
        return _drive(root, j, say)
    return _abort(root, j, f"interrupted at {state}, before the Brain was "
                  "migrated", say)


def _retry_attention(root, j: dict, facts: dict, say) -> int | None:
    """A NEEDS_ATTENTION resumed with nothing serving the Brain (N3): try
    the way out again, now that a release may have been made whole. Forward
    when the update passed a commit point (C1 or C2) and its new release is
    whole -- the switch and the health check are redone, and a failure
    recovers as any failure does (switching back when the old release is
    whole and can read the Brain); else back to the old release when it is
    whole and the Brain was not migrated past it. None when neither release
    can be tried (nothing changes; it still needs attention)."""
    L = home.Layout(root)
    new_whole = not _intact(L.release(j["to"]["release"]))
    old_whole = not _old_damage(root, j)
    forward = _switched(root, j) or _migrated(j, facts)
    _await_openers(j["brain"], j["port"], say)
    if forward and new_whole:
        say(f"{j['to']['release']} is whole; trying it again")
        state = SWITCHED if _switched(root, j) else MIGRATED
        j.pop("needs_attention", None)
        _save(root, j, state)
        return _drive(root, j, say)
    if old_whole and (not forward or can_read(int(j["from"]["schema_target"]),
                                              facts)):
        say(f"{j['from']['release']} is whole; going back to it")
        j.pop("needs_attention", None)
        if forward:
            return _switch_back(root, j, j.get("why") or "needed attention",
                                say)
        return _abort(root, j, j.get("why") or "needed attention", say)
    return None


# -- the commands -------------------------------------------------------------

@contextlib.contextmanager
def _update_lock(root):
    from mentis.spine import brainlock
    L = home.Layout(root)
    if not L.install_json.is_file():
        # refused before anything is created: no lock file, no log, no
        # state folder at a root nobody installed into
        raise UpdateRefused(f"no installed Mentis at {root} "
                            f"(no {L.install_json})")
    d = L.state
    got = brainlock._take(str(d), "update.lock", False)
    if got is None:
        raise UpdateRefused("another update or rollback is running")
    try:
        yield
    finally:
        got.release()


def _ask(question: str, confirm) -> bool:
    try:
        return (confirm(question + " [y/N] ") or "").strip().lower() in (
            "y", "yes")
    except EOFError:
        return False


def build_from_repo(root, spec: str, version: str | None = None,
                    say=print, out=None) -> pathlib.Path:
    """`--from-repo PATH@COMMIT`: build the package with the package builder
    into `out` (default `<root>/packages/`); one already in
    `<root>/packages/` is used as it is. The version defaults to the
    current release's (the commit tells the two apart)."""
    from mentis.release import build
    path, sep, commit = spec.rpartition("@")
    if not sep or not path or not commit:
        raise UpdateRefused("--from-repo wants PATH@COMMIT")
    if version is None:
        inst = _install(root) or {}
        cur = read_json(home.Layout(root).release(inst.get("current", "-"))
                        / home.RELEASE_FILE) if inst.get("current") else None
        if not cur:
            raise UpdateRefused("no current release to take a version from; "
                                "give --version")
        version = cur["version"]
    kept = pathlib.Path(root) / "packages"
    out = pathlib.Path(out) if out is not None else kept
    sha = build.resolve(path, commit)
    existing = kept / build.package_name(version, sha)
    if existing.exists():
        say(f"using the package already built: {existing}")
        return existing
    say(f"building {version} from {path} at {sha[:12]}")
    try:
        got = build.build(version, commit, repo=path, out=out)
    except build.BuildError as exc:
        raise UpdateRefused(f"the package could not be built: {exc}") from None
    return pathlib.Path(got["package"])


def update(root, package=None, *, from_repo: str | None = None,
           version: str | None = None, wheels=None, yes: bool = False,
           confirm=input, out=print, drain_wait_s: float = DRAIN_WAIT_S,
           _kind: str = "update", staged_here: bool = False) -> int:
    """The update transaction, from the plan to COMMITTED (or a recovery).

    With `from_repo` the package is built BEFORE the confirmation, because
    the plan is read from it; it is built into a temporary folder, moved to
    `<root>/packages/` only once the update is confirmed, and the folder is
    removed whatever happens."""
    root = pathlib.Path(root)
    say = _Log(root, out)
    built = None
    try:
        with _update_lock(root):
            if journal(root) is not None:
                raise UpdateRefused("an update is unfinished; run `mentis "
                                    "update --resume` first")
            if from_repo:
                built = pathlib.Path(tempfile.mkdtemp(
                    prefix="mentis-update-build-"))
                package = build_from_repo(root, from_repo, version, say,
                                          out=built)
            if package is None:
                raise UpdateRefused("name a package, or --from-repo")
            package = pathlib.Path(package).resolve()
            p = plan(root, package)
            say(describe(p))
            if not p["ok"]:
                _ended("refused", "Cannot update: " + "; ".join(p["problems"])
                       + ". Nothing was changed.")
                return EXIT_REFUSED
            if not yes and not _ask("Proceed?", confirm):
                say("not confirmed; nothing was changed")
                _ended("not_confirmed", "Not confirmed; nothing was changed.")
                return EXIT_REFUSED
            if built is not None and _inside(package, built):
                package = _keep_package(root, package)
                p["package"] = str(package)
            inst = _install(root)
            j = {"format": FORMAT, "id": f"upd-{uuid.uuid4().hex[:12]}",
                 "kind": _kind, "root": str(root), "package": str(package),
                 "package_sha256": (None if package.is_dir()
                                    else _sha256(package)),
                 "wheels": str(pathlib.Path(wheels).resolve()) if wheels
                 else None,
                 "brain": p["brain"], "port": p["port"],
                 "from": p["from"], "to": p["to"],
                 "migrations": p["migrations"],
                 "allow_breaking": p["breaking"],
                 "rollback_possible": p["rollback_possible"],
                 "brain_before": p["brain_before"],
                 "install_before": inst,
                 "running_before": running(p["brain"], p["port"]),
                 "created_release": False, "backup": None,
                 "drain_wait_s": drain_wait_s,
                 "started_at": _now_iso()}
            if staged_here and p["to"]["release"] not in (
                    inst.get("current"), inst.get("previous")):
                # staged a moment ago, for this update, by the package's
                # own installer (`<package.zip> update`): this update's own
                j["created_release"] = True
            _result["update"] = j["id"]
            _save(root, j, APPROVED)
            return _drive(root, j, say)
    except UpdateRefused as exc:
        say(f"refused: {exc}")
        _ended("refused", f"Not updated: {exc}. Nothing was changed.")
        return EXIT_REFUSED
    finally:
        if built is not None:
            shutil.rmtree(built, ignore_errors=True)


def _keep_package(root, package: pathlib.Path) -> pathlib.Path:
    """Move a package built for a confirmed update, and its `.sha256`, into
    `<root>/packages/`."""
    kept = pathlib.Path(root) / "packages"
    kept.mkdir(parents=True, exist_ok=True)
    side = package.with_name(package.name + ".sha256")
    dest = kept / package.name
    if side.exists():
        shutil.move(str(side), str(kept / side.name))
    shutil.move(str(package), str(dest))
    return dest


def rollback(root, *, yes: bool = False, confirm=input, out=print) -> int:
    """Go back to install.json's `previous` release, through the same
    transaction (the release is already staged; no migration). Refused when
    that release cannot open the Brain: a restore is never automatic."""
    root = pathlib.Path(root)
    say = _Log(root, out)
    inst = _install(root) or {}
    prev = inst.get("previous")
    if not prev:
        say("refused: there is no previous release to go back to")
        _ended("no_previous", "There is no previous release to go back to.")
        return EXIT_REFUSED
    rel_dir = home.Layout(root).release(prev)
    if not rel_dir.is_dir():
        say(f"refused: {rel_dir} is no longer here")
        _ended("previous_missing", f"{rel_dir} is no longer here.")
        return EXIT_REFUSED
    why = _intact(rel_dir)
    if why:
        # N2: going back needs it whole; its own package stages it again
        msg = (f"{prev} is damaged ({json.dumps(why, default=str)[:400]}), so "
               "Mentis did not go back to it and nothing was changed. Its own "
               f"package stages it again and switches to it: `python "
               f"mentis-{prev}[-win64].zip update`")
        say(f"refused: {msg}")
        _ended("previous_damaged", msg)
        return EXIT_REFUSED
    return update(root, rel_dir, yes=yes, confirm=confirm, out=out,
                  _kind="rollback")


def status(root) -> dict:
    """The update side of `mentis status`: an unfinished update, if any, and
    whether a human decision is waiting."""
    L = home.Layout(root)
    j = journal(root)
    return {"update": None if j is None else {
                "id": j["id"], "kind": j.get("kind"), "state": j["state"],
                "from": j["from"]["release"], "to": j["to"]["release"]},
            "needs_attention": read_json(L.needs_attention)}


def unfinished(root) -> bool:
    """Whether the launcher must run `recover` before starting."""
    return home.Layout(root).journal.exists()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="mentis",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update", help="update to another release")
    u.add_argument("package", nargs="?")
    u.add_argument("--from-repo", metavar="PATH@COMMIT",
                   help="build the package from a repository first. The "
                   "build runs BEFORE you are asked to confirm, because the "
                   "plan is read from the package; it is built into a "
                   "temporary folder that is removed if you decline, and "
                   "kept under <root>/packages only once you confirm")
    u.add_argument("--version", help="with --from-repo: the SemVer version "
                   "to build (default: the current release's)")
    u.add_argument("--wheels", metavar="BUNDLE")
    u.add_argument("--yes", action="store_true")
    u.add_argument("--resume", action="store_true")
    #: the package's release was staged a moment ago by the package's own
    #: installer for this update (`<package.zip> update`)
    u.add_argument("--staged-here", action="store_true",
                   help=argparse.SUPPRESS)
    r = sub.add_parser("rollback", help="go back to the previous release")
    r.add_argument("--yes", action="store_true")
    for p in (u, r):
        p.add_argument("--progress", choices=progress.MODES,
                       help="one JSON line per step on stdout; words on "
                       "stderr")
        p.add_argument("--json", action="store_true",
                       help="print the result as one JSON object (I2)")
    a = ap.parse_args(argv)
    progress.configure(a.progress)
    _result.clear()
    quiet = progress.on() or a.json
    out = ((lambda m: print(m, file=sys.stderr, flush=True))
           if quiet else print)
    # the question too goes to stderr: stdout carries JSON lines only
    confirm = ((lambda q: (print(q, end="", file=sys.stderr, flush=True),
                           input())[1]) if quiet else input)
    root = None
    try:
        root = home.root()
        if a.cmd == "rollback":
            code = rollback(root, yes=a.yes, confirm=confirm, out=out)
        elif a.resume:
            if a.package or a.from_repo:
                ap.error("--resume takes no package")
            code = recover(root, out=out)
        else:
            if bool(a.package) == bool(a.from_repo):
                ap.error("name a package or --from-repo PATH@COMMIT (one)")
            code = update(root, a.package, from_repo=a.from_repo,
                          version=a.version, wheels=a.wheels, yes=a.yes,
                          confirm=confirm, out=out,
                          staged_here=a.staged_here)
    except UpdateRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        code = EXIT_REFUSED
        _ended("refused", f"Refused: {exc}. Nothing was changed.")
    except Exception as exc:                                  # noqa: BLE001
        # I1: an unexpected exception is a failure, said, with the result
        # still printed; a journal it leaves is for `--resume`
        import traceback
        traceback.print_exc(file=sys.stderr)
        code = EXIT_FAILED
        _ended("unexpected", f"{type(exc).__name__}: {exc}")
    if progress.last_step() != "update":
        # refused, not confirmed, or nothing to resume: still one last line
        progress.emit("update", progress.DONE if code == EXIT_DONE
                      else progress.FAILED,
                      {EXIT_DONE: "nothing to do",
                       EXIT_REFUSED: "refused; nothing was changed"}.get(
                          code, f"exit {code}"))
    if a.json:
        progress.result(result_doc(root, code))
    return code


def serving_release(root) -> str | None:
    """The release actually serving this install's Brain on its port, by
    the server's own answer (`code` under `releases/<name>`), or None."""
    if root is None:
        return None
    try:
        inst = _install(root) or {}
        who = running(inst["brain"], inst["port"]) if inst else None
    except Exception:                                         # noqa: BLE001
        return None
    if not who or not who.get("code"):
        return None
    L = home.Layout(root)
    for name in (inst.get("current"), inst.get("previous")):
        if name and _inside(who["code"], L.release(name)):
            return name
    try:
        for d in L.releases.iterdir():
            if home.is_release_name(d.name) and _inside(who["code"], d):
                return d.name
    except OSError:
        pass
    return None


def result_doc(root, code: int) -> dict:
    """The final `--json` result of update, rollback and resume (I2)."""
    outcome = progress.OUTCOME_OF.get(code, progress.FAILED_OUTCOME)
    reason = _result.get("reason") or {
        EXIT_DONE: "ok", EXIT_REFUSED: "refused",
        EXIT_ATTENTION: "needs_attention"}.get(code, "failed")
    message = _result.get("message") or f"ended with exit {code}"
    return progress.outcome_doc(
        outcome, reason, message, running=serving_release(root),
        previous_restored=bool(_result.get("previous_restored")),
        update=_result.get("update"))


if __name__ == "__main__":
    sys.exit(main())
