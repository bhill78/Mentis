"""The Git connector: a repository on this machine, read through Git, never
changed.

WHAT THIS IS. The second working connector behind the registry, and the
production form of the disposable repository-onboarding experiment (Bulk
Source / Repository Onboarding, ent-cc71013e9872, Turn 4; its connector is in
held artifact adm-7769a712fdb4). The experiment showed the chain holds --
the connector declares the choices, the generic interface draws them, the
person selects and previews, the connector fetches, the existing ingress
admits -- and this keeps that chain, on the machinery Mark IV has since built
for it: the declaration, the machine-local binding, plan-then-confirm, the
one write path (`mentis.sources.apply`) and the generic reads. EVERYTHING
GIT-SPECIFIC IS IN THIS FILE; nothing above it says "git" except the registry
entry that describes it.

  declare   record a collection: id, name, declarer, time, and its scope --
            include/exclude patterns over paths, and the two options only a
            repository has: the REF it follows and how many RECENT COMMITS on
            it to take. Append-only, an act, like a folder's.
  bind      tell THIS machine which repository the collection is. Must be
            somewhere Git recognises as a repository; nothing is recorded.
  plan      read the repository at the ref and preview exactly what a sweep
            would record against the latest observations. Writes nothing.
  sweep     confirm a plan: the exact bytes of every selected blob and commit
            go into the held store, and the plan is recomputed inside the
            transaction. If it is not what was previewed -- the branch moved,
            the scope or record changed -- nothing is recorded.

ACQUIRED IS NOT KNOWN. Like every connector, the only things this writes are
Admissions, the sweep act that produced them and the `produced` links between
them (`mentis.sources.apply`). Nothing imported from a repository becomes a
Finding, Lesson, Rule or Decision, or stands as anything: establishing is the
owner's governed act, and no argument here leads to one.

READ-ONLY ON THE SOURCE, BY CONSTRUCTION. Only plumbing that reads objects is
run -- `rev-parse`, `symbolic-ref`, `ls-tree`, `cat-file`, `rev-list`,
`diff-tree` -- none of which reads or refreshes the index or the work tree,
with `GIT_OPTIONAL_LOCKS=0`. What is read is COMMITTED content at the ref,
never the working copy, so an observation is reproducible from the
repository's own objects. A repository's own configuration can name programs
for Git to run (`core.fsmonitor`, signature checks on `log`); none of the
commands used consults them, and they are switched off explicitly anyway, and
the inherited `GIT_*` environment -- which could point Git at another
repository -- is dropped.

SOURCE IDENTITY is collection id + key, as for a folder. A FILE's key is its
NFC path in the tree, so Markdown links, embeds, rendering and search read it
exactly as they read a folder's file. A COMMIT's key is `.git/commits/<sha>`:
Git forbids a `.git` path component -- and a tree that has one anyway is
refused here -- so a commit key can never be a file's.

ABSENCE. The tree at the ref is enumerated completely, so a selected path
that is no longer there is absent, and its history stays. A window of recent
commits is NOT a complete enumeration: a commit that slides out of it is not
examined, never absent -- the experiment's rule, kept. SO AFTER THE REF IS
REVISED, commits taken from the old ref's window stay present, each still
labelled with the ref it was read on (`native.ref`); the collection view does
not yet say which of them lie outside the ref now followed (review note F5).

NO NETWORK FOR A REPOSITORY ON THIS MACHINE. Reading one never fetches: a
partial clone's missing objects are withheld as `not acquired: not present
locally`, a repository that is not its own top or sits on a network share is
refused (`_gate`, `_env`).

A REPOSITORY ELSEWHERE is bound by its ADDRESS instead (https or ssh): Mentis
keeps a bare mirror of it outside the corpus, fetches into that mirror only
when the owner previews, and reads the mirror exactly as above. Credentials
come from this machine's own Git credential helper and ssh agent, never from
the address and never into the Brain. See "a repository elsewhere" below.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import unicodedata
import uuid

from mentis.sources import (DECLARED, OVER_HELD_LIMIT, PlanChanged, Refused,
                            apply, diff, effective_scope, latest, observation,
                            record_revision)
from mentis.sources import bindings, lifecycle
# THE FOLDER CONNECTOR'S GENERIC HELPERS, reused rather than copied: how a
# pattern selects a path, how Markdown links are read, what bytes are, what
# a plan id names, what a preview says and what a refused sweep is holding.
# None of them knows what a folder is.
from mentis.sources.filesystem import (_TYPES, _MARKDOWN, embeds_in,
                                       encoding_of, links_of)
from mentis.sources.lifecycle import (Cancelled, _binding_changed, _custody,
                                      _patterns, _plan_id, _preview, _Quiet)
from mentis.sources.filesystem import selected as _selected_path
from mentis.spine import held

__all__ = ["Connector", "Cancelled", "embeds_in", "selected"]

CONNECTOR = "git"

#: What wrote these records, honestly known.
WRITER = "git-connector"

#: How a commit's relations are read. Part of every commit observation's
#: relations, so a change to it is a change the record shows.
RESOLVER = "git-commit/1"

#: Where commits live among a collection's keys. See the module docstring.
COMMITS = ".git/commits/"
CHANGES = ".git/changes/"
BLOBS = ".git/blobs/"
TREES = ".git/trees/"
RENAMES = ".git/renames/"

#: THE RECENT-COMMIT WINDOW. A default, and a bound on one sweep -- not a
#: claim about the repository.
DEFAULT_COMMITS = 10
MAX_COMMITS = 1000

#: The media types for Git objects.
COMMIT_TYPE = "text/x-git-commit"
CHANGE_TYPE = "text/x-git-diff-tree-raw"
TREE_TYPE = "application/x-git-tree"
#: The fixed type candidate 368b778f gave every new retained blob. No new
#: blob is recorded with it; blobs recorded with it keep it (see `read`).
BLOB_TYPE = "application/x-git-blob"


def blob_type_of(data: bytes) -> str:
    """A retained blob's payload type, from its bytes alone and never from a
    path: the type its signature says (`%PDF-` is application/pdf, PNG bytes
    image/png), else text/plain when its recorded encoding is text, else
    application/octet-stream. Identical bytes always get the identical
    type."""
    from mentis.artifacts import _signature
    return (_signature(bytes(data[:16]))
            or ("text/plain" if encoding_of(data).get("text")
                else "application/octet-stream"))


def source_of(collection: str) -> str:
    return f"{CONNECTOR}:{collection}"


def is_git_internal_key(key: str) -> bool:
    return str(key or "").startswith(".git/")


def is_commit_key(key: str) -> bool:
    return str(key or "").startswith(COMMITS)


def is_change_key(key: str) -> bool:
    return str(key or "").startswith(CHANGES)


def is_blob_key(key: str) -> bool:
    return str(key or "").startswith(BLOBS)


def is_tree_key(key: str) -> bool:
    return str(key or "").startswith(TREES)


def is_rename_key(key: str) -> bool:
    return str(key or "").startswith(RENAMES)


def selected(scope: dict, key: str) -> bool:
    """Whether a scope selects a key. Commits and change evidence are selected
    by the window -- patterns are about paths -- and a file by its patterns,
    exactly as a folder's is. `mentis.sources.reading` asks this of every
    link target."""
    if is_git_internal_key(key):
        return int((scope.get("options") or {}).get("commits") or 0) > 0
    return _selected_path(scope, key)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# -- running Git, read-only ---------------------------------------------------

#: CONFIGURATION THAT COULD RUN SOMETHING, switched off. The commands below
#: do not consult either; this is so that a later change to them cannot
#: start to.
_SAFE = ("-c", "core.fsmonitor=false", "-c", "log.showSignature=false")


#: WHAT A MISSING OBJECT IS SAID TO BE. A partial clone has objects only its
#: promisor remote holds; they are withheld, never fetched.
NOT_LOCAL = "not acquired: not present locally"

#: The first Git that honours GIT_NO_LAZY_FETCH.
NO_LAZY_FETCH_SINCE = (2, 45)


def _env(root: str | None = None) -> dict:
    """The environment every Git command here runs in.

    NO NETWORK, EVER (independent review, F1). In a PARTIAL CLONE a read of
    an object the clone does not hold makes Git fetch it from the promisor
    remote -- writing new packs into the source repository and running
    whatever that repository's configuration names for the network
    (`credential.helper`, `core.sshCommand`, `remote.*.uploadpack`). Measured
    by the reviewer: a preview took a clone from 4 pack files to 12.
    `GIT_NO_LAZY_FETCH=1` makes such a read answer "missing" instead, and
    `_gate` refuses a partial clone to a Git too old to honour it.

    NO DISCOVERY ABOVE THE BOUND FOLDER (F2): with the folder's parent as
    the ceiling, a folder that is merely INSIDE a repository is not one."""
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1")
    if root:
        parent = os.path.dirname(os.path.abspath(root).rstrip("\\/"))
        if parent and parent != os.path.abspath(root):
            env["GIT_CEILING_DIRECTORIES"] = parent
    return env


def _git(root: str, *args: str, ok=(0,)) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(["git", *_SAFE, "-C", root, *args],
                              capture_output=True, env=_env(root),
                              stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Refused("Git is not installed on this machine, so a repository "
                      "cannot be read") from None
    if done.returncode not in ok:
        why = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise Refused(f"git {args[0]} could not read the repository: "
                      f"{why[-1] if why else 'exit ' + str(done.returncode)}")
    return done


def _out(root: str, *args: str) -> str:
    return _git(root, *args).stdout.decode("utf-8", "replace").strip()


def repository(root: str) -> bool:
    """Whether `root` is a repository this connector will read."""
    try:
        _gate(root)
    except Refused:
        return False
    return True


def _version() -> tuple[int, int]:
    try:
        out = subprocess.run(["git", "version"], capture_output=True,
                             env=_env()).stdout.decode("ascii", "replace")
    except FileNotFoundError:
        raise Refused("Git is not installed on this machine, so a repository "
                      "cannot be read") from None
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _unc(path: str) -> bool:
    return path.replace("/", "\\").startswith("\\\\")


def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == \
        os.path.normcase(os.path.realpath(b))


def _gate(root: str) -> None:
    """Refuse, with the reason, anything but a repository whose own top is
    `root` and that can be read with no network. Asked before every plan,
    sweep and bind; reads nothing from the objects.

      * A `.git` FILE naming a network `gitdir:` (F6) is refused before Git
        is run at all: resolving it would touch the network share.
      * The repository's top must BE the bound folder (F2): a subfolder of
        one, or a folder under a home directory that is one, would
        otherwise read the whole enclosing repository.
      * A PARTIAL CLONE needs a Git that honours GIT_NO_LAZY_FETCH (F1).
    """
    dotgit = os.path.join(root, ".git")
    if os.path.isfile(dotgit):
        try:
            with open(dotgit, encoding="utf-8", errors="replace") as fh:
                line = fh.readline().strip()
        except OSError as exc:
            raise Refused(f"its `.git` file could not be read "
                          f"({type(exc).__name__})") from None
        target = line[7:].strip() if line.startswith("gitdir:") else ""
        if _unc(target):
            raise Refused("its `.git` file points at a network location; "
                          "only repositories on this machine are read")
    if _unc(root):
        raise Refused("only repositories on this machine are read, not a "
                      "network location")
    bare = _out(root, "rev-parse", "--is-bare-repository") == "true"
    if bare:
        top = _out(root, "rev-parse", "--absolute-git-dir")
    else:
        top = _out(root, "rev-parse", "--show-toplevel")
    if _unc(top):
        raise Refused("its Git directory is on a network location; only "
                      "repositories on this machine are read")
    if not top or not _same(top, root):
        raise Refused("this folder is inside a repository, not the top of "
                      "one; bind the repository's own folder")
    partial = _git(root, "config", "--get", "extensions.partialClone",
                   ok=(0, 1)).stdout.strip() or _git(
        root, "config", "--get-regexp", r"^remote\..*\.promisor$",
        ok=(0, 1)).stdout.strip()
    if partial and _version() < NO_LAZY_FETCH_SINCE:
        raise Refused("this is a partial clone, and this machine's Git is "
                      "older than 2.45, so it cannot be stopped from fetching "
                      "missing objects over the network. Upgrade Git, or "
                      "bind a full clone.")


def _resolve(root: str, ref: str) -> str:
    """The commit a ref names now, or a refusal that says which ref."""
    done = _git(root, "rev-parse", "--verify", "--quiet", "--end-of-options",
                f"{ref}^{{commit}}", ok=(0, 1))
    sha = done.stdout.decode("ascii", "replace").strip()
    if done.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        raise Refused(f"{ref!r} does not name a commit in this repository")
    return sha


def current_branch(root: str) -> str | None:
    done = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD",
                ok=(0, 1, 128))
    name = done.stdout.decode("utf-8", "replace").strip()
    return name if done.returncode == 0 and name else None


class _Objects:
    """`git cat-file --batch`, one object at a time: the experiment measured
    one `git` process per object as nearly all of its time."""

    def __init__(self, root: str):
        try:
            self.p = subprocess.Popen(["git", *_SAFE, "-C", root, "cat-file",
                                       "--batch"], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL,
                                      env=_env(root))
        except FileNotFoundError:
            raise Refused("Git is not installed on this machine") from None

    def get(self, sha: str, max_bytes: int | None = None) -> tuple[str | None, bytes | str | None]:
        """(type, bytes), or (None, None) for an object this repository
        does not hold -- a partial clone's -- which is never fetched.
        If max_bytes is provided and object exceeds it, drains stdout and
        returns (kind, OVER_HELD_LIMIT)."""
        self.p.stdin.write(sha.encode("ascii") + b"\n")
        self.p.stdin.flush()
        head = self.p.stdout.readline().decode("ascii", "replace").split()
        if len(head) == 2 and head[1] == "missing":
            return None, None
        if len(head) != 3:
            raise Refused(f"object {sha} could not be read from the "
                          "repository")
        _, kind, size_str = head
        size = int(size_str)
        if max_bytes is not None and size > max_bytes:
            remaining = size + 1
            while remaining > 0:
                chunk = self.p.stdout.read(min(remaining, 64 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
            return kind, OVER_HELD_LIMIT
        data = self.p.stdout.read(size)
        self.p.stdout.read(1)                   # the newline after the object
        return kind, data

    def close(self):
        try:
            self.p.stdin.close()
        finally:
            self.p.wait(timeout=30)


# -- a repository elsewhere: an address, mirrored on this machine ---------------
#
# ONE CONNECTOR, TWO KINDS OF BINDING. A collection can be bound to a
# repository folder on this machine, as above, or to the ADDRESS of a
# repository elsewhere (https or ssh). An address is never read directly:
# Mentis keeps a bare MIRROR of it in a cache folder outside every corpus,
# fetched only when the owner previews, and everything after that -- the
# survey, the plan id, the sweep -- reads the mirror exactly as it reads a
# local repository. So the source identity, the keys, the observations and
# the one write path are the same whichever way the repository was bound,
# and a confirmed sweep reads what was previewed and never the network.
#
# NO SECRET COMES NEAR THE BRAIN. An address carrying credentials is refused,
# never stripped; the credential-free address is what the binding and the
# sweep act record. Access comes from what this machine already has: the
# user's Git credential helper (Git Credential Manager on Windows) for https,
# and the ssh agent and keys for ssh -- run with every prompt switched off,
# so a missing credential is a refusal rather than a window or a hang.

#: WHAT A BLOB THE MIRROR WAS NEVER SENT IS SAID TO BE. The fetch filters out
#: every blob over the held limit, so a missing one in a Mentis mirror is
#: exactly that -- not a partial clone someone else made.
NOT_FETCHED = "not acquired: over held limit (not fetched)"

#: The transports an address may use. `http` sends credentials in the
#: clear, `git` is unauthenticated and `file`/`ext`/`fd` reach this machine
#: or run programs.
SCHEMES = ("https", "ssh")

#: TEST HOOKS, empty in use. A test may admit `file` and `http` (a local
#: bare repository, a `git http-backend` on 127.0.0.1) and give the Git it
#: runs a private global configuration, so the machine's own credential
#: helper is never asked for anything during a test.
_TEST_SCHEMES: tuple = ()
_TEST_ENV: dict = {}

#: HOW LONG A FETCH MAY TAKE, and how slow it may get before Git gives up.
LS_TIMEOUT = 120
FETCH_TIMEOUT = 900
_LOW_SPEED = ("-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=60")

#: THE MIRROR'S NAME FOR ITS REMOTE. Not `origin`: the user's own global
#: `remote.origin.*` settings would otherwise apply to it.
REMOTE = "mentis-source"

#: WHAT THE FETCH FILTERS AT. `blob:limit=N` leaves out blobs of N bytes or
#: more, and the held store takes up to MAX_BYTES exactly -- so one more.
def _filter() -> str:
    return f"blob:limit={held.MAX_BYTES + 1}"


#: A mirror's own empty hooks folder, named as `core.hooksPath` for every Git
#: command run on it: a fetch runs `reference-transaction` hooks otherwise.
_NO_HOOKS = "mentis-no-hooks"


def source_cache() -> str:
    """Where mirrors are kept: this machine's, never a corpus's."""
    return os.environ.get("MENTIS_SOURCE_CACHE") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "Mentis", "Mark-IV", "source-cache")


_URL = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/]*)(/.*)?$")
_SCP = re.compile(r"^([^@/:\s]+)@([^/:\s]+):(.+)$")
_HOST = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?"
                   r"|\[[0-9A-Fa-f:.]+\])$")
#: A user name: never one Git or ssh could read as an option.
_USER = re.compile(r"^[A-Za-z0-9._~+][A-Za-z0-9._~+-]*$")


def _bad_path(path: str) -> bool:
    return any(seg.startswith("-") for seg in path.split("/"))


def canonical_remote(url) -> str:
    """The address a remote binding records, or a refusal that says why.

    Scheme and host lowercased, trailing `/` dropped, `.git` kept as given
    (some servers answer only one spelling). Accepted: `https://host/path`,
    `ssh://[user@]host[:port]/path` and scp-style `user@host:path`. REFUSED:
    any credential in the address (an https address may carry no user at
    all: a token in the user slot looks exactly like a name), a query or
    fragment, `http`/`git`/`file`, remote-helper transports (`ext::`,
    `fd::`), and anything Git could read as an option."""
    if not isinstance(url, str) or not url.strip():
        raise Refused("a repository address is needed")
    url = url.strip()
    if len(url) > 2048 or any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7f
                              for c in url):
        raise Refused("a repository address has no spaces or control "
                      "characters")
    if url.startswith("-"):
        raise Refused("a repository address cannot begin with `-`")
    if "::" in url.split("/", 1)[0]:
        raise Refused("remote-helper transports (`ext::`, `fd::` and the "
                      "like) run programs; give an https:// or ssh:// address")
    if "?" in url or "#" in url:
        raise Refused("a repository address has no query or fragment: a "
                      "credential is sometimes passed that way, and is "
                      "never accepted here")
    allowed = SCHEMES + tuple(_TEST_SCHEMES)
    m = _URL.match(url)
    if m:
        scheme, netloc, path = m.group(1).lower(), m.group(2), m.group(3) or ""
        if scheme not in allowed:
            raise Refused(f"`{scheme}://` addresses are not fetched; give an "
                          "https:// or ssh:// address")
        if scheme == "file":
            path = path.rstrip("/")
            if netloc or not path or _bad_path(path):
                raise Refused("that is not a repository address")
            return f"file://{path}"
        user, at, hostport = netloc.rpartition("@")
        if at:
            if scheme in ("https", "http"):
                raise Refused(
                    "the address carries a user name or token. Nothing that "
                    "could be a credential is accepted in an address: give "
                    "it without one, and let this machine's Git credential "
                    "manager supply it")
            if ":" in user:
                raise Refused("the address carries a password; use an ssh "
                              "key or agent instead")
            if not _USER.match(user):
                raise Refused(f"{user!r} is not a user name")
        if hostport.startswith("["):
            end = hostport.find("]")
            host, port = hostport[:end + 1], hostport[end + 2:]
        else:
            host, _, port = hostport.partition(":")
        if not _HOST.match(host) or (port and not port.isdigit()):
            raise Refused(f"{host!r} is not a host name")
        path = path.rstrip("/")
        if not path or _bad_path(path):
            raise Refused("the address names no repository")
        return (f"{scheme}://{user + '@' if user else ''}{host.lower()}"
                f"{':' + port if port else ''}{path}")
    m = _SCP.match(url)
    if m:
        user, host, path = m.groups()
        if not _USER.match(user):
            raise Refused(f"{user!r} is not a user name")
        if not _HOST.match(host):
            raise Refused(f"{host!r} is not a host name")
        path = path.rstrip("/")
        if not path or _bad_path(path):
            raise Refused("the address names no repository")
        return f"{user}@{host.lower()}:{path}"
    raise Refused("that is not a repository address: give an https:// or "
                  "ssh:// address, or user@host:path")


def _redact(text: str) -> str:
    """Git's own words, with any user name or token in an address removed."""
    # Up to the LAST `@` before a space or quote: a user name or token may
    # itself hold `/`. Taking a little too much of an address out of an
    # error is harmless; leaving a token in is not.
    return re.sub(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s@'\"]*@", r"\1", text)


def _remote_ok() -> None:
    if _version() < NO_LAZY_FETCH_SINCE:
        raise Refused("a repository address needs Git 2.45 or later on this "
                      "machine: its mirror holds only what was fetched, and "
                      "an older Git cannot be stopped from fetching the rest "
                      "while it is read")


def _cache_for(corpus, url: str) -> str:
    cache = os.path.join(source_cache(), corpus.corpus_id,
                         hashlib.sha256(url.encode("utf-8")).hexdigest()[:16])
    here = os.path.realpath(corpus.root)
    there = os.path.realpath(cache)
    if bindings._inside(there, here) or bindings._inside(here, there):
        raise Refused("the source cache may not lie inside the corpus, or "
                      "the corpus inside it: set MENTIS_SOURCE_CACHE "
                      "elsewhere")
    return cache


def _fetch_env(cache: str) -> dict:
    """`_env`, and nothing that could ask anyone anything."""
    env = _env(cache)
    env.pop("SSH_ASKPASS", None)
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never",
               SSH_ASKPASS_REQUIRE="never",
               GIT_ALLOW_PROTOCOL=":".join(SCHEMES + tuple(_TEST_SCHEMES)))
    env.update(_TEST_ENV)
    # THE USER'S OWN ssh, IF THEY NAMED ONE (core.sshCommand -- on Windows,
    # often the system OpenSSH, to reach its agent), never prompting and
    # never trusting an unknown host. Otherwise the plain `ssh`.
    mine = subprocess.run(["git", "config", "--global", "--get",
                           "core.sshCommand"], capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, timeout=60)
    ssh = mine.stdout.decode("utf-8", "replace").strip() or "ssh"
    env["GIT_SSH_COMMAND"] = (ssh + " -o BatchMode=yes"
                              " -o StrictHostKeyChecking=yes")
    return env


def _remote_args(cache: str) -> list[str]:
    return [*_SAFE, "-c", f"core.hooksPath={os.path.join(cache, _NO_HOOKS)}",
            "-c", "core.askPass=", "-c", "credential.interactive=never",
            "-c", "gc.auto=0", "-c", "maintenance.auto=false",
            "-c", "fetch.recurseSubmodules=false",
            "-c", "submodule.recurse=false", *_LOW_SPEED]


def _remote_git(cache: str, *args: str, timeout: int, url: str
                ) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *_remote_args(cache), "-C", cache,
                               *args], capture_output=True,
                              env=_fetch_env(cache), stdin=subprocess.DEVNULL,
                              timeout=timeout)
    except FileNotFoundError:
        raise Refused("Git is not installed on this machine, so a repository "
                      "cannot be read") from None
    except subprocess.TimeoutExpired:
        raise Refused(f"unreachable: {url} did not answer within {timeout} "
                      "seconds. Nothing was recorded.") from None


def _failed(done: subprocess.CompletedProcess, url: str) -> Refused:
    """A refusal that says which of the usual things went wrong."""
    text = _redact(done.stderr.decode("utf-8", "replace")).strip()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    last = lines[-1] if lines else f"exit {done.returncode}"
    low = text.lower()
    tail = " Nothing was recorded."
    if "host key verification failed" in low or "host key is known" in low:
        return Refused(f"unknown host key: this machine has not accepted the "
                       f"ssh host key of {url}. Connect to it once with ssh "
                       "yourself to check and accept the key, then preview "
                       "again." + tail)
    if "not allowed" in low and "transport" in low:
        return Refused(f"{url}: that transport is not allowed." + tail)
    if any(s in low for s in (
            "authentication failed", "could not read username",
            "could not read password", "terminal prompts disabled",
            "unable to get password", "unable to get username",
            "permission denied", "error: 401", "error: 403",
            "invalid username or password", "access denied")):
        return Refused(f"authentication required: no credential this machine "
                       f"holds was accepted by {url}. Sign in with your Git "
                       "credential manager, or load your ssh key into the "
                       f"agent, then preview again. (Git: {last})" + tail)
    if any(s in low for s in (
            "repository not found", "not found", "does not exist",
            "does not appear to be a git repository", "error: 404",
            "no such file", "not a git repository")):
        return Refused(f"not found, or no access: {url} has no repository "
                       "this machine may read. A private repository answers "
                       "this way too when no credential reaches it. "
                       f"(Git: {last})" + tail)
    if any(s in low for s in (
            "could not resolve", "failed to connect", "connection refused",
            "timed out", "could not connect", "couldn't connect",
            "network is unreachable", "operation too slow",
            "connection reset", "connection closed", "unable to access",
            "no route to host")):
        return Refused(f"unreachable: {url} could not be reached from this "
                       f"machine. (Git: {last})" + tail)
    return Refused(f"{url} could not be read: {last}." + tail)


def _mirror(cache: str, url: str) -> None:
    """Make the mirror if it is not there, and (re)write the only
    configuration it has -- Mentis's: where it fetches from, and that what it
    lacks is the remote's to hold. No credential, no hooks, no template."""
    env = _fetch_env(cache)
    os.makedirs(os.path.join(cache, _NO_HOOKS), exist_ok=True)
    if not os.path.isfile(os.path.join(cache, "HEAD")):
        # `--template=` (empty): nothing from `init.templateDir` -- hooks
        # included -- is copied in; and the user's own `core.hooksPath` is
        # not run either (making HEAD is a reference transaction).
        done = subprocess.run(["git", *_remote_args(cache), "init",
                               "--quiet", "--bare", "--template=", cache],
                              capture_output=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=60)
        if done.returncode != 0:
            raise Refused("the source cache could not be made: "
                          + _redact(done.stderr.decode("utf-8", "replace"))
                          .strip()[-300:])
    config = os.path.join(cache, "config")
    for k, v in ((f"remote.{REMOTE}.url", url),
                 (f"remote.{REMOTE}.promisor", "true"),
                 (f"remote.{REMOTE}.partialclonefilter", _filter())):
        subprocess.run(["git", "config", "--file", config, k, v], check=True,
                       capture_output=True, env=env,
                       stdin=subprocess.DEVNULL, timeout=60)


def _fetch(cache: str, url: str, ref: str, commits: int) -> str:
    """Bring the mirror up to the ref, as far back as the window needs, and
    say which ref was followed (an empty one takes the remote's default
    branch, by name). Only a preview calls this.

    DEPTH IS THE WINDOW PLUS ONE: the oldest commit taken must have its
    parent, or Git reads it as a root commit that added every file. BLOBS
    OVER THE HELD LIMIT ARE NEVER SENT (`--filter`): they would only be
    withheld."""
    _remote_ok()
    _mirror(cache, url)
    done = _remote_git(cache, "ls-remote", "--symref", "--", url, "HEAD",
                       *([ref] if ref else []), timeout=LS_TIMEOUT, url=url)
    if done.returncode != 0:
        raise _failed(done, url)
    refs, default = {}, None
    for line in done.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("ref: ") and line.endswith("\tHEAD"):
            target = line[5:].split("\t", 1)[0]
            if target.startswith("refs/heads/"):
                default = target[len("refs/heads/"):]
                refs.setdefault(target, None)
        elif "\t" in line:
            sha, name = line.split("\t", 1)
            refs[name] = sha
    if not ref:
        if not default:
            raise Refused(f"{url} names no default branch (an empty "
                          "repository?); name the branch, tag or commit to "
                          "follow")
        ref = default
    # THE ORDER `rev-parse` READS A NAME IN, so the mirror resolves the ref
    # to what was fetched: a full ref, then a tag, then a branch.
    names = ((ref,) if ref.startswith("refs/") else ()) + (
        f"refs/tags/{ref}", f"refs/heads/{ref}")
    full = next((n for n in names if n in refs), None)
    if full:
        spec = f"+{full}:{full}"
    elif re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", ref):
        spec = ref
    else:
        raise Refused(f"ref not found: {ref!r} is not a branch or tag at "
                      f"{url}. Nothing was recorded.")
    done = _remote_git(cache, "fetch", "--quiet", "--no-tags",
                       "--no-write-fetch-head", f"--depth={commits + 1}",
                       f"--filter={_filter()}", REMOTE,
                       spec, timeout=FETCH_TIMEOUT, url=url)
    if done.returncode != 0:
        raise _failed(done, url)
    return ref


#: ONE MIRROR, ONE READER OR WRITER AT A TIME. A mirror is shared by every
#: collection and preview of its address, and a fetch rewrites its shallow
#: boundary for EVERY branch in it -- a shallow fetch of one branch can cut
#: another's history short (independent review). So a fetch and the survey
#: that follows it, a sweep's read and record, and a removal each hold the
#: mirror's lock. In-process: the server is one process. (`_shallow` is the
#: second line: a window that is cut short anyway is refused, never recorded
#: as root commits.)
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(root: str) -> threading.RLock:
    key = os.path.normcase(os.path.realpath(root))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


class _Unlocked:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _held(bnd_or_root, remote) :
    """The mirror's lock for a repository bound by address; nothing to hold
    for a folder (it is never written)."""
    return _lock(bnd_or_root) if remote else _Unlocked()


def _rmtree(path: str) -> None:
    def again(fn, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            fn(p)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=again)
    else:                                                  # pragma: no cover
        shutil.rmtree(path, onerror=again)


def _release(cache: str | None) -> bool:
    """Delete a mirror nothing uses any more: no binding on this machine and
    no preview this process holds. Only ever under the source cache."""
    if not cache:
        return False
    base = os.path.realpath(source_cache())
    real = os.path.realpath(cache)
    if not bindings._inside(real, base) or _same(real, base):
        return False
    doc = bindings._load(bindings.store_path())
    for cid, cols in doc.items():
        if cid == bindings.UNBOUND or not isinstance(cols, dict):
            continue
        for b in cols.values():
            if isinstance(b, dict) and b.get("root") and _same(b["root"],
                                                                real):
                return False
    if any(d.get("root") and _same(d["root"], real) for d in _DRAFTS.values()):
        return False
    lock = _lock(real)
    # IN USE RIGHT NOW (a fetch, a survey, a sweep): kept. Never waited
    # for, so a release can never deadlock against another mirror's work.
    if not lock.acquire(blocking=False):
        return False
    try:
        if os.path.isdir(real):
            _rmtree(real)
        return not os.path.exists(real)
    finally:
        lock.release()


# -- scope options: the ref and the commit window ------------------------------

_REF = re.compile(r"^[^\s\x00-\x1f\x7f~^:?*\[\\]+$")


def checked_options(options, *, base=None, root=None) -> dict:
    """The repository's own scope fields, checked: `ref` (a branch, tag or
    commit) and `commits` (how many recent commits on it, 0 to
    MAX_COMMITS). `base` supplies whatever is not given. An empty ref takes
    the repository's current branch when one is bound -- and that NAME is
    what is recorded, never "whatever HEAD is", so another clone checked out
    elsewhere cannot silently change what the collection follows."""
    if options is not None and not isinstance(options, dict):
        raise Refused("options are {ref: ..., commits: ...}")
    got = dict(base or {})
    got.update({k: v for k, v in (options or {}).items() if v is not None})
    unknown = sorted(set(got) - {"ref", "commits"})
    if unknown:
        raise Refused(f"a Git collection has no option {unknown[0]!r}")
    ref = str(got.get("ref") or "").strip()
    if not ref and root is not None:
        ref = current_branch(root) or ""
        if not ref:
            raise Refused("the repository is not on a branch (a detached "
                          "HEAD); name the branch, tag or commit to follow")
    if not ref:
        raise Refused("a Git collection follows a ref: name the branch, tag "
                      "or commit")
    if ref.startswith("-") or not _REF.match(ref) or len(ref) > 255:
        raise Refused(f"{ref!r} is not a ref Git could name")
    raw = got.get("commits", DEFAULT_COMMITS)
    if isinstance(raw, int) and not isinstance(raw, bool):
        n = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        n = int(raw.strip())
    else:
        raise Refused(f"`commits` must be a whole number, not {raw!r}")
    if not 0 <= n <= MAX_COMMITS:
        raise Refused(f"`commits` must be from 0 to {MAX_COMMITS}")
    return {"ref": ref, "commits": n}


# -- the declaration ------------------------------------------------------------

def declare(corpus, cv, *, name: str, include=None, exclude=None,
            options=None, declarer, written_by=None) -> dict:
    """Record a collection with this connector's declaration fields."""
    return lifecycle.declare(_this, corpus, cv, name=name, include=include,
                             exclude=exclude, declarer=declarer,
                             written_by=written_by, options=options)


def declaration(corpus, collection: str) -> dict | None:
    from mentis.sources import declaration as _one
    d = _one(corpus, collection)
    return d if d and d.get("connector") == CONNECTOR else None


# -- the survey: read-only, shared by plan and sweep ----------------------------

def _forbidden(ident: str) -> bool:
    return any(p.casefold() == ".git" for p in ident.split("/"))


def _tree(root: str, head: str) -> list[tuple[str, str, str, str, bytes]]:
    """(mode, type, object, size, raw path) for every entry under the tree."""
    out = []
    raw = _git(root, "ls-tree", "-r", "-l", "-z", "--full-tree", head).stdout
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, obj, size = meta.decode("ascii").split()
        out.append((mode, kind, obj, size, path))
    return out


def _changed(root: str, sha: str) -> list[tuple[str, bytes]]:
    """(status, raw path) for each path a commit changed against its first
    parent; a root commit against nothing. A merge shows none, as Git's own
    default does: its parents are recorded, which is what it is."""
    raw = _git(root, "diff-tree", "-r", "--root", "--no-renames", "-z",
               "--no-commit-id", sha).stdout
    parts = raw.split(b"\0")
    out, i = [], 0
    while i + 1 < len(parts):
        meta = parts[i].decode("ascii", "replace")
        if meta.startswith(":"):
            out.append((meta.split()[-1], parts[i + 1]))
            i += 2
        else:
            i += 1
    return out


def _shallow(root: str) -> set[str]:
    """The commits a shallow repository holds without their parents.

    WHERE GIT ITSELF KEEPS THE LIST: a linked worktree keeps it in the
    COMMON git dir, not its own (re-review), so the path is Git's answer,
    never a guess. `--git-path` may answer relative to the folder read."""
    path = _out(root, "rev-parse", "--git-path", "shallow")
    if not os.path.isabs(path):
        path = os.path.join(root, path)
    try:
        with open(path, encoding="ascii",
                  errors="replace") as fh:
            return {ln.strip() for ln in fh if ln.strip()}
    except OSError:
        return set()


def _decoded(raw: bytes) -> str | None:
    try:
        return _nfc(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def _subject(data: bytes) -> str:
    _, _, msg = data.partition(b"\n\n")
    return msg.decode("utf-8", "replace").strip().split("\n", 1)[0][:200]


def _parents(data: bytes) -> list[str]:
    head, _, _ = data.partition(b"\n\n")
    return [ln[7:].decode("ascii").strip() for ln in head.split(b"\n")
            if ln.startswith(b"parent ")]


def _git_version(root: str) -> str:
    try:
        done = subprocess.run(["git", *_SAFE, "-C", root, "--version"],
                              capture_output=True, env=_env(root))
        return done.stdout.decode("ascii", "replace").strip()
    except Exception:
        return "git"


def verify_git_object(kind: str, expected_id: str, data: bytes) -> bool:
    """Verify Git object id offline (SHA-1 of `<kind> <len>\\0<data>`).
    Refuses if mismatch."""
    header = f"{kind} {len(data)}\0".encode("ascii")
    computed = hashlib.sha1(header + data).hexdigest()
    if computed != expected_id:
        raise Refused(f"corrupt {kind} object {expected_id} in repository: "
                      f"computed SHA-1 {computed} does not match")
    return True


def _tree_of_commit(data: bytes) -> str | None:
    head, _, _ = data.partition(b"\n\n")
    for ln in head.split(b"\n"):
        if ln.startswith(b"tree "):
            return ln[5:].decode("ascii", "replace").strip()
    return None


def _parse_diff_tree_raw(raw: bytes) -> list[dict]:
    parts = raw.split(b"\0")
    records = []
    i = 0
    while i + 1 < len(parts):
        meta = parts[i].decode("ascii", "replace").strip()
        if not meta or not meta.startswith(":"):
            i += 1
            continue
        tokens = meta.split()
        if len(tokens) >= 5:
            old_mode = tokens[0].lstrip(":")
            new_mode = tokens[1]
            old_sha = tokens[2]
            new_sha = tokens[3]
            status = tokens[4]
            raw_path = parts[i + 1]
            records.append({
                "old_mode": old_mode,
                "new_mode": new_mode,
                "old_sha": old_sha,
                "new_sha": new_sha,
                "status": status,
                "raw_path": raw_path,
            })
            i += 2
        else:
            i += 1
    return records


def _parse_tree_entries(data: bytes) -> dict[str, tuple[str, str, str]]:
    entries = {}
    i = 0
    n = len(data)
    while i < n:
        space = data.find(b" ", i)
        if space == -1:
            break
        mode = data[i:space].decode("ascii", "replace")
        null = data.find(b"\0", space)
        if null == -1:
            break
        name = data[space + 1:null].decode("utf-8", "surrogateescape")
        sha_bytes = data[null + 1:null + 21]
        sha_hex = sha_bytes.hex()
        kind = "tree" if mode in ("40000", "040000") else ("commit" if mode == "160000" else "blob")
        entries[name] = (mode, kind, sha_hex)
        i = null + 21
    return entries


def _parse_diff_tree_renames(raw: bytes) -> list[dict]:
    parts = raw.split(b"\0")
    inferred = []
    i = 0
    while i < len(parts):
        meta = parts[i].decode("ascii", "replace").strip()
        if not meta or not meta.startswith(":"):
            i += 1
            continue
        tokens = meta.split()
        if len(tokens) >= 5:
            old_mode = tokens[0].lstrip(":")
            new_mode = tokens[1]
            old_sha = tokens[2]
            new_sha = tokens[3]
            status = tokens[4]
            if status.startswith("R") or status.startswith("C"):
                if i + 2 < len(parts):
                    old_path = parts[i + 1].decode("utf-8", "replace")
                    new_path = parts[i + 2].decode("utf-8", "replace")
                    score = int(status[1:]) if status[1:].isdigit() else None
                    inferred.append({
                        "status": status,
                        "old_path": old_path,
                        "new_path": new_path,
                        "score": score,
                        "old_mode": old_mode,
                        "new_mode": new_mode,
                        "old_sha": old_sha,
                        "new_sha": new_sha,
                    })
                    i += 3
                else:
                    break
            else:
                i += 2
        else:
            i += 1
    return inferred


def _collect_subtrees(cat: _Objects, root_tree_id: str, paths: list[str],
                      needed_trees: set[str], evidence_withheld: dict,
                      missing_reason: str) -> None:
    needed_trees.add(root_tree_id)
    tree_cache: dict[str, dict[str, tuple[str, str, str]]] = {}
    for p in paths:
        dirs = [part for part in p.split("/")[:-1] if part]
        curr_id = root_tree_id
        for d in dirs:
            if curr_id in tree_cache:
                entries = tree_cache[curr_id]
            else:
                kind, data = cat.get(curr_id, max_bytes=held.MAX_BYTES)
                if data is None or kind != "tree":
                    evidence_withheld[f"{TREES}{curr_id}"] = missing_reason
                    break
                if data == OVER_HELD_LIMIT or len(data) > held.MAX_BYTES:
                    evidence_withheld[f"{TREES}{curr_id}"] = OVER_HELD_LIMIT
                    break
                entries = _parse_tree_entries(data)
                tree_cache[curr_id] = entries
            if d in entries and entries[d][1] == "tree":
                curr_id = entries[d][2]
                needed_trees.add(curr_id)
            else:
                break


def _survey(corpus, scope, root, *, keep: bool, progress=None,
            missing: str = NOT_LOCAL, collection: str | None = None,
            prior: dict | None = None) -> dict:
    """Read the repository at the scope's ref. `keep` puts the exact bytes in
    the held store (a sweep); without it they are only hashed (a plan).
    `missing` is what an object the repository does not hold is said to be:
    a Mentis mirror lacks exactly the blobs its fetch filtered out."""
    progress = progress or _Quiet()
    opts = scope.get("options") or {}
    ref = opts["ref"]
    head = _resolve(root, ref)
    files, visible, refused = [], [], []
    spellings: dict[str, list[bytes]] = {}
    for mode, kind, obj, size, raw in _tree(root, head):
        progress.check()
        ident = _decoded(raw)
        if ident is None:
            refused.append({"path": raw.decode("utf-8", "replace"),
                            "reason": "refused: a path that is not UTF-8"})
            continue
        if "\\" in ident:
            refused.append({"path": ident, "reason": "refused: a path with a "
                            "backslash, which reads as another path"})
            continue
        if _forbidden(ident):
            refused.append({"path": ident, "reason": "refused: a `.git` path "
                            "component, which Git itself forbids"})
            continue
        if kind == "commit":
            refused.append({"path": ident, "reason": "refused: a submodule; "
                            "its repository is not followed"})
            continue
        if kind != "blob":
            refused.append({"path": ident, "reason": f"refused: a {kind}"})
            continue
        if mode == "120000":
            refused.append({"path": ident, "reason": "refused: a symbolic "
                            "link; not followed"})
            continue
        if not _selected_path(scope, ident):
            visible.append(ident)
            continue
        files.append((ident, obj, mode,
                      int(size) if size.isdigit() else None))
        spellings.setdefault(ident, []).append(raw)

    clashes = {i: v for i, v in spellings.items() if len(v) > 1}
    if clashes:
        shown = "; ".join(
            f"{i!r} is in the tree as "
            + " and ".join(repr(x.decode("utf-8")) for x in v)
            for i, v in sorted(clashes.items())[:5])
        raise Refused(f"{len(clashes)} source identities would come from more "
                      f"than one path: {shown}. Revise the scope to exclude "
                      "one, and plan again. Nothing was recorded.")

    observations, withheld = [], {}
    cat = _Objects(root)
    try:
        for ident, obj, mode, size in sorted(files):
            progress.check()
            progress.folder(posixpath.dirname(ident))
            if size is None:
                withheld[ident] = missing
                continue
            if size > held.MAX_BYTES:
                withheld[ident] = OVER_HELD_LIMIT
                continue
            _, data = cat.get(obj)
            if data is None:
                withheld[ident] = missing
                continue
            observations.append(_present(corpus, ident, data, keep=keep,
                                         payload_type=_TYPES.guess_type(
                                             ident)[0]
                                         or "application/octet-stream",
                                         relations=None,
                                         native={"blob": obj, "mode": mode,
                                                 "ref": ref, "commit": head},
                                         withheld=withheld))
            progress.read(size)
        n = int(opts.get("commits") or 0)
        shas = (_out(root, "rev-list", f"--max-count={n}", head).split()
                if n else [])
        cut = _shallow(root).intersection(shas)
        if cut:
            raise Refused(f"commit {sorted(cut)[0]} on {ref!r} is the edge of "
                          "a shallow history here, so what it changed cannot "
                          "be read. Preview again (a repository bound by "
                          "address fetches the window afresh), take fewer "
                          "recent commits, or bind a full clone. Nothing was "
                          "recorded.")

        evidence_withheld: dict[str, str] = {}
        held_commits: set[str] = set()
        if prior is None and collection is not None:
            prior = latest(corpus, source_of(collection))
        if prior:
            for obj, entry in prior.items():
                if is_commit_key(obj) and observation(entry).get("state") == "present":
                    held_commits.add(obj[len(COMMITS):])
        available_commits = set(shas) | held_commits
        needed_blobs: dict[str, str] = {}
        needed_trees: set[str] = set()
        change_records_data = []

        for sha in shas:
            progress.check()
            progress.folder(COMMITS.rstrip("/"))
            _, data = cat.get(sha)
            if data is None:
                raise Refused(f"commit {sha} on {ref!r} is not present in "
                              "this repository (a partial or shallow "
                              "clone); it is not fetched. Take fewer recent "
                              "commits, or bind a full clone.")
            rels = [{"rel": "parent", "syntax": "git", "authored": p,
                     "resolver": RESOLVER, "resolution": "in-collection",
                     "resolved": COMMITS + p} for p in _parents(data)]
            for status, raw in _changed(root, sha):
                path = _decoded(raw)
                if path is not None and "\\" in path:
                    path = None
                rels.append({"rel": "changed-path", "syntax": "git",
                             "authored": raw.decode("utf-8", "replace"),
                             "status": status, "resolver": RESOLVER,
                             **({"resolution": "in-collection",
                                 "resolved": path} if path is not None
                                else {"resolution": "not-resolved",
                                      "resolved": None,
                                      "why": "a path that is not UTF-8, "
                                             "or holds a backslash"})})
            key = COMMITS + sha
            observations.append(_present(
                corpus, key, data, keep=keep, payload_type=COMMIT_TYPE,
                relations=rels,
                native={"commit": sha, "ref": ref,
                        "label": f"{sha[:7]} {_subject(data)}"},
                withheld=withheld))
            progress.read(len(data))

            # Stage H: Change evidence for commits in window
            parents = _parents(data)
            comparisons = ([(None, None, ["--root", sha])]
                           if not parents
                           else [(p, idx, [p, sha]) for idx, p in enumerate(parents)])

            commit_root_tree = _tree_of_commit(data)
            if commit_root_tree:
                needed_trees.add(commit_root_tree)

            for parent, parent_idx, cmp_args in comparisons:
                cmd_ev = ["diff-tree", "-r", "-z", "--raw", "--no-renames",
                          "--full-index", "--no-commit-id", *cmp_args]
                raw_ev = _git(root, *cmd_ev).stdout
                recs = _parse_diff_tree_raw(raw_ev)

                cmd_rn = ["diff-tree", "-r", "-z", "-M", "--raw",
                          "--full-index", "--no-commit-id", *cmp_args]
                rename_reason = None
                try:
                    raw_rn = _git(root, *cmd_rn).stdout
                    inferred_renames = _parse_diff_tree_renames(raw_rn)
                except Refused as exc:
                    raw_rn = b""
                    inferred_renames = []
                    rename_reason = str(exc)

                changed_paths = []
                for rec in recs:
                    p = _decoded(rec["raw_path"])
                    if p and "\\" not in p:
                        changed_paths.append(p)
                        if rec["old_sha"] != "0" * 40 and rec["old_mode"] != "160000":
                            needed_blobs.setdefault(rec["old_sha"], p)
                        if rec["new_sha"] != "0" * 40 and rec["new_mode"] != "160000":
                            needed_blobs.setdefault(rec["new_sha"], p)

                record_trees = set()
                if commit_root_tree:
                    _collect_subtrees(cat, commit_root_tree, changed_paths,
                                      record_trees, evidence_withheld, missing)

                parent_root_tree = None
                if parent:
                    _, p_data = cat.get(parent)
                    if p_data:
                        parent_root_tree = _tree_of_commit(p_data)
                        if parent_root_tree:
                            _collect_subtrees(cat, parent_root_tree, changed_paths,
                                              record_trees, evidence_withheld, missing)
                needed_trees.update(record_trees)

                change_records_data.append({
                    "sha": sha,
                    "parent": parent,
                    "parent_idx": parent_idx,
                    "cmp_args": cmp_args,
                    "cmd": ["git", *cmd_ev],
                    "raw": raw_ev,
                    "records": recs,
                    "renames_raw": raw_rn,
                    "inferred_renames": inferred_renames,
                    "rename_reason": rename_reason,
                    "required_trees": record_trees,
                    "parent_tree_missing": bool(parent and not parent_root_tree),
                })

        # Trees (H4)
        for t_id in sorted(needed_trees):
            if f"{TREES}{t_id}" in evidence_withheld:
                continue
            t_kind, t_data = cat.get(t_id, max_bytes=held.MAX_BYTES)
            if t_data is None:
                evidence_withheld[f"{TREES}{t_id}"] = missing
                continue
            if t_data == OVER_HELD_LIMIT or (isinstance(t_data, (bytes, bytearray)) and len(t_data) > held.MAX_BYTES):
                evidence_withheld[f"{TREES}{t_id}"] = OVER_HELD_LIMIT
                continue
            verify_git_object("tree", t_id, t_data)
            obs = _present(
                corpus, f"{TREES}{t_id}", t_data, keep=keep,
                payload_type=TREE_TYPE, relations=[],
                native={"tree": t_id, "label": f"tree {t_id[:7]}",
                        "nature": "change evidence",
                        "claim_or_evidence": "change evidence"},
                withheld=evidence_withheld)
            if obs:
                observations.append(obs)
                progress.read(len(t_data))

        # Blobs (H2, H8)
        for b_id, sample_path in sorted(needed_blobs.items()):
            if f"{BLOBS}{b_id}" in evidence_withheld:
                continue
            b_kind, b_data = cat.get(b_id, max_bytes=held.MAX_BYTES)
            if b_data is None:
                evidence_withheld[f"{BLOBS}{b_id}"] = missing
                continue
            if b_data == OVER_HELD_LIMIT or (isinstance(b_data, (bytes, bytearray)) and len(b_data) > held.MAX_BYTES):
                evidence_withheld[f"{BLOBS}{b_id}"] = OVER_HELD_LIMIT
                continue
            verify_git_object("blob", b_id, b_data)

            # H8/U7: WHICH HEAD PATHS HOLD THESE BYTES IS NOT RECORDED HERE.
            # It depends on HEAD, which moves; a blob is an immutable fact.
            # It is derived when read, from each HEAD file's own recorded
            # `native.blob` (`reading.same_content`). A blob an earlier
            # candidate sweep recorded with `same-content` relations keeps
            # them exactly as recorded -- never rewritten, never re-admitted;
            # a read labels them as of their sweep.
            was = observation((prior or {}).get(f"{BLOBS}{b_id}") or {})
            blob_rels = (list(was.get("relations") or [])
                         if was.get("state") == "present" else [])

            # NOR IS ITS TYPE TAKEN FROM WHICHEVER PATH SELECTED IT: it is
            # the bytes' own -- their signature (a PDF stays extractable and
            # searchable, an image stays an image), else text or binary by
            # their recorded encoding -- so identical bytes always get the
            # identical type and are never re-admitted because a filename
            # changed. A blob an earlier candidate sweep recorded with
            # another type keeps it as recorded -- never re-admitted to
            # correct it; a read labels it.
            ptype = (was["payload_type"]
                     if was.get("state") == "present" and was.get("payload_type")
                     else blob_type_of(b_data))

            obs = _present(
                corpus, f"{BLOBS}{b_id}", b_data, keep=keep,
                payload_type=ptype, relations=blob_rels,
                native={"blob": b_id, "label": f"blob {b_id[:7]}",
                        "nature": "change evidence",
                        "claim_or_evidence": "change evidence"},
                withheld=evidence_withheld)
            if obs:
                observations.append(obs)
                progress.read(len(b_data))

        git_ver = _git_version(root)
        complete_changes = 0
        partial_changes = 0
        record_coverage = []

        for cr in change_records_data:
            sha = cr["sha"]
            parent = cr["parent"]
            parent_idx = cr["parent_idx"]
            change_key = f"{CHANGES}{sha}/{parent or 'root'}"

            missing_or_withheld_items = []
            def _add_missing(item_id: str, reason: str) -> None:
                if not any(x[0] == item_id for x in missing_or_withheld_items):
                    missing_or_withheld_items.append((item_id, reason))

            if len(cr["raw"]) > held.MAX_BYTES:
                _add_missing(change_key, OVER_HELD_LIMIT)
            for tree_id in sorted(cr["required_trees"]):
                tree_key = TREES + tree_id
                if tree_key in evidence_withheld:
                    _add_missing(tree_key, evidence_withheld[tree_key])
            if cr["parent_tree_missing"]:
                _add_missing(COMMITS + parent, "parent root tree unavailable locally; not fetched")
            proof_limitation = None
            if parent and parent not in available_commits:
                proof_limitation = "parent commit anchor is outside this sweep's commit window and is not acquired here; before-side proof requires a separately retained parent anchor"
                _add_missing(COMMITS + parent, proof_limitation)
            for rec in cr["records"]:
                p = _decoded(rec["raw_path"])
                if p is None or "\\" in p:
                    _add_missing(rec["raw_path"].hex(), "a path that is not UTF-8, or holds a backslash; path content refused")
                if rec["old_sha"] != "0" * 40 and rec["old_mode"] != "160000":
                    if f"{BLOBS}{rec['old_sha']}" in evidence_withheld:
                        _add_missing(rec['old_sha'], evidence_withheld[f"{BLOBS}{rec['old_sha']}"])
                if rec["new_sha"] != "0" * 40 and rec["new_mode"] != "160000":
                    if f"{BLOBS}{rec['new_sha']}" in evidence_withheld:
                        _add_missing(rec['new_sha'], evidence_withheld[f"{BLOBS}{rec['new_sha']}"])

            coverage = "partial" if missing_or_withheld_items else "complete"
            record_coverage.append({"key": change_key, "status": coverage,
                                    "reasons": [{"id": item, "reason": reason}
                                                for item, reason in missing_or_withheld_items]})
            if coverage == "complete":
                complete_changes += 1
            else:
                partial_changes += 1

            c_rels = [{
                "rel": "change-of", "syntax": "git", "authored": sha,
                "resolver": RESOLVER, "resolution": "in-collection",
                "resolved": COMMITS + sha
            }]
            if parent:
                c_rels.append({
                    "rel": "against-parent", "syntax": "git", "authored": parent,
                    "resolver": RESOLVER,
                    "resolution": "not-resolved" if proof_limitation else "in-collection",
                    "resolved": None if proof_limitation else COMMITS + parent,
                    **({"why": proof_limitation} if proof_limitation else {}),
                })

            for rec in cr["records"]:
                p = _decoded(rec["raw_path"])
                is_legal_path = p is not None and "\\" not in p
                p_display = p if is_legal_path else rec["raw_path"].decode("utf-8", "replace")

                if rec["status"] != "D":
                    rel = {
                        "rel": "after", "syntax": "git", "authored": p_display,
                        "status": rec["status"], "mode": rec["new_mode"],
                        "new_mode": rec["new_mode"], "old_mode": rec["old_mode"],
                        "path": p_display, "resolver": RESOLVER,
                        "blob": rec["new_sha"],
                    }
                    if not is_legal_path:
                        rel["resolution"] = "not-resolved"
                        rel["resolved"] = None
                        rel["why"] = "a path that is not UTF-8, or holds a backslash"
                    elif rec["new_mode"] == "160000":
                        rel["resolution"] = "not-resolved"
                        rel["resolved"] = None
                        rel["why"] = "submodule (gitlink); content not followed"
                        rel["gitlink"] = rec["new_sha"]
                    elif f"{BLOBS}{rec['new_sha']}" in evidence_withheld:
                        rel["resolution"] = "not-resolved"
                        rel["resolved"] = None
                        rel["why"] = evidence_withheld[f"{BLOBS}{rec['new_sha']}"]
                        rel["blob"] = rec["new_sha"]
                    else:
                        rel["resolution"] = "in-collection"
                        rel["resolved"] = f"{BLOBS}{rec['new_sha']}"
                        rel["blob"] = rec["new_sha"]
                    c_rels.append(rel)

                if rec["status"] != "A":
                    rel = {
                        "rel": "before", "syntax": "git", "authored": p_display,
                        "status": rec["status"], "mode": rec["old_mode"],
                        "old_mode": rec["old_mode"], "new_mode": rec["new_mode"],
                        "path": p_display, "resolver": RESOLVER,
                        "blob": rec["old_sha"],
                    }
                    if not is_legal_path:
                        rel["resolution"] = "not-resolved"
                        rel["resolved"] = None
                        rel["why"] = "a path that is not UTF-8, or holds a backslash"
                    elif rec["old_mode"] == "160000":
                        rel["resolution"] = "not-resolved"
                        rel["resolved"] = None
                        rel["why"] = "submodule (gitlink); content not followed"
                        rel["gitlink"] = rec["old_sha"]
                    elif f"{BLOBS}{rec['old_sha']}" in evidence_withheld:
                        rel["resolution"] = "not-resolved"
                        rel["resolved"] = None
                        rel["why"] = evidence_withheld[f"{BLOBS}{rec['old_sha']}"]
                        rel["blob"] = rec["old_sha"]
                    else:
                        rel["resolution"] = "in-collection"
                        rel["resolved"] = f"{BLOBS}{rec['old_sha']}"
                        rel["blob"] = rec["old_sha"]
                    c_rels.append(rel)

            if cr["inferred_renames"]:
                rn_key = f"{RENAMES}{sha}/{parent or 'root'}"
                c_rels.append({
                    "rel": "rename-inference", "syntax": "git",
                    "authored": f"{sha}/{parent or 'root'}",
                    "resolver": RESOLVER, "resolution": "in-collection",
                    "resolved": rn_key
                })

            native_cr = {
                "commit": sha,
                "parent": parent,
                "parent_index": parent_idx,
                "parent index": parent_idx,
                "git_version": git_ver,
                "git version": git_ver,
                "arguments": cr["cmd"],
                "exact arguments": cr["cmd"],
                "coverage": coverage,
                "label": f"changes in {sha[:7]} against {parent[:7] if parent else 'root'}",
                "nature": "change evidence",
                "claim_or_evidence": "change evidence",
                "rename_inference": {"status": "unavailable" if cr["rename_reason"] else "available",
                                     "reason": cr["rename_reason"], "method": "git diff-tree -M", "threshold": "50%"},
                "proof_limitation": proof_limitation,
            }
            if missing_or_withheld_items:
                native_cr["withheld_items"] = [{"id": item[0], "reason": item[1]} for item in missing_or_withheld_items]

            obs_cr = _present(
                corpus, change_key, cr["raw"], keep=keep,
                payload_type=CHANGE_TYPE, relations=c_rels,
                native=native_cr, withheld=evidence_withheld)
            if obs_cr:
                observations.append(obs_cr)
                progress.read(len(cr["raw"]))

            if cr["inferred_renames"]:
                rn_key = f"{RENAMES}{sha}/{parent or 'root'}"
                rn_rels = [{
                    "rel": "inference-of", "syntax": "git",
                    "authored": change_key, "resolver": RESOLVER,
                    "resolution": "in-collection", "resolved": change_key
                }]
                for rn in cr["inferred_renames"]:
                    rn_rels.append({
                        "rel": "inferred-rename", "syntax": "git",
                        "authored": f"{rn['old_path']} -> {rn['new_path']}",
                        "old_path": rn["old_path"], "new_path": rn["new_path"],
                        "similarity": rn["score"], "resolver": RESOLVER,
                        "resolution": "in-collection",
                        "resolved": rn["new_path"],
                    })
                rn_native = {
                    "method": "git diff-tree -M",
                    "threshold": "50%",
                    "git_version": git_ver,
                    "git version": git_ver,
                    "arguments": ["git", "diff-tree", "-r", "-z", "-M", "--raw", "--full-index", "--no-commit-id", *cr["cmp_args"]],
                    "exact arguments": ["git", "diff-tree", "-r", "-z", "-M", "--raw", "--full-index", "--no-commit-id", *cr["cmp_args"]],
                    "renames": cr["inferred_renames"],
                    "label": f"rename inference for {sha[:7]} against {parent[:7] if parent else 'root'}",
                    "nature": "change evidence",
                    "claim_or_evidence": "change evidence",
                }
                obs_rn = _present(
                    corpus, rn_key, cr["renames_raw"], keep=keep,
                    payload_type=CHANGE_TYPE, relations=rn_rels,
                    native=rn_native, withheld=evidence_withheld)
                if obs_rn:
                    observations.append(obs_rn)
                    progress.read(len(cr["renames_raw"]))

        cov_status = "complete" if partial_changes == 0 else "partial"
        coverage_summary = {
            "status": cov_status,
            "complete": complete_changes,
            "partial": partial_changes,
            "records": record_coverage,
        }

    finally:
        cat.close()
    observations = [o for o in observations if o is not None]
    blocked = {r["path"] for r in refused}

    def examined(obj: str) -> bool:
        # A WINDOW OF COMMITS IS NOT AN ENUMERATION: never absent.
        # Change records, blobs and trees are immutable facts: never absent.
        if is_git_internal_key(obj):
            return False
        if obj in blocked:
            return False
        return _selected_path(scope, obj)

    return {"observations": observations, "withheld": withheld,
            "visible": visible, "refused": refused, "unexamined": [],
            "examined": examined, "within": "", "head": head, "ref": ref,
            "coverage": coverage_summary if n else {"status": "complete", "complete": 0, "partial": 0},
            "evidence_withheld": evidence_withheld if n else {},
            "evidence_counts": {
                "change_records": len([o for o in observations if is_change_key(o["object"])]),
                "blobs": len([o for o in observations if is_blob_key(o["object"])]),
                "trees": len([o for o in observations if is_tree_key(o["object"])]),
            } if n else {"change_records": 0, "blobs": 0, "trees": 0}}


def _present(corpus, key, data, *, keep, payload_type, relations, native,
             withheld) -> dict | None:
    if len(data) > held.MAX_BYTES:
        withheld[key] = OVER_HELD_LIMIT
        return None
    if keep:
        try:
            digest, _ = held.put(corpus.root, data)
        except ValueError:
            withheld[key] = OVER_HELD_LIMIT
            return None
    else:
        digest = hashlib.sha256(data).hexdigest()
    enc = encoding_of(data)
    if relations is None:
        relations = (links_of(key, data.decode("utf-8"))
                     if key.lower().endswith(_MARKDOWN) and enc["text"]
                     else [])
    return {"object": key, "state": "present", "retention": "held",
            "digest": digest, "size": len(data), "payload_type": payload_type,
            "encoding": enc, "relations": relations, "native": native}


# -- plan and sweep -------------------------------------------------------------

def _missing(bnd) -> str:
    return NOT_FETCHED if bnd.get("remote") else NOT_LOCAL


def _ready(corpus, collection, *, fetching=False) -> tuple[dict, dict]:
    """The declaration and this machine's binding, checked. `fetching` (a
    plan) makes a remote binding's mirror again if it has gone -- the next
    fetch fills it; a sweep never fetches, so it is refused instead."""
    decl = declaration(corpus, collection)
    if decl is None:
        raise Refused(f"{collection!r} is not a Git collection declared in "
                      "this corpus")
    bnd = bindings.binding(corpus, collection)
    if bnd is None:
        raise Refused(
            f"{collection!r} is not bound on this machine, so there is no "
            "repository to read. Nothing is inferred from that: acquired "
            "material and its retained bytes are unaffected. Bind it first.")
    root = bnd["root"]
    if bnd.get("remote"):
        if fetching:
            _remote_ok()
            with _lock(root):
                _mirror(root, bnd["remote"])
        elif not os.path.isfile(os.path.join(root, "HEAD")):
            raise Refused(f"this machine's copy of {bnd['remote']} is gone "
                          "(the source cache was cleared); preview again to "
                          "fetch it. Nothing was recorded.")
    try:
        st = os.lstat(root)
    except OSError as exc:
        raise Refused(f"the bound repository is unavailable "
                      f"({type(exc).__name__}); nothing is inferred absent. "
                      "Rebind or restore it.")
    if bindings.is_reparse(st) or not stat.S_ISDIR(st.st_mode) \
            or os.path.realpath(root) != root:
        raise Refused("the bound folder no longer resolves to the folder that "
                      "was bound; rebind it deliberately")
    try:
        _gate(root)
    except Refused as exc:
        raise Refused(f"the bound folder cannot be read as a repository "
                      f"({exc}); nothing is inferred absent. Rebind it "
                      "deliberately.") from None
    return decl, bnd


def _proposed(eff: dict, scope) -> dict:
    """A proposed revision, checked: patterns and options it would put in
    force, on top of the act it would revise."""
    if not isinstance(scope, dict):
        raise Refused("a scope is {include: [...], exclude: [...], "
                      "options: {...}}")
    inc = _patterns(scope.get("include"), eff["include"])
    exc = _patterns(scope.get("exclude"), eff["exclude"])
    opts = checked_options(scope.get("options"), base=eff["options"])
    if (inc, exc, opts) == (eff["include"], eff["exclude"], eff["options"]):
        raise Refused("that is already this collection's scope")
    return {"include": inc, "exclude": exc, "options": opts,
            "act": eff["act"], "revision": "proposed"}


def _basis(collection, decl, bnd, s, scope) -> dict:
    """What a plan id names beyond the folder connector's: the commit the ref
    resolved to, and the options in force. A branch that moves between the
    preview and the confirmation is a different plan."""
    return {"collection": collection, "declaration": decl["declaration"],
            "binding": bnd["binding"], "head": s["head"],
            "options": scope.get("options")}


def _scope_view(scope) -> dict:
    return {"include": scope["include"], "exclude": scope["exclude"],
            "options": scope.get("options")}



def _plan_snapshot(corpus, cv, collection: str, *, within=None, scope=None,
         progress=None) -> tuple:
    """Observe under the mirror lock; only previews fetch a remote."""
    if within:
        raise Refused("a Git collection is planned whole; `within` is a "
                      "folder's")
    decl, bnd = _ready(corpus, collection, fetching=True)
    eff = effective_scope(corpus, collection, decl)
    under = _proposed(eff, scope) if scope is not None else eff
    remote = bnd.get("remote")
    prior = latest(corpus, source_of(collection))
    with _held(bnd["root"], remote):
        if remote:
            # THE ONLY FETCH FOR A BOUND COLLECTION: a preview. Its
            # confirmation reads the mirror as this left it.
            (progress or _Quiet()).check()
            opts = under["options"]
            _fetch(bnd["root"], remote, opts["ref"],
                   int(opts.get("commits") or 0))
        s = _survey(corpus, under, bnd["root"], keep=False,
                    progress=progress, missing=_missing(bnd),
                    collection=collection, prior=prior)
    d = diff(prior, s["observations"], examined=s["examined"],
             withheld=set(s["withheld"]))
    changed, _ = _binding_changed(corpus, collection, bnd["binding"], prior)
    pid = _plan_id(_basis(collection, decl, bnd, s, under), under, s, d,
                   prior)
    return decl, bnd, eff, under, s, d, changed, pid


def _sweep_snapshot(corpus, cv, collection, plan_id, decl, bnd, changed, last, *,
           actor, written_by, scope, because, progress) -> tuple:
    source = source_of(collection)
    eff = effective_scope(corpus, collection, decl)
    under = _proposed(eff, scope) if scope is not None else eff
    prior = latest(corpus, source)
    # NO FETCH HERE: the mirror is read as the preview left it, and a head
    # another preview has moved since is a different plan.
    s = _survey(corpus, under, bnd["root"], keep=True, progress=progress,
                missing=_missing(bnd), collection=collection, prior=prior)
    progress.check()

    return decl, bnd, eff, under, s, changed, last, scope is not None, None


_this = sys.modules[__name__]
NOUN = "repository"
PLAN_CHANGE_REASON = "ref moved, or the binding, the scope or the record changed since it was previewed"


def _binding_extra(bnd):
    return {"remote": bnd["remote"]} if bnd.get("remote") else {}


def _draft_gone(draft, root):
    if draft.get("remote") and not (root is not None and draft["root"] == root):
        _release(draft["root"])


def _preview_result(corpus, s, d, pid, changed, bnd):
    return {**_git_preview(corpus, s, d, pid=pid, changed=changed),
            "at": _at(s, bnd.get("remote"))}


def _confirm_scope(scope, under, s):
    return {"scope": _scope_view(under)} if scope is not None else {}


def _revision_options(under):
    return {"options": under["options"]}


def _sweep_detail(s, plan_id, bnd, changed, last, decl):
    return _act_detail(s, plan_id, bnd["binding"], changed, last,
                       decl["declaration"], bnd.get("remote"))


def plan(corpus, cv, collection: str, *, within=None, scope=None,
         progress=None) -> dict:
    """Preview a sweep using this connector's snapshot policy."""
    return lifecycle.plan(_this, corpus, cv, collection, within=within,
                          scope=scope, progress=progress)


def _git_preview(corpus, s, d, *, pid, changed) -> dict:
    prev = _preview(corpus, s, d, pid=pid, changed=changed)
    admit = prev.get("admit") or []
    evidence_admit = {a["digest"]: a for a in admit
                      if is_git_internal_key(a["path"]) and not is_commit_key(a["path"])}
    evidence_bytes = sum(a["size"] for a in evidence_admit.values()
                         if not held.has(corpus.root, a["digest"]))
    prev["evidence"] = {
        "change_records": s.get("evidence_counts", {}).get("change_records", 0),
        "blobs": s.get("evidence_counts", {}).get("blobs", 0),
        "trees": s.get("evidence_counts", {}).get("trees", 0),
        "new_bytes": evidence_bytes,
        "bytes_to_acquire": evidence_bytes,
        "limit_disclosed": held.MAX_BYTES,
        "limit_disclosed_label": "25 MiB",
        "withheld": [{"key": k, "reason": v}
                     for k, v in sorted(s.get("evidence_withheld", {}).items())],
        "coverage": s.get("coverage", {}),
    }
    prev["counts"]["change_records"] = s.get("evidence_counts", {}).get("change_records", 0)
    prev["counts"]["blobs"] = s.get("evidence_counts", {}).get("blobs", 0)
    prev["counts"]["trees"] = s.get("evidence_counts", {}).get("trees", 0)
    return prev


def _at(s, remote=None) -> dict:
    """WHAT WAS READ: the ref and the commit it named then -- and, for a
    repository bound by address, that address, credential-free. Not a path,
    and nothing about this machine (the mirror's folder stays in the
    machine-local binding)."""
    return {"ref": s["ref"], "commit": s["head"],
            **({"remote": remote} if remote else {})}


def _act_detail(s, plan_id, bnd_token, changed, last, decl_id,
                remote=None) -> dict:
    return {"plan": plan_id, "binding": bnd_token,
            "binding_changed": changed, "previous_binding": last,
            "declaration": decl_id, "resolver": RESOLVER,
            "at": _at(s, remote),
            "not_acquired": [{"path": k, "reason": v} for k, v
                             in sorted(s["withheld"].items())],
            "refused": s["refused"], "unexamined": s["unexamined"],
            "visible_not_selected": len(s["visible"]),
            "coverage": s.get("coverage", {})}


def sweep(corpus, cv, collection: str, plan_id: str, *, within=None,
          acknowledge_binding_change: bool = False, actor="human",
          written_by=WRITER, scope=None, because=None,
          progress=None) -> dict:
    """Confirm a previewed plan. Records it only if it is still that plan."""
    if within:
        raise Refused("a Git collection is swept whole; `within` is a "
                      "folder's")
    progress = progress or _Quiet()
    decl, bnd = _ready(corpus, collection)
    source = source_of(collection)
    prior0 = latest(corpus, source)
    changed, last = _binding_changed(corpus, collection, bnd["binding"],
                                     prior0)
    if changed and not acknowledge_binding_change:
        raise Refused(
            "this is the first sweep under a new or changed binding. A "
            "binding does not certify that the repository holds the same "
            "material, so nothing is recorded until the previewed differences "
            "are confirmed with acknowledge_binding_change.")
    with _held(bnd["root"], bnd.get("remote")):
        return _sweep(corpus, cv, collection, plan_id, decl, bnd, changed,
                      last, actor=actor, written_by=written_by, scope=scope,
                      because=because, progress=progress)


def _sweep(corpus, cv, collection, plan_id, decl, bnd, changed, last, *,
           actor, written_by, scope, because, progress) -> dict:
    return lifecycle.sweep(_this, corpus, cv, collection, plan_id,
                           decl=decl, bnd=bnd, changed=changed, last=last,
                           actor=actor, written_by=written_by, scope=scope,
                           because=because, progress=progress)


# -- a new collection: previewed before anything is declared -------------------
#
# The same flow as a folder's (`filesystem.preview_new`): a draft holds the
# path in this process only, is bounded, and confirming it declares, binds
# and sweeps as one -- or none of them.

_DRAFTS: dict[tuple[str, str], dict] = {}
DRAFT_TTL = 60 * 60
DRAFT_CAP = 16


def _forget_drafts(corpus_id: str, root: str | None = None) -> None:
    return lifecycle.forget_drafts(_this, corpus_id, root)


def _checked_repository(corpus, root) -> str:
    real = bindings._checked_root(corpus, root)
    try:
        _gate(real)
    except Refused as exc:
        # GIT'S OWN REASON, kept: "not a repository" and "a repository Git
        # will not open here" (another owner's, say) need different fixes.
        raise Refused(f"{root!r} is not a Git repository this machine's Git "
                      f"will read ({exc})") from None
    return real


def _either(root, remote) -> None:
    if root is not None and remote is not None:
        raise Refused("a repository is bound by a folder on this machine or "
                      "by its address, not both")


def _remote_draft(corpus, remote, options, progress) -> tuple[str, str, dict]:
    """(address, mirror, options) for a draft by address: the address
    checked, the mirror fetched, an empty ref taken as the remote's default
    branch -- by name."""
    url = canonical_remote(remote)
    _remote_ok()
    if options is not None and not isinstance(options, dict):
        raise Refused("options are {ref: ..., commits: ...}")
    given = dict(options or {})
    # The window and the ref's spelling are checked before anything is
    # fetched; an empty ref is left for the remote to name.
    probe = checked_options({**given, "ref": given.get("ref") or "HEAD"})
    cache = _cache_for(corpus, url)
    (progress or _Quiet()).check()
    ref = _fetch(cache, url, str(given.get("ref") or "").strip(),
                 probe["commits"])
    return url, cache, checked_options({**given, "ref": ref})


def preview_new(corpus, *, name: str, root: str | None = None,
                include=None, exclude=None, options=None, progress=None,
                remote: str | None = None) -> dict:
    """Preview acquiring a repository that is not yet a collection: a folder
    on this machine (`root`) or a repository elsewhere (`remote`, which is
    fetched into this machine's mirror of it, and nowhere else)."""
    name = (name or "").strip()
    if not name:
        raise Refused("a collection needs a name")
    _either(root, remote)
    inc = _patterns(include, ["*"])
    exc = _patterns(exclude, [])
    url = None
    draft = f"draft-{uuid.uuid4().hex[:12]}"
    if remote is not None:
        url = canonical_remote(remote)
        with _lock(_cache_for(corpus, url)):
            url, cache, opts = _remote_draft(corpus, remote, options,
                                             progress)
            real = _checked_repository(corpus, cache)
            scope = {"include": inc, "exclude": exc, "options": opts,
                     "act": draft}
            s = _survey(corpus, scope, real, keep=False, progress=progress,
                        missing=NOT_FETCHED)
    else:
        real = _checked_repository(corpus, root)
        opts = checked_options(options, root=real)
        scope = {"include": inc, "exclude": exc, "options": opts,
                 "act": draft}
        s = _survey(corpus, scope, real, keep=False, progress=progress)
    d = diff({}, s["observations"], examined=s["examined"],
             withheld=set(s["withheld"]))
    pid = _plan_id({"draft": draft, "name": name, "head": s["head"],
                    "options": opts}, scope, s, d, {})
    _forget_drafts(corpus.corpus_id, real)
    _DRAFTS[(corpus.corpus_id, draft)] = {"name": name, "root": real,
                                          "remote": url,
                                          "include": inc, "exclude": exc,
                                          "options": opts, "at": time.time()}
    return {"draft": draft, "collection": None, "name": name,
            **_git_preview(corpus, s, d, pid=pid, changed=False),
            "at": _at(s, url),
            "scope": {"include": inc, "exclude": exc, "options": opts,
                      "act": None, "revision": None},
            "confirm": {"draft": draft, "plan": pid,
                        "acknowledge_binding_change": False}}


def acquire_new(corpus, cv, draft: str, plan_id: str, *, actor="human",
                written_by=WRITER, progress=None) -> dict:
    """Confirm a draft: declare, bind and sweep, or none of them."""
    progress = progress or _Quiet()
    _forget_drafts(corpus.corpus_id)
    got = _DRAFTS.get((corpus.corpus_id, draft))
    if got is None:
        raise Refused(f"{draft!r} is not a preview this server holds (a "
                      "restart forgets previews); preview the repository "
                      "again")
    scope = {"include": got["include"], "exclude": got["exclude"],
             "options": got["options"], "act": draft}
    url = got.get("remote")
    if url and not os.path.isfile(os.path.join(got["root"], "HEAD")):
        raise Refused(f"this machine's copy of {url} is gone (the source "
                      "cache was cleared); preview it again. Nothing was "
                      "declared.")
    with _held(got["root"], url):
        return _acquire(corpus, cv, draft, plan_id, got, scope, url,
                        actor=actor, written_by=written_by,
                        progress=progress)


def _acquire(corpus, cv, draft, plan_id, got, scope, url, *, actor,
             written_by, progress) -> dict:
    real = _checked_repository(corpus, got["root"])
    # A DRAFT BY ADDRESS IS CONFIRMED FROM THE MIRROR its preview fetched;
    # nothing is fetched now.
    s = _survey(corpus, scope, real, keep=True, progress=progress,
                missing=NOT_FETCHED if url else NOT_LOCAL)
    progress.check()

    def check(prior, d):
        now = _plan_id({"draft": draft, "name": got["name"],
                        "head": s["head"], "options": got["options"]},
                       scope, s, d, prior)
        if now != plan_id:
            raise PlanChanged(
                f"{plan_id} is not what would be recorded now ({now}): the "
                "repository changed since it was previewed"
                + _custody(corpus, s) + " Nothing was declared. Preview "
                "again.")

    bound = None
    try:
        with corpus.atomic():
            made = declare(corpus, cv, name=got["name"],
                           include=got["include"], exclude=got["exclude"],
                           options=got["options"], declarer=actor,
                           written_by=written_by)
            col = made["collection"]
            bound = bindings.bind(corpus, col, real, written_by=written_by,
                                  extra={"remote": url} if url else None)
            out = apply(
                corpus, cv, source=source_of(col), collection=col,
                connector=CONNECTOR, observations=s["observations"],
                examined=s["examined"], withheld=set(s["withheld"]),
                scope={"declaration": made["declaration"], "revision": None,
                       "within": None},
                act_detail=_act_detail(s, plan_id, bound["binding"], False,
                                       None, made["declaration"], url),
                actor=actor, written_by=written_by, check=check,
                observed_at=time.time())
    except BaseException:
        if bound is not None:
            bindings.unbind(corpus, bound["collection"],
                            written_by=written_by)
        raise
    _DRAFTS.pop((corpus.corpus_id, draft), None)
    return {**out, "collection": col, "declaration": made["declaration"],
            "binding": bound["binding"], "name": got["name"]}


def binding_state(corpus, collection: str) -> dict:
    """Machine-local binding metadata, without inspecting the source."""
    return lifecycle.binding_state(_this, corpus, collection)


class Connector:
    """The Git connector over one corpus. Owner-side operations; a dispatched
    worker gets the generic reads only, as for every connector."""

    def __init__(self, corpus, cv):
        self.corpus, self.cv = corpus, cv

    def declare(self, name, *, include=None, exclude=None, options=None,
                declarer="human", written_by=None):
        return declare(self.corpus, self.cv, name=name, include=include,
                       exclude=exclude, options=options, declarer=declarer,
                       written_by=written_by)

    def bind(self, collection, root=None, written_by=None, remote=None):
        """A repository folder on this machine (`root`), or a repository
        elsewhere by its address (`remote`). Binding by address makes this
        machine's empty mirror of it and fetches nothing: the next preview
        does. Nothing is recorded either way."""
        if declaration(self.corpus, collection) is None:
            raise Refused(f"{collection!r} is not a Git collection declared "
                          "in this corpus")
        _either(root, remote)
        was = bindings.binding(self.corpus, collection)
        if remote is not None:
            url = canonical_remote(remote)
            _remote_ok()
            cache = _cache_for(self.corpus, url)
            with _lock(cache):
                _mirror(cache, url)
                real = _checked_repository(self.corpus, cache)
            out = bindings.bind(self.corpus, collection, real,
                                written_by=written_by, extra={"remote": url})
            out["remote"] = url
        else:
            _checked_repository(self.corpus, root)
            out = bindings.bind(self.corpus, collection, root,
                                written_by=written_by)
        if was and was.get("remote"):
            _release(was.get("root"))
        return out

    def unbind(self, collection, written_by=None):
        """Unbind; a repository bound by address also loses this machine's
        mirror of it, unless another binding or a preview still uses it.
        Acquired material and its retained bytes are untouched."""
        was = bindings.binding(self.corpus, collection)
        out = bindings.unbind(self.corpus, collection, written_by=written_by)
        if was and was.get("remote"):
            out["cache_removed"] = _release(was.get("root"))
        return out

    def plan(self, collection, *, within=None, scope=None, progress=None):
        return plan(self.corpus, self.cv, collection, within=within,
                    scope=scope, progress=progress)

    def sweep(self, collection, plan_id, *, within=None,
              acknowledge_binding_change=False, actor="human", scope=None,
              because=None, progress=None, written_by=WRITER):
        return sweep(self.corpus, self.cv, collection, plan_id, within=within,
                     acknowledge_binding_change=acknowledge_binding_change,
                     actor=actor, scope=scope, because=because,
                     progress=progress, written_by=written_by)

    def preview_new(self, *, name, root=None, include=None, exclude=None,
                    options=None, progress=None, remote=None):
        return preview_new(self.corpus, name=name, root=root, include=include,
                           exclude=exclude, options=options,
                           progress=progress, remote=remote)

    def acquire_new(self, draft, plan_id, *, actor="human", progress=None,
                    written_by=WRITER):
        return acquire_new(self.corpus, self.cv, draft, plan_id, actor=actor,
                           progress=progress, written_by=written_by)

    def binding_state(self, collection):
        return binding_state(self.corpus, collection)

    def reveal(self, collection, obj):
        return {"revealed": False, "state": "refused",
                "why": "a repository's acquired objects are committed "
                       "content; the working copy is not that object"}
