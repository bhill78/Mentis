"""Production mini request JSON -> real HTTP door -> real worker artifact gate.

Disposable Brain. Dispatch is captured, no agent answer is scripted or claimed.
The backend collection envelope belongs to package A; this test supplies a held
captured page and exercises B's asking Turn, routing, idempotency and reach.
"""
import base64
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

import pytest

from mentis import artifacts
from mentis.worker import CAPABILITY_HEADER, may_coordinate
from tests.test_ask_mentis_permissions import observed, _run  # noqa: F401
from tests._loop import world  # noqa: F401
from tests.respond_grant import bind_run
from tests.test_agent_request_routing import a_magnet, post

ROOT = Path(__file__).resolve().parents[1]


def worker_read(world, expectation, conversation, participant, ref):
    authority = world['state'].agents.authority
    iid = f'mini-{expectation}'
    grant = bind_run(world['cv'], dict(instance=iid, participant=participant,
                     expectation=expectation, conversation=conversation), ended=False)
    authority.authorise_for(iid, {**grant, 'scope': 'worker', 'runtime': 'codex'})
    token = authority._grant(iid, world['state'].path)
    req = urllib.request.Request(world['base'] + '/api/worker', method='POST',
        data=json.dumps({'corpus': world['state'].path, 'op': 'read_artifact',
                         'args': {'ref': ref, 'why': 'answer from retained collection'}}).encode(),
        headers={'Content-Type': 'application/json', CAPABILITY_HEADER: token})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.mark.parametrize('attach', [True, False])
@pytest.mark.parametrize('runtime', ['codex', None])
def test_mini_intentional_file_part_preserves_artifact_reach_without_automatic_pool(world, observed, attach, runtime):
    cv = world['cv']
    mid = a_magnet(world)
    owner = world['who']['@brian']
    agent = cv.create_participant('@MiniGateAgent')
    captured = json.dumps({'sources': [{'key': 'conversation:ent-src', 'results': [
        {'kind': 'post', 'id': 'ent-capturedpost', 'version': 'ent-capturedversion',
         'value': {'parts': [{'type': 'text', 'text': 'Actual held fixture content: 37.'}]}}
    ]}]}).encode()
    held = artifacts.hold(cv.corpus, cv, captured, act=artifacts.SUBMITTED,
                          actor=owner, source='mini captured fixture page', door='human',
                          claimed_media_type='application/json')
    ref = held['admission']
    described = artifacts.describe(cv.corpus, ref)
    value = {'magnet': mid, 'author': owner, 'question': 'What value was captured?',
             'op': f'mini-gate-{attach}', 'agent': {'id': agent, 'alias': '@MiniGateAgent', 'runtime': runtime},
             'permissions': {'coordinate': True, 'followUp': 2,
                             'consent': {'mode': 'task', 'workspaces': [world['root']]}},
             'collection': {'post': 'ent-collectionpost', 'at': 1,
                            'artifact': {'ref': ref, 'digest': described['digest'],
                                         'size': len(captured), 'media_type': 'application/json'}}}
    if runtime is None:
        # Read the real Fluid endpoint on this disposable Brain. All legacy
        # participants have no default; an explicit choice still routes an ask.
        request = urllib.request.Request(
            world['base'] + '/fluid/api/participants?limit=500&runtimes=1',
            headers={'X-Mentis-Client': '1'})
        with urllib.request.urlopen(request, timeout=30) as response:
            people = json.loads(response.read())
        assert people['me'] == owner
        assert all(p['default_runtime'] is None and p['runtime_mode'] == 'undeclared'
                   for p in people['participants'])
        selected = next(p for p in people['participants'] if p['id'] == agent)
        assert {k: selected[k] for k in ('id', 'alias', 'default_runtime', 'runtime_mode')} == {
            'id': agent, 'alias': '@MiniGateAgent',
            'default_runtime': None, 'runtime_mode': 'undeclared'}
        value['people'] = people
    built = subprocess.run(['node', 'tests/quiet_magnet_mini_request.mjs'],
        cwd=ROOT / 'apps/fluid-web', input=json.dumps(value), text=True,
        capture_output=True, check=True, timeout=30)
    body = json.loads(built.stdout)
    assert body['parts'][0] == {'type': 'text', 'text': value['question']}
    assert len(body['parts']) == 1
    assert 'work' not in body['dispatch'][0]
    if attach:
        body['parts'].append({'type': 'file', 'ref': ref, 'media_type': 'application/json', 'alt': 'Intentional fixture attachment'})
    assert body['dispatch'][0]['runtime'] == runtime
    if not attach:
        # Negative control: same dispatch prose, absent from the asking Turn.
        body['parts'] = body['parts'][:1]
    brain_request = urllib.request.Request(world['base'] + '/fluid/api/needs-you/brain',
                                          headers={'X-Mentis-Client': '1'})
    with urllib.request.urlopen(brain_request) as r:
        brain = json.loads(r.read())['brain']
    binding = f"{brain['corpus_id']}@{brain['instance']}"
    status, answer = post(world, body, headers={'X-Mentis-Brain': binding})
    assert status == 200, answer
    own = answer['route']['conversation']
    assert own != 'ent-src'
    assert len(world['sent']) == 1
    assert world['sent'][0]['conversation'] == own
    assert world['sent'][0]['runtime'] == runtime
    expectation = answer['expectations'][0]
    # The real bodyOf -> adapter request authorises exactly the Work choices,
    # checked on the recorded request and on the dispatch to execution.
    act = next(a for a in cv._c.operational(turn=answer['post'])
               if a['act'] == 'expectation-recorded' and a['id'] == expectation)
    assert act['detail']['consent']['mode'] == 'task'
    assert act['detail']['consent']['workspaces'] == [world['root']]
    assert act['detail']['follow_up'] == {'depth': 2}
    assert cv.authority_of(expectation)['operations']
    status, replay = post(world, body, headers={'X-Mentis-Brain': binding})
    assert status == 200 and replay['post'] == answer['post'] and replay['replayed']
    assert len(world['sent']) == 1
    offered = artifacts.available(cv.corpus, cv, {'expectation': expectation})
    assert (ref in {a['ref'] for a in offered}) is attach
    status, read = worker_read(world, expectation, own, agent, ref)
    if attach:
        assert status == 200 and 'error' not in read, read
        assert read['ref'] == ref and base64.b64decode(read['bytes_b64']) == captured
        assert any(a['ref'] == ref and a['because'] == 'asked-with' for a in offered)
    else:
        assert status == 403, read
        assert 'not offered' in read['error']
    _run(world, expectation)
    actual = observed[-1]
    assert may_coordinate(actual['grant'])
    assert actual['grant']['conversation'] == own
    assert actual['consent']['mode'] == 'task'
    assert world['root'] in actual['consent']['workspaces']
    assert actual['asked_with']['follow_up'] == {'depth': 2}
    assert actual['spec'].consent['mode'] == 'task'


def test_mini_request_cannot_write_under_another_brain_binding(world):
    mid = a_magnet(world)
    status, answer = post(world, {'from': {'magnet': mid},
        'author': world['who']['@brian'], 'text': 'must not record',
        'action': 'record-only', 'op': 'mini-wrong-instance'},
        headers={'X-Mentis-Brain': 'another-corpus@another-instance'})
    assert status == 409 and answer['kind'] == 'BrainChanged'
    assert not world['sent']
