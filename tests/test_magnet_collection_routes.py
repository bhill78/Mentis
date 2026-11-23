"""Integrated collection router: explicit historical selectors never fall back."""
import json
import pytest
from tests.test_magnet_activation import MAGNET, JSON_HEADERS, built, world, record_size, send
from tests.test_magnet_collection_history import commit


def get(w, tail='', headers=()):
    return send(w.alone, f'/fluid/api/magnets/{MAGNET}/collection{tail}',
                [*JSON_HEADERS, *headers], b'', method='GET')


def test_latest_exact_and_history_are_one_retained_router(world):
    first = commit(world, 'first-route')
    latest = commit(world, 'latest-route')
    before = record_size(world)
    assert json.loads(get(world)['body'])['activation']['post'] == latest['post']
    selected = get(world, f'?batch={first["artifact"]["ref"]}&digest={first["artifact"]["digest"]}')
    assert selected['status'] == 200
    assert json.loads(selected['body'])['activation']['post'] == first['post']
    history = get(world, '/history?limit=1')
    assert history['status'] == 200
    assert json.loads(history['body'])['batches'][0]['post'] == latest['post']
    assert json.loads(history['body'])['next']
    assert record_size(world) == before


@pytest.mark.parametrize('selector', ['?batch=', '?digest=', '?batch=&digest=', '?batch=&digest=' + 'a'*64,
                                     '?batch=adm-example111111&digest='])
def test_empty_selector_never_reads_latest(world, selector):
    commit(world, 'blank-route')
    before = record_size(world)
    response = get(world, selector)
    assert response['status'] == 400, response
    assert 'activation' not in json.loads(response['body'])
    assert record_size(world) == before


@pytest.mark.parametrize('tail', ['', '/history'])
def test_collection_router_refuses_worker_credentials(world, tail):
    commit(world, 'worker-route')
    before = record_size(world)
    assert get(world, tail, [['X-Mentis-Worker', 'forged']])['status'] == 403
    assert record_size(world) == before
