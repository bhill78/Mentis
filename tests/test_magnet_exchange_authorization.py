"""The owner authorizes the actual asking Turn atomically, before dispatch."""
from copy import deepcopy

import pytest

from mentis.fluid import commands, message_context as M
from mentis.fluid.inspect import brain_key
from mentis.magnet import scope as S
from tests._loop import world  # noqa: F401
from tests.test_agent_request_routing import a_magnet, own_conversation_of, post
from tests.test_magnet_message_boundary import request, send


OPENS = [{"kind": "runtime-web-search"}, {"kind": "collection", "collection": "col-extra"}]


def ready(w):
    mid = a_magnet(w, sources=[])
    own_conversation_of(w, mid)
    return mid


@pytest.mark.parametrize("action", ["ask-mentis", "ask-participant"])
def test_authorized_before_dispatch_and_only_on_actual_turn(world, monkeypatch, action):
    mid = ready(world)
    cv = world["cv"]
    seen = []

    def hand_on(st, start):
        turn = start["turn"]
        seen.append(turn)
        assert S.authorization(cv, S.parsed("magnet:" + mid), turn) == tuple(OPENS)
        assert M.authorized(cv, M.accepted(cv, turn=turn)) == tuple(OPENS)
        assert cv._c.operational(act=commands.REQUEST_ROUTED, turn=turn)

    monkeypatch.setattr(commands, "_hand_on", hand_on)
    b = request(world, mid, action=action, magnet_authorization={"opens": OPENS})
    status, got = send(world, b)
    assert status == 200, got
    assert seen == [got["post"]]
    acts = cv._c.operational(act=S.AUTHORIZED)
    assert len(acts) == 1 and acts[0]["turn"] == got["post"]
    assert acts[0]["actor"] == b["author"] and not acts[0].get("execution")
    assert cv._c.read([got["post"]])[0]["body"]["parts"] == b["parts"]
    # The next exchange is distinct, and a synthesis reads no authorization.
    monkeypatch.setattr(commands, "_hand_on", lambda *args: None)
    status, nxt = send(world, request(world, mid, action=action, op="next"))
    assert status == 200, nxt
    assert S.authorization(cv, S.parsed("magnet:" + mid), nxt["post"]) == ()
    assert S.authorization(cv, S.parsed("magnet-synthesis:" + mid), got["post"]) == ()


@pytest.mark.parametrize("bad", [None, [], {}, {"opens": []}, {"opens": "web"},
    {"opens": [{"kind": "unknown"}]}, {"opens": [{"kind": "collection"}]},
    {"opens": [{"kind": "runtime-web-search", "collection": "col-extra"}]},
    {"opens": [OPENS[0], OPENS[0]]}, {"opens": [OPENS[0]] * 5},
    {"opens": OPENS, "turn": "ent-someotherturn"}, {"opens": OPENS, "author": "ent-fake"}])
def test_malformed_or_cross_turn_input_records_nothing(world, bad):
    mid = ready(world)
    b = request(world, mid, action="ask-participant", magnet_authorization=bad)
    before = world["cv"]._c.advance()
    status, got = send(world, b)
    assert status in (400, 422), got
    assert world["cv"]._c.advance() == before
    assert not world["sent"]
    assert not world["cv"]._c.operational(act=S.AUTHORIZED)


def test_refused_authorizer_rolls_back_post_request_and_route(world, monkeypatch):
    mid = ready(world)
    b = request(world, mid, action="ask-participant", magnet_authorization={"opens": OPENS})
    before = world["cv"]._c.advance()
    original = S.authorize

    def refuse_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise S.Refused("fixture refusal after authorization")

    monkeypatch.setattr(S, "authorize", refuse_after_write)
    assert send(world, b)[0] == 422
    assert world["cv"]._c.advance() == before
    assert not world["sent"]
    assert not world["cv"]._c.operational(act=S.AUTHORIZED)
    monkeypatch.setattr(S, "authorize", original)
    status, got = send(world, b)
    assert status == 200, got
    assert len(world["sent"]) == 1


def test_owner_brain_and_managed_route_required(world):
    mid = ready(world)
    b = request(world, mid, action="ask-participant", magnet_authorization={"opens": OPENS})
    other = world["cv"].create_participant("@NotOwner")
    before = world["cv"]._c.advance()
    assert send(world, {**b, "author": other})[0] == 403
    assert post(world, b, headers={})[0] == 409
    # A workspace with no Magnet destination cannot carry this authority.
    from tests.test_agent_request_routing import a_workspace
    wid = a_workspace(world)
    assert send(world, {**b, "from": {"workspace": wid}})[0] == 400
    assert world["cv"]._c.advance() == before
    assert not world["sent"]


def test_replay_is_unchanged_authority_and_cannot_widen_an_earlier_send(world):
    mid = ready(world)
    b = request(world, mid, action="ask-participant", magnet_authorization={"opens": OPENS})
    status, first = send(world, b)
    assert status == 200, first
    before = world["cv"]._c.advance()
    status, again = send(world, deepcopy(b))
    assert status == 200 and again["post"] == first["post"] and again["replayed"]
    assert world["cv"]._c.advance() == before
    assert len(world["cv"]._c.operational(act=S.AUTHORIZED)) == 1
    assert len(world["sent"]) == 1
    assert send(world, {**b, "magnet_authorization": {"opens": [OPENS[0]]}})[0] == 409
    without = {k: v for k, v in b.items() if k != "magnet_authorization"}
    assert send(world, without)[0] == 409
    status, ordinary = send(world, {**without, "op": "ordinary"})
    assert status == 200, ordinary
    assert send(world, {**b, "op": "ordinary"})[0] == 409
    assert S.authorization(world["cv"], S.parsed("magnet:" + mid), ordinary["post"]) == ()


def test_record_only_and_missing_conversation_fail_closed(world):
    mid = a_magnet(world, sources=[])
    assert send(world, request(world, mid, magnet_authorization={"opens": OPENS}))[0] == 400
    b = request(world, mid, action="ask-participant", magnet_authorization={"opens": OPENS})
    before = world["cv"]._c.advance()
    status, got = send(world, b)
    assert status == 422 and "Conversation" in got["error"]
    assert world["cv"]._c.advance() == before
    assert not world["sent"]


def test_saved_question_cannot_be_widened_by_the_send_route(world):
    from mentis.magnet import perspectives as P
    mid = ready(world)
    created = P.command(world["state"], mid, None, "create", {
        "brain": brain_key(world["cv"]._c), "op": "create-question",
        "name": "A saved question", "question": "What is collected?"})
    selector = {"version": 1, "mode": "ordinary", "references": [],
        "configuration_digest": M.digest(M.definition_body(commands._magnet_config(world["state"], mid))),
        "perspective": {"id": created["perspective"], "question_ref": created["question"]["ref"],
                        "question_digest": created["question"]["digest"]}}
    b = request(world, mid, action="ask-participant", magnet_context=selector,
                magnet_authorization={"opens": OPENS})
    before = world["cv"]._c.advance()
    status, got = send(world, b)
    assert status == 422 and got["code"] == "authorization-refused", got
    assert world["cv"]._c.advance() == before
    assert not world["sent"]


def test_actual_execution_is_told_only_its_own_authorization(world):
    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from tests._loop import script_every_backend
    mid = ready(world)
    prompts = []

    def perform(spec):
        prompts.append(spec.prompt)
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         text="Fixture answer", stop_reason="end_turn", timing={"prompt_sent": 1.0})

    script_every_backend(world["state"].agents, perform)
    b = request(world, mid, action="ask-participant", magnet_authorization={"opens": OPENS})
    assert send(world, b)[0] == 200
    assert D.dispatch(world["state"], **world["sent"][0])["ok"]
    assert "authorized THIS ONE EXCHANGE" in prompts[0]
    assert "collection col-extra" in prompts[0]
    assert send(world, request(world, mid, action="ask-participant", op="ordinary-next"))[0] == 200
    assert D.dispatch(world["state"], **world["sent"][1])["ok"]
    assert "authorized THIS ONE EXCHANGE" not in prompts[1]
