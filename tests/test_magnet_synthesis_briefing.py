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
    assert "Artemis Programme" in lines[0]["text"] or "Roman Space Telescope" in lines[0]["text"], \
        lines[0]["text"]


def test_the_summary_closes_with_exactly_one_line_that_states_a_record_count():
    rows = W._rows_of(page([
        held(feed_text("Artemis Programme returns to the Moon", "Artemis Programme details"), obj=1),
        held(feed_text("Roman Space Telescope reaches orbit", "Roman Space Telescope details"), obj=2),
    ]))
    lines = W._state_of(rows, [], {"at": 1795600000.0}, page([]))
    counters = [i for i, line in enumerate(lines) if line["text"].startswith("This Magnet has gathered")]
    assert counters == [len(lines) - 1], (counters, len(lines), [l["text"] for l in lines])


def test_the_summary_reads_the_feeds_own_published_date_not_the_collection_time():
    # The collection time is far in the future of the material's own recorded
    # publication date -- the bug the owner's plan names (feeds.py:575).
    row = held(feed_text("Juno reaches Jupiter", "Juno mission details",
                         published="2011-08-05T07:00:00+00:00"),
               at=1795600000.0, obj=1)  # `at` -> collected 2026, not 2011
    rows = W._rows_of(page([row]))
    lines = W._state_of(rows, [], {"at": 1795600000.0}, page([]))
    written = next(line["text"] for line in lines if line["text"].startswith("The material it holds"))
    assert "2011-08-05" in written, written
    assert "2026" not in written, written


def test_a_row_with_no_published_line_contributes_no_fabricated_written_date():
    # A webpage row carries no `Published:` line; nothing is inferred from its
    # collection time, which is a different thing.
    row = {"kind": "file", "id": "adm-000000000001", "version": "adm-000000000001",
           "via": "held-source", "conversation": None, "author": None, "at": 1795600000.0,
           "value": {"collection": "col-x", "path": "p",
                     "text": "Europa Clipper\n\nhttps://example.org/europa\nIt flew past Mars."}}
    rows = W._rows_of(page([row]))
    lines = W._state_of(rows, [], {"at": 1795600000.0}, page([]))
    assert not any(line["text"].startswith("The material it holds") for line in lines)


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
    assert lines[0]["text"].startswith("None of the"), lines[0]["text"]
    assert lines[0]["cites"] == []


def test_a_question_with_no_matches_still_refuses_in_the_old_words():
    rows = W._rows_of(page([
        held(feed_text("Artemis Programme returns to the Moon", "Artemis details"), obj=1),
    ]))
    said = W._about("What about zygomorphic frobnication of widgets?", rows)[0]["text"]
    assert "None of the" in said and "records this Magnet has collected mention" in said
    assert "Nothing outside this collection was read" in said
