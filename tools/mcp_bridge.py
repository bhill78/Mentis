"""Start Mentis's MCP bridge from the release the running server is serving.

    python -I mcp_bridge.py --session claude
    python -I mcp_bridge.py --session codex --server http://127.0.0.1:8760

WHY THIS EXISTS. Every agent CLI used to be registered with a command naming one
release directory (`releases/<sha12>`). A deploy changed the server and left every
registration pointing at old code: on 2026-10-27 Claude Code and Antigravity were
starting the bridge from a 13 Oct release against a 27 Oct server. This file names no
release. On each start it asks the server which commit it is running
(`GET /api/server`) and imports `mentis.worker` from that commit's release, so the
bridge an agent talks through is always the server's own code, with nothing to update
on deploy.

It is installed once, outside every release, at `%LOCALAPPDATA%\\Mentis\\Mark-IV\\
mcp_bridge.py`, and registered in each CLI by that path. It decides nothing about
authority: it starts the existing `mentis.worker.serve` in hand-started-session mode
(`session=<runtime>`), which asks the server for its grant and is shown exactly what
the server's door admits.

stdout is the MCP channel, so everything this file says goes to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_SERVER = "http://127.0.0.1:8760"
DEFAULT_HOME = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                            "Mentis", "Mark-IV")


def fail(message: str) -> int:
    print(f"mentis mcp bridge: {message}", file=sys.stderr, flush=True)
    return 1


def running_release(server: str, home: str, timeout: float = 10.0) -> tuple[str, str]:
    """(release directory, corpus path) of the server answering at ``server``."""
    req = urllib.request.Request(server.rstrip("/") + "/api/server",
                                 headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        info = json.load(resp)
    corpus = info.get("corpus")
    if not corpus:
        raise LookupError(f"the server at {server} did not say which Brain it holds")
    # TWO KINDS OF RELEASE. An installed one (`mentis update`, `releases/<semver>+
    # <commit12>`) reports its own code root as `release.path`, and its `code.commit`
    # is usually None because it is no checkout. One published by `tools/release.py`
    # (`releases/<commit12>`, the day-to-day server on 2026-10-27) carries no
    # RELEASE.json, so `release` is None and the commit names the folder.
    installed = info.get("release") or {}
    if installed.get("path"):
        release = str(installed["path"])
        named = f"{installed.get('version')} ({str(installed.get('commit') or '')[:12]})"
    else:
        commit = str((info.get("code") or {}).get("commit") or "")
        if len(commit) < 12:
            raise LookupError(f"the server at {server} did not say which release or commit it runs")
        release = os.path.join(home, "releases", commit[:12])
        named = commit[:12]
    if not os.path.isfile(os.path.join(release, "mentis", "worker.py")):
        raise LookupError(f"the server runs {named} but {release} holds no release")
    return release, str(corpus)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--session", required=True,
                        help="the runtime this session runs on (claude, codex, antigravity, local, kimi, ...)")
    parser.add_argument("--server", default=os.environ.get("MENTIS_BRIDGE_SERVER", DEFAULT_SERVER))
    parser.add_argument("--home", default=DEFAULT_HOME, help="the install holding releases/")
    args = parser.parse_args(argv)
    try:
        release, corpus = running_release(args.server, args.home)
    except (urllib.error.URLError, OSError) as exc:
        return fail(f"Mentis is not answering at {args.server} ({exc}); start it, then reconnect")
    except (LookupError, ValueError) as exc:
        return fail(str(exc))
    print(f"mentis mcp bridge: {os.path.basename(release)} for session {args.session!r}",
          file=sys.stderr, flush=True)
    sys.path.insert(0, release)
    from mentis.worker import serve  # the release's own code, the server's commit

    serve(corpus, via=args.server, capability=None, permits=None, scratch=None,
          project=None, session=args.session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
