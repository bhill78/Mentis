"""Isolated stdlib IFileOpenDialog. Slots/flags follow ShObjIdl_core.h.

--selftest creates and releases the COM dialog without calling Show.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import os
import threading
import uuid


class GUID(c.Structure):
    _fields_ = [('data', c.c_ubyte * 16)]
    def __init__(self, value):
        super().__init__((c.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


def main(args):
    ole, shell, user = c.windll.ole32, c.windll.shell32, c.windll.user32
    HRESULT = c.c_long
    ole.CoInitializeEx.argtypes = [c.c_void_p, w.DWORD]
    ole.CoCreateInstance.argtypes = [c.POINTER(GUID), c.c_void_p, w.DWORD, c.POINTER(GUID), c.POINTER(c.c_void_p)]
    ole.CoTaskMemFree.argtypes = [c.c_void_p]
    shell.SHCreateItemFromParsingName.argtypes = [w.LPCWSTR, c.c_void_p, c.POINTER(GUID), c.POINTER(c.c_void_p)]
    user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int, c.c_int, c.c_int,
                                   w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p]
    user.CreateWindowExW.restype = w.HWND
    user.DestroyWindow.argtypes = [w.HWND]
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindow.argtypes = [w.HWND, w.UINT]
    user.GetWindow.restype = w.HWND
    user.MonitorFromPoint.argtypes = [w.POINT, w.DWORD]
    user.MonitorFromPoint.restype = w.HANDLE
    user.GetMonitorInfoW.argtypes = [w.HANDLE, c.c_void_p]
    user.FlashWindowEx.argtypes = [c.c_void_p]

    def check(hr):
        if hr < 0:
            raise OSError(f'Windows dialog HRESULT 0x{hr & 0xffffffff:08x}')

    def call(obj, slot, types=(), values=()):
        vtable = c.cast(obj, c.POINTER(c.POINTER(c.c_void_p))).contents
        return c.WINFUNCTYPE(HRESULT, c.c_void_p, *types)(vtable[slot])(obj, *values)

    dialog, item, owner = c.c_void_p(), c.c_void_p(), None
    check(ole.CoInitializeEx(None, 2))
    stopped = threading.Event()
    try:
        check(ole.CoCreateInstance(c.byref(GUID('DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7')), None, 1,
              c.byref(GUID('D57C7288-D4AD-4768-BE02-9D969532D960')), c.byref(dialog)))
        if args.selftest:
            return {'state': 'selftest_ok'}
        options = w.DWORD()
        check(call(dialog, 10, (c.POINTER(w.DWORD),), (c.byref(options),)))
        flags = options.value | 0x40 | 0x800 | 0x1000 | 0x8 | (0x20 if args.mode == 'folder' else 0)
        check(call(dialog, 9, (w.DWORD,), (flags,)))
        title = 'Select folder' if args.mode == 'folder' else 'Choose a database file' if args.purpose == 'sqlite' else 'Pick a file inside the folder'
        check(call(dialog, 17, (w.LPCWSTR,), (title,)))
        client = GUID('bca1d80c-a9ae-4d74-a35b-5f963881ef01' if args.purpose == 'sqlite' else
                      'bca1d80c-a9ae-4d74-a35b-5f963881ef02' if args.mode == 'folder' else 'bca1d80c-a9ae-4d74-a35b-5f963881ef03')
        check(call(dialog, 24, (c.POINTER(GUID),), (c.byref(client),)))
        if args.mode == 'file':
            class Filter(c.Structure):
                _fields_ = [('name', w.LPCWSTR), ('pattern', w.LPCWSTR)]
            filters = ([('SQLite databases (*.db;*.sqlite;*.sqlite3;*.db3)', '*.db;*.sqlite;*.sqlite3;*.db3')]
                       if args.purpose == 'sqlite' else []) + [('All files (*.*)', '*.*')]
            specs = (Filter * len(filters))(*(Filter(*f) for f in filters))
            check(call(dialog, 4, (w.UINT, c.POINTER(Filter)), (len(filters), specs)))
        iid = GUID('43826D1E-E718-42EE-BC55-A1E261C37BFE')
        if args.start and os.path.isdir(args.start):
            check(shell.SHCreateItemFromParsingName(args.start, None, c.byref(iid), c.byref(item)))
            check(call(dialog, 12, (c.c_void_p,), (item,)))
            call(item, 2); item = c.c_void_p()
        class Monitor(c.Structure):
            _fields_ = [('size', w.DWORD), ('monitor', w.RECT), ('work', w.RECT), ('flags', w.DWORD)]
        point, monitor = w.POINT(), Monitor()
        monitor.size = c.sizeof(monitor)
        user.GetCursorPos(c.byref(point))
        user.GetMonitorInfoW(user.MonitorFromPoint(point, 2), c.byref(monitor))
        r = monitor.work
        owner = user.CreateWindowExW(0x8 | 0x80, 'STATIC', 'Mentis: choose a source', 0,
            (r.left+r.right)//2, (r.top+r.bottom)//2, 1, 1, None, None, None, None)
        if not owner:
            raise c.WinError()
        class Flash(c.Structure):
            _fields_ = [('size', w.UINT), ('window', w.HWND), ('flags', w.DWORD), ('count', w.UINT), ('timeout', w.DWORD)]
        def attention():
            if not stopped.wait(.5) and user.GetWindow(user.GetForegroundWindow(), 4) != owner:
                flash = Flash(c.sizeof(Flash), owner, 3, 3, 0)
                user.FlashWindowEx(c.byref(flash))
        thread = threading.Thread(target=attention, daemon=True)
        thread.start()
        hr = call(dialog, 3, (w.HWND,), (owner,))
        stopped.set(); thread.join()
        if hr & 0xffffffff == 0x800704c7:
            return {'state': 'cancelled'}
        check(hr)
        check(call(dialog, 20, (c.POINTER(c.c_void_p),), (c.byref(item),)))
        path = c.c_void_p()
        check(call(item, 5, (w.DWORD, c.POINTER(c.c_void_p)), (0x80058000, c.byref(path))))
        try:
            return {'state': 'chosen', 'path': c.wstring_at(path)}
        finally:
            ole.CoTaskMemFree(path)
    finally:
        stopped.set()
        if item: call(item, 2)
        if dialog: call(dialog, 2)
        if owner: user.DestroyWindow(owner)
        ole.CoUninitialize()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('file', 'folder'), default='file')
    parser.add_argument('--purpose', choices=('sqlite', 'folder'), default='sqlite')
    parser.add_argument('--start')
    parser.add_argument('--selftest', action='store_true')
    try:
        result = main(parser.parse_args())
    except Exception as exc:
        result = {'state': 'failed', 'reason': str(exc)}
    print(json.dumps(result, ensure_ascii=True), flush=True)
