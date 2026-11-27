"""Product smoke on TEST after a deploy, against TEST's real data. Read-only: nothing is sent.

Quiet loads, the Needs You panel opens, a conversation draws its posts, a Magnet opens and its
Perspectives read. Prints smoke.json; screenshots go to --out. Record the result with
`mentis_env.py record <release> browser`. Exit 1 if any step failed or the page erred."""
import json, os, sys, time
from playwright.sync_api import sync_playwright
import argparse
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--base", default="http://127.0.0.1:8780")
ap.add_argument("--conversation", default="ent-0db5ea9a3307", help="a conversation with posts")
ap.add_argument("--magnet", default="mag-265878e92e5c987c")
ap.add_argument("--magnet-name", default="Space missions and astronomy")
ap.add_argument("--out", default=".")
A = ap.parse_args()
BASE, MAG = A.base, A.magnet
WHERE = f".q2-magnet-canvas [data-magnet=\"{MAG}\"]"
os.makedirs(A.out, exist_ok=True); os.chdir(A.out)
errors, bad, out = [], [], {}
def step(name, fn):
    t = time.time()
    try: out[name] = {"ok": True, "detail": fn(), "s": round(time.time() - t, 1)}
    except Exception as e: out[name] = {"ok": False, "detail": str(e)[:300], "s": round(time.time() - t, 1)}
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    page = b.new_context(viewport={"width": 1500, "height": 1100}).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.on("response", lambda r: bad.append(f"{r.status} {r.url[:120]}") if r.status >= 500 else None)
    def home():
        page.goto(BASE + "/", wait_until="domcontentloaded"); page.wait_for_timeout(8000)
        page.screenshot(path="1-home.png"); return page.title()
    def needs():
        if not page.locator(".q2-gdock-panel").count():
            page.locator(".q2-gdock-btn[data-panel='activity']").click()
        page.locator(".q2-gdock-panel").first.wait_for(timeout=60000); page.wait_for_timeout(4000)
        page.screenshot(path="2-needs-you.png"); return {"items": page.locator("[data-needs-item]").count()}
    def conv():
        page.goto(BASE + f"/?c={A.conversation}", wait_until="domcontentloaded")
        page.locator(".q2-conv [data-post]").first.wait_for(timeout=120000); page.wait_for_timeout(2000)
        page.screenshot(path="3-conversation.png"); return {"posts_drawn": page.locator(".q2-conv [data-post]").count()}
    def magnet():
        page.goto(BASE + "/quiet2", wait_until="domcontentloaded"); page.wait_for_timeout(15000)
        page.locator("[data-open-magnet]:visible").first.click(); page.wait_for_timeout(1500)
        row = page.get_by_role("option", name=A.magnet_name, exact=False).first
        row.wait_for(timeout=90000); row.click(); page.wait_for_timeout(1200)
        page.get_by_role("button", name="Open in current workspace", exact=False).first.click(); page.wait_for_timeout(5000)
        card = page.locator(f"{WHERE} .q2-magnet-card")
        if card.count() == 0: page.locator(f"{WHERE} .q2-magnet-puck").click(); page.wait_for_timeout(2500)
        try: page.get_by_role("button", name="Larger panel", exact=False).first.click(); page.wait_for_timeout(1500)
        except Exception: pass
        page.screenshot(path="4-magnet.png")
        card.get_by_role("tab", name="Perspectives", exact=False).first.click(); page.wait_for_timeout(5000)
        rows = card.locator(".q2p-aside-row").count()
        page.screenshot(path="5-perspectives.png")
        return {"perspective_rows": rows, "text": card.inner_text()[:400]}
    for n, f in [("home", home), ("needs_you", needs), ("conversation", conv), ("magnet_perspectives", magnet)]:
        step(n, f)
    b.close()
out["page_errors"] = errors; out["http_5xx"] = bad
json.dump(out, open("smoke.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1)[:3000])
sys.exit(0 if all(v.get("ok") for k, v in out.items() if isinstance(v, dict)) and not errors and not bad else 1)
