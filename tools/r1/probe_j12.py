"""What repeating the three sampled unkeyed writes does, on Python alone and BRAIN-SEED.

    <fixtures>\\venv\\Scripts\\python.exe tools/r1/probe_j12.py <seed master> <work dir>

Makes row J12's expected result known rather than read from source. Each write is sent twice with
the same arguments, through `POST /api/worker` under a session grant, on a fresh copy, and the
result is counted from the record once the server has stopped. Never the live Brain. Prints JSON.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402
import py_alone  # noqa: E402

URL = f"http://127.0.0.1:{py_alone.PORT}"
CAPABILITY_HEADER = "X-Mentis-Worker"
ID = re.compile(r"\b(ent|opr)-[0-9a-f]{12}\b")


def post(path: str, body: dict, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(URL + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            return fh.status, json.loads(fh.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    seed, work = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    work.mkdir(parents=True)
    brain = work / "brain"
    shutil.copytree(seed, brain)
    out: dict = {"code_commit": common.head_of(common.code_dir())}

    with py_alone.running(brain):
        status, session = post("/api/worker/session", {"runtime": "claude"},
                               {"X-Mentis-Client": "1"})
        assert status == 200, session
        grant = {CAPABILITY_HEADER: session["grant"]}

        def op(operation: str, /, **args):
            return post("/api/worker",
                        {"corpus": str(brain.resolve()), "op": operation, "args": args}, grant)

        # open_conversation, twice, the same name.
        one = op("open_conversation", name="J12 repeated")
        two = op("open_conversation", name="J12 repeated")
        out["open_conversation"] = {"statuses": [one[0], two[0]],
                                    "differ": one[1]["conversation"] != two[1]["conversation"]}
        here = one[1]["conversation"]

        # record_discovered_work, twice, the same words, under one request.
        _, trunk = op("record_request", conversation=here, text="J12 trunk",
                      follow_up={"depth": 1})
        one = op("record_discovered_work", under=trunk["expectation"], work="J12 finding")
        two = op("record_discovered_work", under=trunk["expectation"], work="J12 finding")
        out["record_discovered_work"] = {
            "statuses": [one[0], two[0]],
            "differ": one[1]["expectation"] != two[1]["expectation"]}

        # take_up, twice, the first finding.
        picked = one[1]["expectation"]
        one = op("take_up", expectation=picked, under=trunk["expectation"])
        two = op("take_up", expectation=picked, under=trunk["expectation"])
        out["take_up"] = {"statuses": [one[0], two[0]],
                          "first_generation": one[1].get("generation"),
                          "second_said": two[1].get("error", "").replace(picked, "<expectation>")}
        here_id, picked_id = here, picked

    db = (brain / "corpus.db").as_posix()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        count = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
        out["open_conversation"]["conversations_named"] = count(
            "SELECT COUNT(*) FROM entry WHERE def_name='conversation' "
            "AND json_extract(body,'$.name')='J12 repeated'")
        out["record_discovered_work"]["turns_saying"] = count(
            "SELECT COUNT(*) FROM entry WHERE def_name='contribution' "
            "AND body LIKE '%J12 finding%'")
        out["record_discovered_work"]["work_discovered_acts"] = count(
            "SELECT COUNT(*) FROM operational WHERE act='work-discovered' "
            "AND conversation=?", here_id)
    finally:
        conn.close()
    # `take_up`'s one assignment, read with Python's own reading of it.
    sys.path.insert(0, str(common.code_dir()))
    import mentis.api as api
    corpus = api.open_corpus(str(brain), access="read")
    try:
        cv = api.conversations(corpus)
        out["take_up"]["carrier_is_the_session"] = (
            cv.assigned_carrier(picked_id)["carrier"] == session["participant"])
    finally:
        corpus.close()
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
