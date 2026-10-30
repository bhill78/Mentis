"""Fluid's brain-wide settings: the global Make room default (Surface Tension
P2, plan §3.8). Fixture corpora only; no live Brain is opened."""
import json
import pathlib
import urllib.error
import urllib.request

import pytest

from mentis.fluid import settings as S
from tests._loop import world  # noqa: F401


@pytest.fixture()
def root(tmp_path):
    return str(tmp_path / "corpus")


def file_of(root):
    return pathlib.Path(root) / "presentation" / "fluid-settings.json"


def test_an_absent_file_reads_as_off(root):
    assert S.settings(root) == {"makeRoom": "off"}
    assert not file_of(root).exists()


@pytest.mark.parametrize("value", ["off", "drag", "expand"])
def test_each_value_is_kept_under_presentation(root, value):
    assert S.save(root, {"makeRoom": value, "op": "op-1"}) == {"makeRoom": value}
    assert S.settings(root) == {"makeRoom": value}
    assert json.loads(file_of(root).read_text(encoding="utf-8")) == {
        "format": "mentis.fluid-settings", "version": 1, "makeRoom": value}
    assert file_of(root).parent == pathlib.Path(root) / "presentation"


@pytest.mark.parametrize("body, words", [
    ({"makeRoom": "always"}, "always"),
    ({"makeRoom": None}, "None"),
    ({}, "makeRoom"),
    ({"makeRoom": "off", "snap": True}, "'snap' is not a setting"),
    ({"makeRoom": "off", "op": ""}, "op"),
    ([], "send"),
])
def test_an_unknown_key_or_value_is_refused(root, body, words):
    with pytest.raises(S.Refused, match=words):
        S.save(root, body)
    assert not file_of(root).exists()


@pytest.mark.parametrize("raw", [
    "{not json",
    json.dumps({"format": "mentis.fluid-settings", "version": 1,
                "makeRoom": "drag", "extra": 1}),
    json.dumps({"format": "mentis.fluid-settings", "version": 2,
                "makeRoom": "drag"}),
    json.dumps({"format": "mentis.fluid-settings", "version": 1,
                "makeRoom": "sideways"}),
    json.dumps(["drag"]),
])
def test_an_unreadable_file_is_never_overwritten_silently(root, raw):
    file_of(root).parent.mkdir(parents=True)
    file_of(root).write_text(raw, encoding="utf-8")
    got = S.settings(root)
    assert got["makeRoom"] == "off" and got["unreadable"]
    with pytest.raises(S.Unreadable, match="left as it is"):
        S.save(root, {"makeRoom": "expand"})
    assert file_of(root).read_text(encoding="utf-8") == raw


def _call(world, method, body=None):
    req = urllib.request.Request(
        world["base"] + "/fluid/api/settings", method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_the_settings_routes(world):
    assert _call(world, "GET") == (200, {"makeRoom": "off"})
    assert _call(world, "POST", {"makeRoom": "drag", "op": "op-s"}) == (200, {"makeRoom": "drag"})
    assert _call(world, "GET") == (200, {"makeRoom": "drag"})
    status, got = _call(world, "POST", {"makeRoom": "never"})
    assert status == 400 and "never" in got["error"]
    file_of(world["root"]).write_text("{", encoding="utf-8")
    status, got = _call(world, "POST", {"makeRoom": "off"})
    assert status == 409 and got["kind"] == "Unreadable"
    assert file_of(world["root"]).read_text(encoding="utf-8") == "{"
