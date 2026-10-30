/* THE MINIMIZED CONVERSATION'S LAUNCHER (model.ts minimize, types.ts
 * `Minimized`). The conversation put away leaves its place to the page; what
 * stays is this: a narrow strip where the column was, its initial and its
 * name, how many posts came since it was put away, and a way back. Pressed,
 * it goes back where it was (Bring back); its ⋯, the one surface chrome's
 * (surface/SurfaceChrome.tsx, an icon: no direct controls), lists Bring back
 * with its other ways back -- as a floating window, as the column, or as a
 * section beside the primary -- and Find an action…. Over the 3D Brain the same
 * launcher waits in the Brain's tray (brain/BrainPlace.tsx).
 *
 * The conversation itself is still drawn, parked (hosts.tsx): the count is
 * read from what the store already holds for it, never asked for. */

import { useMemo } from 'react'
import { store, type Id } from '../store'
import { useCollection } from '../conversation/hooks'
import { focused, setFocused } from '../conversation/threads'
import { workspace } from '../workspace/place'
import { SurfaceChrome } from '../surface/SurfaceChrome'
import { chromeTarget, launcherHost } from '../surface/chromeHosts'
import { minimize, minimizedOf, restore, unreadSince, type RestoreAs } from './model'
import { onPage, shownPage, useShownView } from './page'

/** The room the main area has now, for a float's first rectangle. */
const mainRoom = () => {
  const r = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
  return { w: r?.width || 1200, h: r?.height || 800 }
}

/** Minimize the conversation on page `page` (the shown one): one step, which
 *  Undo takes back. Conversation focus is left, or nothing would be shown. */
export function minimizeConversation(page: string = shownPage()) {
  if (focused()) setFocused(false)
  workspace.edit(onPage((v) => minimize(v, Date.now()), page), 'Conversation minimized.')
}

/** Put it back: where it was, or `as` the launcher's menu says. */
export function restoreConversation(as?: RestoreAs, page: string = shownPage()) {
  const room = mainRoom()
  workspace.edit(onPage((v) => restore(v, as, room), page))
}

/** Posts in conversation `id` newer than `since` (epoch ms), of those the
 *  store holds for it. */
export function useUnread(id: Id | null, since: number): number {
  const coll = useCollection('conversation:' + (id ?? ''))
  return useMemo(() => {
    if (!id || !coll) return 0
    return unreadSince(coll.items.flatMap((p) => store.posts.get(p.id) ?? []), since)
  }, [id, coll, since])
}

export interface LaunchChoice { label: string; says?: string; run: () => void }

/** The launcher itself: `strip` where the column was, `tray` among what
 *  waits at the foot of the 3D Brain. */
export function Launcher({ conversation, name, since, onRestore, choices, variant = 'strip' }: {
  conversation: Id | null
  name: string
  since: number
  onRestore: () => void
  choices: LaunchChoice[]
  variant?: 'strip' | 'tray'
}) {
  const unread = useUnread(conversation, since)
  const called = name.trim() || 'Conversation'
  const said = unread ? `, ${unread} new ${unread === 1 ? 'post' : 'posts'}` : ''
  return (
    <div className={'fq-launcher fq-launcher-' + variant} role="group" aria-label="Minimized conversation">
      <SurfaceChrome target={chromeTarget('launcher:' + (conversation ?? 'conversation'), 'launcher-tile', 'launcher', launcherHost(onRestore, choices))}
        placement="launcher" level="icon" className="fq-launch-chrome"
        title={<button type="button" className="fq-launch" onClick={onRestore}
          aria-label={`Bring back ${called}${said}`} title={`Bring back ${called} where it was${said}`}>
          <span className="fq-launch-mark" aria-hidden="true">{[...called][0]?.toUpperCase()}</span>
          {unread > 0 && <span className="fq-launch-unread" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
          <span className="fq-launch-name">{called}</span>
        </button>} />
    </div>
  )
}

/** The launcher of the page shown, while its conversation is minimized. */
export default function PageLauncher({ conversation, name }: { conversation: Id | null; name: string }) {
  const { page, view } = useShownView()
  const m = minimizedOf(view)
  if (!m) return null
  return (
    <Launcher conversation={conversation} name={name} since={m.at} onRestore={() => restoreConversation(undefined, page)}
      choices={[
        { label: 'Restore as floating window', says: 'over the page, where you can move and size it', run: () => restoreConversation('float', page) },
        { label: 'Dock as column', says: 'at the left of the page, at its width', run: () => restoreConversation('column', page) },
        { label: 'Put in a section', says: 'beside the primary section', run: () => restoreConversation('leaf', page) },
      ]} />
  )
}
