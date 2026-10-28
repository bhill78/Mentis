/* The sections, registered. Importing this module (as Home and the
 * workspace do) puts every built-in section in the registry; the import
 * order is the order the pickers offer them -- Home's collections, then
 * this conversation's views (which Home never offers; a conversation
 * section's picker offers them first, `sources('conversation')`). */

import './conversation'
import './briefing'
import './work'
import './needsYou'
import './forYou'
import './activity'
import './kept'
import './conversationViews'

export { registerSection, sectionOf, sections, sectionOptions, sources } from './registry'
export type { Chrome, ChromeParts, SectionBodyProps, SectionDef } from './registry'
