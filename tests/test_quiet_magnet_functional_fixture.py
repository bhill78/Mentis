import json
import pytest
import mentis.api as api
from mentis.conversation.owner import _owner
from tools.quiet_magnet_fixture import REPO, seed, snapshot
from tools.quiet_magnet_functional_fixture import extend


@pytest.fixture
def inside():
    """The fixture tool writes only inside this checkout (`safe_root`), so the test's root
    is a fresh folder there, removed afterwards."""
    import shutil
    import uuid
    base = REPO / '.test-fixtures' / uuid.uuid4().hex
    try:
        yield base
    finally:
        import gc
        gc.collect()                      # release the fixture Brains' SQLite handles (Windows)
        shutil.rmtree(base, ignore_errors=True)
        try:
            base.parent.rmdir()           # only when no other worker's folder is left
        except OSError:
            pass


def test_functional_history_has_real_owner_reply_and_nonexecuting_work(inside):
    root = inside / 'functional-fixture'
    manifest = seed(root)
    before = snapshot(root)
    extra = extend(str(root))
    corpus = api.open_corpus(str(root / 'primary'), access='read')
    try:
        cv = api.conversations(corpus)
        assert _owner(cv) == extra['owner']
        assert cv.conversation_of(extra['root_post']) == manifest['primary']['C']
        assert cv.conversation_of(extra['historical_reply']) == manifest['primary']['C']
        reply = corpus.read([extra['historical_reply']])[0]
        assert 'seeded during setup' in reply['body']['parts'][0]['text']
        ask = cv._act(extra['work'])
        assert ask['act'] == 'expectation-recorded' and ask['turn'] == extra['root_post']
        assert not corpus.operational(act='execution-started')
    finally:
        corpus.close()
    after = snapshot(root)
    assert before['secondary'] == after['secondary']
    assert before['primary']['held'] == after['primary']['held']
    assert before['primary']['presentation'] == after['primary']['presentation']
    assert json.loads((root / 'manifest.json').read_text('utf-8'))['functional'] == extra


def test_extension_refuses_repetition_and_escape(inside):
    root = inside / 'functional-fixture'
    seed(root)
    extend(str(root))
    before = snapshot(root)
    with pytest.raises(ValueError, match='not-yet-extended'):
        extend(str(root))
    assert snapshot(root) == before
    with pytest.raises(ValueError, match='inside this checkout'):
        extend(str(REPO.parent))
