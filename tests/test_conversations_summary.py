"""`/api/conversations` reads each relation once for every Conversation.

The batched rows (`Conversations.conversation_summaries`) must be exactly the
rows the per-Conversation reads gave (`_conversation_summaries_each`), over a
world with renamed Conversations and Topics, ended links and filings, edited
and deleted Turns, replies, observed delivery failures and a live execution.
"""

from mentis.conversation import versions
from mentis.spine import store as S
from mentis.web import _State, _routes, fixture


def _text(s):
    return [{"type": "text", "text": s}]


def _world(tmp_path):
    built = fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    cv, who = st.cv, built["who"]
    me, nadia, vera, ada = (who[a] for a in ("@brian", "@Nadia", "@Vera",
                                             "@Ada"))

    a = cv.open_conversation("Alpha", about="first", attributed_to=me)
    b = cv.open_conversation("Beta", attributed_to=me)
    cv.open_conversation("Empty", attributed_to=me)
    for p in (me, nadia, vera):
        cv.join(p, a)
    cv.join(me, b)
    cv.join(me, b)                      # twice: counted once

    t1 = cv.open_topic(a, "Plans", attributed_to=me)
    t2 = cv.open_topic(a, "Risks", attributed_to=me)
    tb = cv.open_topic(b, "Only", attributed_to=me)
    cv.edit_topic(t2, by=me, name="Risks, renamed")

    p1 = cv.say(a, me, _text("to Nadia and Vera"), addressed_to=[nadia, vera])
    p2 = cv.say(a, me, _text("to Ada"), addressed_to=[ada])
    p3 = cv.say(a, me, _text("to Nadia, edited later"), addressed_to=[nadia])
    p4 = cv.say(a, me, _text("to Vera, deleted later"), addressed_to=[vera])
    cv.say(a, nadia, _text("Nadia answers"), replies_to=p1)
    cv.observe(p2, "delivery-failed", detail=f"{ada}: no runtime")
    cv.observe(p1, "delivery-failed", detail=f"{nadia}: but she replied")
    versions.edit(cv, p3, by=me, text="edited")
    versions.delete(cv, p4, by=me)

    q1 = cv.say(b, me, _text("in Beta"), addressed_to=[vera])
    cv.say(b, me, _text("in Beta again"))

    cv.assign_topic(p1, t1)
    cv.assign_topic(p2, t1)
    cv.assign_topic(p3, t2)
    cv.end_filing(p2, t1, by=me)
    cv.link_into(p1, b, by=me)
    cv.link_into(p2, b, by=me)
    cv.unlink(p2, b, by=me)
    cv.assign_topic(p1, tb)             # a linked Turn filed in Beta
    cv.link_into(q1, a, by=me)

    cv.rename_conversation(b, "Beta, renamed", by=me)
    cv.begin_execution(participant=nadia, conversation=a)
    ended = cv.begin_execution(participant=vera, conversation=a)
    cv.end_execution(ended.reference)
    cv.begin_execution(participant=vera, conversation=b)
    return st


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


def test_batched_rows_are_the_per_conversation_rows(tmp_path):
    st = _world(tmp_path)
    cv = st.cv
    live = cv.active_executions()
    new = cv.conversation_summaries(live)
    old = cv._conversation_summaries_each(live)
    assert new == old
    # and the world exercised what it was built to
    by = {r["name"]: r for r in new}
    assert by["Alpha"]["awaiting"] and by["Alpha"]["linked"] == 1
    assert by["Alpha"]["live_executions"] == 1
    assert by["Beta, renamed"]["linked"] == 1
    assert "Risks, renamed" in [t["name"] for t in by["Alpha"]["topics"]]
    assert by["Empty"]["turns"] == 0 and by["Empty"]["last_activity"] is None


def test_route_answers_as_it_did(tmp_path):
    st = _world(tmp_path)
    cv = st.cv
    with cv.reading():
        got = _routes(st, "/api/conversations", {}, None, "GET")
        old = cv._conversation_summaries_each(cv.active_executions())
    assert got == {"conversations": sorted(
        old, key=lambda c: -(c["last_activity"] or 0))}


def test_a_write_during_the_batch_falls_back_to_the_per_conversation_reads(
        tmp_path, monkeypatch):
    st = _world(tmp_path)
    cv = st.cv
    calls = []
    real = cv._conversation_summaries

    def racing(live):
        calls.append(1)
        out = real(live)
        cv.open_conversation(f"written meanwhile {len(calls)}")
        return out

    monkeypatch.setattr(cv, "_conversation_summaries", racing)
    got = cv.conversation_summaries(cv.active_executions())
    assert len(calls) == 3
    monkeypatch.undo()
    assert got == cv._conversation_summaries_each(cv.active_executions())


def test_statements_do_not_grow_with_conversations(tmp_path, monkeypatch):
    """What is left per entry is `presented` resolving an entry that WAS
    edited, renamed or deleted -- as the per-Conversation reads did too.
    Every other relation is one read, however many Conversations there are."""
    st = _world(tmp_path)
    cv = st.cv
    me = cv.participants_named("@brian")[0]
    count = _counting(st, monkeypatch)

    def measure():
        live = cv.active_executions()
        count["n"] = 0
        with cv.reading():
            cv._conversation_summaries_each(live)
        each = count["n"]
        count["n"] = 0
        with cv.reading():
            cv.conversation_summaries(live)
        return each, count["n"]

    before = measure()
    for i in range(20):
        c = cv.open_conversation(f"More {i}", attributed_to=me)
        cv.join(me, c)
        t = cv.open_topic(c, "T", attributed_to=me)
        cv.assign_topic(cv.say(c, me, _text("x"), addressed_to=[me]), t)
    after = measure()
    print(f"/api/conversations statements (per-conversation, batched): "
          f"{before} for {len(cv.all_conversations()) - 20} Conversations, "
          f"{after} for {len(cv.all_conversations())}")
    assert after[1] == before[1]
    assert after[0] > before[0] > before[1]
