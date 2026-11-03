"""Row I: Rust wrote nothing. `R1-acceptance.md`, "I: Rust wrote nothing, 3". A fresh BRAIN-COPY.

Not "Brain byte-identical", which Python's own startup can make false: so the front-only session
has no Python in it, and the restart compares what a restart adds.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import time

from tests.front import test_sqlite as pair
from tools.r1 import common, copy_brain

#: What `retire_unconsumable` writes, `web/permissions.py:399`.
RETIRED_ACT = "expectation-met"

#: Whatever opens a file, or reads or writes one by path, in Rust.
FILE_DOOR = re.compile(
    r"\bFile\s*::\s*(?:open|create|create_new|options|from_raw_\w+)\b"
    r"|\bOpenOptions\s*::\s*new\b"
    r"|\bfs\s*::\s*(?:read|read_to_string|write|copy|rename|remove_file|hard_link|soft_link)\s*\("
    r"|\b(?:CreateFile\w*|NtCreateFile|NtOpenFile|OpenFileById|ReOpenFile)\b"
    r"|\blibc\s*::\s*(?:open\w*|fopen\w*|creat\w*)\b"
    r"|\bmmap\w*\b"
    r'|\bextern\s+"')

#: Every door in what ships, by file, with how many it may have and where its path comes from. A
#: file may have fewer. A new one is a person's decision that its path can't be the database.
FILE_DOORS = {
    "mentis-record/src/lock.rs": (1, "`.mentis.lock`, `root.join(OPEN_LOCK)`, for locking only"),
    "mentis-record/src/probe.rs": (3, "`ROW_H_PROBE_DIR`'s own files, with `row-h-probe`"),
    "mentis-record/src/trace.rs": (1, "`trace-<pid>.log` in `WORKLOAD_TRACE_DIR`, with `sql-trace`"),
    "mentis-server/src/front/held.rs": (1, "`.mentis.claim`, `.mentis.serve.lock` and `.mentis.owner.lock`, by name in `grants.rs` and `tail.rs`, read-only, never created"),
    "mentis-server/src/front/probe.rs": (7, "`trace.jsonl`, the stops and the limits, all in `MENTIS_TAIL_DIR`, with `tail-probe`"),
    "mentis-server/src/route_table.rs": (2, "`--route-table`'s file"),
    "mentis-server/src/front/mod.rs": (1, "the digest of `--route-table`'s file"),
    "mentis-server/src/handlers/static_files.rs": (1, "under `--dist`, from the route's own check"),
    "mentis-server/src/bin/mentis-launch.rs": (
        15, "`launch.json`, its temporary, `launch.starting.json` and the logs, all in `--run-dir`; "
            "`/dev/urandom` and `/proc/<pid>/stat`; and the `extern` block of Win32 process calls"),
    "mentis-extract/src/lib.rs": (1, "`Bundle::read`: `render-check.js` under `--dist`, joined in `window/mod.rs`, read-only"),
    "mentis-ops/src/window/objects.rs": (1, "`artifacts/sha256/<2>/<digest>` under the Brain, the name checked by `is_digest`, read-only"),
    # Not in what ships: an example, for R2's JS gate, and only its command line names these.
    "mentis-extract/examples/gate.rs": (2, "its own `<inputs.jsonl>` and `<outputs.jsonl>`, from its arguments"),
}

#: Every way to get a connection on a database.
SQLITE_DOOR = re.compile(
    r"\bopen_with_flags\w*\b|\bopen_in_memory\w*\b|\bConnection\s*::\s*open\w*\b"
    r"|\bsqlite3_open\w*\b|\bsqlite3_deserialize\b|\bBackup\s*::\s*new\w*\b|\bfrom_handle\w*\b")

#: A connection opened properly can still get at the file by these, which are mostly in strings.
WAYS_ROUND_THE_FLAGS = re.compile(
    r"\bATTACH\b|(?i:\battach\s+database\b)|(?i:\bvacuum\s+into\b)|immutable\s*="
    r"|\bSQLITE_OPEN_URI\b|\bjournal_mode\b|\bwal_checkpoint\b")

#: In an import of `std::fs` or `rusqlite`: a new name, or a bare door, which the rest can't see.
DISGUISED_IMPORT = re.compile(
    r"\bas\b|\bfs\s*::\s*\{?[^;]*\b(?:read|read_to_string|write|copy|rename|remove_file|hard_link)\b")

NAMES_THE_DATABASE = re.compile(r'corpus\.db|CORPUS_DB|"[^"\n]*\.db\b[^"\n]*"|-wal\b|-shm\b')

#: Where naming it is the point: the constant, and the one join on it.
NAMES_THE_DATABASE_IN = {"mentis-record/src/lib.rs", "mentis-record/src/open.rs"}


def state_of(brain) -> dict:
    """Row counts per table and `advance()`, from `copy_brain`, on nothing holding it open."""
    held = copy_brain._positions(brain / "corpus.db")
    return {"rows": held["rows"], "advance": held["advance"]}


def digests_of(brain) -> dict:
    return copy_brain.digests(brain)


def sidecars_of(brain) -> dict:
    return {path.name: path.stat().st_size for path in brain.glob("corpus.db-*")}


def test_a_front_only_session_changes_nothing(brain_copy):
    state, digests = state_of(brain_copy), digests_of(brain_copy)
    assert sidecars_of(brain_copy) == {}, "a copy with sidecars would show nothing about them"
    with pair.running_front(brain_copy):
        for path in ("/api/pulse", "/fluid/api/topics?q=load", "/fluid/api/names?ids=ent-nothing",
                     "/"):
            assert pair.get(path)[0] == 200, path
        # Something forwarded, with nothing behind the front to take it: the front only answers.
        assert pair.get("/api/server")[0] == 503
    # SQLite's, as for any reader of a WAL database (`contracts/record.md`, Sidecars). `-shm` holds
    # read marks, which readers move, so its size is what can be said of it. `-wal` holds records:
    # none may be there.
    left = sidecars_of(brain_copy)
    assert set(left) == {"corpus.db-shm", "corpus.db-wal"}, left
    assert left["corpus.db-wal"] == 0, "a frame in -wal: the front wrote"
    assert state_of(brain_copy) == state
    assert digests_of(brain_copy) == digests, "corpus.db or a sibling changed under a reader"

    # Python opens what the session left as it opens anything, and a last close takes them away.
    conn = sqlite3.connect(brain_copy / "corpus.db")
    try:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        conn.close()
    assert sidecars_of(brain_copy) == {}
    with pair.running_pair(brain_copy):
        assert pair.get("/api/server")[0] == 200


def test_r3_s_reads_add_no_rows_and_leave_every_sibling_as_it_was(brain_seed, tmp_path):
    """Answered by the front from the mirror, with Python beside it writing nothing for them."""
    from tests.front.mirror_harness import read_as, world
    with world(brain_seed, tmp_path) as w:
        before = _record_position(w.brain)
        siblings = {path.name: path.read_bytes() for path in w.brain.iterdir()
                    if path.is_file() and not path.name.startswith((".mentis", "corpus.db"))}
        answered = len(w.front.events("last-byte"))
        for op, args in (("capabilities", {}), ("kinds", {}), ("history", {"limit": 5}),
                         ("governed", {}), ("resolve", {"ref": "ent-nothing"})):
            status, body = read_as(w.public, w.token, op, args)
            assert status == 200, (op, body[:200])
        assert len(w.front.events("last-byte")) > answered, "none of them was the front's"
        assert _record_position(w.brain) == before
        assert {path.name: path.read_bytes() for path in w.brain.iterdir()
                if path.is_file() and not path.name.startswith((".mentis", "corpus.db"))
                } == siblings


def test_a_python_restart_adds_only_retire_unconsumables_acts(brain_copy):
    with pair.running_pair(brain_copy) as running:
        before = _record_position(brain_copy)
        running.kill_python()
        filled = {"{brain}": str(brain_copy), "{port}": str(pair.PORT),
                  "{ws}": str(running.run / "ws"), "{mars}": pair.NO_MARS,
                  "{run}": str(running.run)}
        command = [filled.get(word, word) for word in pair.template() if word != "--attached"]
        restarted = subprocess.run(command + ["--only", "python"], cwd=running.run,
                                   env=pair.environment(), capture_output=True, text=True,
                                   encoding="utf-8", timeout=pair.START_LIMIT_S)
        assert restarted.returncode == 0, restarted.stdout + restarted.stderr
        pair.wait_for_server(pair.PORT + 10000)
        time.sleep(1)
        after = _record_position(brain_copy)
        added = _acts_after(brain_copy, before["operational"])
    assert after["entry"] == before["entry"], "an entry appeared"
    assert after["delivery"] == before["delivery"], "a delivery appeared"
    assert [a for a in added if a["act"] != RETIRED_ACT] == [], added
    assert len(added) == after["operational"] - before["operational"]
    # Each is listed, for the release report.
    (common.fixtures_root() / "row-I-restart.json").write_text(
        json.dumps(added, indent=1) + "\n", encoding="utf-8")


def _record_position(brain) -> dict:
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        return {t: conn.execute(f"SELECT COALESCE(MAX(seq), 0) FROM {t}").fetchone()[0]
                for t in ("entry", "operational", "delivery")}
    finally:
        conn.close()


def _acts_after(brain, seq: int) -> list[dict]:
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        return [{"seq": s, "id": i, "act": a, "because": b} for s, i, a, b in conn.execute(
            "SELECT seq, id, act, because FROM operational WHERE seq > ? ORDER BY seq", (seq,))]
    finally:
        conn.close()


RAW_STRING = re.compile(r'(?<![A-Za-z0-9_])b?r(#*)"')
CHAR_LITERAL = re.compile(r"'(?:\\.[^']*|[^\\'])'")


def _strip(source: str) -> tuple[str, str]:
    """A Rust file twice over, less its comments: with its string literals, and with them blanked,
    the two the same length. Comments and strings can each hide the other, so this reads them rather
    than splitting lines."""
    kept, code, at = [], [], 0
    while at < len(source):
        if source.startswith("//", at):
            found = source.find("\n", at)
            at = len(source) if found < 0 else found
        elif source.startswith("/*", at):
            depth, at = 1, at + 2
            while at < len(source) and depth:
                if source.startswith("/*", at):
                    depth, at = depth + 1, at + 2
                elif source.startswith("*/", at):
                    depth, at = depth - 1, at + 2
                else:
                    at += 1
            kept.append(" ")
            code.append(" ")
        elif (raw := RAW_STRING.match(source, at)) or source[at] == '"':
            if raw:
                closing = '"' + raw.group(1)
                found = source.find(closing, raw.end())
                end = len(source) if found < 0 else found + len(closing)
            else:
                end = at + 1
                while end < len(source) and source[end] != '"':
                    end += 2 if source[end] == "\\" else 1
                end = min(end + 1, len(source))
            kept.append(source[at:end])
            code.append('"' + " " * max(end - at - 2, 0) + '"' if end - at >= 2 else '"')
            at = end
        elif char := CHAR_LITERAL.match(source, at):
            blank = " " * (char.end() - at)
            kept.append(blank)
            code.append(blank)
            at = char.end()
        else:
            kept.append(source[at])
            code.append(source[at])
            at += 1
    return "".join(kept), "".join(code)


def _without_test_items(kept: str, code: str) -> tuple[str, str]:
    """Both, less each `#[cfg(test)]` item, which isn't in what ships. Braces are counted in `code`,
    where no string can hold one."""
    while found := re.search(r"#\[cfg\(test\)\]", code):
        at = found.end()
        while at < len(code) and code[at] not in "{;":
            at += 1
        if at < len(code) and code[at] == "{":
            depth = 0
            while at < len(code):
                depth += {"{": 1, "}": -1}.get(code[at], 0)
                at += 1
                if not depth:
                    break
        else:
            at += 1
        kept, code = kept[:found.start()] + kept[at:], code[:found.start()] + code[at:]
    return kept, code

def door_violations(sources: dict[str, str], manifests: dict[str, str]) -> list[str]:
    """Everything wrong with how `crates/` could reach a database, by path relative to `crates/`.

    What it looks at is what ships: every `.rs` under `crates/` but `tests/` directories and
    `#[cfg(test)]` items, which may keep scratch Brains of their own and are only held to not opening
    one but through SQLite. It doesn't trace a path's value: a helper's argument, or `--route-table`
    pointed at a database, is not seen. Which is why every door is listed, wherever its path comes
    from, and a new one fails until a person adds it to `FILE_DOORS` saying where that is.
    """
    wrong: list[str] = []
    sqlite_doors: list[tuple[str, str]] = []
    for name, source in sorted(sources.items()):
        kept, code = _strip(source)
        if "/tests/" in name:
            for statement in kept.split(";"):
                if FILE_DOOR.search(statement) and NAMES_THE_DATABASE.search(statement):
                    wrong.append(f"{name}: a test opens the database but through SQLite: "
                                 f"{' '.join(statement.split())}")
            continue
        kept, code = _without_test_items(kept, code)
        for found in SQLITE_DOOR.finditer(code):
            sqlite_doors.append((name, code[found.start():code.find(";", found.start())]))
        for found in WAYS_ROUND_THE_FLAGS.finditer(kept):
            wrong.append(f"{name}: {found.group(0)}")
        for statement in re.findall(r"\buse\s[^;]*;", code):
            if re.search(r"\bfs\b|\brusqlite\b", statement) and DISGUISED_IMPORT.search(statement):
                wrong.append(f"{name}: an import a door could hide behind: {statement}")
        if re.search(r"\b(?:type|const|static)\s+\w+[^;]*=\s*[^;]*\bConnection\b", code):
            wrong.append(f"{name}: another name for Connection")
        doors = len(FILE_DOOR.findall(code))
        allowed = FILE_DOORS.get(name, (0, ""))[0]
        if doors > allowed:
            wrong.append(f"{name}: {doors} ways to open a file by path, and FILE_DOORS allows "
                         f"{allowed}")
        names = NAMES_THE_DATABASE.search(kept)
        if names and name not in NAMES_THE_DATABASE_IN:
            wrong.append(f"{name}: names the database: {names.group(0)}")
        if names and doors:
            wrong.append(f"{name}: names the database and opens files")
        if name.split("/")[0] != "mentis-record" and "rusqlite" in code:
            wrong.append(f"{name}: reaches for rusqlite")

    # One connection is opened, in the crate that may, with the contract's flags.
    if [name.split("/")[:2] for name, _ in sqlite_doors] != [["mentis-record", "src"]]:
        wrong.append(f"not one way to open a connection: {sqlite_doors}")
    elif not re.search(r"open_with_flags\s*\(\s*[^,]+,\s*OPEN_FLAGS\s*,?\s*\)", sqlite_doors[0][1]):
        wrong.append(f"a connection opened other than with OPEN_FLAGS: {sqlite_doors[0][1]}")

    contract = _strip(sources["mentis-record/src/lib.rs"])[1]
    flags = re.search(r"const OPEN_FLAGS[^;]*;", contract)
    if not flags or "SQLITE_OPEN_READ_ONLY" not in flags.group(0) or re.search(
            r"READ_WRITE|CREATE|URI", flags.group(0)):
        wrong.append(f"OPEN_FLAGS: {flags and flags.group(0)}")
    pragmas = re.search(r"const OPEN_PRAGMAS[^;]*;[^;]*;[^;]*;", _strip(
        sources["mentis-record/src/lib.rs"])[0])
    if not pragmas or "query_only=ON" not in pragmas.group(0):
        wrong.append(f"OPEN_PRAGMAS: {pragmas and pragmas.group(0)}")

    # And only this crate can reach a connection at all.
    wrong += [f"{name} depends on rusqlite" for name, text in sorted(manifests.items())
              if name.split("/")[0] != "mentis-record" and "rusqlite" in text]
    return wrong


def _workspace() -> tuple[dict[str, str], dict[str, str]]:
    crates = common.REPO / "crates"
    relative = lambda path: path.relative_to(crates).as_posix()
    return ({relative(path): path.read_text(encoding="utf-8") for path in crates.rglob("*.rs")},
            {relative(path): path.read_text(encoding="utf-8")
             for path in crates.glob("*/Cargo.toml")})


def _with(sources: dict[str, str], name: str, old: str, new: str) -> dict[str, str]:
    assert old in sources[name], f"{name} has no {old!r} to plant in"
    return {**sources, name: sources[name].replace(old, new, 1)}


def _planted(sources: dict[str, str]) -> dict[str, dict[str, str]]:
    """What the check must catch, each planted in the source as it stands."""
    open_rs, lock_rs = "mentis-record/src/open.rs", "mentis-record/src/lock.rs"
    helper = "mentis-server/src/slurp.rs"
    opening = "Connection::open_with_flags(db, OPEN_FLAGS)"
    return {
        "a helper reading a path from elsewhere": {
            **sources, helper: "pub fn slurp(p: &Path) -> Vec<u8> { std::fs::read(p).unwrap() }"},
        "the same, split over lines and through a comment": {
            **sources, helper: "fn s(p: &Path) { let _ = File /* no */\n  ::\n  open(p); }"},
        "the same, behind a renamed import": {
            **sources, helper: "use std::fs::read as slurp;\nfn s(p: &Path) { slurp(p); }"},
        "the same, behind a renamed module": {
            **sources, helper: "use std::fs as files;\nfn s(p: &Path) { files::read(p); }"},
        "the same, by Win32": {
            **sources, helper: "fn s(p: *const u16) { unsafe { CreateFileW(p, 0, 0) }; }"},
        "the same, after a string that looks like a comment": {
            **sources, helper: 'fn s(p: &Path) { let _ = ("//", File::open(p)); }'},
        "a second door in a file that has one": _with(
            sources, lock_rs, "os::lock_shared(&file)?;",
            'let _ = File::open(root.join("x"));\n        os::lock_shared(&file)?;'),
        "a second door beside the bundle's": _with(
            sources, "mentis-extract/src/lib.rs", "let bytes = std::fs::read(path)?;",
            "let bytes = std::fs::read(path)?;\n        let _ = std::fs::read(path);"),
        "a second door beside the held file's": _with(
            sources, "mentis-ops/src/window/objects.rs", "let path = self.held_path(digest);",
            "let path = self.held_path(digest);\n        let _ = std::fs::read(&self.root);"),
        "a third door in the gate": _with(
            sources, "mentis-extract/examples/gate.rs", "let engines = Engines::new();",
            "let engines = Engines::new();\n    let _ = std::fs::read(bundle);"),
        "another example opening a file": {
            **sources, "mentis-extract/examples/other.rs":
                "fn main() { let _ = std::fs::read(\"x\"); }"},
        "a held file's read naming the database": _with(
            sources, "mentis-ops/src/window/objects.rs", "let path = self.held_path(digest);",
            'let path = self.root.join("corpus.db");'),
        "a database named beside a door": {
            **sources, helper: 'fn s(r: &Path) { std::fs::read(r.join("corpus.db")); }'},
        "a sidecar named": {**sources, helper: 'const W: &str = "corpus.db-wal";'},
        "a test reading the database as a file": {
            **sources, "mentis-record/tests/x.rs": 'fn s() { std::fs::read("corpus.db"); }'},
        "a second connection": {
            **sources, helper: "fn c(p: &Path) { rusqlite::Connection::open(p); }"},
        "a second connection in the crate": _with(
            sources, open_rs, "let mut conn = open_connection(&self.db)?;",
            "let mut conn = Connection::open(&self.db)?;"),
        "a connection with other flags": _with(
            sources, open_rs, opening, "Connection::open_with_flags(db, OpenFlags::default())"),
        "flags that can write": _with(
            sources, "mentis-record/src/lib.rs", "SQLITE_OPEN_READ_ONLY",
            "SQLITE_OPEN_READ_WRITE"),
        "no query_only": _with(
            sources, "mentis-record/src/lib.rs", "PRAGMA query_only=ON; ", ""),
        "immutable": {**sources, helper: 'const U: &str = "file:x?immutable=1";'},
        "attaching another file": {**sources, helper: 'const A: &str = "ATTACH ? AS other";'},
        "another name for Connection": {
            **sources, helper: "type C = mentis::Connection;\nfn c(p: &Path) { C::new(p); }"},
    }


def _harmless(sources: dict[str, str]) -> dict[str, dict[str, str]]:
    """What the check must let by: tidying, and r1-bench's trace as `8ceb70a` has it."""
    open_rs = "mentis-record/src/open.rs"
    return {
        "the opening reworded and rewrapped": _with(
            sources, open_rs, "let conn = Connection::open_with_flags(db, OPEN_FLAGS)?;",
            "let opened = Connection::open_with_flags(\n        db,\n        OPEN_FLAGS,\n    );\n"
            "    let conn = opened?;"),
        "lines added after the opening": _with(
            sources, open_rs, "let conn = Connection::open_with_flags(db, OPEN_FLAGS)?;",
            "let conn = Connection::open_with_flags(db, OPEN_FLAGS)?;\n"
            '    #[cfg(feature = "sql-trace")]\n    let conn = crate::trace::switched_on(conn)?;'),
        "a door in a comment or a string": {
            **sources, "mentis-server/src/words.rs":
                '// std::fs::read(corpus.db)\nconst W: &str = "File::open is a way in";'},
        "a door in a test item": {
            **sources, "mentis-server/src/words.rs":
                "#[cfg(test)]\nmod tests { fn t(p: &Path) { std::fs::write(p, b\"x\"); } }"},
    }


def test_corpus_db_is_opened_read_only_and_only_through_sqlite():
    sources, manifests = _workspace()
    assert len(sources) > 5, "the workspace's source is where it was"
    assert door_violations(sources, manifests) == []
    for what, planted in _planted(sources).items():
        assert door_violations(planted, manifests), f"it didn't see {what}"
    for what, tidied in _harmless(sources).items():
        assert door_violations(tidied, manifests) == [], what
    with_another_dependency = {**manifests, "mentis-ops/Cargo.toml": 'rusqlite = "0.41"'}
    assert door_violations(sources, with_another_dependency), "it didn't see a second dependency"
