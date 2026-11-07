/* THE ONE HOLDER AND NAV ADAPTER. Round 5 bootstrap by S; package W2 owns the
 * body.
 *
 * R MOUNTS THIS HOOK AND NOTHING ELSE. One entrance into the Holder, one
 * history path: W2 replaces this body to validate S's envelope through W1,
 * restore the travelling floats, enter with `localLayout`/`touched` under F9's
 * precedence and hydrate the Pages BEFORE anything captures them -- and R adds
 * no second entrance effect beside it.
 *
 * THE BOOTSTRAP DELEGATES TO THE HOLDER APIS THAT ALREADY EXIST and enters
 * nothing. It reads `fluid/nav.ts`'s Page list and changes it through the
 * existing operations, so the sequence is real from the first commit and
 * there is still exactly one Page list. It reports `ready: false`: no Holder
 * has been entered, so a caller that needs one knows it, rather than being
 * told yes by a placeholder.
 *
 * Quiet's destination history is the browser hash (F8), so the scoped
 * external-history adapter is mounted here -- `fluid/nav.ts`'s
 * `hostExternalNavigation` -- and removed again when this unmounts, which is
 * what keeps /fluid out of that scope.
 */
import { useEffect, useState, useSyncExternalStore } from 'react'
import {
  closePage,
  hostExternalNavigation,
  newPage,
  showPage,
  snapshot,
  subscribe,
  type ExternalNavigation,
} from '../../fluid/nav'
import type { WorkspaceRuntimeHook } from '../contract'
import { CONVERSATION_PAGE } from '../pages/location'
import { useWorkspaceBookmark } from './bookmarks'
import type { QuietSequencePage } from './types'

/** The runtime, as R reads it. */
export const useWorkspaceRuntime: WorkspaceRuntimeHook = ({ originConversation }) => {
  const nav = useSyncExternalStore(subscribe, snapshot, snapshot)
  const bookmark = useWorkspaceBookmark()
  const [, setArea] = useState<HTMLElement | null>(null)

  /* THE ONE SELECTION INTENT, reported to whoever writes the hash. The
     bookmark provider holds it; the location controller (R) reads it and is
     the only writer of the address. */
  const intend = bookmark?.intend
  useEffect(() => {
    if (!intend) return
    const host: ExternalNavigation = {
      page: (page) => intend({ originConversation, topic: null, turn: null, page }),
      /* the hash's turn is the post being read, in whichever conversation the
         Page's destination names */
      read: (_conversation, post, page) =>
        intend({ originConversation, topic: null, turn: post, page }),
    }
    return hostExternalNavigation(host)
  }, [intend, originConversation])

  const pages: QuietSequencePage[] = nav.pages.map((p) => ({
    id: p.id,
    title: p.id === CONVERSATION_PAGE ? 'Conversation' : 'title' in p ? p.title : p.id,
  }))

  return {
    ready: false,
    pages,
    page: nav.page,
    selectPage: showPage,
    addPage: () => {
      newPage()
    },
    closePage,
    setArea,
  }
}
