"""Move a Brain's schema forward, explicitly.

    python -m mentis.migrate <brain> --plan                     # writes nothing
    python -m mentis.migrate <brain> --apply [--allow-breaking]

`--plan` says where the Brain is (S), where this Mentis needs it (T), each
pending migration and its kind, the resulting `min_reader`, and whether a
release older than the schema ledger could still open the result.

`--apply` runs every pending migration in ONE transaction, checks the result
before COMMIT, and holds the Brain's exclusive lock throughout -- so it refuses
while a server, worker or CLI has the Brain open. Opening a Brain never does
any of this (D2); see `mentis.spine.migrations`.

Exit status: 0 done (or nothing to do), 2 refused, 3 failed and rolled back.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv=None) -> int:
    from mentis.spine import brainlock, migrations
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("brain")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--allow-breaking", action="store_true",
                    help="permit a migration that raises min_reader")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.brain)
    try:
        if a.plan:
            out = migrations.plan(root)
        else:
            out = migrations.apply(root, allow_breaking=a.allow_breaking)
    except (migrations.BrainMissing, migrations.MigrationRefused,
            brainlock.BrainBusy) as exc:
        print(f"migrate refused: {exc}", file=sys.stderr)
        return 2
    except migrations.MigrationFailed as exc:
        print(f"migrate failed and was rolled back; the Brain is unchanged: "
              f"{exc}", file=sys.stderr)
        return 3
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
