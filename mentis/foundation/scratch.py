"""Private execution scratch: one directory per execution, and only its own.

WHAT THIS IS FOR. A dispatched run used to work in the server's one workspace,
so every run -- whatever it was carrying, whoever it was -- could open every
file any other run had left there. Artifact custody then held only because a
worker was told to delete what it had returned (S6 on `artifacts/custody`,
51f8406). That is an instruction, not a boundary. This makes it a boundary:

  * each EXECUTION gets its own directory, and it is that run's working
    directory. Nothing else is started in it.
  * it lives as long as the execution's session can be continued -- a Claude
    session resumes only from the directory it was recorded in, so a scratch
    that changed between runs of the same session would end its continuity.
  * it goes when Mentis relinquishes the session (`release`), and a sweep at
    start removes any that the record says were relinquished, or that no
    record names at all, which is what a crash leaves.

WHAT CROSSES BETWEEN EXECUTIONS IS CUSTODY, NOT A PATH. A later run receives an
explicitly granted artifact (`read_artifact`), landed in ITS OWN scratch.

WHAT THIS IS NOT. It is not the project. A run that needs the repository is
given it as well, as a separately named directory; that is intentional access
to a project, and it is not private to anybody. Nor is it a Participant's
storage: an execution is a session, and a new session is a new scratch.

ONE PLACE. Every scratch is `<corpus>/scratch/<execution>`, beside the instance
corpus that already lives there -- never %TEMP% and never the project. So
everything here belongs to this corpus, which is what makes an orphan
recognisable as one rather than possibly somebody else's.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import time

DIR = "scratch"
MARK = ".mentis-scratch.json"
_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def root(record: str) -> pathlib.Path:
    return pathlib.Path(record) / DIR


def path_for(record: str, execution: str) -> pathlib.Path:
    """Where this execution's scratch is. Computed, so every layer that needs
    it -- Foundation, dispatch, the sweep -- names the same directory."""
    if not execution or not _SAFE.match(execution) or execution in (".", ".."):
        raise ValueError(f"{execution!r} cannot name a scratch directory")
    return root(record) / execution


def provision(record: str, execution: str, *, participant=None,
              runtime=None) -> str:
    """This execution's scratch, made if it is not there. Returns its path.

    The marker says what owns the directory and why it exists, so a reader
    -- or the sweep -- never has to infer it from a name.
    """
    p = path_for(record, execution)
    p.mkdir(parents=True, exist_ok=True)
    mark = p / MARK
    if not mark.exists():
        mark.write_text(json.dumps({
            "execution": execution, "participant": participant,
            "runtime": runtime, "created_at": time.time(),
            "why": "private scratch for this execution; discarded when its "
                   "session is relinquished. Anything that must outlive it "
                   "is returned into Mentis custody."}, indent=1),
            encoding="utf-8")
    return str(p)


def present(record: str) -> list[str]:
    """The executions that have a scratch here, by the marker they carry."""
    r = root(record)
    if not r.is_dir():
        return []
    return sorted(d.name for d in r.iterdir()
                  if d.is_dir() and (d / MARK).is_file())


def unmarked(record: str) -> list[str]:
    """Directories under the root that Mentis did not provision. Reported,
    never removed: nothing here says whose they are."""
    r = root(record)
    if not r.is_dir():
        return []
    return sorted(str(d) for d in r.iterdir()
                  if not (d.is_dir() and (d / MARK).is_file()))


def discard(record: str, execution: str) -> str:
    """Remove one execution's scratch. Says what happened; never raises."""
    try:
        p = path_for(record, execution)
    except ValueError as exc:
        return f"not removed: {exc}"
    if not p.exists():
        return "already gone"
    if not (p / MARK).is_file():
        return "left alone: not a scratch Mentis provisioned"
    try:
        shutil.rmtree(p)
    except OSError as exc:
        # Said, not swallowed. A runtime whose sandbox owns the files it
        # wrote (Codex, ent-c25b58e0125f) can leave a scratch this process
        # may not delete; the sweep reports it every time until it can.
        return f"could not be removed: {exc}"
    return "removed"


#: The Mentis operations that reach the web, as the grant names them.
WEB_OPERATIONS = ("web_search", "web_fetch")


def web_note(permits) -> str:
    """What a run is told about the web, from the operations it may perform.

    SAID EITHER WAY. A run with no web tool is told so plainly, so that it
    says so too -- rather than, as a local model did while making no tool
    call at all, blaming "security settings" it never met."""
    given = [op for op in WEB_OPERATIONS if op in set(permits or ())]
    if given:
        return ("Web access: use the Mentis tools "
                + " and ".join(given) + ". They are recorded. This "
                "runtime's own web tools are withheld.")
    return ("Web access: this run has none. The Mentis tools "
            + " and ".join(WEB_OPERATIONS) + " are not granted to it, and "
            "this runtime's own web tools are withheld. If the work needs "
            "the web, say that this run has no web access.")


def note(scratch: str, project: str | None, *, project_writable=True,
         permits=None) -> str:
    """What a run is told about where it is working, and -- given its
    `permits` -- whether it can reach the web. Facts, no policy."""
    lines = [f"Your working directory is {scratch}. It is private to this "
             "execution: no other run can see it, and it is discarded when "
             "this session ends. Anything that must outlive it -- or that "
             "another piece of work needs -- goes into Mentis with "
             "`return_artifact`; a path is never a handoff."]
    if project and os.path.normcase(project) != os.path.normcase(scratch):
        # A PUBLISHED RELEASE (tools/release.py) is denied every write, so a
        # run is told so rather than that it may change it.
        release = os.path.isfile(os.path.join(project, ".git",
                                              "release.json"))
        lines.append(
            f"The project workspace is {project}. It is not your private "
            "scratch; "
            + ("it is the published release this Mentis runs: readable, "
               "and NOT writable." if release else
               "you may read and change it." if project_writable else
               "on this runtime it is readable but NOT writable."))
    if permits is not None:
        lines.append(web_note(permits))
    return "\n".join(lines)
