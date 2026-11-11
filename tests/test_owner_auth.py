"""THE OWNER'S AUTHENTICATION on owner-only HTTP operations (round 3 final, B3).

A local process that can reach the port, send `X-Mentis-Client: 1` and even read the boot secret is
not the owner: a state-changing owner route answers 401 OwnerAuthRequired unless the request carries
a live session the owner's passphrase produced (cookie for the browser, bearer for a tool). Worker
grants keep their own door, unchanged. Requests here are made with `http.client`, which the suite's
urllib opener (tests/conftest.py) does not touch, so each one sends exactly what it says.
"""
from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
from pathlib import Path

from mentis import owner_auth
from mentis.web import _Handler, _State, fixture

PASSPHRASE = "a fixture passphrase for B3"


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A server over a fixture Brain with its OWN credential (not the suite's)."""
    monkeypatch.setenv(owner_auth.CREDENTIAL_ENV, str(tmp_path / "own.owner-auth.json"))
    built = fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    handler = type("H", (_Handler,), {"state": st})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    cred = owner_auth.for_brain(st.path)
    yield {"port": httpd.server_address[1], "st": st, "who": built["who"], "cred": cred,
           "tmp": tmp_path}
    httpd.shutdown()
    httpd.server_close()
    st.agents.close()
    st.corpus.close()


def call(port, method, path, body=None, headers=None, client=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = {"X-Mentis-Client": "1"} if client else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    raw = r.read()
    out = {"status": r.status, "headers": r.headers, "raw": raw}
    try:
        out["json"] = json.loads(raw)
    except ValueError:
        out["json"] = None
    conn.close()
    return out


def new_conversation(port, headers=None, name="b3 probe"):
    return call(port, "POST", "/api/conversations", {"name": name}, headers)


def login(port, passphrase=PASSPHRASE, **extra):
    return call(port, "POST", owner_auth.LOGIN_ROUTE, {"passphrase": passphrase, **extra})


def cookie_of(answer) -> str:
    set_cookie = answer["headers"].get("Set-Cookie")
    return set_cookie.split(";", 1)[0]


# -- no credential ------------------------------------------------------------------------------

def test_no_credential_refuses_owner_operations_and_names_the_command(server):
    got = new_conversation(server["port"])
    assert got["status"] == 401
    body = got["json"]
    assert body["kind"] == "OwnerAuthRequired" and body["login"] == "/owner/login"
    assert body["configured"] is False
    assert "python -m mentis.owner_auth set" in body["error"]
    # login itself says how to set one
    li = login(server["port"])
    assert li["status"] == 409 and li["json"]["kind"] == "OwnerAuthNotConfigured"
    assert "python -m mentis.owner_auth set" in li["json"]["error"]


def test_locality_client_header_and_boot_secret_are_not_the_owner(server):
    server["cred"].set_passphrase(PASSPHRASE)
    for extra in ({}, {"X-Mentis-Boot-Secret": "anything", "X-Mentis-Peer": "127.0.0.1"},
                  {"Authorization": "Bearer not-a-session"},
                  {"Cookie": f"{server['cred'].cookie_name()}=forged"}):
        got = new_conversation(server["port"], extra)
        assert got["status"] == 401, extra
        assert got["json"]["kind"] == "OwnerAuthRequired"
        assert got["json"]["configured"] is True


# -- login, cookie, bearer, logout, expiry -------------------------------------------------------

def test_wrong_passphrase_is_refused(server):
    server["cred"].set_passphrase(PASSPHRASE)
    got = login(server["port"], "not the passphrase at all")
    assert got["status"] == 401 and got["json"]["kind"] == "OwnerAuthFailed"
    assert "Set-Cookie" not in got["headers"]
    assert server["cred"].data()["sessions"] == []


def test_cookie_session_admits_owner_operations(server):
    server["cred"].set_passphrase(PASSPHRASE)
    got = login(server["port"])
    assert got["status"] == 200 and "token" not in got["json"]
    sc = got["headers"].get("Set-Cookie")
    for attr in ("HttpOnly", "SameSite=Strict", "Path=/", "Max-Age="):
        assert attr in sc
    assert sc.startswith(owner_auth.COOKIE_PREFIX)
    made = new_conversation(server["port"], {"Cookie": cookie_of(got)})
    assert made["status"] == 200, made["json"]
    who = call(server["port"], "GET", owner_auth.SESSION_INFO_ROUTE,
               headers={"Cookie": cookie_of(got)})["json"]
    assert who["authenticated"] is True and who["via"] == "cookie"
    # only the digest is kept
    stored = json.dumps(server["cred"].data())
    assert cookie_of(got).split("=", 1)[1] not in stored


def test_bearer_token_from_login_and_logout_ends_it(server):
    server["cred"].set_passphrase(PASSPHRASE)
    got = login(server["port"], token=True, label="a tool")
    token = got["json"]["token"]
    assert "Set-Cookie" not in got["headers"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert new_conversation(server["port"], bearer)["status"] == 200
    out = call(server["port"], "POST", owner_auth.LOGOUT_ROUTE, {}, bearer)
    assert out["status"] == 200 and out["json"]["ended"] is True
    assert new_conversation(server["port"], bearer)["status"] == 401


def test_cookie_logout_clears_the_cookie(server):
    server["cred"].set_passphrase(PASSPHRASE)
    c = {"Cookie": cookie_of(login(server["port"]))}
    out = call(server["port"], "POST", owner_auth.LOGOUT_ROUTE, {}, c)
    assert "Max-Age=0" in out["headers"].get("Set-Cookie")
    assert new_conversation(server["port"], c)["status"] == 401


def test_an_expired_session_is_refused(server):
    server["cred"].set_passphrase(PASSPHRASE)
    token, _ = server["cred"].issue(kind="bearer", ttl_s=0.2)
    bearer = {"Authorization": f"Bearer {token}"}
    time.sleep(0.4)
    assert new_conversation(server["port"], bearer)["status"] == 401


def test_changing_the_passphrase_ends_every_session(server):
    server["cred"].set_passphrase(PASSPHRASE)
    token = login(server["port"], token=True)["json"]["token"]
    server["cred"].set_passphrase(PASSPHRASE + " changed")
    assert new_conversation(server["port"], {"Authorization": f"Bearer {token}"})["status"] == 401


def test_failed_logins_are_throttled(server):
    server["cred"].set_passphrase(PASSPHRASE)
    for _ in range(owner_auth.FAILS_ALLOWED):
        assert login(server["port"], "wrong wrong wrong")["status"] == 401
    got = login(server["port"])                     # even the right one, while throttled
    assert got["status"] == 429 and got["json"]["kind"] == "OwnerAuthThrottled"
    assert int(got["headers"]["Retry-After"]) > 0


# -- what stays as it was -----------------------------------------------------------------------

def test_client_header_is_still_required_with_a_session(server):
    server["cred"].set_passphrase(PASSPHRASE)
    token = login(server["port"], token=True)["json"]["token"]
    got = call(server["port"], "POST", "/api/conversations", {"name": "x"},
               {"Authorization": f"Bearer {token}"}, client=False)
    assert got["status"] == 403 and "X-Mentis-Client" in got["json"]["error"]
    # and login itself needs it: it is a JSON route like any other
    assert call(server["port"], "POST", owner_auth.LOGIN_ROUTE, {"passphrase": PASSPHRASE},
                client=False)["status"] == 403


def test_reads_are_not_gated(server):
    server["cred"].set_passphrase(PASSPHRASE)
    assert call(server["port"], "GET", "/api/conversations")["status"] == 200
    assert call(server["port"], "GET", "/api/server", client=False)["status"] == 200


def test_hand_started_session_route_yields_a_worker_grant_not_owner_authority(server):
    """EXEMPT: `/api/worker/session` hands out a manual-session grant (agent authority); with no
    owner session and no passphrase set at all it still answers, and the grant it gives opens no
    owner route."""
    st = server["st"]
    got = call(server["port"], "POST", "/api/worker/session",
               {"runtime": "claude", "corpus": st.path})
    assert got["status"] == 200, got["json"]
    grant = got["json"]["grant"]
    assert got["json"]["scope"] == "manual-session"
    # the grant reaches /api/worker
    op = call(server["port"], "POST", "/api/worker",
              {"op": "orient", "args": {}, "corpus": st.path}, {"X-Mentis-Worker": grant})
    assert op["status"] == 200, op["json"]
    # and is refused anywhere else, as before (403, not taken for the owner)
    other = new_conversation(server["port"], {"X-Mentis-Worker": grant})
    assert other["status"] == 403 and other["json"]["kind"] == "PermissionError"
    # nor can it name the owner as its Participant
    owner_pid = server["who"]["@brian"]
    bad = call(server["port"], "POST", "/api/worker/session",
               {"runtime": "claude", "corpus": st.path, "participant": owner_pid})
    assert bad["status"] == 403
    end = call(server["port"], "POST", "/api/worker/session/end",
               {"grant": grant, "corpus": st.path})
    assert end["status"] == 200


def test_every_other_owner_post_door_is_gated(server):
    """Not only `_api`: Fluid's command door, staging an artifact, a look's picture and an
    exchange import are refused before they read anything."""
    server["cred"].set_passphrase(PASSPHRASE)
    for path, headers in (("/fluid/api/posts", {}),
                          ("/api/artifacts", {"X-Mentis-Upload": "1"}),
                          ("/api/presentation/pictures", {"X-Mentis-Upload": "1"}),
                          ("/api/exchange/import/preview", {"X-Mentis-Upload": "1"}),
                          ("/api/entries", {}),
                          ("/api/conversations/ent-x/turns", {})):
        got = call(server["port"], "POST", path, {"x": 1}, headers)
        assert got["status"] == 401, (path, got["status"], got["json"])
        assert got["json"]["kind"] == "OwnerAuthRequired"


def test_a_grant_header_opens_no_owner_door(server):
    """Round-3 final review (blocker): the owner gate leaves a request carrying a worker
    grant to its door, so EVERY owner POST door must refuse a grant itself. A bogus grant
    and no owner session never gets a 2xx anywhere but `/api/worker`."""
    server["cred"].set_passphrase(PASSPHRASE)
    bogus = {"X-Mentis-Worker": "not-a-real-grant"}
    for path, headers in (("/fluid/api/posts", {}),
                          ("/api/artifacts", {"X-Mentis-Upload": "1"}),
                          ("/api/presentation/pictures", {"X-Mentis-Upload": "1"}),
                          ("/api/exchange/import/preview", {"X-Mentis-Upload": "1"}),
                          ("/api/exchange/import/stage", {"X-Mentis-Upload": "1"}),
                          ("/api/exchange/import/stage", {}),
                          ("/api/entries", {}),
                          ("/api/conversations/ent-x/turns", {})):
        got = call(server["port"], "POST", path, {"x": 1}, {**headers, **bogus})
        assert got["status"] in (401, 403), (path, got["status"], got["json"])
    assert not (Path(server["st"].path) / ".import-staged.zip").exists()


def test_the_login_page_is_plain_and_same_origin(server):
    got = call(server["port"], "GET", "/owner/login", client=False)
    assert got["status"] == 200
    assert got["headers"]["Content-Type"].startswith("text/html")
    csp = got["headers"]["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp
    page = got["raw"].decode()
    assert "http://" not in page and "https://" not in page    # no external assets
    assert "python -m mentis.owner_auth set" in page           # none set yet: says how
    server["cred"].set_passphrase(PASSPHRASE)
    page = call(server["port"], "GET", "/owner/login", client=False)["raw"].decode()
    assert "/api/owner/login" in page and "disabled" not in page


def test_credential_lives_beside_the_brain_not_in_it(tmp_path, monkeypatch):
    monkeypatch.delenv(owner_auth.CREDENTIAL_ENV, raising=False)
    brain = tmp_path / "brain"
    brain.mkdir()
    path = owner_auth.credential_path(brain)
    assert path.parent == brain.resolve().parent and path.name == "brain.owner-auth.json"
    assert brain.resolve() not in path.parents


def test_console_sets_and_issues_without_echo(tmp_path, monkeypatch, capsys):
    target = tmp_path / "c.json"
    monkeypatch.setenv("B3_FIXTURE_PASS", PASSPHRASE)
    assert owner_auth.main(["set", "--file", str(target),
                            "--passphrase-from-env", "B3_FIXTURE_PASS"]) == 0
    assert owner_auth.main(["token", "--file", str(target),
                            "--passphrase-from-env", "B3_FIXTURE_PASS"]) == 0
    out = capsys.readouterr()
    assert PASSPHRASE not in out.out + out.err + target.read_text()
    token = out.out.strip().splitlines()[-1]
    assert owner_auth.Credential(target).check(token) is not None
    monkeypatch.setenv("B3_FIXTURE_PASS", "short")
    with pytest.raises(ValueError):
        owner_auth.main(["set", "--file", str(target), "--passphrase-from-env",
                         "B3_FIXTURE_PASS"])


def test_the_release_route_table_is_the_binary_default_plus_the_login_page():
    """The unchanged front (magnet-1c0c13a) serves `GET *` itself; the release passes it this table
    so `/owner/login` reaches Python. Nothing else may differ from the binary's own default."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    default = json.loads((root / "crates/mentis-server/route-table.default.json").read_text())
    release = json.loads((root / "tools/release_modernize/route-table.json").read_text())
    added = [r for r in release["routes"] if r not in default["routes"]]
    assert added == [{"id": "owner-login", "method": "GET", "path": "/owner/login",
                      "owner": "python"}]
    assert [r for r in release["routes"] if r != added[0]] == default["routes"]
    assert release["format"] == default["format"]


def test_parallel_logins_get_no_more_guesses_than_the_throttle_allows(tmp_path):
    """Round-3 final review S2: the throttle is checked and the attempt recorded under one
    lock, so parallel wrong guesses cannot exceed FAILS_ALLOWED in a window."""
    import concurrent.futures
    cred = owner_auth.Credential(tmp_path / "c.json") if hasattr(owner_auth, "Credential") \
        else owner_auth.for_file(tmp_path / "c.json")
    cred.set_passphrase(PASSPHRASE)
    outcomes = []

    def guess(i):
        try:
            cred.login(f"wrong-{i}", kind="test")
            return "ok"
        except owner_auth.Throttled:
            return "throttled"
        except PermissionError:
            return "wrong"
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        outcomes = list(pool.map(guess, range(24)))
    assert outcomes.count("wrong") <= owner_auth.FAILS_ALLOWED, outcomes
    assert outcomes.count("ok") == 0
    with pytest.raises(owner_auth.Throttled):
        cred.login(PASSPHRASE, kind="test")


# -- trusted-local installations (owner decision 2026-11-11) ---------------------------------

def test_a_trusted_local_installation_needs_no_login_and_grants_nothing_more(server):
    """Explicit trusted-local mode: owner writes work without a passphrase or a session; the
    worker-grant boundary is unchanged (a forged grant is still refused at every owner door)."""
    cred = server["cred"]
    cred.trust_local(owner_auth.TRUSTED_LOCAL_ACCEPTANCE)
    assert cred.trusted_local() and cred.configured()
    got = call(server["port"], "POST", "/api/conversations", {"name": "trusted local"})
    assert got["status"] == 200, got
    info = call(server["port"], "GET", "/api/owner/session")["json"]
    assert info["authenticated"] is True and info["mode"] == "trusted-local"
    assert info["via"] == "trusted-local" and info["expires"] is None
    login = call(server["port"], "POST", "/api/owner/login", {"passphrase": "anything"})
    assert login["status"] == 200 and login["json"]["mode"] == "trusted-local"
    assert "no login is needed" in call(server["port"], "GET", "/owner/login",
                                        client=False)["raw"].decode()
    bogus = {"X-Mentis-Worker": "not-a-real-grant"}
    for path, headers in (("/api/exchange/import/stage", {"X-Mentis-Upload": "1"}),
                          ("/api/entries", {}), ("/fluid/api/posts", {})):
        got = call(server["port"], "POST", path, {"x": 1}, {**headers, **bogus})
        assert got["status"] in (401, 403), (path, got["status"])
    assert not (Path(server["st"].path) / ".import-staged.zip").exists()


def test_switching_back_to_a_passphrase_requires_login_again(server):
    cred = server["cred"]
    cred.trust_local("test")
    cred.set_passphrase(PASSPHRASE)
    assert not cred.trusted_local()
    got = call(server["port"], "POST", "/api/conversations", {"name": "x"})
    assert got["status"] == 401 and got["json"]["kind"] == "OwnerAuthRequired"


@pytest.mark.parametrize("mode", ["trusted", "TRUSTED-LOCAL", "", None, True])
def test_anything_but_the_exact_trusted_local_mode_is_not_trusted(server, mode):
    cred = server["cred"]
    cred.path.write_text(json.dumps({"format": owner_auth.FORMAT, "install": "x1",
                                     "mode": mode, "sessions": []}), encoding="utf-8")
    assert not cred.trusted_local()
    got = call(server["port"], "POST", "/api/conversations", {"name": "x"})
    assert got["status"] == 401, got


def test_trust_local_from_the_console_records_the_acceptance(tmp_path, capsys):
    target = tmp_path / "c.json"
    assert owner_auth.main(["trust-local", "--file", str(target)]) == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["mode"] == "trusted-local" and "not a sandbox" in data["accepted"]
    assert "passphrase" not in data
    owner_auth.main(["status", "--file", str(target)])
    assert '"mode": "trusted-local"' in capsys.readouterr().out
