"""A PAGE IS A PAGE OF WHAT THERE IS TO READ (owner, 2026-11-27,
ent-15a36a065eb8: "the initial page looks empty").

Folding a Magnet's own bookkeeping out of its Conversation (5788d855) is
right, and left the first page of a busy Magnet reading as nothing but
"30 posts folded. Show them.": the batch `/api/conversations/<id>?batch=30`
takes -- the one Quiet reads a Conversation through -- was the newest 30
UNITS, and on that Magnet all thirty were bookkeeping.

The batch is counted in units the view will DRAW now (`_unfolded_lo`), the
way `latest._sifted` already counts a Latest page. What folds is still IN
the batch, in its place: the fold is the view's to draw, it says how many it
holds, and it shows them where the reader asks.

The classifier has its own tests (`test_conversation_mechanics`); it is
named directly here, so the window arithmetic is what is under test.
"""
import pytest

from mentis.web import BATCH_FOLD_SCAN, _batch_asked


class _Stub:
    """Enough of `_State` for `_unfolded_lo`: it reads `st.cv` and hands it
    to the classifier, which is named directly below."""
    cv = object()


@pytest.fixture()
def folding(monkeypatch):
    """Name which units fold, as the view's fold would."""
    def set_to(folds):
        from mentis.conversation import agent_work
        monkeypatch.setattr(agent_work, "classify", lambda cv, ids, owner: {
            i: ({"kind": "mechanics", "why": "Perspective reconciled",
                 "to": None, "to_name": None} if i in folds else None)
            for i in ids})
        monkeypatch.setattr("mentis.operational.work_overview.owner_of",
                            lambda cv: "@brian")
    return set_to


def _units(n):
    return [{"turn": f"t{i}", "number": i + 1} for i in range(n)]


def _one(**kw):
    return lambda k, default=None: kw.get(k, default)


def test_the_newest_batch_holds_what_there_is_to_read(folding):
    units = _units(60)
    # the newest 30 units are all bookkeeping: the batch as it was would
    # have been thirty folded units and nothing to read
    folding({u["turn"] for u in units[30:]})
    got, refusal = _batch_asked(_one(batch="10"), units, _Stub())
    assert refusal is None
    window = units[got["lo"]:got["hi"]]
    drawn = [u for u in window if u["turn"] in {f"t{i}" for i in range(30)}]
    assert len(drawn) == 10, f"{len(drawn)} to read of {len(window)} units"
    # and what folds is still there, in its place, for the view's own fold
    assert got["lo"] == 20 and got["hi"] == 60


def test_a_batch_that_folds_nothing_is_exactly_what_it_was(folding):
    units = _units(60)
    folding(set())
    got, _ = _batch_asked(_one(batch="10"), units, _Stub())
    assert (got["lo"], got["hi"], got["mode"]) == (50, 60, "recent")


def test_without_a_state_the_batch_is_exactly_what_it_was(folding):
    """`_batch_asked` is still the plain window where no view asked for
    one: nothing reaches past what was asked without `st`."""
    units = _units(60)
    folding({u["turn"] for u in units[30:]})
    got, _ = _batch_asked(_one(batch="10"), units)
    assert (got["lo"], got["hi"]) == (50, 60)


def test_paging_back_counts_the_same_way(folding):
    units = _units(60)
    folding({u["turn"] for u in units[20:50]})
    got, refusal = _batch_asked(
        _one(batch="10", before="t50"), units, _Stub())
    assert refusal is None
    assert got["mode"] == "before" and got["hi"] == 50
    window = units[got["lo"]:got["hi"]]
    assert len([u for u in window
                if int(u["turn"][1:]) < 20]) == 10, window


def test_a_batch_at_a_named_unit_is_untouched(folding):
    """`after` and `around` sit where the reader pointed; widening them
    would move the page away from what was asked for."""
    units = _units(60)
    folding({u["turn"] for u in units})
    after, _ = _batch_asked(_one(batch="10", after="t10"), units, _Stub())
    assert (after["lo"], after["hi"]) == (11, 21)
    around, _ = _batch_asked(_one(batch="10", around="t30"), units, _Stub())
    assert (around["lo"], around["hi"]) == (25, 35)


def test_a_conversation_folded_all_the_way_down_reaches_its_start(folding):
    units = _units(60)
    folding({u["turn"] for u in units})
    got, _ = _batch_asked(_one(batch="10"), units, _Stub())
    assert (got["lo"], got["hi"]) == (0, 60), "the whole of it, once"


def test_the_reach_past_what_folds_is_bounded(folding):
    """A very long Conversation with nothing to read stops at the bound
    rather than reading itself whole."""
    units = _units(BATCH_FOLD_SCAN + 200)
    folding({u["turn"] for u in units})
    got, _ = _batch_asked(_one(batch="10"), units, _Stub())
    assert got["hi"] - got["lo"] <= BATCH_FOLD_SCAN + 10
    assert got["lo"] == len(units) - 10 - BATCH_FOLD_SCAN


def test_a_whole_read_is_still_whole(folding):
    units = _units(60)
    folding({u["turn"] for u in units[30:]})
    got, _ = _batch_asked(_one(batch="all"), units, _Stub())
    assert (got["lo"], got["hi"], got["mode"]) == (0, 60, "all")
    zero, _ = _batch_asked(_one(batch="0"), units, _Stub())
    assert (zero["lo"], zero["hi"]) == (60, 60), "no units asked for"
