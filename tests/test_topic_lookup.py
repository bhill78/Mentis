"""Stage 1a: the composer's `#` is answered from Topic names, never a scan.

  - `/fluid/api/topics?q=` answers from the Topics under their CURRENT names,
    Brain-wide, ordered prefix / word start / anywhere, and says where each is;
  - it reads no Turn and no acquired text, and stays small;
  - `Surface.find` keeps its exhaustive answer (Topics, Turns as they now
    read, its report of what was not searched) with one read per Turn;
  - the folded-text cache keeps what a sequential walk larger than it found,
    so a repeated walk costs less than the first.
"""

import json

import pytest

from mentis.conversation import versions
from mentis.fluid import route
from mentis.web import _State, _surface, fixture

TOPICS = "/fluid/api/topics"


def _text(s):
    return [{"type": "text", "text": s}]


@pytest.fixture
def world(tmp_path):
    built = fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    cv, me = st.cv, built["who"]["@brian"]
    a = cv.open_conversation("Alpha room", attributed_to=me)
    b = cv.open_conversation("Beta room", attributed_to=me)
    t = {
        "plan": cv.open_topic(a, "Planning", attributed_to=me),
        "road": cv.open_topic(b, "Roadmap plans", attributed_to=me),
        "explan": cv.open_topic(b, "Explanations", attributed_to=me),
        "old": cv.open_topic(a, "Old name", attributed_to=me),
    }
    cv.edit_topic(t["old"], by=me, name="Renamed planet")
    turn = cv.say(a, me, _text("we plan the move on friday"))
    return {"st": st, "cv": cv, "me": me, "a": a, "b": b, "t": t, "turn": turn}


def test_topics_by_current_name_ranked_and_placed(world):
    st, t = world["st"], world["t"]
    got = route(st, TOPICS, {"q": ["plan"]})
    assert [r["name"] for r in got["topics"]] == [
        "Planning", "Renamed planet", "Roadmap plans", "Explanations"]
    assert got["matched"] == 4
    row = {r["ref"]: r for r in got["topics"]}[t["road"]]
    assert row["conversation"] == world["b"]
    assert row["conversation_name"] == "Beta room"
    # the name a Topic had before is not its name
    assert route(st, TOPICS, {"q": ["old name"]})["topics"] == []
    # `#` and case are not part of the name asked for
    assert [r["ref"] for r in route(st, TOPICS, {"q": ["#PLANNING"]})["topics"]] \
        == [t["plan"]]


def test_topics_limit_counts_every_match(world):
    got = route(world["st"], TOPICS, {"q": ["plan"], "limit": ["2"]})
    assert len(got["topics"]) == 2 and got["matched"] == 4


def test_topics_reads_no_turn_and_no_source_text(world, monkeypatch):
    from mentis.conversation import Conversations
    from mentis.sources import search

    def scanned(*_a, **_k):
        raise AssertionError("the topic lookup scanned")

    monkeypatch.setattr(Conversations, "contributions", scanned)
    monkeypatch.setattr(search, "_load", scanned)
    got = route(world["st"], TOPICS, {"q": ["plan"]})
    assert got["matched"] == 4
    assert len(json.dumps(got).encode()) <= 5 * 1024


def test_topics_read_their_links_through_the_topics(world, monkeypatch):
    """`link_relation = ?` alone has no index: a relation-wide read of the
    Topic links read every row of the corpus (22 ms of the route's 32 on the
    2026-10-31 Brain). The links are read from the Topics, by `frm_any`."""
    from mentis.conversation import TOPIC_OF
    from mentis.spine.store import Store
    real = Store.links

    def links(self, *, relation=None, to=None, frm=None, to_any=None,
              frm_any=None):
        assert not (relation == TOPIC_OF and to is None and frm is None
                    and to_any is None and frm_any is None), \
            "the Topic links were read relation-wide"
        return real(self, relation=relation, to=to, frm=frm, to_any=to_any,
                    frm_any=frm_any)

    monkeypatch.setattr(Store, "links", links)
    got = route(world["st"], TOPICS, {"q": ["plan"]})
    assert [r["name"] for r in got["topics"]] == [
        "Planning", "Renamed planet", "Roadmap plans", "Explanations"]
    assert {r["ref"]: r["conversation"] for r in got["topics"]} == {
        world["t"]["plan"]: world["a"], world["t"]["old"]: world["a"],
        world["t"]["road"]: world["b"], world["t"]["explan"]: world["b"]}


def test_find_keeps_topics_turns_and_its_report(world):
    st, me, turn = world["st"], world["me"], world["turn"]
    surface = _surface(st)
    got = surface.find("plan")
    whats = {(r["what"], r["ref"]) for r in got["found"]}
    assert ("topic", world["t"]["plan"]) in whats
    assert ("turn", turn) in whats
    assert "not_searched" in got and "pending" in got
    # a Turn is found AS IT NOW READS, from the one read `contributions` gave
    versions.edit(st.cv, turn, by=me, text="we schedule the move on friday")
    again = surface.find("schedule")
    [hit] = [r for r in again["found"] if r["ref"] == turn]
    assert hit["said"].startswith("we schedule")
    assert hit["conversation_name"] == "Alpha room" and hit["number"] == 1
    assert turn not in {r["ref"] for r in surface.find("plan the move")["found"]}


def test_find_numbers_hits_as_turn_number_does(world):
    st, cv, me, a = world["st"], world["cv"], world["me"], world["a"]
    cv.say(a, me, _text("an unrelated second turn"))
    form = cv.say(a, me, _text(
        "Please tick:\n\n```checklist version=1 name=launchlist\n"
        "- [ ] Zeppelin launch ready\n```\n"))
    got = _surface(st).find("zeppelin")
    hits = [r for r in got["found"] if r["ref"] == form]
    assert {r["what"] for r in hits} >= {"turn", "block"}
    assert all(r["number"] == cv.turn_number(form) == 3 for r in hits)


def test_find_reads_each_turn_once(world, monkeypatch):
    from mentis.worker import Surface
    surface = _surface(world["st"])
    asked = []
    real = Surface._entry
    monkeypatch.setattr(Surface, "_entry",
                        lambda self, ref: asked.append(ref) or real(self, ref))
    surface.find("friday")
    assert world["turn"] not in asked


class _Held:
    def __init__(self, cost):
        self.cost = cost


def test_cache_keeps_what_a_walk_larger_than_it_found():
    from mentis.sources.search import _Cache
    cache = _Cache(100)
    walk = [f"f{i}" for i in range(15)]           # 150 against 100

    def once():
        missed = 0
        for k in walk:
            if cache.get(k) is None:
                missed += 1
                cache.put(k, _Held(10))
        return missed

    first = once()
    assert first == 15
    later = [once() for _ in range(4)]
    # never more than the first ask, and at most what does not fit
    assert all(m <= 5 for m in later), later
    assert cache.size <= cache.cap


def test_cache_asked_once_never_displaces_what_is_asked_again():
    from mentis.sources.search import _Cache
    cache = _Cache(30)
    for k in ("a", "b", "c"):
        cache.put(k, _Held(10))
    cache.put("one-off", _Held(10))
    assert cache.get("one-off") is None
    assert all(cache.get(k) is not None for k in ("a", "b", "c"))
    # asked more often than what it would push out: let in, in place of
    # the least recent
    for _ in range(3):
        cache.put("busy", _Held(10))
    assert cache.get("busy") is not None and cache.size == 30
    assert cache.get("a") is None
