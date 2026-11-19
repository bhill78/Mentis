"""THE GOVERNANCE CREATION FORM (`R2Create`), where it is still hosted.

This file held eighteen browser tests of the creation form as QUIET CHAT
hosted it (`R2Forms.tsx`'s `quiet` variant under `quiet2/brain/BrainPages.tsx`'s
`NewRecord`). Quiet Chat no longer hosts that form: the owner approved one
compact Brain record editor for making and revising (2026-11-18,
`apps/fluid-web/src/quiet2/brain/author/`), opened as a modal from "New" in
the Brain browser. The creation page, its Kind select, its three steps, its
live preview and establishing at creation are gone from Quiet Chat.

FLUID IS UNCHANGED and still hosts `R2Create` without the `quiet` variant;
the one test that drives that host stays here.

WHERE EACH OF THE EIGHTEEN WENT. "author::" is
`tests/test_quiet_brain_author_browser.py`; "unit::" is
`apps/fluid-web/tests/brain_author_unit.ts`.

| old test (this file)                                   | now                                                                                  |
|--------------------------------------------------------|--------------------------------------------------------------------------------------|
| test_dynamic_kind_fields_and_widgets                   | covered: author::test_a_discipline_starts_small_and_its_advanced_parts_are_reachable (declared line/paragraph/list rows/capabilities checkboxes; revise side: author::test_revising_a_discipline_uses_rows_and_a_checklist). Its "Initial status" default: removed by the approved design: there is no status choice, recording always writes a proposal. |
| test_generic_persona_instruction_defaults_and_api_bodies_unchanged | covered: author::test_a_persona_is_recorded_as_a_proposal (`propose: true`, `establish: false`), author::test_the_instructions_box_opens_the_same_editor_and_does_not_establish (`establish: false`), author::test_new_lists_the_seven_kinds_and_a_rule_is_recorded_from_one_field; every Kind in unit:: section 5. `attributed_to`: author::test_what_is_recorded_is_attributed_to_the_resolved_participant. |
| test_create_cite_establish_place_ordering              | create -> cite -> place order: covered by author::test_a_rule_with_evidence_and_a_placement_is_three_acts_in_order_and_retries and unit:: section 5. The establish step: removed by the approved design: nothing is established at creation; establishing is a separate act on the record (author::test_open_the_record_after_recording_and_establish_is_a_separate_act). |
| test_failed_citation_retries_original_identity         | ported: author::test_a_failed_citation_is_retried_on_the_same_record_and_nothing_is_made_twice |
| test_failed_establishment_retries_original_identity    | removed by the approved design: creation never establishes, so there is no establishment to fail or retry. |
| test_failed_placement_retries_original_identity        | covered: author::test_a_rule_with_evidence_and_a_placement_is_three_acts_in_order_and_retries |
| test_quiet_guard_one_question_keeps_state_resets_only_on_discard | Close/Escape/outside press, one question, draft kept, cleared only on Discard: covered by author::test_typed_work_is_never_dropped_without_a_question. No discard offered once the record exists: ported into author::test_a_failed_citation_is_retried_on_the_same_record_and_nothing_is_made_twice. The Kind-change guard: removed by the approved design: there is no Kind select, each Kind is opened by name. |
| test_pending_guard_blocks_background_escape_and_resubmit | ported: author::test_while_recording_nothing_else_can_be_started |
| test_attribution_is_the_resolved_participant           | ported: author::test_what_is_recorded_is_attributed_to_the_resolved_participant |
| test_no_participant_blocks_write_before_any_post       | ported: author::test_no_participant_blocks_the_write_before_any_post (with this file's `world_no_owner` fixture, moved there) |
| test_failed_citation_edited_refs_show_truthful_progress_then_restore_keeps_identity | identity kept, one create, truthful "recorded as a proposal, but ... was not": ported into author::test_a_failed_citation_is_retried_on_the_same_record_and_nothing_is_made_twice. Editing the references after the failure: removed by the approved design: once a record exists its draft is inert and a retry finishes exactly the acts decided at recording (asserted there and in the three-acts test). |
| test_leave_guard_keyboard_decides_once_and_keeps_every_value | ported: author::test_the_discard_question_is_decided_once_from_the_keyboard. The step and "Initial status" it also checked: removed by the approved design (no steps, no status choice). |
| test_default_non_quiet_host_unchanged                  | KEPT, below: it drives Fluid's host (`/fluid?gov=1&s=rules`), which is unchanged. |
| test_compact_rendering_normal_and_narrow               | the step bar it looked for: removed by the approved design (no steps). Compact at a normal width and usable at a phone width: covered by author::test_new_lists_the_seven_kinds_and_a_rule_is_recorded_from_one_field and author::test_phone_width_is_a_sheet_with_no_sideways_scrolling. |
| test_each_shaped_kind_opens_its_own_layout_with_a_live_preview | removed by the approved design: no per-Kind workspace and no live preview; every Kind opens the same small editor (first view per Kind: unit:: section 2; on screen: the author:: tests of each Kind). |
| test_workflow_sequence_adds_reorders_and_removes_with_its_own_question | add, reorder (button and keyboard), remove: covered by author::test_a_workflow_grows_one_activity_at_a_time; an activity's own participant kept through a move: ported into author::test_every_kind_and_structure_nobody_wrote_in_yet_is_a_draft_to_protect. The remove question and the preview beside it: removed by the approved design: Remove acts at once and offers Undo. |
| test_shaped_draft_protection_keeps_part_written_activities_and_list_rows | ported: author::test_every_kind_and_structure_nobody_wrote_in_yet_is_a_draft_to_protect (all seven Kinds, an empty added activity, a part-written one, an empty added list row); the decision purely: unit:: section 8 (`dirty`). |
| test_shaped_layout_uses_the_width_and_falls_back_to_one_column | removed by the approved design: no two-column writing/preview layout. Narrow width: author::test_phone_width_is_a_sheet_with_no_sideways_scrolling. |

Build apps/fluid-web first (`npm ci && npm run build` under apps/fluid-web),
then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import re

import pytest

from tests._loop import world, post, get  # noqa: F401
from tests.conftest import owner_headers

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

ENGINE = "chrome"  # the owner's own browser; no other engine here
APPEARS_MS = 15000


@pytest.fixture
def me_id(world):
    """The participant the page's `useMe()` will actually resolve to, by
    the same route it calls (`/api/participants?limit=1`)."""
    rows = get(world, "/api/participants?limit=1")["participants"]
    assert rows, "the fixture Brain must hold at least one participant"
    return rows[0]["participant"]


@pytest.fixture
def conv(world):
    return post(world, "/api/conversations", {"name": "Governance creation browser"})["conversation"]


def _page(playwright, width=1440, height=1000):
    browser = playwright.chromium.launch(channel=ENGINE)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return browser, page, errors


def _log_in_as_owner(page, world):
    """The browser is the owner through the suite's one session (see
    `test_quiet_brain_author_browser._open`: a login per browser test evicts
    that session from the credential's 64 during a full run)."""
    page.context.set_extra_http_headers(owner_headers())


def _dialog(page):
    return page.locator(".r2-form")


def _field(page, key):
    return _dialog(page).get_by_label(key, exact=True)


def test_default_non_quiet_host_unchanged(world, conv, me_id):
    """GovPage hosts `R2Create`, `quiet` unset: no step bar, no guard --
    cancelling with unsaved text goes at once, exactly as before the Quiet
    work, and exactly as before Quiet Chat stopped hosting the form."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _log_in_as_owner(page, world)
            page.goto(world["base"] + "/fluid?gov=1&s=rules")
            page.get_by_role("button", name=re.compile("Record a rule or decision")).click()
            page.locator(".fg-create .r2-form").wait_for(timeout=APPEARS_MS)
            assert page.locator(".r2-create-steps").count() == 0
            # the new Quiet editor is not what Fluid opens
            assert page.locator("[data-author-modal], [data-author]").count() == 0
            _field(page, "text").fill("Unsaved, non-Quiet.")
            _dialog(page).get_by_role("button", name="Close creation").click()
            # no Quiet guard exists on this host at all
            assert page.locator(".r2-create-guard").count() == 0
            assert not errors, errors
        finally:
            browser.close()
