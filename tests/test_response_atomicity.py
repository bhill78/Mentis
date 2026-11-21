"""C1b T1-T4 at the actual worker door, on disposable fixture Brains."""
import copy
import json
import sqlite3
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest

from mentis.operational import completion
from mentis.web import dispatch
from mentis.worker import CAPABILITY_HEADER, _operate
from mentis.web import _surface
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.decision_descriptors import question
from tests.respond_grant import bind_run


def mint(world, grant):
    auth = world['state'].agents.authority
    auth.authorise_for(grant['instance'], {**grant, 'operations': grant.get('operations')})
    return auth._grant(grant['instance'], world['state'].path)


def door(world, token, op='respond', **args):
    req = urllib.request.Request(world['base'] + '/api/worker', method='POST',
        data=json.dumps({'op': op, 'args': args}).encode(),
        headers={'Content-Type': 'application/json', CAPABILITY_HEADER: token})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as response:
        return response.code, json.load(response)


def counts(world):
    # Count every durable table, including chain, deliveries and keyed receipts.
    with sqlite3.connect(world['root'] + '/corpus.db') as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {t: db.execute('SELECT count(*) FROM "' + t + '"').fetchone()[0] for t in tables}


@pytest.fixture()
def carrying(world):
    _, _, grant = _coordinator(world, a_conversation(world))
    return grant


@pytest.mark.parametrize('bad', ['absent', 'null', 'unknown', 'not-start', 'execution',
                                'request', 'turn', 'conversation', 'non-string'])
def test_identity_validation_writes_nothing(world, carrying, bad):
    cv, grant = world['cv'], dict(carrying)
    if bad == 'absent':
        grant.pop('run')
    elif bad == 'null':
        grant['run'] = None
    elif bad == 'unknown':
        grant['run'] = 'opr-unknown'
    elif bad == 'not-start':
        grant['run'] = grant['expectation']
    elif bad == 'non-string':
        grant['run'] = ['not an identity']
    else:
        start = cv._act(grant['run'])
        values = dict(actor=grant['participant'], act='execution-started',
                      execution=grant['instance'], caused_by=grant['expectation'],
                      turn=start['turn'], conversation=grant['conversation'])
        values[{'execution': 'execution', 'request': 'caused_by', 'turn': 'turn',
                'conversation': 'conversation'}[bad]] = 'wrong'
        grant['run'] = cv.record_act(**values)
    token = mint(world, grant)
    before = counts(world)
    status, got = door(world, token, text='answer', run=carrying['run'],
                       outcome={'result': 'met', 'approval': {'mode': 'create', 'questions': [question()]}})
    assert status == 403 and 'identity-validation' in json.dumps(got), got
    assert counts(world) == before


def payload(world, grant, mode):
    if mode in ('create', 'existing'):
        pending = _operate(_surface(world['state']), 'request_decision', question('Inspect the chart?'), grant)
        approval = ({'mode': 'existing', 'form': pending['form'], 'questions': [pending['expectation']]}
                    if mode == 'existing' else {'mode': 'create', 'questions': [question()]})
        return {'parts': [{'type': 'text', 'text': 'Prepared chart.'}],
                'outcome': {'result': 'partly', 'summary': 'prepared', 'approval': approval},
                'results': [world['cv']._act(grant['expectation'])['turn']]}
    if mode == 'malformed':
        return {'text': 'Prepared.\n\n```outcome\nresult: invalid\n```'}
    return {'text': 'Prepared without a claim.'}


@pytest.mark.parametrize('mode', ['create', 'existing', 'nonclaiming', 'malformed'])
def test_replay_and_second_calls_preserve_all_identities(world, carrying, mode):
    args, token = payload(world, carrying, mode), mint(world, carrying)
    status, first = door(world, token, **args, op_key='lost-ack')
    assert status == 200, first
    before = counts(world)
    status, replay = door(world, token, **args, op_key='lost-ack')
    assert status == 200 and replay['replayed']
    assert {k: v for k, v in replay.items() if k not in ('replayed', 'op_key')} == first
    assert counts(world) == before
    for update in ({'op_key': 'new'}, {'op_key': 'changed', 'text': 'other', 'parts': None}, {}):
        status, refused = door(world, token, **{**args, **update})
        assert status == 403 and 'already answered' in json.dumps(refused), refused
        assert counts(world) == before


@pytest.mark.parametrize('field', ['parts', 'claim', 'approval', 'results'])
def test_changed_descriptor_under_same_key_conflicts(world, carrying, field):
    args = payload(world, carrying, 'create')
    token = mint(world, carrying)
    assert door(world, token, **args, op_key='same')[0] == 200
    before, changed = counts(world), copy.deepcopy(args)
    if field == 'parts':
        changed['parts'][0]['text'] = 'different'
    elif field == 'claim':
        changed['outcome']['summary'] = 'different'
    elif field == 'approval':
        changed['outcome']['approval']['questions'][0]['question'] = 'Different action?'
    else:
        changed['results'] = []
    status, got = door(world, token, **changed, op_key='same')
    assert status == 403 and 'different respond' in json.dumps(got), got
    assert counts(world) == before


@pytest.mark.parametrize('keys', [('a', 'b'), (None, None), ('a', None)])
@pytest.mark.parametrize('mode', ['create', 'existing'])
def test_distinct_concurrent_answers_have_one_atomic_winner(world, carrying, keys, mode, monkeypatch):
    args, token = payload(world, carrying, mode), mint(world, carrying)
    barrier = threading.Barrier(2)
    import mentis.web as web
    original_surface = web._surface
    def synchronized_surface(st):
        surface = original_surface(st)
        barrier.wait(10)
        return surface
    # Both HTTP requests reach the write door before either opens its
    # transaction. The outcome cannot depend on sequential request arrival.
    monkeypatch.setattr(web, '_surface', synchronized_surface)
    def call(i):
        return door(world, token, **{**args, 'parts': [{'type': 'text', 'text': f'answer {i}'}],
                                    **({'op_key': keys[i]} if keys[i] else {})})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(call, range(2)))
    assert sorted(s for s, _ in results) == [200, 403], results
    cv = _surface(world['state']).cv
    answers = [a for a in cv.corpus.operational(act='turn-said')
               if (a.get('detail') or {}).get('run') == carrying['run']]
    assert len(answers) == 1
    claim = completion.claims_of(cv, carrying['expectation'])
    assert len(claim) == 1 and claim[0]['detail']['reply_turn'] == answers[0]['turn']
    assert len(cv.decision_forms_on(answers[0]['turn'])) == 1
    form = cv.decision_form(cv.decision_forms_on(answers[0]['turn'])[0])
    assert len(form['questions']) == (2 if mode == 'create' else 1)


@pytest.mark.parametrize('keyed', [False, True])
@pytest.mark.parametrize('point', ['turn', 'provenance', 'attachment', 'claim', 'reconcile'])
@pytest.mark.parametrize('mode', ['create', 'existing'])
def test_fault_after_append_rolls_back_answer_forms_claim_and_receipt(
        world, carrying, keyed, point, mode, monkeypatch):
    args, token = payload(world, carrying, mode), mint(world, carrying)
    cv = _surface(world['state']).cv
    owner, name = {'turn': (cv, 'say'), 'provenance': (cv, 'record_act'),
                   'attachment': (cv, 'attach_pending_forms'), 'claim': (completion, 'claim'),
                   'reconcile': (completion, 'reconcile')}[point]
    original = getattr(owner, name)
    def fail(*a, **kw):
        got = original(*a, **kw)
        if point != 'provenance' or kw.get('act') == 'turn-said':
            raise RuntimeError('C1b injected after ' + point)
        return got
    before = counts(world)
    with monkeypatch.context() as patch:
        patch.setattr(owner, name, fail)
        status, got = door(world, token, **args, **({'op_key': 'retry'} if keyed else {}))
    assert status == 400 and 'C1b injected' in json.dumps(got), got
    assert counts(world) == before
    status, got = door(world, token, **args, **({'op_key': 'retry'} if keyed else {}))
    assert status == 200 and got['claim'] and not got.get('replayed'), got


def test_resumed_run_old_receipt_and_late_old_answer_cannot_own_new_start(world, carrying):
    cv, grant = world['cv'], carrying
    token = mint(world, grant)
    status, first = door(world, token, text='same text', op_key='old')
    assert status == 200, first
    # Existing receipts are read before new-write identity validation. Even
    # an old fixture grant lacking run may replay, and acquires no ownership.
    invalid = {**grant, 'run': None}
    before = counts(world)
    status, old = door(world, mint(world, invalid), text='same text', op_key='old')
    assert status == 200 and old['turn'] == first['turn'] and old['replayed']
    assert counts(world) == before
    new = bind_run(cv, grant)
    token = mint(world, new)
    before = counts(world)
    status, replay = door(world, token, text='same text', op_key='old')
    assert status == 200 and replay['turn'] == first['turn'] and replay['replayed']
    assert counts(world) == before
    def owned(g):
        return dispatch._already_answered(cv, execution=g['instance'], expectation=g['expectation'],
            request_turn=cv._act(g['expectation'])['turn'], since=g['run'])
    assert owned(new) is None
    status, second = door(world, token, text='same text', op_key='new')
    assert status == 200 and second['turn'] != first['turn'], second
    assert owned(new) == second['turn'] and owned(grant) == first['turn']
    # A separately bound old run may finish late, after the new start.
    late = bind_run(cv, grant)
    fresh = bind_run(cv, grant)
    assert door(world, mint(world, late), text='late old answer')[0] == 200
    assert owned(fresh) is None
    status, answer = door(world, mint(world, fresh), text='fresh answer')
    assert status == 200 and owned(fresh) == answer['turn']


def test_caller_identity_cannot_override_grant_and_post_write_hooks_are_outside(world, carrying, monkeypatch):
    cv = _surface(world['state']).cv
    from mentis.conversation import render_check
    from mentis.web import prose_decisions
    seen = []
    original = cv.say
    def say(*a, **kw):
        seen.append(('write', cv.corpus._store._conn.in_transaction))
        return original(*a, **kw)
    monkeypatch.setattr(cv, 'say', say)
    original_check = render_check.of_turn
    def check(*a, **kw):
        seen.append(('render', cv.corpus._store._conn.in_transaction))
        return original_check(*a, **kw)
    monkeypatch.setattr(render_check, 'of_turn', check)
    monkeypatch.setattr(prose_decisions, 'raise_from_reply', lambda *a, **kw:
                        seen.append(('prose', cv.corpus._store._conn.in_transaction)))
    status, out = door(world, mint(world, carrying), text='useful answer', run='caller-selected',
                       instance='someone-else', expectation='different')
    assert status == 200, out
    assert cv._act(out['said_act'])['detail']['run'] == carrying['run']
    assert seen == [('write', True), ('render', False), ('prose', False)]


def test_actual_ordinary_and_manual_grants_still_do_not_expose_respond(world, monkeypatch):
    from mentis.execution import RunResult
    from mentis.web import dispatch
    import mentis.web as web
    from tests._loop import say
    st, cv = world['state'], world['cv']
    refused = []
    def perform(spec):
        token = st.agents.authority.grant_of(spec.run_id)
        before = counts(world)
        refused.append(door(world, token, text='not granted'))
        assert counts(world) == before
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason='end_turn', text='ordinary aggregate answer')
    st.agents.execution.script = {'codex': perform}
    monkeypatch.setattr(web, 'dispatch_soon', lambda st, **kw: dispatch.dispatch(st, **kw))
    agent = cv.create_participant('@Ordinary')
    out = say(world, a_conversation(world), 'Please summarize', action='ask-participant',
              dispatch=[{'participant': agent, 'work': 'summarize', 'runtime': 'codex'}])
    assert refused[0][0] == 403
    start = next(a for a in cv.history(caused_by=out['expectations'][0]) if a['act'] == 'execution-started')
    end = cv.run_end(start['id'])
    assert end['detail']['response_owner'] == 'dispatch-completion' and end['detail']['reply_turn']
    token, _ = st.agents.authority.grant_session(st.path, runtime='codex', participant=agent)
    before = counts(world)
    status, got = door(world, token, text='manual cannot respond',
                       authorized_by={'source': 'owner-in-chat'})
    assert status == 403, got
    assert counts(world) == before


@pytest.mark.parametrize('keyed', [False, True])
def test_pre_answer_helper_append_is_in_the_rollback(world, carrying, monkeypatch, keyed):
    cv, token = _surface(world['state']).cv, mint(world, carrying)
    monkeypatch.setattr(cv, 'follow_ups_unseen', lambda *a: ['follow-up'])
    original = cv.record_act
    def fail(*a, **kw):
        got = original(*a, **kw)
        if kw.get('act') == 'follow-up-shown':
            raise RuntimeError('C1b injected after pre-answer helper')
        return got
    monkeypatch.setattr(cv, 'record_act', fail)
    before = counts(world)
    status, got = door(world, token, text='prepared', fulfils=True,
                       **({'op_key': 'helper'} if keyed else {}))
    assert status == 400 and 'C1b injected' in json.dumps(got), got
    assert counts(world) == before
