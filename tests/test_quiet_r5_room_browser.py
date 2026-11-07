"""PACKAGE L's room, against real Mentis HTTP routes on a fixture Brain.

The owner's decision is what these cases hold the room to (ent-ecba3f3dcf3c):
the working area opens on the RIGHT and the conversation slides LEFT, with the
tools consolidated immediately left of the work area.

  * THE THREE ROOMS. Single chat keeps round four's tracks and its 760px
    measure; Chat and panes and Workspace board put the reading, a dragged
    separator, the consolidated tools and the working area in that order from
    left to right, each at or above its own minimum (reading 330, tools 240,
    work 300 -- F12), with the real gaps, the separator and a pinned toolbar
    taken off the available width first.
  * THE SEPARATOR IS CONTROLLED (F3). Dragging and the arrow keys change the
    room; a cancelled drag commits nothing; and no path through it writes
    Fluid's own conversation width or the place's arrangement.
  * ONE SURFACE WHERE THREE WILL NOT FIT, at 390px and at 901px alike, with an
    explicit switch, a named Return to conversation, no parked surface
    reachable by Tab, and the invoker's focus and the reading put back.
  * THE TOOLS ARE ONE STABLE MOUNT EACH (F27), in the `tools` slot, never
    reparented by expanding or collapsing the room, and keeping the reading M
    left open in them.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.

Set QUIET_ROOM_EVIDENCE to a folder to write the evidence screenshots.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

#: The three minima the room may never draw anything under (F12).
READING_MIN, TOOLS_MIN, WORK_MIN = 330, 240, 300

#: Fluid's own stores, by the prefixes they persist under (`fluid/nav.ts`,
#: `fluid/workspace/place.ts`). Nothing a Quiet drag does may touch one.
FLUID_KEYS = ("mentis.fluid.arr:", "mentis.fluid.travel", "mentis:fluid:")

STORAGE = """
() => {
  const read = (store) => {
    const out = {}
    for (let i = 0; i < store.length; i++) { const k = store.key(i); out[k] = store.getItem(k) }
    return out
  }
  return { local: read(localStorage), session: read(sessionStorage) }
}
"""

BOXES = """
(selectors) => {
  const out = {}
  for (const [name, selector] of Object.entries(selectors)) {
    const el = document.querySelector(selector)
    // NOT DRAWN is the question, not "has no display of its own": a fixed
    // dock inside a parked surface keeps its own `position: fixed` and is
    // laid out nowhere, which is exactly no client rects.
    if (!el || el.getClientRects().length === 0) { out[name] = null; continue }
    const r = el.getBoundingClientRect()
    out[name] = { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }
  }
  return out
}
"""

ROOM = {
    "room": ".qw-room",
    "tools": ".qw-tools",
    "railTools": ".qc-rail-tools",
    "nav": ".qc-cell-nav",
    "reading": "#qc-reading",
    "stream": "#qc-stream",
    "dock": ".qc-dock",
    "margin": ".qc-margin",
    "working": ".qw-working",
    "gutter": ".qw-room > .fx-gutter",
    "title": ".qc-cell-title",
}


def _a_conversation(world, name="Quiet room"):
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation(name, about="What the room is drawn around.")
    cv.join(owner, cid)
    cv.open_topic(cid, "Reading", about="What the margin lists.")
    for n in range(16):
        cv.say(cid, owner, [text(f"Post {n}. " + "A quiet conversation with room in its margins. " * 12)])
    return cid


def _open(page, world, conversation, name="Quiet room"):
    page.goto(world["base"] + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()
    page.get_by_label("Continue the conversation", exact=True).wait_for()
    page.get_by_role("radio", name="Single chat", exact=True).wait_for()


def _mode(page, name):
    """Choose a room, and wait for the room to say it is in it. An expanded
    room that can be drawn in full also waits for its separator: Fluid's
    Boundary is fetched when there is something to separate, so it arrives a
    tick after the room does."""
    page.get_by_role("radio", name=name, exact=True).check()
    want = {"Single chat": "single", "Chat and panes": "panes", "Workspace board": "board"}[name]
    page.wait_for_function("(m) => document.querySelector('.qw-room')?.dataset.mode === m", arg=want)
    page.wait_for_function("""() => {
      const room = document.querySelector('.qw-room')
      if (!room || room.dataset.mode === 'single' || room.hasAttribute('data-one')) return true
      return !!room.querySelector(':scope > .fx-gutter')
    }""")


def _boxes(page):
    return page.evaluate(BOXES, ROOM)


def _no_sideways(page, where):
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"), (
        f"the page scrolls sideways: {where}")


def _reading_post(page):
    """The post the reader can see, read the way the reader's own anchor
    reads it: the first one drawn below the top of the reading."""
    return page.evaluate("""() => {
      for (const el of document.querySelectorAll('.qc-post')) {
        const r = el.getBoundingClientRect()
        if (r.bottom > 2 && r.top < innerHeight) return el.id
      }
      return null
    }""")


def _shot(page, name):
    folder = os.environ.get("QUIET_ROOM_EVIDENCE")
    if not folder:
        return
    Path(folder).mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(Path(folder) / name))


# -- 1. the room the owner asked for ------------------------------------------

@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_working_area_opens_right_and_the_conversation_slides_left(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page, world, conversation)

            # SINGLE CHAT IS ROUND FOUR'S ROOM. Tools left, reading in the
            # middle under the header's own centre cell, margin right.
            at = _boxes(page)
            assert at["tools"]["x"] < at["reading"]["x"] < at["margin"]["x"]
            assert abs(at["reading"]["x"] - at["title"]["x"]) <= 1
            assert abs(at["reading"]["width"] - at["title"]["width"]) <= 1
            # The measure is `--qc-measure`'s cap, which a 1440px window with
            # a scrollbar does not quite reach -- as in round four, and for
            # round four's reason: the three tracks share what the frame has.
            assert READING_MIN < at["reading"]["width"] <= 760 + 1, at["reading"]
            assert at["reading"]["width"] > at["tools"]["width"], "the reading is not the widest track"
            assert at["gutter"] is None, "no separator is drawn where there is nothing to share"
            assert at["working"] is None, "Single chat shows no working area"
            # The margin's top is still the heading row's lower edge: nothing
            # was added above the work row.
            heading = page.locator(".qc-heading").bounding_box()
            assert abs((heading["y"] + heading["height"]) - at["margin"]["y"]) <= 1
            _no_sideways(page, "1440 single")
            was = _reading_post(page)

            # CHAT AND PANES: reading | separator | tools | work, left to right.
            _mode(page, "Chat and panes")
            at = _boxes(page)
            assert at["working"], "the working area is not drawn in Chat and panes"
            assert (at["reading"]["right"] <= at["gutter"]["x"] + 1
                    <= at["tools"]["x"] + 1 <= at["working"]["x"] + 1), (
                f"the room is not reading | separator | tools | work: {at}")
            assert at["working"]["right"] > at["tools"]["right"], "the work area is not on the right"
            # The margins consolidated immediately left of the work area: same
            # column as the tools, and clear of the work.
            assert abs(at["margin"]["x"] - at["tools"]["x"]) <= 1, "the margin left the tools column"
            assert at["margin"]["right"] <= at["working"]["x"] + 1
            assert at["railTools"]["x"] >= at["tools"]["x"] - 1, "the reading switches left the tools column"
            # Every minimum met, with the real gaps already spent.
            assert at["reading"]["width"] >= READING_MIN
            assert at["tools"]["width"] >= TOOLS_MIN
            assert at["working"]["width"] >= WORK_MIN
            assert abs(at["reading"]["width"] - 640) <= 2, "panes did not open near 640px"
            _no_sideways(page, "1440 panes")
            assert _reading_post(page) == was, "expanding the room lost the visible post"

            # WORKSPACE BOARD: the work takes the room, the reading its floor.
            _mode(page, "Workspace board")
            board = _boxes(page)
            assert abs(board["reading"]["width"] - READING_MIN) <= 2, "the board did not open at the readable floor"
            assert board["working"]["width"] >= at["working"]["width"], "the board gave the work no more room"
            assert board["tools"]["width"] >= TOOLS_MIN
            _no_sideways(page, "1440 board")

            # COLLAPSE keeps the same visible post and the tools' reading.
            page.get_by_role("button", name="Brief", exact=True).click()
            page.get_by_role("button", name="Close margin").wait_for()
            # Read the place with the control ALREADY in view: clicking
            # something below the fold scrolls the page first, so the post
            # the collapse has to keep would otherwise be read before the
            # click moved the reader.
            back = page.get_by_role("button", name="Return to conversation", exact=True)
            back.scroll_into_view_if_needed()
            page.wait_for_timeout(150)
            was = _reading_post(page)
            back.click()
            page.wait_for_function("() => document.querySelector('.qw-room')?.dataset.mode === 'single'")
            assert page.get_by_role("radio", name="Single chat", exact=True).is_checked()
            assert page.locator(".qc-margin").get_by_role("heading", name="Brief").count() == 1, (
                "collapsing the room lost the reading the tools had open"
            )
            assert _reading_post(page) == was, "collapsing the room lost the visible post"
            assert errors == []
        finally:
            browser.close()


# -- 2. the separator (F3) ----------------------------------------------------

@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_separator_moves_the_room_and_writes_nothing_of_fluids(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page, world, conversation)
            _mode(page, "Chat and panes")
            gutter = page.locator(".qw-room > .fx-gutter")
            gutter.wait_for()
            assert gutter.get_attribute("aria-label") == (
                "Conversation width: drag or use arrow keys to resize")
            assert gutter.get_attribute("role") == "separator"

            before = page.evaluate(STORAGE)
            start = _boxes(page)

            # DRAGGING IT RIGHT gives the conversation room and the work less.
            box = gutter.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 120)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 80, box["y"] + 120, steps=8)
            said = page.locator(".qw-room > .fx-gutter .fx-readout")
            said.wait_for()
            assert "working area" in said.text_content(), said.text_content()
            page.mouse.up()
            page.wait_for_function(
                "(w) => Math.abs(document.querySelector('#qc-reading').getBoundingClientRect().width - w) > 40",
                arg=start["reading"]["width"])
            dragged = _boxes(page)
            assert dragged["reading"]["width"] > start["reading"]["width"] + 40
            assert dragged["working"]["width"] < start["working"]["width"] - 40
            assert dragged["working"]["width"] >= WORK_MIN
            assert dragged["tools"]["width"] >= TOOLS_MIN

            # THE KEYBOARD IS THE SAME CHANNEL, and clamps the same way.
            gutter.focus()
            page.keyboard.press("ArrowLeft")
            page.wait_for_function(
                "(w) => document.querySelector('#qc-reading').getBoundingClientRect().width < w - 8",
                arg=dragged["reading"]["width"])
            keyed = _boxes(page)
            page.keyboard.press("Home")
            page.wait_for_function(
                f"() => Math.abs(document.querySelector('#qc-reading').getBoundingClientRect().width - {READING_MIN}) <= 1")
            page.keyboard.press("End")
            page.wait_for_function(
                "() => document.querySelector('.qw-working').getBoundingClientRect().width >= 299")
            ended = _boxes(page)
            assert ended["working"]["width"] >= WORK_MIN, "End drove the work area under its minimum"
            assert ended["reading"]["width"] <= 760 + 1, "End drove the reading past Quiet's measure"

            # A CANCELLED DRAG COMMITS NOTHING, and leaves no drag class behind.
            settled = _boxes(page)
            box = gutter.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 120)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 - 120, box["y"] + 120, steps=6)
            page.evaluate("() => window.dispatchEvent(new Event('pointercancel'))")
            page.mouse.up()
            page.wait_for_function(
                "(w) => Math.abs(document.querySelector('#qc-reading').getBoundingClientRect().width - w) <= 1",
                arg=settled["reading"]["width"])
            assert not page.evaluate("document.body.classList.contains('fx-dragging')")

            # CLEANUP: the separator goes with the room, mid-drag or not.
            box = gutter.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 120)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 60, box["y"] + 120, steps=4)
            _mode(page, "Single chat")
            page.mouse.up()
            assert page.locator(".qw-room > .fx-gutter").count() == 0
            assert not page.evaluate("document.body.classList.contains('fx-dragging')")

            # NOTHING OF FLUID'S WAS WRITTEN BY ANY OF THAT. The conversation
            # width Fluid draws from lives in its nav and in the place's
            # arrangement; neither has a key here that changed, and the only
            # key that did is Quiet's own room bookmark.
            after = page.evaluate(STORAGE)
            for store in ("local", "session"):
                for key, value in after[store].items():
                    if key in before[store] and before[store][key] == value:
                        continue
                    assert not key.startswith(FLUID_KEYS), (
                        f"a Quiet drag wrote Fluid's {store}Storage key {key}")
                    assert "quiet" in key, f"a Quiet drag wrote an unrelated key: {key}"
                for key in before[store]:
                    if key not in after[store]:
                        assert not key.startswith(FLUID_KEYS), (
                            f"a Quiet drag removed Fluid's {store}Storage key {key}")
            assert errors == []
        finally:
            browser.close()


# -- 3. one surface at a time -------------------------------------------------

@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_at_390_one_surface_is_active_and_returning_puts_it_back(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=PHONE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page, world, conversation)
            page.wait_for_function("() => document.querySelector('.qw-room')?.hasAttribute('data-one')")

            # THE CONVERSATION IS WHAT A PHONE OPENS ON -- round four's own
            # narrow column, margins and navigation stacked above the reading.
            at = _boxes(page)
            assert at["reading"] and at["nav"] and at["margin"], at
            assert at["margin"]["y"] < at["stream"]["y"], "the margin left the narrow column"
            assert abs(at["margin"]["width"] - at["stream"]["width"]) <= 1
            # The composer is reachable, and the end of the reading is not
            # under it.
            page.evaluate("() => document.scrollingElement.scrollTo(0, document.scrollingElement.scrollHeight)")
            end = page.evaluate("""() => {
              const posts = [...document.querySelectorAll('.qc-post')]
              const last = posts[posts.length - 1].getBoundingClientRect()
              const dock = document.querySelector('.qc-dock').getBoundingClientRect()
              return { last: last.bottom, dock: dock.y, bottom: dock.bottom, height: innerHeight }
            }""")
            assert end["dock"] >= 0 and end["bottom"] <= end["height"] + 1, end
            assert end["last"] <= end["dock"] + 2, "the end of the reading hides beneath the composer"
            _no_sideways(page, "390 conversation")
            _shot(page, f"{engine}-390-conversation.png")
            page.evaluate("() => document.scrollingElement.scrollTo(0, 0)")
            was = _reading_post(page)

            # SHOWING THE TOOLS PARKS THE READING -- out of sight and out of
            # the focus order, its composer with it.
            switch = page.get_by_role("button", name="Show tools", exact=True)
            switch.click()
            page.wait_for_function("() => document.querySelector('.qw-room')?.dataset.showing === 'tools'")
            at = _boxes(page)
            assert at["reading"] is None and at["dock"] is None, "the reading is still drawn"
            assert at["margin"] and at["railTools"], "the tools surface shows no tools"
            assert page.get_by_label("Continue the conversation", exact=True).count() == 1
            assert not page.get_by_label("Continue the conversation", exact=True).is_visible()
            reachable = page.evaluate("""() => {
              const reading = document.querySelector('#qc-reading')
              return reading ? [...reading.querySelectorAll('a,button,input,textarea,select,[tabindex]')]
                .some((el) => el.offsetParent !== null) : false
            }""")
            assert not reachable, "a parked surface can still be reached by Tab"
            _no_sideways(page, "390 tools")
            _shot(page, f"{engine}-390-tools.png")

            # RETURNING RESTORES THE READING AND THE INVOKER'S FOCUS.
            page.get_by_role("button", name="Return to conversation", exact=True).click()
            page.wait_for_function("() => document.querySelector('.qw-room')?.dataset.showing === 'conversation'")
            page.locator("#qc-reading").wait_for(state="visible")
            page.wait_for_function("""() => {
              const el = document.querySelector('.qw-switch [data-for="tools"]')
              return !!el && el === document.activeElement
            }""")
            assert _reading_post(page) == was, "returning lost the post that was being read"
            _shot(page, f"{engine}-390-return.png")

            # THE WORKSPACE IS ITS OWN SURFACE, offered once there is one.
            _mode(page, "Chat and panes")
            page.get_by_role("button", name="Show the workspace", exact=True).click()
            page.wait_for_function("() => document.querySelector('.qw-room')?.dataset.showing === 'workspace'")
            at = _boxes(page)
            assert at["working"], "the workspace surface draws no working area"
            assert at["reading"] is None and at["margin"] is None and at["tools"] is None, at
            assert page.get_by_role("button", name="Return to conversation", exact=True).count() == 1
            _no_sideways(page, "390 workspace")
            _shot(page, f"{engine}-390-workspace.png")
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [900, 901, 1024, 1025])
def test_the_boundaries_keep_every_minimum_or_draw_one_surface(world, engine, width):
    """F12 to the pixel. At each boundary either all three surfaces are drawn
    at or above their minima, or exactly one is -- never three squeezed."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page, world, conversation)
            _mode(page, "Chat and panes")
            page.wait_for_timeout(120)
            one = page.evaluate("() => document.querySelector('.qw-room').hasAttribute('data-one')")
            at = _boxes(page)
            if one:
                # One surface, with the way back and the way on both named.
                assert at["reading"], "the fallback does not show the conversation"
                assert page.get_by_role("button", name="Show tools", exact=True).count() == 1
                assert page.get_by_role("button", name="Show the workspace", exact=True).count() == 1
                assert at["gutter"] is None, "a separator with nothing to share"
            else:
                assert at["reading"]["width"] >= READING_MIN, at
                assert at["tools"]["width"] >= TOOLS_MIN, at
                assert at["working"]["width"] >= WORK_MIN, at
                assert at["reading"]["right"] <= at["tools"]["x"] + 1 <= at["working"]["x"] + 1
            # 901px cannot hold three of them, whatever else is true (F12).
            if width == 901:
                assert one, "three surfaces were drawn at 901px"
            _no_sideways(page, f"{width} panes")
            # And the room settles: nothing measured here oscillates.
            settled = page.evaluate("""async () => {
              const read = () => document.querySelector('.qw-room').getBoundingClientRect().width
              const a = read()
              await new Promise((go) => requestAnimationFrame(() => requestAnimationFrame(go)))
              return [a, read()]
            }""")
            assert settled[0] == settled[1], f"the room is still resizing itself: {settled}"
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_pins_a_long_heading_a_tall_composer_and_reduced_motion(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    cv, owner = world["cv"], world["who"]["@brian"]
    name = "Quiet room with " + "a very long heading indeed " * 6
    conversation = _a_conversation(world, name)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE, reduced_motion="reduce")
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page, world, conversation, name)
            _mode(page, "Chat and panes")

            # A LONG HEADING DOES NOT WIDEN THE ROOM.
            _no_sideways(page, "long heading")
            at = _boxes(page)
            assert at["working"]["width"] >= WORK_MIN

            # BOTH PIN PREFERENCES. The header and margins first.
            page.get_by_role("button", name="Settings", exact=True).click()
            page.get_by_label("Pin header", exact=True).check()
            page.get_by_label("Pin margins", exact=True).check()
            page.get_by_role("checkbox", name="Pin toolbar", exact=True).check()
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector('.qc-toolbar')).position === 'fixed'")
            page.get_by_role("button", name="Close settings").click()
            page.wait_for_function("() => document.querySelector('.qw-room').dataset.mode === 'panes'")
            page.wait_for_timeout(160)
            pinned = page.evaluate("""() => {
              const room = document.querySelector('.qw-room')
              if (room.hasAttribute('data-one')) return { one: true }
              const strip = document.querySelector('.qc-toolbar').getBoundingClientRect()
              const work = document.querySelector('.qw-working').getBoundingClientRect()
              const tools = document.querySelector('.qw-tools').getBoundingClientRect()
              const reading = document.querySelector('#qc-reading').getBoundingClientRect()
              return { one: false, strip: strip.x, work: [work.x, work.right, work.width],
                       tools: tools.width, reading: reading.width }
            }""")
            if not pinned["one"]:
                assert pinned["work"][2] >= WORK_MIN, pinned
                assert pinned["tools"] >= TOOLS_MIN, pinned
                assert pinned["reading"] >= READING_MIN, pinned
                assert pinned["work"][1] <= pinned["strip"] + 1, (
                    f"the working area runs under the pinned strip: {pinned}")
            _no_sideways(page, "1440 panes, everything pinned")

            # A TALL COMPOSER STAYS ON SCREEN, with the room expanded.
            page.get_by_label("Continue the conversation", exact=True).fill(
                "\n".join(f"line {n}" for n in range(40)))
            page.wait_for_timeout(120)
            composer = page.get_by_label("Continue the conversation", exact=True).bounding_box()
            assert composer and 0 <= composer["y"] < 900, composer
            assert composer["y"] + composer["height"] <= 900 + 1, composer
            _no_sideways(page, "tall composer")

            # REDUCED MOTION: the room does not animate, in either preference.
            # The shared reduced-motion rule leaves durations at .00001s
            # rather than 0, so "does not animate" is "nothing a reader could
            # see move": under 20ms, in either property, for every duration
            # declared on it.
            moving = page.evaluate("""() => {
              const seconds = (list) => list.split(',').map((v) => {
                const n = parseFloat(v)
                return Number.isFinite(n) ? (v.trim().endsWith('ms') ? n / 1000 : n) : 0
              })
              const out = []
              for (const el of document.querySelectorAll('.qw-room, .qw-room *')) {
                const s = getComputedStyle(el)
                const all = [...seconds(s.transitionDuration), ...seconds(s.animationDuration)]
                if (all.some((n) => n >= 0.02))
                  out.push([el.className, s.transitionDuration, s.animationDuration])
              }
              return out
            }""")
            assert moving == [], f"the room animates under reduced motion: {moving}"
            assert errors == []
        finally:
            browser.close()


# -- 4. one stable mount each (F27) -------------------------------------------

@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_tools_are_one_mount_each_in_the_tools_slot_and_are_never_reparented(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page, world, conversation)

            # ONE OF EACH, BOTH IN THE `tools` SLOT.
            where = page.evaluate("""() => {
              const nav = document.querySelectorAll('[aria-label="Conversations by recency"]')
              const tools = document.querySelectorAll('[aria-label="Conversation tools"]')
              const slot = document.querySelector('[data-slot="tools"]')
              const main = document.querySelector('main')
              return {
                navs: nav.length, toolbars: tools.length,
                navInSlot: !!slot && slot.contains(nav[0]),
                toolsInSlot: !!slot && slot.contains(tools[0]),
                slotBeforeConversation: !!(slot.compareDocumentPosition(
                  document.querySelector('[data-slot="conversation"]')) & Node.DOCUMENT_POSITION_FOLLOWING),
                toolsBeforeNav: !!(tools[0].compareDocumentPosition(nav[0]) & Node.DOCUMENT_POSITION_FOLLOWING),
                navBeforeMain: !!(nav[0].compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING),
                slots: [...document.querySelectorAll('[data-slot]')].map((el) => el.dataset.slot),
              }
            }""")
            assert where["navs"] == 1 and where["toolbars"] == 1, where
            assert where["navInSlot"] and where["toolsInSlot"], where
            assert where["slotBeforeConversation"], "the tools slot does not precede the conversation slot"
            assert where["toolsBeforeNav"], "the baseline's order of the two is not the drawn one"
            assert where["navBeforeMain"], "the navigation no longer precedes main"
            assert where["slots"] == ["tools", "conversation", "working", "pageControls"], where["slots"]

            # NEVER REPARENTED, AND NEVER REPLACED: the same two elements,
            # with the same parents, through every room (F27). Marked on the
            # nodes themselves, so a remount would lose the mark.
            page.evaluate("""() => {
              for (const sel of ['[aria-label="Conversations by recency"]', '[aria-label="Conversation tools"]'])
                document.querySelector(sel).dataset.witness = 'r5-l'
            }""")
            seen = []
            for mode in ("Chat and panes", "Workspace board", "Single chat"):
                _mode(page, mode)
                seen.append(page.evaluate("""() => {
                  const nav = document.querySelector('[aria-label="Conversations by recency"]')
                  const tools = document.querySelector('[aria-label="Conversation tools"]')
                  return {
                    mark: [nav.dataset.witness, tools.dataset.witness],
                    parents: [nav.parentElement.className, tools.parentElement.className],
                    count: document.querySelectorAll('[aria-label="Conversation tools"]').length,
                  }
                }"""))
            for state, mode in zip(seen, ("panes", "board", "single")):
                assert state["mark"] == ["r5-l", "r5-l"], f"{mode} remounted a tool: {state}"
                assert state["count"] == 1, f"{mode} drew a second set of tools: {state}"
            assert len({tuple(s["parents"]) for s in seen}) == 1, (
                f"a tool was reparented between rooms: {[s['parents'] for s in seen]}")
            assert errors == []
        finally:
            browser.close()


# -- 5. the evidence ----------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("QUIET_ROOM_EVIDENCE"), reason="set QUIET_ROOM_EVIDENCE")
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_evidence(world, engine, theme):
    """Every room, at both viewports, in both themes -- for the return."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            _open(page, world, conversation)
            page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
            for name, mode in (("single", "Single chat"), ("panes", "Chat and panes"),
                               ("board", "Workspace board")):
                _mode(page, mode)
                page.wait_for_timeout(150)
                _shot(page, f"{engine}-{theme}-1440x900-{name}.png")
            _mode(page, "Chat and panes")
            page.set_viewport_size(PHONE)
            page.wait_for_function("() => document.querySelector('.qw-room')?.hasAttribute('data-one')")
            page.wait_for_timeout(150)
            _shot(page, f"{engine}-{theme}-390x844-conversation.png")
            page.get_by_role("button", name="Show tools", exact=True).click()
            page.wait_for_function("() => document.querySelector('.qw-room')?.dataset.showing === 'tools'")
            _shot(page, f"{engine}-{theme}-390x844-tools.png")
            page.get_by_role("button", name="Return to conversation", exact=True).click()
            page.wait_for_function("() => document.querySelector('.qw-room')?.dataset.showing === 'conversation'")
            _shot(page, f"{engine}-{theme}-390x844-return.png")
            page.get_by_role("button", name="Show the workspace", exact=True).click()
            page.wait_for_function("() => document.querySelector('.qw-room')?.dataset.showing === 'workspace'")
            _shot(page, f"{engine}-{theme}-390x844-workspace.png")
        finally:
            browser.close()
