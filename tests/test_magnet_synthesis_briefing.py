"""THE SYNTHESIS FLOOR: content-first, and no keyword matching.

Owner's complaint (`ent-599e68de0893`), confirmed on TEST reading off the
astronomy Magnet `mag-265878e92e5c987c` (plan `MAGNET-EXPERIENCE-PLAN.md`
Part 2, 0a/0b): the no-agent Summary opened with four lines of collection
statistics and nothing else, the last of which reported each row's
collection time as when its material was "written"; and a Perspective
answer was literal substring keyword matching that opened "71 of the 71
records this Magnet has collected mention 'missions', 'slated', 'next' and
'years'. Here is what they say." -- which is the owner's complaint verbatim,
read off `mentis.magnet.perspectives_work._about`.

This file pins what replaced both, over `mentis.magnet.perspectives_work`
directly, the same way `test_magnet_answer_links.py` pins `_row_said`. It
does not touch `answer()`'s record-writing, which `test_magnet_perspectives.py`
already drives end to end.
"""
from __future__ import annotations

import re

from mentis.magnet import perspectives_work as W

FEED_LINK = "https://news.google.com/rss/articles/exampleLink?oc=5"


def feed_text(title, summary, *, published="2011-08-05T07:00:00+00:00",
              publisher="Space", link=FEED_LINK):
    return "\n".join([
        title, "", link, "", summary, "", "--",
        f"Published: {published}", f"Publisher: {publisher}",
        "Search: 'Space missions and astronomy' through Google News search",
        "Entry id (guid): " + link,
    ])


def held(text, at=1312531200.0, obj=1):
    ref = f"adm-{obj:011d}"
    return {"kind": "file", "id": ref, "version": ref,
            "via": "held-source", "conversation": None, "author": None, "at": at,
            "value": {"collection": "col-fea202869d76",
                      "path": f"space-missions/{obj}", "text": text}}


def page(rows, state="ok"):
    return {"state": state,
            "sources": [{"key": "file:col-fea202869d76:", "status": "ok",
                         "source": {"kind": "web-search", "collection": "col-fea202869d76"},
                         "results": rows}]}


_RECORDS_MENTION = re.compile(r"\brecords?\b.*\bmention\b", re.IGNORECASE)


# -- _state_of: content-first, counts closing, not opening -------------------

def test_the_summary_leads_with_named_subjects_not_with_a_count():
    rows = W._rows_of(page([
        held(feed_text("Artemis Programme: NASA's return to the Moon", "Artemis Programme details"), obj=1),
        held(feed_text("Artemis Programme update: new launch window", "Artemis Programme schedule"), obj=2),
        held(feed_text("Roman Space Telescope reaches orbit", "Roman Space Telescope details"), obj=3),
    ]))
    lines = W._state_of(rows, [], {"at": 1795600000.0}, page([]))
    assert not lines[0]["text"].startswith("This Magnet has gathered"), lines[0]["text"]
    assert "Artemis Programme" in " ".join(l["text"] for l in lines) or "Roman Space Telescope" in " ".join(l["text"] for l in lines), \
        lines[0]["text"]


def test_summary_lists_developments_without_collection_statistics_or_raw_links():
    rows = W._rows_of(page([
        held(feed_text("Artemis Programme returns to the Moon", "A new launch window."), obj=1),
        held(feed_text("Roman Space Telescope reaches orbit", "The telescope is operational."), obj=2),
    ]))
    lines = W._state_of(rows, [], {"at": 1795600000.0}, page([]))
    text, rendered, citations = W._compose(lines, rows)
    assert text.startswith("## Developments\n\n- ")
    assert "\n- " in text
    assert "[1]" in text and "[2]" in text
    assert "https://" not in text and "adm-" not in text
    assert "This Magnet" not in text and "From the" not in text
    assert citations[0]["url"] == FEED_LINK


def test_repeated_support_reuses_one_number_and_keeps_reading_order():
    rows = W._rows_of(page([held("First captured statement", obj=2), held("Second statement", obj=1)]))
    first, second = [r["row"]["id"] for r in rows]
    text, lines, notes = W._compose([
        {"text": "First finding.", "cites": [first, second]},
        {"text": "Related finding.", "cites": [first]},
    ], rows)
    assert text == "First finding. [1] [2]\n\nRelated finding. [1]"
    assert [n["item"] for n in notes] == [first, second]


# -- subject extraction: named entities, not a publisher's byline ------------

def test_a_feeds_appended_publisher_name_is_not_read_as_a_subject():
    rows = W._rows_of(page([
        held(feed_text("Juno reaches Jupiter - Example Astronomy Publisher",
                       "Juno reaches Jupiter Example Astronomy Publisher",
                       publisher="Example Astronomy Publisher"), obj=1),
        held(feed_text("Juno sends new data - Example Astronomy Publisher",
                       "Juno sends new data Example Astronomy Publisher",
                       publisher="Example Astronomy Publisher"), obj=2),
    ]))
    lines = W._state_of(rows, [], {"at": 1.0}, page([]))
    assert "Example Astronomy Publisher" not in lines[0]["text"], lines[0]["text"]


# -- _about: phrase/co-occurrence over content, never the provenance footer --

def test_an_answer_with_matches_never_reports_which_words_were_found():
    rows = W._rows_of(page([
        held(feed_text("Artemis Programme: NASA's return to the Moon",
                       "Artemis Programme schedule for upcoming years"), obj=1),
        held(feed_text("Roman Space Telescope, NASA's next great observatory",
                       "Roman Space Telescope launch details"), obj=2),
    ]))
    lines = W._about("What are missions slated for the next 5 years?", rows)
    joined = " ".join(line["text"] for line in lines)
    assert not _RECORDS_MENTION.search(joined), joined


def test_an_answer_with_matches_names_distinct_subjects_each_with_its_own_citation():
    rows = W._rows_of(page([
        held(feed_text("Artemis Programme: NASA's return to the Moon",
                       "Artemis Programme schedule for upcoming years"), obj=1),
        held(feed_text("Roman Space Telescope, NASA's next great observatory",
                       "Roman Space Telescope launch details"), obj=2),
        held(feed_text("Chang'e 7 lunar mission launches next year",
                       "Chang'e 7 lunar mission launch window"), obj=3),
    ]))
    lines = W._about("What are missions slated for the next 5 years?", rows)
    joined = " ".join(line["text"] for line in lines)
    named = [n for n in ("Artemis Programme", "Roman Space Telescope", "Chang'e 7") if n in joined]
    assert len(named) >= 3, joined
    for name in named:
        assert any(name in line["text"] and line["cites"] for line in lines), (name, lines)


def test_the_provenance_footers_echoed_search_query_does_not_count_as_a_match():
    # The footer every feed entry carries restates the Magnet's own configured
    # search (`feeds.py::_entry_body`'s "Search: ..." line). A row whose own
    # headline and material say nothing about the question must not be
    # selected merely because the footer repeats the question's words.
    unrelated = held(feed_text("A calibration note about sensor drift",
                               "Nothing here bears on that at all",
                               link="https://example.org/unrelated"), obj=1)
    rows = W._rows_of(page([unrelated]))
    lines = W._about("What are missions slated for the next 5 years?", rows)
    assert "does not establish an answer" in lines[0]["text"]
    assert lines[0]["cites"] == []


def test_a_question_with_no_matches_still_refuses_in_the_old_words():
    rows = W._rows_of(page([
        held(feed_text("Artemis Programme returns to the Moon", "Artemis details"), obj=1),
    ]))
    said = W._about("What about zygomorphic frobnication of widgets?", rows)[0]["text"]
    assert "does not establish an answer" in said
    assert "Nothing outside" not in said
