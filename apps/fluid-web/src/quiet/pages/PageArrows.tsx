/* PREVIOUS AND NEXT PAGE, BY DESTINATION. Round 5 bootstrap by S; package P
 * owns the body.
 *
 * `previous` or `next` null is an unavailable end, which is what disables
 * that control: the sequence does not wrap around, and a Page somebody cannot
 * go to is not offered.
 *
 * THE BOOTSTRAP DRAWS NOTHING, for the same reason as the strip: arrows that
 * reach nowhere are worse than no arrows.
 */
import type { PageArrowsView } from '../contract'
import './pages.css'

export const PageArrows: PageArrowsView = () => null

export default PageArrows
