/* WHICH CONVERSATION A LINK INSIDE THE READING BELONGS TO (F6). Round 5
 * bootstrap by S; package R owns the body and mounts it.
 *
 * WHY A HELPER AND NOT A RULE IN EVERY LINK. Quiet reads one conversation on
 * a Page that belongs to another: a Deep dive's posts are the child's, and
 * the Holder, the Page sequence and the address all still belong to the
 * origin. A link written inside that reading has to keep the origin and the
 * Page; a link LEAVING it must not, because carrying the suffix out would
 * point it back home. One helper decides which, and Post, ParentHeader, the
 * Rail and the Activity panel all ask it.
 */
import { createContext, useCallback, useContext, type ReactNode } from 'react'
import type { Id } from '../../api'
import { href } from '../model'
import type { QuietHref } from '../contract'

interface Here {
  originConversation: Id
  effectiveConversation: Id
  page: string
}

const Navigation = createContext<Here | null>(null)

export function QuietNavigationProvider(props: {
  originConversation: Id
  effectiveConversation: Id
  page: string
  children?: ReactNode
}): ReactNode {
  const { originConversation, effectiveConversation, page, children } = props
  return (
    <Navigation.Provider value={{ originConversation, effectiveConversation, page }}>
      {children}
    </Navigation.Provider>
  )
}

/** HOW TO WRITE A LINK FROM HERE. With no provider mounted this is exactly
 *  `model.href` and every existing link is unchanged -- which is also what
 *  /fluid and the welcome page get. */
export function useQuietHref(): QuietHref {
  const here = useContext(Navigation)
  return useCallback(
    (conversation: Id, topic: Id | null = null, turn: Id | null = null) =>
      here && conversation === here.effectiveConversation
        ? href(conversation, topic, turn, {
          originConversation: here.originConversation,
          page: here.page,
          effectiveConversation: here.effectiveConversation,
        })
        : href(conversation, topic, turn),
    [here],
  )
}
