"""Evidence of the existing boundary gap, not a security-boundary repair.

Disposable Brain and actual /api/worker door. No native model is invoked.
An ordinary work-reach request carries one selected artifact; unrelated Brain
words and acquired bytes are deliberately outside its Magnet configuration.
"""
import json
import urllib.error
import urllib.request

import pytest

from mentis import artifacts
from mentis import sources as bulk
from mentis.spine import held
from mentis.worker import CAPABILITY_HEADER
from tests._loop import world, a_conversation, say  # noqa: F401
from tests.respond_grant import bind_run
from tests.test_agent_request_routing import a_magnet, post


@pytest.fixture()
def scoped(world, tmp_path):
    cv, st = world['cv'], world['state']
    owner = world['who']['@brian']
    agent = cv.create_participant('@ScopeProbeAgent')
    magnet = a_magnet(world)
    selected = artifacts.hold(st.corpus, cv, b'SELECTED COLLECTION WORDS',
        act=artifacts.SUBMITTED, actor=owner, source='selected-probe', door='human',
        claimed_media_type='text/plain')['admission']
    unrelated = artifacts.hold(st.corpus, cv, b'UNSELECTED ARTIFACT WORDS',
        act=artifacts.SUBMITTED, actor=owner, source='unselected-probe', door='human',
        claimed_media_type='text/plain')['admission']
    outside = a_conversation(world, 'Outside configured Magnet sources')
    outside_post = say(world, outside, 'UNSELECTED BRAIN WORDS')['turn']
    status, answer = post(world, {'from': {'magnet': magnet}, 'author': owner,
        'text': 'Answer from the selected retained evidence only.', 'action': 'ask-participant',
        'parts': [{'type': 'text', 'text': 'Answer from the selected retained evidence only.'},
                  {'type': 'file', 'ref': selected, 'media_type': 'text/plain'}],
        'addressed_to': [agent], 'dispatch': [{'participant': agent, 'reach': 'work',
            'work': 'Use only the selected retained evidence; do not consult unrelated material.'}],
        'op': 'scope-probe-request'})
    assert status == 200, answer
    exp = answer['expectations'][0]
    assert artifacts.reach_of(cv, exp)['reach'] == 'work'
    offered = {row['ref'] for row in artifacts.available(st.corpus, cv, {'expectation': exp})}
    assert selected in offered and unrelated not in offered
    iid = 'scope-probe-fixture'
    grant = bind_run(cv, {'instance': iid, 'participant': agent, 'expectation': exp,
        'conversation': answer['route']['conversation']}, ended=False)
    st.agents.authority.authorise_for(iid, {**grant, 'scope': 'worker', 'runtime': 'codex'})
    token = st.agents.authority._grant(iid, st.path)

    def worker(op, **args):
        req = urllib.request.Request(world['base'] + '/api/worker', method='POST',
            data=json.dumps({'corpus': st.path, 'op': op, 'args': args}).encode(),
            headers={'Content-Type': 'application/json', CAPABILITY_HEADER: token})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)
    return {**world, 'worker': worker, 'selected': selected, 'unrelated': unrelated,
            'outside_post': outside_post, 'owner': owner, 'magnet': magnet}


def test_work_reach_blocks_unoffered_artifact_but_not_unselected_brain_post(scoped):
    status, denied = scoped['worker']('read_artifact', ref=scoped['unrelated'])
    assert status == 403 and 'not offered' in denied['error']
    status, allowed = scoped['worker']('resolve', ref=scoped['outside_post'])
    assert status == 200 and allowed['known'] is True, allowed
    assert 'UNSELECTED BRAIN WORDS' in allowed['said']


def test_work_reach_can_read_unselected_acquired_file_through_existing_worker_door(scoped):
    # Construct a valid acquired fixture Admission and declaration, not an
    # acquisition demonstration. The real worker read/permission path is tested.
    corpus, cv = scoped['state'].corpus, scoped['cv']
    collection = 'col-unselected-probe'
    cv.record_act(actor=scoped['owner'], act=bulk.DECLARED, detail={
        'collection': collection, 'connector': 'filesystem', 'name': 'Outside Magnet',
        'include': ['*.txt'], 'exclude': [], 'declared_by': scoped['owner']})
    data = b'UNSELECTED ACQUIRED WORDS'
    digest, _ = held.put(corpus.root, data)
    observation = {'object': 'outside.txt', 'state': 'present', 'retention': 'held',
        'digest': digest, 'size': len(data), 'payload_type': 'text/plain',
        'encoding': {'text': True}, 'relations': []}
    admission = bulk._admission(source=f'filesystem:{collection}', collection=collection,
        connector='filesystem', obs=observation, action='new', tok='probe', batch='probe',
        scope={'include': ['*.txt'], 'exclude': []}, observed_at='2026-11-23T00:00:00Z')
    corpus.admit(**admission, attributed_to=scoped['owner'], written_by='scope-probe-fixture')
    # The Magnet was never reconfigured to name this held source.
    from mentis import magnet as M
    config = M.read(scoped['state'].corpus.root, scoped['magnet'])
    assert all(s.get('collection') != collection for s in config['sources'])
    status, allowed = scoped['worker']('read_source', collection=collection, path='outside.txt')
    assert status == 200, allowed
    assert allowed['text'] == 'UNSELECTED ACQUIRED WORDS'
