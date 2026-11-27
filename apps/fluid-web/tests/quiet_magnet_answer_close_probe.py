"""The closing bookkeeping is gone from what the surfaces draw.

Owner `ent-bce57ba67f38`, read again on the narration strip's screenshots. The
same fixture and the same harness as `quiet_magnet_answer_read_shots.py` -- the
reply TEST's running candidate holds -- read for its TEXT rather than its
picture: the closing paragraph's sentences and its bare reference ids must be
absent from the Summary and Perspectives answers, and the answer's own last
paragraph must still be there. It also writes a shot of the answer's end on
each surface, which is where the owner saw the defect.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quiet_magnet_answer_read_shots import BASE, OUT, serve  # noqa: E402

GONE = [
    "The frozen question for Topic",
    "returned briefing",
    "returned successfully",
    "Nothing is required from the owner",
    "ent-85f547319077",
    "adm-3cfefbd3d5ad",
]
STAYS = "The collection also contains headline leads"


def main():
    proc = serve()
    bad = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1040, "height": 1500},
                                    device_scale_factor=2)
            page.on("console", lambda m: bad.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: bad.append(str(e)))
            for name, press in (("summary", None), ("perspectives", "#shot-perspectives")):
                page.goto(BASE, wait_until="load")
                page.wait_for_timeout(700)
                if press:
                    page.click(press)
                    page.wait_for_timeout(500)
                words = page.inner_text("body")
                for phrase in GONE:
                    if phrase in words:
                        bad.append(f"{name}: still draws {phrase!r}")
                if STAYS not in words:
                    bad.append(f"{name}: lost the answer's own last paragraph")
                print(f"{name}: checked {len(GONE)} phrases absent, the answer's own close present")
                end = page.locator(".q2-prose").last
                end.screenshot(path=str(OUT / f"after-{name}-close.png"))
                print("wrote", OUT / f"after-{name}-close.png")
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    if bad:
        raise SystemExit("\n".join(bad))
    print("PASS: no closing bookkeeping on either surface")


if __name__ == "__main__":
    sys.exit(main())
