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

# MODEL SUITABILITY AND OUTCOME EVIDENCE (Workstream C) stand in for tests
# only until the real modules are merged (`tests/_suitability_stub.py`).
from tests import _suitability_stub  # noqa: E402

_suitability_stub.install()


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


#: WEBKIT CAN HANG AT LAUNCH ON THIS MACHINE, AND IT IS NOT FIXED
#: (opr-74d4f3d5f15a). Playwright's WebKit sometimes starts its browser process
#: and never opens a page, and the test waits for ever: Quiet Chat round 7's
#: carrier sat 20 minutes on one (2026-11-07). So a browser test's `webkit`
#: case is skipped unless it is asked for -- release verification sets
#: MENTIS_QUIET_WEBKIT=1 -- and when it is asked for, a case still running
#: after WEBKIT_HANG_S is stopped with its traceback instead of hanging.
WEBKIT_HANG = "opr-74d4f3d5f15a"
WEBKIT_HANG_S = 600


def _webkit_case(item) -> bool:
    spec = getattr(item, "callspec", None)
    return bool(spec) and spec.params.get("engine") == "webkit"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MENTIS_QUIET_WEBKIT") == "1":
        return
    hung = pytest.mark.skip(
        reason=f"KNOWN HANG, NOT FIXED ({WEBKIT_HANG}): Playwright's WebKit can "
               f"hang at launch on this machine and never return. Skipped by "
               f"default; set MENTIS_QUIET_WEBKIT=1 to run it (release "
               f"verification), bounded to {WEBKIT_HANG_S} s a case.")
    for item in items:
        if _webkit_case(item):
            item.add_marker(hung)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """A WEBKIT CASE THAT WAS ASKED FOR ENDS ITS RUN IF IT HANGS, with every
    thread's traceback, rather than holding whoever started it for ever."""
    if not _webkit_case(item):
        yield
        return
    import faulthandler
    import sys
    sys.stderr.write(f"\n[{WEBKIT_HANG}] {item.nodeid}: stopped with a traceback "
                     f"if still running after {WEBKIT_HANG_S} s\n")
    faulthandler.dump_traceback_later(WEBKIT_HANG_S, exit=True)
    try:
        yield
    finally:
        faulthandler.cancel_dump_traceback_later()


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


def _owner_credential():
    """THE TEST PROCESS IS THE OWNER, AND PROVES IT LIKE THE OWNER DOES.

    Owner-only operations need an owner session (`mentis.owner_auth`, round 3
    final). One credential for the whole run, named by MENTIS_OWNER_AUTH_FILE
    so every server the suite starts -- in this process or a child that
    inherits the environment -- uses it, with one long session minted from it.
    A test of the boundary itself names another file or sends nothing."""
    import atexit
    import shutil
    import tempfile

    from mentis import owner_auth
    # Imported twice (as `conftest` and `tests.conftest`) is still one owner.
    kept = os.environ.get(TOKEN_ENV)
    if kept and os.path.isfile(os.environ.get(owner_auth.CREDENTIAL_ENV, "")):
        return os.environ[owner_auth.CREDENTIAL_ENV], kept
    where = tempfile.mkdtemp(prefix="mentis-test-owner-")
    atexit.register(shutil.rmtree, where, ignore_errors=True)
    path = os.path.join(where, "owner-auth.json")
    os.environ[owner_auth.CREDENTIAL_ENV] = path
    cred = owner_auth.Credential(path)
    cred.set_passphrase(OWNER_PASSPHRASE)
    token, _ = cred.issue(kind="bearer", label="test suite", ttl_s=7 * 24 * 3600)
    os.environ[TOKEN_ENV] = token
    return path, token


#: Where a raw-socket helper finds the suite's owner session (`owner_headers`).
TOKEN_ENV = "MENTIS_TEST_OWNER_TOKEN"
#: The suite's owner passphrase and session (`_owner_credential`).
OWNER_PASSPHRASE = "test-suite-owner-passphrase"
OWNER_CREDENTIAL, OWNER_TOKEN = _owner_credential()
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def owner_headers() -> dict:
    """What an owner client sends: the suite's bearer session."""
    return {"Authorization": f"Bearer {OWNER_TOKEN}"}


class _AsTheInterface(urllib.request.BaseHandler):
    """THE TEST PROCESS STANDS WHERE THE OWNER'S INTERFACE STANDS.

    Every JSON route needs `X-Mentis-Client: 1` (mentis/web CLIENT_HEADER),
    and every owner operation an owner session. The suite's per-file urllib
    helpers talk to their test servers as that interface, so both are added
    here, once, to urllib requests for a loopback `/api/` or `/fluid/api/`
    path -- and nowhere else. A request that already names either is left
    alone for that one."""

    handler_order = 100

    def http_request(self, req):
        u = urllib.parse.urlparse(req.full_url)
        if u.hostname in _LOOPBACK and u.path.startswith("/api/") \
                and not req.has_header("X-mentis-client"):
            req.add_unredirected_header("X-Mentis-Client", "1")
        if (u.hostname in _LOOPBACK
                and (u.path.startswith("/api/") or u.path.startswith("/fluid/api/"))
                and not req.has_header("Authorization")
                and not req.has_header("X-mentis-worker")):
            req.add_unredirected_header("Authorization", f"Bearer {OWNER_TOKEN}")
        return req


urllib.request.install_opener(urllib.request.build_opener(_AsTheInterface()))
