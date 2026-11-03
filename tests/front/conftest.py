"""R1's tests. They run on the fixtures in `docs/rust/R1-acceptance.md`, named by env
MENTIS_R1_FIXTURES.

Without it this directory's tests aren't collected, apart from the ones that need no fixture, so a
general `pytest` elsewhere isn't affected. A row is never passed that way: its command then runs 0
tests, which pytest exits 5 for and which isn't the row's count. Once it is set, a missing or
mismatched fixture fails: nothing here skips.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

from tools.r1 import common, copy_brain

NEED_NO_FIXTURE = {"test_fixture_tools.py", "test_permission_matrix.py"}

if os.environ.get("MENTIS_R1_FIXTURES"):
    collect_ignore: list[str] = []
else:
    collect_ignore = [p.name for p in pathlib.Path(__file__).parent.glob("test_*.py")
                      if p.name not in NEED_NO_FIXTURE]

SEED_IDENTITY = common.EVIDENCE / "brain-seed-identity.json"
COPY_MANIFEST = common.EVIDENCE / "brain-copy-manifest.json"


def build_seed(dest: pathlib.Path) -> dict:
    """BRAIN-SEED, as the document's command builds it. Returns what it says it built."""
    done = subprocess.run(
        [str(common.venv_python()), str(common.HERE / "seed_brain.py"), str(dest)],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def brain_seed(tmp_path_factory) -> pathlib.Path:
    """A new BRAIN-SEED, per module, which must be what the manifest says."""
    dest = tmp_path_factory.mktemp("seed") / "brain"
    got = build_seed(dest)
    assert got == json.loads(SEED_IDENTITY.read_text(encoding="utf-8"))
    return dest


@pytest.fixture
def brain_copy(tmp_path) -> pathlib.Path:
    """A fresh BRAIN-COPY, checked against its manifest. A mismatch raises, and fails."""
    return copy_brain.fresh(tmp_path / "brain", common.master_dir(), COPY_MANIFEST)
