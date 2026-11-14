"""Where R1's fixtures live, and the digests they are identified by.

Everything built lives outside the repository, under `fixtures_root()`. What is
committed is how to build it and what it must come out as
(`docs/rust/R1-acceptance.md`, "Fixtures"). Standard library only, so these tools run
before the test environment exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess

#: The Python that PY-ALONE runs and that seeds and verifies the fixtures. Fixed, not
#: "whatever this clone has": R1-acceptance.md says why. RE-BASELINED (owner, 2026-11-14) from
#: `b8e324c` to `3dea184`, the reference that reads the 0002-erasure Brain format: a reader before
#: it can't open a Brain this release writes (min_reader 2), so it can no longer be the other
#: side of a differential. That older reader is now `OLD_PY_COMMIT`, and only
#: `tests/front/test_older_reader.py` runs it, to show it refuses such a Brain safely.
PY_COMMIT = "3dea184"
OLD_PY_COMMIT = "b8e324c"

DEFAULT_ROOT = r"C:\Work\Mentis-workspace\r1-fixtures"

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
EVIDENCE = REPO / "docs" / "rust" / "evidence"


def fixtures_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("MENTIS_R1_FIXTURES") or DEFAULT_ROOT)


def code_dir() -> pathlib.Path:
    """The detached checkout of PY_COMMIT."""
    return fixtures_root() / f"py-{PY_COMMIT}"


def old_code_dir() -> pathlib.Path:
    """The detached checkout of OLD_PY_COMMIT, the reader from before 0002-erasure."""
    return fixtures_root() / f"py-{OLD_PY_COMMIT}"


def old_front() -> pathlib.Path:
    """A copy of the front from before 0002-erasure (the release DAY-TO-DAY serves,
    `msel-front-62a67e4`), kept with the fixtures: `old-front-62a67e4/mentis-server.exe`."""
    return fixtures_root() / "old-front-62a67e4" / "mentis-server.exe"


def venv_python() -> pathlib.Path:
    return fixtures_root() / "venv" / "Scripts" / "python.exe"


def dist_dir() -> pathlib.Path:
    """Fluid's build, from that checkout."""
    return code_dir() / "apps" / "fluid-web" / "dist"


def master_dir() -> pathlib.Path:
    return fixtures_root() / "brain-copy-master"


def current_schema(brain, code=None, python=None) -> dict | None:
    """BRING A FIXTURE COPY TO THE SCHEMA OF THE CODE THAT WILL OPEN IT. The BRAIN-COPY master is
    recorded at schema 1 and stays so: its manifest says those bytes. A copy that PAIR or
    PY-ALONE opens is migrated first by that code's own `mentis.migrate`, as a person upgrading
    would (0002-erasure raises `min_reader`, and the front's ledger names it); a copy already at
    that schema is left as it is. Raises if the migration is refused or fails."""
    code = pathlib.Path(code or REPO).resolve()
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("MENTIS") and k.upper() != "PYTHONPATH"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    done = subprocess.run(
        [str(python or venv_python()), "-m", "mentis.migrate", str(brain), "--apply",
         "--allow-breaking"],
        cwd=code, env=env, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise RuntimeError(f"migrating {brain} for {code} failed ({done.returncode}): "
                           f"{done.stderr.strip()}")
    return json.loads(done.stdout)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree_digest(root) -> dict:
    """A directory's files, sorted, by relative path, size and content. An empty directory
    and a missing one have the same digest: both hold nothing."""
    root = pathlib.Path(root)
    h = hashlib.sha256()
    files = size = 0
    if root.is_dir():
        found = sorted(
            p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        for rel in found:
            one = root / rel
            n = one.stat().st_size
            h.update(f"{rel}\0{n}\0{sha256_file(one)}\n".encode("utf-8"))
            files += 1
            size += n
    return {"files": files, "bytes": size, "sha256": h.hexdigest()}


def git_blob(path) -> str:
    """The Git blob id of a file's bytes, so a manifest can name the tool that made it
    without waiting for the commit that will hold both."""
    data = pathlib.Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def head_of(cwd) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()
