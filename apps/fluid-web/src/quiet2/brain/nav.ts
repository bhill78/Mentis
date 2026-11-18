/* WHERE A RECORD'S LINKS GO. A record is read in two places -- the main
 * reading area (opened from the Brain browser) and a working surface beside
 * the conversation (opened from a post's record mark) -- and in each a link
 * to another record, to a post, or to the browser means something different.
 * Whoever hosts the record says what; the record only asks. */
import { createContext, useContext } from 'react'
import type { Id } from '../../api'

export interface BrainNav {
  /** another record, read where this one is, with Back to this one */
  openRecord: (id: Id) => void
  /** the post a record points at: its conversation shown, the post found */
  goToPost: (conversation: Id, turn: Id) => void
  /** this record in the main reading area (from beside); absent where it is there already */
  openFull?: (id: Id) => void
  /** the Brain browser, as it was left */
  openBrowser?: () => void
  /** authoring: a new record of this Kind, optionally resting on this one */
  newRecord?: (kind: string, basis?: Id) => void
  /** what an agent would receive (optionally as a persona) */
  preview?: (persona?: Id) => void
  /** AN ENTRY THAT IS NOT A RECORD TO MANAGE, read read-only by the entry
   *  inspector (a topic, a participant, substrate, acquired material).
   *  Absent where its host has no such reader (3D Brain, addendum §4). */
  openEntry?: (id: Id) => void
  /** false: nothing that writes is offered (a read-only page) */
  canWrite: boolean
}

export const BrainNavContext = createContext<BrainNav | null>(null)
export const useBrainNav = (): BrainNav => useContext(BrainNavContext) ?? { openRecord: () => {}, goToPost: () => {}, canWrite: false }
