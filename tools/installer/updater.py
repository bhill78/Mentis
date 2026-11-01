"""`mentis.cmd update` and `rollback`: move an install to another release, safely.

    mentis.cmd update <Mentis-Setup-....exe> [--yes] [--drain-wait S]
    mentis.cmd update --resume
    mentis.cmd rollback [--yes]

Mark IV's guarantees (its mentis/updater.py, the reference), in the smallest form
this install's layout allows. docs/windows-installer.md says what each is for.

BESIDE THE RUNNING ONE. The setup exe's payload is unpacked by itself into
`releases\\.incoming-<pid>` (`/EXTRACT=`), every file checked against FILES.json,
its Python run, and only then renamed to `releases\\<name>` and locked read-only
(`mentis.readonly`). The running server has not been touched. Everything after that
runs in THE NEW RELEASE'S OWN LAUNCHER, so a defect in the old one's update cannot
hold an install back. Double-clicking the setup exe over an install does the same
thing (`arrive`), from a copy in `.incoming`, which also needs nothing of the old
release to work.

THE TRANSACTION. Each state is written to `state\\update.journal.json` (atomic
replace + fsync) once it is reached:

  APPROVED   the plan was shown and confirmed (or --yes); the new release re-hashed
  STOPPED    running work drained through /api/working, every declared process
             stopped in reverse order, the Brain's open lock confirmed free
  BACKED_UP  `mentis.brain backup`, then verify-backup says usable
  MIGRATED   `mentis.migrate --apply`, by the new release: one transaction. C1.
  SWITCHED   state\\previous = old, state\\current = new. C2.
  HEALTHY    `mentis.brain verify`, the new release's `start`, then its answer at
             the manifest's `identity` names this commit and this Brain, and every
             manifest `health` URL answers 200 with no `"intact": false`
  COMMITTED  the journal archived under state\\updates\\ and removed

RECOVERY IS DERIVED FROM FACTS, as in Mark IV: the journal says what was intended;
what happened is read from the Brain's lock and ledger and from state\\current.

  - something not a server holds the Brain's lock: wait, then refuse. Nothing is
    decided until it lets go: a migration the update started may still be running.
  - before C1: the update did not happen. The staged release is discarded when it
    can be and the old server restarted if it was running. ABORTED.
  - after C1, not switched: forward; the switch is redone.
  - after C1 or C2 and unhealthy, and the old release can read the Brain: switch
    back, start it, check it. ROLLED_BACK; no record is lost.
  - after C1 or C2 and unhealthy, and it cannot: NEEDS_ATTENTION
    (state\\needs-attention.json). Everything is kept and the restore-plan command
    is said. NEVER a restore.

A release's files are re-hashed before it is trusted: a damaged one is not switched
back to or started. Staged again from its package, the damaged copy is set aside as
`<name>.damaged-<stamp>`, never deleted. A commit removes no release. `start` and `open`
run the recovery first, so a killed update cannot be started around.

`mentis.cmd rollback` is the same transaction, to `state\\previous`, with no
migration; refused when that release cannot read the Brain.

Exit status, and one JSON object on stdout: 0 done, 2 refused and nothing changed,
3 the update did not happen (aborted or switched back; `previous_restored` says
whether the old release is verified and healthy), 4 NEEDS_ATTENTION.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

import launcher
from launcher import Install, Refused

FORMAT = 1
APPROVED, STOPPED, BACKED_UP, MIGRATED, SWITCHED, HEALTHY, COMMITTED = (
    "APPROVED", "STOPPED", "BACKED_UP", "MIGRATED", "SWITCHED", "HEALTHY", "COMMITTED")
STATES = (APPROVED, STOPPED, BACKED_UP, MIGRATED, SWITCHED, HEALTHY, COMMITTED)
ROLLING_BACK, ABORTED, ROLLED_BACK, NEEDS_ATTENTION = (
    "ROLLING_BACK", "ABORTED", "ROLLED_BACK", "NEEDS_ATTENTION")
EXIT_DONE, EXIT_REFUSED, EXIT_FAILED, EXIT_ATTENTION = 0, 2, 3, 4
OUTCOME = {0: "ok", 2: "refused", 3: "failed", 4: "needs_attention"}

DRAIN_WAIT_S = 600
OPEN_WAIT_S = 15
STILL_OPEN = "a migration or another opener is still running; try again"
#: how this build's setup exe says it is one, in its version resource
SETUP_MARK = "Mentis server and Fluid setup".encode("utf-16-le")

#: TESTS AND THE PROOF ONLY: at every label `_at` names, on both sides of each commit
#: point, die as a kill would. In-process by `_hook`, in a real install by this variable.
_hook = None
KILL_AT = "MENTIS_UPDATE_KILL_AT"


def _at(label: str) -> None:
    if _hook is not None:
        _hook(label)
    if os.environ.get(KILL_AT) == label:
        os.kill(os.getpid(), signal.SIGTERM)         # TerminateProcess, on Windows


class StepFailed(RuntimeError):
    """A step did not succeed; recovery decides what next."""


# -- small io -------------------------------------------------------------------

def _journal_path(inst: Install) -> pathlib.Path:
    return inst.state_dir / "update.journal.json"


def _attention_path(inst: Install) -> pathlib.Path:
    return inst.state_dir / "needs-attention.json"


def _write(path: pathlib.Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".partial")
    with open(part, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(part, path)


def _read(path: pathlib.Path) -> dict | None:
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def journal(inst: Install) -> dict | None:
    return _read(_journal_path(inst))


def _sayer(inst: Install):
    def say(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
        with contextlib.suppress(OSError):
            inst.logs.mkdir(parents=True, exist_ok=True)
            with open(inst.logs / "update.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    return say


def _save(inst: Install, j: dict, state: str | None = None) -> None:
    if state is not None:
        j["state"] = state
        j["history"].append({"state": state, "at": time.time()})
    _write(_journal_path(inst), j)
    if state is not None:
        _at(f"state:{state}")


def _finish(inst: Install, j: dict, outcome: str) -> None:
    """Archive the journal and remove it."""
    j["outcome"] = outcome
    j["history"].append({"state": outcome, "at": time.time()})
    _write(inst.state_dir / "updates" / f"{j['id']}.json", j)
    _journal_path(inst).unlink(missing_ok=True)
    _attention_path(inst).unlink(missing_ok=True)


@contextlib.contextmanager
def _update_lock(inst: Install):
    from mentis.spine import brainlock
    inst.state_dir.mkdir(parents=True, exist_ok=True)
    got = brainlock._take(str(inst.state_dir), "update.lock", False)
    if got is None:
        raise Refused("another update or rollback is running")
    try:
        yield
    finally:
        got.release()


# -- releases -------------------------------------------------------------------

def name_of(build: dict) -> str:
    return f"{build['version']}+{build['commit'][:12]}"


def _build_of(home: pathlib.Path) -> dict | None:
    return _read(home / "app" / "BUILD.json")


def _damage(home: pathlib.Path) -> list:
    """Why this release is not whole (empty when it is)."""
    try:
        got = launcher.verify_dir(home)
    except (OSError, ValueError) as exc:
        return [f"{type(exc).__name__}: {exc}"]
    return [] if got["ok"] else [{"missing": got["missing"][:5], "changed": got["changed"][:5]}]


def _discard(path: pathlib.Path) -> None:
    """Remove a release folder, its read-only lock first."""
    if not path.exists():
        return
    from mentis import readonly
    readonly.unlock(path)
    for tries in range(20):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            # what Windows says while a scanner still has a file open
            if tries == 19:
                raise
            time.sleep(0.5)


def _inside(path, root) -> bool:
    p, r = (os.path.normcase(os.path.abspath(str(x))) for x in (path, root))
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)


def _running_from(home: pathlib.Path) -> bool:
    return _inside(__file__, home)


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}


def _launch(inst: Install, name: str, *args) -> subprocess.CompletedProcess:
    """That release's own launcher, which alone reads its own manifest."""
    home = inst.releases / name
    return subprocess.run([str(home / "runtime" / "python.exe"), "-I", "-X", "utf8",
                           str(home / "app" / "launcher.py"), *args],
                          cwd=inst.state_dir, env=_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                          creationflags=launcher.NO_WINDOW)


def _run_release(inst: Install, name: str, *args, timeout=3600) -> subprocess.CompletedProcess:
    """The Brain is only ever touched through that release's own existing commands."""
    home = inst.releases / name
    return subprocess.run([str(home / "runtime" / "python.exe"), "-I", "-X", "utf8", *args],
                          cwd=inst.state_dir, env=_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          stdin=subprocess.DEVNULL, creationflags=launcher.NO_WINDOW)


_SELFTEST = ("import json, sys\n"
             "import mentis.web, mentis.migrate, mentis.bootstrap.new_brain, mentis.readonly\n"
             "from mentis.web import identity\n"
             "print(json.dumps(identity._INSTALLED))\n")


def _self_test(home: pathlib.Path, build: dict) -> None:
    """The release runs, as the release it says it is."""
    r = subprocess.run([str(home / "runtime" / "python.exe"), "-I", "-B", "-X", "utf8", "-c", _SELFTEST],
                       cwd=home.parent, env=_env(), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL, timeout=300,
                       creationflags=launcher.NO_WINDOW)
    if r.returncode:
        raise Refused(f"its Python does not run it:\n{r.stderr[-1500:]}")
    if (json.loads(r.stdout.strip().splitlines()[-1]) or {}).get("commit") != build["commit"]:
        raise Refused(f"it does not say it is {build['commit'][:12]}: {r.stdout[-300:]}")


def _lock(home: pathlib.Path) -> None:
    from mentis import readonly
    readonly.lock(home)


def _unpack(package: pathlib.Path, into: pathlib.Path) -> None:
    """A setup exe's payload, by the exe itself. It is run only once it says it is one."""
    try:
        with open(package, "rb") as f:
            head = f.read(4 << 20)
    except OSError as exc:
        raise Refused(f"{package} cannot be read: {exc}") from None
    if SETUP_MARK not in head:
        raise Refused(f"{package} is not a Mentis setup exe")
    side = package.with_name(package.name + ".sha256")
    if side.is_file():
        import hashlib
        want = side.read_text("utf-8").split()[0]
        h = hashlib.sha256()
        with open(package, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest() != want:
            raise Refused(f"{package} is not what {side.name} says it is")
    r = subprocess.run(f'"{package}" /S /EXTRACT="{into}"', timeout=900, env=_env(),
                       stdin=subprocess.DEVNULL, capture_output=True,
                       creationflags=launcher.NO_WINDOW)
    if r.returncode or not (into / "app" / "BUILD.json").is_file():
        raise Refused(f"{package} did not unpack (exit {r.returncode}): it is damaged or incomplete")


def _set_aside(inst: Install, dest: pathlib.Path) -> None:
    """A damaged copy is evidence: renamed beside it, never deleted."""
    from mentis import readonly
    aside = dest.with_name(f"{dest.name}.damaged-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
    with contextlib.suppress(Exception):
        readonly.unlock(dest)
    try:
        os.rename(dest, aside)
    except OSError as exc:
        raise Refused(f"the damaged {dest.name} could not be set aside ({exc}); something still "
                      "holds a file in it. Nothing was replaced; run the same command again") from None
    _sayer(inst)(f"the damaged copy is kept as releases\\{aside.name}")


def place(inst: Install, src: pathlib.Path, build: dict, *, move: bool) -> bool:
    """`src`, checked, as `releases\\<name>`, locked. True if it was made here; a whole
    one already there is reused, a damaged one set aside once this one has verified.
    The caller removes `src` if it was not moved."""
    name = name_of(build)
    dest = inst.releases / name
    damaged = dest.exists() and bool(_damage(dest))
    if dest.exists() and not damaged:
        return False
    checked = launcher.verify_dir(src)
    if not checked["ok"]:
        raise Refused(f"{checked['files']} files, but missing {checked['missing'][:5]} "
                      f"changed {checked['changed'][:5]}")
    _self_test(src, build)
    if not move:
        part = dest.with_name(name + ".partial")
        _discard(part)
        shutil.copytree(src, part)
        src = part
    if damaged:
        _set_aside(inst, dest)
    for tries in range(40):
        try:
            os.replace(src, dest)
            break
        except OSError:
            # a scanner reading what was just unpacked
            if tries == 39:
                raise
            time.sleep(0.25)
    _lock(dest)
    return True


def _clear_incoming(inst: Install) -> None:
    """What a killed staging left. Never a named release."""
    if inst.releases.is_dir():
        for d in inst.releases.iterdir():
            if d.name.startswith(".incoming-") or d.name.endswith(".partial"):
                with contextlib.suppress(OSError):
                    _discard(d)


# -- the Brain ------------------------------------------------------------------

def _brain_facts(brain: str) -> dict:
    """What the Brain's ledger says, read-only; any reader can tell these."""
    from mentis.spine import migrations
    try:
        st = migrations.status_of(str(brain))
    except migrations.BrainMissing:
        return {"exists": False, "version": None, "min_reader": None, "state": None,
                "problems": ["no Brain there"], "legacy_open": False}
    except Exception as exc:                                  # noqa: BLE001
        return {"exists": True, "version": None, "min_reader": None, "state": "unreadable",
                "problems": [f"{type(exc).__name__}: {exc}"], "legacy_open": False}
    return {"exists": True, "version": st.version, "min_reader": st.min_reader, "state": st.state,
            "problems": list(st.problems), "legacy_open": st.legacy_open}


def can_read(target: int, facts: dict) -> bool:
    """Whether a release whose schema target is `target` opens this Brain: the open
    gate of `mentis.spine.migrations.inspect`."""
    v, mr = facts.get("version"), facts.get("min_reader")
    if v is None or facts.get("problems"):
        return False
    return v == target or (v > target and (mr or 0) <= target)


def _brain_is_open(brain: str) -> bool:
    from mentis.spine import brainlock
    return os.path.isdir(brain) and brainlock.is_open(brain)


def _held_by_other(inst: Install, j: dict) -> bool:
    return _brain_is_open(j["brain"]) and _serving(inst, j["to"]["release"]) is None \
        and _serving(inst, j["from"]["release"]) is None


def _await_openers(inst: Install, j: dict, say, wait_s: float = OPEN_WAIT_S) -> None:
    end = time.time() + wait_s
    said = False
    while _held_by_other(inst, j):
        if time.time() >= end:
            raise Refused(f"the Brain at {j['brain']} is open: {STILL_OPEN}")
        if not said:
            say("something still has the Brain open; waiting for it to finish")
            said = True
        time.sleep(0.5)


def _verify_brain(inst: Install, j: dict, name: str, say) -> None:
    """`mentis.brain verify` by that release; rebuild-derived when the only problem is
    the derived indexes its migrations declare, as Mark IV. The server is stopped."""
    got = _run_release(inst, name, "-m", "mentis.brain", "verify", j["brain"])
    try:
        out = json.loads(got.stdout)
    except ValueError:
        raise StepFailed(f"brain verify did not answer: {got.stderr[-1000:]}") from None
    if not out["ok"] and out.get("missing_indexes") and len(out["problems"]) == 1:
        say("rebuilding missing derived indexes: " + ", ".join(out["missing_indexes"]))
        r = _run_release(inst, name, "-m", "mentis.brain", "rebuild-derived", j["brain"])
        if r.returncode:
            raise StepFailed(f"rebuild-derived failed: {r.stderr[-1000:]}")
        out = json.loads(_run_release(inst, name, "-m", "mentis.brain", "verify", j["brain"]).stdout)
    if not out["ok"]:
        raise StepFailed("brain verify: " + "; ".join(out["problems"]))


# -- servers --------------------------------------------------------------------

def _get(url: str, timeout: float = 10.0):
    try:
        return launcher._answer(url, timeout)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:300]
    except (urllib.error.URLError, OSError) as exc:
        return None, str(exc).encode()


def _serving(inst: Install, name: str | None = None) -> dict | None:
    """Whatever answers for this install's Brain, read as that release's manifest says."""
    st = inst.state()
    there = inst.at(name or inst.release)
    if not st:
        return None
    try:
        url = there.manifest()["identity"].format_map(there.values(st))
    except (OSError, ValueError, KeyError):
        return None
    code, body = _get(url, 3.0)
    if code != 200:
        return None
    try:
        who = json.loads(body)
    except ValueError:
        return None
    return who if launcher._same_path(who.get("corpus") or "", st["brain"]) else None


def _serving_name(inst: Install) -> str | None:
    who = _serving(inst, inst.current() or inst.release)
    rel = (who or {}).get("release") or {}
    return f"{rel['version']}+{rel['commit'][:12]}" if rel.get("commit") and rel.get("version") else None


def _drain(inst: Install, wait_s: float, say) -> None:
    """Wait until no run this server holds is still open."""
    st = inst.state()
    cur = inst.at(inst.current() or inst.release)
    declared = cur.manifest().get("working")
    if not declared:
        return
    url = declared.format_map(cur.values(st))
    end = time.time() + wait_s
    said = False
    while True:
        code, body = _get(url)
        if code == 404:
            return                      # this server has no such question
        try:
            doc = json.loads(body) if code == 200 else {"why_not": f"HTTP {code}"}
        except ValueError:
            doc = {"why_not": "it did not answer in JSON"}
        held = [r for r in doc.get("open") or []
                if r.get("held_here") and r.get("state") != "runtime-ended"]
        if not held and not doc.get("why_not"):
            return
        if time.time() >= end:
            raise StepFailed(f"running work did not finish within {wait_s:g} s ("
                             + (f"{len(held)} run(s) still open" if held
                                else f"could not ask: {doc.get('why_not')}")
                             + "); Mentis was left running")
        if not said:
            say(f"waiting for {len(held)} running piece(s) of work to finish"
                if held else "waiting to learn what is running")
            said = True
        time.sleep(2)


def _stop_all(inst: Install, brain: str) -> dict:
    """Every declared process, in reverse, then the Brain's own lock confirmed free."""
    got = launcher.stop(inst)
    end = time.time() + OPEN_WAIT_S
    while _brain_is_open(brain):
        if time.time() >= end:
            raise StepFailed(f"something still has the Brain at {brain} open after stopping Mentis")
        time.sleep(0.25)
    return got


def _start(inst: Install, name: str) -> None:
    r = _launch(inst, name, "start", "--in-update")
    if r.returncode:
        # the launcher's own sentence, then the end of the log it quotes
        said = (r.stderr or r.stdout).strip().splitlines() or ["it said nothing"]
        raise StepFailed(f"{name} did not start: " + "\n".join([said[0], *said[1:][-10:]])[-1500:])


def _health(inst: Install, name: str) -> list:
    """What is wrong with what answers, as release `name` (empty when nothing is)."""
    st = inst.state()
    there = inst.at(name)
    build, man = there.build(), there.manifest()
    values = there.values(st)
    wrong = []
    code, body = _get(man["identity"].format_map(values))
    try:
        who = json.loads(body) if code == 200 else None
    except ValueError:
        who = None
    if not who:
        return [f"{man['identity'].format_map(values)} answered {code}"]
    rel = who.get("release") or {}
    if rel.get("commit") != build["commit"] or rel.get("version") != build["version"]:
        wrong.append(f"it runs {rel.get('version')} {str(rel.get('commit'))[:12]}, "
                     f"not {build['version']} {build['commit'][:12]}")
    if not launcher._same_path(who.get("corpus") or "", st["brain"]):
        wrong.append(f"it serves the Brain {who.get('corpus')}")
    for row in man.get("health", []):
        url = row.format_map(values)
        code, body = _get(url)
        if code != 200:
            wrong.append(f"{url} answered {code}")
            continue
        try:
            said = json.loads(body)
        except ValueError:
            continue
        if isinstance(said, dict) and said.get("intact") is False:
            wrong.append(f"{url} says the record is not intact")
    return wrong


# -- the plan -------------------------------------------------------------------

def _version_key(version: str | None) -> tuple:
    try:
        return tuple(int(x) for x in str(version).split("."))
    except ValueError:
        return (0,)


def plan(inst: Install, to: dict) -> dict:
    """What moving this install to the release with BUILD `to` would do. Writes nothing."""
    problems: list = []
    st = inst.state() or {}
    cur_name = inst.current()
    to_name = name_of(to)
    cur = _build_of(inst.releases / cur_name) if cur_name else None
    cur = cur or {}
    brain = st.get("brain")
    if _journal_path(inst).exists():
        problems.append("an update is unfinished; run `mentis.cmd update --resume` first")
    facts = _brain_facts(brain)
    v, mr = facts["version"], facts["min_reader"] or 0
    target = int(to.get("schema_target", 0))
    old_target = cur.get("schema_target")
    pending = (list(to.get("migrations", []))[v:target] if v is not None and v < target else [])
    after = {"version": max(v or 0, target) if pending else v,
             "min_reader": max(mr, int(to.get("min_reader_after") or 0)) if pending else facts["min_reader"],
             "problems": []}
    rollback_ok = old_target is not None and can_read(int(old_target), after)
    now_v, to_v = _version_key(cur.get("version")), _version_key(to.get("version"))
    direction = ("upgrade" if to_v > now_v else "downgrade" if to_v < now_v
                 else "same version, other commit")
    if to_name == cur_name:
        problems.append(f"{to_name} is already the current release")
    if not facts["exists"]:
        problems.append(f"no Brain at {brain}")
    elif v is None:
        problems.append(f"the Brain at {brain} has no schema ledger yet ({facts['state']}): "
                        "`mentis.migrate --plan` says how to adopt it")
    elif facts["problems"]:
        problems.append(f"the Brain at {brain} needs attention: " + "; ".join(facts["problems"]))
    elif facts["legacy_open"]:
        problems.append("a release older than the schema ledger opened the Brain; run "
                        "`mentis.brain reconcile` first")
    elif not can_read(target, after):
        problems.append(f"{to_name} cannot open this Brain (schema version {v}, needs a reader of "
                        f"at least {mr}; that release reads up to {target}). Nothing was changed")
    return {"ok": not problems, "problems": problems, "brain": brain,
            "from": {"release": cur_name, "version": cur.get("version"), "commit": cur.get("commit"),
                     "schema_target": old_target},
            "to": {"release": to_name, "version": to.get("version"), "commit": to.get("commit"),
                   "schema_target": target, "min_reader_after": to.get("min_reader_after")},
            "brain_before": {"version": v, "min_reader": facts["min_reader"]},
            "brain_after": {"version": after["version"], "min_reader": after["min_reader"]},
            "direction": direction, "major": to_v[0] > now_v[0], "migrations": pending,
            "breaking": bool(pending) and int(to.get("min_reader_after") or 0) > mr,
            "rollback_possible": rollback_ok}


def describe(p: dict) -> str:
    f, t = p["from"], p["to"]
    lines = [f"Update Mentis {f['release']} -> {t['release']}, {p['direction']}",
             f"Brain: {p['brain']} (schema version {p['brain_before']['version']})"]
    if p["migrations"]:
        lines.append(f"Brain migrations: {', '.join(p['migrations'])} (schema "
                     f"{p['brain_before']['version']} -> {p['brain_after']['version']}); "
                     "a backup is taken first")
    else:
        lines.append("Brain migrations: none")
    if p["rollback_possible"]:
        lines.append(f"If the new release is not healthy, Mentis switches back to {f['release']} "
                     "automatically; no records are lost.")
    else:
        lines.append(f"After this update {f['release']} can no longer open the Brain. If the new "
                     "release is not healthy, the update stops and asks you (NEEDS ATTENTION); "
                     "nothing is restored automatically.")
    if p["breaking"] or p["major"]:
        lines.append("This is a BREAKING update.")
    lines.append("Steps: finish running work and stop Mentis, back up the Brain, migrate it, "
                 "switch, check health.")
    if p["problems"]:
        lines.append("Cannot update:")
        lines += [f"  - {x}" for x in p["problems"]]
    return "\n".join(lines)


# -- the steps ------------------------------------------------------------------

def _step_stopped(inst: Install, j: dict, say) -> None:
    if _serving(inst, j["from"]["release"]):
        if _damage(inst.releases / j["from"]["release"]):
            # its files are damaged, so what its API says is not waited on
            say("the release running now is damaged; stopping it without asking it "
                "about running work")
        else:
            say("finishing running work before stopping Mentis")
            _drain(inst, j["drain_wait_s"], say)
    got = _stop_all(inst, j["brain"])["stopped"]
    say(f"Mentis stopped {got}" if got else "Mentis was not running")


def _step_backed_up(inst: Install, j: dict, say) -> None:
    got = _run_release(inst, j["runner"], "-m", "mentis.brain", "backup", j["brain"])
    if got.returncode:
        raise StepFailed(f"the Brain could not be backed up: {(got.stderr or got.stdout)[-1000:]}")
    backup = json.loads(got.stdout)["backup"]
    checked = _run_release(inst, j["runner"], "-m", "mentis.brain", "verify-backup", backup,
                           "--brain", j["brain"])
    if checked.returncode:
        raise StepFailed(f"the backup is not usable: {checked.stdout[-1000:]}")
    j["backup"] = backup
    say(f"Brain backed up to {backup} (checked usable)")


def _step_migrated(inst: Install, j: dict, say) -> None:
    _at("before:C1")
    if j["migrations"]:
        args = ["-m", "mentis.migrate", j["brain"], "--apply"]
        if j.get("allow_breaking"):
            args.append("--allow-breaking")
        got = _run_release(inst, j["to"]["release"], *args)
        if got.returncode:
            raise StepFailed("the migration did not apply and was rolled back: "
                             + (got.stderr or got.stdout)[-2000:])
    _at("after:C1")
    facts = _brain_facts(j["brain"])
    if j["migrations"] and facts["version"] != j["to"]["schema_target"]:
        raise StepFailed(f"after migrating, the Brain is at version {facts['version']}, "
                         f"not {j['to']['schema_target']}")
    say(f"Brain migrated: {', '.join(j['migrations'])}" if j["migrations"]
        else "no Brain migration needed")


def _step_switched(inst: Install, j: dict, say) -> None:
    # never switch to a release that is not whole: it may have changed since
    why = _damage(inst.releases / j["to"]["release"])
    if why:
        raise StepFailed(f"{j['to']['release']} is not whole, so it was not switched to: {why}")
    _at("before:C2")
    inst.point(j["to"]["release"], j["from"]["release"])
    _at("after:C2")
    say(f"switched to {j['to']['release']}")


def _step_healthy(inst: Install, j: dict, say) -> None:
    name = j["to"]["release"]
    who = _serving(inst, name)
    rel = (who or {}).get("release") or {}
    if rel.get("commit") != j["to"]["commit"]:
        _stop_all(inst, j["brain"])
        _verify_brain(inst, j, name, say)
        say(f"starting {name}")
        _start(inst, name)
        _at("started")
    wrong = _health(inst, name)
    if wrong:
        raise StepFailed(f"{name} is not healthy: " + "; ".join(wrong)[:1500])
    say(f"{name} is healthy")


_STEPS = {STOPPED: _step_stopped, BACKED_UP: _step_backed_up, MIGRATED: _step_migrated,
          SWITCHED: _step_switched, HEALTHY: _step_healthy}


def _drive(inst: Install, j: dict, say) -> tuple[int, dict]:
    """Every step after the journal's state; on failure, recover. Only a kill leaves
    the journal behind."""
    while True:
        nxt = STATES[STATES.index(j["state"]) + 1]
        if nxt == COMMITTED:
            _save(inst, j, COMMITTED)
            _finish(inst, j, COMMITTED)
            msg = f"Mentis is now {j['to']['release']}"
            say(msg)
            return EXIT_DONE, _doc(inst, "committed", msg, j)
        try:
            _STEPS[nxt](inst, j, say)
        except Exception as exc:                              # noqa: BLE001
            say(f"step {nxt} failed: {type(exc).__name__}: {exc}")
            return _recover_failure(inst, j, str(exc), say)
        _save(inst, j, nxt)


# -- recovery -------------------------------------------------------------------

def _doc(inst: Install, reason: str, message: str, j: dict | None = None,
         previous_restored: bool = False) -> dict:
    with contextlib.suppress(Exception):
        running = _serving_name(inst)
        return {"reason": reason, "message": message, "running": running,
                "previous_restored": previous_restored, "update": (j or {}).get("id")}
    return {"reason": reason, "message": message, "running": None,
            "previous_restored": previous_restored, "update": (j or {}).get("id")}


def _migrated(j: dict, facts: dict) -> bool:
    """Whether C1 happened: the ledger says, or with no migration, the journal."""
    if j["migrations"]:
        return facts.get("version") == j["to"]["schema_target"]
    return j["state"] not in STATES or STATES.index(j["state"]) >= STATES.index(MIGRATED)


def _switched(inst: Install, j: dict) -> bool:
    return inst.current() == j["to"]["release"]


def _attention(inst: Install, j: dict, why: str, say) -> tuple[int, dict]:
    runner = inst.releases / j["from"]["release"]
    py = runner / "runtime" / "python.exe"
    backup = j.get("backup")
    cmd = (f'"{py}" -I -m mentis.brain restore-plan "{j["brain"]}" "{backup}"' if backup else None)
    doc = {"format": FORMAT, "at": time.time(), "update": j["id"], "why": why, "brain": j["brain"],
           "backup": backup, "releases": {"from": j["from"]["release"], "to": j["to"]["release"]},
           "nothing_deleted": True, "restore_plan_command": cmd,
           "what_to_do": [
               "Nothing was restored and nothing was deleted: the Brain, the backup taken "
               "before the update and both releases are all still here.",
               f"Look at the server log under {inst.logs}.",
               (f"To see what restoring the backup would do (it changes nothing): {cmd}"
                if cmd else "No backup was taken."),
               "After acting, run `mentis.cmd update --resume` to check again."]}
    _write(_attention_path(inst), doc)
    j["needs_attention"] = why
    _save(inst, j, NEEDS_ATTENTION)
    say(f"NEEDS ATTENTION: {why}")
    for line in doc["what_to_do"]:
        say("  " + line)
    return EXIT_ATTENTION, _doc(inst, "needs_attention", f"The update stopped and needs a decision: {why}", j)


def _abort(inst: Install, j: dict, why: str, say) -> tuple[int, dict]:
    """Before C1: the Brain is as it was. Discard what this update staged, restart the
    old release if it was running."""
    name, old = j["to"]["release"], j["from"]["release"]
    rel = inst.releases / name
    may_migrate = j["state"] not in STATES or STATES.index(j["state"]) >= STATES.index(BACKED_UP)
    if may_migrate and _held_by_other(inst, j):
        say(f"the Brain is still open, so {name} was kept: {STILL_OPEN}")
    elif _running_from(rel):
        # Windows refuses to delete what it has loaded. It is whole and locked; whoever
        # started this removes it when it can, and the next commit does in any case.
        say(f"kept the staged release {name}: this update runs from it")
    elif rel.exists() and j.get("made_release") and name not in (inst.current(), inst.previous()):
        try:
            _discard(rel)
            say(f"discarded the staged release {name}")
        except OSError as exc:
            say(f"the staged release {name} could not be removed ({exc}); it is not used")
    damage = _damage(inst.releases / old)
    restored = False
    if damage:
        say(f"{old} is damaged ({json.dumps(damage)[:600]}), so it was not started again. "
            "Updating again replaces it; so does running its own setup exe over this folder")
    elif j.get("running_before"):
        try:
            if _serving(inst, old) is None:
                _start(inst, old)
                say(f"restarted {old}")
            wrong = _health(inst, old)
            if wrong:
                raise StepFailed("; ".join(wrong))
            restored = True
        except StepFailed as exc:
            return _attention(inst, j, f"the update was undone (the Brain was not changed), but "
                              f"{old} did not start again: {exc}", say)
    else:
        restored = True         # it was not running before, and is left so: its files verified
    j["why"] = why
    _finish(inst, j, ABORTED)
    msg = (f"the update did not happen; {old} is unchanged and the Brain was not changed"
           + ("" if restored else f", but {old} is not running and healthy"))
    say(msg)
    return EXIT_FAILED, _doc(inst, "aborted", f"{msg}. Why: {why}", j, restored)


def _switch_back(inst: Install, j: dict, why: str, say) -> tuple[int, dict]:
    if j["state"] != ROLLING_BACK:
        j["why"] = why
        _save(inst, j, ROLLING_BACK)
    name = j["from"]["release"]
    try:
        damage = _damage(inst.releases / name)
        if damage:
            raise StepFailed(f"{name} is damaged, so it was not switched back to: {json.dumps(damage)[:800]}")
        _stop_all(inst, j["brain"])
        _at("rollingback:stopped")
        inst.point(j["before"]["current"], j["before"]["previous"])
        _at("rollingback:pointed")
        _verify_brain(inst, j, name, say)
        _start(inst, name)
        _at("rollingback:started")
        wrong = _health(inst, name)
        if wrong:
            raise StepFailed(f"the old release is not healthy either: {'; '.join(wrong)[:1500]}")
        damage = _damage(inst.releases / name)
        if damage:
            raise StepFailed(f"{name} answered, but its files are damaged: {json.dumps(damage)[:800]}")
    except Exception as exc:                                  # noqa: BLE001
        with contextlib.suppress(Exception):
            _stop_all(inst, j["brain"])
        return _attention(inst, j, f"switching back to {name} failed: {exc} (after: {j.get('why')})", say)
    _finish(inst, j, ROLLED_BACK)
    msg = (f"switched back to {name}: it is running and healthy, and no records were lost. "
           f"{j['to']['release']} is kept but not used.")
    say(msg)
    return EXIT_FAILED, _doc(inst, "rolled_back", f"The update did not take: {j.get('why')}. {msg}", j, True)


def _from_can_read(j: dict, facts: dict) -> bool:
    """A release too damaged to say what it reads cannot be said to read it."""
    target = j["from"]["schema_target"]
    return target is not None and can_read(int(target), facts)


def _recover_failure(inst: Install, j: dict, why: str, say) -> tuple[int, dict]:
    facts = _brain_facts(j["brain"])
    if _switched(inst, j) or _migrated(j, facts):
        if _from_can_read(j, facts):
            return _switch_back(inst, j, why, say)
        with contextlib.suppress(Exception):
            _stop_all(inst, j["brain"])
        return _attention(inst, j, f"{j['to']['release']} is not healthy and {j['from']['release']} "
                          f"cannot open the Brain at schema version {facts.get('version')}: {why}", say)
    return _abort(inst, j, why, say)


def _retry_attention(inst: Install, j: dict, facts: dict, say) -> tuple[int, dict] | None:
    """Resumed with nothing serving the Brain: try the way out again, now that a release
    may be whole again or the Brain restored. None when neither can be tried."""
    new_whole = not _damage(inst.releases / j["to"]["release"])
    old_whole = not _damage(inst.releases / j["from"]["release"])
    forward = _switched(inst, j) or _migrated(j, facts)
    _await_openers(inst, j, say)
    if forward and new_whole:
        say(f"{j['to']['release']} is whole; trying it again")
        j.pop("needs_attention", None)
        _save(inst, j, SWITCHED if _switched(inst, j) else MIGRATED)
        return _drive(inst, j, say)
    if old_whole and (not forward or _from_can_read(j, facts)):
        say(f"{j['from']['release']} is whole; going back to it")
        j.pop("needs_attention", None)
        if forward:
            return _switch_back(inst, j, j.get("why") or "needed attention", say)
        return _abort(inst, j, j.get("why") or "needed attention", say)
    return None


def _recover(inst: Install, j: dict, say) -> tuple[int, dict]:
    state = j["state"]
    say(f"resuming update {j['id']} ({j['from']['release']} -> {j['to']['release']}), "
        f"last recorded state {state}")
    if state == COMMITTED:
        _finish(inst, j, COMMITTED)
        return EXIT_DONE, _doc(inst, "committed", f"Mentis is now {j['to']['release']}", j)
    if state == NEEDS_ATTENTION:
        cur = inst.current()
        facts = _brain_facts(j["brain"])
        build = _build_of(inst.releases / cur) if cur else None
        who = _serving(inst, cur) if cur else None
        if build and who and can_read(int(build.get("schema_target", 0)), facts) \
                and not _damage(inst.releases / cur) and not _health(inst, cur):
            _finish(inst, j, f"RESOLVED ({cur} healthy)")
            return EXIT_DONE, _doc(inst, "resolved", f"resolved: {cur} is running and healthy", j,
                                   cur == j["from"]["release"])
        if who is None:
            retry = _retry_attention(inst, j, facts, say)
            if retry is not None:
                return retry
        say(f"still needs attention: {j.get('needs_attention')}")
        say(f"see {_attention_path(inst)}")
        return EXIT_ATTENTION, _doc(inst, "needs_attention", f"Still needs a decision: {j.get('needs_attention')}. "
                                    f"See {_attention_path(inst)}", j)
    _await_openers(inst, j, say)
    if state == ROLLING_BACK:
        return _switch_back(inst, j, j.get("why") or "interrupted", say)
    facts = _brain_facts(j["brain"])
    if _switched(inst, j):
        if STATES.index(state) < STATES.index(SWITCHED):
            _save(inst, j, SWITCHED)
        return _drive(inst, j, say)
    if _migrated(j, facts):
        say("the Brain was already migrated (commit point C1 passed); continuing forward")
        if state != MIGRATED:
            _save(inst, j, MIGRATED)
        try:
            _stop_all(inst, j["brain"])
        except StepFailed as exc:
            return _recover_failure(inst, j, str(exc), say)
        return _drive(inst, j, say)
    return _abort(inst, j, f"interrupted at {state}, before the Brain was migrated", say)


def recover(inst: Install) -> tuple[int, dict]:
    say = _sayer(inst)
    try:
        with _update_lock(inst):
            j = journal(inst)
            if j is None:
                return EXIT_DONE, _doc(inst, "nothing_to_resume", "There is no unfinished update.")
            return _recover(inst, j, say)
    except Refused as exc:
        return EXIT_REFUSED, _doc(inst, "refused", f"Not resumed: {exc}")


def _resumer(inst: Install, j: dict) -> str | None:
    """Whose launcher finishes it: the one that began it, if whole, else the other."""
    others = [j.get("runner"), j["to"]["release"], j["from"]["release"]]
    return next((n for n in others if n and not _damage(inst.releases / n)), None)


def _resume(inst: Install) -> tuple[int, dict]:
    j = journal(inst)
    if j is None:
        return recover(inst)
    if j.get("format") != FORMAT:
        return EXIT_REFUSED, _doc(inst, "refused", f"this release does not know journal format "
                                  f"{j.get('format')}: run the setup exe of a newer build")
    who = _resumer(inst, j)
    if who is None:
        return EXIT_ATTENTION, _doc(
            inst, "needs_attention",
            f"neither release the unfinished update names ({j['to']['release']}, "
            f"{j['from']['release']}) is whole, so it cannot be finished from here. Nothing was "
            "deleted. Running the setup exe of either over this folder makes it whole; then "
            "`mentis.cmd update --resume`", j)
    if who == inst.release:
        return recover(inst)
    r = _launch(inst, who, "update", "--resume")
    print(r.stderr, end="", file=sys.stderr, flush=True)
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        return EXIT_FAILED, _doc(inst, "crashed", f"the resume ended with exit {r.returncode} and gave no result", j)
    return _undo_staged(inst, j["to"]["release"], bool(j.get("made_release")), r.returncode, doc)


def before_start(inst: Install) -> int | None:
    """`start` and `open`: an unfinished update first. None to carry on; else an exit."""
    if journal(inst) is None:
        return None
    code, doc = _resume(inst)
    print(doc.get("message", ""), file=sys.stderr, flush=True)
    if code in (EXIT_REFUSED, EXIT_ATTENTION):
        return code
    cur = inst.current()
    if cur and cur != inst.release:         # it finished forward: the new release's manifest
        r = _launch(inst, cur, *sys.argv[1:])
        print(r.stdout, end="", flush=True)
        print(r.stderr, end="", file=sys.stderr, flush=True)
        return r.returncode
    return None


def status(inst: Install) -> dict:
    j = journal(inst)
    return {"unfinished_update": j and {"id": j["id"], "kind": j.get("kind"), "state": j["state"],
                                        "from": j["from"]["release"], "to": j["to"]["release"]},
            "needs_attention": _read(_attention_path(inst))}


# -- the transaction, from its plan ---------------------------------------------

def _confirmed(a, question: str = "Proceed?") -> bool:
    if getattr(a, "yes", False):
        return True
    if sys.stdin is None or not sys.stdin.isatty():
        return False
    # To stderr: stdout is the one JSON answer, and Windows calls NUL a terminal too.
    print(question + " [y/N] ", end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def transact(inst: Install, a, to_name: str, *, kind: str, made: bool) -> tuple[int, dict]:
    say = _sayer(inst)
    to = _build_of(inst.releases / to_name)
    if not to:
        raise Refused(f"{to_name} has no BUILD.json")
    with _update_lock(inst):
        if journal(inst) is not None:
            raise Refused("an update is unfinished; run `mentis.cmd update --resume` first")
        p = plan(inst, to)
        if kind == "rollback":
            say(f"Going back: {p['from']['release']} -> {to_name}")
        else:
            say(describe(p))
        if not p["ok"]:
            raise Refused("; ".join(p["problems"]))
        if not _confirmed(a):
            raise Refused("not confirmed (say --yes where nobody can be asked); nothing was changed")
        why = _damage(inst.releases / to_name)
        if why:
            raise Refused(f"{to_name} is not whole, so it was not switched to: {json.dumps(why)[:600]}")
        j = {"format": FORMAT, "id": f"upd-{uuid.uuid4().hex[:12]}", "kind": kind,
             "runner": inst.release, "brain": p["brain"], "from": p["from"], "to": p["to"],
             "migrations": p["migrations"], "allow_breaking": p["breaking"],
             "rollback_possible": p["rollback_possible"], "brain_before": p["brain_before"],
             "before": {"current": inst.current(), "previous": inst.previous()},
             "running_before": bool(_serving(inst, p["from"]["release"])),
             "made_release": made, "backup": None, "history": [], "started_at": time.time(),
             "drain_wait_s": getattr(a, "drain_wait", None) or DRAIN_WAIT_S}
        _save(inst, j, APPROVED)
        return _drive(inst, j, say)


def _rollback(inst: Install, a) -> tuple[int, dict]:
    prev = inst.previous()
    if not prev:
        raise Refused("there is no previous release to go back to")
    home = inst.releases / prev
    if not home.is_dir():
        raise Refused(f"{home} is no longer here")
    why = _damage(home)
    if why:
        raise Refused(f"{prev} is damaged ({json.dumps(why)[:400]}), so Mentis did not go back to it "
                      "and nothing was changed. Running its own setup exe over this folder puts it "
                      "back and switches to it")
    build = _build_of(home) or {}
    facts = _brain_facts((inst.state() or {}).get("brain") or "")
    if inst.state() and not can_read(int(build.get("schema_target", 0)), facts):
        raise Refused(f"{prev} reads Brain schema up to {build.get('schema_target')}, and this Brain "
                      f"is at version {facts.get('version')} and needs a reader of at least "
                      f"{facts.get('min_reader')}. Going back would start old code on a Brain it cannot "
                      "read, so nothing was changed. A restore from a backup is never automatic: "
                      "`python -m mentis.brain restore-plan <brain> <backup>` says what one would do")
    if not inst.state():
        inst.point(prev, inst.current())
        return EXIT_DONE, _doc(inst, "switched", f"Mentis is now {prev}; nothing is set up yet")
    return transact(inst, a, prev, kind="rollback", made=False)


def _stage_and_hand_over(inst: Install, a) -> tuple[int, dict | None]:
    """`mentis.cmd update <package>`, in the running release's launcher: checked and
    placed beside it, then the rest in the new release's own."""
    say = _sayer(inst)
    package = pathlib.Path(a.package).resolve()
    if not package.is_file():
        raise Refused(f"no such file: {package}")
    with _update_lock(inst):
        if journal(inst) is not None:
            raise Refused("an update is unfinished; run `mentis.cmd update --resume` first")
        _clear_incoming(inst)
        inst.releases.mkdir(parents=True, exist_ok=True)
        incoming = inst.releases / f".incoming-{os.getpid()}"
        try:
            _unpack(package, incoming)
            build = _build_of(incoming)
            if not build:
                raise Refused(f"{package} holds no BUILD.json")
            name = name_of(build)
            if name == inst.current():
                raise Refused(f"{name} is already the current release; nothing to update")
            say(f"{package.name} is {name}; checking every file and that it runs")
            _at("stage:unpacked")
            try:
                made = place(inst, incoming, build, move=True)
            except Refused as exc:
                raise Refused(f"{package.name} was refused: {exc}") from None
            _at("stage:placed")
        finally:
            with contextlib.suppress(OSError):
                _discard(incoming)
    if inst.state() is None:
        inst.point(name, inst.current())
        return EXIT_DONE, _doc(inst, "switched", f"Mentis is now {name}; nothing is set up yet")
    args = ["update", "--staged-here", "--yes"] + (["--made"] if made else [])
    if getattr(a, "drain_wait", None):
        args += ["--drain-wait", str(a.drain_wait)]
    if not a.yes:
        # the plan is the new release's to say, on this console
        said = _launch(inst, name, "update", "--plan-only")
        print(said.stderr, end="", file=sys.stderr, flush=True)
        if said.returncode:
            problems = json.loads(said.stdout).get("message")
            return _undo_staged(inst, name, made, EXIT_REFUSED, _doc(
                inst, "refused", f"{problems}. Nothing was changed."))
        if not _confirmed(a):
            return _undo_staged(inst, name, made, EXIT_REFUSED, _doc(
                inst, "not_confirmed", "Not confirmed (say --yes where nobody can be asked). "
                "Nothing was changed."))
    return _hand_over(inst, name, made, args)


def _hand_over(inst: Install, name: str, made: bool, args: list) -> tuple[int, dict | None]:
    r = _launch(inst, name, *args)
    print(r.stderr, end="", file=sys.stderr, flush=True)
    if r.returncode not in OUTCOME:
        return EXIT_FAILED, _doc(
            inst, "interrupted",
            f"the update stopped part-way (exit {r.returncode}). `mentis.cmd update --resume` finishes "
            "or undoes it; `mentis.cmd start` does that first too.")
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = _doc(inst, "crashed", f"the update ended with exit {r.returncode} and gave no result")
    return _undo_staged(inst, name, made, r.returncode, doc)


def _undo_staged(inst: Install, name: str, made: bool, code: int, doc: dict) -> tuple[int, dict]:
    """The new release could not delete itself: this launcher, outside it, can. Not
    after a switch back, which says it is kept: it ran, and its log is about it."""
    if code and made and doc.get("reason") != "rolled_back" and journal(inst) is None \
            and name not in (inst.current(), inst.previous()):
        with contextlib.suppress(OSError):
            _discard(inst.releases / name)
    return code, doc


def arrive(inst: Install, a) -> tuple[int, dict]:
    """The setup exe, from `.incoming`, over this folder: a first install, the same
    build over itself, or an update. Needs nothing of what is already here to work."""
    src = pathlib.Path(launcher.__file__).resolve().parents[1]
    build = _build_of(src)
    name = name_of(build)
    inst = Install(a.root, name)
    inst.python = sys.executable                # the Ctrl-C helper; the release may be away
    cur = inst.current()
    j = journal(inst)
    if a.plan:
        if j:
            said = "An update did not finish; this finishes or undoes it."
        elif cur and cur != name and inst.state():
            said = describe(plan(inst, build))
        elif cur == name:
            said = f"{name} is already installed; it is stopped, and a damaged copy is replaced and kept aside."
        else:
            said = ""
        return EXIT_DONE, {"message": said}
    inst.state_dir.mkdir(parents=True, exist_ok=True)
    inst.releases.mkdir(parents=True, exist_ok=True)
    if j:
        names = (j["to"]["release"], j["from"]["release"])
        if name in names and _damage(inst.home):
            with _update_lock(inst):
                place(inst, src, build, move=False)
        return _resume(inst)
    if cur == name:
        launcher.stop(inst)
        with _update_lock(inst):
            place(inst, src, build, move=False)
        return EXIT_DONE, {"message": f"{name} was installed again over itself, and is stopped"}
    with _update_lock(inst):
        made = place(inst, src, build, move=False)
    if not cur or not inst.state():
        inst.point(name, cur)
        return EXIT_DONE, {"message": f"Mentis {name} is installed"}
    return _hand_over(inst, name, made, ["update", "--staged-here", "--yes"] + (["--made"] if made else []))


def command(inst: Install, a) -> int:
    """`update`, `rollback` and `arrive`: one JSON object on stdout, whatever happened."""
    try:
        if a.command == "arrive":
            code, doc = arrive(inst, a)
        elif a.command == "rollback":
            code, doc = _rollback(inst, a)
        elif a.resume:
            code, doc = _resume(inst)
        elif a.plan_only:
            p = plan(inst, inst.build())
            print(describe(p), file=sys.stderr, flush=True)
            code, doc = (EXIT_DONE if p["ok"] else EXIT_REFUSED), {"message": "; ".join(p["problems"])}
        elif a.staged_here:
            code, doc = transact(inst, a, inst.release, kind="update", made=a.made)
        elif a.package:
            code, doc = _stage_and_hand_over(inst, a)
        else:
            raise Refused("name a Mentis-Setup-....exe, or --resume")
    except Refused as exc:
        # `running` says what it is still running on: nothing was touched
        code, doc = EXIT_REFUSED, _doc(inst, "refused", f"{exc}")
    except Exception as exc:                                  # noqa: BLE001
        code, doc = EXIT_FAILED, _doc(inst, "crashed", f"{type(exc).__name__}: {exc}. `mentis.cmd update "
                                      "--resume` finishes or undoes whatever it left; `mentis.cmd start` "
                                      "does that first too.")
    if a.command == "arrive":
        print(doc.get("message", ""))       # words, for the wizard to show
    else:
        print(json.dumps({"outcome": OUTCOME.get(code, "failed"), **doc}, indent=1, default=str))
    return code
