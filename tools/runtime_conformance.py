"""Run the runtime-conformance scenarios against one runtime (round 2, O9 / program §12).

    python tools/runtime_conformance.py --runtime claude [--model sonnet]
        [--scenarios main,failure,cancellation,continuity,delegation]
        [--mars "C:/Work/MARS-wt/r2-parity/rust/target/release/mars.exe stdio"]
        [--root C:/Work/Mentis-Test-Server/r2-parity] [--port 8841]
    python tools/runtime_conformance.py --offline --runtime antigravity   # scripted profile

LIVE: a throwaway fixture Brain and a Mentis HTTP server on `--port` under `--root`, the
real dispatch, and MARS (`--mars`) with its own data directory under `--root` (never the
production one). Each dispatched run is given the Mentis bridge pointing at THIS fixture
server as its `mentis` MCP server; MARS's MCP isolation keeps the owner's user-level
`mentis` registration (DAY-TO-DAY) out of it. The live Brain is counted read-only before
and after, and the run fails if those counts moved.

Writes `<root>/evidence/<runtime>-<stamp>.json` and `.md`: every check with its status
(passed / failed / not-run / capacity-blocked) and evidence (run, act and request ids).
The fixture Brain and MARS data are deleted afterwards unless `--keep`.

Offline mode (`--offline`) runs the same scenarios over the scripted profile, as
`pytest tests/conformance_runtime` does.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

LIVE_BRAIN = Path(os.environ.get("LOCALAPPDATA", "")) / "Mentis" / "Mark-IV" / "brain" / "corpus.db"
DEFAULT_MARS = "C:/Work/MARS-wt/r2-parity/rust/target/release/mars.exe stdio"
DEFAULT_ROOT = "C:/Work/Mentis-Test-Server/r2-parity"


def live_counts() -> dict:
    """The live Brain's row counts, read-only (`mode=ro`): what a leak would move."""
    if not LIVE_BRAIN.is_file():
        return {"missing": str(LIVE_BRAIN)}
    con = sqlite3.connect(f"file:{LIVE_BRAIN.as_posix()}?mode=ro", uri=True)
    try:
        return {t: con.execute(f"select count(*) from {t}").fetchone()[0]
                for t in ("entry", "operational")}
    finally:
        con.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--scenarios", default="main,failure,cancellation,continuity")
    ap.add_argument("--mars", default=DEFAULT_MARS)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--port", type=int, default=8841)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--backends-file", default=None,
                    help="a backends.json for MARS (configured runtimes such as kimi-k3)")
    args = ap.parse_args(argv)

    from mentis.core import service
    from mentis.execution import FakeExecution
    service.unavailable_execution = lambda why: FakeExecution()  # never the production fallback
    from tests.conformance_runtime import scenarios as S
    from tests.conformance_runtime.profiles import PROFILES
    from tests.conformance_runtime.rig import Rig

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    work = root / f"{args.runtime}-{stamp}"
    work.mkdir()
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    report = {"runtime": args.runtime, "model": args.model, "mode": "offline" if args.offline else "live",
              "started": stamp, "scenarios": {}, "live_brain_before": live_counts()}
    rig = None
    try:
        if args.offline:
            rig = Rig(args.runtime, root=work, profile=PROFILES[args.runtime], model=args.model)
        else:
            import shlex
            data = work / "mars-data"
            data.mkdir()
            os.environ["MARS_DATA_DIR"] = str(data)
            os.environ["MARS_BACKENDS_FILE"] = args.backends_file or str(data / "backends.json")
            mars = shlex.split(args.mars, posix=False)
            if "--data-dir" not in mars:
                mars = mars[:-1] + ["--data-dir", str(data), mars[-1]] if mars[-1] == "stdio" \
                    else mars + ["--data-dir", str(data), "stdio"]
            rig = Rig(args.runtime, root=work, model=args.model, mars=mars, port=args.port)
            report["mars"] = mars
            report["server"] = rig.base
            report["backends"] = [{k: b.get(k) for k in ("id", "available", "reason", "contract")}
                                  for b in rig.state.agents._backends() if b.get("id") == args.runtime]
        for name in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
            t0 = time.time()
            try:
                checks = [c.as_dict() for c in S.ALL[name](rig)]
            except Exception as exc:                      # noqa: BLE001
                checks = [{"name": name, "group": "universal", "status": "failed",
                           "evidence": f"the scenario raised {type(exc).__name__}: {exc}",
                           "trace": traceback.format_exc()[-1500:]}]
            report["scenarios"][name] = {"seconds": round(time.time() - t0, 1), "checks": checks}
            print(f"[{args.runtime}] {name}: " + ", ".join(f"{c['name']}={c['status']}" for c in checks),
                  flush=True)
    finally:
        if rig is not None:
            try:
                rig.close()
            except Exception:                             # noqa: BLE001
                pass
        report["live_brain_after"] = live_counts()
        report["live_brain_unchanged"] = report["live_brain_before"] == report["live_brain_after"]
        out = evidence / f"{args.runtime}-{stamp}.json"
        out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        lines = [f"# {args.runtime} ({report['mode']}, model {args.model}) {stamp}",
                 f"live Brain unchanged: {report['live_brain_unchanged']} "
                 f"({report['live_brain_before']} -> {report['live_brain_after']})", ""]
        for name, sc in report["scenarios"].items():
            for c in sc["checks"]:
                lines.append(f"- {name}/{c['name']} [{c['group']}]: **{c['status']}** - {c['evidence']}")
        (evidence / f"{args.runtime}-{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"evidence: {out}")
        if not args.keep:
            time.sleep(1)
            shutil.rmtree(work, ignore_errors=True)
    return 0 if report["live_brain_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
