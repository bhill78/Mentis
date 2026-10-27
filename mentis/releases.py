"""`mentis releases list|prune`: the release folders under one install root.

    mentis releases list  [--root ROOT]
    mentis releases prune [--root ROOT] [--confirm]

NOTHING IS EVER DELETED AUTOMATICALLY. `prune` is a dry run that lists what it
would remove and why everything else is kept; only `--confirm` removes, and
it removes exactly what the same rules list at that moment. Nothing else in
Mentis calls it.

A RELEASE IS KEPT, never pruned, when it is (owner decision, Stage 1 brief):
- `current` or `previous` in `state/install.json`;
- named anywhere in an unfinished update (`state/update.journal.json`) or in
  `state/needs-attention.json`;
- for some kept backup, the newest release able to open that backup's
  schema (its RELEASE.json `reads_schema` and `schema_target`, below);
- one of the newest 5 releases.

WHAT IS NOT KNOWN IS KEPT. A folder under `releases/` that ends in
`.partial` (a release being staged, or left by a staging that stopped), is
not named `<semver>+<commit12>`, has no readable format 1 RELEASE.json, or
whose RELEASE.json version is not its name's (something put there by hand)
is listed as unrecognised: it is never removed and never counts toward the
newest 5. An install.json, journal or
needs-attention file that exists but cannot be read refuses the prune
outright, because what it protects cannot be told. A backup whose
BACKUP.json cannot be read protects the newest release outright. A link or
junction is never followed or removed.

WHICH RELEASE OPENS A BACKUP. A backup records the ledger `version` and
`min_reader` of the Brain it copied (None/None for a Brain that predates the
ledger, which every release since adoption can adopt, so it reads as 0). A
release opens it when `reads_schema.min <= version` and either `version <=
schema_target` (it is at, or migrates to, that release's target) or
`min_reader <= schema_target` (a newer Brain this release may still read) --
the same gate `mentis.spine.migrations.inspect` applies at open.

"NEWEST" is SemVer precedence of RELEASE.json `version`, ties broken by
`source_date`, then by folder name.

Removing a release first lifts its read-only lock (`mentis.readonly.unlock`),
then deletes the folder; a folder that fails part-way is reported, never
retried by itself.

Exit status: 0 done (or nothing to do), 1 a removal failed, 2 refused.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys

from mentis import home

KEEP_NEWEST = 5
BACKUP_MANIFEST = "BACKUP.json"   # mentis.spine.backup.MANIFEST
PARTIAL = ".partial"              # mentis.spine.backup.PARTIAL

_SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


class Refused(RuntimeError):
    pass


# -- SemVer precedence -----------------------------------------------------------

def semver_key(version: str) -> tuple:
    """A sort key giving SemVer 2.0.0 precedence (build metadata ignored).
    An unparseable version sorts before every valid one."""
    m = _SEMVER.fullmatch(str(version))
    if not m:
        return (0,)
    core = tuple(int(x) for x in m.group(1, 2, 3))
    pre = m.group(4)
    if pre is None:
        # a release outranks every pre-release of the same core
        return (1, core, 1, ())
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p)
                for p in pre.split("."))
    return (1, core, 0, ids)


# -- reading the root ----------------------------------------------------------------

def _read_state(path: pathlib.Path) -> dict | None:
    """None when absent; Refused when present and unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Refused(f"{path} cannot be read ({e}); what it protects "
                      f"cannot be told, so nothing is pruned") from e
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise Refused(f"{path} is not readable JSON; what it protects "
                      f"cannot be told, so nothing is pruned") from e
    if not isinstance(doc, dict):
        raise Refused(f"{path} is not a JSON object; nothing is pruned")
    return doc


def _strings(doc) -> set[str]:
    out = set()
    if isinstance(doc, str):
        out.add(doc)
    elif isinstance(doc, dict):
        for k, v in doc.items():
            out |= _strings(k) | _strings(v)
    elif isinstance(doc, list):
        for v in doc:
            out |= _strings(v)
    return out


def _names_in(doc, names: set[str]) -> set[str]:
    """Release folder names a state document mentions, as a name or as the
    last part of a path. Read wholesale, so a field another module adds is
    not missed."""
    hit = set()
    for s in _strings(doc):
        for cand in (s, s.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1]):
            if cand in names:
                hit.add(cand)
    return hit


def _is_link(p: pathlib.Path) -> bool:
    return p.is_symlink() or bool(getattr(os.path, "isjunction",
                                          lambda _: False)(p))


def _release_doc(folder: pathlib.Path) -> dict | None:
    try:
        doc = json.loads((folder / home.RELEASE_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("format") != 1 \
            or not isinstance(doc.get("version"), str):
        return None
    return doc


def scan_releases(layout: home.Layout) -> tuple[list[dict], list[dict]]:
    """(releases newest first, unrecognised folders)."""
    rels, odd = [], []
    try:
        children = sorted(layout.releases.iterdir())
    except FileNotFoundError:
        return [], []
    for p in children:
        if not p.is_dir() and not _is_link(p):
            continue
        if _is_link(p):
            odd.append({"name": p.name, "path": str(p),
                        "why": "a link or junction; never followed"})
            continue
        if p.name.endswith(PARTIAL):
            # an install or update staging it, or one killed while it did
            odd.append({"name": p.name, "path": str(p),
                        "why": "still being staged, or left by a staging "
                               "that stopped"})
            continue
        # the one definition the installer, the updater and Layout.release
        # use, so all of them agree on what a release is
        if not home.is_release_name(p.name):
            odd.append({"name": p.name, "path": str(p),
                        "why": "not named <version>+<commit12>"})
            continue
        doc = _release_doc(p)
        if doc is None:
            odd.append({"name": p.name, "path": str(p),
                        "why": f"no readable format 1 {home.RELEASE_FILE}"})
            continue
        if doc["version"] != p.name.rpartition("+")[0]:
            odd.append({"name": p.name, "path": str(p),
                        "why": f"its {home.RELEASE_FILE} says version "
                               f"{doc['version']}, not its name's"})
            continue
        reads = doc.get("reads_schema") or {}
        rels.append({
            "name": p.name, "path": str(p), "version": doc["version"],
            "commit": doc.get("commit"), "source_date": doc.get("source_date"),
            "schema_target": doc.get("schema_target"),
            "reads_schema": {"min": reads.get("min"), "max": reads.get("max")},
            "min_reader_after": doc.get("min_reader_after"),
            "breaking": doc.get("breaking"),
        })
    rels.sort(key=lambda r: (semver_key(r["version"]),
                             str(r["source_date"] or ""), r["name"]),
              reverse=True)
    return rels, odd


def _backup_dirs(layout: home.Layout, install: dict | None) -> list[pathlib.Path]:
    """Where backups of this install's Brain are kept: `<root>/backups`, and
    `mentis brain backup`'s default beside a Brain kept elsewhere."""
    places = [layout.backups]
    brain = (install or {}).get("brain")
    if isinstance(brain, str) and brain:
        places.append(pathlib.Path(brain).resolve().parent / "backups")
    seen, out = set(), []
    for p in places:
        key = os.path.normcase(str(p.resolve()))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _unreadable_backups(path: pathlib.Path, e: OSError) -> Refused:
    return Refused(f"{path} cannot be read ({e}); which releases its backups "
                   f"need cannot be told, so nothing is pruned")


def scan_backups(layout: home.Layout, install: dict | None) -> list[dict]:
    """Every complete backup under the backup places: `<place>/<corpus>/<b>/`
    with a BACKUP.json. Read from its manifest only; the Brain is not
    opened, and no lock is taken."""
    out = []
    for place in _backup_dirs(layout, install):
        try:
            corpora = sorted(place.iterdir())
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError as e:
            raise _unreadable_backups(place, e) from e
        for corpus in corpora:
            if not corpus.is_dir():
                continue
            try:
                kept = sorted(corpus.iterdir())
            except (FileNotFoundError, NotADirectoryError):
                continue
            except OSError as e:
                raise _unreadable_backups(corpus, e) from e
            for b in kept:
                if not b.is_dir() or b.name.endswith(PARTIAL):
                    continue
                man = b / BACKUP_MANIFEST
                if not man.exists():
                    continue
                try:
                    led = json.loads(man.read_text("utf-8")).get("ledger") or {}
                    version = led.get("version")
                    reader = led.get("min_reader")
                    ok = (version is None or isinstance(version, int)) and \
                         (reader is None or isinstance(reader, int))
                except (OSError, ValueError, AttributeError):
                    ok, version, reader = False, None, None
                out.append({"path": str(b), "readable": ok,
                            "version": version, "min_reader": reader})
    return out


def opens(release: dict, version: int | None, min_reader: int | None) -> bool:
    """Whether `release` can open a Brain at this ledger version."""
    lo = (release.get("reads_schema") or {}).get("min")
    tgt = release.get("schema_target")
    if not isinstance(lo, int) or not isinstance(tgt, int):
        return False
    v = 0 if version is None else version
    if v < lo:
        return False
    if v <= tgt:
        return True
    return isinstance(min_reader, int) and min_reader <= tgt


# -- the retention rules -----------------------------------------------------------------

def plan(root: os.PathLike | str | None = None) -> dict:
    """What prune would keep and remove, and why. Reads only."""
    layout = home.Layout(root)
    install = _read_state(layout.install_json)
    journal = _read_state(layout.journal)
    attention = _read_state(layout.needs_attention)
    rels, odd = scan_releases(layout)
    names = {r["name"] for r in rels}
    why: dict[str, list[str]] = {r["name"]: [] for r in rels}

    for role in ("current", "previous"):
        for n in _names_in((install or {}).get(role), names):
            why[n].append(f"the {role} release in install.json")
    if journal is not None:
        state = journal.get("state")
        for n in _names_in(journal, names):
            why[n].append(f"named in the unfinished update journal "
                          f"(state {state})")
    if attention is not None:
        for n in _names_in(attention, names):
            why[n].append("named in needs-attention.json")
    backups = scan_backups(layout, install)
    for b in backups:
        if not b["readable"]:
            if rels:
                why[rels[0]["name"]].append(
                    f"backup {b['path']} cannot be read, so the newest "
                    f"release is kept for it")
            continue
        able = next((r for r in rels
                     if opens(r, b["version"], b["min_reader"])), None)
        if able is not None:
            why[able["name"]].append(
                f"the newest release able to open backup {b['path']} "
                f"(schema {b['version']})")
    for i, r in enumerate(rels[:KEEP_NEWEST], start=1):
        why[r["name"]].append(f"one of the newest {KEEP_NEWEST} (#{i})")

    for r in rels:
        r["role"] = [role for role in ("current", "previous")
                     if r["name"] in _names_in((install or {}).get(role),
                                               names)]
        r["kept_because"] = why[r["name"]]
        r["prunable"] = not why[r["name"]]
    return {"root": str(layout.root), "releases": rels,
            "unrecognised": odd, "backups_considered": len(backups),
            "update_unfinished": journal is not None,
            "needs_attention": attention is not None,
            "would_remove": [r["name"] for r in rels if r["prunable"]]}


def _writable(func, path, _exc):
    """rmtree's error handler: a file another lock left read-only (POSIX mode
    bits, the Windows read-only attribute) is made writable and retried."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    func(path)


def _remove(layout: home.Layout, rel: dict) -> dict:
    p = pathlib.Path(rel["path"])
    parent = layout.releases.resolve()
    if _is_link(p) or p.resolve().parent != parent:
        return {"name": rel["name"], "removed": False,
                "error": "not a folder directly inside releases/"}
    from mentis import readonly
    try:
        readonly.unlock(p)
        if sys.version_info >= (3, 12):
            shutil.rmtree(p, onexc=_writable)
        else:
            shutil.rmtree(p, onerror=_writable)
    except (OSError, subprocess.SubprocessError) as e:
        # an icacls timeout or failure included: reported, and prune goes on
        return {"name": rel["name"], "removed": False,
                "error": f"{type(e).__name__}: {e}",
                "left": p.exists()}
    return {"name": rel["name"], "removed": True}


def prune(root: os.PathLike | str | None = None, confirm: bool = False) -> dict:
    out = plan(root)
    out["dry_run"] = not confirm
    if not confirm:
        return out
    layout = home.Layout(root)
    out["removed"] = [_remove(layout, r) for r in out["releases"]
                      if r["prunable"]]
    return out


# -- the command ---------------------------------------------------------------------------

def _say_list(out: dict) -> str:
    lines = [f"Releases under {out['root']}:"]
    if not out["releases"]:
        lines.append("  (none)")
    for r in out["releases"]:
        role = f" [{', '.join(r['role'])}]" if r["role"] else ""
        lines.append(f"  {r['name']}{role}  schema {r['schema_target']} "
                     f"(reads {r['reads_schema']['min']}..{r['reads_schema']['max']})")
        for k in r["kept_because"]:
            lines.append(f"      kept: {k}")
        if r["prunable"]:
            lines.append("      could be pruned")
    for o in out["unrecognised"]:
        lines.append(f"  {o['name']}  unrecognised ({o['why']}); never pruned")
    return "\n".join(lines)


def _say_prune(out: dict) -> str:
    lines = [_say_list(out), ""]
    if out["dry_run"]:
        if out["would_remove"]:
            lines.append("Dry run. `mentis releases prune --confirm` would "
                         "remove: " + ", ".join(out["would_remove"]))
        else:
            lines.append("Dry run. Nothing would be removed.")
        return "\n".join(lines)
    if not out["removed"]:
        lines.append("Nothing was removed.")
    for r in out["removed"]:
        lines.append(f"removed {r['name']}" if r["removed"] else
                     f"could not remove {r['name']}: {r['error']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mentis releases",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "prune"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=None,
                       help="install root (default: MENTIS_HOME, else this "
                            "OS's root)")
        p.add_argument("--json", action="store_true", help="print JSON")
    sub.choices["prune"].add_argument(
        "--confirm", action="store_true",
        help="remove what the dry run lists (default: dry run)")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["releases"]:
        # `mentis releases ...`: the CLI hands over the whole argv,
        # command word first
        argv = argv[1:]
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            out = plan(a.root)
            text = _say_list(out)
        else:
            out = prune(a.root, confirm=a.confirm)
            text = _say_prune(out)
    except Refused as e:
        print(f"{a.cmd} refused: {e}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=1) if a.json else text)
    if a.cmd == "prune" and not out["dry_run"]:
        return 0 if all(r["removed"] for r in out["removed"]) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
