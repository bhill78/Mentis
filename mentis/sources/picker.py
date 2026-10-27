"""Machine-local Windows picker; availability is checked on every request."""
import ctypes
import ipaddress
import os
import json
import pathlib
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

from mentis.sources import Refused, runs

TIMEOUT = 300
_FLIGHT = threading.Lock()


def _command(mode, purpose, start):
    command = [sys.executable, '-I', str(pathlib.Path(__file__).with_name('native_picker.py')),
               '--mode', mode, '--purpose', purpose]
    return command + (['--start', start] if start else [])


def _work(run, mode, purpose, start):
    process = None
    try:
        process = subprocess.Popen(_command(mode, purpose, start), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        end = time.monotonic() + TIMEOUT
        while process.poll() is None:
            run.check()
            if time.monotonic() >= end:
                return {'state': 'timed_out'}
            time.sleep(.1)
        run.check()
        output, _ = process.communicate()
        try:
            result = json.loads(output.decode('utf-8'))
            if not isinstance(result, dict) or result.get('state') not in ('chosen', 'cancelled', 'failed'):
                raise ValueError()
            if result['state'] == 'chosen':
                if not isinstance(result.get('path'), str) or not os.path.isabs(result['path']):
                    raise ValueError()
                result = {'state': 'chosen', 'path': result['path']}
                if purpose == 'folder':
                    result['folder'] = os.path.dirname(result['path']) if mode == 'file' else result['path']
            return result
        except (ValueError, UnicodeError):
            return {'state': 'failed', 'reason': 'The Windows dialog returned an unreadable result. Use a pasted path.'}
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate()
        _FLIGHT.release()


def start(st, body, *, wait=False, wrote=None):
    mode, purpose, initial = body.get('mode'), body.get('purpose'), body.get('start')
    if mode not in ('file', 'folder') or purpose not in ('sqlite', 'folder'):
        raise Refused('choose file or folder mode and a sqlite or folder purpose')
    if initial is not None and not isinstance(initial, str):
        raise Refused('the starting folder must be text')
    if not _FLIGHT.acquire(blocking=False):
        raise Refused('a Windows dialog is already open; finish or cancel it')
    key = 'pick-'+uuid.uuid4().hex[:12]
    try:
        result = runs.start(st.corpus, key, 'pick', lambda run: _work(run, mode, purpose, initial), started_by=wrote)
    except BaseException:
        _FLIGHT.release()
        raise
    return runs.wait(st.corpus, key, timeout=TIMEOUT+5) if wait else result


def _loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _interactive():
    if os.name != 'nt':
        return False
    from ctypes import wintypes as w
    kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
    session = w.DWORD()
    if not kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), ctypes.byref(session)) or not session.value:
        return False
    class Flags(ctypes.Structure):
        _fields_ = [('inherit', w.BOOL), ('reserved', w.BOOL), ('flags', w.DWORD)]
    flags, needed = Flags(), w.DWORD()
    user.GetProcessWindowStation.restype = w.HANDLE
    user.GetUserObjectInformationW.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    return bool(user.GetUserObjectInformationW(user.GetProcessWindowStation(), 1, ctypes.byref(flags),
                ctypes.sizeof(flags), ctypes.byref(needed)) and flags.flags & 1)


def available(st, peer=None):
    why = None
    if not _loopback(urlsplit(st.answers_at or '').hostname or ''):
        why = 'The Windows picker needs a server bound to loopback.'
    elif not _loopback(peer or ''):
        why = 'The Windows picker is available only to a loopback peer.'
    elif os.name != 'nt':
        why = 'The Windows picker is available only on Windows.'
    elif os.environ.get('MENTIS_NO_NATIVE_PICKER') is not None:
        why = 'The Windows picker is disabled by MENTIS_NO_NATIVE_PICKER.'
    elif not _interactive():
        why = 'The Windows picker needs an interactive desktop session.'
    return {'available': why is None, 'why_not': why}
