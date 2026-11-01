"""Rows L and M decided per test, so equal totals can't hide a repair and a new regression.

    python tools/r1/compare_outcomes.py pytest <baseline.json> <junit.xml>
    python tools/r1/compare_outcomes.py npm <baseline.json> <output of npm test>
    python tools/r1/compare_outcomes.py record-pytest <junit.xml> --commit <c> --command <text>
    python tools/r1/compare_outcomes.py record-npm <output> --commit <c> --command <text>

Comparing prints each difference and exits 1 on any: a test missing, a test added, or an outcome
changed, in either direction. Exit 0 means every test has its baseline outcome. Pytest's own exit
code isn't the row's: the baseline's allowed failure makes it nonzero. Recording prints the baseline
as JSON.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET


def pytest_outcomes(junit) -> dict[str, str]:
    out: dict[str, str] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        kinds = {child.tag for child in case}
        outcome = ("error" if "error" in kinds else "failed" if "failure" in kinds
                   else "skipped" if "skipped" in kinds else "passed")
        module = case.get("classname", "")
        # `tests.test_a.TestB` is class TestB of tests/test_a.py.
        parts = module.split(".")
        cut = next((i for i, p in enumerate(parts) if p.startswith("test_")), len(parts) - 1)
        path = "/".join(parts[:cut + 1]) + ".py"
        node = "::".join([path, *parts[cut + 1:], case.get("name", "")])
        if node in out:
            raise SystemExit(f"{junit} names {node} twice")
        out[node] = outcome
    return out


def npm_outcomes(text: str) -> dict[str, str]:
    """`tests/run.mjs` says `ok   <file>`, `FAIL <file>` or `skip <file> (why)`."""
    out = {}
    for line in text.splitlines():
        found = re.match(r"(ok  |FAIL|skip) +(\S+_unit\.mjs)", line)
        if found:
            out[found.group(2)] = {"ok  ": "passed", "FAIL": "failed",
                                   "skip": "skipped"}[found.group(1)]
    return out


def differences(want: dict[str, str], got: dict[str, str]) -> list[str]:
    wrong = []
    for node in sorted(set(want) | set(got)):
        if node not in got:
            wrong.append(f"missing: {node}, baseline {want[node]}")
        elif node not in want:
            wrong.append(f"added: {node}, {got[node]}")
        elif want[node] != got[node]:
            wrong.append(f"changed: {node}, baseline {want[node]}, now {got[node]}")
    return wrong


def _read(path) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="compare per-test outcomes with a baseline")
    ap.add_argument("action", choices=("pytest", "npm", "record-pytest", "record-npm"))
    ap.add_argument("paths", nargs="+", type=pathlib.Path)
    ap.add_argument("--commit")
    ap.add_argument("--command")
    a = ap.parse_args(argv)
    if a.action.startswith("record"):
        got = (pytest_outcomes(a.paths[0]) if a.action == "record-pytest"
               else npm_outcomes(_read(a.paths[0])))
        print(json.dumps({"commit": a.commit, "command": a.command,
                          "totals": dict(sorted(collections.Counter(got.values()).items())),
                          "outcomes": dict(sorted(got.items()))}, indent=1))
        return 0
    baseline, result = a.paths
    want = json.loads(baseline.read_text(encoding="utf-8"))["outcomes"]
    got = pytest_outcomes(result) if a.action == "pytest" else npm_outcomes(_read(result))
    wrong = differences(want, got)
    if not got:
        wrong.append(f"{result} holds no outcomes at all")
    for line in wrong:
        print(line, file=sys.stderr)
    totals = dict(sorted(collections.Counter(got.values()).items()))
    print(f"{len(got)} tests, {totals}, {len(wrong)} different from {baseline.name}")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
