"""`mentis <command>`: what the launcher runs, from the current release.

    mentis status [--json]
    mentis start [--json] [--progress jsonl]
    mentis stop [--json] [--progress jsonl]
    mentis update ...          -> mentis.updater.main(argv)
    mentis rollback ...        -> mentis.updater.main(argv)
    mentis releases ...        -> mentis.releases.main(argv)
    mentis brain ...           -> python -m mentis.brain ...
    mentis backups ...         -> python -m mentis.backups ...
    mentis migrate ...         -> python -m mentis.migrate ...

The install root is `MENTIS_HOME`, which the launcher sets to its own root,
else this OS's default (`mentis.home`).

DISPATCH (frozen). `update` and `rollback` hand the WHOLE argv, command word
first (`["update", "pkg.zip", "--yes"]`, `["rollback"]`), to
`mentis.updater.main(argv)`, and `releases` hands its whole argv
(`["releases", "list"]`) to `mentis.releases.main(argv)`; each returns the
exit status. A release without those modules says so and exits 2.

START RECOVERS FIRST. When an update is unfinished (`state/update.journal
.json` exists), `mentis start` runs `mentis update --resume` instead of
starting anything: recovery decides which release runs. While a decision is
waiting (`state/needs-attention.json`), start refuses and shows it.

START CHECKS THE FILES (S7). Before it starts or reports anything, `mentis
start` re-hashes the current release against its RELEASE.json
(`installer.release_problems`), and the launcher in `bin/` against what
install writes for it (`installer.launcher_problems`, D16): a missing,
changed or extra file means "Mentis's files are damaged; reinstall", exit 3,
and nothing is started -- never "healthy". A server already running is left
as it is. `status` makes the same checks.

FOR A PROGRAM (S8; installer plan adm-06dbd34701bf, frozen: the desktop app
and the uninstaller call these). `status --json`, `start --json` and `stop
--json` ask nothing and print exactly one JSON object on stdout, whatever
happens -- an unexpected exception included; the words go to stderr.
`--progress jsonl` on start and stop adds `mentis.progress` lines (steps:
files, start, health; stop) before it, the object then being one line.
Every object carries "outcome", "reason" and "message", and the exit status
is the outcome's (shared interface I1/I2, `mentis.progress`): 0 ok, 1 only
running but not healthy, 2 refused, 3 failed, 4 needs attention.

  status  {"installed": bool, "root", "install", "release", "brain",
           "server", "journal", "damaged": bool (every file of the current
           release hashed), "problems", "needs_attention": bool,
           "attention" (the decision's document, or null), "update_pending":
           {"id", "kind", "state", "from", "to"} | null}; exit 0 whenever it
           could tell (nothing installed included), 3 when it could not.
  start   {"ok", "started", "already_running", "damaged", "problems",
           "port", "url", "release", "health", "error"}; exit 0 healthy, 1
           running but unhealthy, 2 refused, 3 damaged or failed, 4 a
           decision is waiting (or a resumed update stopped at one).
  stop    {"ok", "installed", "was_running", "stopped", "how", "why",
           "port", "error"}; exit 0 stopped or not running (or nothing
           installed), 2 refused, 3 failed or not stopped.
"""

from __future__ import annotations

import importlib
import json
import sys

from mentis import home, install_state, progress

USAGE = __doc__.split("\n\n")[1]


def _optional(module: str):
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name != module:
            raise
        return None


def _delegate(module: str, argv: list) -> int:
    mod = _optional(module)
    if mod is None:
        print(f"mentis {argv[0]}: this release does not carry {module}",
              file=sys.stderr)
        return 2
    return int(mod.main(argv) or 0)


def _attention(lay: home.Layout) -> dict | None:
    try:
        return install_state.read_json(lay.needs_attention)
    except install_state.InstallStateError as exc:
        return {"unreadable": str(exc)}


def _pending(journal) -> dict | None:
    """I7: the unfinished update in a few fields, or None."""
    if not isinstance(journal, dict):
        return None
    if "unreadable" in journal:
        return {"unreadable": journal["unreadable"]}
    return {"id": journal.get("id"), "kind": journal.get("kind"),
            "state": journal.get("state"),
            "from": (journal.get("from") or {}).get("release"),
            "to": (journal.get("to") or {}).get("release")}


def status(lay: home.Layout, as_json: bool) -> int:
    from mentis import installer, servers
    st = install_state.load(lay, required=False)
    attention = _attention(lay)
    if st is None:
        if as_json:
            _json(progress.outcome_doc(
                progress.OK, "not_installed",
                f"Nothing is installed at {lay.root}.",
                installed=False, root=str(lay.root), install=None,
                release=None, brain=None, server=None, journal=None,
                damaged=False, problems=[],
                needs_attention=attention is not None, attention=attention,
                update_pending=None))
        else:
            print(f"Nothing is installed at {lay.root}.")
        return 0
    rel_dir = lay.release(st["current"])
    try:
        rel = home.release(rel_dir)
    except (OSError, ValueError) as exc:
        rel = {"error": str(exc)}
    out = {"installed": True, "root": str(lay.root), "install": st,
           "release": rel,
           "brain": None, "server": None,
           "journal": None, "damaged": False, "problems": [],
           "needs_attention": attention is not None, "attention": attention,
           "update_pending": None}
    # I7: a full hash check of the current release, as `mentis start` makes
    try:
        why = (installer.release_problems(rel_dir)
               + installer.launcher_problems(lay, st["current"]))
    except Exception as exc:                                  # noqa: BLE001
        why = [{"problem": "unverifiable",
                "detail": f"{type(exc).__name__}: {exc}"}]
    out.update(damaged=bool(why), problems=why)
    try:
        from mentis.spine import migrations
        b = migrations.status_of(st["brain"])
        out["brain"] = {"state": b.state, "version": b.version,
                        "min_reader": b.min_reader,
                        "explain": b.explain(st["brain"])}
    except Exception as exc:                                  # noqa: BLE001
        out["brain"] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        out["journal"] = install_state.read_json(lay.journal)
    except install_state.InstallStateError as exc:
        out["journal"] = {"unreadable": str(exc)}
    out["update_pending"] = _pending(out["journal"])
    who = servers.identity(st["port"], timeout=3)
    if who:
        out["server"] = {**who, "ours": installer.ours(lay, who, st["brain"]),
                         "current": installer._inside(who["code"], rel_dir)}
    if as_json:
        reason, message = "installed", f"Mentis {st['current']} is installed."
        if out["needs_attention"]:
            reason, message = "needs_attention", ("A decision is waiting "
                                                  "from an update.")
        elif out["update_pending"]:
            reason, message = "update_pending", ("An update is unfinished; "
                                                 "`mentis update --resume`.")
        elif out["damaged"]:
            reason, message = "damaged", ("Mentis's files are damaged; "
                                          "repair Mentis.")
        _json(progress.outcome_doc(progress.OK, reason, message, **out))
        return 0
    print(f"Install root: {lay.root}")
    if out["damaged"]:
        print("DAMAGED: the current release does not match what it was built "
              "with: " + json.dumps(out["problems"], default=str)[:800])
    print(f"Current release: {st['current']}"
          + (f"   (previous: {st['previous']})" if st.get("previous") else ""))
    print(f"Brain: {st['brain']}")
    b = out["brain"]
    print("  " + (b.get("explain") or b.get("error", "")))
    if who:
        print(f"Server: running on http://127.0.0.1:{st['port']} (pid "
              f"{who['pid']}, release "
              f"{(who.get('release') or {}).get('version')})"
              + ("" if out["server"]["ours"] else "  -- NOT this install's"))
    else:
        print(f"Server: not running (port {st['port']})")
    if out["journal"]:
        j = out["journal"]
        print(f"Update in progress or interrupted: state {j.get('state')}. "
              "Run `mentis update --resume`.")
    if out["needs_attention"]:
        print("NEEDS ATTENTION: " + json.dumps(out["attention"], indent=1))
    return 0


def _json(doc) -> None:
    progress.result(doc)


def _words(as_json: bool):
    """Where a command's words go: stdout, or stderr when stdout is for the
    one JSON object (or progress lines)."""
    quiet = as_json or progress.on()
    return lambda msg="": print(msg, file=sys.stderr if quiet else sys.stdout,
                                flush=True)


def start(lay: home.Layout, as_json: bool = False) -> int:
    # only what the file check needs is imported before it: any other
    # module may be the file that is missing
    from mentis import installer
    say = _words(as_json)
    out = {"ok": False, "started": False, "already_running": False,
           "damaged": False, "problems": [], "port": None, "url": None,
           "release": None, "health": None, "error": None}

    def done(code: int, reason: str, message: str) -> int:
        if as_json:
            _json(progress.outcome_doc(
                progress.OUTCOME_OF.get(code, progress.FAILED_OUTCOME),
                reason, message, **out))
        return code

    if lay.needs_attention.exists():
        out["error"] = "a decision is waiting"
        say("Not started: a decision is waiting.\n"
            + json.dumps(_attention(lay), indent=1))
        progress.emit("start", progress.FAILED, "A decision is waiting")
        return done(4, "needs_attention", "Not started: an update stopped and "
                    "a decision is waiting.")
    if lay.journal.exists():
        say("An update was interrupted; recovering it first "
            "(`mentis update --resume`).")
        progress.emit("recover", progress.RUNNING,
                      "Finishing an interrupted update")
        code = _delegate("mentis.updater", ["update", "--resume",
                                            *progress.argv()])
        progress.emit("recover", progress.DONE if code == 0
                      else progress.FAILED, f"Recovery ended with {code}")
        out.update(ok=code == 0, error=None if code == 0
                   else f"recovery ended with exit {code}")
        if code not in progress.OUTCOME_OF:
            code = 3
        return done(code, "resumed", "An interrupted update was resumed: "
                    + ("it is finished." if code == 0 else
                       f"it ended with exit {code}."))
    st = install_state.load(lay, required=True)
    rel = lay.release(st["current"])
    out.update(port=st["port"], url=f"http://127.0.0.1:{st['port']}",
               release=st["current"])
    progress.emit("files", progress.RUNNING, "Checking Mentis's files")
    try:
        why = (installer.release_problems(rel)
               + installer.launcher_problems(lay, st["current"]))
    except ImportError as exc:
        why = [{"problem": "unimportable", "detail": f"{exc}"}]
    try:
        from mentis import health, servers
    except ImportError as exc:
        why = why + [{"problem": "unimportable", "detail": f"{exc}"}]
    if why:
        out.update(damaged=True, problems=why,
                   error="Mentis's files are damaged; reinstall")
        say(f"Mentis's files are damaged; reinstall Mentis. Release "
            f"{st['current']} does not match what it was built with: "
            + json.dumps(why, default=str)[:1500])
        progress.emit("files", progress.FAILED,
                      "Mentis's files are damaged; reinstall")
        return done(3, "damaged", "Mentis's files are damaged; repair Mentis. "
                    "Nothing was started.")
    progress.emit("files", progress.DONE, "Every file matches")
    progress.emit("start", progress.RUNNING, "Starting Mentis")
    who = servers.identity(st["port"], timeout=3)
    if who and installer.ours(lay, who, st["brain"]):
        if not installer._inside(who["code"], rel):
            out["error"] = (f"a different release of this install is serving "
                            f"on :{st['port']} ({who['code']})")
            say(f"A different release of this install is serving on "
                f":{st['port']} ({who['code']}); run `mentis stop` first.")
            progress.emit("start", progress.FAILED, out["error"])
            return done(2, "other_release", out["error"])
        out["already_running"] = True
        say(f"Already running on http://127.0.0.1:{st['port']}.")
    else:
        try:
            who = installer.start_server(lay)
        except (installer.InstallRefused, installer.InstallFailed) as exc:
            out["error"] = str(exc)
            say(f"Not started: {exc}")
            progress.emit("start", progress.FAILED, str(exc))
            code = 2 if isinstance(exc, installer.InstallRefused) else 3
            return done(code, exc.reason, f"Not started: {exc}")
        out["started"] = True
        say(f"Started {st['current']} on http://127.0.0.1:{st['port']} "
            f"(pid {who['pid']}).")
    progress.emit("start", progress.DONE, f"Running on {out['url']}")
    progress.emit("health", progress.RUNNING, "Checking Mentis's health")
    h = health.check(lay, st["current"], st["brain"])
    out.update(ok=bool(h["ok"]), health=h)
    say(health.render(h))
    progress.emit("health", progress.DONE if h["ok"] else progress.FAILED,
                  "Mentis is healthy" if h["ok"] else "Mentis is not healthy")
    if h["ok"]:
        return done(0, "healthy", f"Mentis is running and healthy on "
                    f"{out['url']}.")
    return done(1, "unhealthy", f"Mentis is running on {out['url']} but is "
                "not healthy.")


def stop(lay: home.Layout, as_json: bool = False) -> int:
    from mentis import installer
    say = _words(as_json)
    progress.emit("stop", progress.RUNNING, "Stopping Mentis")
    if as_json and install_state.load(lay, required=False) is None:
        # the uninstaller asks this whatever is there: nothing to stop
        progress.emit("stop", progress.DONE, "Nothing is installed")
        _json(progress.outcome_doc(
            progress.OK, "not_installed", "Nothing is installed, so nothing "
            "was stopped.", ok=True, installed=False, was_running=False,
            stopped=True, how=None, why=None, port=None, error=None))
        return 0
    out = installer.stop_ours(lay)
    doc = {"ok": bool(out["stopped"]), "installed": True, **out,
           "error": None if out["stopped"] else out.get("why")}
    if not out["was_running"]:
        say("Not running.")
        code, reason, message = 0, "not_running", "Mentis was not running."
    elif out["stopped"]:
        say(f"Stopped ({out['how']}).")
        code, reason, message = 0, "stopped", f"Mentis is stopped ({out['how']})."
    else:
        print(f"Not stopped: {out['why']}", file=sys.stderr)
        code, reason, message = 3, "not_stopped", f"Not stopped: {out['why']}"
    progress.emit("stop", progress.DONE if code == 0 else progress.FAILED,
                  "Mentis is stopped" if code == 0
                  else f"Not stopped: {out['why']}")
    if as_json:
        _json(progress.outcome_doc(progress.OUTCOME_OF[code], reason, message,
                                   **doc))
    return code


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("usage:\n" + USAGE)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd in ("update", "rollback"):
        return _delegate("mentis.updater", argv)
    if cmd == "releases":
        return _delegate("mentis.releases", argv)
    if cmd == "brain":
        from mentis.brain.__main__ import main as m
        return m(rest)
    if cmd == "backups":
        from mentis.backups import main as m
        return m(rest)
    if cmd == "migrate":
        from mentis.migrate import main as m
        return m(rest)
    from mentis import installer
    as_json = "--json" in rest
    if cmd in ("start", "stop"):
        mode = None
        if "--progress" in rest:
            i = rest.index("--progress")
            mode = rest[i + 1] if i + 1 < len(rest) else None
            if mode not in progress.MODES:
                print(f"mentis {cmd}: --progress takes "
                      f"{', '.join(progress.MODES)}", file=sys.stderr)
                return 2
        progress.configure(mode)
    try:
        lay = home.Layout()
        if cmd == "status":
            return status(lay, as_json)
        if cmd == "start":
            return start(lay, as_json)
        if cmd == "stop":
            return stop(lay, as_json)
    except Exception as exc:                                  # noqa: BLE001
        # I1: refused 2, anything else 3 -- an unexpected exception
        # included -- and the final JSON is printed whatever happened
        if isinstance(exc, installer.InstallRefused):
            code, reason = 2, exc.reason
        elif isinstance(exc, installer.InstallFailed):
            code, reason = 3, exc.reason
        elif isinstance(exc, install_state.InstallStateError):
            code, reason = 3, "install_state_invalid"
        else:
            code, reason = 3, "unexpected"
        message = (str(exc) if reason != "unexpected"
                   else f"{type(exc).__name__}: {exc}")
        progress.fail(message, cmd)
        print(f"mentis {cmd}: {message}", file=sys.stderr)
        if reason == "unexpected":
            import traceback
            traceback.print_exc(file=sys.stderr)
        if as_json:
            _json(progress.outcome_doc(progress.OUTCOME_OF[code], reason,
                                       message, ok=False, error=message,
                                       exit=code))
        return code
    print(f"mentis: unknown command {cmd!r}\nusage:\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    progress.utf8_streams()
    sys.exit(main())
