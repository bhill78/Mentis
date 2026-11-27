"""ORDINARY RUNS ARE PARALLEL WHEN THEY CAN BE (loaded early by `-p` in pyproject.toml).

With pytest-xdist installed (the test venv), a run that did not choose `-n` itself gets
`-n 8 --dist loadfile`: one file per worker, so each file's fixtures stay in one process.
Without it (the shared runtime venv must not carry test-only packages), runs stay serial
rather than failing on an unknown option. `-n 0` runs a targeted test in-process."""
import importlib.util


def pytest_load_initial_conftests(early_config, parser, args):
    spec = importlib.util.find_spec("xdist")
    if spec is None or spec.origin is None:     # absent, or only a leftover folder
        return
    if any(a == "-n" or a.startswith(("-n", "--numprocesses", "--dist")) for a in args):
        return
    args[:] = ["-n", "8", "--dist", "loadfile", *args]
