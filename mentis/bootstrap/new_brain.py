"""Set up a new Brain: the baseline, then the welcome tour.

    python -m mentis.bootstrap <brain> --owner @alias [--runtime claude]
        [--match KEY=<entry>|new ...] [--check] [--no-tour] [--update-tour]

Run once by the owner. On a path with no Brain it CREATES one, explicitly
(`mentis.api.create_corpus`); on a Brain that predates the schema ledger it
refuses and says to run `python -m mentis.migrate` -- it never adopts one. Both steps share one
transaction, so a refusal or a content error in either writes nothing. Each is
idempotent: run again, it writes nothing. A Brain that already has an
earlier welcome tour gets a newer version's additions only with --update-tour.
See baseline.py and welcome.py.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import mentis.api as api
from mentis.bootstrap import baseline, welcome


def setup(corpus, owner_alias, *, runtime=None, match=None, no_tour=False,
          update_tour=False, dry_run=False, spec=None, tour=None) -> dict:
    # Broken content is refused before anything is written.
    tour = tour if tour is not None else welcome.load()
    if not no_tour:
        welcome.validate_spec(tour)
    with corpus.atomic():
        base = baseline.install(corpus, owner_alias, runtime=runtime,
                                match=match, spec=spec, dry_run=dry_run)
        out = {}
        if not (no_tour or dry_run):
            out = welcome.bootstrap(corpus, update=update_tour, spec=tour)
    return {"baseline": base, "tour": out.get("tour"),
            "tour_update": out.get("tour_update"),
            "tour_update_available": out.get("tour_update_available")}


def open_or_create(path: str):
    """The Brain at `path`, created first when there is none (D2: creation is
    this explicit act). An existing Brain must be writable as it stands."""
    import os
    from mentis.spine.migrations import BrainNotWritable
    if not os.path.isfile(os.path.join(path, "corpus.db")):
        print(f"no Brain at {path}: creating one", file=sys.stderr)
        return api.create_corpus(path)
    try:
        return api.open_corpus(path, access="write")
    except BrainNotWritable as exc:
        raise baseline.BootstrapRefused(str(exc)) from exc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    baseline.arguments(ap)
    ap.add_argument("--no-tour", action="store_true")
    ap.add_argument("--update-tour", action="store_true",
                    help="append a newer tour's additions to an existing tour")
    a = ap.parse_args(argv)
    try:
        corpus = open_or_create(str(pathlib.Path(a.corpus).resolve()))
    except baseline.BootstrapRefused as exc:
        print(f"bootstrap refused: {exc}", file=sys.stderr)
        return 1
    try:
        print(json.dumps(setup(corpus, a.owner, runtime=a.runtime,
                               match=baseline.parse_match(a.match),
                               no_tour=a.no_tour, update_tour=a.update_tour,
                               dry_run=a.check), indent=2))
    except baseline.BootstrapRefused as exc:
        print(f"bootstrap refused: {exc}", file=sys.stderr)
        return 1
    finally:
        corpus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
