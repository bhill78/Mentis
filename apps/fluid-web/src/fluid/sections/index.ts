/* The sections, registered. Importing this module (as Home and the
 * workspace do) puts every built-in section in the registry; the import
 * order is the order the pickers offer them -- this conversation's views
 * first, then Home's collections. */

import './conversationViews'
import './conversation'
import './briefing'
import './work'
import './needsYou'
import './forYou'
import './activity'
import './kept'

export { registerSection, sectionOf, sections, sectionOptions, sources } from './registry'
export type { Chrome, ChromeParts, SectionBodyProps, SectionDef } from './registry'
