"""What `test_r2_window.py` has Python's own commands do to a Brain.

    python r2_side.py attach <brain>        posts holding one attachment; prints what they are
    python r2_side.py purge <brain> <ref>   ends possession of it, as the owner does
"""

from __future__ import annotations

import json
import sys

import mentis.api as api
from mentis import artifacts


def _open(brain):
    corpus = api.open_corpus(brain)
    return corpus, api.brain(corpus).conversations


def attach(brain) -> dict:
    corpus, cv = _open(brain)
    owner = cv.resolve_participant("@r1-owner")
    home = next(e["id"] for e in corpus.entries_of_kind("conversation")
                if e["body"].get("name") == "R1 known conversation")
    held = artifacts.hold(corpus, cv, b"bytes that will be purged", act=artifacts.SUBMITTED,
                          actor=owner, source=f"submission:{owner}", door="human-ingress",
                          conversation=home, claimed_name="purged.txt",
                          claimed_media_type="text/plain")
    ref = held["admission"]
    posts = {name: cv.say(home, owner, [artifacts.part(ref, corpus=corpus)])
             for name in ("read_before", "read_after")}
    corpus.close()
    return {"ref": ref, "home": home, "owner": owner, **posts}


def purge(brain, ref) -> dict:
    corpus, cv = _open(brain)
    owner = cv.resolve_participant("@r1-owner")
    done = artifacts.purge(corpus, cv, ref, by=owner, because="R2's purge test")
    corpus.close()
    return {"state": done["state"]}


if __name__ == "__main__":
    what, brain, *rest = sys.argv[1:]
    print(json.dumps({"attach": attach, "purge": purge}[what](brain, *rest)))
