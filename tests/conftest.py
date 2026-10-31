"""Suite-wide fixtures.

Lifted from Mark IV's tests/conftest.py and pruned: no runtime adapters exist
any more, so the capacity, Codex-home, child-guard and wake-check fixtures
went with them. Agents run through `mentis.execution`; every service a test
makes gets its own `FakeExecution` (`fake_execution` below), so no test can
start a real agent.
"""

from __future__ import annotations

import os

# EVERY SHARED READING ANSWER IS CHECKED for in-place change on reuse
# (`mentis.conversation._MEMO_CHECK`): set before anything imports it.
os.environ.setdefault("MENTIS_MEMO_CHECK", "1")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fake_execution(monkeypatch):
    """NO TEST RUNS A REAL AGENT. A `MentisService` made without an
    `Execution` (every `_State` a test builds) gets a fresh `FakeExecution`
    instead of the production fallback, so dispatch selects among its
    backends (claude, codex, antigravity, local) and every run answers
    "done". A test that wants other behaviour sets `st.agents.execution.script`
    or passes its own `execution`."""
    from mentis.core import service
    from mentis.execution import FakeExecution
    monkeypatch.setattr(service, "unavailable_execution",
                        lambda why: FakeExecution())


@pytest.fixture(autouse=True)
def no_machine_source_cache(tmp_path, monkeypatch):
    """NO TEST STAGES INTO THIS MACHINE'S SOURCE CACHE. A folder preview
    stages bytes under `source_cache()`, which defaults to the machine's own
    %LOCALAPPDATA% cache; its stage count and byte bounds include leftovers
    from other processes, so a test that did not choose a cache shared one
    with every earlier run and was refused once they filled it. Each test
    gets its own; a test that names one still does (`monkeypatch.setenv`)."""
    monkeypatch.setenv("MENTIS_SOURCE_CACHE", str(tmp_path / "machine-source-cache"))


@pytest.fixture(autouse=True)
def brains_shaped_before_the_presets(request, monkeypatch):
    """A TEST BRAIN IS ONE SHAPED BEFORE THE PRESETS (P12). A brand-new brain
    starts Home on Triage and conversations on Focus
    (mentis/fluid/arrangements.py NEW_DEFAULTS); every fixture brain is
    brand-new, and the suites written before the presets test Home and the
    Stage as Mentis starts them. So here a fixture brain is one somebody
    already shaped -- no default until one is chosen -- and a module that
    tests the new defaults says so with `NEW_BRAIN_DEFAULTS = True`."""
    if getattr(request.module, "NEW_BRAIN_DEFAULTS", False):
        return
    from mentis.fluid import arrangements
    monkeypatch.setattr(arrangements, "_brand_new", lambda root: False)


def pytest_configure(config):
    """TEST SERVERS NOTICE SHUTDOWN WITHIN 50 MS. `serve_forever` checks its
    shutdown flag every `poll_interval`, 0.5 s by default, so each teardown's
    `shutdown()` waited ~0.44 s. Only this test process is changed;
    `mentis.web.serve()` in production keeps the standard 0.5 s."""
    import functools
    import socketserver

    if not getattr(socketserver.BaseServer.serve_forever, "_mentis_fast", False):
        real = socketserver.BaseServer.serve_forever

        @functools.wraps(real)
        def serve_forever(self, poll_interval=0.05):
            return real(self, poll_interval)

        serve_forever._mentis_fast = True
        socketserver.BaseServer.serve_forever = serve_forever


import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402


class _AsTheInterface(urllib.request.BaseHandler):
    """THE TEST PROCESS STANDS WHERE THE OWNER'S INTERFACE STANDS.

    Every JSON route needs `X-Mentis-Client: 1` (mentis/web CLIENT_HEADER).
    The suite's per-file urllib helpers talk to their test servers as that
    interface, so the header is added here, once, to urllib requests for a
    loopback `/api/` path -- and nowhere else. A request that already names
    it is left alone."""

    handler_order = 100

    def http_request(self, req):
        u = urllib.parse.urlparse(req.full_url)
        if (u.hostname in ("127.0.0.1", "localhost", "::1")
                and u.path.startswith("/api/")
                and not req.has_header("X-mentis-client")):
            req.add_unredirected_header("X-Mentis-Client", "1")
        return req


urllib.request.install_opener(urllib.request.build_opener(_AsTheInterface()))
