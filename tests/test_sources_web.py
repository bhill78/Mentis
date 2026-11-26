"""THE WEB PAGE CONNECTOR (Part W, amendment adm-c38044ee5157 §2).

OFFLINE BY DEFAULT, for the same reason and in the same way as
`tests/test_sources_feeds.py`: `fetch.get` is replaced with a local stub, and
the bounds of `fetch.get` itself are proved in
`tests/test_sources_fetch_bounds.py`. What this file is about is the
connector: the keys, `depth` -- the field that turns a page fetch into a
crawler -- robots.txt, the per-sweep caps, and what it reports when a page
fails.

ONE test reaches the real network, marked `live` and excluded from every
ordinary run.
"""
import pytest

from mentis import api
from mentis.sources import Refused, fetch, reading
from mentis.sources import webpages as web
from mentis.web import _State, fixture

HOME = "https://orchard.example/"
PAGE = """<!doctype html>
<html><head><title>The orchard</title>
  <style>body { color: red }</style>
  <script>var secret = 1;</script>
</head>
<body>
  <h1>Pears</h1>
  <p>We grow <b>pears</b> and quinces.</p>
  <img src="/photo.jpg" alt="a pear">
  <script src="/app.js"></script>
  <a href="/pruning">Pruning</a>
  <a href="https://elsewhere.example/off">Somewhere else</a>
  <a href="mailto:ada@orchard.example">Mail</a>
  <a href="javascript:alert(1)">No</a>
  <noscript>Turn on JavaScript</noscript>
</body></html>
"""
PRUNING = ("<html><head><title>Pruning</title></head><body><p>Cut in "
           "frost.</p><a href='/deeper'>Deeper</a></body></html>")
DEEPER = "<html><head><title>Deeper</title></head><body>At depth two.</body></html>"


class _Stub:
    """A stand-in for `fetch.get`: canned pages by address, and a record of
    every address asked for -- which is how "nothing a page references is
    fetched" is checked."""

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
        kind, text = got if isinstance(got, tuple) else ("text/html", got)
        body = text.encode("utf-8")
        if budget is not None:
            budget.spend(len(body))
        return fetch.Response(url=url, final_url=url, status=200,
                              media_type=kind, charset="utf-8", body=body)


@pytest.fixture
def brain(tmp_path):
    fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    return {"st": st, "src": api.sources(st.corpus), "corpus": st.corpus}


def _serve(monkeypatch, pages):
    stub = _Stub(pages)
    monkeypatch.setattr(fetch, "get", stub)
    return stub


def _acquire(brain, options, name="Orchard"):
    src = brain["src"]
    plan = src.preview_new(connector="web", name=name, options=options)
    out = src.acquire_new(plan["draft"], plan["plan"], connector="web",
                          actor="human", written_by="test")
    return plan, out


ROBOTS_ALL = ("text/plain", "User-agent: *\nAllow: /\n")


# -- a declared page acquires one object ---------------------------------------

def test_a_declared_page_acquires_one_object_keyed_by_its_url(brain,
                                                              monkeypatch):
    _serve(monkeypatch, {HOME: PAGE})
    plan, out = _acquire(brain, {"urls": [HOME]})
    assert plan["counts"]["new"] == 1
    rows = reading.objects(brain["corpus"], out["collection"])["objects"]
    assert [r["key"] for r in rows] == [web.object_key(HOME)]
    assert rows[0]["label"] == "The orchard"
    assert rows[0]["state"] == "present"


def test_a_page_is_reduced_to_text_with_no_script_or_style(brain,
                                                           monkeypatch):
    _serve(monkeypatch, {HOME: PAGE})
    _, out = _acquire(brain, {"urls": [HOME]})
    rows = reading.objects(brain["corpus"], out["collection"])["objects"]
    text = brain["src"].read(ref=rows[0]["ref"])["text"]
    assert "We grow pears and quinces." in text
    assert "var secret" not in text and "color: red" not in text
    assert "Turn on JavaScript" not in text
    assert "<b>" not in text


def test_the_citation_of_a_page_resolves(brain, monkeypatch):
    _serve(monkeypatch, {HOME: PAGE})
    _, out = _acquire(brain, {"urls": [HOME]})
    got = brain["src"].provenance(out["admitted"][0])
    assert got["collection"] == out["collection"]
    assert got["connector"] == "web"


def test_the_same_page_twice_records_nothing_new(brain, monkeypatch):
    _serve(monkeypatch, {HOME: PAGE})
    _, out = _acquire(brain, {"urls": [HOME]})
    again = brain["src"].plan(out["collection"])
    assert again["counts"]["new"] == 0 and again["unchanged"] == 1
    done = brain["src"].sweep(out["collection"], again["plan"],
                              actor="human", written_by="test")
    assert done["admitted"] == [] and done["absent"] == []


@pytest.mark.parametrize("given,key", [
    ("https://Orchard.Example/A", "https://orchard.example/A"),
    ("https://orchard.example/a/../b", "https://orchard.example/b"),
    ("https://orchard.example:443/x#frag", "https://orchard.example/x"),
])
def test_an_address_normalises_to_one_key(brain, monkeypatch, given, key):
    _serve(monkeypatch, {key: PAGE})
    _, out = _acquire(brain, {"urls": [given]})
    assert [r["key"] for r in reading.objects(
        brain["corpus"], out["collection"])["objects"]] == [web.object_key(key)]
    # the two spellings of the one address reach the one object
    assert web.object_key(given) == web.object_key(key)


# -- depth: the field that turns a page fetch into a crawler -------------------

def test_depth_defaults_to_zero_and_follows_nothing(brain, monkeypatch):
    stub = _serve(monkeypatch, {HOME: PAGE,
                                "https://orchard.example/pruning": PRUNING})
    assert web.checked_options({"urls": [HOME]})["depth"] == 0
    assert web.DEFAULT_DEPTH == 0
    plan = brain["src"].preview_new(connector="web", name="Orchard",
                                    options={"urls": [HOME]})
    assert plan["counts"]["new"] == 1
    pages = [a for a in stub.asked if not a.endswith("/robots.txt")]
    assert pages == [HOME]            # one survey, one page, nothing else


def test_nothing_a_page_references_is_ever_fetched(brain, monkeypatch):
    """No subresource fetching: the image and the script the page names are
    not requested, at any depth."""
    stub = _serve(monkeypatch, {HOME: PAGE,
                                "https://orchard.example/pruning": PRUNING,
                                "https://orchard.example/deeper": DEEPER})
    _acquire(brain, {"urls": [HOME], "depth": 2})
    assert not any("photo.jpg" in a or "app.js" in a for a in stub.asked)


def test_depth_one_follows_only_links_the_page_states_on_its_own_host(
        brain, monkeypatch):
    stub = _serve(monkeypatch, {HOME: PAGE,
                                "https://orchard.example/pruning": PRUNING,
                                "https://elsewhere.example/off": DEEPER,
                                "https://orchard.example/deeper": DEEPER})
    plan, out = _acquire(brain, {"urls": [HOME], "depth": 1})
    keys = sorted(r["key"] for r in reading.objects(
        brain["corpus"], out["collection"])["objects"])
    assert keys == sorted([web.object_key(HOME),
                           web.object_key("https://orchard.example/pruning")])
    assert not any("elsewhere.example" in a for a in stub.asked)
    # mailto: and javascript: are not addresses this fetches at all
    assert not any(a.startswith(("mailto", "javascript")) for a in stub.asked)
    # depth 1 stops at depth 1: /deeper is stated by /pruning and not taken
    assert web.object_key("https://orchard.example/deeper") not in keys


def test_depth_two_follows_two_hops(brain, monkeypatch):
    _serve(monkeypatch, {HOME: PAGE,
                         "https://orchard.example/pruning": PRUNING,
                         "https://orchard.example/deeper": DEEPER})
    _, out = _acquire(brain, {"urls": [HOME], "depth": 2})
    keys = sorted(r["key"] for r in reading.objects(
        brain["corpus"], out["collection"])["objects"])
    assert web.object_key("https://orchard.example/deeper") in keys


def test_depth_has_a_hard_maximum():
    assert web.MAX_DEPTH == 2
    with pytest.raises(Refused) as exc:
        web.checked_options({"urls": [HOME], "depth": web.MAX_DEPTH + 1})
    assert f"0 to {web.MAX_DEPTH}" in str(exc.value)
    assert "crawl" in str(exc.value)


@pytest.mark.parametrize("bad", [-1, "two", 1.5, True, {"depth": 1}])
def test_a_depth_that_is_not_a_whole_number_in_range_is_refused(bad):
    with pytest.raises(Refused):
        web.checked_options({"urls": [HOME], "depth": bad})


def test_the_links_followed_from_one_page_are_capped(brain, monkeypatch):
    many = "".join(f"<a href='/p{i}'>p{i}</a>"
                   for i in range(web.MAX_LINKS_PER_PAGE + 10))
    pages = {HOME: f"<html><body>{many}</body></html>"}
    pages.update({f"https://orchard.example/p{i}": f"<html><body>{i}</body>"
                  f"</html>" for i in range(web.MAX_LINKS_PER_PAGE + 10)})
    _serve(monkeypatch, pages)
    plan, _ = _acquire(brain, {"urls": [HOME], "depth": 1})
    assert plan["counts"]["new"] == web.MAX_LINKS_PER_PAGE + 1


def test_the_pages_per_sweep_are_capped(brain, monkeypatch):
    """The crawl cannot run away even inside the depth and link caps."""
    monkeypatch.setattr(web, "MAX_LINKS_PER_PAGE", 100)
    many = "".join(f"<a href='/p{i}'>p{i}</a>" for i in range(200))
    pages = {HOME: f"<html><body>{many}</body></html>"}
    pages.update({f"https://orchard.example/p{i}":
                  f"<html><body>{i}</body></html>" for i in range(200)})
    _serve(monkeypatch, pages)
    plan, _ = _acquire(brain, {"urls": [HOME], "depth": 1})
    assert plan["counts"]["new"] == web.MAX_PAGES_PER_SWEEP
    assert any("its limit of" in r["reason"] for r in plan["refused"])


def test_the_sweep_budget_is_the_named_per_sweep_caps(brain, monkeypatch):
    stub = _serve(monkeypatch, {HOME: PAGE})
    _acquire(brain, {"urls": [HOME]})
    budget = stub.budgets[0]
    assert budget.max_fetches == web.SWEEP_FETCHES
    assert budget.max_bytes == web.SWEEP_BYTES


def test_a_page_is_capped_below_the_whole_response_cap(brain, monkeypatch):
    asked = {}

    def stub(url, *, accept=None, budget=None, max_bytes=None):
        asked.setdefault("max_bytes", max_bytes)
        return fetch.Response(url=url, final_url=url, status=200,
                              media_type="text/html", charset="utf-8",
                              body=PAGE.encode())

    monkeypatch.setattr(fetch, "get", stub)
    _acquire(brain, {"urls": [HOME]})
    assert asked["max_bytes"] in (web.MAX_PAGE_BYTES, fetch.ROBOTS_MAX_BYTES)
    assert web.MAX_PAGE_BYTES <= fetch.MAX_RESPONSE_BYTES


# -- robots.txt ----------------------------------------------------------------

def test_robots_txt_is_respected_for_a_declared_page(brain, monkeypatch):
    _serve(monkeypatch, {
        "https://orchard.example/robots.txt":
            ("text/plain", "User-agent: *\nDisallow: /private/\n"),
        HOME: PAGE,
        "https://orchard.example/private/notes": PAGE})
    plan = brain["src"].preview_new(
        connector="web", name="Orchard",
        options={"urls": [HOME, "https://orchard.example/private/notes"]})
    assert plan["counts"]["new"] == 1
    barred = [n for n in plan["not_acquired"]
              if n["path"] == web.object_key(
                  "https://orchard.example/private/notes")]
    assert barred and "robots.txt" in barred[0]["reason"]


def test_robots_txt_is_respected_for_a_followed_page(brain, monkeypatch):
    _serve(monkeypatch, {
        "https://orchard.example/robots.txt":
            ("text/plain", "User-agent: *\nDisallow: /pruning\n"),
        HOME: PAGE,
        "https://orchard.example/pruning": PRUNING})
    plan, _ = _acquire(brain, {"urls": [HOME], "depth": 1})
    assert plan["counts"]["new"] == 1
    assert any("robots.txt" in n["reason"] for n in plan["not_acquired"])


def test_a_robots_txt_that_cannot_be_read_withholds_the_page(brain,
                                                             monkeypatch):
    _serve(monkeypatch, {
        "https://orchard.example/robots.txt":
            fetch.Unreachable("server error", status=503),
        HOME: PAGE})
    with pytest.raises(Refused) as exc:
        brain["src"].preview_new(connector="web", name="Orchard",
                                 options={"urls": [HOME]})
    assert "no page in this collection could be read" in str(exc.value)


def test_a_redirect_cannot_be_used_to_get_around_robots_txt(brain,
                                                            monkeypatch):
    """robots.txt was consulted for the address asked for; a redirect can
    land somewhere the host asks readers not to fetch, so it is consulted
    again for where the page actually came from."""
    def stub(url, *, accept=None, budget=None, max_bytes=None):
        url = fetch.canonical_url(url)
        if url.endswith("/robots.txt"):
            return fetch.Response(
                url=url, final_url=url, status=200, media_type="text/plain",
                charset="utf-8",
                body=b"User-agent: *\nDisallow: /private/\n")
        return fetch.Response(
            url=url, final_url="https://orchard.example/private/notes",
            status=200, media_type="text/html", charset="utf-8",
            body=PAGE.encode(), redirects=(url,))

    monkeypatch.setattr(fetch, "get", stub)
    with pytest.raises(Refused) as exc:
        brain["src"].preview_new(connector="web", name="Orchard",
                                 options={"urls": [HOME]})
    assert "redirected to" in str(exc.value)
    assert "robots.txt" in str(exc.value)


def test_a_declared_page_address_that_looks_like_a_credential_is_refused():
    with pytest.raises(Refused) as exc:
        web.checked_options({"urls": ["https://e.example/p?token=abc"]})
    assert "credential" in str(exc.value)


def test_robots_txt_is_fetched_once_per_host_per_sweep(brain, monkeypatch):
    stub = _serve(monkeypatch, {
        "https://orchard.example/robots.txt": ROBOTS_ALL,
        HOME: PAGE, "https://orchard.example/pruning": PRUNING,
        "https://orchard.example/deeper": DEEPER})
    brain["src"].preview_new(connector="web", name="Orchard",
                             options={"urls": [HOME], "depth": 2})
    assert sum(1 for a in stub.asked if a.endswith("/robots.txt")) == 1
    assert len([a for a in stub.asked
                if not a.endswith("/robots.txt")]) == 3


# -- absence reported, never dropped -------------------------------------------

def test_a_page_that_404s_is_reported_and_is_not_absent(brain, monkeypatch):
    two = [HOME, "https://orchard.example/gone"]
    _serve(monkeypatch, {HOME: PAGE, "https://orchard.example/gone": PAGE})
    _, out = _acquire(brain, {"urls": two})
    assert len(out["admitted"]) == 2
    _serve(monkeypatch, {HOME: PAGE})                      # one page removed
    again = brain["src"].plan(out["collection"])
    assert again["absent"] == []                 # never inferred absent
    assert again["counts"]["absent"] == 0
    gone = [n for n in again["not_acquired"]
            if n["path"] == web.object_key("https://orchard.example/gone")]
    assert gone and "404" in gone[0]["reason"]
    assert [r for r in again["at"]["read"]
            if r["status"] == "failed"][0]["http"] == 404


def test_something_that_is_not_a_page_is_reported_as_what_it_is(brain,
                                                                monkeypatch):
    _serve(monkeypatch, {HOME: PAGE,
                         "https://orchard.example/map.pdf":
                             ("application/pdf", "%PDF-1.4 ...")})
    plan = brain["src"].preview_new(
        connector="web", name="Orchard",
        options={"urls": [HOME, "https://orchard.example/map.pdf"]})
    assert plan["counts"]["new"] == 1
    said = [n for n in plan["not_acquired"]
            if n["path"] == web.object_key(
                "https://orchard.example/map.pdf")]
    assert said and "application/pdf" in said[0]["reason"]
    assert "extractor" in said[0]["reason"]


def test_every_page_failing_refuses_rather_than_recording_nothing(brain,
                                                                  monkeypatch):
    _serve(monkeypatch, {})
    with pytest.raises(Refused) as exc:
        brain["src"].preview_new(connector="web", name="Gone",
                                 options={"urls": [HOME]})
    assert "nothing is inferred absent" in str(exc.value)


# -- the scope -----------------------------------------------------------------

def test_the_page_count_per_collection_is_capped():
    many = [f"https://e{i}.example/" for i in range(web.MAX_URLS + 1)]
    with pytest.raises(Refused) as exc:
        web.checked_options({"urls": many})
    assert f"at most {web.MAX_URLS}" in str(exc.value)


@pytest.mark.parametrize("bad", ["http://e.example/", "file:///C:/x.html",
                                 "ftp://e.example/x", "https://tok@e.example/"])
def test_a_page_address_goes_through_the_same_address_rules(bad):
    with pytest.raises(Refused):
        web.checked_options({"urls": [bad]})


def test_no_address_at_all_is_refused():
    with pytest.raises(Refused):
        web.checked_options({"urls": []})


def test_an_unknown_scope_option_is_refused_not_dropped():
    with pytest.raises(Refused):
        web.checked_options({"urls": [HOME], "since": "2026-01-01"})


def test_a_web_collection_is_not_bound_to_this_machine(brain, monkeypatch):
    _serve(monkeypatch, {HOME: PAGE})
    _, out = _acquire(brain, {"urls": [HOME]})
    state = brain["src"].binding_state(out["collection"])
    assert state["binding"] == fetch.NET_BINDING
    with pytest.raises(Refused) as exc:
        brain["src"].bind(out["collection"], "C:\\Temp")
    assert "declared in its scope" in str(exc.value)


# -- the HTML reduction itself --------------------------------------------------

def test_a_key_is_one_a_magnet_can_actually_read(brain, monkeypatch):
    """WHY THE KEY IS NOT THE LITERAL URL. A Magnet reads a collection
    through a `file` source, and the one rule that decides what that may
    name -- `mentis.magnet.activation.file_choice`, with its Rust twin
    `held_file::choice` -- refuses a key holding `:` or `?`. A literal URL
    would be acquired and then unreadable by the thing Part W exists to
    feed, so the key is the host plus a digest of the normalised URL, and
    the URL itself is recorded beside it."""
    from mentis.magnet.activation import file_choice

    assert file_choice({"collection": "col-x", "path": HOME}) is None
    assert file_choice({"collection": "col-x",
                        "path": "https://e.example/s?q=1"}) is None
    for url in (HOME, "https://e.example/s?q=1",
                "https://e.example/a/b/c.html"):
        key = web.object_key(url)
        assert file_choice({"collection": "col-x", "path": key}) == \
            ("exact", key)
    _serve(monkeypatch, {HOME: PAGE})
    _, out = _acquire(brain, {"urls": [HOME]})
    for row in reading.objects(brain["corpus"], out["collection"])["objects"]:
        assert file_choice({"collection": out["collection"],
                            "path": row["key"]}) == ("exact", row["key"])


def test_a_page_is_found_by_the_address_that_was_declared(brain, monkeypatch):
    """The descriptor's `normalise` hook is the connector's own key rule, so
    nothing has to know the digest to read a page."""
    from mentis.sources import registry
    _serve(monkeypatch, {HOME: PAGE})
    _, out = _acquire(brain, {"urls": [HOME]})
    assert registry.normalise("web", HOME) == web.object_key(HOME)
    assert registry.normalise("web", "https://Orchard.Example") == \
        web.object_key(HOME)
    got = brain["src"].read(collection=out["collection"], path=HOME)
    assert "We grow pears" in got["text"]
    # and normalising a key is idempotent
    key = web.object_key(HOME)
    assert web.object_key(key) == key


def test_links_in_html_keeps_only_https_addresses_the_page_states():
    got = fetch.links_in_html(PAGE, HOME)
    assert got == ["https://orchard.example/pruning",
                   "https://elsewhere.example/off"]


def test_text_of_html_survives_malformed_markup():
    assert "hello" in fetch.text_of_html("<p>hello<p attr=<<>")


@pytest.mark.parametrize("tag", ["script", "svg", "style", "iframe"])
def test_self_closing_skipped_html_keeps_following_text(tag):
    text = fetch.text_of_html(f'<p>Before</p><{tag}/><p>After</p>'
                              '<script>danger()</script>')
    assert "Before" in text and "After" in text
    assert "danger()" not in text


# -- the live check ------------------------------------------------------------

@pytest.mark.live
def test_live_a_declared_page_acquires_a_real_object(brain):
    """Part W's done-when, for its third kind: a real declared page on this
    machine's network acquires an object whose citation resolves and whose
    text reads back. Marked `live`."""
    src = brain["src"]
    plan = src.preview_new(connector="web", name="Live",
                           options={"urls": ["https://example.com/"]})
    assert plan["counts"]["new"] == 1, plan["at"]
    out = src.acquire_new(plan["draft"], plan["plan"], connector="web",
                          actor="human", written_by="test")
    assert len(out["admitted"]) == 1
    got = src.provenance(out["admitted"][0])
    assert got["collection"] == out["collection"] and got["connector"] == "web"
    text = src.read(ref=out["admitted"][0])["text"]
    assert "Example" in text
    native = [e for e in brain["corpus"].admissions_from(
        web.source_of(out["collection"]))][0][
            "body"]["envelope"]["bulk_source"]["native"]
    assert native["link"] == "https://example.com/"
    assert native["url"] == "https://example.com/"
    assert native["depth"] == 0
    print(f"\nLIVE web: 1 object, {plan['at']['spent']['bytes']} bytes from "
          f"{plan['at']['spent']['fetches']} fetches")


@pytest.mark.live
def test_live_a_declared_page_serves_this_machine():
    """One real page over the real bounded GET, with its robots.txt
    consulted first. Marked `live`, so no ordinary run depends on it."""
    where = "https://example.com/"
    rules = fetch.robots(where, cache={})
    assert rules.may(where) is None
    answer = fetch.get(where, accept=web.ACCEPT, max_bytes=web.MAX_PAGE_BYTES)
    assert answer.status == 200
    assert answer.media_type in web.PAGE_TYPES
    text, title, _ = fetch.read_html(answer.text())
    assert "Example" in (title + text)
