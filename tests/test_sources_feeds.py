"""THE FEED CONNECTORS: `rss-atom` and `web-search` (Part W, amendment
adm-c38044ee5157 §2).

OFFLINE BY DEFAULT. `fetch.get` -- the one bounded GET, whose own bounds are
proved in `tests/test_sources_fetch_bounds.py` -- is replaced here with a
local stub that answers from canned feed documents. What this file is about
is what the CONNECTOR does with what comes back: the keys, the entry
identity and which one was used, the per-collection caps, the window
semantics, and what it reports when a feed fails.

ONE test reaches the real network. It is marked `live`, which `pyproject.toml`
excludes from every ordinary run, so this suite never depends on a feed's
mood.
"""
import pytest

from mentis import api
from mentis.sources import Refused, fetch, reading
from mentis.sources import feeds
from mentis.web import _State, fixture

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Orchard Weekly</title>
  <item>
    <title>Blossom arrives early</title>
    <link>https://orchard.example/blossom</link>
    <guid isPermaLink="false">tag:orchard.example,2026:1</guid>
    <pubDate>Tue, 24 Nov 2026 09:00:00 GMT</pubDate>
    <description>&lt;p&gt;The &lt;b&gt;first&lt;/b&gt; blossom.&lt;/p&gt;
                 &lt;script&gt;alert(1)&lt;/script&gt;</description>
    <source url="https://fruitpress.example/">Fruit Press</source>
  </item>
  <item>
    <title>Pruning in frost</title>
    <link>https://orchard.example/pruning</link>
    <guid>tag:orchard.example,2026:2</guid>
    <pubDate>Mon, 02 Nov 2026 07:30:00 GMT</pubDate>
    <description>Short days.</description>
  </item>
</channel></rss>
"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Kiln Notes</title>
  <entry>
    <id>urn:uuid:4f1c</id>
    <title>Glaze at cone six</title>
    <link rel="edit" href="https://kiln.example/edit/1"/>
    <link rel="alternate" href="https://kiln.example/glaze"/>
    <updated>2026-11-20T11:00:00Z</updated>
    <summary type="html">&lt;p&gt;A satin matte.&lt;/p&gt;</summary>
    <author><name>Ada</name></author>
  </entry>
</feed>
"""

#: No guid and no id: identified by its link and its date instead.
NO_ID = """<rss version="2.0"><channel><title>Loose</title>
  <item><title>One</title><link>https://loose.example/one</link>
        <pubDate>Tue, 24 Nov 2026 09:00:00 GMT</pubDate></item>
</channel></rss>
"""

#: Nothing that could identify it at all.
NOTHING = """<rss version="2.0"><channel><title>Bare</title>
  <item><title>Anonymous</title><description>No link, no id.</description></item>
</channel></rss>
"""

FEED = "https://orchard.example/feed.xml"


class _Stub:
    """A stand-in for `fetch.get`: canned documents by address, and a record
    of the budget each call was given."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.asked: list[str] = []
        self.budgets: list = []

    def __call__(self, url, *, accept=None, budget=None, max_bytes=None):
        url = fetch.canonical_url(url)
        self.asked.append(url)
        self.budgets.append(budget)
        if budget is not None:
            budget.fetch(url)
        got = self.pages.get(url)
        if got is None:
            raise fetch.Unreachable(f"{url} answered HTTP 404", status=404)
        if isinstance(got, Exception):
            raise got
        body = got.encode("utf-8")
        if budget is not None:
            budget.spend(len(body))
        return fetch.Response(url=url, final_url=url, status=200,
                              media_type="application/rss+xml",
                              charset="utf-8", body=body)


@pytest.fixture
def brain(tmp_path):
    fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    return {"st": st, "src": api.sources(st.corpus), "corpus": st.corpus}


def _serve(monkeypatch, pages):
    stub = _Stub(pages)
    monkeypatch.setattr(fetch, "get", stub)
    return stub


def _acquire(brain, *, connector, options, name="Feed"):
    src = brain["src"]
    plan = src.preview_new(connector=connector, name=name, options=options)
    out = src.acquire_new(plan["draft"], plan["plan"], connector=connector,
                          actor="human", written_by="test")
    return plan, out


# -- rss-atom: real objects with resolving citations ---------------------------

def test_a_declared_feed_acquires_one_object_per_entry(brain, monkeypatch):
    _serve(monkeypatch, {FEED: RSS})
    plan, out = _acquire(brain, connector="rss-atom",
                         options={"feeds": [FEED]})
    assert plan["counts"]["new"] == 2
    assert len(out["admitted"]) == 2
    rows = reading.objects(brain["corpus"], out["collection"])["objects"]
    assert {r["state"] for r in rows} == {"present"}
    labels = sorted(r["label"] for r in rows)
    assert labels == ["Blossom arrives early", "Pruning in frost"]


def test_an_entry_keeps_its_title_link_date_and_summary(brain, monkeypatch):
    _serve(monkeypatch, {FEED: RSS})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    first = [e for e in brain["corpus"].admissions_from(
        feeds.RSS.source_of(out["collection"]))][0]
    native = first["body"]["envelope"]["bulk_source"]["native"]
    assert native["title"] == "Blossom arrives early"
    assert native["link"] == "https://orchard.example/blossom"
    assert native["published"].startswith("2026-11-24T09:00")
    assert native["publisher"] == "Fruit Press"
    assert native["feed"] == FEED
    assert native["feed_format"] == "rss-2.0"


def test_a_summary_is_reduced_to_text_and_no_script_survives(brain,
                                                             monkeypatch):
    _serve(monkeypatch, {FEED: RSS})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    rows = sorted(reading.objects(brain["corpus"],
                                  out["collection"])["objects"],
                  key=lambda r: r["label"])
    got = brain["src"].read(ref=rows[0]["ref"])
    text = got.get("text") or ""
    assert "The first blossom." in text
    assert "alert(1)" not in text
    assert "<b>" not in text and "<p>" not in text


@pytest.mark.parametrize("order", ["description-first", "content-first"])
def test_full_rss_content_is_retained_instead_of_the_teaser(brain, monkeypatch,
                                                          order):
    prose = "The telescope measured the planet's atmosphere. " * 50
    content = ("<content:encoded><![CDATA[<p>" + prose
               + "</p><script>steal()</script>"
               + '<img src="https://private.example/pixel"/>]]>'
               + "</content:encoded>")
    description = "<description>A short teaser.</description>"
    parts = description + content if order == "description-first" else content + description
    document = ('<rss xmlns:content="http://purl.org/rss/1.0/modules/content/">'
                '<channel><item><guid>article-1</guid><title>Atmosphere</title>'
                '<link>https://publisher.example/article</link>' + parts
                + '</item></channel></rss>')
    stub = _serve(monkeypatch, {FEED: document})
    plan, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    text = brain["src"].read(ref=out["admitted"][0])["text"]
    body = text.split("\n\n", 2)[2].split("\n--\n", 1)[0].strip()
    assert body == prose.strip()
    assert len(body) > 1500
    assert "A short teaser" not in text
    assert "steal()" not in text
    assert "private.example" not in text
    assert stub.asked == [FEED, FEED]  # preview and acquire, no page/subresource
    assert plan["at"]["spent"]["fetches"] == 1
    again = brain["src"].plan(out["collection"])
    assert again["counts"]["changed"] == 0
    assert again["counts"]["unchanged"] == 1


@pytest.mark.parametrize("content", [
    "<content:encoded/>",
    "<content:encoded>&lt;script&gt;code()&lt;/script&gt;</content:encoded>",
    '<content src="https://publisher.example/remote" type="html"/>',
    '<content type="application/pdf">JVBERi0xLjQ=</content>',
    '<content type="image/png">iVBORw0KGgo=</content>',
])
def test_empty_external_or_binary_content_falls_back_to_the_summary(content):
    document = ('<feed xmlns="http://www.w3.org/2005/Atom" '
                'xmlns:content="http://purl.org/rss/1.0/modules/content/">'
                '<entry><id>one</id><summary>Useful abstract.</summary>'
                + content + '</entry></feed>')
    assert feeds.parse_feed(document.encode())["entries"][0]["summary"] == \
        "Useful abstract."


@pytest.mark.parametrize("kind,content", [
    ('type="text"', "Full plain text about the observatory."),
    ('type="html"', "&lt;p&gt;Full &lt;b&gt;HTML&lt;/b&gt; prose.&lt;/p&gt;"),
    ('type="xhtml"', '<div xmlns="http://www.w3.org/1999/xhtml">'
     '<p>First paragraph.</p><script>code()</script><p>Second paragraph.</p></div>'),
])
def test_inline_atom_content_takes_priority_and_uses_the_shared_reducer(kind, content):
    document = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>one</id>'
                '<summary>A teaser.</summary><content ' + kind + '>' + content
                + '</content></entry></feed>')
    text = feeds.parse_feed(document.encode())["entries"][0]["summary"]
    assert "A teaser" not in text and "code()" not in text
    if "xhtml" in kind:
        assert text == "First paragraph.\n\nSecond paragraph."
    else:
        assert text.startswith("Full ")


def test_larger_inline_content_still_obeys_the_held_limit(brain, monkeypatch):
    from mentis.spine import held

    document = ('<rss><channel><item><guid>large</guid>'
                '<description>Small teaser.</description><content>'
                + "A substantive paragraph. " * 100
                + '</content></item></channel></rss>')
    _serve(monkeypatch, {FEED: document})
    monkeypatch.setattr(held, "MAX_BYTES", 512)
    plan = brain["src"].preview_new(connector="rss-atom", name="Larger body",
                                   options={"feeds": [FEED]})
    assert plan["counts"]["new"] == 0
    assert plan["not_acquired"]
    assert "held limit" in plan["not_acquired"][0]["reason"]


def test_the_citation_of_an_entry_resolves(brain, monkeypatch):
    _serve(monkeypatch, {FEED: RSS})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    got = brain["src"].provenance(out["admitted"][0])
    assert got["collection"] == out["collection"]
    assert got["connector"] == "rss-atom"


# -- the entry identity, and which one was used -------------------------------

def test_a_guid_is_the_identity_and_is_recorded_as_such():
    feed = feeds.parse_feed(RSS.encode())
    basis, how = feeds.identity_of(feed["entries"][0])
    assert basis == "tag:orchard.example,2026:1"
    assert how == "guid"


def test_an_atom_id_is_the_identity():
    feed = feeds.parse_feed(ATOM.encode())
    assert feed["format"] == "atom"
    entry = feed["entries"][0]
    assert feeds.identity_of(entry) == ("urn:uuid:4f1c", "id")
    assert entry["link"] == "https://kiln.example/glaze"   # rel=alternate
    assert entry["publisher"] == "Ada"
    assert feeds._iso(entry["when"]) == "2026-11-20T11:00:00+00:00"
    assert entry["summary"] == "A satin matte."            # HTML reduced


@pytest.mark.parametrize("given,want", [
    ("Tue, 24 Nov 2026 09:00:00 GMT", "2026-11-24T09:00:00+00:00"),
    ("Tue, 24 Nov 2026 09:00:00 +0000", "2026-11-24T09:00:00+00:00"),
    ("2026-11-20T11:00:00Z", "2026-11-20T11:00:00+00:00"),
    ("2026-11-20T11:00:00+02:00", "2026-11-20T09:00:00+00:00"),
    ("nonsense", None),
    ("", None),
])
def test_a_date_is_read_from_rfc_822_or_iso_8601_or_said_to_be_missing(
        given, want):
    assert feeds._iso(feeds._when(given)) == want


def test_link_plus_date_is_the_fallback_and_says_so(brain, monkeypatch):
    _serve(monkeypatch, {FEED: NO_ID})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    native = [e for e in brain["corpus"].admissions_from(
        feeds.RSS.source_of(out["collection"]))][0][
            "body"]["envelope"]["bulk_source"]["native"]
    assert native["id_from"] == "link+date"
    assert native["entry_id"].startswith("https://loose.example/one\n")


def test_an_entry_with_no_usable_id_is_reported_not_dropped(brain,
                                                            monkeypatch):
    _serve(monkeypatch, {FEED: NOTHING, "https://orchard.example/ok.xml": RSS})
    src = brain["src"]
    plan = src.preview_new(connector="rss-atom", name="Mixed",
                           options={"feeds": [FEED,
                                              "https://orchard.example/ok.xml"]})
    assert plan["counts"]["new"] == 2                      # the good feed's
    said = [r["reason"] for r in plan["refused"]]
    assert any("no guid, no id and no link" in s for s in said)
    assert any("Anonymous" in r["path"] for r in plan["refused"])


def test_both_feeds_failing_refuses_rather_than_recording_nothing(brain,
                                                                  monkeypatch):
    _serve(monkeypatch, {})
    with pytest.raises(Refused) as exc:
        brain["src"].preview_new(connector="rss-atom", name="Gone",
                                 options={"feeds": [FEED]})
    assert "nothing is inferred absent" in str(exc.value)


# -- the window: nothing is ever inferred absent ------------------------------

def test_a_second_sweep_of_the_same_feed_records_nothing_new(brain,
                                                             monkeypatch):
    """Stable keys AND stable bytes: an entry that has not changed is
    `unchanged`, not re-admitted."""
    _serve(monkeypatch, {FEED: RSS})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    col = out["collection"]
    again = brain["src"].plan(col)
    assert again["counts"]["new"] == 0
    assert again["counts"]["changed"] == 0
    assert again["unchanged"] == 2
    done = brain["src"].sweep(col, again["plan"], actor="human",
                              written_by="test")
    assert done["admitted"] == []
    assert done["absent"] == []


def test_an_entry_that_scrolls_off_the_feed_is_never_absent(brain,
                                                            monkeypatch):
    """A feed is a window, not an enumeration -- git's rule for a commit
    window (`mentis.sources.git:52-61`), kept."""
    _serve(monkeypatch, {FEED: RSS})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    shorter = RSS.split("<item>")[0] + "<item>" + \
        RSS.split("<item>")[1] + "</channel></rss>"
    _serve(monkeypatch, {FEED: shorter})
    again = brain["src"].plan(out["collection"])
    assert again["absent"] == []
    assert again["counts"]["absent"] == 0
    assert again["counts"]["not_examined"] == 1


def test_a_feed_that_fails_is_reported_and_makes_nothing_absent(brain,
                                                                monkeypatch):
    two = {FEED: RSS, "https://kiln.example/atom": ATOM}
    _serve(monkeypatch, two)
    _, out = _acquire(brain, connector="rss-atom",
                      options={"feeds": list(two)})
    assert len(out["admitted"]) == 3
    _serve(monkeypatch, {FEED: RSS})                 # the Atom feed is gone
    again = brain["src"].plan(out["collection"])
    assert again["absent"] == []
    assert any("404" in r["reason"] for r in again["refused"])
    assert [r for r in again["at"]["read"]
            if r["status"] == "failed"][0]["shown"] == \
        "https://kiln.example/atom"


# -- `since` -------------------------------------------------------------------

def test_since_leaves_older_entries_counted_and_unacquired(brain,
                                                           monkeypatch):
    _serve(monkeypatch, {FEED: RSS})
    plan, out = _acquire(brain, connector="rss-atom",
                         options={"feeds": [FEED], "since": "2026-11-10"})
    assert plan["counts"]["new"] == 1
    assert plan["counts"]["visible_not_selected"] == 1


@pytest.mark.parametrize("bad", ["24/11/2026", "2026-13-01", "yesterday"])
def test_a_since_that_is_not_a_date_is_refused(bad):
    with pytest.raises(Refused):
        feeds.RSS.checked_options({"feeds": [FEED], "since": bad})


# -- the per-collection caps ---------------------------------------------------

def test_the_feed_count_per_collection_is_capped():
    many = [f"https://e{i}.example/f.xml" for i in range(feeds.MAX_FEEDS + 1)]
    with pytest.raises(Refused) as exc:
        feeds.RSS.checked_options({"feeds": many})
    assert f"at most {feeds.MAX_FEEDS}" in str(exc.value)


def test_the_query_count_per_collection_is_capped():
    many = [f"query {i}" for i in range(feeds.MAX_QUERIES + 1)]
    with pytest.raises(Refused) as exc:
        feeds.SEARCH.checked_options({"queries": many})
    assert f"at most {feeds.MAX_QUERIES}" in str(exc.value)


def test_the_entries_per_feed_are_capped(brain, monkeypatch):
    items = "".join(
        f"<item><title>n{i}</title><guid>g{i}</guid>"
        f"<link>https://e.example/{i}</link></item>"
        for i in range(feeds.MAX_ENTRIES_PER_FEED + 10))
    _serve(monkeypatch, {FEED: f"<rss version='2.0'><channel><title>Many"
                               f"</title>{items}</channel></rss>"})
    plan, _ = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    assert plan["counts"]["new"] == feeds.MAX_ENTRIES_PER_FEED


def test_the_sweep_budget_is_the_named_per_sweep_caps(brain, monkeypatch):
    stub = _serve(monkeypatch, {FEED: RSS})
    _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    budget = stub.budgets[0]
    assert budget.max_fetches == feeds.SWEEP_FETCHES
    assert budget.max_bytes == feeds.SWEEP_BYTES


def test_a_feed_document_is_capped_below_the_whole_response_cap(brain,
                                                                monkeypatch):
    asked = {}

    def stub(url, *, accept=None, budget=None, max_bytes=None):
        asked["max_bytes"] = max_bytes
        return fetch.Response(url=url, final_url=url, status=200,
                              media_type="text/xml", charset="utf-8",
                              body=RSS.encode())

    monkeypatch.setattr(fetch, "get", stub)
    _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    assert asked["max_bytes"] == feeds.MAX_FEED_BYTES
    assert feeds.MAX_FEED_BYTES <= fetch.MAX_RESPONSE_BYTES


def test_a_query_is_bounded_in_length():
    with pytest.raises(Refused):
        feeds.SEARCH.checked_options({"queries": ["x" * 400]})
    with pytest.raises(Refused):
        feeds.SEARCH.checked_options({"queries": [""]})


# -- the addresses a scope may hold --------------------------------------------

@pytest.mark.parametrize("bad", ["http://e.example/f.xml",
                                 "file:///C:/feed.xml",
                                 "https://tok@e.example/f.xml"])
def test_a_feed_address_goes_through_the_same_address_rules(bad):
    with pytest.raises(Refused):
        feeds.RSS.checked_options({"feeds": [bad]})


def test_a_declared_feed_address_that_looks_like_a_credential_is_refused():
    with pytest.raises(Refused) as exc:
        feeds.RSS.checked_options({"feeds": ["https://e.example/f?apikey=x"]})
    assert "credential" in str(exc.value)


def test_an_ordinary_feed_query_is_not_mistaken_for_a_credential():
    got = feeds.RSS.checked_options(
        {"feeds": ["https://e.example/f?format=rss&tag=orchard"]})
    assert got["feeds"] == ["https://e.example/f?format=rss&tag=orchard"]
    # and the provider's own address, which is a query, passes
    feeds.address_for("pears")


def test_an_unknown_scope_option_is_refused_not_dropped():
    with pytest.raises(Refused):
        feeds.RSS.checked_options({"feeds": [FEED], "depth": 3})
    with pytest.raises(Refused):
        feeds.SEARCH.checked_options({"queries": ["x"], "feeds": [FEED]})


def test_a_feed_collection_is_not_bound_to_this_machine(brain, monkeypatch):
    _serve(monkeypatch, {FEED: RSS})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    state = brain["src"].binding_state(out["collection"])
    assert state["binding"] == fetch.NET_BINDING
    with pytest.raises(Refused) as exc:
        brain["src"].bind(out["collection"], "C:\\Temp")
    assert "declared in its scope" in str(exc.value)


# -- web-search ----------------------------------------------------------------

def test_a_query_resolves_to_the_providers_address():
    where = feeds.address_for("solar roof tiles")
    assert where.startswith("https://news.google.com/rss/search?q=")
    assert "solar%20roof%20tiles" in where


def test_an_unknown_provider_is_refused_and_names_the_known_ones():
    with pytest.raises(Refused) as exc:
        feeds.provider("not-a-provider")
    assert "google-news" in str(exc.value)


def test_the_provider_table_is_data_with_a_terms_note():
    for key, entry in feeds.PROVIDERS.items():
        assert "{query}" in entry["template"]
        assert entry["template"].startswith("https://")
        assert len(entry["terms"]) > 40
        assert entry["terms_url"].startswith("https://")
    table = feeds.provider_table()
    assert {t["id"] for t in table} == set(feeds.PROVIDERS)
    assert all(t["terms"] for t in table)


def test_a_search_acquires_results_as_feed_entries(brain, monkeypatch):
    where = feeds.address_for("blossom")
    _serve(monkeypatch, {where: RSS})
    plan, out = _acquire(brain, connector="web-search", name="Blossom",
                         options={"queries": ["blossom"]})
    assert plan["counts"]["new"] == 2
    native = [e for e in brain["corpus"].admissions_from(
        feeds.SEARCH.source_of(out["collection"]))][0][
            "body"]["envelope"]["bulk_source"]["native"]
    assert native["query"] == "blossom"
    assert native["provider"] == "google-news"
    assert "personal" in native["provider_terms"]
    assert native["search_address"] == where


def test_a_search_result_key_reads_as_its_query(brain, monkeypatch):
    where = feeds.address_for("roof tiles")
    _serve(monkeypatch, {where: RSS})
    _, out = _acquire(brain, connector="web-search",
                      options={"queries": ["roof tiles"]})
    keys = [r["key"] for r in reading.objects(
        brain["corpus"], out["collection"])["objects"]]
    assert all(k.startswith("roof-tiles/") for k in keys)


def test_a_feed_entry_key_is_one_a_magnet_can_actually_read(brain,
                                                            monkeypatch):
    """A Magnet reads a collection through a `file` source, and the rule
    that decides what that may name (`magnet.activation.file_choice`, with
    its Rust twin `held_file::choice`) refuses a key holding `:` or `?` --
    which is why an entry is keyed by a digest of its own id and not by the
    id itself, a guid being able to hold anything at all."""
    from mentis.magnet.activation import file_choice

    _serve(monkeypatch, {FEED: RSS})
    _, out = _acquire(brain, connector="rss-atom", options={"feeds": [FEED]})
    rows = reading.objects(brain["corpus"], out["collection"])["objects"]
    assert rows
    for row in rows:
        assert file_choice({"collection": out["collection"],
                            "path": row["key"]}) == ("exact", row["key"])


def test_search_and_feeds_are_one_implementation():
    """The amendment's words: "this is one implementation, not two"."""
    assert type(feeds.RSS) is type(feeds.SEARCH)
    assert feeds.RSS._survey.__func__ is feeds.SEARCH._survey.__func__
    assert feeds.RSS.CONNECTOR != feeds.SEARCH.CONNECTOR


# -- what a feed document may be ----------------------------------------------

def test_a_feed_that_declares_entities_is_refused_unread():
    bomb = ('<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaa">]>'
            '<rss version="2.0"><channel><title>&a;</title></channel></rss>')
    with pytest.raises(Refused) as exc:
        feeds.parse_feed(bomb.encode())
    assert "DTD" in str(exc.value)


@pytest.mark.parametrize("bad", [b"not xml at all", b"<html><body>hi</body></html>",
                                 b"<rss><channel><title>x"])
def test_something_that_is_not_a_feed_is_refused(bad):
    with pytest.raises(Refused):
        feeds.parse_feed(bad)


def test_rss_1_0_rdf_reads_too():
    rdf = ("""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                        xmlns="http://purl.org/rss/1.0/">
             <channel><title>Old</title></channel>
             <item><title>One</title><link>https://old.example/1</link></item>
           </rdf:RDF>""")
    feed = feeds.parse_feed(rdf.encode())
    assert feed["format"] == "rss-1.0"
    assert feed["entries"][0]["title"] == "One"


# -- the live check ------------------------------------------------------------

@pytest.mark.live
@pytest.mark.parametrize("connector,options", [
    # A plain feed, from a different host than the search provider, so the
    # two live cases do not share one host's rate limit.
    ("rss-atom", {"feeds": ["https://feeds.bbci.co.uk/news/rss.xml"]}),
    ("web-search", {"queries": ["apple orchard"]}),
])
def test_live_a_feed_and_a_query_acquire_real_objects(brain, connector,
                                                      options):
    """Part W's done-when, for two of its three kinds: a real address on
    this machine's network acquires real objects whose citations resolve and
    whose bytes read back. Marked `live`."""
    src = brain["src"]
    plan = src.preview_new(connector=connector, name="Live", options=options)
    assert plan["counts"]["new"] > 0, plan["at"]
    out = src.acquire_new(plan["draft"], plan["plan"], connector=connector,
                          actor="human", written_by="test")
    assert out["admitted"]
    got = src.provenance(out["admitted"][0])
    assert got["collection"] == out["collection"]
    assert got["connector"] == connector
    assert src.read(ref=out["admitted"][0])["text"]
    rows = reading.objects(brain["corpus"], out["collection"])["objects"]
    assert all(r["state"] == "present" for r in rows)
    first = [e for e in brain["corpus"].admissions_from(
        src._conn(out["collection"]).kind.source_of(out["collection"]))][0]
    native = first["body"]["envelope"]["bulk_source"]["native"]
    assert native["link"].startswith("https://")
    assert native["id_from"] in ("guid", "id", "link+date", "link")
    print(f"\nLIVE {connector}: {len(out['admitted'])} objects, "
          f"read {plan['at']['spent']['bytes']} bytes from "
          f"{plan['at']['spent']['fetches']} fetches")


@pytest.mark.live
def test_live_a_search_query_serves_this_machine():
    """The amendment's verification, repeatable: the provider's address
    answers 200 with real RSS, with a guid and a date per item. Marked
    `live`, so it is opt-in (`-m live`) and no ordinary run depends on it.

    A PROVIDER MAY RATE-LIMIT. Google News answers 429 to a burst of
    queries from one machine, which is the terms note in the provider table
    being enforced rather than anything wrong here: the connector reports it
    as `Unreachable` with its status, which is what the amendment asks for.
    This test says so rather than retrying, so a 429 reads as what it is."""
    where = feeds.address_for("orchard")
    answer = fetch.get(where, accept=feeds.ACCEPT,
                       max_bytes=feeds.MAX_FEED_BYTES)
    assert answer.status == 200
    feed = feeds.parse_feed(answer.body, charset=answer.charset)
    assert feed["format"] == "rss-2.0"
    assert feed["entries"], "the provider returned no items"
    first = feed["entries"][0]
    assert feeds.identity_of(first)[1] in ("guid", "link+date", "link")
    assert first["link"].startswith("https://")
