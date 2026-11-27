"""WHAT A WRITTEN ANSWER QUOTES, AND WHAT IT POINTS AT.

The owner approved the Magnet and asked for one refinement (ent-0b4f3f69b836):
"The summaries and replies about the information could be formatted a bit
better. Include clickable links and maybe slightly better formatting for
reading."

A Magnet now collects from the web, and every such row has a real address. On
the deployed candidate `20261125-5294531-f4e3ecd4` an answer's statement
quoted a collected news row's whole captured text, which begins with the
headline and then 200 characters of opaque feed permalink, so the owner read

    From the web search: 71 records, most recently "Juno - NASA Science (.gov)
    https://news.google.com/rss/articles/CBMiT0FVX3lxTE45Yy1LbDRvVGs5VXJwS0Fz…
    Juno NASA Science (.gov) -- Published: 2011-08-05T07:00:00+00:00".

This file pins what replaced it, and the three things it must not do:

  * THE ADDRESS IS READ, NEVER BUILT. It is the permalink Part W recorded, in
    the row's own captured bytes, character for character.
  * A ROW THAT IS NOT WEB-SHAPED IS QUOTED EXACTLY AS BEFORE -- a collected
    post, a README, a Git file, a feed entry with no link of its own.
  * NOTHING IS CLAIMED THAT WAS NOT. Only what a row recorded is stated, and a
    row that retained no words of its own says so rather than being quoted.

These are the statement builders of `mentis.magnet.perspectives_work`, driven
directly: `tests/test_magnet_perspectives.py` drives the whole answer path
(grounding, provenance, citations, the append-only history) and is unchanged.
"""
from __future__ import annotations

import pytest

from mentis import api
from mentis.magnet import perspectives_work as W
from mentis.web import _State, fixture

# The exact bytes TEST holds for one row of the owner's Magnet
# `mag-265878e92e5c987c`, read from GET /fluid/api/magnets/<id>/collection on
# release 20261125-5294531-f4e3ecd4. The shape is `sources.feeds._entry_body`'s.
FEED_LINK = ("https://news.google.com/rss/articles/CBMiT0FVX3lxTE45Yy1LbDRvVGs5VXJwS0FzWEZr"
             "Vm0wb3N0VGRNaXNQd1FtZVdDeGVxWjNyejFHY0dmU3BXdmJPVGZlS2ZGSWNzVnNmQnhRVXc?oc=5")
FEED_TEXT = "\n".join([
    "Juno - NASA Science (.gov)",
    "",
    FEED_LINK,
    "",
    "Juno NASA Science (.gov)",
    "",
    "--",
    "Published: 2011-08-05T07:00:00+00:00",
    "Publisher: news.google.com",
    "Results are Google News links; each links to its publisher.",
    "Entry id (guid): " + FEED_LINK,
])
# `sources.webpages._page_body`: the material follows the address with no blank
# line between them.
PAGE_TEXT = "\n".join([
    "Europa Clipper completes its Mars gravity assist",
    "",
    "https://science.nasa.gov/mission/europa-clipper/",
    "The spacecraft passed 550 miles above the Martian surface on 1 March,",
    "trimming its arrival at Jupiter to April 2030.",
])


def held(text, at=1312531200.0):
    return {"kind": "file", "id": "adm-eae23465f170", "version": "adm-eae23465f170",
            "via": "held-source", "conversation": None, "author": None, "at": at,
            "value": {"collection": "col-fea202869d76",
                      "path": "space-missions-and-astronomy-what-launch/a733ec1ec5e51a4b",
                      "text": text}}


def post(text):
    return {"kind": "post", "id": "ent-00000000000f", "version": "ent-00000000000f",
            "conversation": "ent-2865e11386f6", "author": "ent-b20d8e47f196", "via": "home",
            "at": 1795000000.0, "number": 9,
            "value": {"parts": [{"type": "text", "text": text}]}}


def page(rows, kind="web-search", state="ok"):
    return {"state": state,
            "sources": [{"key": "file:col-fea202869d76:", "status": "ok",
                         "source": {"kind": kind, "collection": "col-fea202869d76"},
                         "results": rows}]}


# -- the header, read back out of the row's own bytes --------------------------

def test_a_feed_entrys_recorded_header_is_read_back_exactly_as_it_was_written():
    headline, link, body = W._row_said(held(FEED_TEXT))
    assert headline == "Juno - NASA Science (.gov)"
    assert link == FEED_LINK, "the recorded permalink, character for character"
    assert body == "Juno NASA Science (.gov)", \
        "the entry's own words, without the `--` trailer the feed recorded about it"


def test_a_web_pages_header_gives_the_same_three_things_with_no_blank_line_to_skip():
    headline, link, body = W._row_said(held(PAGE_TEXT))
    assert headline == "Europa Clipper completes its Mars gravity assist"
    assert link == "https://science.nasa.gov/mission/europa-clipper/"
    assert body.startswith("The spacecraft passed 550 miles")
    assert body.endswith("April 2030.")


def test_a_page_with_no_title_of_its_own_offers_no_headline_only_its_address():
    url = "https://example.org/launch-report"
    headline, link, body = W._row_said(held("\n".join([url, "", url, "", "The report."])))
    assert headline is None, "the address is already the link; it is not said twice"
    assert link == url
    assert body == "The report."


def test_nothing_that_is_not_web_shaped_is_touched():
    for text in ["# Disposable audit folder\n\nNotes kept here.",
                 "A newly arrived record about calibration drift.",
                 "Title\n\nA feed entry that recorded no link of its own.",
                 "Title\nhttps://example.org/x\nno blank line above",
                 ""]:
        for row in (held(text), post(text)):
            assert W._row_said(row) == (None, None, text), text


def test_no_address_is_read_from_a_line_that_is_not_purely_an_https_address():
    for third in ["http://example.org/x", "ftp://example.org/x", "javascript:alert(1)",
                  "see https://example.org/x", "https://example.org/x and more", "  "]:
        _, link, _ = W._row_said(held("\n".join(["Headline", "", third, "", "Body"])))
        assert link is None, third


# -- what a statement says -----------------------------------------------------

def test_the_evolving_summary_names_an_article_with_openable_numbered_provenance():
    rows = W._rows_of(page([held(FEED_TEXT)]))
    text, lines, notes = W._compose(W._state_of(rows, [], {}, page([])), rows)
    assert "Juno - NASA Science (.gov)" in text
    assert "[1]" in text and "https://" not in text
    assert notes == [{"n": 1, "item": "adm-eae23465f170",
                      "title": "Juno - NASA Science (.gov)", "url": FEED_LINK}]
    assert "Published:" not in text
    assert lines[-1]["cites"] == ["adm-eae23465f170"]


def test_a_new_row_is_prioritized_without_announcing_collection_mechanics():
    first = held(FEED_TEXT)
    new = post("A newly arrived record about calibration drift.")
    rows = W._rows_of(page([first, new]))
    lines = W._state_of(rows, [new["id"]], {}, page([]))
    assert "calibration drift" in lines[1]["text"]
    assert lines[1]["cites"] == [new["id"]]
    assert "New, from the" not in lines[1]["text"]


def test_a_feed_that_repeats_its_own_title_as_its_summary_does_not_say_it_twice():
    rows = W._rows_of(page([held(FEED_TEXT)]))
    text, _, _ = W._compose(W._state_of(rows, [], {}, page([])), rows)
    assert text.count("Juno") == 1
    rows = W._rows_of(page([held(PAGE_TEXT)]))
    text, _, _ = W._compose(W._state_of(rows, [], {}, page([])), rows)
    assert "The spacecraft passed 550 miles" in text


def test_a_row_that_retained_only_a_headline_is_named_without_an_empty_quote():
    bare = held("Only a headline\n\nhttps://example.org/a\n\n--\nPublished: 2026-01-01")
    rows = W._rows_of(page([bare]))
    text, _, notes = W._compose(W._state_of(rows, [], {}, page([])), rows)
    assert "Only a headline" in text and "https://" not in text
    assert notes[0]["url"] == "https://example.org/a"


def test_a_row_without_text_does_not_claim_substantive_content():
    rows = W._rows_of(page([held("")]))
    assert "No readable text was retained" in W._state_of(rows, [], {}, page([]))[1]["text"]


def test_an_answered_question_names_the_article_and_maps_its_exact_recorded_link():
    rows = W._rows_of(page([held(PAGE_TEXT)]))
    text, _, notes = W._compose(W._about("What happened at Mars?", rows), rows)
    assert "Europa Clipper completes its Mars gravity assist" in text
    assert "The spacecraft passed 550 miles" in text
    assert "[1]" in text and "https://" not in text
    assert notes[0]["url"] == "https://science.nasa.gov/mission/europa-clipper/"


def test_an_answer_over_rows_that_are_not_web_shaped_reads_exactly_as_it_did():
    # The wording `test_magnet_perspectives.py` pins, over the row it pins it on.
    rows = W._rows_of(page([post("A newly arrived record about calibration drift.")],
                           kind="conversation"))
    said = [line["text"] for line in
            W._about("What do the records say about calibration drift?", rows)]
    joined = " ".join(said)
    assert "A newly arrived record about calibration drift." in joined
    assert "calibration" in joined and "drift" in joined
    assert "https://" not in joined, "nothing invents an address for a row that has none"
    assert joined.count("·") == 0, "and nothing is pointed at that recorded nothing to point at"


def test_a_question_the_collection_cannot_answer_still_refuses_to_answer_it():
    rows = W._rows_of(page([held(FEED_TEXT)]))
    said = W._about("What about zygomorphic frobnication of widgets?", rows)[0]["text"]
    assert "does not establish an answer" in said
    assert "Nothing outside" not in said
    assert said and not said.startswith("From the")


# -- what the batch itself says about where a row came from (ent-49620b753f71) -

# A Magnet's configured source always names a held-file collection the same
# way (`kind: "file"`, a `collection` id) whatever connector actually
# acquired its bytes -- a web search, a feed or an ordinary file on disk.
# `page()` above fakes the configured kind directly as "web-search" to pin
# the wording; these tests drive the real seam, a declared collection's own
# connector read back through `mentis.sources.declaration`.

@pytest.fixture
def brain(tmp_path):
    fixture.build(str(tmp_path / "brain"))
    return _State(str(tmp_path / "brain"))


def _configured_file_source(collection, rows):
    return {"sources": [{"key": f"file:{collection}:", "status": "ok",
                         "source": {"kind": "file", "collection": collection},
                         "results": rows}]}


def test_a_file_source_over_a_declared_web_search_collection_is_named_accurately(brain):
    out = api.sources(brain.corpus).declare(name="Space news", connector="web-search",
                                            options={"queries": ["space missions"]})
    rows = W._rows_of(_configured_file_source(out["collection"], [held(FEED_TEXT)]), brain.corpus)
    assert rows[0]["words"] == "web search", \
        "the collection's own connector is named, not the Magnet's generic 'file' source kind"


def test_an_ordinary_file_source_still_reads_as_a_held_file(brain):
    out = api.sources(brain.corpus).declare(name="Notes", connector="filesystem")
    rows = W._rows_of(_configured_file_source(out["collection"], [held(PAGE_TEXT)]), brain.corpus)
    assert rows[0]["words"] == "held file", "an ordinary file collection stays honestly named"


def test_an_undeclared_collection_falls_back_to_held_file(brain):
    rows = W._rows_of(_configured_file_source("col-missing111", [held(PAGE_TEXT)]), brain.corpus)
    assert rows[0]["words"] == "held file"


def test_with_no_corpus_given_the_configured_kind_is_used_exactly_as_before():
    rows = W._rows_of(_configured_file_source("col-missing111", [held(PAGE_TEXT)]))
    assert rows[0]["words"] == "held file"
