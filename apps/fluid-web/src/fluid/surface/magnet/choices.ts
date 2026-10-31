/* THE MAGNET'S INTERACTION CHOICES, HELD OPEN (part P7, stage A).
 *
 * The owner tries the first Magnet before its presentation is finished
 * (Turn #1442) and may change any of these. Each is the plan's behaviour
 * (adm-b848fa881c8d §3.6, §3.7, §3.10) and is decided HERE, once, so that
 * changing one is an edit to this file and nothing else. Browser-free. */

import type { Level } from '../types'
import type { MagnetSeed } from './types'
import type { Appearance } from '../../present/types'

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
  /** The disc's diameter, wide (px). */
  disc: 56,
  /** Opened from its disc in a window (compact), a Magnet is a slide-out:
   *  a panel out of the disc's centre, drawn at the window's own rectangle
   *  (saved like any window's), held within these bounds (owner Turn #1617).
   *  `normal` is a new window's rectangle (the server's launcher rect) and
   *  what Restore size returns to; `large` is what Enlarge asks for, as the
   *  room allows. Standard and expanded use the window's rectangle as is. */
  slide: { min: { w: 320, h: 300 }, max: { w: 1100, h: 940 }, normal: { w: 360, h: 480 }, large: { w: 820, h: 680 } },
  /** The slide-out's look until the owner gives it one of its own (amendment
   *  ent-56d18f7b54a5): Solid, fully opaque, for reading. It is the shared
   *  Appearance; Look in its actions changes it as any window's. */
  slideLook: { panel: 'solid', content: 'solid', opacity: 1 } as Appearance,
  /** The quick summary card, anchored with the disc at its corner (owner's
   *  sketch, Turn #1592), and how long a mouse rests on the disc before it
   *  shows; touch and the keyboard open it from Peek in the actions. */
  card: { w: 320, maxH: 460 },
  peekAfterMs: 450,
  /** How far a press on the disc moves before it is a move of the disc, not
   *  a tap or a hold (px; mouse, then touch and pen). On touch it is past the
   *  hold's own slop (chrome.ts LONG_PRESS_SLOP), so a move never also opens T2. */
  moveAfter: { mouse: 4, touch: 10 },
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
 *  files, images and media, and attachments, once, drawn as a disc. */
export function conversationSeed(conversation: string): MagnetSeed {
  return {
    sources: [{ kind: 'conversation', conversation }],
    selection: { informationTypes: ['post', 'file', 'image', 'attachment'] },
    collection: { mode: 'one-time' },
    synthesis: { mode: 'manual' },
    notifications: { newItems: false, changes: false, failures: false },
    presentation: { renderer: 'disc' },
  }
}
