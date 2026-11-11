"""The rig each conformance test runs against: offline (a scripted runtime per profile) unless
`MENTIS_RUNTIME_CONFORMANCE` selects a live runtime, in which case only that runtime runs."""

from __future__ import annotations

import os

import pytest

from tests.conformance_runtime.profiles import PROFILES, RUNTIMES
from tests.conformance_runtime.rig import (MARS_ENV, ROOT_ENV, Rig, fresh_root,
                                          live_selection)


def _runtimes():
    live = live_selection()
    return [live[0]] if live else list(RUNTIMES)


def pytest_generate_tests(metafunc):
    if "runtime" in metafunc.fixturenames:
        metafunc.parametrize("runtime", _runtimes())


@pytest.fixture()
def rig(runtime, tmp_path):
    live = live_selection()
    if live:
        import shlex
        mars = os.environ.get(MARS_ENV)
        if not mars:
            pytest.skip(f"{MARS_ENV} names no MARS command for the live mode")
        made = Rig(runtime, root=fresh_root(os.environ.get(ROOT_ENV), runtime),
                   model=live[1], mars=shlex.split(mars, posix=False))
    else:
        made = Rig(runtime, root=tmp_path, profile=PROFILES[runtime])
    yield made
    made.close()
