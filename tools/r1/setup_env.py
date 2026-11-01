"""Builds what R1's fixtures stand on, under `MENTIS_R1_FIXTURES`, from this clone.

    python tools/r1/setup_env.py

In order, each only if it isn't there yet:

1. `py-b8e324c`, a detached checkout of PY_COMMIT, by plain `git worktree add --detach`;
2. `venv`, Python 3.12 with exactly `docs/rust/evidence/r1-venv-freeze.txt`;
3. Chromium for Playwright: `python -m playwright install chromium`, into the machine's own
   `ms-playwright` directory;
4. Fluid's build in that checkout: `npm ci`, then `npm run build`.

Run by a person or an agent, once. Nothing watches or repairs any of it. The BRAIN-COPY master is
separate, because it reads the owner's Brain: tools/r1/copy_brain.py.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402


def _run(*argv, cwd=None) -> None:
    print("+", " ".join(str(a) for a in argv), flush=True)
    subprocess.run([str(a) for a in argv], cwd=cwd, check=True)


def main() -> int:
    root = common.fixtures_root()
    root.mkdir(parents=True, exist_ok=True)
    code, python = common.code_dir(), common.venv_python()
    if not code.exists():
        _run("git", "worktree", "add", "--detach", code, common.PY_COMMIT, cwd=common.REPO)
    if not python.exists():
        _run(sys.executable, "-m", "venv", root / "venv")
        _run(python, "-m", "pip", "install", "--no-deps", "-q", "-r",
             common.EVIDENCE / "r1-venv-freeze.txt")
    _run(python, "-m", "playwright", "install", "chromium")
    web = code / "apps" / "fluid-web"
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm isn't on PATH: Fluid can't be built here")
    if not (web / "node_modules").exists():
        _run(npm, "ci", "--no-audit", "--no-fund", cwd=web)
    if not common.dist_dir().exists():
        _run(npm, "run", "build", cwd=web)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
