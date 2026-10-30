/* THE MAGNET'S INTERACTION CHOICES, HELD OPEN (part P7, stage A).
 *
 * The owner tries the first Magnet before its presentation is finished
 * (Turn #1442) and may change any of these. Each is the plan's behaviour
 * (adm-b848fa881c8d §3.6, §3.7, §3.10) and is decided HERE, once, so that
 * changing one is an edit to this file and nothing else. Browser-free. */

import type { Level } from '../types'
import type { MagnetSeed } from './types'

export const MAGNET_CHOICES = {
  /** The level a new Magnet starts at: its disc (§3.10 "compact disc"). */
  newLevel: 'icon' as Level,
  /** Where wide puts a new Magnet: the server's chosen fallback (§3.7), a
   *  window at a stepped corner rectangle, drawn at its level -- so at
   *  `newLevel` it is a disc at that rectangle's corner. 'dock' would put it
   *  in the sections instead. */
  wideFallback: 'launcher' as 'launcher' | 'dock',
  /** What a tap (click) on the disc does: one level up, Expand (§3.6 icon row:
   *  "tap = Expand"). A hold or right-click opens T2, as on every surface. */
  discTap: 'expand' as 'expand' | 'open',
  /** What a double-click on the disc does (§3.6: "double-click = Open"):
   *  here Open as workspace, the Magnet's one way out to a place. */
  discDoubleTap: 'openAsWorkspace' as 'openAsWorkspace' | 'none',
  /** Make magnet on a conversation that already has a Magnet here: show the
   *  one there (§3.10 "Reveal existing"), rather than make a second. */
  secondMake: 'reveal' as 'reveal' | 'create',
  /** The disc's diameter and the compact pane's size, wide (px). Standard
   *  and expanded use the window's own rectangle. */
  disc: 56,
  compact: { w: 340, h: 440 },
  /** Unread on the disc: posts newer than when this browser last opened the
   *  Magnet past its disc (device-local, like Close); a new Magnet starts
   *  with nothing unread. */
  unreadFrom: 'last-opened-here' as const,
  /** Selecting a post in a Magnet reads it in its own conversation's place
   *  (§3.10: Reply routes to Open there; expanded Magnets are read-only). */
  postTap: 'readInItsPlace' as const,
  /** Where Make magnet is offered in this build: a conversation's workspace.
   *  Home and the Stream draw zones by other rules, so it is disabled there
   *  with this reason. */
  onlyIn: 'conversation' as const,
  notHere: 'Magnets go in a conversation’s workspace in this build: open a conversation first.',
} as const

/** What a Magnet made from a conversation is set up to collect: its posts,
 *  files and images, once, drawn as a disc. */
export function conversationSeed(conversation: string): MagnetSeed {
  return {
    sources: [{ kind: 'conversation', conversation }],
    selection: { informationTypes: ['post', 'file', 'image'] },
    collection: { mode: 'one-time' },
    synthesis: { mode: 'manual' },
    notifications: { newItems: false, changes: false, failures: false },
    presentation: { renderer: 'disc' },
  }
}
