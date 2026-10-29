/* A REPLY THREAD AS A WORK SURFACE (owner feedback, round 2: "Conversation
 * replies still are awkward ... I would think it should match everything
 * else, including having a search like the conversations do").
 *
 * A thread is a content like a section or an object (focus/model.ts
 * THREAD_SHOW): it opens in a window beside the conversation
 * (focus/threadWindow.ts), and like every window it is docked, made primary,
 * focused, pinned and minimised, with the chrome every window has -- grip,
 * title, minimise, gear and close. The zone body (Zones.tsx WorkspaceZone) draws this
 * wherever it is: a window, a section, the primary column, the Focus area.
 *
 * Inside, the thread reads and is replied to exactly as beside the
 * conversation (Sheets.tsx ThreadBody: its root, its replies, Show N earlier,
 * its own composer, what is unread). 🔍 searches it (search-in/). Its ⋯ is
 * the same columns as every window's (workspace/zoneMenu.tsx): Thread (Follow,
 * the post, Search, full screen), Look, Arrange. The sheet's own head icons
 * (⇢ follow, 📌 pin, its ✕) are gone from here: Follow is in the menu by
 * name, pinning is the window's, closing is its ×. */

import { useCallback, useRef, useState } from 'react'
import * as nav from '../nav'
import { repliesOf } from '../store'
import { useCollection, useNav, usePost } from './hooks'
import { ThreadBody } from './Sheets'
import { useThreads } from './threads'
import { Sheet } from '../frame/Sheet'
import { GearMark, IconMenu, type IconGroup, type IconItem } from '../frame/IconMenu'
import { SectionSpin, useSectionLoad } from '../../loading'
import { SearchButton, useFocusSearch } from '../search-in/FocusSearch'
import { DEFAULT_APPEARANCE, readAppearance, zoneAppearanceStyle } from '../present'
import { useScheme } from '../frame/look'
import { useArr, workspace } from '../workspace/place'
import { ZoneTools, type ZoneCtl } from '../workspace/TreeView'
import { FloatingHeader, type FloatingZoneHead } from '../focus/FloatingHeader'
import type { Rect, Zone } from '../workspace/tree'
import { arrangeGroup, lookGroup, placeItems, windowItems } from '../workspace/zoneMenu'
import { lookOf, primaryOf, setThreadLook, swapBack, threadRootOf } from '../focus/model'
import { onPage, pageView } from '../focus/page'
import { focusSurface } from '../focus/lensImpl'
import { followIn } from '../focus/threadWindow'

/** The thread's title: its post and how many replies it has. */
export function threadTitle(number: number | null | undefined, replies: number): string {
  return `${number != null ? `#${number}` : 'Thread'} · ${replies} ${replies === 1 ? 'reply' : 'replies'}`
}

export function ThreadZone({ z, ctl, page, floating }: { z: Zone; r: Rect; ctl: ZoneCtl; page: string; first: boolean; floating?: FloatingZoneHead }) {
  const root = threadRootOf(z) ?? ''
  const conversation = typeof z.options?.conversation === 'string' ? z.options.conversation : null
  const post = usePost(root)
  const coll = useCollection('thread:' + root)
  const s = useNav()
  useThreads()
  const title = threadTitle(post?.number, coll?.total ?? (post ? repliesOf(post) : 0))
  const name = post?.number != null ? `Thread #${post.number}` : z.name ?? 'Thread'
  const loadId = 'fluid:thread-window:' + z.id
  useSectionLoad(loadId, name, { loading: !coll, error: null, data: coll ? true : null })
  const [menuAt, setMenuAt] = useState<HTMLElement | null>(null)
  const close = useCallback(() => setMenuAt(null), [])
  /* FOCUS SEARCH, as the conversation has it: in the thread's posts. Kept by
     the content's id, so the window docked or made primary finds it again. */
  const box = useRef<HTMLDivElement | null>(null)
  const search = useFocusSearch(() => box.current?.querySelector<HTMLElement>('.fw-thread-body') ?? null, undefined, z.id)
  const scheme = useScheme()
  const placeLook = readAppearance(useArr().appearance, DEFAULT_APPEARANCE)
  const own = lookOf(z)
  const appearance = readAppearance(own, placeLook)
  const look = zoneAppearanceStyle(appearance, scheme)
  const setLook = (a: typeof appearance | undefined, words?: string) => workspace.edit(onPage((v) => setThreadLook(v, z.id, a), page), words)
  /* FOLLOW, by name (it was the sheet's ⇢): this window shows the replies of
     each post read in the conversation; reading a reply in it moves nothing. */
  const following = !!s.follow && z.options?.follow === true
  const thread: IconItem[] = [
    { id: 'follow', icon: '⇢', label: following ? 'Following' : 'Follow', on: following,
      says: following ? 'Following the post you read: each post you read shows its replies here. Press to stop' : 'Follow the post you read: each post you read shows its replies in this window',
      onPick: () => followIn(following ? null : z.id, page) },
    { id: 'post', icon: '↗', label: 'Post', says: `Read ${post?.number != null ? `#${post.number}` : 'the post'} in its conversation`,
      off: !post, onPick: () => { if (post) nav.read(post.home ?? conversation ?? s.conversation ?? '', root, post.number ?? null) } },
    { id: 'search', icon: '🔍', label: 'Search', says: `Search in ${name}`, onPick: () => search.setOpen(true) },
    { id: 'full', icon: '⤢', label: 'Full', says: 'Full screen: enlarge the whole thread over everything (Esc returns)',
      onPick: () => nav.openDetail({ kind: 'full', of: 'thread', id: root, anchor: { kind: 'post', id: root }, mode: 'over' }) },
  ]
  const view = pageView(workspace.arr, page)
  const back = !floating && primaryOf(view) === z.id && view.focus?.previous?.length
    ? () => workspace.edit(onPage(swapBack, page), 'Swapped back to the primary before.') : undefined
  const arrange = [
    ...placeItems(ctl, { floating: !!floating, back, focus: () => focusSurface(z.id, name) }),
    ...(floating?.window ? windowItems(floating.window) : []),
  ]
  const groups: IconGroup[] = [
    { title: 'Thread', items: thread, summary: following ? 'Following what you read' : 'This thread' },
    (() => {
      const g = lookGroup({
        value: appearance, onChange: (a) => setLook(a),
        reset: { run: () => setLook(undefined, `${name} takes this place's look again.`), isDefault: !own },
      })
      return { ...g, summary: [(g.items ?? []).find((it) => it.on)?.label, typeof appearance.opacity === 'number' ? `${Math.round(appearance.opacity * 100)}%` : null].filter(Boolean).join(' · ') }
    })(),
    ...(arrangeGroup(arrange) ? [{ ...arrangeGroup(arrange)!, summary: floating ? 'Floating window' : 'Docked' }] : []),
  ]
  return (
    <section className={'wk-zone wk-panel fq-thread-zone ' + look.className} style={look.style} data-zone="thread" data-thread={root}
      data-zone-name={name} aria-label={`${name} thread`} aria-busy={!coll || undefined}>
      {floating ? <FloatingHeader name={name} title={title} floating={floating} menuAt={menuAt} onMenu={setMenuAt}
        settingsTitle={`Settings for ${name}: the thread, how it looks, where it sits`} /> :
      <div className="wk-zcap">
        <span className="wk-what" title={title}>{title}</span>
        <SectionSpin id={loadId} label={name} />
        <span className="wk-grow" />
        <ZoneTools ctl={ctl} name={name} search={<SearchButton onOpen={() => search.setOpen(true)} label={`Search in ${name}`} />} />
        <button className="wk-zmenu" aria-label={`${name} settings`} title={`Settings for ${name}: the thread, how it looks, where it sits`} aria-expanded={!!menuAt}
          onClick={(e) => setMenuAt(e.currentTarget)}><GearMark /></button>
      </div>}
      {search.bar}
      <div ref={box} className="fq-thread fx-sheet fw-thread" data-thread={root}>
        {root ? <ThreadBody root={root} conversation={conversation} /> : <p className="wk-quietline">This thread has no post to show.</p>}
      </div>
      {menuAt && (
        <Sheet anchor={menuAt} onClose={close} label={`${name} menu`}>
          <IconMenu groups={groups} label={name} onDone={close} layout="accordion" />
        </Sheet>
      )}
    </section>
  )
}
