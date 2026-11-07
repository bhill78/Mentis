/* THE HORIZONTAL PAGE SEQUENCE. Round 5 bootstrap by S; package P owns the
 * body.
 *
 * Conversation is always first: it is the existing `this-post` Page under its
 * Quiet label, never a second conversation Page implementation.
 *
 * THE BOOTSTRAP DRAWS NOTHING. A strip of placeholder tabs would be a set of
 * controls that look like they go somewhere, and a "+" that made nothing
 * would be worse: a Page is made by `nav.newPage()` once the origin Holder is
 * ready, which is P's work, so until P lands there is no affordance here at
 * all.
 */
import type { PageStripView } from '../contract'
import './pages.css'

export const PageStrip: PageStripView = () => null

export default PageStrip
