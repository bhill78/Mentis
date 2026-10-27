"""Is an installed Mentis healthy: the right release, serving the right Brain,
and the Brain whole.

    check(root_or_port, expect_release, expect_brain) -> {"ok", "checks": [...]}

ONE FUNCTION, USED BY INSTALL AND BY UPDATE. Each check is a row
{"check", "ok", "detail"} and `ok` is true only when every row is. The checks:

  server         `/api/server` answers 200 and its `release` block names the
                 expected version, commit and release directory, and its
                 `corpus` is the expected Brain (same path, case and links
                 resolved). A server run from a checkout has `release: null`
                 and fails this: it is not the release.
  integrity      `/api/integrity` answers 200 and its chain is `intact`.
  api <path>     every CORE path answers 200.
  brain-verify   `mentis brain verify` of the Brain is ok, run by the
                 EXPECTED release's own interpreter (its code is the one that
                 knows the Brain's newest migrations). When the only problem
                 is derived indexes the ledger declares and the Brain lacks,
                 and `repair` is true, `mentis brain rebuild-derived` is run
                 and verify is asked again.

REBUILD-DERIVED NEEDS THE BRAIN TO ITSELF (exclusive lock), so it cannot run
beside a server. A caller that may need it checks the Brain BEFORE starting
the server -- `check(..., server=False)` -- and everything with the server up
afterwards. With a server running, missing indexes are reported, not
repaired, and the row says to stop the server and rebuild.

`root_or_port`: an install root (path or `home.Layout`; its install.json
gives the port), or a port number. `expect_release`: a release name
(`<semver>+<commit12>`, under the root's `releases/`), a release directory
path, or {version, commit[, path]}. `expect_brain`: the Brain's path.

The signature is frozen: `check(root_or_port, expect_release, expect_brain,
*, server=True, brain=True, repair=True, timeout=10.0)`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

from mentis import home, install_state

#: answered 200 by any healthy server, with no parameters
CORE = ("/api/server", "/api/brain", "/api/conversations", "/api/participants",
        "/api/working", "/api/integrity")
#: `mentis.web.CLIENT_HEADER`: what the web surface sends on every API call
CLIENT_HEADER = "X-Mentis-Client"
#: a release directory name, `<semver>+<commit12>`
_NAME = re.compile(r"[0-9A-Za-z.\-]+\+[0-9a-f]{12}")


def _same(a, b) -> bool:
    return (os.path.normcase(os.path.realpath(str(a)))
            == os.path.normcase(os.path.realpath(str(b))))


def _resolve(root_or_port, expect_release) -> tuple[int | None, dict, list]:
    """(port, expected {version, commit, path}, rows already failed)."""
    rows = []
    port, lay = None, None
    if isinstance(root_or_port, int) and not isinstance(root_or_port, bool):
        port = root_or_port
    else:
        lay = (root_or_port if isinstance(root_or_port, home.Layout)
               else home.Layout(root_or_port))
        try:
            port = install_state.load(lay, required=True)["port"]
        except install_state.InstallStateError as exc:
            rows.append({"check": "install", "ok": False, "detail": str(exc)})
    want: dict = {}
    if isinstance(expect_release, dict):
        want = {k: expect_release.get(k) for k in ("version", "commit", "path")}
    else:
        p = pathlib.Path(str(expect_release))
        if lay is not None and not p.is_absolute():
            p = lay.release(str(expect_release))
        if p.is_dir():
            try:
                r = home.release(p)
            except (OSError, ValueError) as exc:
                r = None
                rows.append({"check": "release", "ok": False,
                             "detail": f"{p}: {exc}"})
            if r is not None:
                want = r
            elif not rows:
                rows.append({"check": "release", "ok": False,
                             "detail": f"{p} has no RELEASE.json"})
        elif _NAME.fullmatch(str(expect_release)):
            # a name and a port, no root: the name says version and commit
            v, c = str(expect_release).rsplit("+", 1)
            want = {"version": v, "commit": c}
        else:
            rows.append({"check": "release", "ok": False,
                         "detail": f"no release directory {p}"})
    return port, want, rows


def _get(port: int, path: str, timeout: float) -> tuple[int | None, object]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 headers={CLIENT_HEADER: "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            status = r.status
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:300].decode("utf-8", "replace")
    except Exception as exc:                                  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    try:
        return status, json.loads(body.decode("utf-8"))
    except ValueError:
        return status, None


def _server_rows(port, want, brain, timeout) -> list:
    rows = []
    code, srv = _get(port, "/api/server", timeout)
    if code != 200 or not isinstance(srv, dict):
        return [{"check": "server", "ok": False,
                 "detail": f"/api/server on :{port} answered {code}: "
                           f"{str(srv)[:200]}"}]
    rel = srv.get("release") or {}
    wrong = []
    if not rel:
        wrong.append("it reports no release (run from a checkout, or an "
                     "older release)")
    else:
        if want.get("version") and rel.get("version") != want["version"]:
            wrong.append(f"version {rel.get('version')}, expected "
                         f"{want['version']}")
        c, wc = str(rel.get("commit") or ""), str(want.get("commit") or "")
        if wc and not (c.startswith(wc) or wc.startswith(c)) or (wc and not c):
            wrong.append(f"commit {c[:12]}, expected {wc[:12]}")
        if want.get("path") and not (rel.get("path")
                                     and _same(rel["path"], want["path"])):
            wrong.append(f"runs from {rel.get('path')}, expected "
                         f"{want['path']}")
    if not (srv.get("corpus") and _same(srv["corpus"], brain)):
        wrong.append(f"serves the Brain {srv.get('corpus')}, expected {brain}")
    rows.append({"check": "server", "ok": not wrong,
                 "detail": "; ".join(wrong) or
                 f"release {rel.get('version')} ({str(rel.get('commit'))[:12]}) "
                 f"serving {srv.get('corpus')} on :{port}"})
    code, integ = _get(port, "/api/integrity", timeout)
    intact = isinstance(integ, dict) and integ.get("intact") is True
    rows.append({"check": "integrity", "ok": code == 200 and intact,
                 "detail": ("the record's chain is intact" if code == 200
                            and intact else f"/api/integrity answered {code}, "
                            f"intact={(integ or {}).get('intact') if isinstance(integ, dict) else None}")})
    for path in CORE:
        code, body = _get(port, path, timeout)
        rows.append({"check": f"api {path}", "ok": code == 200,
                     "detail": f"{code}" if code == 200
                     else f"{code}: {str(body)[:200]}"})
    return rows


def _brain_cli(python, args, timeout=600) -> tuple[int, dict | None, str]:
    if python is None:
        # no release to ask: this process's own code, found from its root
        cmd, cwd = [sys.executable, "-m", "mentis.brain", *args], home.CODE_ROOT
    else:
        cmd, cwd = [str(python), "-I", "-m", "mentis.brain", *args], None
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    run = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=env,
                         timeout=timeout)
    try:
        out = json.loads(run.stdout)
    except ValueError:
        out = None
    return run.returncode, out, (run.stderr or run.stdout).strip()[-600:]


def _brain_rows(want, brain, repair, server_up) -> list:
    py = None
    if want.get("path"):
        py = install_state.venv_python(want["path"])
        if not py.is_file():
            py = None
    rows = []
    rc, out, said = _brain_cli(py, ["verify", brain])
    if out is None:
        return [{"check": "brain-verify", "ok": False,
                 "detail": f"verify exited {rc}: {said}"}]
    missing = out.get("missing_indexes") or []
    only_indexes = (not out.get("ok") and missing
                    and len(out.get("problems") or []) == 1)
    if only_indexes and repair and not server_up:
        rc2, built, said2 = _brain_cli(py, ["rebuild-derived", brain])
        rows.append({"check": "rebuild-derived", "ok": rc2 == 0,
                     "detail": (f"re-created {', '.join(built['rebuilt'])}"
                                if rc2 == 0 and built else
                                f"rebuild-derived exited {rc2}: {said2}")})
        rc, out, said = _brain_cli(py, ["verify", brain])
        if out is None:
            rows.append({"check": "brain-verify", "ok": False,
                         "detail": f"verify exited {rc}: {said}"})
            return rows
    elif only_indexes and repair:
        rows.append({"check": "rebuild-derived", "ok": False,
                     "detail": "derived indexes are missing ("
                     + ", ".join(missing) + ") and a server has the Brain "
                     "open; stop it and run `mentis brain rebuild-derived`"})
    rows.append({"check": "brain-verify", "ok": bool(out.get("ok")),
                 "detail": out.get("explain") if out.get("ok")
                 else "; ".join(out.get("problems") or [])
                 or out.get("explain")})
    return rows


def check(root_or_port, expect_release, expect_brain, *, server: bool = True,
          brain: bool = True, repair: bool = True,
          timeout: float = 10.0) -> dict:
    """Every health check (see the module docstring). Never raises for an
    unhealthy answer; every finding is a row."""
    expect_brain = os.path.abspath(str(expect_brain))
    port, want, rows = _resolve(root_or_port, expect_release)
    # anything answering on the port may hold the Brain open
    server_up = port is not None and _get(port, "/api/server",
                                          min(timeout, 3.0))[0] is not None
    if server and port is not None:
        rows += _server_rows(port, want, expect_brain, timeout)
    elif server:
        rows.append({"check": "server", "ok": False,
                     "detail": "no port to ask"})
    if brain:
        rows += _brain_rows(want, expect_brain, repair, server_up)
    return {"ok": bool(rows) and all(r["ok"] for r in rows), "port": port,
            "release": want, "brain": expect_brain, "checks": rows}


def render(result: dict) -> str:
    """The rows as plain lines, for a person."""
    return "\n".join(f"  [{'ok' if r['ok'] else 'FAIL'}] {r['check']}: "
                     f"{r['detail']}" for r in result["checks"])
