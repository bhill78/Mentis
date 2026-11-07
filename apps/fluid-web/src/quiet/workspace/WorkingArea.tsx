/* THE WORKING AREA. Round 5 bootstrap by S; package W2 owns the body.
 *
 * W2 replaces this with the existing Fluid zones over the origin Holder, and
 * O adds the floating, object and Magnet hosts inside the area it measures.
 *
 * THE BOOTSTRAP SAYS THERE IS NOTHING HERE YET, in those words. It is the one
 * placeholder in this round that draws anything at all, because the alternative
 * is an empty rectangle beside the conversation that looks like a workspace
 * that lost its contents. It offers no action: there is nothing it could
 * honestly do, and a Keep or a float that silently did nothing would be worse
 * than a sentence saying so.
 */
import type { WorkingAreaView } from '../contract'
import './working.css'

const WorkingArea: WorkingAreaView = () => (
  <div className="qw-area" role="group" aria-label="Working area">
    <p className="qw-area-empty">This working area has no content yet.</p>
  </div>
)

export default WorkingArea
