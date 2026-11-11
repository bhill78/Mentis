"""A recursive text search over a directory that holds secret files.

Round 2 (Builder A; docs/modernization/CONTRACT.md "Round 2 — A"). A shell
command such as `grep -r TOKEN .` reads only a directory by its path, so a
path check sees nothing protected -- yet its output prints the lines of every
`.env`, key or credentials file beneath it (live: Grep over a workspace
printed `.env`). This module says, for ONE simple command, whether it is such a
search and which secret files (`operations._SECRET_NAMES`) it would read that
it does not explicitly exclude. The policy then treats the command as touching
a protected location: asked of the owner, refused under `deny`, allowed only
under Approve All.

WHAT IS RECOGNISED, and nothing else:
  grep / egrep / fgrep   with -r, -R, --recursive, --dereference-recursive or
                         -d recurse; excludes: --exclude=GLOB, --exclude-dir=GLOB
  rg                     always recursive; skips hidden files unless --hidden,
                         -., or -uu/-uuu; excludes: -g/--glob/--iglob '!GLOB'
  findstr                with /s; only files its masks name
Not recognised (said in the contract): Select-String, `git grep`, ack/ag, a
search inside an interpreter. rg's .gitignore handling is not modelled: a
gitignored secret still counts (conservative).

BOUNDED WALK. Dependency trees (`node_modules`, `.venv`, `venv`,
`site-packages`, `.git`, `__pycache__`) are not walked -- their `*.pem` /
`*.key` files are package data, and walking them would make every search of a
repository an owner question -- and at most `MAX_ENTRIES` entries are looked
at; past that, what was found so far decides.
"""

from __future__ import annotations

import fnmatch
import os

#: Directories not walked (package data, not the owner's secrets).
SKIP_DIRS = frozenset({"node_modules", ".venv", "venv", "site-packages", ".git",
                       "__pycache__", ".tox", ".mypy_cache"})
MAX_ENTRIES = 20000


def _name(word: str) -> str:
    return os.path.basename(word.strip("'\"").replace("\\", "/")).lower()


def _secret(name: str) -> bool:
    from mentis.operations import _SECRET_NAMES
    return bool(_SECRET_NAMES.search(os.sep + name))


def _excluded(rel: str, globs: list[str]) -> bool:
    base = os.path.basename(rel)
    parts = rel.replace("\\", "/").split("/")
    for g in globs:
        g = g.replace("\\", "/").lstrip("/")
        g2 = g[3:] if g.startswith("**/") else g
        if fnmatch.fnmatch(base, g2) or fnmatch.fnmatch(rel.replace("\\", "/"), g) \
                or any(fnmatch.fnmatch(p, g2) for p in parts[:-1]):
            return True
    return False


def _walk(root: str, *, hidden: bool, masks: list[str] | None,
          excluded: list[str]) -> list[str]:
    found, seen = [], 0
    if os.path.isfile(root):
        n = os.path.basename(root)
        return [root] if _secret(n) and not _excluded(n, excluded) else []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS
                       and (hidden or not d.startswith("."))]
        for f in filenames:
            seen += 1
            if seen > MAX_ENTRIES:
                return found
            if not hidden and f.startswith("."):
                continue
            if masks is not None and not any(fnmatch.fnmatch(f.lower(), m.lower()) for m in masks):
                continue
            if not _secret(f):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            if not _excluded(rel, excluded):
                found.append(os.path.join(dirpath, f))
    return found


def _grep(args, cwd):
    recursive, excluded, targets, pattern_given = False, [], [], False
    i = 0
    while i < len(args):
        a = args[i].strip("'\"")
        if a == "--":
            targets += [x.strip("'\"") for x in args[i + 1:]]
            break
        if a in ("-r", "-R", "--recursive", "--dereference-recursive"):
            recursive = True
        elif a in ("-d", "--directories") and i + 1 < len(args):
            recursive = recursive or args[i + 1].strip("'\"") == "recurse"
            i += 1
        elif a.startswith("--directories="):
            recursive = recursive or a.split("=", 1)[1] == "recurse"
        elif a.startswith(("--exclude=", "--exclude-dir=")):
            excluded.append(a.split("=", 1)[1].strip("'\""))
        elif a in ("--exclude", "--exclude-dir") and i + 1 < len(args):
            excluded.append(args[i + 1].strip("'\""))
            i += 1
        elif a in ("-e", "--regexp", "-f", "--file") and i + 1 < len(args):
            pattern_given = True
            i += 1
        elif a.startswith(("--regexp=", "--file=")):
            pattern_given = True
        elif a.startswith("--"):
            pass
        elif a.startswith("-") and len(a) > 1:
            letters = a[1:]
            if "r" in letters or "R" in letters:
                recursive = True
            if letters.endswith(("e", "f")):
                pattern_given = True
                i += 1
        else:
            targets.append(a)
        i += 1
    if not recursive:
        return None
    if not pattern_given and targets:
        targets = targets[1:]
    return targets or ["."], excluded, True, None


def _rg(args, cwd):
    excluded, targets, hidden, pattern_given, u = [], [], False, False, 0
    i = 0
    while i < len(args):
        a = args[i].strip("'\"")
        if a == "--":
            targets += [x.strip("'\"") for x in args[i + 1:]]
            break
        if a in ("--hidden", "-."):
            hidden = True
        elif a in ("-g", "--glob", "--iglob") and i + 1 < len(args):
            g = args[i + 1].strip("'\"")
            if g.startswith("!"):
                excluded.append(g[1:])
            i += 1
        elif a.startswith(("--glob=", "--iglob=")):
            g = a.split("=", 1)[1].strip("'\"")
            if g.startswith("!"):
                excluded.append(g[1:])
        elif a in ("-e", "--regexp", "-f", "--file") and i + 1 < len(args):
            pattern_given = True
            i += 1
        elif a.startswith("-u") and set(a[1:]) == {"u"}:
            u += len(a) - 1
        elif a.startswith("-"):
            pass
        else:
            targets.append(a)
        i += 1
    if u >= 2:
        hidden = True
    if not pattern_given and targets:
        targets = targets[1:]
    return targets or ["."], excluded, hidden, None


def _findstr(args, cwd):
    opts = [a.strip("'\"").lower() for a in args if a.startswith("/")]
    if not any(o == "/s" or (o.startswith("/") and "s" in o[1:] and ":" not in o) for o in opts):
        return None
    rest = [a.strip("'\"") for a in args if not a.startswith("/")]
    masks = rest[1:] if len(rest) > 1 else ["*"]
    return [os.path.dirname(m) or "." for m in masks], [], True, [os.path.basename(m) or "*" for m in masks]


SEARCHERS = {"grep": _grep, "egrep": _grep, "fgrep": _grep, "rg": _rg,
             "rg.exe": _rg, "grep.exe": _grep, "findstr": _findstr, "findstr.exe": _findstr}


def secrets_searched(words: list[str], cwd: str | None) -> list[str] | None:
    """For one simple command: the secret files a recursive search would read
    that it does not exclude ([] when none), or None when the command is not
    a recognised recursive search or where it searches cannot be known."""
    if not words:
        return None
    reader = SEARCHERS.get(_name(words[0]))
    if reader is None:
        return None
    got = reader(words[1:], cwd)
    if got is None:
        return None
    targets, excluded, hidden, masks = got
    from mentis.operations import resolve
    found = []
    for t in targets:
        path = resolve(t, cwd)
        if path is None:
            return None
        if os.path.exists(path):
            found += _walk(path, hidden=hidden, masks=masks, excluded=excluded)
    return found
