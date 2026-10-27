/* What Governance asks of the shell that holds it: who is acting, and the
 * moves only the shell can make -- open an item beside its conversation, go
 * back to the Governance page, read a Turn in the column. Provided by Shell
 * around everything it draws, so an item page inside the workspace reaches it
 * as the Governance page does. */

import { createContext, useContext } from 'react'
import type { Id } from '../../api'
import type { OpenHint, Source } from './model'

export interface GovNav {
  me: Id | null
  /** this Brain's owner as the server names it, or null where it names
   *  none: Set aside is offered only to the owner */
  owner: Id | null
  /** open an item: beside the conversation it was proposed from, as a tab
   *  next to This post. `edit` opens it with Propose new version… open. */
  openItem: (entry: Id, hint?: OpenHint | null, opts?: { edit?: boolean }) => void
  /** the Governance page, at a section where one is named: naming one
   *  closes the item open on its Stage, so that section is what shows.
   *  `card` focuses that entry's adoption card on For adoption. */
  openGov: (section?: string, opts?: { card?: Id | null }) => void
  /** close an item's page (its Close, its tab's ×): back to where it was
   *  opened from -- the Governance list, during a visit to Governance */
  closeItem: (page: string) => void
  /** read a Turn in the conversation column */
  readTurn: (conversation: Id, turn: Id) => void
  /** whether this item was asked to open with its edit form; asked once */
  takeEdit: (entry: Id) => boolean
  /** where this item was opened beside, when that was decided this session */
  sourceOf: (entry: Id) => Source | null | undefined
  /** bumped whenever an item is asked to open with its edit form, so an
   *  item already open is drawn afresh with it */
  editNonce: number
}

export const GovContext = createContext<GovNav | null>(null)

export function useGovNav(): GovNav {
  const g = useContext(GovContext)
  if (!g) throw new Error('Governance is drawn outside the Fluid shell')
  return g
}
