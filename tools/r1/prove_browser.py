"""Proves row P5's check on Python alone: it passes on a real build, and it fails when broken.

    <fixtures>\\venv\\Scripts\\python.exe tools/r1/prove_browser.py <seed master> <work dir>

Fluid's real build, from the checkout of PY_COMMIT, served by Python on a fresh copy of
BRAIN-SEED. Then the same check with the index's stylesheet missing from a copy of the build,
with its script missing, with an API read aborted, with a page error, and with a known post the
fixture doesn't hold. Writes one JSON object to stdout. Exit 0 only when the real load passes and
every broken one fails.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import browser_check  # noqa: E402
import common  # noqa: E402
import py_alone  # noqa: E402

URL = f"http://127.0.0.1:{py_alone.PORT}/"


def _brain(seed: pathlib.Path, where: pathlib.Path) -> pathlib.Path:
    brain = where / "brain"
    shutil.copytree(seed, brain)
    return brain


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    seed, work = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    work.mkdir(parents=True)
    out: dict = {"build": common.tree_digest(common.dist_dir()),
                 "code_commit": common.head_of(common.code_dir())}

    with py_alone.running(_brain(seed, work / "good")):
        out["real_build"] = browser_check.check(URL)
        out["fault_api_read_aborted"] = browser_check.check(URL, block="/fluid/api/conversations")
        out["fault_page_error"] = browser_check.check(URL, throw=True)
        out["fault_known_post_absent"] = browser_check.check(URL, known_post="no such post")

    # The assets the index names, so the page is certain to ask for them. A stylesheet leaves
    # the page working, so only the failed request can catch it; the script leaves nothing.
    index = (common.dist_dir() / "index.html").read_text(encoding="utf-8")
    for label, pattern in (("stylesheet", r'href="/?(assets/[^"]+\.css)"'),
                           ("script", r'src="/?(assets/[^"]+\.js)"')):
        named = re.search(pattern, index)
        assert named, f"the index names no {label}"
        broken = work / f"dist-no-{label}"
        shutil.copytree(common.dist_dir(), broken)
        (broken / named.group(1)).unlink()
        with py_alone.running(_brain(seed, work / f"no-{label}"), dist=broken):
            out[f"fault_{label}_missing"] = {"removed": named.group(1),
                                             **browser_check.check(URL)}

    print(json.dumps(out, indent=1))
    faults = [k for k in out if k.startswith("fault_")]
    good = out["real_build"]["passed"] and not any(out[k]["passed"] for k in faults)
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
