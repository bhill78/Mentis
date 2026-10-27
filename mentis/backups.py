"""`mentis backups ...`: list, prune and release one Brain's backups (R1).

    python -m mentis.backups list <brain>
    python -m mentis.backups prune <brain> [--confirm [--allow-no-backups]]
    python -m mentis.backups release <brain> <backup-id> --confirm <backup-id>

Nothing prunes by itself. `prune` is a dry run unless `--confirm` is typed,
and it never removes the newest usable backup, a backup an unfinished restore
uses, the last usable backup before a breaking migration (until `release`),
a backup younger than 30 days, or one of the newest 5 usable backups -- nor,
by the same counts, a recovery point (a backup intact in itself), nor any
backup that only damage in the live store makes unusable. Where what it
would remove is every backup the Brain has, it warns, and `--confirm` is
refused unless `--allow-no-backups` is typed too. Both refuse during an
interrupted restore.
Quarantine folders are never pruned; `python -m mentis.brain
discard-quarantine` is the only way one is removed.

Exit status: 0 done, 2 refused.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _print(out) -> None:
    print(json.dumps(out, indent=2, default=str))


def main(argv=None) -> int:
    from mentis.spine import backup, brainlock, migrations
    ap = argparse.ArgumentParser(prog="python -m mentis.backups",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").add_argument("brain")
    p = sub.add_parser("prune")
    p.add_argument("brain")
    p.add_argument("--confirm", action="store_true",
                   help="remove what the dry run lists (default: dry run)")
    p.add_argument("--allow-no-backups", action="store_true",
                   help="with --confirm: remove them even when that leaves "
                        "the Brain with no backup at all")
    r = sub.add_parser("release")
    r.add_argument("brain")
    r.add_argument("backup_id")
    r.add_argument("--confirm", default=None,
                   help="the backup id again, typed to confirm")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.brain)
    try:
        if a.cmd == "list":
            _print(backup.list_backups(root))
        elif a.cmd == "prune":
            out = backup.prune(root, confirm=a.confirm,
                               allow_no_backups=a.allow_no_backups)
            if out.get("warning"):
                print(f"warning: {out['warning']}", file=sys.stderr)
            _print(out)
        elif a.cmd == "release":
            _print(backup.release(root, a.backup_id, confirm=a.confirm))
        return 0
    except (backup.BackupRefused, migrations.BrainMissing,
            brainlock.BrainBusy) as exc:
        print(f"{a.cmd} refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
