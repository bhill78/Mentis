"""A MAGNET'S BOOKKEEPING FOLDS AWAY (owner, 2026-11-27, ent-de11a0235181).

The owner's Magnet Conversation read as "Perspective reconciled: reconciled"
dozens of times instead of what the collection had found. Those posts are
RECORD_ONLY, their words composed by Mentis, and their author is whoever
activated the Magnet -- the owner -- so the agent-work fold's "never hide the
owner's own post" rule could never reach them. `agent_work.classify` now calls
them `mechanics` and folds them, except the one that carries an answer's words.

Real Brain, real doors: the `inquiry` fixture of `test_magnet_perspectives`.
"""
from mentis.conversation import agent_work
from mentis.conversation import posting
from mentis.magnet import perspectives as P
from mentis.operational.work_overview import owner_of

from tests.test_magnet_perspectives import inquiry, cmd, create  # noqa: F401
from tests.test_magnet_activation import MAGNET, world, built  # noqa: F401


def classify(w, posts):
    return agent_work.classify(w.cv, posts, owner_of(w.cv))


def test_perspective_lifecycle_posts_are_mechanics(inquiry):
    w = inquiry
    created = create(w)
    topic = created["perspective"]
    # The two posts creation writes: "Perspective created: ..." and
    # "Perspective question: ...". Both are the owner's by author.
    rows = P._rows(w.state, MAGNET, topic, limit=10)
    posts = [r["post"] for r in rows]
    assert len(posts) >= 2
    owner = owner_of(w.cv)
    for p in posts:
        assert w.corpus.read([p])[0]["attributed_to"] == owner, "the owner is the author"
    got = classify(w, posts)
    assert all(got[p] and got[p]["kind"] == "mechanics" for p in posts), got
    whys = {got[p]["why"] for p in posts}
    assert whys == {"Perspective created", "Perspective question"}, whys


def test_a_reconciled_event_folds_and_an_answer_with_words_does_not(inquiry):
    w = inquiry
    topic = create(w)["perspective"]
    book = P.event(w.state, MAGNET, topic, "reconciled", {"status": "qualified"}, w.by)
    empty = P.event(w.state, MAGNET, topic, "answered", {"intent": "x"}, w.by)
    words = P.event(w.state, MAGNET, topic, "answered",
                    {"text": "Three launches were reported this week."}, w.by)
    got = classify(w, [book["post"], empty["post"], words["post"]])
    assert got[book["post"]]["kind"] == "mechanics"
    assert got[book["post"]]["why"] == "Perspective reconciled"
    # the dispatched-run wrapper: the answer is its own post, this one folds
    assert got[empty["post"]]["kind"] == "mechanics"
    # THE ANSWER ITSELF IS NEVER FOLDED: it is what the owner came to read
    assert got[words["post"]] is None, got[words["post"]]


def test_the_collection_extraction_post_is_mechanics(inquiry):
    w = inquiry
    rows = w.corpus.operational(act=agent_work.MAGNET_EXTRACTED, limit=5)
    assert rows, "the fixture committed a collection page"
    posts = [a["turn"] for a in rows if a.get("turn")]
    got = classify(w, posts)
    assert all(got[p] and got[p]["kind"] == "mechanics" for p in posts), got
    assert {got[p]["why"] for p in posts} == {"collection: one page extracted"}


def test_an_ordinary_owner_post_in_the_magnet_is_untouched(inquiry):
    w = inquiry
    cid = P.home(w.state, MAGNET)
    out, _ = posting.post(w.cv, w.corpus, cid, {
        "author": w.by, "action": posting.RECORD_ONLY,
        "parts": [{"type": "text", "text": "What did it actually find?"}]},
        agents=w.state.agents, written_by=lambda: None, _record_only=True)
    assert classify(w, [out["turn"]])[out["turn"]] is None


def test_an_owner_reply_under_mechanics_keeps_it_in_the_room(inquiry):
    w = inquiry
    topic = create(w)["perspective"]
    book = P.event(w.state, MAGNET, topic, "reconciled", {"status": "qualified"}, w.by)
    assert classify(w, [book["post"]])[book["post"]]["kind"] == "mechanics"
    out, _ = posting.post(w.cv, w.corpus, P.home(w.state, MAGNET), {
        "author": w.by, "action": posting.RECORD_ONLY,
        "parts": [{"type": "text", "text": "Why did this one fail?"}],
        "replies_to": book["post"]},
        agents=w.state.agents, written_by=lambda: None, _record_only=True)
    assert out.get("turn"), out
    assert classify(w, [book["post"]])[book["post"]] is None, "its reply shows, so it does"
