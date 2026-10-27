"""The MARS command given to the server (--mars / MENTIS_MARS_COMMAND) becomes an
argument list. Found live: a Windows path was split into characters."""

import os

import pytest

from mentis.core.service import mars_argv


@pytest.mark.skipif(os.name != "nt", reason="Windows path rules")
def test_windows_path_keeps_its_backslashes():
    assert mars_argv(r"C:\Work\MARS-venv\Scripts\mars.exe stdio") == [
        r"C:\Work\MARS-venv\Scripts\mars.exe", "stdio"]


@pytest.mark.skipif(os.name != "nt", reason="Windows path rules")
def test_quoted_windows_path_with_spaces():
    assert mars_argv(r'"C:\Program Files\MARS\mars.exe" stdio') == [
        r"C:\Program Files\MARS\mars.exe", "stdio"]


def test_plain_and_list_forms():
    assert mars_argv("mars stdio") == ["mars", "stdio"]
    assert mars_argv(["mars", "stdio"]) == ["mars", "stdio"]
    assert mars_argv(None) == []
