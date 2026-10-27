/* Home's sections, registered. Importing this module (as Home does) puts
 * every built-in section in the registry; the import order is the order the
 * picker offers them. */

import './conversation'
import './briefing'
import './work'
import './needsYou'
import './forYou'
import './activity'
import './kept'

export { registerSection, sectionOf, sections, sectionOptions } from './registry'
export type { Chrome, ChromeParts, SectionBodyProps, SectionDef } from './registry'
