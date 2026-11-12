"""Submit one detached verdict. No retry, polling, or owner credential."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--operation", required=True)
    secret = parser.add_mutually_exclusive_group()
    secret.add_argument("--token-file", help="file containing only the report token")
    secret.add_argument("--token-env", default="MENTIS_DETACHED_TOKEN")
    parser.add_argument("--result", required=True,
                        choices=["succeeded", "failed", "rolled_back", "unknown"])
    parser.add_argument("--summary", required=True)
    parser.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args(argv)
    token = (Path(args.token_file).read_text(encoding="utf-8-sig").strip()
             if args.token_file else os.environ.get(args.token_env, "").strip())
    if not token:
        parser.error("supply the one-time token in --token-file or --token-env")
    # The token is in the JSON body, never a URL or process argument.
    body = json.dumps({"token": token, "result": args.result,
                       "summary": args.summary, "evidence": args.evidence}).encode()
    request = urllib.request.Request(
        args.server.rstrip("/") + "/api/detached/"
        + urllib.parse.quote(args.operation, safe="") + "/report",
        data=body, headers={"Content-Type": "application/json", "X-Mentis-Client": "1"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(response.read().decode())
    except urllib.error.HTTPError as error:
        print(f"report refused ({error.code}): {error.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"report not confirmed: {error.reason}; no retry was made", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
