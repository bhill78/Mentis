/* THE NARROW SHEET'S HEAD, AND THE WAY INTO IT (adm-c93a 5.6; narrow.ts).
 *
 *   ‹ Back to conversation   (Thread #152) (This post · #186) (Evidence) (Page 2)
 *
 * One pill per pane the sheet can show: the thread open or pinned here, then
 * the workspace's pages in their order. With the sheet closed, a quiet pair
 * of buttons at the column's top edge opens it on the workspace or the
 * thread. */

import * as nav from '../nav'
import { useNav, usePost } from '../conversation/hooks'
import { pinsOf, useThreads } from '../conversation/threads'
import { closeSheetPane, openPane, useSheetPane } from './narrow'

function ThreadPill({ on, here }: { on: boolean; here: string | null }) {
  const s = useNav()
  useThreads()
  const sheet = nav.sheetOf(s)
  const pinned = pinsOf(here)
  const root = sheet?.kind === 'replies' ? sheet.root : sheet?.kind === 'post-details' ? sheet.id : pinned.active
  const post = usePost(root ?? '')
  const label = sheet?.kind === 'about' ? 'About this conversation'
    : sheet?.kind === 'post-details' ? `Details${post?.number != null ? ` #${post.number}` : ''}`
      : `${!sheet ? '📌 ' : ''}Thread${post?.number != null ? ` #${post.number}` : ''}${!sheet && pinned.pinned.length > 1 ? ` +${pinned.pinned.length - 1}` : ''}`
  return (
    <button className={'fx-npill' + (on ? ' on' : '')} data-pill="thread" aria-current={on ? 'true' : undefined}
      onClick={() => openPane('thread')}>{label}</button>
  )
}

export default function NarrowHead({ here, threadOpen }: { here: string | null; threadOpen: boolean }) {
  const s = useNav()
  const pane = useSheetPane()
  return (
    <nav className="fx-nhead" aria-label="sheet">
      <button className="fx-nback" data-act="back-to-conversation" onClick={() => closeSheetPane()}>
        {'‹'} Back to conversation
      </button>
      <span className="fx-npills">
        {threadOpen && <ThreadPill on={pane === 'thread'} here={here} />}
        {s.pages.map((p) => {
          const on = pane === 'workspace' && s.page === p.id
          return (
            <button key={p.id} className={'fx-npill' + (on ? ' on' : '')} data-pill={p.id} aria-current={on ? 'page' : undefined}
              onClick={() => {
                /* The page already shown is only shown: moving to another page
                   closes a slid-out thread, as it does beside the conversation. */
                if (p.id !== nav.snapshot().page) nav.showPage(p.id)
                openPane('workspace')
              }}>
              {'title' in p ? p.title : `This post${s.readingNumber != null ? ` · #${s.readingNumber}` : ''}`}
            </button>
          )
        })}
      </span>
    </nav>
  )
}

/** With the sheet closed: open it on the workspace, or on the thread. */
export function NarrowOpen({ threadOpen }: { threadOpen: boolean }) {
  const s = useNav()
  return (
    <span className="fx-nopen" role="group" aria-label="open beside the conversation">
      {threadOpen && <button data-act="open-thread" onClick={() => openPane('thread')}>Thread {'›'}</button>}
      <button data-act="open-workspace" title="The workspace: This post and your pages"
        onClick={() => openPane('workspace')}>{s.pages.length > 1 ? `Workspace · ${s.pages.length} pages` : 'Workspace'} {'›'}</button>
    </span>
  )
}
