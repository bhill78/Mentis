# Contract: the route table

Code: `crates/mentis-server/src/route_table.rs`, with its tests. For P1.2, P1.3, and any later release that moves a route.

## Format

A UTF-8 JSON file. The launcher names it with `--route-table`. With none, the front uses the table built into the binary, `crates/mentis-server/route-table.default.json`, and never re-reads.

```json
{
  "format": 1,
  "routes": [
    {"id": "pulse",  "method": "GET", "path": "/api/pulse",    "owner": "rust"},
    {"id": "api",    "method": "GET", "path": "/api/*",        "owner": "python"},
    {"id": "fluid",  "method": "GET", "path": "/fluid/api/*",  "owner": "python"},
    {"id": "static", "method": "GET", "path": "*",             "owner": "rust"}
  ]
}
```

| Field | Rule |
|---|---|
| `id` | Unique. For `rust` it is the handler's name in `mentis_server::HANDLERS`. Logs name the rule by it |
| `method` | `GET`, `POST`, `OPTIONS`, or `*` |
| `path` | Exact `/api/pulse`; one-segment `/fluid/api/posts/{}/anchors`; prefix `/fluid/api/*`; or `*` |
| `owner` | `rust` or `python` |
| `python_handler` | Optional, default true. Set to `false` when Python's handler is retired, and `python` is then refused |

Unknown fields are refused, so a typo can't silently change nothing.

## Deciding

1. **Unknown means forwarded.** A request no rule matches goes to Python.
2. **The raw path, as sent, before `?`.** Nothing is decoded, trimmed or collapsed. An odd spelling of an owned route (`/api/pulse/`, `/api/%70ulse`, `/api/pulse;x`, `//api/pulse`) matches no `rust` rule and gets Python's answer. Python's own parsing decides what those mean, so the front never reinterprets them.
3. **Most specific wins, whatever order the file is in:** exact, then the most literal segments, then the longest prefix, then `*`. At one path, a rule naming the method beats `*`. Two rules with the same method and path are refused.
4. **`rust` may still forward.** A handler that meets a case it doesn't own returns `OpError::NotOwned` or its equivalent, and the request goes to Python unchanged. That is how `resolve` moves kind by kind.
5. **Python gone:** a request for a `rust` rule is answered. A forwarded one gets 503 with the reason.

**A Magnet's activation (`docs/magnets/M1-contract.md`, "Manual activation"), in the built-in table:** `{"id": "magnet-activate", "method": "POST", "path": "/fluid/api/magnets/{}/activate", "owner": "rust"}`, listed in `handlers::WATCHES_ITS_CLIENT`. It is the front's first `rust` POST beside `/api/worker`, so it has a door of its own. By rule 2 the trailing-slash spelling matches no `rust` rule and goes to Python, which answers it as it answers the path itself on Python alone, and records nothing. Rolling the rule back gives the same answer on the exact path.

`/private/*` is decided before the table and is never in it (`contracts/launcher.md`). `static` must be written with the `/api/*` and `/fluid/api/*` rules above, because Python serves every other GET as a file or `index.html` (`web/__init__.py:6471`), and an unknown `/api/x` has to reach Python's own 404.

## Re-reading

- **Every second** (`REREAD_EVERY`), on a blocking thread, the front calls `LiveRouteTable::reread`, which compares the file's bytes to those last seen.
- **Changed and good:** in force from the next request. A request already started keeps the table it started with. Logged with the file's digest.
- **Changed and bad** (unreadable, malformed, wrong format, a rule refused): the table in force stays in force. Logged once per version of the file, naming the rule. A half-written file can't do harm, but write it to a temporary name and rename it anyway.
- **At start,** a bad file is a refusal to start: exit 3, in words.
- **Checked against this binary:** a `rust` rule naming a handler this build lacks is refused. So is the whole file, not only that rule, because a file half taken is a table nobody wrote.

**A route's rollback** is one edit to this file, with no restart and no runs lost, and it works until that route's Python handler is retired. Row J5 in `R1-acceptance.md` tests it, allowing 2 s for the change to take effect.

## What the front does for a forwarded request (P1.2)

- **The Host header, path and query go on byte for byte.** Python's own Host check and grant checks still run behind the front.
- **Inbound `X-Mentis-Peer` and `X-Mentis-Boot-Secret` are stripped,** then the real peer and the secret are added (`contracts/launcher.md`).
- **Bodies stream in both directions.** The export ZIP and a 200 MB upload must not be buffered (`R1-acceptance.md`, Streaming).
- **A client that leaves ends Python's request at once.** For a request with no body, the client's side is watched while Python works; its end (or a reset) drops the connection to Python then, not when the answer fails to write. Bytes the client sends ahead (a next request) count as still there. A half-close reads as leaving, as it does for the routes that watch their client.

## Forwarded reads (2026-11-25)

Code: `front/flights.rs`. Tests: `tests/forwarded_reads.rs`.

**Why.** A `rust` route forwards a case it can't answer, most often because the live snapshot is stale (`contracts/live-snapshot.md`). That happens when Python is slow, so every client polling a view used to send Python its heaviest reads exactly when it had least to spare: on 2026-11-25, with Python overloaded, 642 of 669 `turns` reads forwarded, p95 52 s, and `conversation-fields` forwards had p95 210 s.

Only these forwards change: a `GET` that a `rust` route's handler returned as not owned. A request the table gives to Python, and every write, is forwarded as above, unchanged.

- **Identical reads in flight share one request.** A read joins one already on its way to Python when its request line (target and HTTP version), peer and headers are the same, credentials included, ignoring only headers Python doesn't answer by (`Connection`, `Keep-Alive`, `Priority`, `Referer`, `Cache-Control`, `Pragma`, `DNT`, `Sec-Fetch-*`, `Sec-CH-*`). Each gets Python's whole answer as Python sent it. A read with a body, `Content-Length` or `Transfer-Encoding` at all, `Expect`, or a worker grant (`X-Mentis-Worker`) is never shared.
- **Never an answer older than the read's own writes.** A read joins only if no request other than a `GET` or `HEAD` was in hand at any moment since the shared one was sent. So a read made after any write has been answered (the client's own, or anyone's through this front) gets an answer asked for after that write, as it would without sharing. Writes, authority checks and grants are never shared or held.
- **Not a cache.** Nothing is kept once it is answered: the next read asks Python again.
- **At most `MOST_FORWARDED_READS` (4) at once.** A read that can't be shared waits up to `WAIT_FOR_A_PLACE` (3 s) for a place. With none, nothing is sent, and it is answered `503` with `Retry-After: 2` and `{"error": "Mentis is busy: ...", "kind": "Busy"}`, the `kind` Fluid's Magnet answers already use for "nothing was done, ask again". Its time is filed as `<route>:busy`.
- **A client leaving.** A read's client that leaves lets its share go. The request to Python ends only when the last read waiting for it has gone, and at once then.
- **What can't be shared is forwarded on its own:** an answer not framed by `Content-Length`, a 1xx, or one over 32 MiB.
- **Freshness is unchanged.** These reads forward for the same reasons as before, and the pulse still says stale or unavailable as it did. Sharing changes only how many requests Python gets for them.

## Warning for P1.2: framing is Python's answer, not the library's

`R1-acceptance.md`'s framing cases compare status, named headers and body against Python. Python's refusals are its own JSON and close the connection (`web/__init__.py:6276-6295`, `parse_request` from `:6323`). HTTP libraries reject some of the same requests before your code runs, with their own response: `Transfer-Encoding : chunked` is one such case. So check this before choosing a library, and record the choice and why.

Three more facts the contract cases depend on:

| Case | Python's answer | Where |
|---|---|---|
| A refused Host | **421**, not 403 | `web/__init__.py:6411` |
| HEAD, PUT, DELETE, any method with no `do_` method | 501 from `http.server`'s default error page | `:6432-6491` defines only OPTIONS, GET, POST |
| A grant on another route | 403, **in that door's own wording:** `_api` (`:6876`), Fluid GET (`fluid/__init__.py:362`), Fluid POST (`fluid/commands.py:1195`), and the artifact, picture and export doors (`:6580`, `:6620`, `:6673`, `:6700`, `:6729`) | An owned route takes the wording of the door it replaced: for R1, `_api` for pulse, Fluid GET for topics and names |

`_missing_client` lets a request presenting a grant through (`:6422`), so a grant reaches the grant refusal rather than a missing-header refusal. The order is Host, client header, grant.
