"""`mentis brain ...`: inspect, reconcile, back up and restore one Brain.

    python -m mentis.brain inspect <folder> [--json]
    python -m mentis.brain status <brain>
    python -m mentis.brain verify <brain>
    python -m mentis.brain reconcile <brain>
    python -m mentis.brain rebuild-derived <brain>
    python -m mentis.brain backup <brain> [--dest DIR] [--portable]
    python -m mentis.brain verify-backup <backup> [--brain BRAIN]
    python -m mentis.brain restore-plan <brain> <backup>
    python -m mentis.brain restore <brain> <backup> --confirm <plan digest>
    python -m mentis.brain restore <brain> --resume <quarantine id>
    python -m mentis.brain discard-quarantine <brain> <quarantine id> --confirm <id>
    python -m mentis.brain export <brain> (--conversation ID | --turn ID | --item ID) --out <zip>
    python -m mentis.brain import <brain> <zip> --preview [--json]
    python -m mentis.brain import <brain> <zip> --apply [--json] [--backup-dest DIR]

Nothing here runs by itself and nothing restores automatically (D4): every
command that changes a Brain is typed by somebody. `inspect`, `status`,
`verify`, `verify-backup`, `restore-plan`, `export` and `import --preview`
write nothing to the Brain (`mentis.exchange`); `import --apply` writes the
conflict-free part of an export, after a verified backup, in one transaction
(`mentis.exchange.apply`);
`inspect` (`mentis.brain.inspect`) asks any folder, Brain or not, and
creates nothing.

Exit status: 0 done, 1 checked and found wanting, 2 refused, 3 failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _print(out) -> None:
    print(json.dumps(out, indent=2, default=str))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["inspect"]:
        from mentis.brain import inspect
        return inspect.main(argv[1:])
    from mentis.spine import brainlock, migrations
    ap = argparse.ArgumentParser(prog="python -m mentis.brain",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inspect", help="what a folder holds (read-only)")
    for name in ("status", "verify", "reconcile", "rebuild-derived"):
        sub.add_parser(name).add_argument("brain")
    b = sub.add_parser("backup")
    b.add_argument("brain")
    b.add_argument("--dest", default=None)
    b.add_argument("--portable", action="store_true",
                   help="also copy every referenced stored file, so the "
                        "backup restores on another machine")
    v = sub.add_parser("verify-backup")
    v.add_argument("backup")
    v.add_argument("--brain", default=None,
                   help="the live Brain whose stored files a local recovery "
                        "backup refers to (default: the one it records)")
    p = sub.add_parser("restore-plan")
    p.add_argument("brain")
    p.add_argument("backup")
    r = sub.add_parser("restore")
    r.add_argument("brain")
    r.add_argument("backup", nargs="?")
    r.add_argument("--confirm", default=None,
                   help="the digest restore-plan printed for this state")
    r.add_argument("--resume", default=None, metavar="QUARANTINE_ID",
                   help="complete or reverse an interrupted restore")
    r.add_argument("--reverse", action="store_true",
                   help="with --resume: put the quarantined Brain back")
    d = sub.add_parser("discard-quarantine")
    d.add_argument("brain")
    d.add_argument("quarantine")
    d.add_argument("--confirm", default=None,
                   help="the quarantine id again, typed to confirm")
    x = sub.add_parser("export", help="one Conversation, Turn or item, as "
                                      "a zip outside every Brain (read-only)")
    x.add_argument("brain")
    which = x.add_mutually_exclusive_group(required=True)
    which.add_argument("--conversation", default=None)
    which.add_argument("--turn", default=None)
    which.add_argument("--item", default=None)
    x.add_argument("--out", required=True, help="the zip to write")
    x.add_argument("--by", default=None,
                   help="who is exporting, recorded in the manifest")
    i = sub.add_parser("import", help="what importing an export would do "
                                      "(--preview; read-only), or do the "
                                      "conflict-free part of it (--apply)")
    i.add_argument("brain")
    i.add_argument("zip")
    how = i.add_mutually_exclusive_group()
    how.add_argument("--preview", action="store_true",
                     help="say what an import would do and write nothing")
    how.add_argument("--apply", action="store_true",
                     help="write the conflict-free part, after a verified "
                          "backup, in one transaction")
    i.add_argument("--json", action="store_true",
                   help="the Plan, or what was applied, as JSON")
    i.add_argument("--backup-dest", default=None,
                   help="with --apply: where the backup taken first goes "
                        "(default: the Brain's backups folder)")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.brain) if getattr(a, "brain", None) else None
    if a.cmd in ("export", "import"):
        return _exchange(a, root)
    try:
        if a.cmd == "status":
            st = migrations.status_of(root)
            _print({**st.as_dict(), "explain": st.explain(root)})
            return 0 if st.writable else 1
        if a.cmd == "verify":
            out = migrations.verify(root)
            _print(out)
            return 0 if out["ok"] else 1
        if a.cmd == "reconcile":
            _print(migrations.reconcile(root))
            return 0
        if a.cmd == "rebuild-derived":
            _print(migrations.rebuild_derived(root))
            return 0
        from mentis.spine import backup
        if a.cmd == "backup":
            _print(backup.backup(root, dest=a.dest, portable=a.portable))
            return 0
        if a.cmd == "verify-backup":
            out = backup.verify_backup(os.path.abspath(a.backup),
                                       brain=root)
            _print(out)
            return 0 if out["usable"] else 1
        if a.cmd == "restore-plan":
            _print(backup.restore_plan(root, os.path.abspath(a.backup)))
            return 0
        if a.cmd == "restore":
            if a.resume:
                _print(backup.resume_restore(root, a.resume,
                                             reverse=a.reverse))
                return 0
            if not a.backup:
                print("restore needs a backup, or --resume", file=sys.stderr)
                return 2
            _print(backup.restore(root, os.path.abspath(a.backup),
                                  confirm=a.confirm))
            return 0
        if a.cmd == "discard-quarantine":
            _print(backup.discard_quarantine(root, a.quarantine,
                                             confirm=a.confirm))
            return 0
    except (migrations.BrainMissing, migrations.MigrationRefused,
            brainlock.BrainBusy) as exc:
        print(f"{a.cmd} refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:                                 # noqa: BLE001
        refused = getattr(sys.modules.get("mentis.spine.backup"),
                          "BackupRefused", None)
        if refused is not None and isinstance(exc, refused):
            print(f"{a.cmd} refused: {exc}", file=sys.stderr)
            return 2
        failed = getattr(sys.modules.get("mentis.spine.backup"),
                         "RestoreFailed", None)
        if failed is not None and isinstance(exc, failed):
            print(f"{a.cmd} failed; nothing was deleted: {exc}",
                  file=sys.stderr)
            return 3
        if isinstance(exc, migrations.MigrationFailed):
            print(f"{a.cmd} failed and was rolled back: {exc}",
                  file=sys.stderr)
            return 3
        raise
    return 2


def _exchange(a, root) -> int:
    """`export` and `import --preview`, both read-only, and `import --apply`
    (`mentis.exchange`)."""
    from mentis.exchange import ExchangeRefused
    from mentis.spine import brainlock, migrations
    try:
        if a.cmd == "import" and a.apply:
            from mentis.exchange.apply import ImportFailed, apply, describe
            try:
                out = apply(root, os.path.abspath(a.zip),
                            backup_dest=a.backup_dest)
            except ImportFailed as exc:
                print(f"import failed and was undone: {exc}", file=sys.stderr)
                return 3
            if a.json:
                _print(out)
            else:
                print(describe(out))
            return 0
        if a.cmd == "export":
            from mentis.exchange.export import export
            out = export(root, out=a.out, conversation=a.conversation,
                         turn=a.turn, item=a.item, by=a.by)
            _print({"path": out["path"], "marks": out["marks"],
                    "origin": out["origin"], "counts": out["counts"],
                    "blobs_missing": out["blobs_missing"]})
            return 0
        if not a.preview:
            print("import refused: say --preview (what an import would do, "
                  "writing nothing) or --apply (do the conflict-free part)",
                  file=sys.stderr)
            return 2
        from mentis.exchange import format as fmt
        from mentis.exchange.preview import classify, describe
        from mentis.spine.store import Store
        export = fmt.read(os.path.abspath(a.zip))
        st = Store(root, access="read")
        try:
            plan = classify(st, export)
        finally:
            st.close()
        if a.json:
            _print(plan.as_dict())
        else:
            print(describe(plan))
        return 1 if plan.refused else 0
    except (ExchangeRefused, migrations.BrainMissing,
            migrations.BrainNotWritable, brainlock.BrainBusy) as exc:
        print(f"{a.cmd} refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
