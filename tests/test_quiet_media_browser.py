"""Package F, against real Mentis HTTP routes on a disposable fixture Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis import artifacts
from mentis.conversation import text
from tests._loop import get, world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

# A minimal, valid 1x1 transparent PNG -- its own signature decides `treatment`,
# the way the server decides it for any sender's bytes.
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
       b"\x00\x00\x05\x00\x01\r\n\x00\x00\x00\x00IEND\xaeB`\x82")


def hold(world, data, name, media_type, conversation):
    held = artifacts.hold(
        world["state"].corpus, world["cv"], data, act="artifact-submitted",
        actor=world["who"]["@brian"], source=f"submission:{world['who']['@brian']}",
        door="human-ingress", conversation=conversation,
        claimed_name=name, claimed_media_type=media_type)
    return held["admission"]


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_media_real_api(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner = world["cv"], world["who"]["@brian"]
    corpus = world["state"].corpus
    conv = cv.open_conversation("Quiet media browser", about="Attachments for the gallery.")
    cv.join(owner, conv)

    cat = hold(world, PNG, "cat.png", "image/png", conv)
    dog = hold(world, PNG, "dog.png", "image/png", conv)
    gallery_turn = cv.say(conv, owner, [
        artifacts.part(cat, corpus=corpus),
        artifacts.part(dog, corpus=corpus),
    ])

    notes = hold(world, b"a short note", "notes.txt", "text/plain", conv)
    file_turn = cv.say(conv, owner, [artifacts.part(notes, corpus=corpus)])
    file_number = get(world, f"/api/turns/{file_turn}")["number"]

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{conv}")
            page.get_by_role("heading", name="Quiet media browser", exact=True).wait_for()

            # An image part renders as an image, not a bare "name ↗" link.
            gallery = page.locator(f"#qc-post-{gallery_turn}")
            gallery.wait_for()
            assert gallery.locator("img").count() == 2
            assert gallery.get_by_text("↗", exact=False).count() == 0

            # The images in the post form a gallery: clicking one opens the
            # lightbox, previous/next step through the post's other images,
            # Escape closes, and focus returns to the thumbnail that opened it.
            first_thumb = gallery.locator("[data-qc-gallery]").first
            first_thumb.click()
            dialog = page.get_by_role("dialog")
            dialog.wait_for()
            assert dialog.get_by_role("button", name="Previous image").count() == 1
            assert dialog.get_by_role("button", name="Next image").count() == 1
            dialog.get_by_text("1 of 2", exact=True).wait_for()
            page.keyboard.press("ArrowRight")
            dialog.get_by_text("2 of 2", exact=True).wait_for()
            page.keyboard.press("ArrowLeft")
            dialog.get_by_text("1 of 2", exact=True).wait_for()
            page.keyboard.press("Escape")
            dialog.wait_for(state="detached")
            assert page.evaluate(
                "document.activeElement.getAttribute('data-qc-name')") == "cat.png"

            # Focus is trapped while the dialog is open: Tab from the last
            # focusable control cycles back to the first rather than escaping
            # into the page behind it.
            first_thumb.click()
            dialog.wait_for()
            close_button = dialog.get_by_role("button", name="Close")
            next_button = dialog.get_by_role("button", name="Next image")
            next_button.focus()
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Close"
            close_button.focus()
            page.keyboard.press("Shift+Tab")
            assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Next image"
            page.keyboard.press("Escape")
            dialog.wait_for(state="detached")

            # A non-image attachment states its name, type and size, names its
            # originating post, and still reaches the artifact's own URL.
            file_post = page.locator(f"#qc-post-{file_turn}")
            file_post.wait_for()
            assert file_post.locator("img").count() == 0
            link = file_post.get_by_role("link", name="notes.txt", exact=True)
            link.wait_for()
            assert link.get_attribute("href") == f"/api/artifacts/{notes}"
            meta = file_post.locator(".qc-media-meta")
            assert "text/plain" in meta.inner_text()
            assert f"#{file_number}" in meta.inner_text()

            assert errors == []
        finally:
            browser.close()
