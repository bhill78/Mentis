"""`mentis brain inspect <folder> [--json]`: what a folder holds, before
anybody chooses it. READ-ONLY: nothing is created, written or locked, and a
folder that does not exist is not made.

    {"folder": <absolute path>, "is_brain": bool, "is_backup": bool,
     "usable": bool,
     "schema": "compatible" | "will-upgrade" | "too-new" | "needs-attention"
               | "backup" | null,
     "backup_first": bool, "owner": "@x" | null, "owners": [...],
     "records": int | null, "version": int | null, "min_reader": int | null,
     "target": int, "state": <mentis.spine.migrations state> | null,
     "explain": "<plain words>"}

(installer plan adm-06dbd34701bf, S5; frozen, the desktop app reads it.)

- `is_brain` false: there is no `corpus.db`, or it is not a database Mentis
  can read. `schema` is null and `usable` false.
- `compatible`: this release serves it as it is.
- `will-upgrade`: install adopts it -- a backup first, then the migration
  (or the reconcile of an older release's open) it needs. `backup_first`.
- `too-new`: it needs a newer Mentis.
- `needs-attention`: its schema ledger does not add up, or a restore of it
  is unfinished; nothing will be repaired by installing.
- `backup` (`is_backup` true; I4): a backup of a Brain -- it holds
  BACKUP.json, or sits in the backup layout
  (`backups/<corpus id>/<stamp>-<kind>`), or is a folder of backups. Never
  usable, whatever its corpus.db says: serving it would change it and it
  would no longer restore. `install --brain` refuses it (`backup`).

`usable` is `compatible` or `will-upgrade`. `owner` is the owner alias the
Brain records (the first, when several), as install would adopt it; `records`
the number of Entries.

The same reads install makes before it adopts a Brain (`migrations.status_of`
and the owner rows of `installer._brain_owner`), on query-only connections.
Stdlib only, so the package zip answers it on a bare Python before anything is
installed: `python -I <package.zip> brain inspect <folder> --json`.

Exit status: 0 a Brain this release can use, 2 refused (not a Brain, too new,
needs attention), 3 failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

#: mentis.bootstrap.baseline's names for the owner Participant (that module
#: imports the whole API, which a bare Python cannot); a test keeps them equal
OWNER_ABOUT = "the owner"

COMPATIBLE, WILL_UPGRADE = "compatible", "will-upgrade"
TOO_NEW, NEEDS_ATTENTION = "too-new", "needs-attention"
BACKUP = "backup"


def _owners_and_records(db: str) -> tuple[list, int]:
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT body FROM entry WHERE def_name = 'participant' "
            "AND family = 'entry' AND link_relation IS NULL "
            "ORDER BY seq").fetchall()
        count = conn.execute("SELECT COUNT(*) FROM entry").fetchone()[0]
    finally:
        conn.close()
    owners = []
    for (body,) in rows:
        try:
            b = json.loads(body)
        except (TypeError, ValueError):
            continue
        if isinstance(b, dict) and b.get("about") == OWNER_ABOUT \
                and b.get("alias"):
            owners.append(b["alias"])
    return owners, int(count)


#: mentis.spine.backup's names (that module imports the store); a test keeps
#: them equal
BACKUP_MANIFEST = "BACKUP.json"
BACKUP_KINDS = ("local-recovery", "portable")
BACKUPS_DIR = "backups"


def _has_manifest(folder: str) -> bool:
    return os.path.isfile(os.path.join(folder, BACKUP_MANIFEST))


def backup_reason(folder) -> str | None:
    """Why `folder` is a backup of a Brain rather than a Brain, in words, or
    None when it is not one. A backup holds BACKUP.json; the backup layout is
    `<brains>/backups/<corpus id>/<stamp>-<kind>[.partial]/`, and choosing
    the `backups` folder or a corpus's folder under it counts too. Reads
    only; a folder that is not there is not a backup."""
    folder = os.path.abspath(str(folder))
    if not os.path.isdir(folder):
        return None
    if _has_manifest(folder):
        return f"it holds {BACKUP_MANIFEST}"
    name = os.path.basename(folder)
    parent = os.path.dirname(folder)
    grand = os.path.basename(os.path.dirname(parent))
    base = name[:-len(".partial")] if name.endswith(".partial") else name
    if grand.casefold() == BACKUPS_DIR and base.endswith(
            tuple("-" + k for k in BACKUP_KINDS)):
        return (f"it is a backup's folder ({BACKUPS_DIR}/"
                f"{os.path.basename(parent)}/{name})")
    try:
        children = [os.path.join(folder, c) for c in os.listdir(folder)]
    except OSError:
        return None
    here = name.casefold() == BACKUPS_DIR
    under = os.path.basename(parent).casefold() == BACKUPS_DIR
    if (here or under) and any(os.path.isdir(c) and (
            _has_manifest(c) or (here and any(
                _has_manifest(os.path.join(c, g)) for g in _listdir(c))))
            for c in children):
        return f"it is a folder of backups ({name})"
    return None


def _listdir(path: str) -> list:
    try:
        return os.listdir(path)
    except OSError:
        return []


def inspect(folder) -> dict:
    """What `folder` holds. Never raises for what it finds; never writes."""
    from mentis.spine import migrations
    folder = os.path.abspath(str(folder))
    out = {"folder": folder, "is_brain": False, "is_backup": False,
           "usable": False,
           "schema": None, "backup_first": False, "owner": None,
           "owners": [], "records": None, "version": None,
           "min_reader": None, "target": migrations.target(),
           "state": None, "explain": ""}
    db = os.path.join(folder, migrations.DB)
    if not os.path.isdir(folder):
        out["explain"] = f"There is no folder at {folder}."
        return out
    why = backup_reason(folder)
    if why:
        # I4: never usable, whatever its corpus.db would say -- serving it
        # would change it and it would no longer restore
        out.update(is_backup=True, schema=BACKUP,
                   is_brain=os.path.isfile(db),
                   explain=(f"{folder} is a backup of a Brain ({why}), not a "
                            "Brain to use: serving it would change it, and "
                            "it would no longer restore. Choose the Brain "
                            "itself, or restore the backup first."))
        return out
    if not os.path.isfile(db):
        out["explain"] = (f"{folder} is not a Mentis Brain: it holds no "
                          f"{migrations.DB}.")
        return out
    try:
        st = migrations.status_of(folder)
    except sqlite3.DatabaseError as exc:
        out["explain"] = (f"{folder} is not a Mentis Brain: its "
                          f"{migrations.DB} cannot be read as a database "
                          f"({exc}).")
        return out
    except Exception as exc:                                  # noqa: BLE001
        # a restore of it is unfinished (brainlock.refuse_if_restoring), or
        # anything else that stops it being read
        out.update(is_brain=True, schema=NEEDS_ATTENTION,
                   explain=f"{type(exc).__name__}: {exc}")
        return out
    out.update(is_brain=True, state=st.state, version=st.version,
               min_reader=st.min_reader, target=st.target,
               explain=st.explain(folder))
    if st.state == migrations.NEEDS_NEWER:
        out["schema"] = TOO_NEW
    elif st.state == migrations.NEEDS_ATTENTION:
        out["schema"] = NEEDS_ATTENTION
    elif st.state in (migrations.UNADOPTED, migrations.NEEDS_MIGRATE) \
            or st.legacy_open:
        out["schema"] = WILL_UPGRADE
        out["backup_first"] = True
    else:
        out["schema"] = COMPATIBLE
    try:
        out["owners"], out["records"] = _owners_and_records(db)
    except sqlite3.DatabaseError as exc:
        # an unadopted Brain may predate a column; its schema state stands
        out["explain"] += f" (its owner and records could not be read: {exc})"
    out["owner"] = out["owners"][0] if out["owners"] else None
    out["usable"] = out["schema"] in (COMPATIBLE, WILL_UPGRADE)
    return out


def words(r: dict) -> str:
    if not r["is_brain"] or r.get("is_backup"):
        return r["explain"]
    head = {COMPATIBLE: "a Mentis Brain this release uses as it is",
            WILL_UPGRADE: "a Mentis Brain this release brings up to date, "
                          "taking a backup first",
            TOO_NEW: "a Mentis Brain that needs a newer Mentis",
            NEEDS_ATTENTION: "a Mentis Brain that needs attention"}[r["schema"]]
    lines = [f"{r['folder']}: {head}.",
             f"  owner: {r['owner'] or '(none recorded)'}",
             f"  records: {r['records'] if r['records'] is not None else '?'}",
             f"  {r['explain']}"]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mentis brain inspect",
                                 description="What a folder holds; read-only.")
    ap.add_argument("folder")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = inspect(a.folder)
    except Exception as exc:                                  # noqa: BLE001
        print(f"inspect failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    if a.json:
        print(json.dumps(r, indent=1, ensure_ascii=True))
    else:
        print(words(r))
    return 0 if r["usable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
