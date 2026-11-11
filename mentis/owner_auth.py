"""THE OWNER'S AUTHENTICATION for the owner-only HTTP operations (round 3 final, decision 4).

WHAT THIS IS FOR. An agent the owner dispatches runs as the same operating-system user as the
owner's server. Under Unrestricted Host it has a shell and the network. Until this module, every
owner JSON route trusted locality plus `X-Mentis-Client: 1` (`mentis.web.CLIENT_HEADER`): a
cross-site-request guard, not authentication. Any local process could send that header and act as
the owner. Owner-only operations now need a session obtained with the owner's passphrase.

WHAT IT IS NOT. It is HTTP authentication. It does NOT make the Brain safe from a process running
as the same Windows user: such a process can open the Brain through the Python spine with no HTTP
at all (`mentis.web._Handler._api` docstring, "THIS ROUTE IS NOT THE WORST PATH"), read the
browser's cookie store, read this server's memory, or rewrite the credential file below. Closing
those needs a separate OS principal for dispatched work (or the future container). Nothing here
claims more than: a request reaching an owner-only HTTP operation carries a session the owner's
passphrase produced.

THE CREDENTIAL. One JSON file per installation, never inside the Brain:

    MENTIS_OWNER_AUTH_FILE, if set (test rigs, rehearsal servers), else
    <brain>.owner-auth.json, the Brain folder's sibling
    (live: %LOCALAPPDATA%\\Mentis\\Mark-IV\\brain.owner-auth.json)

Beside the Brain rather than in it, because every Brain copy (backups, fixture copies, the rehearsal
Brain) copies the Brain folder: a copy must not inherit the owner's credential, and a server over a
copy at another path finds none until somebody sets one there. Beside it rather than one per
machine, because a development or rehearsal server must be able to have its own.

It holds the passphrase only as a slow salted hash (`hashlib.scrypt`), and the live sessions only
as SHA-256 digests with their expiry: the token itself is given to the client once and never kept.
Sessions are in the file (not only in memory) so a restart or a deploy does not log the owner out,
and so a test or rig can give a server it starts a session (`issue`) without a login round-trip.

SET IT (the owner, at a console; the passphrase is asked twice and never echoed):

    python -m mentis.owner_auth set --brain <brain folder>
    python -m mentis.owner_auth status --brain <brain folder>
    python -m mentis.owner_auth token --brain <brain folder>    # a bearer token for an owner tool
    python -m mentis.owner_auth revoke --brain <brain folder>   # end every session

`--passphrase-from-env NAME` reads it from an environment variable instead: FOR TEST FIXTURES AND
REHEARSAL RIGS ONLY, never for the owner's own credential.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sys
import threading
import time

CREDENTIAL_ENV = "MENTIS_OWNER_AUTH_FILE"
#: A programmatic owner client's token, for the owner's own tools (`client_headers`).
TOKEN_ENV = "MENTIS_OWNER_TOKEN"
SUFFIX = ".owner-auth.json"
FORMAT = 1

COOKIE_PREFIX = "mentis_owner_"
LOGIN_PAGE = "/owner/login"
LOGIN_ROUTE = "/api/owner/login"
LOGOUT_ROUTE = "/api/owner/logout"
SESSION_INFO_ROUTE = "/api/owner/session"

#: How long a session lasts from login. A browser session and a bearer token alike.
SESSION_TTL_S = 14 * 24 * 3600
#: The most live sessions one credential keeps; the oldest goes first.
MOST_SESSIONS = 64
MIN_PASSPHRASE = 12

#: scrypt at 2^15 x 8: about 32 MiB and a tenth of a second a try on this class of machine.
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 15, 8, 1, 32
SCRYPT_MAXMEM = 64 * 1024 * 1024

#: Failed logins: at most FAILS_ALLOWED in FAIL_WINDOW_S per credential, then refused until the
#: window has moved on. Per credential, not per client: every client here is loopback.
FAILS_ALLOWED = 5
FAIL_WINDOW_S = 300.0



#: How many scrypt verifications may run at once (each holds about 32 MiB).
SCRYPT_AT_ONCE = 2
_SCRYPT_SLOTS = threading.BoundedSemaphore(SCRYPT_AT_ONCE)

class NotConfigured(RuntimeError):
    """No owner passphrase is set for this installation."""


class Throttled(RuntimeError):
    def __init__(self, retry_after: int):
        super().__init__(f"too many failed logins: try again in {retry_after} s")
        self.retry_after = retry_after


def credential_path(brain: str | os.PathLike) -> pathlib.Path:
    """Where this Brain's owner credential lives. See the module docstring."""
    named = os.environ.get(CREDENTIAL_ENV)
    if named:
        return pathlib.Path(named).resolve()
    b = pathlib.Path(brain).resolve()
    return b.parent / (b.name + SUFFIX)


def set_command(brain: str | os.PathLike | None = None) -> str:
    where = f' --brain "{brain}"' if brain else " --brain <brain folder>"
    return f"python -m mentis.owner_auth set{where}"


def _now() -> float:
    return time.time()


def _iso(t: float) -> str:
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).isoformat(timespec="seconds")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "surrogateescape")).hexdigest()


def _scrypt(passphrase: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(passphrase.encode("utf-8", "surrogateescape"), salt=salt, n=n, r=r,
                          p=p, dklen=dklen, maxmem=SCRYPT_MAXMEM)


class Credential:
    """One credential file. Reads follow the file (by mtime and size), so a passphrase set at the
    console takes effect without a restart; writes replace it whole."""

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self._lock = threading.RLock()
        self._seen: tuple | None = None
        self._data: dict | None = None
        self._fails: list[float] = []

    # -- the file ----------------------------------------------------------------------------
    def _stamp(self):
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def data(self) -> dict | None:
        with self._lock:
            stamp = self._stamp()
            if stamp is None:
                self._seen, self._data = None, None
                return None
            if stamp != self._seen:
                try:
                    loaded = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    loaded = None
                if not (isinstance(loaded, dict) and loaded.get("format") == FORMAT
                        and isinstance(loaded.get("passphrase"), dict)):
                    loaded = None
                self._seen, self._data = stamp, loaded
            return self._data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        for attempt in range(20):
            try:
                os.replace(tmp, self.path)
                break
            except PermissionError:     # Windows: a reader has it open for a moment
                if attempt == 19:
                    with contextlib.suppress(OSError):
                        tmp.unlink()
                    raise
                time.sleep(0.05)
        self._seen, self._data = None, None

    def configured(self) -> bool:
        return self.data() is not None

    def install_id(self) -> str | None:
        d = self.data()
        return d.get("install") if d else None

    def cookie_name(self) -> str:
        """Per installation: a browser keeps cookies per host, not per port, so a development
        server's login on 127.0.0.1 must not replace DAY-TO-DAY's (or be taken for it)."""
        return COOKIE_PREFIX + (self.install_id() or "none")

    # -- the passphrase ------------------------------------------------------------------------
    def set_passphrase(self, passphrase: str) -> None:
        """Set or change it. Every session ends with the old passphrase."""
        if not isinstance(passphrase, str) or len(passphrase) < MIN_PASSPHRASE:
            raise ValueError(f"a passphrase is at least {MIN_PASSPHRASE} characters")
        salt = secrets.token_bytes(16)
        key = _scrypt(passphrase, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN)
        with self._lock:
            old = self.data() or {}
            self._write({
                "format": FORMAT,
                "about": "Mentis owner credential: a scrypt hash and session digests only. "
                         "Not part of the Brain; never copied with it.",
                "install": old.get("install") or secrets.token_hex(6),
                "set_at": _iso(_now()),
                "passphrase": {"scheme": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
                               "salt": salt.hex(), "hash": key.hex()},
                "sessions": [],
            })

    def _verify(self, passphrase: str) -> bool:
        d = self.data()
        if d is None:
            raise NotConfigured(f"no owner passphrase is set: run {set_command()}")
        ph = d["passphrase"]
        try:
            got = _scrypt(passphrase, bytes.fromhex(ph["salt"]), int(ph["n"]), int(ph["r"]),
                          int(ph["p"]), len(bytes.fromhex(ph["hash"])))
        except (KeyError, ValueError, TypeError):
            return False
        return hmac.compare_digest(got, bytes.fromhex(ph["hash"]))

    def login(self, passphrase, *, kind: str, label: str = "") -> tuple[str, float]:
        """(token, expires) for the right passphrase. Raises NotConfigured, Throttled, or
        PermissionError for a wrong one."""
        if not isinstance(passphrase, str) or not passphrase:
            raise PermissionError("a passphrase is required")
        # AN ATTEMPT COUNTS AS A FAILURE FROM THE MOMENT IT IS ADMITTED (round-3 final review
        # S2): checked and recorded under one lock, so N parallel logins get no more than
        # FAILS_ALLOWED guesses a window; a success withdraws its own mark. And at most
        # SCRYPT_AT_ONCE verifications run at once (each scrypt holds ~32 MiB).
        with self._lock:
            now = _now()
            self._fails = [t for t in self._fails if now - t < FAIL_WINDOW_S]
            if len(self._fails) >= FAILS_ALLOWED:
                raise Throttled(int(FAIL_WINDOW_S - (now - self._fails[0])) + 1)
            mark = now
            self._fails.append(mark)
        with _SCRYPT_SLOTS:
            ok = self._verify(passphrase)
        with self._lock:
            if not ok:
                raise PermissionError("that is not the owner's passphrase")
            self._fails.clear()
            return self.issue(kind=kind, label=label)

    # -- sessions ------------------------------------------------------------------------------
    def issue(self, *, kind: str, label: str = "", ttl_s: float = SESSION_TTL_S
              ) -> tuple[str, float]:
        """A new session. Only its digest is kept. Called by `login`, and directly by the console
        command and test rigs that hold the file."""
        with self._lock:
            d = self.data()
            if d is None:
                raise NotConfigured(f"no owner passphrase is set: run {set_command()}")
            d = json.loads(json.dumps(d))
            now = _now()
            token = secrets.token_urlsafe(32)          # 256 bits
            expires = now + ttl_s
            live = [s for s in d.get("sessions") or [] if float(s.get("expires", 0)) > now]
            live.append({"sha256": _digest(token), "kind": kind, "label": str(label)[:80],
                         "created": _iso(now), "expires": expires})
            d["sessions"] = live[-MOST_SESSIONS:]
            self._write(d)
            return token, expires

    def check(self, token) -> dict | None:
        """The live session `token` is, or None. Every stored digest is compared, in constant
        time each, whatever matched first."""
        if not isinstance(token, str) or not token or len(token) > 512:
            return None
        d = self.data()
        if d is None:
            return None
        want = _digest(token).encode()
        now = _now()
        found = None
        for s in d.get("sessions") or []:
            same = hmac.compare_digest(want, str(s.get("sha256", "")).encode())
            if same and float(s.get("expires", 0)) > now and found is None:
                found = s
        return found

    def revoke(self, token) -> bool:
        if not isinstance(token, str) or not token:
            return False
        with self._lock:
            d = self.data()
            if d is None:
                return False
            d = json.loads(json.dumps(d))
            want = _digest(token)
            before = d.get("sessions") or []
            d["sessions"] = [s for s in before
                             if not hmac.compare_digest(want, str(s.get("sha256", "")))]
            if len(d["sessions"]) == len(before):
                return False
            self._write(d)
            return True

    def revoke_all(self) -> int:
        with self._lock:
            d = self.data()
            if d is None:
                return 0
            d = json.loads(json.dumps(d))
            n = len(d.get("sessions") or [])
            d["sessions"] = []
            self._write(d)
            return n


_CREDENTIALS: dict[str, Credential] = {}
_CREDENTIALS_LOCK = threading.Lock()


def for_brain(brain: str | os.PathLike) -> Credential:
    """The one `Credential` this process holds for that Brain's file (so the failed-login count
    is shared by every request)."""
    path = credential_path(brain)
    with _CREDENTIALS_LOCK:
        c = _CREDENTIALS.get(str(path))
        if c is None:
            c = _CREDENTIALS[str(path)] = Credential(path)
        return c


# -- the request side ----------------------------------------------------------------------------

def presented_token(headers, cookie_name: str) -> tuple[str | None, str | None]:
    """(token, "bearer"|"cookie") from `Authorization: Bearer` or this installation's cookie."""
    auth = headers.get("Authorization") or ""
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None, "bearer"
    raw = headers.get_all("Cookie") if hasattr(headers, "get_all") else [headers.get("Cookie")]
    for line in raw or []:
        for part in str(line or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == cookie_name and value:
                return value.strip().strip('"'), "cookie"
    return None, None


def session_cookie(name: str, token: str, expires: float) -> str:
    """HttpOnly; SameSite=Strict; Path=/ (round 3 PLAN.md). Not `Secure`: this server is plain
    HTTP on loopback or a tailnet name, where a Secure cookie would not be kept."""
    max_age = max(0, int(expires - _now()))
    return f"{name}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}"


def cleared_cookie(name: str) -> str:
    return f"{name}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"


def required_answer(configured: bool, brain: str | None = None) -> dict:
    """The 401 body for an owner-only operation without valid owner authentication."""
    if configured:
        error = ("this is an owner operation: log in as the owner "
                 "(a local process or shell is not the owner)")
    else:
        error = ("this is an owner operation, and no owner passphrase is set for this "
                 f"installation: the owner sets one at a console with `{set_command(brain)}`, "
                 "then logs in")
    return {"error": error, "kind": "OwnerAuthRequired", "login": LOGIN_PAGE,
            "configured": configured}


def client_headers(token: str | None = None) -> dict:
    """`Authorization` for an owner tool: the token given, else MENTIS_OWNER_TOKEN, else none."""
    token = token or os.environ.get(TOKEN_ENV)
    return {"Authorization": f"Bearer {token}"} if token else {}


LOGIN_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Mentis owner login</title>
<style>
 :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
 body { margin: 0; min-height: 100vh; display: grid; place-items: center; }
 form { width: min(22rem, calc(100vw - 2rem)); display: grid; gap: .75rem; }
 h1 { font-size: 1.15rem; margin: 0; }
 p { margin: 0; font-size: .9rem; opacity: .8; }
 input, button { font: inherit; padding: .55rem .7rem; }
 #said { min-height: 1.2em; }
</style></head>
<body><form id="f" autocomplete="on">
<h1>Mentis: the owner</h1>
<p>__STATE__</p>
<input type="text" name="username" value="owner" autocomplete="username" hidden>
<input id="p" type="password" autocomplete="current-password" placeholder="Passphrase" required __DISABLED__>
<button __DISABLED__>Log in</button>
<p id="said" role="status"></p>
</form>
<script nonce="__NONCE__">
const f = document.getElementById('f'), said = document.getElementById('said');
function next() {
  const n = new URLSearchParams(location.search).get('next') || '/';
  return (n.startsWith('/') && !n.startsWith('//') && !n.startsWith('/\\\\')) ? n : '/';
}
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  said.textContent = 'Checking\\u2026';
  try {
    const r = await fetch('/api/owner/login', {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-Mentis-Client': '1'},
      body: JSON.stringify({passphrase: document.getElementById('p').value})});
    const b = await r.json().catch(() => ({}));
    if (r.ok) { location.replace(next()); return; }
    said.textContent = b.error || ('refused: ' + r.status);
  } catch (err) { said.textContent = 'could not reach Mentis: ' + err; }
});
</script></body></html>
"""


def login_page(configured: bool, brain: str | None, nonce: str) -> bytes:
    import html
    state = ("Owner operations need the owner's passphrase." if configured else
             "No owner passphrase is set for this installation. At a console, run: "
             + html.escape(set_command(brain)))
    return (LOGIN_HTML.replace("__STATE__", state)
            .replace("__DISABLED__", "" if configured else "disabled")
            .replace("__NONCE__", nonce)).encode("utf-8")


def login_page_csp(nonce: str) -> str:
    return (f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
            "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")


# -- the console --------------------------------------------------------------------------------

def _ask_new() -> str:
    import getpass
    first = getpass.getpass("New owner passphrase: ")
    if len(first) < MIN_PASSPHRASE:
        raise SystemExit(f"a passphrase is at least {MIN_PASSPHRASE} characters")
    if getpass.getpass("Again: ") != first:
        raise SystemExit("the two did not match; nothing was changed")
    return first


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mentis.owner_auth",
                                 description="The Mentis owner's passphrase and sessions.")
    ap.add_argument("action", choices=("set", "status", "token", "revoke"))
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--brain", help="the Brain folder the server serves")
    where.add_argument("--file", help="the credential file itself (overrides --brain)")
    ap.add_argument("--passphrase-from-env", metavar="NAME",
                    help="FIXTURES AND REHEARSAL RIGS ONLY: read the passphrase from this "
                         "environment variable instead of asking")
    ap.add_argument("--label", default="console", help="token: what the token is for")
    args = ap.parse_args(argv)
    if args.file:
        cred = Credential(pathlib.Path(args.file).resolve())
    elif args.brain or os.environ.get(CREDENTIAL_ENV):
        cred = Credential(credential_path(args.brain or "."))
    else:
        ap.error("name the Brain (--brain) or the credential file (--file)")

    def passphrase(new: bool) -> str:
        if args.passphrase_from_env:
            value = os.environ.get(args.passphrase_from_env)
            if not value:
                raise SystemExit(f"{args.passphrase_from_env} is not set")
            return value
        if new:
            return _ask_new()
        import getpass
        return getpass.getpass("Owner passphrase: ")

    if args.action == "status":
        d = cred.data()
        live = [s for s in (d or {}).get("sessions") or [] if s.get("expires", 0) > _now()]
        print(json.dumps({"file": str(cred.path), "configured": d is not None,
                          "set_at": (d or {}).get("set_at"), "live_sessions": len(live)}))
        return 0
    if args.action == "set":
        cred.set_passphrase(passphrase(True))
        print(f"owner passphrase set in {cred.path}; every earlier session has ended")
        return 0
    if args.action == "revoke":
        print(f"{cred.revoke_all()} session(s) ended")
        return 0
    try:
        token, expires = cred.login(passphrase(False), kind="bearer", label=args.label)
    except (PermissionError, NotConfigured, Throttled) as e:
        raise SystemExit(str(e)) from None
    print(token)
    print(f"expires {_iso(expires)}; send it as `Authorization: Bearer <token>` "
          f"(owner tools read {TOKEN_ENV})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
