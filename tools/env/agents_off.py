"""What an environment with agents off runs where MARS would be.

`MENTIS_MARS_COMMAND` cannot be empty (the server would then look for `mars` on PATH, which
may be another environment's), so an environment whose `agents` is false is given this
instead. It says why and exits without speaking the protocol: no runtime is ever listed, and
every dispatch fails and is recorded as failed. It starts nothing and reads nothing.
"""

import sys

sys.stderr.write("agents are off in this Mentis environment (tools/env/environments.json, "
                 "\"agents\": false): no MARS is started here\n")
raise SystemExit(3)
