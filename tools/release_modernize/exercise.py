"""Write the records only the candidate writes, or read them back under any release.

    python -I exercise.py write BASE BRAIN OUT.json      # candidate: session w/ host, contribute (op_key x2),
                                                          #   leases, record_request + outcome claim, session end
    python -I exercise.py read  BASE BRAIN IN.json OUT.json  # any release: reads that touch those records

`read` is what proves a rollback tolerates a Brain the candidate wrote to: every call must answer
(no 5xx), and the Brain's counts must not change from reading. Nothing here dispatches anybody.
"""
import json
import sys
import time
import urllib.error
import urllib.request

CLIENT = {"X-Mentis-Client": "1", "Content-Type": "application/json"}


def call(base, path, body=None, headers=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET",
                                 headers={**CLIENT, **(headers or {})})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    ms = round((time.perf_counter() - t) * 1000)
    try:
        value = json.loads(raw)
    except ValueError:
        value = raw[:300].decode("utf-8", "replace")
    return status, value, ms


def op(base, grant, name, args, brain):
    return call(base, "/api/worker", {"op": name, "args": args, "corpus": brain}, {"X-Mentis-Worker": grant})


def short(v):
    s = json.dumps(v, default=str)
    return s if len(s) < 400 else s[:400] + "..."


def write(base, brain, out):
    log, ids = [], {}

    def rec(what, status, value, ms):
        log.append({"what": what, "status": status, "ms": ms, "value": short(value)})
        print(f"{status} {ms:>5}ms {what}", flush=True)
        return value

    s, v, ms = call(base, "/api/worker/session", {"runtime": "claude", "host": "R2-REHEARSAL", "corpus": brain})
    rec("session start (host R2-REHEARSAL)", s, v, ms)
    grant = v["grant"]; ids["participant"] = v.get("participant"); ids["execution"] = v.get("execution")
    for i in (1, 2):  # the same op_key twice: one act
        s, v, ms = op(base, grant, "contribute", {"kind": "finding", "text": "r2 rehearsal: rollback tolerance probe",
                                                  "evidence": ["r2-release rehearsal"], "op_key": "r2-rehearsal-contribute-1"}, brain)
        rec(f"contribute op_key send {i}", s, v, ms)
        ids.setdefault("contribute", []).append(v)
    s, v, ms = op(base, grant, "claim_resource", {"kind": "port", "name": "8869", "purpose": "r2 rehearsal probe", "ttl_s": 600}, brain)
    rec("claim_resource port 8869", s, v, ms); ids["lease1"] = v
    s, v, ms = op(base, grant, "claim_resource", {"kind": "path", "name": "C:\\Work\\Mentis-Test-Server\\r2-release\\probe", "ttl_s": 600}, brain)
    rec("claim_resource path (left for session end)", s, v, ms)
    s, v, ms = op(base, grant, "resources", {}, brain); rec("resources", s, v, ms)
    s, v, ms = op(base, grant, "release_resource", {"kind": "port", "name": "8869"}, brain); rec("release_resource port", s, v, ms)
    s, v, ms = op(base, grant, "open_conversation", {"name": "r2 rehearsal probe"}, brain)
    rec("open_conversation", s, v, ms)
    conv = (v or {}).get("conversation") or (v or {}).get("id") if isinstance(v, dict) else None
    ids["conversation"] = conv
    if conv:
        s, v, ms = op(base, grant, "record_request", {"conversation": conv, "text": "r2 rehearsal probe request"}, brain)
        rec("record_request", s, v, ms); ids["request"] = v
        exp = (v or {}).get("expectation") if isinstance(v, dict) else None
        ids["expectation"] = exp
        if exp:
            s, v, ms = op(base, grant, "record_outcome", {"expectation": exp, "outcome": "probe done",
                                                          "result": "done", "evidence": ["r2 rehearsal"]}, brain)
            rec("record_outcome result=done (outcome claim)", s, v, ms)
    s, v, ms = op(base, grant, "orient", {}, brain); rec("orient", s, v, ms)
    s, v, ms = call(base, "/api/worker/session/end", {"grant": grant, "corpus": brain}); rec("session end (leases end)", s, v, ms)
    json.dump({"ids": ids, "log": log}, open(out, "w"), indent=1, default=str)
    bad = [x for x in log if x["status"] >= 500]
    if bad:
        raise SystemExit(f"{len(bad)} server errors while writing")


def read(base, brain, inp, out):
    ids = json.load(open(inp))["ids"]
    log = []
    gets = ["/api/server", "/api/working", "/api/work", "/api/operational", "/api/execution",
            "/fluid/api/home/work", "/fluid/api/home/needs-you", "/fluid/api/needs-you",
            "/fluid/api/home/activity?limit=64", "/api/conversations", "/api/participants",
            "/fluid/api/participants", "/fluid/api/conversations", "/fluid/api/decisions"]
    if ids.get("conversation"):
        gets += [f"/fluid/api/collections/conversation?id={ids['conversation']}&limit=20",
                 f"/api/conversations/{ids['conversation']}"]
    for c in ids.get("contribute") or []:
        if isinstance(c, dict):
            for k in ("conversation",):
                if c.get(k):
                    gets.append(f"/fluid/api/collections/conversation?id={c[k]}&limit=20")
            break
    for g in gets:
        s, v, ms = call(base, g)
        log.append({"what": "GET " + g, "status": s, "ms": ms, "value": short(v)})
        print(f"{s} {ms:>5}ms GET {g}", flush=True)
    s, v, ms = call(base, "/api/worker/session", {"runtime": "claude", "corpus": brain})
    log.append({"what": "session start", "status": s, "ms": ms, "value": short(v)})
    print(f"{s} {ms:>5}ms session start", flush=True)
    if s == 200:
        grant = v["grant"]
        reads = [("orient", {}), ("work_overview", {}), ("find", {"q": "r2 rehearsal"}),
                 ("kinds", {}), ("capabilities", {})]
        if ids.get("expectation"):
            reads += [("history", {"expectation": ids["expectation"]}), ("resolve", {"ref": ids["expectation"]})]
        if ids.get("conversation"):
            reads += [("history", {"conversation": ids["conversation"]})]
        for name, args in reads:
            s, v, ms = op(base, grant, name, args, brain)
            log.append({"what": f"op {name} {args}", "status": s, "ms": ms, "value": short(v)})
            print(f"{s} {ms:>5}ms op {name}", flush=True)
        call(base, "/api/worker/session/end", {"grant": grant, "corpus": brain})
    json.dump({"log": log}, open(out, "w"), indent=1, default=str)
    bad = [x for x in log if x["status"] >= 500]
    print(json.dumps({"calls": len(log), "server_errors": len(bad), "non_200": [(x["what"], x["status"]) for x in log if x["status"] != 200]}))
    if bad:
        raise SystemExit(f"{len(bad)} server errors while reading")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "write":
        write(a[1], a[2], a[3])
    elif a[0] == "read":
        read(a[1], a[2], a[3], a[4])
    else:
        raise SystemExit(__doc__)
