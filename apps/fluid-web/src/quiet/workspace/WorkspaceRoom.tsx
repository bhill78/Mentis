/* THE ROOM THE CONVERSATION AND ITS WORKING AREA SHARE. Round 5 bootstrap by
 * S; package L owns the body and its CSS.
 *
 * WHY THE BOOTSTRAP IS NOT EMPTY (F11). Four packages mount into this room at
 * once and two of them -- W2 and P -- have to be inspectable before L has
 * drawn anything. So the bootstrap renders ALL FOUR fixed slot containers:
 *
 *    conversation   the reading and its one composer
 *    tools          the consolidated navigation and contextual readings
 *    working        the working stage
 *    pageControls   the Page sequence and its arrows
 *
 * THESE NAMES AND THESE MOUNT IDENTITIES ARE FIXED. L replaces the body and
 * keeps them: a slot that moved or was conditionally mounted would reparent
 * somebody else's React subtree and lose the state in it (F27).
 *
 * THE SAVED MODE SAYS WHICH MAIN SURFACE IS ACTIVE, and a parked surface is
 * INERT AND HIDDEN -- `hidden`, so it cannot be reached by Tab -- rather than
 * an absent slot. The Page controls are reachable in every mode, which is why
 * they are outside the parked surfaces, and Return to conversation is
 * explicit rather than implied by closing something.
 *
 * It draws no mode switch: choosing between Single chat, Chat and panes and
 * Workspace board is L's control, and a bootstrap one would be a control the
 * owner's decision has not been drawn for yet.
 */
import type { WorkspaceRoomView } from '../contract'
import './room.css'

/** Which main surface this mode shows. Single chat is the conversation alone;
 *  the other two show the working area beside or instead of it. The narrow
 *  choice of ONE active surface is drawing state and is not this bookmark. */
const showsWorking = (mode: string) => mode === 'panes' || mode === 'board'

const WorkspaceRoom: WorkspaceRoomView = ({
  page,
  room,
  onRoom,
  conversation,
  tools,
  working,
  pageControls,
}) => {
  const working_ = showsWorking(room.mode)
  const back = (): void => {
    /* Return to conversation is a room change, not a navigation: the reading
       was never closed, only parked. */
    if (working_) onRoom({ mode: 'single' })
  }
  return (
    <div className="qw-room" data-mode={room.mode} data-page={page}>
      <div className="qw-slot qw-conversation" data-slot="conversation">
        {conversation}
      </div>
      <div className="qw-slot qw-tools" data-slot="tools">
        {tools}
      </div>
      <div className="qw-slot qw-working" data-slot="working" hidden={!working_}>
        {working}
      </div>
      <div className="qw-slot qw-page-controls" data-slot="pageControls">
        {pageControls}
      </div>
      {working_ ? (
        <button type="button" className="qw-return" onClick={back}>
          Return to conversation
        </button>
      ) : null}
    </div>
  )
}

export default WorkspaceRoom
