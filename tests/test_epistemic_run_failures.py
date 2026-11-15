"""B4's post-start failure correction, using dispatch's recorded lineage."""
import pytest

from tests.test_epistemic_learning import (  # noqa: F401
    built, server, a_request, close, L,
)


def failed_after_start(cv, cid, request, *, detail=None):
    from mentis.web.dispatch import FAILED, STARTED
    actor = cv._act(request)['actor']
    began = cv.record_act(actor=actor, act=STARTED, conversation=cid,
                          turn=cv._act(request)['turn'], execution='fixture-instance',
                          runtime='claude', caused_by=request,
                          because='this work was dispatched here')
    return cv.record_act(actor=actor, act=FAILED, conversation=cid,
                         turn=cv._act(request)['turn'], execution='fixture-instance',
                         runtime='claude', caused_by=began,
                         because='RuntimeError: the run crashed before reporting',
                         detail=detail or {})


@pytest.mark.parametrize('detail', [
    {'traceback': 'perform raised'},
    {'terminal': 'crashed', 'exit_code': 1},
])
def test_post_start_failures_reach_one_evaluation_without_a_claim(server, detail):
    _, op = server.session()
    cv = server.st.cv
    cid, request = a_request(op, 'Run browser checks')
    failures = [failed_after_start(cv, cid, request, detail=detail) for _ in range(2)]
    started = []
    got = L.after_run(server.st, request, start=lambda st, **kw: started.append(kw))
    signal, = [s for s in got['fired'] if s['signal'] == 'repeated-failure']
    assert signal['evidence'] == failures
    assert len(got['opened']) == len(started) == 1
    assert all(ref in started[0]['work'] for ref in failures)
    assert not L.consider(cv, request, trigger='run-ended')['evaluated']
    new = failed_after_start(cv, cid, request, detail=detail)
    later = L.consider(cv, request, trigger='run-ended')
    assert later['evaluated']
    assert any(new in s['evidence'] for s in later['fired'])


def test_mixed_failure_lineages_are_read_in_recorded_order(server):
    from mentis.web import dispatch as D
    _, op = server.session()
    cv = server.st.cv
    cid, request = a_request(op, 'Run browser checks')
    post = failed_after_start(cv, cid, request)
    before = D._failed_before_start(
        cv, participant=cv._act(request)['actor'], conversation=cid,
        turn=cv._act(request)['turn'], expectation=request, stage='selection',
        exc=RuntimeError('a later unavailable runtime'), requested={})
    got = L.consider(cv, request, trigger='run-ended')
    signal, = [s for s in got['fired'] if s['signal'] == 'repeated-failure']
    assert signal['evidence'] == [post, before]
    assert 'a later unavailable runtime' in signal['because']


def test_other_request_failures_do_not_count_and_recovery_ends_the_episode(server):
    from mentis.operational import completion
    _, op = server.session()
    cv = server.st.cv
    cid, request = a_request(op, 'Run browser checks')
    _, other = op('record_request', conversation=cid, text='Unrelated work')
    for _ in range(2):
        failed_after_start(cv, cid, other['expectation'])
    assert not L.consider(cv, request, trigger='run-ended')['fired']
    for _ in range(2):
        failed_after_start(cv, cid, request)
    assert L.consider(cv, request, trigger='run-ended')['evaluated']
    completion.claim(cv, request, {'result': 'met', 'summary': 'Recovered'},
                     actor=cv._act(request)['actor'], via='test')
    assert not L.consider(cv, request, trigger='run-ended')['fired']
    failed_after_start(cv, cid, request)
    assert not L.consider(cv, request, trigger='run-ended')['fired']
    failed_after_start(cv, cid, request)
    assert L.consider(cv, request, trigger='run-ended')['evaluated']
