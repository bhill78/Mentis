"""TEST's data: one consistent snapshot of production, made independent and inert.

Called by `mentis_env.py snapshot --owner-authorized "..."`. It refuses when the target
already holds a Brain: a refresh of TEST's data is the owner's separate decision, and no
deploy ever does it.

HOW THE COPY IS MADE. Mentis's own supported backup (`python -m mentis.brain backup
--portable`, mentis/spine/backup.py): the record through SQLite's backup API under a shared
lock beside the running server, every stored file COPIED and checked against its name (no
hardlinks: TEST shares no file with production), and bytes that only purged or permanently
deleted material named are left out. It is restored into a new folder with `mentis.brain
restore`, which verifies it. The production Brain is only read.

WHAT IS CHANGED IN THE COPY, and why (each is a way a copy would otherwise act as, or on,
its original):

  name and role       mentis-corpus.json says "TEST" / development, so the interface says TEST
  owner credential    its own, never production's file (a copied one would share the cookie)
  mcp-policy.json     runs get no user-level MCP servers or connectors; TEST's own ports are
                      named as Mentis servers
  machine-wide state  source bindings, source cache, MARS data and resume key are TEST's own
                      (environments.json `env`): these are keyed by the Brain's id, which a
                      copy keeps, so without this TEST would read and change production's
  agents              off (environments.json `agents: false`): the server is given
                      agents_off.py where MARS would be, so no runtime is ever listed. A
                      delegation made in the 24 h before the snapshot and never started would
                      still be picked up by start-up recovery -- and fail, recorded as failed,
                      instead of running. Production's open runs stay in the record as history;
                      nothing resumes them. (Mentis has no execution-off switch of its own.)
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sqlite3
import time


def _counts(brain: str) -> dict:
    """Row counts of every table in the copy, read-only. Never run on production."""
    conn = sqlite3.connect(f"file:{pathlib.Path(brain, 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        out = {}
        for t in tables:
            try:
                out[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                out[t] = None
        return out
    finally:
        conn.close()


def populate(cfg, a, me) -> int:
    src_name = a.source or next(n for n, e in cfg.envs.items() if e["role"] == "production")
    dst_name = a.target or next(n for n, e in cfg.envs.items() if e["role"] == "test")
    src, dst = cfg.env(src_name), cfg.env(dst_name)
    if dst["role"] == "production":
        raise me.Refused("a snapshot is never written into production")
    if not a.owner_authorized.strip():
        raise me.Refused("--owner-authorized carries the owner's own words for this copy")
    brain = pathlib.Path(dst["brain"])
    if brain.exists():
        raise me.Refused(f"{dst_name} already has a Brain at {brain}. Refreshing TEST's data replaces "
                         f"everything tested there and is the owner's separate decision; nothing was copied")
    for port in (dst["port"], dst["private_port"]):
        if me.port_owner(port):
            raise me.Refused(f"{dst_name}'s port {port} is in use")
    seen = me.observe(cfg, src_name)
    rid = seen.get("serves_release")
    if not rid:
        raise me.Refused(f"{src_name} serves no recorded release, so there is no code known to read "
                         f"its Brain's schema: build the baseline release first")
    code = cfg.release_dir(rid) / "code"
    state = cfg.state(dst_name)
    state.mkdir(parents=True, exist_ok=True)
    backup = state / "snapshot-backup"
    if backup.exists() or pathlib.Path(str(backup) + ".partial").exists():
        raise me.Refused(f"{backup} is left from an earlier attempt: look at it before anything else")
    py = [cfg.python, "-B", "-X", "utf8", "-m"]
    t0 = time.time()
    made = json.loads(me.run([*py, "mentis.brain", "backup", src["brain"], "--dest", backup,
                              "--portable"], cwd=code, timeout=3600).stdout)
    manifest = me.read_json(backup / "BACKUP.json") or {}
    plan = json.loads(me.run([*py, "mentis.brain", "restore-plan", brain, backup], cwd=code).stdout)
    restored = json.loads(me.run([*py, "mentis.brain", "restore", brain, backup, "--confirm",
                                  plan["digest"]], cwd=code, timeout=3600).stdout)
    seconds = round(time.time() - t0, 1)
    # the permanent-deletion ledger and erase-set live BESIDE a Brain, keyed by its path, and a
    # portable backup does not carry them: the copy gets its own copies, so it knows the same
    # deletions its original does
    carried = []
    base = src["brain"].rstrip("/" + chr(92))
    ledger, erase_sets = pathlib.Path(base + ".erasures.jsonl"), pathlib.Path(base + ".erasures")
    if ledger.is_file():
        shutil.copy2(ledger, str(brain) + ".erasures.jsonl")
        carried.append(ledger.name)
    if erase_sets.is_dir():
        shutil.copytree(erase_sets, str(brain) + ".erasures")
        carried.append(erase_sets.name)

    done = []
    # nothing that binds the copy to the original's processes
    for p in brain.glob(".mentis.*"):
        if p.is_file() and p.name not in (".mentis.lock",):
            p.unlink()
            done.append(f"removed {p.name}")
    marker = brain / "mentis-corpus.json"
    doc = me.read_json(marker) or {}
    was = {"name": doc.get("name"), "role": doc.get("role")}
    doc.update(name=dst["label"], role="development")
    marker.write_text(json.dumps(doc, indent=1), "utf-8")
    done.append(f"mentis-corpus.json: name {was['name']!r} -> {dst['label']!r}, role {was['role']!r} -> 'development'")
    (brain / "mcp-policy.json").write_text(json.dumps({
        "format": "mentis.mcp-policy", "version": 1,
        "user_servers": {"default": "deny", "allow": [], "deny": [], "other_brains": []},
        "mentis_servers": [f"127.0.0.1:{dst['port']}", f"127.0.0.1:{dst['private_port']}"]}, indent=1), "utf-8")
    done.append("mcp-policy.json: user-level MCP servers denied to runs; TEST's ports named as Mentis servers")
    cred = pathlib.Path(str(brain) + ".owner-auth.json")
    if cred.exists():
        raise me.Failed(f"{cred} exists before this tool made one: it must not be production's")
    me.run([*py, "mentis.owner_auth", "trust-local", "--brain", brain, "--accept",
            f"{dst['label']} environment on this machine, a copy of production data made on the owner's "
            f"instruction ({a.owner_authorized.strip()}). Same single-user local trust as DAY-TO-DAY, "
            f"with its own credential file. Not a sandbox."], cwd=code)
    done.append(f"its own owner credential ({cred.name}, trusted-local); production's file was not read")
    for var, value in (dst.get("env") or {}).items():
        if var in ("MENTIS_SOURCE_CACHE", "MARS_DATA_DIR"):
            os.makedirs(value, exist_ok=True)
    bindings = (dst.get("env") or {}).get("MENTIS_SOURCE_BINDINGS")
    if bindings and not os.path.exists(bindings):
        done.append("source bindings: TEST starts with none of its own (production's folder and "
                    "repository bindings are not shared; the record of sources is kept)")
    if src.get("backends") and os.path.isfile(src["backends"]) and dst.get("backends"):
        shutil.copy2(src["backends"], dst["backends"])
        done.append("backends.json: a copy of production's runtime list, for when agents are turned on")
    os.makedirs(dst["workspace"], exist_ok=True)

    counts = _counts(str(brain))
    blobs = sum(1 for p in (brain / "artifacts").rglob("*") if p.is_file()) if (brain / "artifacts").is_dir() else 0
    shared = 0
    if (brain / "artifacts").is_dir():
        for p in (brain / "artifacts").rglob("*"):
            if p.is_file() and os.stat(p).st_nlink > 1:
                shared += 1
    me.write_json(state / "SNAPSHOT.json", {
        "environment": dst_name, "source_environment": src_name, "source_brain": src["brain"],
        "source_as_of": manifest.get("created_at_utc"), "made_at": me.now(), "seconds": seconds,
        "owner_authorized": a.owner_authorized.strip(),
        "method": "python -m mentis.brain backup --portable (SQLite backup API under a shared lock; "
                  "stored files copied and hash-checked), then mentis.brain restore into a new folder",
        "read_with_release": rid, "backup": {k: made.get(k) for k in (
            "id", "kind", "corpus_id", "ledger", "stored_files", "unnamed_stored_files",
            "purged_stored_files_left_out", "db_sha256")},
        "restore": {k: restored.get(k) for k in restored
                    if k in ("mode", "verified", "complete", "erasure", "erasure_ledger")},
        "erasure_sidecars_copied": carried or "production has none beside its Brain",
        "tables": counts, "stored_files_in_copy": blobs,
        "stored_files_hardlinked_to_anything": shared, "made_independent": done,
        "refresh": "never automatic. A later refresh needs the owner's explicit authorization."})
    me._rm_tree(backup)
    print(json.dumps({"snapshot": str(brain), "source_as_of": manifest.get("created_at_utc"),
                      "seconds": seconds, "stored_files": blobs, "hardlinked": shared,
                      "tables": {k: v for k, v in counts.items() if v}, "made_independent": done}, indent=1))
    return 0
