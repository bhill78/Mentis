"""Regression replay of the independent real-route P4 falsifiers; adapted to assert corrections.
No live Brain, real execution, TEST, or production input.
"""
import json
import subprocess
from pathlib import Path
import urllib.request

from tests._loop import world, get, a_conversation
from mentis.conversation import text, versions, erasure
from mentis.operational import current_work
from mentis.fluid.inspect import brain_key

def test_reviewer_group_beyond_first_page_and_unplaced_group(world, tmp_path):
    current_work.forget()
    cv, who = world['cv'], world['who']['@brian']
    home = a_conversation(world, 'Independent many groups')
    ask = cv.say(home, who, [text('Review old result groups')])
    work = cv.expect(ask, of=who, kind='result', by=who, conversation=home)
    groups = []
    for n in range(23):
        source = cv.say(home, who, [text('same result source prose')])
        note = cv.corpus.write(kind='note', body={'text': f'independent group {n}'},
                               attributed_to=who, written_by='independent-review')
        cv.record_act(actor=who, act='outcome-claimed', conversation=home, turn=source,
                      caused_by=work, detail={'reply_turn': source, 'result': 'partly',
                                             'summary': 'results', 'results': [note]})
        groups.append((source, note))
    first = get(world, f'/api/work/{work}')['result_groups']
    assert len(first['groups']) == 20 and first['omitted_groups'] == 3
    oldest, target = groups[0]
    exact = get(world, f'/api/work/{work}?result_group={oldest}')['result_groups']
    assert exact['groups'][0]['items'][0]['ref'] == target
    assert exact['groups'][0]['items'][0]['available']
    # No producing Turn: structural group identity is the act, and still routable.
    note = cv.corpus.write(kind='note', body={'text': 'unplaced result'},
                           attributed_to=who, written_by='independent-review')
    act = cv.record_act(actor=who, act='outcome-claimed', conversation=home,
                        caused_by=work, detail={'result': 'partly', 'summary': 'unplaced',
                                               'results': [note]})
    page = get(world, f'/api/work/{work}?result_group={act}')['result_groups']
    assert page['groups'][0]['unplaced'] and page['groups'][0]['source'] is None
    assert page['groups'][0]['items'][0]['ref'] == note
    tmp_path.joinpath('old-and-unplaced-groups.json').write_text(json.dumps(
        {'first': first, 'exact_oldest': exact, 'unplaced': page}, indent=2), encoding='utf-8')
    current_work.forget()


def test_reviewer_real_route_and_client(world, monkeypatch, tmp_path):
    current_work.forget()
    cv, who = world['cv'], world['who']['@brian']
    home = a_conversation(world, 'Reviewer origin; no builder data')
    remote = a_conversation(world, 'Reviewer remote deliverables')
    request_post = cv.say(home, who, [text('Inspect exact independent results')])
    work = cv.expect(request_post, of=who, kind='result', by=who, conversation=home)
    source = cv.say(home, who, [text('Result source, unrelated to target prose')])
    posts = [cv.say(remote, who, [text('identical result prose')]) for _ in range(2)]
    notes = [cv.corpus.write(kind='note', body={'text': 'identical note prose'},
                            attributed_to=who, written_by='independent-review') for _ in range(25)]
    refs = [posts[0], posts[1], remote, work, 'ent-ffffffffffff', *notes]
    cv.record_act(actor=who, act='outcome-claimed', conversation=home,
                  turn=source, caused_by=work, detail={'reply_turn': source,
                  'result': 'partly', 'summary': 'Independent results', 'results': refs})
    path = f'/api/work/{work}?result_group={source}'
    first = get(world, path)
    group = first['result_groups']['groups'][0]
    assert len(group['items']) == 20 and group['next_items_after']
    rest = get(world, path + '&items_after=' + group['next_items_after'])
    later = rest['result_groups']['groups'][0]['items'][-1]
    assert later['available'] and later['inspection']['opens'] == 'record'
    first_post = next(i for i in group['items'] if i['ref'] == posts[0])
    assert first_post['inspection']['post'] == posts[0]
    assert first_post['inspection']['conversation'] == remote
    # A claim reference alone has no returned-byte provenance; source stays null.
    assert first_post['source'] is None
    versions.delete(cv, posts[1], by=who, because='reviewer deletion')
    deleted = get(world, path)
    assert next(i for i in deleted['result_groups']['groups'][0]['items'] if i['ref'] == posts[1])['inspection']['state'] == 'deleted'
    # Fault injection is limited to a single target's reader, never the route.
    from mentis.fluid.inspect import _Resolver
    original = _Resolver._read
    def bad_read(self, ref):
        if ref == notes[0]:
            raise OSError('independent unreadable fixture')
        return original(self, ref)
    with monkeypatch.context() as m:
        m.setattr(_Resolver, '_read', bad_read)
        unreadable = get(world, path)
    assert next(i for i in unreadable['result_groups']['groups'][0]['items'] if i['ref'] == notes[0])['inspection']['state'] == 'unreadable'
    # Same viewer reach is an observation, not a permission proof.
    other = get(world, path + '&viewer=' + world['steward'])
    assert other['result_groups']['groups'][0]['items'] == deleted['result_groups']['groups'][0]['items']
    # A stale named Brain on GET is not checked by the write-only Brain guard.
    req = urllib.request.Request(world['base'] + path, headers={'X-Mentis-Brain': 'foreign@instance'})
    with urllib.request.urlopen(req) as response:
        foreign = json.load(response)
    assert foreign['expectation'] == work
    from mentis.worker import CAPABILITY_HEADER
    payload = dict(base=world['base'], work=work, group=source, post=posts[0],
                   deleted_post=posts[1], conversation=remote, late=later['ref'],
                   note=notes[0], source=source, first=first, rest=rest,
                   deleted=deleted, unreadable=unreadable, foreign=foreign,
                   capability_header=CAPABILITY_HEADER, brain=brain_key(cv.corpus))
    # The Node probe shares this test's disposable evidence, never repo-root evidence.
    tmp_path.joinpath('route-fixture.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    run = subprocess.run(['node', 'tests/p4_corrections_routes.mjs', str(tmp_path)],
                         cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=60)
    tmp_path.joinpath('correction-node.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    assert run.returncode == 0, run.stdout + run.stderr
    # Permanently erase only the remote fixture, then reread the source's Work.
    cv.change_conversation_state(remote, 'trash', by=who)
    imp = erasure.impact(cv, remote)
    erasure.delete(cv, remote, by=who, token=imp['token'])
    erased = get(world, path)
    erased_rows = erased['result_groups']['groups'][0]['items']
    assert all(next(i for i in erased_rows if i['ref'] == ref)['inspection']['state'] == 'erased'
               for ref in [posts[0], posts[1], remote])
    tmp_path.joinpath('erased-route.json').write_text(json.dumps(erased, indent=2), encoding='utf-8')
    current_work.forget()


def test_exact_reference_reader_uses_existing_boundary_and_fresh_resolver(world, monkeypatch):
    from tests.test_owner_auth import call
    port = int(world['base'].rsplit(':', 1)[1])
    cv, who = world['cv'], world['who']['@brian']
    home = a_conversation(world, 'Direct reference fixture')
    post = cv.say(home, who, [text('exact direct target')])
    request_home = a_conversation(world, 'Separate request fixture')
    request_post = cv.say(request_home, who, [text('direct request alias')])
    work = cv.expect(request_post, of=who, kind='result', by=who, conversation=request_home)
    note = cv.corpus.write(kind='note', body={'text': 'direct record'},
                           attributed_to=who, written_by='fixture')
    def read(ref):
        got = call(port, 'GET', '/fluid/api/result-ref?ref=' + ref)
        assert got['status'] == 200, got['json']
        return got['json']
    for ref, opens in [(post, 'post'), (home, 'conversation'), (note, 'record'), (work, 'post')]:
        got = read(ref)
        assert got['inspection']['id'] == ref and got['inspection']['opens'] == opens
        assert got['inspection']['available'] and got['inspection']['state'] == 'ok'
        assert brain_key(cv.corpus) == got['brain']['corpus_id'] + '@' + got['brain']['instance']
    assert read(work)['inspection']['post'] == request_post
    from mentis.fluid.inspect import _Resolver
    original = _Resolver._read
    def unreadable(self, ref):
        if ref == note:
            raise OSError('fixture unreadable')
        return original(self, ref)
    with monkeypatch.context() as m:
        m.setattr(_Resolver, '_read', unreadable)
        assert read(note)['inspection']['state'] == 'unreadable'
    assert read('ent-ffffffffffff')['inspection']['state'] == 'missing'
    versions.delete(cv, post, by=who, because='direct fixture deletion')
    assert read(post)['inspection']['state'] == 'deleted'
    cv.change_conversation_state(home, 'trash', by=who)
    erasure.delete(cv, home, by=who, token=erasure.impact(cv, home)['token'])
    assert read(post)['inspection']['state'] == 'erased'
    assert read(home)['inspection']['state'] == 'erased'
    from mentis.worker import CAPABILITY_HEADER
    path = '/fluid/api/result-ref?ref=' + note
    refused = call(port, 'GET', path, headers={CAPABILITY_HEADER: 'not-a-grant'})
    assert refused['status'] == 403 and refused['json']['kind'] == 'PermissionError'
    assert call(port, 'GET', path, client=False)['status'] == 403
    for query in ['', '?ref=', '?ref=' + post + ',' + note]:
        assert call(port, 'GET', '/fluid/api/result-ref' + query)['status'] == 400
