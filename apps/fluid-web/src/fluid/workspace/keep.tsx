/* KEEP, WHEREVER THE READER CHOOSES (Fluid completion, stream A; #448:
 * "Kept content belongs wherever I choose, not in a mandatory Kept column").
 *
 * Keep offers, in this order: here (a following zone keeps it in place:
 * it stays while what is read changes), any other zone on this page, a new
 * zone beside this one, another page, or a new page. Dragging a card onto a
 * zone does the same without the menu: a followed card is kept there, a kept
 * one MOVES there (Ctrl keeps a copy). Every change has Undo. */

import { useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { store } from '../store'
import type { ObjectRef } from '../present'
import { shownOf, titleOf } from './hooks'
import { treeOf, withTree, workspace, type Arr } from './place'
import { Opt, Sec, Sheet } from '../frame/Sheet'
import { tabTitle } from './hooks'
import { canSplit, findZone, keepIn, keepSlot, splitZone, unkeep, zone, zones, type Rect } from './tree'

/** What a dragged card carries. */
export const DRAG = 'application/x-mentis-fluid-object'
/** What a post dragged by its head carries (D1): `{ post }`. Kept, it is
 *  what it is made of -- its words and every object in it, in order. */
export const POST = 'application/x-mentis-fluid-post'

interface Asking { item: ObjectRef; anchor: HTMLElement | null }
let asking: Asking | null = null
const fns = new Set<() => void>()
const emit = () => fns.forEach((fn) => fn())
const sub = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }
const useAsking = () => useSyncExternalStore(sub, () => asking)
/** What Keep is choosing a place for, for a chooser other than the
 *  workspace's (Home's, D1), and how it says it is done. */
export const useKeepAsked = useAsking
export const keepAsked = () => { asking = null; hinted = null; emit() }

/* -- WHILE SOMETHING IS BEING KEPT, THE ZONES SAY WHERE IT CAN GO (#568 3.3) --
 * During a drag of an object, or while Keep's choices are open (from a
 * zone's card, a detail, or ◆ on a post), every zone on the page shows
 * itself as a place for it; the zone a choice names is lit while that choice
 * is pointed at. Once kept, the zone that took it shows it arriving
 * (#568 3.1: choosing, keeping and locating read as one path). */
let dragging = false
let hinted: string | null = null
let landed: { zone: string; address: string; n: number } | null = null
let lands = 0
/** Something is being kept: a drag carrying an object, or Keep's choices open. */
export const useKeeping = () => useSyncExternalStore(sub, () => dragging || asking !== null)
/** The zone the pointed-at Keep choice names. */
export const useHinted = () => useSyncExternalStore(sub, () => hinted)
/** What just arrived in zone `zone`, for a moment. */
export const useLanded = (zone: string) => useSyncExternalStore(sub, () => (landed && landed.zone === zone ? landed : null))
const hint = (zone: string | null) => { if (hinted !== zone) { hinted = zone; emit() } }
/** Light the zone a choice names (a chooser other than the workspace's). */
export const hintZone = hint
export function land(zone: string, address: string) {
  const n = ++lands
  landed = { zone, address, n }
  emit()
  setTimeout(() => { if (landed?.n === n) { landed = null; emit() } }, 1800)
}
if (typeof document !== 'undefined') {
  document.addEventListener('dragstart', (e) => { if (e.dataTransfer?.types.includes(DRAG) || e.dataTransfer?.types.includes(POST)) { dragging = true; emit() } })
  const end = () => { if (dragging) { dragging = false; emit() } }
  document.addEventListener('dragend', end)
  window.addEventListener('drop', end, true)
}

const titleFor = (address: string) => {
  const st = store.objects.get(address)
  return st && 'object' in st ? titleOf(st.object) : 'it'
}
const zoneName = (a: Arr, page: string, id: string) => (treeOf(a, page) && findZone(treeOf(a, page)!, id)?.name) || 'the zone'
const pageTitle = (page: string) => {
  const p = nav.snapshot().pages.find((x) => x.id === page)
  return p && 'title' in p ? p.title : 'This post'
}

/** Offer the choices for `item`, anchored to `from`. The zone it is shown in
 *  (`item.zone`) is "here"; an object opened over the arrangement names the
 *  zone of the card it grew from. */
export function askKeep(item: ObjectRef, from?: HTMLElement | null) {
  const cell = (from ?? null)?.closest?.('[data-zone-id]') as HTMLElement | null
  const page = item.page ?? (from?.closest?.('[data-page]') as HTMLElement | null)?.dataset.page ?? nav.snapshot().page
  asking = { item: { ...item, zone: item.zone ?? cell?.dataset.zoneId, page }, anchor: from ?? null }
  emit()
}
const done = () => { asking = null; hinted = null; emit() }

/** Keep in zone `zoneId` of `page`; `move` takes it out of where it was kept. */
export function keepInZone(address: string, page: string, zoneId: string, move?: { page: string; zone: string }, inPlace = false) {
  /* Home keeps in its own arrangement (a card flicked between its zones). */
  if (page === 'home' && homeKeeper) { homeKeeper([address], zoneId, move); return }
  const a = workspace.arr
  const t = treeOf(a, page)
  const z = t && findZone(t, zoneId)
  if (!t || !z) return
  const already = z.slot?.items.includes(address)
  const here = move && move.page === page && move.zone === zoneId
  if (already || here) { nav.toast({ text: `${titleFor(address)} is already kept in ${z.name ?? 'that zone'}.` }); return }
  const following = z.slot?.follow
  workspace.edit((x) => {
    let y = withTree(x, page, keepIn(treeOf(x, page)!, zoneId, address))
    if (move) y = withTree(y, move.page, unkeep(treeOf(y, move.page)!, move.zone, address))
    return y
  }, move
    ? `Moved ${titleFor(address)} to ${z.name ?? 'the zone'}.`
    : following && inPlace
      ? `Kept ${titleFor(address)} here: it stays while you read other posts.`
      : `Kept ${titleFor(address)} in ${z.name ?? 'the zone'}${page !== nav.snapshot().page ? ` on ${pageTitle(page)}` : ''}.`)
  land(zoneId, address)
}

/** Keep in a new zone split off beside `zoneId`. */
function keepBeside(address: string, page: string, zoneId: string, r: Rect | undefined) {
  const dir = canSplit(r, 'row') || !canSplit(r, 'col') ? 'row' : 'col'
  const t0 = treeOf(workspace.arr, page)
  if (!t0) return
  const made = { ...zone(t0, keepSlot([address])) }
  workspace.edit((x) => withTree(x, page, splitZone(treeOf(x, page)!, zoneId, dir, made).tree),
    `Kept ${titleFor(address)} in ${made.name ?? 'a new zone'}, beside ${zoneName(workspace.arr, page, zoneId)}: it keeps what you put there.`)
  land(made.id, address)
}

/** A zone's size on screen, for choosing which way a new zone splits off. */
function rectOf(page: string, zoneId: string): Rect | undefined {
  const cell = document.querySelector(`[data-page-tree="${CSS.escape(page)}"] [data-zone-id="${CSS.escape(zoneId)}"]`)
  if (!cell) return undefined
  const b = cell.getBoundingClientRect()
  return { x: 0, y: 0, w: b.width, h: b.height }
}

/** Keep on a page of its own (Open as page). */
export function keepOnNewPage(address: string) {
  const st = store.objects.get(address)
  const o = st && 'object' in st ? st.object : null
  const here = nav.snapshot().conversation
  nav.openAsPage(address, tabTitle(o ? titleOf(o) : 'Kept', [o ? store.posts.get(o.post)?.home_name : null, here ? store.conversations.get(here)?.name : null]))
}

/** The menu Keep opens: mounted once, by the workspace. */
export function KeepChooser() {
  const ask = useAsking()
  if (!ask) return null
  const { item } = ask
  const a = workspace.arr
  const page = item.page ?? nav.snapshot().page
  const t = treeOf(a, page)
  const here = t && item.zone ? findZone(t, item.zone) : undefined
  /* Kept from outside a zone (◆ on a post): the zones that keep what is put
     in them first, then those that follow what is read. */
  const others = t ? zones(t).filter((z) => z.id !== item.zone).sort((x, y) => Number(!!x.slot?.follow) - Number(!!y.slot?.follow)) : []
  const pages = a.pages.filter((p) => p.id !== page)
  const move = item.kept && item.zone ? { page, zone: item.zone } : undefined
  /* A new zone splits off beside this one, or, kept from a post, beside the page's last. */
  const besideZone = here ?? (t ? zones(t)[zones(t).length - 1] : undefined)
  const r = besideZone ? rectOf(page, besideZone.id) : undefined
  const pick = (fn: () => void) => () => { done(); fn() }
  const lit = (id: string) => (on: boolean) => hint(on ? id : null)
  return (
    <Sheet anchor={ask.anchor} onClose={done} label="keep">
      <Sec>Keep {titleFor(item.address)}</Sec>
      {here && !here.slot?.items.includes(item.address) && (
        <Opt onHover={lit(here.id)} onPick={pick(() => keepInZone(item.address, page, here.id, undefined, true))}>
          Here, in {here.name ?? 'this zone'}{here.slot?.follow ? ' (stays while you read on)' : ''}
        </Opt>
      )}
      {others.map((z) => (
        <Opt key={z.id} onHover={lit(z.id)} onPick={pick(() => keepInZone(item.address, page, z.id, move))}>
          {move ? 'Move to' : 'In'} {z.name ?? 'a zone'}{z.slot?.items.includes(item.address) ? ' (already there)' : !here && z.slot?.follow ? ' (stays while you read on)' : ''}
        </Opt>
      ))}
      {besideZone && (
        <Opt onHover={lit(besideZone.id)} onPick={pick(() => keepBeside(item.address, page, besideZone.id, r))}>
          In a new zone beside {besideZone.name ?? 'this one'}
        </Opt>
      )}
      {pages.length > 0 && <Sec>On a page</Sec>}
      {pages.map((p) => (
        <Opt key={p.id} onPick={pick(() => keepInZone(item.address, p.id, zones(p.tree)[0].id))}>On {p.title}</Opt>
      ))}
      {page !== 'this-post' && (
        <Opt onPick={pick(() => keepInZone(item.address, 'this-post', zones(a.tree)[0].id))}>On This post</Opt>
      )}
      <Opt onPick={pick(() => keepOnNewPage(item.address))}>On a new page</Opt>
    </Sheet>
  )
}

/** How Home keeps (Home.tsx registers it): these addresses into its zone. */
let homeKeeper: ((addresses: string[], zone: string, move?: { page: string; zone: string }) => void) | null = null
export function keepOnHome(fn: typeof homeKeeper) { homeKeeper = fn; return () => { if (homeKeeper === fn) homeKeeper = null } }

/* -- dragging a card onto a zone --------------------------------------------- */

export const carries = (e: React.DragEvent) => e.dataTransfer.types.includes(DRAG) || e.dataTransfer.types.includes(POST)

/** A post's own objects, in order: its words and what it carries, read
 *  once if not read yet. A block inside another comes with the block that
 *  draws it, as a zone shows it (hooks `shownOf`); one whose holder is not
 *  listed is kept on its own rather than lost. */
export async function objectsOfPost(post: string): Promise<string[]> {
  await store.loadObjects(post).catch(() => {})
  const read = (store.postObjects.get(post)?.addresses ?? []).flatMap((a) => {
    const st = store.objects.get(a)
    return st && 'object' in st ? [st.object] : []
  })
  return shownOf(read, 'everything').map((o) => o.address.live)
}

/** What a drag let go carries: one object (and where it was kept), or a post. */
export function dropped(e: React.DragEvent): { item: ObjectRef } | { post: string } | null {
  try {
    const got = JSON.parse(e.dataTransfer.getData(DRAG) || 'null') as ObjectRef | null
    if (got?.address) return { item: got }
  } catch { /* not a card */ }
  try {
    const p = JSON.parse(e.dataTransfer.getData(POST) || 'null') as { post?: string } | null
    if (p?.post) return { post: p.post }
  } catch { /* not a post */ }
  return null
}

/** A card let go over zone `zoneId` of `page`; a post, its objects. */
export function dropOn(e: React.DragEvent, page: string, zoneId: string) {
  const got = dropped(e)
  if (!got) return
  e.preventDefault()
  if ('post' in got) { void keepPostIn(got.post, page, zoneId); return }
  const from = got.item.kept && got.item.zone && got.item.page ? { page: got.item.page, zone: got.item.zone } : undefined
  keepInZone(got.item.address, page, zoneId, e.ctrlKey ? undefined : from)
}

/** A post dropped on a zone: what it is made of, kept there in one step. */
async function keepPostIn(post: string, page: string, zoneId: string) {
  const all = await objectsOfPost(post)
  const n = store.posts.get(post)?.number
  const what = n != null ? `#${n}` : 'the post'
  if (!all.length) { nav.toast({ text: `${what} has nothing to keep yet.` }); return }
  const t = treeOf(workspace.arr, page)
  const z = t && findZone(t, zoneId)
  if (!t || !z) return
  workspace.edit((x) => withTree(x, page, all.reduce((tr, a) => keepIn(tr, zoneId, a), treeOf(x, page)!)),
    `Kept ${what} in ${z.name ?? 'the zone'}: its words and what it carries.`)
  land(zoneId, all[0])
}
