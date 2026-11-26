"""Integrated collection router: explicit historical selectors never fall back."""
import json
import pytest
from tests.test_magnet_activation import MAGNET, JSON_HEADERS, built, world, record_size, send
from tests.test_magnet_collection_history import NEWLY, commit, commit_with_rows


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


def test_new_route_reports_true_new_items_over_http(world):
    first = commit(world, 'new-route-first')
    second = commit(world, 'new-route-second')
    before = record_size(world)
    same = get(world, f'/new?since={second["artifact"]["ref"]}')
    assert same['status'] == 200
    assert json.loads(same['body'])['new_count'] == 0
    earlier = get(world, f'/new?since={first["artifact"]["ref"]}')
    assert earlier['status'] == 200
    body = json.loads(earlier['body'])
    assert body['batch'] == second['artifact']['ref'] and body['new_count'] == len(body['new'])
    assert get(world, '/new')['status'] == 400
    assert get(world, '/new?since=not-a-batch')['status'] == 400
    assert get(world, '/new?since=adm-000000000000')['status'] == 404
    assert record_size(world) == before


def test_new_route_counts_what_actually_changed(world):
    """What the badge is fed: over HTTP, the true count and nothing else.

    The two fixture batches above hold the same rows, so their diff is honestly
    empty. This is the other case -- a later batch over a changed source -- read
    the way the client reads it.
    """
    first = commit(world, 'true-count-first')
    changed = commit_with_rows(world, 'true-count-second', NEWLY)
    before = record_size(world)
    body = json.loads(get(world, f'/new?since={first["artifact"]["ref"]}')['body'])
    assert body['batch'] == changed['artifact']['ref']
    assert body['new'] == sorted(NEWLY) and body['new_count'] == 2
    # Nothing changed since the batch the viewer was last shown: no new items.
    assert json.loads(get(world, f'/new?since={changed["artifact"]["ref"]}')['body'])['new_count'] == 0
    assert record_size(world) == before


def test_new_route_refuses_worker_credentials(world):
    commit(world, 'new-worker-route')
    assert get(world, '/new?since=adm-000000000000',
               [['X-Mentis-Worker', 'forged']])['status'] == 403
