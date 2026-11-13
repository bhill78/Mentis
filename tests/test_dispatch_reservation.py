"""The dispatch reservation count (`dispatch.dispatch_soon`,
`fluid.commands.dispatching_now`): regression tests built from the
independent verification probes of 74d6952 (conv-mgmt/verify-74d6952.md).

Every read of the count is made under its lock, and every hand-off releases
its reservation exactly once -- also when `Thread.start()` is interrupted
after the native thread launched.
"""
import collections
import contextlib
import inspect
import sys
import threading
from types import SimpleNamespace

import pytest
from mentis.fluid import commands
from mentis.web import dispatch as D


def locked():
    return getattr(D, '_DISPATCHING_LOCK', contextlib.nullcontext())


def count(st):
    with locked():
        return dict(getattr(st, 'dispatching', {}))


@pytest.mark.parametrize('where', ['construct', 'start'])
@pytest.mark.parametrize('failure_type', [RuntimeError, KeyboardInterrupt])
def test_failure_before_launch_releases_and_reraises_identically(monkeypatch, where, failure_type):
    st = SimpleNamespace(requests_started=set())
    boom = failure_type('injected pre-launch failure')
    calls = []
    monkeypatch.setattr(D, 'dispatch', lambda *a, **kw: calls.append(kw))
    if where == 'construct':
        def broken(*a, **kw):
            raise boom
        monkeypatch.setattr(threading, 'Thread', broken)
    else:
        def broken(self):
            raise boom
        monkeypatch.setattr(threading.Thread, 'start', broken)
    with pytest.raises(failure_type) as seen:
        D.dispatch_soon(st, expectation='req', participant='p', conversation='c')
    assert seen.value is boom
    assert not calls
    assert count(st) == {}, 'a thread that never launched leaked its reservation'


def test_hand_on_failure_cleans_both_markers_and_preserves_error(monkeypatch):
    import mentis.web as web
    st = SimpleNamespace(requests_started=set())
    boom = RuntimeError('cannot launch')
    monkeypatch.setattr(web, 'dispatch_soon', D.dispatch_soon)
    def broken(self):
        raise boom
    monkeypatch.setattr(threading.Thread, 'start', broken)
    with pytest.raises(RuntimeError) as seen:
        commands._hand_on(st, dict(expectation='req', participant='p', conversation='c'))
    assert seen.value is boom
    assert st.requests_started == set()
    assert count(st) == {}


@pytest.mark.parametrize('ending', ['normal', 'early', 'exception', 'recording-exception', 'base-exception'])
def test_thread_end_releases_once_and_dispatches_once(monkeypatch, ending):
    st = SimpleNamespace(cv=object())
    made, calls, failures = [], [], []
    real_thread = threading.Thread
    def make_thread(*a, **kw):
        t = real_thread(*a, **kw)
        made.append(t)
        return t
    monkeypatch.setattr(threading, 'Thread', make_thread)
    monkeypatch.setattr(threading, 'excepthook', lambda args: failures.append(args.exc_value))
    def work(st_, **kw):
        calls.append(kw['expectation'])
        assert count(st_) == {'req': 1}
        if ending in ('exception', 'recording-exception'):
            raise RuntimeError('body failure')
        if ending == 'base-exception':
            raise SystemExit('body exit')
        if ending == 'early':
            return
        return {'ok': True}
    monkeypatch.setattr(D, 'dispatch', work)
    recorded = []
    def record(*a, **kw):
        recorded.append(kw)
        if ending == 'recording-exception':
            raise RuntimeError('recording failure')
    monkeypatch.setattr(D, '_failed_before_start', record)
    D.dispatch_soon(st, expectation='req', participant='p', conversation='c')
    made[0].join(5)
    assert not made[0].is_alive()
    assert count(st) == {}
    assert calls == ['req']
    assert len(made) == 1
    assert len(recorded) == (1 if ending in ('exception', 'recording-exception') else 0)
    assert len(failures) == (1 if ending == 'base-exception' else 0)


def test_same_and_different_expectations_retain_each_live_reservation(monkeypatch):
    st = SimpleNamespace()
    real_thread = threading.Thread
    made, calls, gates = [], [], [threading.Event() for _ in range(3)]
    entered = [threading.Event() for _ in range(3)]
    def make_thread(*a, **kw):
        t = real_thread(*a, **kw)
        made.append(t)
        return t
    monkeypatch.setattr(threading, 'Thread', make_thread)
    def work(st_, **kw):
        i = kw['probe_index']
        calls.append(i)
        entered[i].set()
        assert gates[i].wait(5)
    monkeypatch.setattr(D, 'dispatch', work)
    try:
        for i, exp in enumerate(('same', 'same', 'other')):
            D.dispatch_soon(st, expectation=exp, participant='p', conversation='c', probe_index=i)
            assert entered[i].wait(5)
        assert count(st) == {'same': 2, 'other': 1}
        gates[0].set()
        made[0].join(5)
        assert count(st) == {'same': 1, 'other': 1}
        gates[2].set()
        made[2].join(5)
        assert count(st) == {'same': 1}
    finally:
        for gate in gates:
            gate.set()
        for t in made:
            t.join(5)
    assert count(st) == {}
    assert sorted(calls) == [0, 1, 2]


def test_count_truth_read_is_locked():
    observed = []
    class ObservedCounter(collections.Counter):
        def __len__(self):
            observed.append(D._DISPATCHING_LOCK.locked())
            return super().__len__()
    st = SimpleNamespace(dispatching=ObservedCounter(), requests_started=set())
    assert commands.dispatching_now(st) == set()
    assert observed and all(observed), f'count truth reads under lock: {observed}'


def test_snapshot_acquiring_lock_after_reservation_sees_it(monkeypatch):
    st = SimpleNamespace(dispatching=collections.Counter(), requests_started=set())
    paused, resume, entered, finish = (threading.Event() for _ in range(4))
    result = {}
    source, start_line = inspect.getsourcelines(commands.dispatching_now)
    pause_line = start_line + next(i for i, line in enumerate(source) if 'with _DISPATCHING_LOCK:' in line)
    def trace(frame, event, arg):
        if frame.f_code is commands.dispatching_now.__code__ and event == 'line' and frame.f_lineno == pause_line:
            paused.set()
            assert resume.wait(5)
        return trace
    def read():
        sys.settrace(trace)
        try:
            result['snapshot'] = commands.dispatching_now(st)
        finally:
            sys.settrace(None)
    def work(st_, **kw):
        entered.set()
        assert finish.wait(5)
    monkeypatch.setattr(D, 'dispatch', work)
    real_thread = threading.Thread
    reader = real_thread(target=read)
    made = []
    def make_thread(*a, **kw):
        t = real_thread(*a, **kw)
        made.append(t)
        return t
    reader.start()
    try:
        assert paused.wait(5)
        monkeypatch.setattr(threading, 'Thread', make_thread)
        D.dispatch_soon(st, expectation='pending', participant='p', conversation='c')
        assert entered.wait(5)
        result['count_before_reader_lock'] = count(st)
        resume.set()
        reader.join(5)
        assert result['snapshot'] == {'pending'}, repr(result)
    finally:
        resume.set()
        finish.set()
        reader.join(5)
        for t in made:
            t.join(5)


def test_start_interrupted_after_os_launch_preserves_live_reservations(monkeypatch):
    """Real Thread.start, injecting KeyboardInterrupt in its final Event.wait.

    CPython 3.12 launches the native thread before this wait. Only the wait
    is interrupted; both dispatch bodies run on real threads exactly once.
    """
    st = SimpleNamespace()
    gates = {name: threading.Event() for name in ('I', 'S')}
    entered = {name: threading.Event() for name in gates}
    made, calls, observed = [], [], {}
    boom = KeyboardInterrupt('interrupt in Thread.start after launch')
    real_init = threading.Thread.__init__
    def init(self, *a, **kw):
        real_init(self, *a, **kw)
        if self.name.startswith('dispatch-'):
            made.append(self)
        if self.name == 'dispatch-I':
            real_wait = self._started.wait
            def interrupted_wait(*a, **kw):
                real_wait(*a, **kw)
                assert entered['I'].wait(5)
                raise boom
            self._started.wait = interrupted_wait
    monkeypatch.setattr(threading.Thread, '__init__', init)
    def work(st_, **kw):
        who = kw['participant']
        calls.append(who)
        entered[who].set()
        assert gates[who].wait(5)
    monkeypatch.setattr(D, 'dispatch', work)
    try:
        with pytest.raises(KeyboardInterrupt) as seen:
            D.dispatch_soon(st, expectation='shared', participant='I', conversation='c')
        assert seen.value is boom
        observed['interrupted_thread_alive'] = made[0].is_alive()
        observed['count_with_interrupted_thread_alive'] = count(st)
        D.dispatch_soon(st, expectation='shared', participant='S', conversation='c')
        assert entered['S'].wait(5)
        observed['count_with_two_threads_alive'] = count(st)
        gates['I'].set()
        made[0].join(5)
        observed['sibling_still_alive'] = made[1].is_alive()
        observed['count_with_sibling_still_alive'] = count(st)
        assert observed['count_with_interrupted_thread_alive'] == {'shared': 1} and observed['count_with_sibling_still_alive'] == {'shared': 1}, repr(observed)
    finally:
        for gate in gates.values():
            gate.set()
        for t in made:
            t.join(5)
    assert sorted(calls) == ['I', 'S']
    assert count(st) == {}


def test_first_handoff_initialization_does_not_replace_another_count(monkeypatch):
    """Pause A after its first missing-count read; B initializes before A resumes."""
    st = SimpleNamespace()
    paused, resume, finish = (threading.Event() for _ in range(3))
    entered = {name: threading.Event() for name in ('A', 'B')}
    made, errors = [], []
    if hasattr(D, '_dispatching_of'):
        target = D._dispatching_of
        marker = 'with _DISPATCHING_LOCK:'
    else:
        target = D.dispatch_soon
        marker = 'if held is None:'
    source, line = inspect.getsourcelines(target)
    pause_line = line + next(i for i, text in enumerate(source) if marker in text)
    def trace(frame, event, arg):
        if frame.f_code is target.__code__ and event == 'line' and frame.f_lineno == pause_line:
            paused.set()
            assert resume.wait(5)
        return trace
    def work(st_, **kw):
        entered[kw['participant']].set()
        assert finish.wait(5)
    monkeypatch.setattr(D, 'dispatch', work)
    real_thread = threading.Thread
    def make_thread(*a, **kw):
        t = real_thread(*a, **kw)
        made.append(t)
        return t
    def hand_a():
        sys.settrace(trace)
        try:
            D.dispatch_soon(st, expectation='A', participant='A', conversation='c')
        except BaseException as exc:
            errors.append(exc)
        finally:
            sys.settrace(None)
    hand = real_thread(target=hand_a)
    monkeypatch.setattr(threading, 'Thread', make_thread)
    hand.start()
    try:
        assert paused.wait(5)
        D.dispatch_soon(st, expectation='B', participant='B', conversation='c')
        assert entered['B'].wait(5)
        resume.set()
        hand.join(5)
        assert entered['A'].wait(5)
        assert not errors, repr(errors)
        assert count(st) == {'A': 1, 'B': 1}
    finally:
        resume.set()
        finish.set()
        hand.join(5)
        for t in made:
            t.join(5)
    assert count(st) == {}


def test_count_lock_is_released_before_thread_and_external_calls(monkeypatch):
    st = SimpleNamespace(cv=object())
    made, calls = [], []
    real_thread = threading.Thread
    def verify(label):
        assert D._DISPATCHING_LOCK.acquire(timeout=1), label
        D._DISPATCHING_LOCK.release()
        calls.append(label)
    def make_thread(*a, **kw):
        verify('Thread construction')
        t = real_thread(*a, **kw)
        made.append(t)
        return t
    def work(*a, **kw):
        verify('dispatch body')
        raise RuntimeError('exercise recorder')
    def record(*a, **kw):
        verify('failure recorder')
    monkeypatch.setattr(threading, 'Thread', make_thread)
    monkeypatch.setattr(D, 'dispatch', work)
    monkeypatch.setattr(D, '_failed_before_start', record)
    D.dispatch_soon(st, expectation='req', participant='p', conversation='c')
    made[0].join(5)
    assert calls == ['Thread construction', 'dispatch body', 'failure recorder']
    assert count(st) == {}
