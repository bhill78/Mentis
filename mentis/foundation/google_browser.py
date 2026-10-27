"""GOOGLE IN A HEADLESS BROWSER: `web_search`'s last, opt-in backup.

WHAT IT IS. When SearXNG (and Tavily, if a key is set) cannot answer, and
the owner has turned this on (`MENTIS_GOOGLE_BROWSER=1`), Mentis loads
Google's results page in headless Chromium through Playwright and reads the
results off it. That is scraping a search page, done deliberately, opt-in
and only as a backup (owner approval ent-4cb54d76e466 on the terms of
ent-d95eaf455987). It is never the first thing tried.

NO WAY ROUND GOOGLE'S BOT CHECK. The browser is plain headless Chromium as
Playwright ships it: its own user agent, no stealth script, no fingerprint
changes, no saved cookies, no consent button clicked and no CAPTCHA solved.
Whenever Google answers with anything but a results page -- its "unusual
traffic" page, a CAPTCHA, its consent wall -- this backend fails and says
which, and the search answers with what the other backends said.

EVERY BROWSER IS KILLED, WHOLE. A search runs in a child Python process of
its own (`_child`, this file run as a script), which starts Playwright's
driver, which starts Chromium and its helpers. On Windows the child is
created suspended and put in a Job Object that kills every process in it
when it is closed, before it runs a line (`_Job`); the job is terminated
when the search ends, however it ends, and the slot is given back only once
nothing in it is still alive. If Mentis itself dies, Windows closes the job
and kills them too. Elsewhere the child leads a process group of its own,
and the group is killed. So no Chromium outlives its search.

BOUNDED IN TIME AND IN NUMBER. The child is given less time than the caller
and is killed at the caller's deadline whatever it is doing (`search`); at
most MAX_BROWSERS run at once, each inside a thread that already holds one
of `web_reach.MAX_THREADS`'s slots, and the child's answer comes back
through a file rather than a pipe, so no reader thread is added.

PORTED FROM noapi-google-search-mcp (https://github.com/engram-ae/
noapi-google-search-mcp, `src/google_search_mcp/server.py`: the search URL,
the block check and the result-reading script of `_do_google_search` and
`_is_blocked`), which is distributed under this licence:

    MIT License

    Copyright (c) 2025 Vincent Kaufmann

    Permission is hereby granted, free of charge, to any person obtaining a
    copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to
    the following conditions:

    The above copyright notice and this permission notice shall be included
    in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
    OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
    TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
    SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Only plain search was ported. Its stealth script, user agent, cookie store,
consent clicking, CAPTCHA solver (onnxruntime and its model) and every other
tool it offers were left out on purpose.

SETUP, ONCE PER MACHINE: `pip install -r requirements-browser.txt` brings
Playwright (opt-in: it is not in requirements.txt or a release's lock); its
Chromium is a separate download, `python -m playwright install chromium`.
Without either, this backend fails saying which is missing.

STANDARD LIBRARY ONLY ON THE SERVER'S SIDE: Playwright is imported by the
child alone, so a Mentis without it starts and searches as before.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

#: How many browser searches may run at once. Each is a Chromium of a few
#: hundred MB; two lets two agents fall back at once without letting a burst
#: fill the machine.
MAX_BROWSERS = 2
_slots = threading.BoundedSemaphore(MAX_BROWSERS)

#: The child is told to finish this much before it is killed, so it answers
#: in its own words ("timed out loading the page") whenever it can.
CHILD_MARGIN_S = 1.0
#: How long the job's processes are given to be gone once it is terminated.
KILL_WAIT_S = 5.0

#: The line the child's answer is written on, so nothing else it prints can
#: be mistaken for it.
_MARK = "MENTIS-GOOGLE-BROWSER-ANSWER "

INSTALL_CHROMIUM = "python -m playwright install chromium"

#: Names in the environment the child is not given: it needs none of them.
_SECRET = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.I)


class BrowserFailed(Exception):
    """The browser search did not produce results, and why. An answer."""


# -- the parent: start, bound, kill ------------------------------------------

def search(q: str, limit: int, seconds: float, env=None) -> list[dict]:
    """Google's results for `q` as rows (title, url, snippet, engine), read
    in a headless browser that is killed by `seconds` whatever it is doing.
    Raises `BrowserFailed` with the reason, or TimeoutError."""
    if not available():
        raise BrowserFailed(
            "playwright is not installed in this Mentis's Python, so the "
            "Google browser backup cannot run (pip install -r "
            f"requirements-browser.txt, then {INSTALL_CHROMIUM})")
    if not _slots.acquire(blocking=False):
        raise BrowserFailed(
            f"not tried: {MAX_BROWSERS} browser searches are already running "
            f"(at most {MAX_BROWSERS} at once)")
    try:
        argv = _command(q, limit, max(0.5, seconds - CHILD_MARGIN_S))
        return _rows(_run(argv, seconds, _child_env(env)), limit)
    finally:
        _slots.release()


def available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _command(q: str, limit: int, budget: float) -> list[str]:
    """This file run as the child. `-P` keeps this directory off its path."""
    flags = ["-P"] if sys.version_info >= (3, 11) else []
    return [sys.executable, *flags, os.path.abspath(__file__),
            json.dumps({"q": q, "limit": limit, "budget": budget})]


def _child_env(env) -> dict:
    """The server's environment without its secrets: the child reads the
    Playwright settings it holds (PLAYWRIGHT_BROWSERS_PATH) and needs no key.
    """
    base = dict(os.environ if env is None else env)
    if env is not None:
        # A test's environment names the backends; the OS's own variables
        # still have to reach the child for it to start at all.
        base = {**os.environ, **base}
    return {k: v for k, v in base.items() if not _SECRET.search(k)}


def _run(argv: list[str], seconds: float, env: dict) -> dict:
    """The child's answer, or TimeoutError once `seconds` are up. Whatever
    happens, every process it started is dead before this returns."""
    began = time.monotonic()
    with tempfile.TemporaryFile() as out:
        proc, job = _spawn(argv, out, env)
        timed_out = False
        try:
            proc.wait(timeout=max(0.0, seconds - (time.monotonic() - began)))
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            _kill(proc, job)
        if timed_out:
            raise TimeoutError(f"timed out after {seconds:.1f}s; the browser "
                               f"was killed")
        out.seek(0)
        said = out.read(1 << 20).decode("utf-8", "replace")
    for line in reversed(said.splitlines()):
        if line.startswith(_MARK):
            try:
                got = json.loads(line[len(_MARK):])
            except ValueError:
                break
            if isinstance(got, dict):
                return got
            break
    raise BrowserFailed(f"the browser process ended (exit code "
                        f"{proc.returncode}) without an answer")


def _spawn(argv, out, env):
    """The child, started so that it and everything it starts can be
    killed together: (the process, its job or None)."""
    if os.name != "nt":
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.DEVNULL, env=env,
                                start_new_session=True)
        return proc, None
    job = _Job()
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=out,
            stderr=subprocess.DEVNULL, env=env,
            creationflags=_CREATE_SUSPENDED | subprocess.CREATE_NO_WINDOW)
    except BaseException:
        job.close()
        raise
    try:
        # BEFORE IT RUNS A LINE: created suspended, so nothing it starts can
        # be started outside the job.
        job.assign(proc)
        _resume(proc)
    except BaseException:
        proc.kill()
        proc.wait()
        job.close()
        raise
    return proc, job


def _kill(proc, job) -> None:
    """Every process the child started, and the child, killed and gone."""
    if job is not None:
        job.terminate()
        job.wait_empty(KILL_WAIT_S)
        job.close()
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=KILL_WAIT_S)
    except subprocess.TimeoutExpired:
        pass


# -- Windows: the Job Object -------------------------------------------------

_CREATE_SUSPENDED = 0x00000004
_KILL_ON_JOB_CLOSE = 0x00002000
_EXTENDED_LIMITS = 9           # JobObjectExtendedLimitInformation
_BASIC_ACCOUNTING = 1          # JobObjectBasicAccountingInformation


def _kernel():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                          ctypes.c_void_p, wintypes.DWORD)
    k.QueryInformationJobObject.restype = wintypes.BOOL
    k.QueryInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.c_void_p)
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k.TerminateJobObject.restype = wintypes.BOOL
    k.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k.CloseHandle.restype = wintypes.BOOL
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    return k


def _resume(proc) -> None:
    import ctypes
    nt = ctypes.WinDLL("ntdll")
    nt.NtResumeProcess.argtypes = (ctypes.c_void_p,)
    nt.NtResumeProcess.restype = ctypes.c_long
    status = nt.NtResumeProcess(int(proc._handle))
    if status != 0:
        raise OSError(f"NtResumeProcess failed with status {status:#x}")


class _Job:
    """A Windows Job Object that kills every process in it when closed."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                        ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic),
                        ("IoInfo", ctypes.c_ulonglong * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self._k = _kernel()
        self._lock = threading.Lock()
        self.handle = self._k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        if not self._k.SetInformationJobObject(
                self.handle, _EXTENDED_LIMITS, ctypes.byref(info),
                ctypes.sizeof(info)):
            err = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise err

    def assign(self, proc) -> None:
        import ctypes
        if not self._k.AssignProcessToJobObject(self.handle,
                                                int(proc._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self) -> None:
        with self._lock:
            if self.handle:
                self._k.TerminateJobObject(self.handle, 1)

    def active(self) -> int:
        """How many processes in the job are still alive."""
        import ctypes
        from ctypes import wintypes

        class Accounting(ctypes.Structure):
            _fields_ = [("TotalUserTime", ctypes.c_longlong),
                        ("TotalKernelTime", ctypes.c_longlong),
                        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                        ("TotalPageFaultCount", wintypes.DWORD),
                        ("TotalProcesses", wintypes.DWORD),
                        ("ActiveProcesses", wintypes.DWORD),
                        ("TotalTerminatedProcesses", wintypes.DWORD)]
        got = Accounting()
        with self._lock:
            if not self.handle or not self._k.QueryInformationJobObject(
                    self.handle, _BASIC_ACCOUNTING, ctypes.byref(got),
                    ctypes.sizeof(got), None):
                return 0
        return int(got.ActiveProcesses)

    def wait_empty(self, seconds: float) -> bool:
        """True once no process in the job is alive; False at `seconds`."""
        end = time.monotonic() + seconds
        while self.active():
            if time.monotonic() >= end:
                return False
            time.sleep(0.02)
        return True

    def close(self) -> None:
        """Closing the last handle kills whatever is still in the job."""
        with self._lock:
            if self.handle:
                self._k.CloseHandle(self.handle)
                self.handle = None


# -- reading what the child saw ----------------------------------------------

def _rows(info: dict, limit: int) -> list[dict]:
    """The results the child read, or BrowserFailed saying what Google
    answered instead. A page that is not plainly results is never taken for
    one."""
    kind = info.get("kind")
    if kind == "no_playwright":
        raise BrowserFailed("playwright is not installed in this Mentis's "
                            "Python, so the Google browser backup cannot run")
    if kind == "no_chromium":
        raise BrowserFailed(f"Playwright's Chromium is not installed, so the "
                            f"Google browser backup cannot run (run "
                            f"`{INSTALL_CHROMIUM}`)")
    if kind == "timeout":
        raise BrowserFailed(f"Google did not answer in time: "
                            f"{info.get('why') or 'timed out'}")
    if kind != "page":
        raise BrowserFailed(f"the browser failed: "
                            f"{info.get('why') or 'no reason given'}")
    blocked = why_not_results(info)
    if blocked:
        raise BrowserFailed(blocked)
    out = []
    for r in info.get("rows") or ():
        if not isinstance(r, dict):
            continue
        url = _unwrapped(str(r.get("url") or ""))
        if not url or _is_google_search(url):
            continue
        out.append({"title": r.get("title"), "url": url,
                    "snippet": r.get("snippet"), "engine": "google"})
        if len(out) >= limit:
            break
    return out


def why_not_results(info: dict) -> str | None:
    """Why the page the browser landed on is not Google's results, or None.
    Bot checks first: they can carry a results-like frame. The page's words
    are read only when it is not a results page, so a search FOR "unusual
    traffic" is not taken for Google's bot check."""
    url = str(info.get("url") or "")
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    results = bool(info.get("results_page"))
    text = "" if results else str(info.get("text") or "").lower()
    if ("/sorry/" in parts.path or info.get("captcha")
            or "unusual traffic" in text or "not a robot" in text):
        return ("Google answered with its bot check (\"unusual traffic\" / "
                "CAPTCHA) instead of results; it is not bypassed, so the "
                "browser backup has nothing to give until Google lets this "
                "network search again")
    if host.startswith("consent.") or "before you continue" in text:
        return ("Google answered with its cookie consent page instead of "
                "results; it is not clicked through, so the browser backup "
                "cannot search from here")
    if not results:
        title = str(info.get("title") or "")[:120]
        return (f"Google's answer was not a results page (title "
                f"{title!r}, at {host or 'no host'})")
    return None


def _unwrapped(url: str) -> str:
    """A Google redirect link (`/url?q=...`) as the address it leads to."""
    parts = urllib.parse.urlsplit(url)
    if _is_google_search(url) and parts.path == "/url":
        query = urllib.parse.parse_qs(parts.query)
        for key in ("q", "url"):
            if query.get(key):
                return query[key][0]
    return url


def _is_google_search(url: str) -> bool:
    """A link back into Google's own search site (more results, settings),
    not a result. Google's other sites -- support, developers -- are kept."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return bool(re.fullmatch(r"(?:www\.)?google\.[a-z]{2,3}(?:\.[a-z]{2})?",
                             host))


# -- the child: this file run as a script ------------------------------------

def search_url(q: str, limit: int) -> str:
    """Google's results page for `q`, in English, as the source built it."""
    return ("https://www.google.com/search?" + urllib.parse.urlencode(
        {"q": q, "num": limit + 5, "hl": "en"}))


#: What marks Google's bot check on a page (the source's `_is_blocked`).
BLOCK_SELECTOR = ("iframe[src*='recaptcha'], #captcha-form, "
                  "form[action*='sorry'], div.g-recaptcha")
#: What the page is waited for: results, or a reason there are none.
READY_SELECTOR = "div#search, " + BLOCK_SELECTOR

#: The source's result-reading script (`_do_google_search`), unchanged but
#: for its name: each result's title, link and snippet in page order.
READ_RESULTS_JS = """
(numResults) => {
    const results = [];
    const containers = document.querySelectorAll('div#search div.g');
    for (const el of containers) {
        if (results.length >= numResults) break;
        const linkEl = el.querySelector('a[href^="http"]');
        const titleEl = el.querySelector('h3');
        const snippetEl = el.querySelector(
            'div[data-sncf], div.VwiC3b, span.aCOpRe, div[style*="-webkit-line-clamp"]'
        );
        if (linkEl && titleEl) {
            results.push({
                title: titleEl.innerText.trim(),
                url: linkEl.href,
                snippet: snippetEl ? snippetEl.innerText.trim() : ''
            });
        }
    }
    if (results.length === 0) {
        const allLinks = document.querySelectorAll('div#search a[href^="http"]');
        for (const a of allLinks) {
            if (results.length >= numResults) break;
            const h3 = a.querySelector('h3');
            if (h3) {
                const parent = a.closest('div.g') || a.parentElement?.parentElement;
                const snippetEl = parent?.querySelector(
                    'div[data-sncf], div.VwiC3b, span.aCOpRe, div[style*="-webkit-line-clamp"]'
                );
                results.push({
                    title: h3.innerText.trim(),
                    url: a.href,
                    snippet: snippetEl ? snippetEl.innerText.trim() : ''
                });
            }
        }
    }
    return results;
}
"""


def look(page, limit: int) -> dict:
    """What the page in front of the browser is: where it is, whether it is
    a results page or a bot check, and the results read off it."""
    info = {"kind": "page", "url": page.url, "title": page.title(),
            "captcha": page.locator(BLOCK_SELECTOR).count() > 0,
            "results_page": page.locator("div#search").count() > 0,
            "text": page.evaluate(
                "document.body ? document.body.innerText.slice(0, 600) : ''"),
            "rows": []}
    if info["results_page"] and not info["captcha"]:
        info["rows"] = page.evaluate(READ_RESULTS_JS, limit + 5)
    return info


def _child(argv: list[str]) -> dict:
    ask = json.loads(argv[1])
    q, limit = ask["q"], int(ask["limit"])
    end = time.monotonic() + float(ask["budget"])

    def left_ms() -> float:
        return max(1.0, (end - time.monotonic()) * 1000)
    try:
        from playwright.sync_api import Error, TimeoutError as PwTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"kind": "no_playwright"}
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True,
                                             timeout=left_ms())
            except PwTimeout as exc:
                return {"kind": "timeout", "why": _first_line(exc)}
            except Error as exc:
                said = str(exc)
                if ("Executable doesn't exist" in said
                        or "playwright install" in said):
                    return {"kind": "no_chromium"}
                return {"kind": "error", "why": _first_line(exc)}
            try:
                page = browser.new_context(locale="en-US").new_page()
                page.goto(search_url(q, limit), wait_until="domcontentloaded",
                          timeout=left_ms())
                if "/sorry/" not in page.url:
                    try:
                        page.wait_for_selector(READY_SELECTOR,
                                               timeout=left_ms())
                    except PwTimeout:
                        pass          # read as it is: not a results page
                return look(page, limit)
            except PwTimeout as exc:
                return {"kind": "timeout", "why": _first_line(exc)}
            finally:
                browser.close()
    except Exception as exc:                             # noqa: BLE001
        return {"kind": "error",
                "why": f"{type(exc).__name__}: {_first_line(exc)}"}


def _first_line(exc) -> str:
    return (str(exc).strip().splitlines() or [""])[0][:300]


if __name__ == "__main__":
    sys.stdout.write(_MARK + json.dumps(_child(sys.argv)) + "\n")
    sys.stdout.flush()
