"""The names a server and whoever stops it agree on, and nothing else.

Kept apart from `mentis.servers` so the server (`mentis.web`) imports without
psutil: only stopping a server needs psutil, serving one does not. This module
imports nothing outside the standard library and `mentis.spine.brainlock`.
"""

from __future__ import annotations

from mentis.spine.brainlock import SERVE_INFO

#: the graceful-shutdown endpoint (`mentis.web._Handler._shutdown`)
SHUTDOWN_PATH = "/api/server/shutdown"
#: the header carrying this start's token
SHUTDOWN_HEADER = "X-Mentis-Shutdown-Token"

__all__ = ["SERVE_INFO", "SHUTDOWN_HEADER", "SHUTDOWN_PATH"]
