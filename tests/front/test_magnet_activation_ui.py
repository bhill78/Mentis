"""A Magnet's manual activation from Fluid itself: real Chromium on the real build, the real Rust front and
real Python, on a disposable copy of BRAIN-SEED. `docs/magnets/M1-contract.md`, "The client's controls".

A press is a press of the drawn button, and what it came to is read from the page and from the record.
Live because it needs Chromium: run it with `-m live`, `MENTIS_R1_FIXTURES` and `MENTIS_UNDER_TEST`.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.front.pair import CLIENT, SPARE_PORTS, Pair, advance, ask, post_json, rows
from tools.r1 import common

pytestmark = pytest.mark.live

PORT = list(SPARE_PORTS)[0]
SIDE = common.REPO / "crates" / "mentis-rules" / "tests" / "support" / "python_side.py"
DIST = common.REPO / "apps" / "fluid-web" / "dist"
SLOW = 30_000


def conversation_of(brain, cid):
    return json.loads(rows(brain, "SELECT body FROM entry WHERE id = ?", cid)[0][0])


def posts_in(brain, cid):
    """The Turns homed in a Conversation, oldest first."""
    return [r[0] for r in rows(brain, "SELECT e.id FROM entry e JOIN entry l ON l.link_from = e.id "
                                      "WHERE l.link_relation = 'in-conversation' AND l.link_to = ? "
                                      "AND e.def_name = 'contribution' ORDER BY e.seq", cid)]


def extracted(brain, magnet):
    found = rows(brain, "SELECT conversation, turn, detail FROM operational WHERE act = 'magnet-extracted'")
    return [(c, t) for c, t, d in found if json.loads(d)["magnet"] == magnet]


def definition(brain, magnet):
    return json.loads((brain / "presentation" / "magnets" / f"{magnet}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pair(brain_seed, tmp_path_factory):
    brain = tmp_path_factory.mktemp("activation-ui") / "brain"
    shutil.copytree(brain_seed, brain)
    done = subprocess.run([str(common.venv_python()), str(SIDE), "change", str(brain)],
                          cwd=common.REPO, capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONPATH": str(common.REPO),
                               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0, done.stderr
    assert (DIST / "index.html").exists(), "build apps/fluid-web first"
    with Pair(brain, port=PORT, dist=DIST) as running:
        yield running


@pytest.fixture(scope="module")
def source(pair):
    """A Conversation with posts: what Magnets here read."""
    return rows(pair.brain, "SELECT l.link_to FROM entry l WHERE l.link_relation = 'in-conversation' "
                            "GROUP BY l.link_to ORDER BY COUNT(*) DESC")[0][0]


@pytest.fixture()
def page(pair):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1500, "height": 950})
        page = context.new_page()
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        yield page
        browser.close()
    assert page.errors == []


def open_conversation(page, pair, cid):
    page.goto(f"{pair.url}/fluid?c={cid}", wait_until="load", timeout=SLOW)
    expect(page.locator(".mg-zone, [data-conversation], main").first).to_be_visible(timeout=SLOW)


def from_palette(page, words):
    page.keyboard.press("Control+k")
    box = page.locator("input:visible").last
    box.fill(words)
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")


def made_in_ui(page, pair, source) -> str:
    """A Magnet made by the palette's New magnet, answered with the id the server gave it."""
    open_conversation(page, pair, source)
    page.wait_for_timeout(1500)
    with page.expect_response(lambda r: r.url.endswith(f"/arrangements/{source}/magnets") and r.request.method == "POST",
                              timeout=SLOW) as made:
        from_palette(page, "New magnet")
    assert made.value.status in (200, 201), made.value.text()
    return made.value.json()["magnet"]["id"]


def opened(page, magnet):
    zone = page.locator(f'.mg-zone[data-magnet="{magnet}"]')
    expect(zone).to_be_visible(timeout=SLOW)
    if not zone.locator(".mg-activation").count():
        zone.locator(".mg-disc").first.click(force=True)
    expect(zone.locator(".mg-activation")).to_be_visible(timeout=SLOW)
    return zone


def phase(zone, is_it):
    expect(zone.locator(".mg-activation")).to_have_attribute("data-phase", is_it, timeout=SLOW)


def test_a_magnet_made_in_the_ui_runs_by_a_press_and_replays_under_its_key(page, pair, source):
    brain = pair.brain
    magnet = made_in_ui(page, pair, source)
    made = definition(brain, magnet)
    assert made["activation"] == {"mode": "manual"} and made["processing"] == {"operations": [{"op": "extract"}]}
    for absent in ("ai", "outputs", "destinations", "conversation"):
        assert absent not in made, absent
    assert extracted(brain, magnet) == [], "nothing runs until it is pressed"

    zone = opened(page, magnet)
    bodies = []
    page.on("request", lambda r: bodies.append(json.loads(r.post_data)) if r.url.endswith(f"/{magnet}/activate") else None)
    with page.expect_response(lambda r: r.url.endswith(f"/{magnet}/activate"), timeout=SLOW) as first:
        zone.locator(".mg-activate").click()
    assert first.value.status == 201, first.value.text()
    answer = first.value.json()
    phase(zone, "complete")
    assert sorted(bodies[0]) == ["author", "op"], "exactly what the door takes"
    own = answer["conversation"]
    assert own != source and answer["conversation_created"] is True
    assert extracted(brain, magnet) == [(own, answer["post"])]
    name = conversation_of(brain, own)["name"]
    source_name = conversation_of(brain, source)["name"]
    assert name == f"{source_name} (Magnet)", "under its name, not Unnamed"
    assert definition(brain, magnet)["conversation"] == own

    # The answer to a second press is lost on its way back: it was recorded, and nobody here knows.
    posted = len(posts_in(brain, own))
    def lose_it(route):
        route.fetch()
        route.abort()
    page.route(f"**/{magnet}/activate", lose_it)
    zone.locator(".mg-activate").click()
    phase(zone, "unknown")
    expect(zone.locator(".mg-activate")).to_have_text("Ask again (same key)")
    assert len(posts_in(brain, own)) == posted + 1
    page.unroute(f"**/{magnet}/activate")
    lost_key = bodies[-1]
    assert lost_key["op"] != bodies[0]["op"], "the second press is a new key"

    # Even past a reload the key waits, and asking again replays what it recorded.
    page.reload(wait_until="load")
    zone = opened(page, magnet)
    phase(zone, "unknown")
    before = advance(brain)
    with page.expect_request(lambda r: r.url.endswith(f"/{magnet}/activate"), timeout=SLOW) as asked, \
            page.expect_response(lambda r: r.url.endswith(f"/{magnet}/activate"), timeout=SLOW) as again:
        zone.locator(".mg-activate").click()
    assert json.loads(asked.value.post_data) == lost_key, "only ever under the key it was lost under"
    assert again.value.status == 200, again.value.text()
    assert again.value.json()["replayed"] is True
    assert again.value.json()["post"] == extracted(brain, magnet)[-1][1]
    phase(zone, "complete")
    expect(zone.locator(".mg-activation [role=status]")).to_contain_text("Already recorded under this key")
    assert advance(brain) == before, "a replay writes nothing"
    assert len(posts_in(brain, own)) == posted + 1

    # The way to its result: its own Conversation, under its name, with the page in it.
    zone.get_by_role("button", name="Read the result").click()
    page.wait_for_url(f"**c={own}**", timeout=SLOW)
    expect(page.get_by_text("Extracted one page from this Magnet").first).to_be_visible(timeout=SLOW)
    expect(page.get_by_text(name).first).to_be_visible(timeout=SLOW)


def old_magnet(pair, source, op) -> str:
    """A Magnet as one was saved before this: no activation and no processing."""
    place = f"/fluid/api/arrangements/{source}"
    new = {"base": {"format": "mentis.fluid-arrangement", "version": 3,
                    "tree": {"type": "zone", "id": "stage", "show": "objects"}}}
    base = new if ask(pair.port, "GET", place).json.get("saved") is None else {}
    got = post_json(pair.port, f"{place}/magnets", {
        "op": op, "wideFallback": "launcher",
        "seed": {"sources": [{"kind": "conversation", "conversation": source}], "selection": {},
                 "collection": {"mode": "one-time"}, "synthesis": {"mode": "manual"},
                 "notifications": {"newItems": False, "changes": False, "failures": False},
                 "presentation": {"renderer": "list"}},
        "attach": {"zone": {"type": "zone", "show": "magnet", "name": "Saved before", "level": "icon"}, **base}}, CLIENT)
    assert got.status < 300, got
    return got.json["magnet"]["id"]


def test_an_unsupported_definition_says_why_writes_nothing_and_is_set_up_only_by_a_press(page, pair, source):
    brain = pair.brain
    magnet = old_magnet(pair, source, "ui-old-1")
    kept = definition(brain, magnet)
    open_conversation(page, pair, source)

    # Disabled in its T2, with the reason, and from the same registry; set-up and its Conversation beside it.
    disc = page.locator(f'.mg-zone[data-magnet="{magnet}"] .mg-disc').first
    expect(disc).to_be_visible(timeout=SLOW)
    disc.click(button="right", force=True)
    items = page.locator("[role=menuitem]:visible")
    item = items.filter(has_text="Activate").first
    expect(item).to_have_attribute("aria-disabled", "true", timeout=SLOW)
    words = "this build activates a Magnet only by hand: its activation must be manual"
    assert words in (item.get_attribute("title") or "") + item.inner_text()
    expect(items.filter(has_text="Set up manual activation")).to_have_count(1)
    expect(items.filter(has_text="Open its own Conversation")).to_have_count(1)
    page.keyboard.press("Escape")

    zone = opened(page, magnet)
    button = zone.locator(".mg-activate")
    expect(button).to_be_disabled()
    expect(zone.locator(".mg-activation")).to_contain_text(words)
    before = advance(brain)
    button.click(force=True)
    page.wait_for_timeout(500)
    assert advance(brain) == before and extracted(brain, magnet) == []
    assert definition(brain, magnet) == kept, "opening and pressing rewrites nothing"

    # Only this press changes it, on the same id, adding only what it lacked.
    zone.get_by_role("button", name="Set up manual activation").click()
    expect(button).to_be_enabled(timeout=SLOW)
    now = definition(brain, magnet)
    assert {k: v for k, v in now.items() if k not in ("activation", "processing")} == kept
    assert now["activation"] == {"mode": "manual"} and now["processing"] == {"operations": [{"op": "extract"}]}
    assert advance(brain) == before, "setting it up writes nothing to the record"

    # A server that has since been told otherwise refuses, in its words, and writes nothing.
    changed = post_json(pair.port, f"/fluid/api/arrangements/{source}/magnets/{magnet}/reconfigure",
                        {"change": {"synthesis": {"mode": "on-new-information"}}, "op": "ui-old-2"}, CLIENT)
    assert changed.status == 200, changed
    with page.expect_response(lambda r: r.url.endswith(f"/{magnet}/activate"), timeout=SLOW) as refused:
        button.click()
    assert refused.value.status == 422
    phase(zone, "refused")
    expect(zone.locator(".mg-activation [role=status]")).to_have_text(refused.value.json()["reason"]["message"])
    assert advance(brain) == before and extracted(brain, magnet) == []


def test_its_own_conversation_is_made_only_on_that_press_and_is_not_its_source(page, pair, source):
    brain = pair.brain
    magnet = old_magnet(pair, source, "ui-old-3")
    open_conversation(page, pair, source)
    zone = opened(page, magnet)
    assert "conversation" not in definition(brain, magnet)
    with page.expect_response(lambda r: r.url.endswith(f"/{magnet}/conversation"), timeout=SLOW) as asked:
        zone.get_by_role("button", name="Its Conversation").click()
    assert asked.value.status == 201, asked.value.text()
    own = asked.value.json()["conversation"]
    assert own != source
    page.wait_for_url(f"**c={own}**", timeout=SLOW)
    assert conversation_of(brain, own)["name"] == f'{conversation_of(brain, source)["name"]} (Magnet)'
    assert definition(brain, magnet)["conversation"] == own
    again = post_json(pair.port, f"/fluid/api/magnets/{magnet}/conversation",
                      {"author": rows(brain, "SELECT id FROM entry WHERE def_name='participant' AND id LIKE 'ent-%'")[0][0]},
                      CLIENT)
    assert again.json["conversation"] == own and again.json["created"] is False, "and it is the one"


def test_the_editor_sets_every_new_facet_and_what_is_unset_stays_absent(page, pair, source):
    brain = pair.brain
    magnet = old_magnet(pair, source, "ui-old-4")
    kept = definition(brain, magnet)
    open_conversation(page, pair, source)
    zone = opened(page, magnet)
    zone.get_by_role("tab", name="Configure").click()
    editor = zone.locator(".mg-edit")
    save = editor.locator(".mg-save")
    for part in ("activation", "processing", "ai", "outputs", "destinations", "theme"):
        expect(editor.locator(f'[data-part="{part}"]')).to_be_visible()
    expect(save).to_be_disabled()

    # Asked and taken back before saving, nothing is sent.
    ai = editor.locator('[data-part="ai"] select')
    ai.select_option("agent")
    expect(editor.locator('[data-part="ai"]')).to_contain_text("AI participation (agent) is kept but not run")
    assert "agent: kept, not run" in ai.locator("option:checked").inner_text()
    ai.select_option("")
    expect(save).to_be_disabled()

    # Saved, then taken out again: exactly what it was.
    editor.locator('[data-part="theme"] input[type=radio]').nth(3).check()
    editor.locator('[data-part="outputs"] input[type=checkbox]').first.check()
    ai.select_option("runtime")
    save.click()
    expect(zone.locator(".mg-edit")).to_have_count(0, timeout=SLOW)
    saved = definition(brain, magnet)
    assert saved["presentation"]["theme"] == "glass" and saved["outputs"] == ["findings"] and saved["ai"] == {"mode": "runtime"}
    assert "activation" not in saved and "destinations" not in saved and "processing" not in saved

    zone.get_by_role("tab", name="Configure").click()
    editor = zone.locator(".mg-edit")
    editor.locator('[data-part="theme"] input[type=radio]').nth(0).check()
    editor.locator('[data-part="outputs"] input[type=checkbox]').first.uncheck()
    editor.locator('[data-part="ai"] select').select_option("")
    editor.locator(".mg-save").click()
    expect(zone.locator(".mg-edit")).to_have_count(0, timeout=SLOW)
    assert definition(brain, magnet) == kept, "a round trip keeps every unset field absent"
