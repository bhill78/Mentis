"""Only the preview's seed/read seam. No browser, MARS, or live Brain."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mentis import api
from mentis.web import _Handler, _State
from mentis.execution import FakeExecution
from tools.preview_quiet_navigation import seed


def test_preview_reuses_existing_long_and_mixed_fixtures(tmp_path):
    root = tmp_path / "brain"
    manifest = seed(root, "http://127.0.0.1:19871")
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == manifest
    corpus = api.open_corpus(str(root), access="read")
    try:
        cv = api.brain(corpus).conversations
        assert len(cv.turns(manifest["long"]["conversation"])) == 12
        assert len(cv.turns(manifest["mixed"]["conversation"])) == 4
        assert manifest["viewport"] == {"width": 1440, "height": 1000}
    finally:
        corpus.close()


def test_preview_refuses_an_existing_directory(tmp_path):
    root = tmp_path / "brain"
    root.mkdir()
    with pytest.raises(FileExistsError, match="reuse its manifest"):
        seed(root, "http://127.0.0.1:19871")


def test_preview_conversation_and_artifact_urls_use_real_http_routes(tmp_path):
    root = tmp_path / "brain"
    manifest = seed(root, "http://127.0.0.1:19871")
    state = _State(str(root), execution=FakeExecution())
    handler = type("PreviewHandler", (_Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(path):
        with urllib.request.urlopen(base + path) as response:
            return response.read()

    try:
        for kind in ("long", "mixed"):
            data = json.loads(get(f"/api/conversations/{manifest[kind]['conversation']}"))
            assert data["name"] == manifest[kind]["name"]
            assert data["turns"]
        data = json.loads(get(f"/api/conversations/{manifest['mixed']['conversation']}"))
        assert any(topic["name"] == "Reading" for topic in data["topics"])
        assert get(f"/api/artifacts/{manifest['mixed']['notes']}") == b"a short note, read in the page"
        assert b"/assets/" in get("/quiet")  # the local production bundle
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        state.corpus.close()
