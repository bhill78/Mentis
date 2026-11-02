"""MEASUREMENT ONLY. Tabulate candidates side by side, from HOME/results/<label>/workload.json.
It tabulates; it does not judge.

    compare.py C0 S P            markdown tables on stdout, one per foreground read
    compare.py --noise C0        how far one candidate's rounds differ
    compare.py C0 S --csv out.csv
    compare.py --evidence pilots/C0-pre-gate     ONE result, read as evidence, compared with nothing

Numbers are as stored: measured p50/p95/max over each level's pooled runs. `by run` shows
each run's own value. It REFUSES, exit 3, with no override, when a workload_sha differs or is
not this tree's, when an isolation record is missing or unfinished, when a result is marked
invalid, when it is a pilot, or when the two ran on different Brains. A comparison of results with
a bad status prints its tables and exits FAILED, 4. Earlier results stay readable, one at a time,
with --evidence, which judges nothing and exits 0.
"""
import argparse, csv, json, pathlib, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import benchgate as G
import wl_common as W
PROBES = ["topic_lookup", "window_total", "window_collection", "window_posts", "pulse",
          "activity", "needs_you", "needs_you_items", "turns",
          "agent_resolve", "agent_orient", "agent_recall", "agent_find",
          "agent_kinds", "agent_history", "agent_brief", "agent_work_overview",
          "after_commit_total", "after_commit_collection", "after_commit_posts"]
LEVEL_ORDER = ["idle", "closed-4", "closed-16", "paced-4", "paced-16", "agents-1", "agents-4",
               "n-sql", "n-cpu", "n-agents-write", "write"]


def load(label):
    return json.load(open(G.RESULTS / label / "workload.json", encoding="utf-8"))


def levels_of(results):
    seen = {lv for r in results.values() for lv in r["levels"]}
    return [lv for lv in LEVEL_ORDER if lv in seen] + sorted(seen - set(LEVEL_ORDER))


def fmt(x):
    if x is None:
        return "-"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:g}"


def header(results):
    print("Candidates: " + "; ".join(
        f"**{k}** {r['code'].get('commit') or r['code']['dir']} (workload {r.get('workload_sha')}, {r.get('started')})"
        for k, r in results.items()))
    print()


def probe_tables(results, rows):
    for probe in PROBES:
        print(f"### {probe}: p50 / p95 / max ms (count; errors+bad status). Measured.\n")
        labels = list(results)
        print("| level | " + " | ".join(labels) + " |")
        print("|---|" + "---|" * len(labels))
        for lv in levels_of(results):
            cells = []
            for k in labels:
                p = results[k]["levels"].get(lv, {}).get("aggregate", {}).get("probes", {}).get(probe)
                if not p or not p.get("count"):
                    cells.append("-")
                    continue
                cells.append(f"{fmt(p['p50'])} / {fmt(p['p95'])} / {fmt(p['max'])} ({p['count']}; {p['errors'] + p['bad_status']})")
                rows.append([k, lv, probe, p["count"], p["p50"], p["p95"], p["max"], p["errors"], p["bad_status"]])
            print(f"| {lv} | " + " | ".join(cells) + " |")
        print()


def background_table(results):
    labels = list(results)
    print("### Background and server, per level. Measured.\n")
    print("qps mean, query p50/p95 ms, workers looping by run of n, errors+503s; server cores, RSS MB max; client cores.\n")
    print("| level | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(labels))
    for lv in levels_of(results):
        cells = []
        for k in labels:
            a = results[k]["levels"].get(lv, {}).get("aggregate")
            if not a:
                cells.append("-")
                continue
            s = a["server"]
            b = a.get("background")
            text = ""
            if b:
                text = (f"{fmt(b['throughput_qps_mean'])} q/s, {fmt(b['p50'])}/{fmt(b['p95'])} ms, "
                        f"looping {b['workers_looping_by_run']} of {b['n']}, {b['errors'] + b['bad_status']}e+{b['busy_503']}b; ")
            w = a.get("writes")
            if w:
                text += f"writes {w['per_s_by_run']}/s, {fmt(w['p50'])}/{fmt(w['p95'])} ms, {w['errors']}e; "
            apart = "".join(f"; {n} {p['cores_mean']} cores, {p['rss_mb_max']} MB" for n, p in s.get("by_process", {}).items())
            cells.append(text + f"{s['cores_mean']} cores, {s['rss_mb_max']} MB{apart}; client {a['client_cores_mean']}")
        print(f"| {lv} | " + " | ".join(cells) + " |")
    print()


def statement_table(results):
    labels = list(results)
    print("### Statements per foreground read (data statements on the request thread; bookkeeping apart). Measured by trace.\n")
    print("A candidate reading through its own native connection is not visible to the trace: see each result's `statements.note`.\n")
    print("| read | " + " | ".join(f"{k}: warm / after a commit / cold" for k in labels) + " |")
    print("|---|" + "---|" * len(labels))
    names = []
    for r in results.values():
        for n in (r.get("statements") or {}).get("reads", {}):
            if n not in names:
                names.append(n)
    for n in names:
        cells = []
        for k in labels:
            v = (results[k].get("statements") or {}).get("reads", {}).get(n)
            if not v:
                cells.append("-")
            elif "warm_data_statements" in v:
                cells.append(f"{v['warm_data_statements']} / {v.get('post_commit_data_statements')} / {v['cold_data_statements']} (derived sum)")
            else:
                w, c, p = v.get("warm") or {}, v.get("cold") or {}, v.get("post_commit") or {}
                cells.append(f"{w.get('request_thread_data')} / {p.get('request_thread_data')} / {c.get('request_thread_data')}")
        print(f"| {n} | " + " | ".join(cells) + " |")
    print()


def cold_table(results):
    labels = list(results)
    print("### Cold: first reads of a boot, quiet server. p50 / max ms (count). Measured.\n")
    print("| probe | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(labels))
    names = []
    for r in results.values():
        for n in (r.get("cold") or {}).get("by_probe", {}):
            if n not in names:
                names.append(n)
    for n in names:
        cells = []
        for k in labels:
            p = (results[k].get("cold") or {}).get("by_probe", {}).get(n)
            cells.append(f"{fmt(p['p50'])} / {fmt(p['max'])} ({p['count']})" if p and p.get("count") else "-")
        print(f"| {n} | " + " | ".join(cells) + " |")
    print()


def ratio(xs):
    xs = [x for x in xs if x]
    return round(max(xs) / min(xs), 2) if len(xs) > 1 else None


def noise(results):
    """Runs within a boot, and boots: ratio largest/smallest of a metric's per-run value."""
    print("### Noise: largest / smallest, for one candidate. Derived from measured runs.\n")
    print("`within`: across runs of a boot, per label. `boots`: pooled value of one boot against another.\n")
    labels = list(results)
    print("| level | metric | " + " | ".join(f"{k} by run" for k in labels) + " | within | boots |")
    print("|---|---|" + "---|" * len(labels) + "---|---|")
    out = []
    for lv in levels_of(results):
        for probe in PROBES:
            for stat in ("p50", "p95"):
                by_run, pooled = [], []
                for k in labels:
                    p = results[k]["levels"].get(lv, {}).get("aggregate", {}).get("probes", {}).get(probe)
                    by_run.append(p.get(f"{stat}_by_run") if p else None)
                    pooled.append(p.get(stat) if p else None)
                if not any(by_run):
                    continue
                within = [ratio(x) for x in by_run if x]
                within = max([w for w in within if w], default=None)
                boots = ratio(pooled)
                cnt = min((results[k]["levels"][lv]["aggregate"]["probes"][probe]["count"]
                           for k in labels if probe in results[k]["levels"].get(lv, {}).get("aggregate", {}).get("probes", {})), default=0)
                out.append({"level": lv, "probe": probe, "stat": stat, "within": within, "boots": boots, "count": cnt})
                cells = [",".join(fmt(v) for v in x) if x else "-" for x in by_run]
                print(f"| {lv} | {probe} {stat} | " + " | ".join(cells) + f" | {within} | {boots} |")
    print()
    for stat in ("p50", "p95"):
        ws = [r["within"] for r in out if r["stat"] == stat and r["within"]]
        bs = [r["boots"] for r in out if r["stat"] == stat and r["boots"]]
        if ws:
            print(f"{stat}: within-boot ratio median {statistics.median(ws):.2f}, worst {max(ws):.2f}; "
                  + (f"boot-to-boot median {statistics.median(bs):.2f}, worst {max(bs):.2f}" if bs else "one boot only"))
    print()
    if len(labels) > 1:
        for stat in ("p50", "p95"):
            print(f"Per probe, {stat}, worst within or boots across levels:")
            for probe in PROBES:
                vals = [max(x for x in (r["within"], r["boots"]) if x) for r in out
                        if r["probe"] == probe and r["stat"] == stat and (r["within"] or r["boots"])]
                if vals:
                    print(f"  {probe}: median {statistics.median(vals):.2f}, worst {max(vals):.2f} over {len(vals)} levels")
            print()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--noise", action="store_true")
    ap.add_argument("--csv")
    ap.add_argument("--evidence", action="store_true", help="read exactly one result, which need not qualify")
    a = ap.parse_args()
    results = {k: load(k) for k in a.labels}
    bad = []
    if a.evidence:
        if len(results) != 1 or a.noise or a.csv:
            raise G.Refused("--evidence reads one result and compares nothing")
        k, r = next(iter(results.items()))
        print(f"**EVIDENCE ONLY, NOT A CANDIDATE: {k}.** " + "; ".join(G.why_not_a_candidate(k, r) or ["it would qualify"]) + "\n")
    else:
        G.refuse_unless_comparable(results)
        bad = [f"{k}: {why}" for k, r in results.items() for why in W.bad_statuses(r)]
    header(results)
    if a.noise:
        out = noise(results)
        if a.csv:
            with open(a.csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["level", "probe", "stat", "within", "boots", "count"])
                w.writeheader()
                w.writerows(out)
        return report_bad(bad)
    rows = []
    probe_tables(results, rows)
    background_table(results)
    statement_table(results)
    cold_table(results)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["label", "level", "probe", "count", "p50", "p95", "max", "errors", "bad_status"])
            w.writerows(rows)
    return report_bad(bad)


def report_bad(bad):
    for why in bad:
        print(f"BAD STATUS: {why}", file=sys.stderr)
    return G.FAILED if bad else 0


if __name__ == "__main__":
    sys.exit(main())
