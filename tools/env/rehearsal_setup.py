"""Rehearsal environments on fixture Brains, for proving promote / rollback / snapshot
without touching DAY-TO-DAY or TEST.

    python tools/env/rehearsal_setup.py <rehearsal root> <release id that builds the fixtures>

Writes <root>/environments.json naming three environments on ports nothing else uses
(rprod 8784 as `production`, rtest 8786 and rsnap 8788 as `test`), sharing the real
releases folder but with their own state, and builds a fixture Brain for rprod and rtest.
Agents are off in all three. Delete the root when the rehearsal is recorded.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REAL = json.loads((HERE / "environments.json").read_text("utf-8"))


def env(root: pathlib.Path, name: str, role: str, port: int) -> dict:
    b = root / name
    return {
        "role": role, "label": name.upper(), "port": port, "private_port": port + 10000,
        "brain": str(b / "brain"), "workspace": str(b / "workspace"), "run_dir": str(b / "run"),
        "mars_data": str(b / "mars-data"), "backends": str(b / "backends.json"),
        "start_script": str(b / "start-mentis.ps1") if role == "production" else None,
        "agents": False,
        "env": {"MENTIS_SOURCE_BINDINGS": str(b / "source-bindings.json"),
                "MENTIS_SOURCE_CACHE": str(b / "source-cache"),
                "MARS_DATA_DIR": str(b / "mars-data"),
                "MARS_RESUME_KEY_FILE": str(b / "mars-data" / "resume.key"),
                "MENTIS_PROTECTED_PATHS": str(b / "brain")},
        "unset": ["MENTIS_OWNER_AUTH_FILE", "MENTIS_OWNER_TOKEN"],
    }


def main() -> int:
    root = pathlib.Path(sys.argv[1]).resolve()
    rid = sys.argv[2]
    real_root = pathlib.Path(REAL["root"])
    if root == real_root or real_root not in root.parents:
        print(f"refused: the rehearsal root must be a folder under {real_root}", file=sys.stderr)
        return 2
    root.mkdir(parents=True, exist_ok=True)
    doc = {"format": 1, "root": str(root), "releases": str(real_root / "releases"),
           "repo": str(HERE.parents[1]), "python": REAL["python"], "mars_local_python": None,
           "environments": {"rprod": env(root, "rprod", "production", 8784),
                            "rtest": env(root, "rtest", "test", 8786),
                            "rsnap": env(root, "rsnap", "test", 8788)}}
    (root / "environments.json").write_text(json.dumps(doc, indent=2), "utf-8")
    code = real_root / "releases" / rid / "code"
    for name in ("rprod", "rtest"):
        brain = root / name / "brain"
        if brain.exists():
            continue
        brain.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([REAL["python"], "-B", "-c",
                        "import sys; from mentis.web import fixture; fixture.build(sys.argv[1])",
                        str(brain)], cwd=code, check=True)
        subprocess.run([REAL["python"], "-B", "-m", "mentis.owner_auth", "trust-local", "--brain",
                        str(brain), "--accept", "rehearsal fixture"], cwd=code, check=True,
                       stdout=subprocess.DEVNULL)
    (root / "rprod" / "start-mentis.ps1").write_text(
        "$ErrorActionPreference = 'Stop'\n$Launcher = 'C:\\legacy\\run.cmd'\n"
        "$WorkingDirectory = 'C:\\legacy'\n", "utf-8")
    print(root / "environments.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
