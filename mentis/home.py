"""Where an installed Mentis lives on this machine, and what a release says
it is.

THE INSTALL ROOT, PER OPERATING SYSTEM (Stage 1 contract, as changed by the
Caretaker: the brief's `%LOCALAPPDATA%\\Mentis` is Mark III's own folder, with
its own bin/, logs/ and workspace/, so Mark IV lives one level down):

  Windows  %LOCALAPPDATA%\\Mentis\\Mark-IV
  macOS    ~/Library/Application Support/Mentis/Mark-IV
  Linux    ${XDG_DATA_HOME:-~/.local/share}/mentis/mark-iv

`MENTIS_HOME`, when set and not empty, overrides all three. Tests and sandbox
demonstrations set it; nothing here falls back to the owner's real root when
it is set, and nothing here creates anything -- this module only names paths.

Under the root:

  releases/<semver>+<commit12>/   immutable once verified; own .venv; read-only
  backups/                        default destination of `mentis brain backup`
  state/install.json              {format, current, previous, brain, port, ...}
  state/update.journal.json       only while an update is unfinished
  state/needs-attention.json      only when a human decision is required
  bin/mentis(.cmd)                the launcher
  install-logs/                   the installer's, updater's and servers' logs
  brains/default/                 the default Brain (install.json may name another)

LEGACY ITEMS SHARE THE WINDOWS ROOT. `%LOCALAPPDATA%\\Mentis\\Mark-IV` already
holds what the old `tools/release.py` deployment made: `releases/<commit12>/`
folders, `brain/`, `codex/`, `restart-*`, `server-<port>.log(.err)`,
`source-cache/`, `source-bindings.json` and `tool-use-demonstrations.json`
(and `brain/` there IS the live Brain). There is no `logs/` there -- that is
Mark III's, one level up -- but the brief's `logs/` would sit beside those
server logs, so none of these is this layout's: its logs are `install-logs/`
and its default Brain `brains/default/`, not the brief's `logs/` and `brain/`.
`releases/` is shared: a legacy release folder is named by a bare commit,
which `is_release_name` refuses, so it is never taken for (or reached through)
`Layout.release`; whoever lists `releases/` must filter with `is_release_name`
and leave everything else alone.

A RELEASE SAYS WHAT IT IS in the `RELEASE.json` at its top, beside `mentis/`
(written by the package builder). Code run from a repository checkout has no
such file and so is no release: `release()` answers None for it.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

ENV = "MENTIS_HOME"
RELEASE_FILE = "RELEASE.json"

#: the top of the code this process imported: the release directory when run
#: from a release, the checkout when run from a repository
CODE_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: a release directory's name: `<semver>+<commit12>`, the SemVer core and
#: pre-release (https://semver.org regex, no build metadata of its own), `+`,
#: then the first 12 hex digits of the commit as git writes them (lowercase).
#: Nothing else, so no separator, drive (`C:`), stream (`a:b`), NUL, `.` or
#: `..` can reach a path join, and a legacy `releases/<commit12>` is not one.
RELEASE_NAME = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"\+[0-9a-f]{12}", re.ASCII)


def is_release_name(name) -> bool:
    """Whether `name` is a release directory name, `<semver>+<commit12>`."""
    return isinstance(name, str) and RELEASE_NAME.fullmatch(name) is not None


def default_root(platform: str | None = None,
                 environ: dict | None = None) -> pathlib.Path:
    """The install root this OS uses when MENTIS_HOME is not set.

    `platform` and `environ` default to this process's; they are parameters
    so every OS's answer can be checked on any one OS."""
    platform = platform or sys.platform
    env = os.environ if environ is None else environ
    home = pathlib.Path(env.get("HOME") or env.get("USERPROFILE")
                        or pathlib.Path.home())
    if platform == "win32":
        base = env.get("LOCALAPPDATA")
        if not base:
            # Not guessed into some other user's profile: LOCALAPPDATA is set
            # in every interactive Windows session, and its absence is said.
            raise RuntimeError("LOCALAPPDATA is not set, so the Windows "
                               f"install root cannot be named; set {ENV}")
        return pathlib.Path(base) / "Mentis" / "Mark-IV"
    if platform == "darwin":
        return (home / "Library" / "Application Support" / "Mentis"
                / "Mark-IV")
    # Linux and any other POSIX: the XDG base directory spec. An empty or
    # relative XDG_DATA_HOME is invalid by that spec and is ignored.
    xdg = env.get("XDG_DATA_HOME") or ""
    base = pathlib.Path(xdg) if os.path.isabs(xdg) else home / ".local" / "share"
    return base / "mentis" / "mark-iv"


def root(environ: dict | None = None,
         platform: str | None = None) -> pathlib.Path:
    """The install root: MENTIS_HOME when set, otherwise this OS's default.
    Absolute; never created here."""
    env = os.environ if environ is None else environ
    override = env.get(ENV)
    if override:
        return pathlib.Path(os.path.abspath(os.path.expanduser(override)))
    return default_root(platform, env)


class Layout:
    """The named places under one install root. Paths only."""

    def __init__(self, base: os.PathLike | str | None = None):
        self.root = pathlib.Path(base) if base is not None else root()

    @property
    def releases(self) -> pathlib.Path:
        return self.root / "releases"

    @property
    def backups(self) -> pathlib.Path:
        return self.root / "backups"

    @property
    def state(self) -> pathlib.Path:
        return self.root / "state"

    @property
    def install_json(self) -> pathlib.Path:
        return self.state / "install.json"

    @property
    def journal(self) -> pathlib.Path:
        return self.state / "update.journal.json"

    @property
    def needs_attention(self) -> pathlib.Path:
        return self.state / "needs-attention.json"

    @property
    def bin(self) -> pathlib.Path:
        return self.root / "bin"

    @property
    def launcher(self) -> pathlib.Path:
        return self.bin / ("mentis.cmd" if sys.platform == "win32" else "mentis")

    @property
    def logs(self) -> pathlib.Path:
        # not `logs/`: beside the legacy deployment's server logs, in the
        # Windows root, and Mark III's name one level up
        return self.root / "install-logs"

    @property
    def default_brain(self) -> pathlib.Path:
        # not `brain/`: in the Windows root that is the live legacy Brain
        return self.root / "brains" / "default"

    def release(self, name: str) -> pathlib.Path:
        """`releases/<semver>+<commit12>`. Any other name -- a separator,
        `..`, a drive (`C:`), a `:`, NUL, a legacy bare commit, empty -- is
        refused, not resolved. A staging folder beside it (`<name>.partial`)
        is the caller's to name from this path; it is never a release."""
        if not is_release_name(name):
            raise ValueError(f"{name!r} is not a release directory name "
                             "(<semver>+<commit12>)")
        return self.releases / name


def release(code_root: os.PathLike | str | None = None) -> dict | None:
    """What the release this code was installed from says it is, as
    `/api/server` reports it: {version, commit, path}. None when the code is
    not a release -- no RELEASE.json beside `mentis/`, as in a repository
    checkout or a release made by the old `tools/release.py`.

    A RELEASE.json that is present but cannot be read, or is not format 1,
    raises: a release that cannot say what it is must not pass for a
    checkout."""
    top = pathlib.Path(code_root) if code_root is not None else CODE_ROOT
    p = top / RELEASE_FILE
    if not p.is_file():
        return None
    doc = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("format") != 1:
        raise ValueError(f"{p} is not a format 1 RELEASE.json")
    version, commit = doc.get("version"), doc.get("commit")
    if not (isinstance(version, str) and version
            and isinstance(commit, str) and commit):
        raise ValueError(f"{p} names no version and commit")
    return {"version": version, "commit": commit, "path": str(top)}
