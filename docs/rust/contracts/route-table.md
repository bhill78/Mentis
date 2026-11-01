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
- **A 403 from Python on `POST /api/worker` leaves a line in `<run dir>/worker-refusals.jsonl`** (`launch::WORKER_REFUSALS_FILE`): `{"received_at", "answered_at", "body"}`, the first two in Unix seconds as a float, from when the request arrived and when the answer's body was read. `body` is its first 4,800 bytes, decoded as UTF-8 with replacement, which always covers the 1,200 characters `_over` reads. **The line is appended and flushed before the answer's first byte is relayed,** so a message an agent saw has its line even if the front dies. A restarted front appends. The answer itself is relayed unchanged. Nothing else goes in this file, and no other answer costs anything. Row J reads it for its refusal evidence, and row A's Grant case checks it. If it can't be written the answer still goes, with the reason on stderr, and the refusal then has no evidence and fails row J.

## Warning for P1.2: framing is Python's answer, not the library's

`R1-acceptance.md`'s framing cases compare status, named headers and body against Python. Python's refusals are its own JSON and close the connection (`web/__init__.py:6276-6295`, `parse_request` from `:6323`). HTTP libraries reject some of the same requests before your code runs, with their own response: `Transfer-Encoding : chunked` is one such case. So check this before choosing a library, and record the choice and why.

Three more facts the contract cases depend on:

| Case | Python's answer | Where |
|---|---|---|
| A refused Host | **421**, not 403 | `web/__init__.py:6411` |
| HEAD, PUT, DELETE, any method with no `do_` method | 501 from `http.server`'s default error page | `:6432-6491` defines only OPTIONS, GET, POST |
| A grant on another route | 403, **in that door's own wording:** `_api` (`:6876`), Fluid GET (`fluid/__init__.py:351`), Fluid POST (`fluid/commands.py:1057`), and the artifact, picture and export doors (`:6580`, `:6620`, `:6673`, `:6700`, `:6729`) | An owned route takes the wording of the door it replaced: for R1, `_api` for pulse, Fluid GET for topics and names |

`_missing_client` lets a request presenting a grant through (`:6422`), so a grant reaches the grant refusal rather than a missing-header refusal. The order is Host, client header, grant.
