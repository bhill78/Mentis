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

from mentis.magnet import perspectives_work as W

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

def test_the_evolving_summary_names_a_collected_article_and_points_at_it():
    rows = W._rows_of(page([held(FEED_TEXT)]))
    lines = W._state_of(rows, [], {"at": 1795600000.0}, page([held(FEED_TEXT)]))
    said = [line["text"] for line in lines]
    one = next(t for t in said if t.startswith("From the web search:"))
    assert "“Juno - NASA Science (.gov)”" in one, "it names the article, not a held-file key"
    assert FEED_LINK in one, "and carries the address the reader follows"
    assert "a733ec1ec5e51a4b" not in " ".join(said), "the object key reaches no statement"
    assert "Published:" not in " ".join(said), "nor does the feed's recorded trailer"
    assert not one.endswith("."), "no full stop a reader cannot tell from the address"
    # Every statement still names the rows it was written from.
    assert all(isinstance(line["cites"], list) for line in lines)
    assert any(line["cites"] == ["adm-eae23465f170"] for line in lines)


def test_a_new_row_is_announced_with_its_headline_and_its_address():
    rows = W._rows_of(page([held(FEED_TEXT)]))
    lines = W._state_of(rows, ["adm-eae23465f170"], {"at": 1795600000.0},
                        page([held(FEED_TEXT)]))
    fresh = next(line for line in lines if line["text"].startswith("New, from the"))
    assert "“Juno - NASA Science (.gov)”" in fresh["text"]
    assert FEED_LINK in fresh["text"]
    assert fresh["cites"] == ["adm-eae23465f170"]


def test_a_feed_that_repeats_its_own_title_as_its_summary_does_not_say_it_twice():
    # The owner's Magnet is full of these: the entry's summary IS its headline.
    rows = W._rows_of(page([held(FEED_TEXT)]))
    fresh = next(line["text"] for line in
                 W._state_of(rows, ["adm-eae23465f170"], {"at": 1.0}, page([held(FEED_TEXT)]))
                 if line["text"].startswith("New, from the"))
    assert fresh.count("Juno") == 1, fresh
    # A row whose material is its own says it, quoted.
    other = W._rows_of(page([held(PAGE_TEXT)]))
    says = next(line["text"] for line in
                W._state_of(other, ["adm-eae23465f170"], {"at": 1.0}, page([held(PAGE_TEXT)]))
                if line["text"].startswith("New, from the"))
    assert "“The spacecraft passed 550 miles" in says, says


def test_a_row_that_retained_no_words_of_its_own_is_named_and_not_quoted():
    bare = held("\n".join(["Only a headline", "", "https://example.org/a", "", "--",
                           "Published: 2026-01-01"]))
    rows = W._rows_of(page([bare]))
    said = [line["text"] for line in W._state_of(rows, [bare["id"]], {"at": 1.0}, page([bare]))]
    joined = " ".join(said)
    assert "“Only a headline”" in joined
    assert "https://example.org/a" in joined
    assert "“”" not in joined, "nothing is shown as an empty quotation"


def test_a_source_whose_rows_retained_nothing_at_all_still_says_so():
    empty = held("")
    rows = W._rows_of(page([empty]))
    one = next(line["text"] for line in W._state_of(rows, [], {"at": 1.0}, page([empty]))
               if line["text"].startswith("From the web search:"))
    assert one.endswith("none of which retained any words.")


def test_an_answered_question_names_the_article_it_read_and_points_at_it():
    rows = W._rows_of(page([held(PAGE_TEXT)]))
    said = [line["text"] for line in W._about("What happened at Mars?", rows)]
    quoted = next(t for t in said if t.startswith("From the web search"))
    assert "on “mars”" in quoted, quoted
    assert "“Europa Clipper completes its Mars gravity assist”" in quoted
    assert "https://science.nasa.gov/mission/europa-clipper/" in quoted
    assert "“The spacecraft passed 550 miles" in quoted


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
    assert "None of the" in said and "records this Magnet has collected mention" in said
    assert "Nothing outside this collection was read" in said
    assert said and not said.startswith("From the")
