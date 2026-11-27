"""A conversation's page and a Topic's page are cut at the query layer.

The statements one page costs do not grow with the Conversation, and a
Topic's page (`members_page(only=)`) is exactly the page the old in-memory cut
of every member gave -- newest page, older pages, newer pages, an empty page.
"""

from mentis.conversation import (CONTRIBUTION, IN_CONVERSATION, REPLIES_TO)
from mentis.fluid import route
from mentis.spine import store as S
from mentis.web import _State, fixture

COLL = "/fluid/api/collections/conversation"


def _text(s):
    return [{"type": "text", "text": s}]


def _world(tmp_path, n):
    """`n` posts in one Conversation: every 5th a reply to the one before,
    every 3rd filed under a Topic (one filing ended), and a post from
    elsewhere included and filed."""
    built = fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    cv, me = st.cv, built["who"]["@brian"]
    c = cv.open_conversation("Long", attributed_to=me)
    other = cv.open_conversation("Elsewhere", attributed_to=me)
    t = cv.open_topic(c, "Filed", attributed_to=me)
    posts = []
    for i in range(n):
        reply = posts[-1] if i % 5 == 4 else None
        posts.append(cv.say(c, me, _text(f"post {i}"), replies_to=reply))
        if i % 3 == 0:
            cv.assign_topic(posts[-1], t)
    cv.end_filing(posts[3], t, by=me)
    away = cv.say(other, me, _text("from elsewhere"))
    cv.link_into(away, c, by=me)
    cv.assign_topic(away, t)
    return st, c, t


def _counting(st, monkeypatch):
    count = {"n": 0}

    def trace(_stmt):
        count["n"] += 1

    real = S.Store._read_connection

    def traced(self):
        conn = real(self)
        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(S.Store, "_read_connection", traced)
    st.corpus._store._conn.set_trace_callback(trace)
    return count


def _old_topic_units(st, c, t):
    """What `_topic_page` cut in memory before: every member, flat, filtered
    to what is filed under the Topic now."""
    from mentis.fluid.read import _in_force
    from mentis.conversation import ABOUT_TOPIC, LINKED_INTO
    corpus = st.corpus
    filed = {x["link"]["from"] for x in _in_force(
        corpus, corpus.links(relation=ABOUT_TOPIC, to=t))}
    also = [x["link"]["from"] for x in _in_force(
        corpus, corpus.links(relation=LINKED_INTO, to=c))]
    every = corpus.members_page(c, home=IN_CONVERSATION, kind=CONTRIBUTION,
                                replies=REPLIES_TO, also=also, roots=False,
                                limit=100000)["rows"]
    return [r for r in every if r[0] in filed]


def _cost(st, monkeypatch, query):
    count = _counting(st, monkeypatch)
    got = route(st, COLL, query)
    return count["n"], got


def test_a_page_costs_the_same_statements_however_long(tmp_path,
                                                       monkeypatch):
    costs = {}
    for n in (20, 240):
        st, c, t = _world(tmp_path / str(n), n)
        newest = route(st, COLL, {"id": [c], "limit": ["10"]})
        costs[n] = [
            _cost(st, monkeypatch, {"id": [c], "limit": ["10"]})[0],
            _cost(st, monkeypatch, {"id": [c], "limit": ["10"],
                                    "before": [newest["before"]]})[0],
            _cost(st, monkeypatch, {"id": [c], "limit": ["10"], "topic": [t]})[0],
        ]
        got = _cost(st, monkeypatch, {"id": [c], "limit": ["10"]})[1]
        assert len(got["items"]) == 10 and got["newer"] == 0
    assert costs[20] == costs[240], costs


def test_a_topic_page_is_the_old_in_memory_cut(tmp_path, monkeypatch):
    st, c, t = _world(tmp_path, 40)
    want = _old_topic_units(st, c, t)
    # the page is cut in SQL: never a read of every member
    limits = []
    real = S.Store.members_page

    def spy(self, to, **kw):
        limits.append(kw.get("limit"))
        return real(self, to, **kw)
    monkeypatch.setattr(S.Store, "members_page", spy)
    assert len(want) > 10
    ids = [r[0] for r in want]
    # newest page, then older pages to the start
    got = route(st, COLL, {"id": [c], "topic": [t], "limit": ["4"]})
    assert got["key"] == f"topic:{c}:{t}" and got["total"] == len(want)
    pages = [got]
    while pages[0]["before"]:
        pages.insert(0, route(st, COLL, {"id": [c], "topic": [t], "limit": ["4"],
                                         "before": [pages[0]["before"]]}))
    held = [i["id"] for p in pages for i in p["items"]]
    assert held == ids
    assert pages[0]["older"] == 0 and pages[-1]["newer"] == 0
    for p in pages:
        assert p["older"] + len(p["items"]) + p["newer"] == len(want)
    # numbers are home numbers, never ranks among the filed
    by = {r[0]: r for r in want}
    for p in pages:
        for i in p["items"]:
            assert i["number"] == by[i["id"]][3]
            assert i["reply_to"] == by[i["id"]][4]
    # forward from the start, and an empty page after the newest
    fwd = route(st, COLL, {"id": [c], "topic": [t], "limit": ["5"],
                           "from": ["start"]})
    assert [i["id"] for i in fwd["items"]] == ids[:5]
    nxt = route(st, COLL, {"id": [c], "topic": [t], "limit": ["5"],
                           "after": [fwd["after"]]})
    assert [i["id"] for i in nxt["items"]] == ids[5:10]
    end = route(st, COLL, {"id": [c], "topic": [t], "limit": ["5"],
                           "after": [ids[-1]]})
    assert end["items"] == [] and end["total"] == len(want)
    assert end["older"] == len(want)
    assert limits and max(limits) <= 5, limits


# -- a page that folds away is not an empty page (opr-d8e0ec806221) -----------
#
# Folding a Magnet's own bookkeeping out of its Conversation (5788d855) left a
# page that was all bookkeeping reading as nothing but "30 posts folded". The
# page now keeps READING until it holds `limit` members the view will draw --
# `latest._sifted`'s pattern -- while still carrying what folds, which the
# view's own fold draws and counts.
#
# WHAT FOLDS IS THE CLASSIFIER'S ANSWER, and it has its own tests
# (`test_conversation_mechanics`, `test_agent_work`). Here it is named
# directly, so the paging is what is under test and nothing else.

def _folding(monkeypatch, folds):
    """`classify` says the posts in `folds` fold, as the view's fold does."""
    from mentis.conversation import agent_work
    monkeypatch.setattr(agent_work, "classify", lambda cv, ids, owner: {
        i: ({"kind": "mechanics", "why": "Perspective reconciled",
             "to": None, "to_name": None} if i in folds else None)
        for i in ids})


def _ordered(st, c):
    """Every member the conversation draws, in page order. Read before any
    folding is named, so it is the page's own order, nothing left out."""
    got = route(st, COLL, {"id": [c], "limit": ["200"], "from": ["start"]})
    assert not got["after"] and got["older"] == 0, "the whole conversation"
    return [i["id"] for i in got["items"]]


def test_a_page_whose_newest_members_all_fold_still_reads(tmp_path,
                                                          monkeypatch):
    st, c, _t = _world(tmp_path, 60)
    ids = _ordered(st, c)
    # the newest 30 drawable members are bookkeeping: a plain page of 10
    # would be ten folded members and nothing to read
    folds = set(ids[-30:])
    _folding(monkeypatch, folds)
    got = route(st, COLL, {"id": [c], "limit": ["10"]})
    drawn = [i["id"] for i in got["items"] if i["id"] not in folds]
    assert len(drawn) == 10, f"{len(drawn)} drawable of {len(got['items'])}"
    # and what folds is still in the page, in its place, for the view's fold
    assert folds <= {i["id"] for i in got["items"]}
    assert [i["id"] for i in got["items"]] == ids[-40:]


def test_a_page_that_folds_nothing_is_exactly_what_it_was(tmp_path,
                                                          monkeypatch):
    st, c, _t = _world(tmp_path, 60)
    ids = _ordered(st, c)
    _folding(monkeypatch, set())
    got = route(st, COLL, {"id": [c], "limit": ["10"]})
    assert [i["id"] for i in got["items"]] == ids[-10:]
    assert got["older"] == len(ids) - 10 and got["newer"] == 0


def test_paging_back_from_a_folded_page_reaches_every_member_once(
        tmp_path, monkeypatch):
    st, c, _t = _world(tmp_path, 60)
    ids = _ordered(st, c)
    _folding(monkeypatch, set(ids[-30:]))
    pages, got = [], route(st, COLL, {"id": [c], "limit": ["10"]})
    while True:
        pages.insert(0, got)
        if not got["before"]:
            break
        got = route(st, COLL, {"id": [c], "limit": ["10"],
                               "before": [got["before"]]})
    held = [i["id"] for p in pages for i in p["items"]]
    assert held == ids, "every member once, in order, no gap and no repeat"
    for p in pages:
        assert p["older"] + len(p["items"]) + p["newer"] == len(ids)


def test_forward_paging_cuts_at_the_limit_th_drawable_member(tmp_path,
                                                             monkeypatch):
    st, c, _t = _world(tmp_path, 60)
    ids = _ordered(st, c)
    _folding(monkeypatch, set(ids[:30]))
    got = route(st, COLL, {"id": [c], "limit": ["10"], "from": ["start"]})
    assert [i["id"] for i in got["items"]] == ids[:40]
    nxt = route(st, COLL, {"id": [c], "limit": ["10"],
                           "after": [got["after"]]})
    assert [i["id"] for i in nxt["items"]] == ids[40:50]


def test_fewer_drawable_than_a_page_reaches_the_start(tmp_path, monkeypatch):
    """Only a handful to draw in the whole Conversation: the page ends AT the
    start, never a few folded members short of it -- an "earlier" page that
    is folded all the way down is the thing being repaired."""
    st, c, _t = _world(tmp_path, 60)
    ids = _ordered(st, c)
    drawable = set(ids[20:24])              # four, nothing older or newer
    _folding(monkeypatch, set(ids) - drawable)
    got = route(st, COLL, {"id": [c], "limit": ["10"]})
    assert [i["id"] for i in got["items"]] == ids
    assert got["older"] == 0 and got["before"] is None


def test_a_conversation_that_is_all_bookkeeping_ends_rather_than_scanning_on(
        tmp_path, monkeypatch):
    """Nothing to draw anywhere: the page is the whole Conversation, read
    once within the scan's bound, not an endless walk."""
    st, c, _t = _world(tmp_path, 60)
    ids = _ordered(st, c)
    _folding(monkeypatch, set(ids))
    reads = []
    real = S.Store.members_page

    def spy(self, to, **kw):
        reads.append(kw.get("limit"))
        return real(self, to, **kw)
    monkeypatch.setattr(S.Store, "members_page", spy)
    got = route(st, COLL, {"id": [c], "limit": ["10"]})
    assert [i["id"] for i in got["items"]] == ids
    assert got["older"] == 0 and got["newer"] == 0
    from mentis.fluid.read import ROUNDS
    assert len(reads) <= ROUNDS + 1, reads
