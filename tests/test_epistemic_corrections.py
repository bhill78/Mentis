"""Regression assertions for B1-B6, using the reviewer scenarios."""
import pytest
from tests.test_epistemic_learning import (
    built, server, a_request, helper, hand_out, close, shipped_then_grown,
    opened_acts, OBJECTIVE, EXPANSION, L)


def test_keyed_hook_still_inside_transaction(server, monkeypatch):
    _, op = server.session()
    _, trunk = a_request(op, 'Ordinary completion')
    original = L.after_outcome
    observed = []
    def watch(cv, expectation, **kw):
        observed.append(cv.corpus._store._conn.in_transaction)
        return original(cv, expectation, **kw)
    monkeypatch.setattr(L, 'after_outcome', watch)
    close(op, trunk, op_key='review-transaction')
    assert observed == [False]


def test_key_write_failure_commits_partial_evaluation_and_allows_duplicate(server, monkeypatch):
    from mentis import opkeys
    _, op = server.session()
    cv = server.st.cv
    trunk = shipped_then_grown(op)['trunk']
    original = opkeys.remember
    def fail_learning(cv, owner, name, *args, **kw):
        if name.startswith('learning:'):
            raise RuntimeError('review injected learning key-write failure')
        return original(cv, owner, name, *args, **kw)
    monkeypatch.setattr(opkeys, 'remember', fail_learning)
    first = close(op, trunk, op_key='review-partial')
    assert first['learning'].get('failed')
    assert len(opened_acts(cv)) == 0
    assert not [s for s in server.sent if cv._act(s.get('expectation'))['detail'].get(L.MARK)]
    assert not [a for a in cv.corpus.operational(act='operation-keyed')
                if (a['detail'] or {}).get('op', '').startswith('learning:')]
    monkeypatch.setattr(opkeys, 'remember', original)
    close(op, trunk, op_key='review-next')
    assert len(opened_acts(cv)) == 1


def test_new_evidence_same_request_suppressed(server):
    _, op = server.session()
    cv = server.st.cv
    made = shipped_then_grown(op)
    first = close(op, made['trunk'])
    assert first['learning']['evaluated']
    new = hand_out(op, made['who'], 'Now also build backup restore infrastructure',
                   made['conversation'], made['trunk'])
    later = close(op, made['trunk'])
    assert any(new in s['evidence'] for s in later['learning']['fired'])
    assert later['learning']['evaluated']
    assert len(opened_acts(cv)) == 2


def test_expansion_before_first_met_claim_missed(server):
    _, op = server.session()
    cid, trunk = a_request(op, OBJECTIVE)
    who = helper(op, cid, trunk)
    hand_out(op, who, EXPANSION, cid, trunk)
    got = close(op, trunk, outcome='Built permanent deletion and a schema migration')
    assert any(s['signal'] == 'scope-expansion' for s in got['learning']['fired'])
    assert got['learning']['evaluated']


def test_unchanged_replay_op_key_dispatches_once(server):
    _, op = server.session()
    cv = server.st.cv
    trunk = shipped_then_grown(op)['trunk']
    first = close(op, trunk, op_key='review-replay')
    count = len(server.sent)
    replay = close(op, trunk, op_key='review-replay')
    assert replay['replayed']
    assert len(server.sent) == count
    assert len(opened_acts(cv)) == 1


def test_any_owner_followup_masks_unrelated_expansion(server):
    from mentis.conversation import text
    _, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, OBJECTIVE)
    who = helper(op, cid, trunk)
    turn = cv.say(cid, cv._act(trunk)['actor'], [text('Also fix a typo in the Archive button label')])
    follow = cv.expect(turn, of=None, kind='result', by=cv._act(trunk)['actor'])
    cv.attach_follow_up(follow, trunk, by=cv._act(trunk)['actor'])
    close(op, trunk)
    grew = hand_out(op, who, EXPANSION, cid, trunk)
    got = close(op, trunk)
    assert any(grew in s['evidence'] for s in got['learning']['fired'])
    assert not any(r['ref'] == grew and r['reason'] == 'owner-authorized'
                   for r in got['learning']['ruled_out'])


def test_two_signals_final_ending_loses_second_evaluation(server):
    from mentis.operational import completion
    _, op = server.session()
    cv = server.st.cv
    trunk = shipped_then_grown(op)['trunk']
    for n in (1, 2):
        completion.claim(cv, trunk, {'result':'not-met', 'summary':f'correction {n}'},
                         actor=cv._act(trunk)['actor'], via='review')
    got = L.after_run(server.st, trunk, start=lambda st, **kw: None)
    assert {s['signal'] for s in got['fired']} == {'scope-expansion', 'repeated-correction'}
    assert len(got['opened']) == 1
    assert got['deduped'] == []
    assert 'repeated-correction' in got['dispatches'][0]['work']
    assert L.consider(cv, trunk, trigger='run-ended')['opened'] == []


def test_escaping_hook_error_rolls_back_keyed_outcome(server, monkeypatch):
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, 'Ordinary outcome whose learning hook fails')
    def boom(*args, **kw):
        raise RuntimeError('review hook failure')
    monkeypatch.setattr(L, 'after_outcome', boom)
    status, got = op('record_outcome', expectation=trunk, result='done',
                     outcome='Finished ordinary work', op_key='review-rollback')
    assert status == 200 and got['learning']['failed']
    assert [a for a in cv._children(trunk)
                if a['act'] in ('manual-session-outcome-recorded', 'outcome-claimed')]


def test_repeated_runtime_failures_without_claims_missed(server):
    from mentis.web import dispatch as D
    _, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, 'Run browser checks')
    status, prior = op('record_material', kind='note',
                       body={'text':'Runtime unavailable: quota exhausted browser checks failed'})
    assert status == 200
    for n in range(2):
        D._failed_before_start(cv, participant=cv._act(trunk)['actor'],
                               conversation=cid, turn=cv._act(trunk)['turn'],
                               expectation=trunk, stage='selection',
                               exc=RuntimeError('quota exhausted'), requested={})
    got = L.after_run(server.st, trunk, start=lambda st, **kw: None)
    assert any(s['signal'] == 'repeated-failure' for s in got['fired'])


def test_brief_bounds_withholding_and_owner_adoption(server):
    from mentis.conversation import ladder_writes
    from mentis.web import _routes
    _, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, 'quartz zircon basalt boundary knowledge')
    owner = cv.resolve_participant('@brian')
    ids = []
    for n in range(16):
        status, got = op('record_material', kind='lesson', basis=[cid],
                         body={'text': f'quartz zircon basalt boundary knowledge {n}'})
        assert status == 200
        ids.append(got['entry'])
        if n < 8:
            got = ladder_writes.owner_act(cv, got['entry'], 'adopt',
                                          {'because':'fixture owner adopted'}, by=owner)
    # A matching entry that is no longer eligible must stay out of both payload tiers.
    deleted = _routes(server.st, f'/api/entries/{ids[-1]}/delete', {},
                      {'attributed_to': owner, 'because':'fixture owner deletion'}, 'POST')
    assert 'error' not in deleted, deleted
    status, got = op('brief', conversation=cid, work='quartz zircon basalt boundary knowledge', detail=True)
    assert status == 200
    known = got['knowledge']
    assert len(known['adopted']) == len(known['experience']) == 5
    assert ids[-1] not in [r['id'] for tier in ('adopted','experience') for r in known[tier]]
    assert any(w['tier'] == 'adopted' for w in known['withheld'])
    assert any(w['tier'] == 'experience' for w in known['withheld'])
    with pytest.raises(ValueError, match='only the owner'):
        ladder_writes.owner_act(cv, ids[-2], 'adopt', {'because':'attempt'},
                                by=cv._act(trunk)['actor'])


def test_challenged_rule_actually_delivered_but_not_named_missed(server):
    from mentis.conversation import ladder_writes
    _, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, 'Review integration test results')
    status, got = op('record_material', kind='rule', body={
        'text':'Run the full suite for every integration', 'about':'integration'})
    assert status == 200
    rule = got['entry']
    owner = cv.resolve_participant('@brian')
    ladder_writes.owner_act(cv, rule, 'adopt',
                            {'because':'fixture owner adoption',
                             'scope':{'where':cid}}, by=owner)
    status, challenged = op('challenge', target=rule, because='Targeted tests are sufficient')
    assert status == 200
    comp = cv.compose(conversation=cid, participant=cv._act(trunk)['actor'], question='integration')
    assert rule in comp.governing_ids()
    assert rule not in cv.governed_named(trunk)
    got = close(op, trunk)
    assert [s for s in got['learning']['fired'] if s['signal'] == 'contested-basis']


def test_second_learning_key_failure_rolls_back_all_signals(server, monkeypatch):
    from mentis import opkeys
    from mentis.operational import completion
    _, op = server.session()
    cv = server.st.cv
    trunk = shipped_then_grown(op)['trunk']
    for n in range(2):
        completion.claim(cv, trunk, {'result': 'not-met', 'summary': f'round {n}'},
                         actor=cv._act(trunk)['actor'], via='test')
    original = opkeys.remember
    calls = []

    def fail_second(cv, owner, name, *args, **kw):
        if name.startswith('learning:'):
            calls.append(name)
            if len(calls) == 2:
                raise RuntimeError('second evidence key failed')
        return original(cv, owner, name, *args, **kw)

    monkeypatch.setattr(opkeys, 'remember', fail_second)
    got = L.after_run(server.st, trunk, start=lambda *a, **kw: pytest.fail('dispatch'))
    assert got['failed'] and len(calls) == 2
    assert opened_acts(cv) == []
    assert not [a for a in cv.corpus.operational(act='operation-keyed')
                if (a['detail'] or {}).get('op', '').startswith('learning:')]


def test_outcome_key_failure_rolls_back_outcome_and_never_runs_learning(server, monkeypatch):
    from mentis import opkeys
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, 'Ordinary outcome')
    original = opkeys.remember

    def fail_outcome(cv, owner, name, *args, **kw):
        if name.startswith('worker:record_outcome:'):
            raise RuntimeError('ordinary key failed')
        return original(cv, owner, name, *args, **kw)

    monkeypatch.setattr(opkeys, 'remember', fail_outcome)
    monkeypatch.setattr(L, 'after_outcome', lambda *a, **kw: pytest.fail('learning'))
    status, got = op('record_outcome', expectation=trunk, result='done',
                     outcome='done', op_key='outcome-key-fault')
    assert status != 200
    assert not [a for a in cv._children(trunk)
                if a['act'] in ('manual-session-outcome-recorded', 'outcome-claimed')]


def test_repeated_runtime_failures_need_no_prior_ladder_material(server):
    from mentis.web import dispatch as D
    _, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, 'Run browser checks')
    for _ in range(2):
        D._failed_before_start(cv, participant=cv._act(trunk)['actor'],
                               conversation=cid, turn=cv._act(trunk)['turn'],
                               expectation=trunk, stage='selection',
                               exc=RuntimeError('runtime missing'), requested={})
    got = L.consider(cv, trunk, trigger='run-ended')
    assert any(s['signal'] == 'repeated-failure' for s in got['fired'])
    assert got['evaluated']
    unchanged = L.consider(cv, trunk, trigger='run-ended')
    assert not unchanged['evaluated']
    D._failed_before_start(cv, participant=cv._act(trunk)['actor'],
                           conversation=cid, turn=cv._act(trunk)['turn'],
                           expectation=trunk, stage='selection',
                           exc=RuntimeError('another attempt'), requested={})
    assert L.consider(cv, trunk, trigger='run-ended')['evaluated']


def test_trunk_scope_expansion_before_first_completion(server):
    _, op = server.session()
    _, trunk = a_request(op, OBJECTIVE)
    got = close(op, trunk, outcome='Implemented permanent deletion and a migration')
    assert any(s['signal'] == 'scope-expansion' for s in got['learning']['fired'])
    assert got['learning']['evaluated']


def test_persona_carried_challenge_is_in_current_brief(server):
    _, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, 'Review integration results')
    owner = cv.resolve_participant('@brian')
    persona = cv.corpus.create_and_establish(
        kind='persona', body={'name': 'Correction Reviewer', 'behaviour': 'Review work.', 'about': ''},
        attributed_to=owner)
    rule = cv.corpus.create_and_establish(
        kind='rule', body={'text': 'Run all checks', 'about': 'integration'}, attributed_to=owner)
    cv.place(rule, where=persona, by=owner, because='fixture Persona carries this rule')
    # Persona is recorded on the request in real record_request; use a fresh
    # request with that ordinary detail rather than changing an existing act.
    from mentis.conversation import text
    turn = cv.say(cid, cv._act(trunk)['actor'], [text('Review integration results')])
    trunk = cv.expect(turn, of=cv._act(trunk)['actor'], kind='result', by=cv._act(trunk)['actor'],
                      detail={'manual_session': True, 'persona': persona})
    assert op('challenge', target=rule, because='Targeted checks suffice')[0] == 200
    got = close(op, trunk)
    assert any(rule in s['evidence'] for s in got['learning']['fired']
               if s['signal'] == 'contested-basis')


def test_delivered_challenged_rule_is_used_even_after_placement_removed(server):
    from mentis.conversation import Composition, Component
    _, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, 'Review integration results')
    actor = cv._act(trunk)['actor']
    owner = cv.resolve_participant('@brian')
    rule = cv.corpus.create_and_establish(
        kind='rule', body={'text': 'Run all checks', 'about': 'integration'}, attributed_to=owner)
    # Historical delivery is sufficient even though it is not currently placed.
    began = cv.record_act(actor=actor, act='execution-started', conversation=cid,
                          execution='fixture-instance', caused_by=trunk)
    ex = cv.begin_execution(participant=actor, conversation=cid, for_expectation=trunk)
    comp = Composition((Component('rule', rule, 'invocation:named', 'Run all checks',
                                   'named', 'integration', 'governance'),), (), ())
    cv.record_delivery(ex, comp, mechanism='test')
    cv.end_execution(ex.reference)
    cv.record_act(actor=actor, act='result-returned', conversation=cid,
                  execution='fixture-instance', caused_by=began)
    assert op('challenge', target=rule, because='Targeted checks suffice')[0] == 200
    got = close(op, trunk)
    assert any(rule in s['evidence'] for s in got['learning']['fired']
               if s['signal'] == 'contested-basis')
