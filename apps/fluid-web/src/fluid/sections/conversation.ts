/* -- Section: Conversation ---------------------------------------------------
 *
 * A zone showing `conversation` draws the conversation column itself
 * (conversation/HomeColumn.tsx, given by the frame; owner decision D1,
 * #599). Home draws it in the zone, so the section has no body; it docks
 * as the rail when narrowed. */

import { registerSection } from './registry'

registerSection({ show: 'conversation', name: 'Conversation', conversation: true })
