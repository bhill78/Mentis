"""Focused interaction and preservation checks for the standalone Magnet preview.

Run on the committed artifact with installed Windows Edge, headless. No server,
Brain, agent, source adapter, screenshots or application suite is involved.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

from playwright.sync_api import sync_playwright, expect


ROOT = Path(__file__).resolve().parent
HTML = ROOT / "magnet-preview.html"
checks, failures, errors, requests, page_errors = [], [], [], [], []


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


def reset(page):
    page.goto(HTML.as_uri())
    page.evaluate("localStorage.clear()")
    page.reload()
    expect(page.locator('[data-tab="Summary"]')).to_have_attribute("aria-current", "page")


def tab(page, name):
    page.locator(f'button[data-tab="{name}"]').click()
    expect(page.locator(f'button[data-tab="{name}"]')).to_have_attribute("aria-current", "page")


def main_menu(page, name):
    page.locator("#send-options").click()
    page.locator('[data-send="record"' + ']' if name == "Record only" else '[data-send="ask"]').click()


def scroll_position(page):
    return page.locator("#view").evaluate("el => el.scrollTop")


def assert_scroll(page, target, name):
    # Sending removes the context chip and gives the reader more height, so an
    # earlier bottom position is legitimately clamped to the new scroll maximum.
    page.wait_for_function("([el, top]) => Math.abs(el.scrollTop - Math.min(top, el.scrollHeight-el.clientHeight)) <= 2", arg=[page.locator("#view").element_handle(), target], timeout=1500)
    maximum = page.locator("#view").evaluate("el => el.scrollHeight - el.clientHeight")
    check(name, abs(scroll_position(page) - min(target, maximum)) <= 2)


def journey(page):
    reset(page)
    names = page.locator("button[data-tab]").all_text_contents()
    check("Six compact tabs in owner order", [n.strip() for n in names] == ["Summary", "All", "Posts", "Files", "Perspectives", "Conversation"])
    check("Summary opens alone, with composer", page.locator("#summary").is_visible() and page.locator("#inquiry").count() == 0 and page.locator("#discussion").count() == 0 and page.locator("#composer").is_visible())
    check("Grounded synthesis remains unavailable with reason", page.get_by_role("button", name="Synthesize from evidence", exact=True).is_disabled() and "restricted" in page.locator("#grounded-status").inner_text())
    reader = page.locator("#workspace-reader").bounding_box()
    original_draft = page.locator("#workspace-draft").input_value()
    page.locator("#workspace-reader").evaluate("el => el.scrollTop = 113")
    outside_scroll = page.locator("#workspace-reader").evaluate("el => el.scrollTop")
    page.locator("#support-file").click()
    expect(page.locator("#inspect-title")).to_have_text("calibration.txt")
    check("Evidence inspection remains inside Summary", page.locator("#summary #inspect-title").count() == 1)
    page.get_by_text("Source & captured version", exact=True).click()
    check("Evidence reveals version and scope", "Captured attachment bytes" in page.locator(".provenance").inner_text() and "Bounds" in page.locator(".provenance").inner_text())
    page.locator("#message").fill("Which reference would make this comparison meaningful?")
    check("Typing attaches inspected evidence context", "calibration.txt" in page.locator("#composer-context").inner_text())
    page.locator("#view").evaluate("el => el.scrollTop = el.scrollHeight")
    before = scroll_position(page)
    page.locator("#send").click()
    expect(page.locator('[data-tab="Conversation"]')).to_have_attribute("aria-current", "page")
    check("Sending automatically enters Conversation with submitted question", "Which reference would make this comparison meaningful?" in page.locator("#messages").inner_text())
    check("Illustrative reply labels its evidence boundary", "illustrative reply" in page.locator("#messages").inner_text().lower() and "not read" in page.locator("#messages").inner_text().lower())
    check("Submitted message carries explicit evidence reference", "calibration.txt" in page.locator("#messages .owner").inner_text())
    page.locator("#return-view").click()
    expect(page.locator('[data-tab="Summary"]')).to_have_attribute("aria-current", "page")
    check("Return restores evidence and provenance working state", page.locator("#inspect-title").inner_text() == "calibration.txt" and page.locator(".provenance").evaluate("el => el.open"))
    assert_scroll(page, before, "Return restores Summary reading position")
    check("Workspace reader, its position and draft remain unchanged", reader == page.locator("#workspace-reader").bounding_box() and original_draft == page.locator("#workspace-draft").input_value() and outside_scroll == page.locator("#workspace-reader").evaluate("el => el.scrollTop"))


def tabs_and_drafts(page):
    reset(page)
    page.locator("#message").fill("Keep my unsent message")
    for name in ["All", "Posts", "Files", "Perspectives", "Summary"]:
        tab(page, name)
        check("Composer and unsent draft persist on " + name, page.locator("#message").is_visible() and page.locator("#message").input_value() == "Keep my unsent message")
        if name == "Posts":
            check("Posts shows only post evidence", page.locator(".evidence-row").count() == 3 and "calibration.txt" not in page.locator("#view").inner_text())
        if name == "Files":
            check("Files shows only file evidence", page.locator(".evidence-row").count() == 2 and page.locator("#view").inner_text().find("README.md") >= 0)
    tab(page, "Posts")
    page.locator("#send").click()
    expect(page.locator('[data-tab="Conversation"]')).to_have_attribute("aria-current", "page")
    page.locator("#return-view").click()
    check("Posts send returns to Posts", page.locator('[data-tab="Posts"]').get_attribute("aria-current") == "page")
    tab(page, "Files")
    page.locator("#message").fill("Discuss file scope")
    page.locator("#send").click()
    expect(page.locator('[data-tab="Conversation"]')).to_have_attribute("aria-current", "page")
    page.locator("#return-view").click()
    check("Files send returns to Files", page.locator('[data-tab="Files"]').get_attribute("aria-current") == "page")


def search(page):
    reset(page)
    page.locator("#message").fill("Search should keep this draft")
    page.locator("#search").fill("calibration")
    expect(page.locator("#search-results")).to_be_visible()
    check("Search replaces reading body rather than stacking Summary", page.locator("#summary").count() == 0 or not page.locator("#summary").is_visible())
    page.locator("#search-type").select_option(label="Files")
    check("Search type filtering narrows to file results", "calibration.txt" in page.locator("#search-results").inner_text() and "Calibration delta: 37" not in page.locator("#search-results").inner_text())
    page.locator("#search-results").get_by_role("button", name="calibration.txt", exact=False).first.click()
    expect(page.locator("#inspect-title")).to_have_text("calibration.txt")
    check("Search inspection keeps query and type", page.locator("#search").input_value() == "calibration" and page.locator("#back-search").is_visible())
    page.locator("#message").fill("Explain what to collect next")
    page.locator("#send").click()
    expect(page.locator('[data-tab="Conversation"]')).to_have_attribute("aria-current", "page")
    page.locator("#return-view").click()
    check("Conversation return restores search inspection", page.locator("#inspect-title").inner_text() == "calibration.txt" and page.locator("#search").input_value() == "calibration")
    page.locator("#back-search").click()
    expect(page.locator("#search-results")).to_be_visible()
    check("Back to results restores query and type filter", page.locator("#search").input_value() == "calibration" and page.locator("#search-type option:checked").inner_text() == "Files")
    page.locator("#close-search").click()
    check("Search returns to original Summary", page.locator('[data-tab="Summary"]').get_attribute("aria-current") == "page" and page.locator("#summary").is_visible())
    page.locator("#search").fill("a-phrase-with-no-match-912346")
    check("No search matches provides recovery", "No matches" in page.locator("#search-results").inner_text() and page.locator("#close-search").is_visible())


def settings(page):
    reset(page)
    page.locator("#message").fill("Unsent message across settings")
    page.locator("#settings-toggle").click()
    expect(page.locator("#settings-panel")).to_be_visible()
    check("Header uses accessible gear rather than Settings text", "Settings" not in page.locator("#settings-toggle").inner_text() and bool(page.locator("#settings-toggle").get_attribute("aria-label")))
    check("Settings is a focused internal view", page.locator("#summary").count() == 0 or not page.locator("#summary").is_visible())
    text = page.locator("#settings-panel").inner_text().lower()
    check("Universal source model distinguishes future adapters", all(word in text for word in ["conversation", "posts", "topic", "files", "web page", "web search", "database", "repositor", "connected service"]) and "future" in text and "supported" in text)
    lab = page.locator('[data-source="lab"]')
    lab.check()
    page.get_by_role("button", name="Cancel", exact=True).click()
    page.locator("#settings-toggle").click()
    check("Cancel discards staged source selection without losing message", not page.locator('[data-source="lab"]').is_checked() and page.locator("#message").input_value() == "Unsent message across settings")
    page.locator('[data-source="lab"]').check()
    page.get_by_role("button", name="Save settings · demo", exact=True).click()
    page.locator("#settings-toggle").click()
    check("Save retains source selection", page.locator('[data-source="lab"]').is_checked())
    page.locator("#after").fill("2026-11-25")
    page.locator("#before").fill("2026-11-20")
    page.get_by_role("button", name="Save settings · demo", exact=True).click()
    check("Invalid date scope is blocked in settings", page.locator("#settings-error").is_visible() and page.locator("#settings-panel").is_visible())
    page.get_by_role("button", name="Cancel", exact=True).click()


def perspectives(page):
    reset(page)
    page.locator("#message").fill("Independent unsent conversation draft")
    tab(page, "Perspectives")
    page.locator("#new-question").click()
    question = "Which reference should the next observation include?"
    page.locator("#question-text").fill(question)
    check("Creation is question first without a name field", page.locator("#question-form input").count() == 0)
    page.locator('[data-act="revise-question"]').click()
    revision = "Revise independently without overwriting the new inquiry"
    page.locator("#question-text").fill(revision)
    page.locator("#new-question").click()
    check("Revise cannot destroy typed new-question draft", page.locator("#question-text").input_value() == question)
    page.locator('[data-act="rename"]').click()
    page.locator("#rename-text").fill("Separate rename draft")
    page.locator("#new-question").click()
    check("Rename cannot destroy typed new-question or message drafts", page.locator("#question-text").input_value() == question and page.locator("#message").input_value() == "Independent unsent conversation draft")
    page.locator('[data-act="revise-question"]').click()
    check("Revision draft is restored independently", page.locator("#question-text").input_value() == revision)
    page.locator("#new-question").click()
    tab(page, "Files")
    tab(page, "Perspectives")
    check("Tab switches retain active question draft", page.locator("#question-text").input_value() == question)
    page.reload()
    check("Reload preserves active question and message drafts", page.locator("#question-text").input_value() == question and page.locator("#message").input_value() == "Independent unsent conversation draft")
    page.get_by_role("button", name="Save Perspective · demo", exact=True).click()
    check("Saved Perspective gets automatic name", page.locator(".lens-question").inner_text() == question and page.locator("#lens option:checked").inner_text().startswith("Which reference"))
    page.locator("#lens").select_option(index=0)
    page.locator('[data-act="revise-question"]').click()
    check("Saving new inquiry leaves earlier Perspective revision draft intact", page.locator("#question-text").input_value() == revision)
    page.locator("#lens").select_option(index=1)
    page.locator("#question-text").fill("A separate revision of the second Perspective")
    page.locator("#lens").select_option(index=0)
    check("Perspective selection preserves each revision draft", page.locator("#question-text").input_value() == revision)
    page.locator('[data-act="rename"]').click()
    check("Earlier rename draft survives creation and selection", page.locator("#rename-text").input_value() == "Separate rename draft")
    page.locator("#lens").select_option(index=1)
    page.locator('[data-act="cancel-editor"]').click()
    page.locator("#message").fill("How should we develop this inquiry?")
    check("Perspective is attached compactly while typing", question in page.locator("#composer-context").inner_text())
    page.locator("#send").click()
    expect(page.locator('[data-tab="Conversation"]')).to_have_attribute("aria-current", "page")
    check("Perspective discussion uses shared composer and context", "How should we develop this inquiry?" in page.locator("#messages").inner_text() and question in page.locator("#messages .owner").inner_text())
    page.locator("#return-view").click()
    check("Discussion return restores selected Perspective", page.locator('[data-tab="Perspectives"]').get_attribute("aria-current") == "page" and page.locator(".lens-question").inner_text() == question)


def composer_keyboard(page):
    reset(page)
    check("Compact composer has split button and no Action or Agent dropdowns", page.locator("#send-options").is_visible() and page.locator("#composer select").count() == 0)
    page.locator("#message").fill("First line")
    page.locator("#message").press("Shift+Enter")
    page.locator("#message").type("Second line")
    check("Shift+Enter keeps a multiline draft", page.locator("#message").input_value() == "First line\nSecond line" and page.locator('[data-tab="Summary"]').get_attribute("aria-current") == "page")
    page.locator("#message").press("Enter")
    expect(page.locator('[data-tab="Conversation"]')).to_have_attribute("aria-current", "page")
    check("Enter submits once and preserves newlines", page.locator("#messages .owner").count() == 1 and "First line\nSecond line" in page.locator("#messages .owner").inner_text())
    page.locator("#message").fill("Control submission")
    page.locator("#message").press("Control+Enter")
    check("Ctrl+Enter submits", page.locator("#messages .owner").count() == 2)
    count_before = page.locator("#messages .bubble").count()
    page.locator("#message").fill("Record this without an agent reply")
    page.locator("#message").press("Alt+Enter")
    check("Alt+Enter records only without illustrative agent response", page.locator("#messages .bubble").count() == count_before + 1)
    main_menu(page, "Record only")
    page.locator("#message").fill("Record from split menu")
    count_before = page.locator("#messages .bubble").count()
    page.locator("#send").click()
    check("Split menu changes the main sending action", page.locator("#messages .bubble").count() == count_before + 1)
    main_menu(page, "Ask Mentis")
    page.locator("#message").fill("Ask after record")
    page.locator("#send").click()
    check("Ask action is available after record only", "Ask after record" in page.locator("#messages").inner_text())
    tab(page, "Summary")
    page.locator("#support-file").click()
    page.locator("#message").fill("Remove this evidence reference before sending")
    page.locator("#composer-context").get_by_role("button").click()
    check("Context removal retains message words", not page.locator("#composer-context").inner_text().strip() and page.locator("#message").input_value() == "Remove this evidence reference before sending")
    page.locator("#message").type(" safely")
    page.locator("#send").click()
    check("Removed context does not silently reattach on further typing", "calibration.txt" not in page.locator("#messages .owner").last.inner_text())


def empty_and_puck(page):
    reset(page)
    page.locator("#settings-toggle").click()
    page.get_by_text("Preview fixtures", exact=True).click()
    page.locator("#empty-demo").click()
    tab(page, "Conversation")
    page.locator("#message").fill("Help me plan an inquiry before collecting anything")
    page.locator("#send").click()
    check("Ordinary conversation works with no collected evidence", "Help me plan an inquiry before collecting anything" in page.locator("#messages").inner_text() and page.locator("#messages .bubble").count() >= 2)
    page.locator("#message").fill("Puck close must preserve this")
    page.locator("#close").click()
    check("Yellow puck remains when card closes", page.locator("#puck").is_visible() and not page.locator("#card").is_visible())
    page.locator("#puck").click()
    check("Puck reopens card with message state", page.locator("#card").is_visible() and page.locator("#message").input_value() == "Puck close must preserve this")
    puck_before = page.locator("#puck").bounding_box()
    page.locator("#puck").focus()
    page.locator("#puck").press("ArrowRight")
    check("Desktop puck still moves by keyboard", page.locator("#puck").bounding_box()["x"] > puck_before["x"])


def narrow(page):
    for width, height in [(390, 844), (320, 640)]:
        page.set_viewport_size({"width": width, "height": height})
        reset(page)
        check(f"{width}px Summary composer and card stay in viewport", page.locator("#message").is_visible() and page.locator("#card").bounding_box()["x"] >= 0 and page.locator("#card").bounding_box()["x"] + page.locator("#card").bounding_box()["width"] <= width)
        check(f"{width}px no horizontal body overflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        page.locator("#support-file").click()
        page.locator("#message").fill(f"Question at {width}px")
        page.locator("#send").click()
        check(f"{width}px send enters Conversation", page.locator('[data-tab="Conversation"]').get_attribute("aria-current") == "page")
        page.locator("#return-view").click()
        page.locator("#settings-toggle").click()
        check(f"{width}px focused settings remains internally scrollable", page.locator("#settings-panel").is_visible() and page.locator("#view").evaluate("el => el.scrollHeight >= el.clientHeight") and page.evaluate("document.documentElement.scrollWidth <= innerWidth"))


def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 700})
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("request", lambda request: requests.append({"url": request.url, "type": request.resource_type}))
        for scenario in [journey, tabs_and_drafts, search, settings, perspectives, composer_keyboard, empty_and_puck, narrow]:
            try:
                scenario(page)
            except AssertionError as error:
                failures.append({"scenario": scenario.__name__, "error": str(error), "traceback": traceback.format_exc()})
            except Exception as error:
                failures.append({"scenario": scenario.__name__, "error": str(error), "traceback": traceback.format_exc()})
        check("No JavaScript page errors", not page_errors)
        check("No network or source adapter requests", all(request["url"].startswith("file:") and request["type"] == "document" for request in requests))
        version = browser.version
        browser.close()
        return version


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    browser_version = None
    try:
        browser_version = run()
    except Exception as error:
        errors.append({"scenario": "run", "error": str(error), "traceback": traceback.format_exc()})
    result = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "artifact_sha256": hashlib.sha256(HTML.read_bytes()).hexdigest() if HTML.exists() else None,
        "browser": "Installed Windows Edge, headless",
        "browser_version": browser_version,
        "counts": {"passed": sum(check["passed"] for check in checks), "failed": len(failures), "skipped": 0, "errors": len(errors)},
        "checks": checks, "failures": failures, "errors": errors,
        "page_errors": page_errors, "requests": requests,
    }
    (ROOT / "checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(1 if failures or errors else 0)
