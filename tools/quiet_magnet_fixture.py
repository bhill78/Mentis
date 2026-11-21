"""Synthetic Quiet Magnet fixture. Setup writes end before the read-only trial.

Run from the candidate checkout with the repository's Python environment:
  python tools/quiet_magnet_fixture.py seed --root .preview/quiet-magnet
  python tools/quiet_magnet_fixture.py snapshot --root .preview/quiet-magnet --out baseline.json

No production path, source binding, MARS connection or existing Brain is accepted.
The separate preview helper refuses writes before forwarding to the Rust front.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
FORMAT = "quiet-magnet-disposable-fixture-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    if REPO not in root.parents:
        raise ValueError("fixture root must be a new directory inside this checkout")
    return root


def seed_brain(brain: Path, *, small: bool = False) -> dict:
    import mentis.api as api
    from mentis import artifacts, magnet
    from mentis.conversation import text
    from mentis.fluid import arrangements, commands

    corpus = api.create_corpus(str(brain))
    cv = api.conversations(corpus)
    by = cv.resolve_participant("@FixtureOwner", about="synthetic disposable preview author")
    other = cv.resolve_participant("@FixtureReader", about="synthetic second participant")
    a = cv.open_conversation("Fixture A — origin", attributed_to=by)
    b = cv.open_conversation("Fixture B — collected source", attributed_to=by)
    for conversation in (a, b):
        cv.join(by, conversation, attributed_to=by)
        cv.join(other, conversation, attributed_to=by)
    origin_post = cv.say(a, by, [text("ORIGIN A: Open the saved yellow Magnet here. Source B and Magnet C are separate Conversations. This labelled post is the return anchor.")])
    cv.say(a, other, [text("ORIGIN A: The page is a disposable read-only preview after setup.")])
    posts: list[str] = []
    for i in range(4 if small else 8):
        posts.append(cv.say(b, by, [text(f"OLDER SOURCE B {i + 1}: dated-out fixture evidence; retained in the source-wide tally.")]))
    # A real time boundary between two groups, without rewriting record timestamps.
    time.sleep(0.02)
    after = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    time.sleep(0.02)
    for i in range(4 if small else 24):
        posts.append(cv.say(b, by if i % 2 == 0 else other, [text(f"SOURCE B {i + 1}: Synthetic field note about the island observatory. This is ordinary collected evidence with a readable author and post origin. No synthesis or Perspective is created.")]))

    held = artifacts.hold(corpus, cv, b"# Fixture field notes\n\nHeld file from source B. Synthetic content for the yellow Magnet preview.\n",
        act="artifact-returned", actor=by, source="fixture:quiet-magnet", door="worker-return",
        claimed_name="fixture-field-notes.md", claimed_media_type="text/markdown", conversation=b,
        because="fixture setup only")
    file_post = cv.say(b, by, [text("SOURCE B: Held field notes, attributed to this source post."), artifacts.part(held["admission"], corpus=corpus)])
    # Attach through the same stage/submit/record functions the human post operation uses.
    staged = artifacts.stage(corpus.root, b"Fixture attachment: instrument calibration, synthetic and disposable.\n", "text/plain")
    with corpus.atomic():
        parts, pending = artifacts.submit_staged(corpus, cv,
            [text("SOURCE B: Attached calibration note, attributed to this source post."),
             {"type": "file", "ref": staged["staged"], "media_type": "text/plain", "alt": "fixture-calibration.txt"}],
            author=other, conversation=b)
        attachment_post = cv.say(b, other, parts)
        artifacts.record_submissions(corpus, cv, pending, author=other, conversation=b, turn=attachment_post)
    image_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=")
    picture = artifacts.hold(corpus, cv, image_bytes, act="artifact-returned", actor=by,
        source="fixture:quiet-magnet", door="worker-return", claimed_name="fixture-observatory.png",
        claimed_media_type="image/png", conversation=b, because="fixture setup only")
    image_post = cv.say(b, by, [text("SOURCE B: Tiny labelled fixture image; navigation target only."), artifacts.part(picture["admission"], corpus=corpus)])
    # A reply checks that navigation retains the actual post/thread origin.
    reply = cv.say(b, other, [text("SOURCE B REPLY: a synthetic follow-up on the first in-range note.")], replies_to=posts[-1])

    def create(name: str, op: str, dates: bool) -> str:
        seed = {"sources": [{"kind": "conversation", "conversation": b}],
                "selection": {"informationTypes": ["post", "file", "attachment", "image"],
                              **({"dates": {"after": after}} if dates else {})},
                "collection": {"mode": "one-time"}, "synthesis": {"mode": "manual"},
                "notifications": {"newItems": False, "changes": False, "failures": False},
                "presentation": {"renderer": "disc"}}
        out = arrangements.create_magnet(corpus.root, a, {"seed": seed, "op": op,
            "attach": {"zone": {"type": "zone", "show": "magnet", "name": name},
                       "base": {"format": "mentis.fluid-arrangement", "version": 2,
                                "tree": {"type": "zone", "id": "fixture-objects", "show": "objects"}}}})
        return out["magnet"]["id"]

    first = create("Island observatory", "quiet-magnet-primary", True)
    missing = create("Without own conversation", "quiet-magnet-missing-own", False)
    # Existing sanctioned operation; this creates C and its durable claim and sets the
    # top-level definition reference. No seed or hand-written file supplies C.
    st = SimpleNamespace(corpus=corpus, cv=cv, agents=None)
    status, own, later = commands.magnet_definition_command(st,
        commands.MAGNET_DEFINITION_ACTS["conversation"], first,
        {"author": by, "name": "Fixture C — Magnet conversation"}, written_by=lambda: "fixture/setup")
    if status >= 300 or later:
        raise RuntimeError(f"own-Conversation setup refused: {status}: {own}")
    c = own["conversation"]
    cv.say(c, by, [text("MAGNET C: This pre-created Conversation belongs to the Magnet. It contains only ordinary labelled fixture text. No activation, extraction, synthesis, Perspective or agent request ran.")])
    definition = magnet.read(corpus.root, first)
    claims = corpus.operational(act="own-conversation-claimed", detail_is={"magnet": first}, limit=10)
    assert definition["conversation"] == c and c != a and c != b and claims
    result = {"corpus_id": corpus.corpus_id, "A": a, "B": b, "C": c,
              "arrangement_key": a, "origin_post": origin_post, "origin_number": 1,
              "magnets": {"primary": first, "missing_own": missing},
              "claim": claims[0]["id"], "dates_after": after,
              "source_posts": len(posts) + 4, "dated_out_posts": 4 if small else 8,
              "bounded_page_size": 20, "expected_post_page_more": not small,
              "held_file": {"ref": held["admission"], "post": file_post, "name": "fixture-field-notes.md"},
              "attachment": {"ref": pending[0]["admission"], "post": attachment_post, "name": "fixture-calibration.txt"},
              "image": {"ref": picture["admission"], "post": image_post, "name": "fixture-observatory.png"},
              "reply": reply}
    corpus.close()
    result["definition_digests"] = {p.name: digest(p) for p in (brain / "presentation" / "magnets").glob("*.json")}
    result["arrangement_digests"] = {p.name: digest(p) for p in (brain / "presentation" / "fluid-arrangements").glob("*.json")}
    return result


def snapshot(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    if manifest.get("format") != FORMAT or not manifest.get("setup_closed"):
        raise ValueError("not a completed disposable fixture")
    answer = {}
    for name in ("primary", "secondary"):
        brain = root / name
        with sqlite3.connect(brain.joinpath("corpus.db").as_uri() + "?mode=ro", uri=True) as db:
            # Logical record state works while the server owns the WAL. Reading the
            # database file alone would miss changes not checkpointed yet.
            dump = "\n".join(db.iterdump()).encode("utf-8")
            counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                      for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        answer[name] = {"record_sha256": hashlib.sha256(dump).hexdigest(), "table_counts": counts,
            "presentation": {str(p.relative_to(brain)): digest(p) for p in sorted((brain / "presentation").rglob("*.json"))},
            "held": {str(p.relative_to(brain)): digest(p) for p in sorted((brain / "artifacts").rglob("*")) if p.is_file()},
            "content_files": {str(p.relative_to(brain)): digest(p) for p in sorted(brain.rglob("*"))
                if p.is_file() and p.relative_to(brain).parts[0] != "instances"
                and not p.name.startswith(("corpus.db", ".mentis"))}}
    return answer


def seed(root: Path) -> dict:
    if root.exists() and any(root.iterdir()):
        raise ValueError("refusing to seed an existing directory; choose a fresh disposable root")
    root.mkdir(parents=True, exist_ok=True)
    result = {"format": FORMAT, "setup_closed": False,
              "description": "Synthetic disposable fixture; never DAY-TO-DAY or persistent TEST",
              "primary": seed_brain(root / "primary"), "secondary": seed_brain(root / "secondary", small=True),
              "setup_operations": ["api.create_corpus", "Conversation open/join/say", "artifact hold/stage/submit",
                                   "arrangements.create_magnet", "magnet_definition_command conversation"],
              "runtime_forbidden": ["non-read HTTP methods", "GET /api/capacity", "activation", "own-Conversation repair", "arrangement save", "post/send"],
              "setup_closed": True, "seed_completed_at": datetime.now(timezone.utc).isoformat()}
    (root / "manifest.json").write_text(json.dumps(result, indent=2), "utf-8")
    (root / "seed-baseline.json").write_text(json.dumps(snapshot(root), indent=2), "utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "snapshot", "compare"))
    parser.add_argument("--root", default=".preview/quiet-magnet")
    parser.add_argument("--out")
    parser.add_argument("--baseline")
    args = parser.parse_args()
    root = safe_root(args.root)
    if args.action == "seed":
        result = seed(root)
    elif args.action == "snapshot":
        result = snapshot(root)
    else:
        if not args.baseline:
            parser.error("compare needs --baseline")
        before = json.loads(Path(args.baseline).read_text("utf-8"))
        now = snapshot(root)
        result = {"unchanged": before == now, "baseline": str(Path(args.baseline).resolve()), "now": now}
        if before != now:
            print(json.dumps(result, indent=2))
            return 1
    encoded = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(encoded, "utf-8")
        print(str(Path(args.out).resolve()))
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
