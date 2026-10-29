"""The Brain owner is remembered only for one unchanged read."""

from __future__ import annotations

import mentis.api as api
from mentis.bootstrap.baseline import OWNER_ABOUT
from mentis.conversation.owner import _owner


def test_owner_is_reread_after_participant_writes_in_the_same_scope(
        tmp_path, monkeypatch):
    corpus = api.create_corpus(str(tmp_path / "brain"))
    cv = api.brain(corpus).conversations
    calls = []
    real = type(corpus).entries_of_kind

    def counted(self, kind, *args, **kwargs):
        if self is corpus and kind == "participant":
            calls.append(kind)
        return real(self, kind, *args, **kwargs)

    monkeypatch.setattr(type(corpus), "entries_of_kind", counted)
    try:
        with cv.reading():
            assert _owner(cv) is None
            assert _owner(cv) is None
            assert calls == ["participant"]

            owner = cv.create_participant("@Owner", about=OWNER_ABOUT)
            after_create = len(calls)
            assert _owner(cv) == owner
            assert len(calls) == after_create + 1
            assert _owner(cv) == owner
            assert len(calls) == after_create + 1

            cv.rename_participant(owner, "@Renamed", by=owner)
            after_rename = len(calls)
            assert _owner(cv) == owner
            assert len(calls) == after_rename + 1
            assert _owner(cv) == owner
            assert len(calls) == after_rename + 1
            assert cv.alias(owner) == "@Renamed"
    finally:
        corpus.close()
