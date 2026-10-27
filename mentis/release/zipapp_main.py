"""The package's entry: `python3.12 mentis-<version>.zip <command>`.

The builder copies this file to `__main__.py` at the root of every package.
It checks the interpreter and hands the command to `mentis.installer`, which
the package carries (`install`, `version`; see that module). A package built
from a commit older than the installer only says what it is.

Nothing here imports beyond the standard library: the zip runs on a bare
Python 3.12, before any dependency is installed.

BOOTSTRAP MODE. A `-win64` package is run by a copy of python.org's
embeddable Python that travels beside it (the desktop installer's
`payload\\bootstrap\\python\\python.exe -I <zip> ...`): no site-packages, no
pip, no venv. Everything the zip itself does -- verify, stage, and `brain
inspect <folder> --json` (S5), which the first-run screen asks before
anything is installed -- uses only the standard library; the rest runs with
the release's own `runtime\\python.exe` once it is staged.
"""

import importlib
import json
import sys
import zipfile


def _release() -> dict:
    try:
        with zipfile.ZipFile(sys.argv[0]) as z:
            return json.loads(z.read("RELEASE.json"))
    except Exception:                                       # noqa: BLE001
        return {}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if sys.version_info[:2] != (3, 12):
        print(f"Mentis needs Python 3.12; this is {sys.version.split()[0]}",
              file=sys.stderr)
        return 2
    try:
        installer = importlib.import_module("mentis.installer")
    except ModuleNotFoundError as e:
        if e.name != "mentis.installer":
            raise
    else:
        if argv[:2] == ["brain", "inspect"]:
            from mentis.brain import inspect
            return inspect.main(argv[2:])
        if not argv or argv[0] in ("-h", "--help", "help"):
            rel = _release()
            print(f"Mentis {rel.get('version', '(unknown version)')} "
                  f"(commit {rel.get('commit', 'unknown')})\n")
            return installer.main(["--help"])     # argparse exits 0
        return installer.main(argv)
    rel = _release()
    print(f"Mentis {rel.get('version', '(unknown version)')} "
          f"(commit {rel.get('commit', 'unknown')})\n\n"
          "usage: python3.12 <package.zip> <command>\n\n"
          "This package carries no installer, so it has no commands. "
          "See INSTALL.md inside the package.")
    return 0 if not argv or argv[0] in ("-h", "--help", "help") else 2


def _utf8_streams() -> None:
    """`-I` ignores PYTHONIOENCODING, and a pipe on Windows otherwise gets
    the ANSI code page: every path a profile may have must still print."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass


if __name__ == "__main__":
    _utf8_streams()
    raise SystemExit(main())
