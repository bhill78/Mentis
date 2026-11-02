"""MEASUREMENT ONLY. What the workload's processes share: the conversations, the
background mix, the foreground probes, one HTTP client, one way to summarise.

Changing anything in here after the baseline means re-running the baseline: every
candidate runs through this unchanged.
"""
import http.client, json, math, time, urllib.parse

SCHEMA = 2
OWNER = "ent-5936369158a8"          # the owner's Participant in this copy of the record
CLIENT = {"X-Mentis-Client": "1"}   # owner routes require it (web/__init__.py CLIENT_HEADER)
WORKER = "X-Mentis-Worker"          # worker.CAPABILITY_HEADER

MID = "ent-84dadf9f66dd"            # Setup Installation / Updates
BIG = "ent-cd0ddc9713a5"            # Fluid Workspace
#: the background's conversations, as lane C rotated them
CONVS = [MID, BIG, "ent-578e55420d23", "ent-128690b59552",
         "ent-22f6a92fccb3", "ent-98c0a097dbd9", "ent-0a1a163beb3a", "ent-5f457799f3cf"]
#: first-read targets: never touched before the cold phase of a boot, and never in CONVS.
#: Chosen once by tools/pick_cold.py: 70-276 posts in this copy of the record.
COLD_CONVS = ["ent-099caccce2c4", "ent-dca5ea664adf", "ent-4d627d2376e1",
              "ent-14af5a3cf286", "ent-cc71013e9872", "ent-6e37125ee551"]
WORDS = ["load", "magnet", "topic", "review", "cursor", "windows", "brain", "delivery"]
TOPIC_WORDS = ["load", "mag", "rev", "sta"]
WORK_TEXT = ["concurrent read contention in the server", "fluid loading of a post window",
             "shared data operations and statement counts", "magnet sources over conversations"]

#: ONE BACKGROUND WORKER'S ROUND. What a Magnet's `live.load` asks of the store on a notice
#: (surface-tension 14984a5: magnet/runtime.ts storeReads, magnet/live.ts): posts of the
#: newest page, the object index, its `about`. Plus `scan`, the palette's Brain-wide
#: references, which Magnets do not issue and Fluid does. The routes are real; the
#: proportions and the cadence are a stand-in, since no real Magnet workload exists.
#: v2 (BRIEF.md): `activity` and `needs_you` take two of `window`'s four slots, so that moving
#: window reads off Python no longer passes for isolation.
MIX = ("window", "objects", "activity", "window", "about", "needs_you", "objects", "scan")
#: ONE AGENT'S ROUND through /api/worker: gated reads, ungated ones. v2 adds kinds, resolve of
#: a Conversation, brief, work_overview, governed and history to v1's, in v1's order.
AGENT_MIX = ("orient", "resolve", "recall", "kinds", "resolve", "find", "resolve_conv", "brief",
             "resolve", "work_overview", "governed", "history")
#: THE NEIGHBOURS' ROUNDS. None touches a route a candidate serves outside Python.
SQL_MIX = ("scan", "activity", "needs_you")
#: `n-cpu` walks every conversation holding posts, most posts first, a page of WALK_PAGE roots
#: at a time, starting each round CPU_ROUND_SHIFT conversations further on. About 3,400 posts
#: are not yet extracted after the warm-up, and a run gets through only a few hundred, so the
#: walk keeps reaching posts the JS engine has not read (tools/check_cpu.py counts them).
WALK_PAGE = 10
CPU_ROUND_SHIFT = 13
#: Warm-up: this many of each rotation conversation's newest object pages. The windows have
#: already extracted page 1, which is what a level's few object reads ask for.
WARM_PAGES = 1
CPU_CONVS = [
    "ent-cd0ddc9713a5", "ent-84dadf9f66dd", "ent-128690b59552", "ent-0a1a163beb3a", "ent-099caccce2c4",
    "ent-98c0a097dbd9", "ent-22f6a92fccb3", "ent-578e55420d23", "ent-dca5ea664adf", "ent-4d627d2376e1",
    "ent-14af5a3cf286", "ent-cc71013e9872", "ent-6e37125ee551", "ent-5bfed2a54cda", "ent-6f1ae762493d",
    "ent-2865e11386f6", "ent-bf3ee55e5574", "ent-d03b64846b8e", "ent-dff13b28c18d", "ent-7a71cef2d536",
    "ent-5f457799f3cf", "ent-24563106406c", "ent-a729d7fe84ff", "ent-87607b5c5b9e", "ent-493eceb21487",
    "ent-a2bf2360e5d9", "ent-2b0c57fb2f95", "ent-f28cd94996ae", "ent-6f03f3bdb30b", "ent-c348e9f4a5ff",
    "ent-933432292fc5", "ent-fa4b0e6e8fe0", "ent-237f0cccdf84", "ent-25987c4f25c4", "ent-a9de07336a6f",
    "ent-47ced870a943", "ent-7c6896c1d109", "ent-bf9a9defe054", "ent-5ce090ab3e0f", "ent-1497b95f7670",
    "ent-3f83c0d6eecb", "ent-a221db3552de", "ent-54a472d1de56", "ent-6f80c56a6307", "ent-28f1c77b4b40",
    "ent-f4714a85bbc5", "ent-ad2a23705996", "ent-b4e74adcca03", "ent-b78bfba90762", "ent-532ce2ff268e",
    "ent-568e2c71a193", "ent-eced620d023b", "ent-c57669db6282", "ent-8bef450fefee", "ent-6c704316f033",
    "ent-cf156695afde", "ent-bd9ed8cab9ed", "ent-4bb9e3feb0e6"]
#: Where the statement pass's commits go: a conversation the passes' windows do not read.
COMMIT_CONV = "ent-22f6a92fccb3"

ACTIVITY = "/fluid/api/conversations?activity=1&limit=40"   # store.ts: the Conversation list
NEEDS_YOU = "/fluid/api/home/needs-you"
NEEDS_ITEMS = "/fluid/api/needs-you/items"
#: `/api/turns?ids=` as Addressing.tsx batches it: the newest eight posts of MID in this copy.
TURN_IDS = ["ent-3a1058b222a1", "ent-d474a459ac0a", "ent-705f9e106396", "ent-ba5c0008c3d8",
            "ent-5df25973658d", "ent-0ceca1e70bd0", "ent-ba2d0ed82186", "ent-c18365b907e5"]


class Conn:
    """One keep-alive connection, as a browser or a worker holds."""

    def __init__(self, port, timeout=120):
        self.port, self.timeout = port, timeout
        self.c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)

    def ask(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        hdrs = dict(headers or {})
        if data is not None:
            hdrs["Content-Type"] = "application/json"
        for attempt in (0, 1):
            try:
                self.c.request(method, path, body=data, headers=hdrs)
                r = self.c.getresponse()
                return r.status, r.read()
            except (http.client.HTTPException, OSError):
                self.c.close()
                self.c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
                if attempt or method != "GET":
                    raise

    def close(self):
        self.c.close()


def once(port, method, path, body=None, headers=None, timeout=120):
    """A person's read: a fresh connection, one request. (ms, status, bytes)"""
    c = Conn(port, timeout)
    t = time.perf_counter()
    try:
        st, b = c.ask(method, path, body, headers)
        return (time.perf_counter() - t) * 1000, st, b
    finally:
        c.close()


def worker_body(op, conv, rnd_word, work, ref):
    if op == "orient":
        return {"op": "orient", "args": {}}
    if op == "resolve":
        return {"op": "resolve", "args": {"ref": ref}}
    if op == "recall":
        return {"op": "recall", "args": {"work": work, "conversation": conv}}
    if op == "find":
        return {"op": "find", "args": {"q": rnd_word, "limit": 12}}
    if op == "kinds":
        return {"op": "kinds", "args": {}}
    if op == "resolve_conv":
        return {"op": "resolve", "args": {"ref": conv}}
    if op == "brief":
        return {"op": "brief", "args": {"conversation": conv}}
    if op == "work_overview":
        return {"op": "work_overview", "args": {}}
    if op == "governed":
        return {"op": "governed", "args": {"limit": 30}}
    if op == "history":
        return {"op": "history", "args": {"conversation": conv, "limit": 50}}
    raise ValueError(op)


def collection_path(conv):
    return f"/fluid/api/collections/conversation?id={conv}&limit=50"


def posts_path(ids):
    return "/fluid/api/posts?ids=" + ",".join(ids) + "&thread=1"


def objects_path(conv, before, limit=30):
    q = {"conversation": conv, "limit": str(limit)}
    if before:
        q["before"] = before
    return "/fluid/api/objects?" + urllib.parse.urlencode(q)


def turns_path():
    return "/api/turns?ids=" + ",".join(TURN_IDS)


def bad_statuses(res):
    """Everything in a timed result that was not answered well, in words. Empty: nothing. A 503 counts:
    no bench run has ever had one, and a forwarded route that cannot reach Python answers it."""
    out = []

    def probe(where, p):
        if p.get("bad_status") or p.get("errors"):
            out.append(f"{where}: {p.get('bad_status')} bad status, {p.get('errors')} errors")

    for level, d in (res.get("levels") or {}).items():
        a = d.get("aggregate") or {}
        for name, p in (a.get("probes") or {}).items():
            probe(f"{level} {name}", p)
        b = a.get("background") or {}
        if b.get("bad_status") or b.get("errors") or b.get("busy_503"):
            out.append(f"{level} background: {b.get('bad_status')} bad status, {b.get('errors')} errors, "
                       f"{b.get('busy_503')} 503s")
        if (a.get("writes") or {}).get("errors"):
            out.append(f"{level} writes: {a['writes']['errors']} errors")
    for name, p in ((res.get("cold") or {}).get("by_probe") or {}).items():
        probe(f"cold {name}", p)
    for name, v in ((res.get("statements") or {}).get("reads") or {}).items():
        for phase in ("cold", "warm", "post_commit"):
            st = (v.get(phase) or {}).get("status", 200) if isinstance(v.get(phase), dict) else 200
            if st != 200:
                out.append(f"statements {name} {phase}: status {st}")
    return out


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[max(0, math.ceil(p / 100 * len(xs)) - 1)], 1) if xs else None


def summ(xs):
    return {"count": len(xs), "p50": pct(xs, 50), "p95": pct(xs, 95),
            "max": round(max(xs), 1) if xs else None}
