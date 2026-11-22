"""The preview helper's reporting seam, without any Brain or real report token."""
import io
import json
import urllib.error

import pytest
from tools.quiet_magnet_preview import DetachedReporter


def config(tmp_path):
    p = tmp_path / "private.json"
    p.write_text(json.dumps({"url": "http://127.0.0.1:8760/api/detached/opr-fixture/report", "token": "synthetic-one-time"}))
    return p


def test_report_names_client_and_operation_token_and_writes_only_receipt(tmp_path, monkeypatch):
    requests = []
    def send(request, timeout):
        requests.append(request)
        assert timeout == 30
        assert request.get_header("X-mentis-client") == "1"
        assert request.get_header("Content-type") == "application/json"
        assert json.loads(request.data) == {"token": "synthetic-one-time", "result": "succeeded", "summary": "ready", "evidence": ["ready.json"]}
        return io.BytesIO(b'{"ok": true, "report": "opr-receipt"}')
    monkeypatch.setattr("urllib.request.urlopen", send)
    receipt = tmp_path / "receipt.json"
    reporter = DetachedReporter(str(config(tmp_path)), receipt)
    reporter.report("succeeded", "ready", ["ready.json"])
    reporter.report("failed", "a later exception", [])
    assert len(requests) == 1
    assert json.loads(receipt.read_text()) == {"ok": True, "report": "opr-receipt"}
    assert "synthetic-one-time" not in receipt.read_text()


def test_refused_or_lost_report_is_not_retried_as_a_second_verdict(tmp_path, monkeypatch):
    for error in (urllib.error.HTTPError("http://fixture", 403, "refused", {}, io.BytesIO(b'{"error":"fixture refusal"}')), TimeoutError("answer unknown")):
        attempts = []
        def send(request, timeout):
            attempts.append(request)
            raise error
        monkeypatch.setattr("urllib.request.urlopen", send)
        receipt = tmp_path / "no-receipt.json"
        reporter = DetachedReporter(str(config(tmp_path)), receipt)
        with pytest.raises((RuntimeError, TimeoutError)):
            reporter.report("succeeded", "ready", [])
        reporter.report("failed", "not sent twice", [])
        assert len(attempts) == 1
        assert not receipt.exists()


def test_no_configuration_reports_nothing(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("no detached operation was armed")
    monkeypatch.setattr("urllib.request.urlopen", unexpected)
    receipt = tmp_path / "none.json"
    DetachedReporter(None, receipt).report("succeeded", "foreground only", [])
    assert not receipt.exists()
