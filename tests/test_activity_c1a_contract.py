"""Read the actual pinned C1a retained-end helper without merging dispatch.

MENTIS_C1A_SOURCE names a read-only source clone holding the returned commit.
Tests use the function's exact Git bytes, fixture Brains and C2's route patch;
this is the writer/read seam, not full C1b or front-proxy integration.
"""
import ast
import os
from pathlib import Path
import subprocess

import pytest

from mentis import artifacts
from mentis.api.types import WorkOutcome
from mentis.conversation import text
from mentis.operational.runs import recorded_end
from tests._loop import world  # noqa: F401
from tests.test_run_activity import _get, _with_c2_route

C1A = '21dd13dcccf0c0b1474ae0d06bce0bd858c96d18'
pytestmark = pytest.mark.skipif(not os.environ.get('MENTIS_C1A_SOURCE'),
    reason='explicit pinned C1a source needed for writer/read seam; set MENTIS_C1A_SOURCE')


@pytest.fixture(scope='module')
def terminal_writer():
    source = subprocess.run(['git', '-C', os.environ['MENTIS_C1A_SOURCE'], 'show',
                             C1A + ':mentis/web/dispatch.py'], check=True,
                            capture_output=True, encoding='utf-8').stdout
    tree = ast.parse(source)
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_retained_end')
    ns = {'_artifacts': artifacts}
    exec(compile(ast.Module(body=[func], type_ignores=[]), f'C1a:{C1A}', 'exec'), ns)
    return ns['_retained_end']


LONG = 'BEGIN\n' + '\U0001f680' * 11000 + '\nMIDDLE\n' + 'x' * 11000 + '\nTAIL\n'


@pytest.mark.parametrize('terminal,collected', [
    ('reported_done', LONG), ('failed', LONG), ('cancelled', LONG),
    ('stopped_at_deadline', LONG), ('reported_done', ''), ('failed', None),
    ('exception', None),
], ids=['success-long', 'failed-long', 'cancelled-long', 'deadline-long',
        'empty-collected', 'missing-collected', 'perform-exception'])
def test_actual_c1a_terminal_projects_full_fields_held_and_evicted(world, monkeypatch, terminal_writer, terminal, collected):
    _with_c2_route(monkeypatch)
    cv, svc = world['cv'], world['state'].agents
    cid, who = world['conversations']['design'], world['steward']
    request_turn = cv.turns(cid)[0]['turn']
    request = cv.expect(request_turn, of=who, kind='result', by=world['who']['@brian'])
    # A prior resumed run's artifact must not enter this run's association.
    cv.record_act(actor=who, act=artifacts.RETURNED, caused_by=request,
                  execution='c1a-instance', about=['adm-old'])
    start = cv.record_act(actor=who, act='execution-started', conversation=cid,
                          turn=request_turn, caused_by=request, execution='c1a-instance')
    cv.record_act(actor=who, act=artifacts.RETURNED, caused_by=request,
                  execution='c1a-instance', about=['adm-current'])
    answer = cv.say(cid, who, [text('Earlier useful answer')], replies_to=request_turn)
    outcome = None if terminal == 'exception' else WorkOutcome(
        instance_id='c1a-instance', terminal=terminal, reported=collected, exit_code=-1,
        error='specific full failure ' + 'e' * 500,
        notes=('full diagnostic note ' + 'n' * 600,), timed_out=terminal == 'stopped_at_deadline')
    detail = terminal_writer(cv, execution='c1a-instance', started=start,
                             expectation=request, request_turn=request_turn,
                             outcome=outcome, answered=answer,
                             error='RuntimeError: escaped perform failure' if outcome is None else None)
    assert detail['collected_text'] == collected
    assert detail['returned_artifacts'] == ['adm-current']
    end = cv.record_act(actor=who, act='result-returned' if terminal == 'reported_done' else 'delivery-failed',
                        conversation=cid, turn=request_turn, caused_by=start,
                        execution='c1a-instance', detail=detail)
    svc.agents_open_run('c1a-instance', start)
    svc._runs[start]['ended_at'] = 9.0
    before = cv.history()
    held = _get(world, f'/api/runs/{start}/feed?after=9999')
    assert held['held_here']
    r = held['recorded']
    for key, value in detail.items():
        assert r[key] == value, key
    assert r['run'] == start and r['end'] == end and r['reply_turn'] == answer
    assert r['availability']['collected_text'] == (collected is not None)
    assert r['collected_text_chars'] == (len(collected) if collected is not None else None)
    assert r['collected_text_format'] == 'work-outcome-reported-v1'
    svc._runs.pop(start)
    assert _get(world, f'/api/runs/{start}/feed')['recorded'] == r
    assert recorded_end(cv, start) == r
    assert cv.history() == before
