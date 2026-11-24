"""ACP fixture: acknowledge this prompt, then fail the runtime's turn."""
import asyncio
import sys

import acp
from acp import RequestError, update_agent_message_text
from mars_send_boundary_stand_in import SendBoundaryAgent


class AcknowledgedFailure(SendBoundaryAgent):
    async def prompt(self, session_id, prompt, **kwargs):
        self._write(event="prompt", session=session_id,
                    text="".join(getattr(block, "text", "") for block in prompt))
        await self.conn.session_update(session_id=session_id,
                                       update=update_agent_message_text("accepted, then failed"))
        raise RequestError.internal_error({"why": "runtime failed after acknowledgement"})


if __name__ == "__main__":
    asyncio.run(acp.run_agent(AcknowledgedFailure(sys.argv[1], "ack-fail"),
                              use_unstable_protocol=True))
