"""BRAIN-SEED: a small Brain written by Python's own commands.

    <fixtures>\\venv\\Scripts\\python.exe tools/r1/seed_brain.py <new directory>
    <fixtures>\\venv\\Scripts\\python.exe tools/r1/seed_brain.py <directory> --digest-only

Python's commands take their ids from `uuid.uuid4` and their times from `time.time`.
Both are pinned here, in this process only, before Mentis is imported, so two builds
write the same record. Nothing is normalised: the content digest covers every column of
every table, ids, times and hashes included. The code is `common.code_dir()`, the checkout
of PY_COMMIT, whichever clone this script is run from.

Prints one JSON object, the identity R1-acceptance.md records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import sqlite3
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

SEED = 20261101
START = 1793500000.0
TICK = 0.001
DATA = pathlib.Path(__file__).with_name("seed_data.json")


def _pin() -> None:
    import time

    rng = random.Random(SEED)
    uuid.uuid4 = lambda: uuid.UUID(int=rng.getrandbits(128), version=4)
    clock = [START]

    def now() -> float:
        clock[0] += TICK
        return clock[0]

    time.time = now


def _text(words: str) -> list:
    return [{"type": "text", "text": words}]


def build(dest: pathlib.Path, data: dict) -> None:
    sys.path.insert(0, str(common.code_dir()))
    import mentis.api as api
    from mentis.bootstrap import new_brain

    if dest.exists():
        raise SystemExit(f"{dest} already exists: BRAIN-SEED is built new, never over")
    corpus = api.create_corpus(str(dest))
    new_brain.setup(corpus, data["owner"])
    cv = api.brain(corpus).conversations
    who = {data["owner"]: cv.resolve_participant(data["owner"])}
    for one in data["participants"]:
        who[one["alias"]] = cv.resolve_participant(one["alias"], about=one["about"])
    me = who[data["owner"]]
    for place in data["conversations"]:
        conv = cv.open_conversation(place["name"], about=place["about"], attributed_to=me)
        for alias in place["members"]:
            cv.join(who[alias], conv)
        topics = {n: cv.open_topic(conv, n, attributed_to=me) for n in place["topics"]}
        for post in place["posts"]:
            turn = cv.say(conv, who[post["by"]], _text(post["text"]))
            cv.assign_topic(turn, topics[post["topic"]], attributed_to=me)
    corpus.close()
    # The Brain's own marker, role development. `create_corpus` doesn't write it.
    from mentis.corpus.store import Corpus as Marker
    Marker(str(dest)).create("r1-brain-seed")


def content_digest(brain: pathlib.Path) -> dict:
    """Every row of every table, in a stated order, as SQLite holds it. Normalises nothing.
    Read through a read-only connection to a Brain nothing has open."""
    db = (brain / "corpus.db").as_posix()
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name")]
        h = hashlib.sha256()
        counts = {}
        for table in tables:
            width = len(conn.execute(f'PRAGMA table_info("{table}")').fetchall())
            order = ", ".join(str(i + 1) for i in range(width))
            n = 0
            for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY {order}'):
                h.update(repr((table,) + row).encode("utf-8", "surrogatepass"))
                n += 1
            counts[table] = n
    finally:
        conn.close()
    return {"sha256": h.hexdigest(), "rows": counts}


def identity(brain: pathlib.Path) -> dict:
    return {
        "content": content_digest(brain),
        "corpus_db_sha256": common.sha256_file(brain / "corpus.db"),
        "mentis_corpus_json_sha256": common.sha256_file(brain / "mentis-corpus.json"),
        "trees": {d: common.tree_digest(brain / d)
                  for d in ("artifacts", "instances", "presentation", "derived")},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="build BRAIN-SEED")
    ap.add_argument("dest", type=pathlib.Path)
    ap.add_argument("--digest-only", action="store_true",
                    help="say the identity of an existing build, changing nothing")
    a = ap.parse_args(argv)
    if not a.digest_only:
        _pin()
        build(a.dest, json.loads(DATA.read_text(encoding="utf-8")))
    out = identity(a.dest)
    out["code_commit"] = common.head_of(common.code_dir())
    out["seed_script_blob"] = common.git_blob(__file__)
    out["seed_data_blob"] = common.git_blob(DATA)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
