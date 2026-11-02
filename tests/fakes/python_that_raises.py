"""`mentis.web`, unchanged but for ways to make a handler raise where no request can.

    python tests/fakes/python_that_raises.py <the arguments `python -m mentis.web` takes>

`tests/front/test_handler_failure.py` needs a raise after a commit, and with half a head written,
and neither has a request that reaches it. So this replaces what they raise from, and then starts
the real server: every request goes through the real `_Handler`, and the routes that write, write.

- `POST /api/conversations`: commits, and then `_send`'s `json.dumps` raises, as if on its answer.
- `POST /fluid/api/posts`: commits, and then `dispatch_soon` raises if there is anything to start.
- `POST /api/raises/<how>`: as `RAISES` says.
"""

from __future__ import annotations

import sys
import threading

import mentis.web as web
from mentis.web import _Handler, _Server


def _half_a_head(handler):
    handler.send_response(200)
    handler.send_header("X-Half", "this head was never ended")
    raise RuntimeError("stand-in: after send_response, before end_headers")


def _a_whole_head(handler):
    handler.send_response(200)
    handler.send_header("Content-Length", "5")
    handler.end_headers()
    raise RuntimeError("stand-in: after the head")


def _raises(what):
    def raising(_handler):
        raise what
    return raising


def _flight(handler):
    """Whether draining had let go of the last 500 before it was sent, and what it counts now."""
    return handler._send(200, {"left_before_its_500": handler.server.left_before_500,
                               "now": handler.server._in_flight})


RAISES = {"half-a-head": _half_a_head, "a-whole-head": _a_whole_head,
          "timeout": _raises(TimeoutError("stand-in: a handler's own timeout")),
          "client-gone": _raises(ConnectionResetError("stand-in: the client went")),
          "flight": _flight}

_real_api, _real_send, _real_leave = _Handler._api, _Handler._send, _Server.leave
#: Per connection, and each of these closes after one request: `ThreadingHTTPServer`'s own thread.
_this_thread = threading.local()


def _api(self, parsed, body, method):
    if parsed.path.startswith("/api/raises/"):
        return RAISES[parsed.path[len("/api/raises/"):]](self)
    return _real_api(self, parsed, body, method)


def _send(self, code, payload=None, raw=None, ctype="application/json"):
    if code == 200 and self.command == "POST" and self.path == "/api/conversations":
        raise TypeError("stand-in: json.dumps in _send, after the commit")
    if code == 500:
        self.server.left_before_500 = getattr(_this_thread, "left", False)
    return _real_send(self, code, payload, raw, ctype)


def _leave(self):
    _this_thread.left = True
    _real_leave(self)


def _dispatch_soon(_st, **_kw):
    raise RuntimeError("stand-in: dispatch_soon, after the commit")


_Handler._api, _Handler._send, _Server.leave = _api, _send, _leave
_Server.left_before_500 = None
web.dispatch_soon = _dispatch_soon

if __name__ == "__main__":
    raise SystemExit(web.main(sys.argv[1:]))
