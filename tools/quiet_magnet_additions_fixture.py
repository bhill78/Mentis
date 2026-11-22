"""The Magnet additions' OWN synthetic disposable fixture, and nothing else.

    python tools/quiet_magnet_additions_fixture.py seed --root .preview/quiet-magnet-additions-fixture
    python tools/quiet_magnet_additions_fixture.py snapshot --root <root> --out baseline.json
    python tools/quiet_magnet_additions_fixture.py compare  --root <root> --baseline baseline.json

WHY A SECOND HELPER rather than a change to `quiet_magnet_fixture.py`: that one
seeds the READ-ONLY trial's fixture and is owned by the work that wrote it. This
one extends it -- it imports `seed_brain`/`safe_root` and changes nothing there --
for the additions' trial, where exactly two writes are allowed through the new
identity-gated proxy (`tools/quiet-magnet-additions-preview.mjs`).

WHAT IT ADDS over the read-only fixture's seed, through the same sanctioned
operations, before setup closes:

  * a HISTORICAL reply in the Magnet's own Conversation C, so the mini
    Conversation has real history and a real reply parent to read. It is
    written by a synthetic fixture participant and says so. No agent ran,
    and no agent reply is fabricated.
  * a TRUTHFUL, NON-EXECUTING Work record: an expectation recorded against a
    post in C and never dispatched, so the mini's Work status reads what it
    actually is -- recorded, nothing started. It is attempted through the
    shared posting operation; where this build cannot record one without an
    agent service, the manifest says so in `work_fixture` and nothing is
    faked.
  * trusted-local owner mode ON THE DISPOSABLE FIXTURE BRAIN ONLY, so the two
    sanctioned writes are the owner's without a passphrase or a borrowed
    cookie. The credential file sits beside the fixture Brain inside this
    checkout and is thrown away with it. No production or TEST Brain is
    touched, read or configured here.
  * `writes_allowed`, the manifest's statement of the ONLY Conversation and
    the ONLY arrangement this fixture's proxy may write into, and the
    participants it may write as. The proxy reads it and refuses everything
    else; a loopback port is never the gate.

No production path, no live Brain, no MARS connection, no existing Brain is
accepted: the root must be a fresh directory inside this checkout.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quiet_magnet_fixture import REPO, digest, safe_root, seed_brain

#: This fixture's own format. The additions' proxy accepts no other, so the
#: read-only trial's fixture cannot be mistaken for a write-capable one.
FORMAT = "quiet-magnet-additions-disposable-fixture-v1"

TRUST = ("A synthetic, disposable Quiet Magnet fixture Brain inside a work "
         "checkout, created for one preview and thrown away with it. It holds "
         "no real record, and nothing outside this fixture trusts it.")


def _extend(brain: Path, mid: str) -> dict:
    """The additions' own history in C, and a truthful Work record, through the
    ordinary operations. Returns what the manifest says about them."""
    import mentis.api as api
    from mentis import magnet
    from mentis.conversation import text

    corpus = api.open_corpus(str(brain), access="write")
    try:
        cv = api.conversations(corpus)
        c = magnet.read(corpus.root, mid)["conversation"]
        by = cv.find_participant("@FixtureOwner")
        other = cv.find_participant("@FixtureReader")
        if not by or not other:
            raise RuntimeError("the seeded fixture participants were not found")
        cv.join(other, c, attributed_to=by)
        first = cv.turns(c)[0]["turn"]
        # HISTORY, NOT A FABRICATED AGENT REPLY: a synthetic participant's own
        # follow-up, labelled as fixture text, replying to the first post of C.
        reply = cv.say(c, other, [text(
            "MAGNET C REPLY (fixture history): a synthetic follow-up written at "
            "setup by a fixture participant, so the mini Conversation has real "
            "earlier history and a real reply parent. No agent ran.")],
            replies_to=first)
        anchor = cv.say(c, by, [text(
            "MAGNET C: a fixture record of work that was never started. The "
            "Work status below is the truth about this record: it was asked "
            "for and nothing has run.")])
        work = _work_fixture(cv, corpus, c, anchor, by, other)
        return {"conversation": c, "history_reply": reply,
                "first_post": first, "work_anchor": anchor,
                "work_fixture": work,
                "participants": sorted({by, other})}
    finally:
        corpus.close()


def _work_fixture(cv, corpus, c, anchor, by, other) -> dict:
    """An expectation recorded and NEVER dispatched, or why none was recorded.

    `posting.post` hands the dispatches back for the caller to start; nothing
    here starts one, and no agent service is attached, so what the record holds
    afterwards is exactly what it says: work asked for, nothing run. If this
    build refuses to record one without an agent service, that refusal is
    reported as it stands rather than worked around.
    """
    try:
        out, later = posting_post(
            cv, corpus, c,
            {"author": by, "text": "FIXTURE WORK: recorded, never started.",
             "action": "ask-participant", "replies_to": anchor,
             "op": "quiet-magnet-additions-fixture-work",
             "dispatch": [{"participant": other, "work": "Nothing runs for "
                           "this fixture record; it exists so the mini "
                           "Conversation can read a truthful Work status."}]})
    except Exception as exc:                                     # noqa: BLE001
        return {"recorded": False, "why_not": f"{type(exc).__name__}: {exc}",
                "started": False}
    if "error" in out:
        return {"recorded": False, "why_not": out["error"], "started": False}
    # The dispatches are deliberately dropped on the floor: never started.
    return {"recorded": True, "started": False, "post": out.get("turn"),
            "expectations": list(out.get("expectations") or []),
            "dispatches_returned_and_not_started": len(later)}


def posting_post(cv, corpus, cid, body):
    from mentis.conversation import posting
    return posting.post(cv, corpus, cid, body, agents=None,
                        written_by=lambda: "fixture/setup")


def brain_state(brain: Path) -> dict:
    """One Brain's logical record, presentation and held bytes."""
    with sqlite3.connect(brain.joinpath("corpus.db").as_uri() + "?mode=ro",
                         uri=True) as db:
        dump = "\n".join(db.iterdump()).encode("utf-8")
        counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                  for (table,) in db.execute("SELECT name FROM sqlite_master "
                                             "WHERE type='table' AND "
                                             "name NOT LIKE 'sqlite_%'")}
    return {"record_sha256": hashlib.sha256(dump).hexdigest(),
            "table_counts": counts,
            "presentation": {str(p.relative_to(brain)): digest(p)
                             for p in sorted((brain / "presentation").rglob("*.json"))},
            "held": {str(p.relative_to(brain)): digest(p)
                     for p in sorted((brain / "artifacts").rglob("*")) if p.is_file()}}


def snapshot(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    if manifest.get("format") != FORMAT or not manifest.get("setup_closed"):
        raise ValueError("not a completed additions fixture")
    return {name: brain_state(root / name) for name in ("primary", "secondary")}


def seed(root: Path) -> dict:
    if root.exists() and any(root.iterdir()):
        raise ValueError("refusing to seed an existing directory; "
                         "choose a fresh disposable root")
    root.mkdir(parents=True, exist_ok=True)
    primary = seed_brain(root / "primary")
    secondary = seed_brain(root / "secondary", small=True)
    extra = _extend(root / "primary", primary["magnets"]["primary"])
    if extra["conversation"] != primary["C"]:
        raise RuntimeError("the extension wrote into another Conversation "
                           "than the Magnet's own")
    primary = {**primary, "history": extra}
    _trust_local(root / "primary")
    result = {
        "format": FORMAT,
        "setup_closed": False,
        "description": "Synthetic disposable fixture for the Magnet additions; "
                       "never DAY-TO-DAY, never persistent TEST, never MARS",
        "primary": primary,
        "secondary": secondary,
        "setup_operations": [
            "quiet_magnet_fixture.seed_brain (api.create_corpus, Conversation "
            "open/join/say, artifact hold/stage/submit, arrangements."
            "create_magnet, magnet_definition_command conversation)",
            "Conversations.join/say for C's history",
            "conversation.posting.post with no agent service, dispatches "
            "returned and not started",
            "owner_auth trust-local on the disposable fixture Brain only"],
        # WHAT THE PROXY MAY LET THROUGH, and nothing else. It is checked
        # against the running server's own identity before it is believed.
        "writes_allowed": {
            "conversation": primary["C"],
            "arrangement": primary["arrangement_key"],
            "magnet_sources": sorted({primary["A"], primary["B"], primary["C"]}),
            "participants": extra["participants"],
            "post": "record-only plain text or a reply whose parent is in this "
                    "Conversation: no ask, dispatch, addressing or attachment",
            "magnet": "one Conversation source from magnet_sources, a one-time "
                      "manual configuration with notifications off"},
        "runtime_forbidden": [
            "every method and path but the two allowed writes",
            "GET /api/capacity", "percent-encoded path aliases",
            "activation", "own-Conversation repair", "arrangement save",
            "post edit/delete/react/comment/deep-dive/address",
            "credentials, cookies and method-override headers"],
        "owner_mode": "trusted-local, on this disposable fixture Brain only",
        "setup_closed": True,
        "seed_completed_at": datetime.now(timezone.utc).isoformat()}
    (root / "manifest.json").write_text(json.dumps(result, indent=2), "utf-8")
    (root / "seed-baseline.json").write_text(json.dumps(snapshot(root), indent=2),
                                             "utf-8")
    return result


def _trust_local(brain: Path) -> None:
    """Trusted-local owner mode for THIS disposable fixture Brain.

    The credential is one file per Brain, beside it (`owner_auth.credential_path`),
    so this configures the fixture and nothing else. It is refused unless the
    Brain is inside this checkout."""
    from mentis import owner_auth
    brain = brain.resolve()
    if REPO not in brain.parents:
        raise ValueError("a credential is set only for a fixture Brain inside "
                         "this checkout")
    # BESIDE THIS BRAIN, SPELLED OUT. `credential_path` honours an ambient
    # MENTIS_OWNER_AUTH_FILE, which a test session sets for itself; the server
    # that serves this fixture is started with a clean environment and looks
    # beside the Brain, so that is where this is written and nowhere else.
    where = brain.parent / (brain.name + owner_auth.SUFFIX)
    if REPO not in where.parents:
        raise ValueError(f"the fixture credential would be written outside "
                         f"this checkout: {where}")
    owner_auth.Credential(where).trust_local(TRUST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "snapshot", "compare"))
    parser.add_argument("--root", default=".preview/quiet-magnet-additions-fixture")
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
        result = {"unchanged": before == now,
                  "baseline": str(Path(args.baseline).resolve()), "now": now}
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
