/* The workspace's subscriptions: each card hears only what it shows (the
 * store's keys, as the shell's own hooks do), and the navigation state. */

import { useCallback, useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { store, type Id, type PostObjectEntry } from '../store'
import { feedOf, type Show, type Slot } from './tree'
import { KINDS, kindOf as isOf } from '../../experimental/objectkinds'
import { isBrainRef } from '../brain/address'

/* present/NeedsYou's ASK, spelled here: that module reads this one. */
const isAsk = (a: string) => a.startsWith('needs-you:')

function useKey<T>(key: string, read: () => T): T {
  const sub = useCallback((fn: () => void) => store.subscribe(key, fn), [key])
  return useSyncExternalStore(sub, read)
}
export const usePost = (id: Id) => useKey('post:' + id, () => store.posts.get(id))
export const useCollection = (key: string) => useKey('coll:' + key, () => store.collections.get(key))
export const usePostObjects = (root: Id) => useKey('objects:' + root, () => store.postObjects.get(root))
export const useThreadObjects = (root: Id) => useKey('tobjects:' + root, () => store.threadObjects.get(root))
export const useObject = (address: string) => useKey('obj:' + address, () => store.objects.get(address))
export const useKept = () => useKey('kept', () => store.kept)
export const useIsKept = (address: string) => useKey('keep:' + address, () => store.isKept(address))
export const useSelection = () => useKey('selection', () => store.selected)
export const useNav = () => useSyncExternalStore(nav.subscribe, nav.snapshot)

/** A card's title: the block's own, else what it is. */
export function titleOf(o: PostObjectEntry): string {
  if (o.title && o.title !== o.type) return o.title
  if (o.kind === 'post-text') return 'Post text'
  if (o.kind === 'media') return o.type === 'returned' ? 'Returned file' : 'Attachment'
  return o.type.charAt(0).toUpperCase() + o.type.slice(1)
}

/** The page title Open as page gives a tab: the demo truncates past 22.
 *  A title that begins with its conversation's name ("Local LLM Prelim:
 *  context sizes") loses that name first, which every tab would otherwise
 *  share, so tabs read apart (F6 final fix round). */
export function tabTitle(t: string, names: (string | null | undefined)[] = []): string {
  for (const name of names) {
    if (!name) continue
    const esc = name.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const rest = t.replace(new RegExp(`^\\s*${esc}\\s*[:\\-–—·|]\\s*`, 'i'), '')
    if (rest !== t && rest.trim()) { t = rest; break }
  }
  return t.length > 22 ? t.slice(0, 20) + '…' : t
}

/** Which objects a zone shows (the zone sheet's SHOW, #188), as the kind
 *  registry (experimental/objectkinds.ts) answers what each object is:
 *  everything, the post's own words too; its objects; its sections (blocks
 *  its author wrote); media (pictures, film, sound, video links); files;
 *  forms; what can be filled in (forms, checklists, tables with editable
 *  columns or rows to choose, pads); or only some kinds. */
export type { Show } from './tree'
export { KINDS }
/** The "Only some kinds" choice an object answers to. */
export const kindOf = (o: PostObjectEntry): string => isOf(o).filter
/** Does `show` take this object, on its own? Where it sits is `shownOf`'s. */
export function shows(o: PostObjectEntry, show: Show, kinds?: string[]): boolean {
  const is = isOf(o)
  if (show === 'everything') return true
  if (show === 'needs-you') return false
  if (show === 'media') return is.family === 'media'
  if (show === 'files') return is.family === 'file'
  if (show === 'sections') return is.family === 'section'
  if (show === 'forms') return is.filter === 'form'
  if (show === 'fillable') return !!is.fillable
  if (show === 'kinds') return !!kinds?.includes(is.filter)
  return is.family !== 'text'
}

/** What a zone held on a post shows (P10b), in words: a post and its
 *  replies, or -- held on a reply, which is read on its own -- that reply. */
export const heldOn = (number: number | null, reply: boolean, none = 'this post'): string =>
  `${number != null ? `#${number}` : none}${reply ? '' : ' and its replies'}`

/** What a zone shows of one post's objects, in order. A block inside
 *  another (a form in a panel) is drawn by the block holding it, so it is
 *  shown on its own only where no block holding it is drawn in the zone:
 *  a panel's form is there under Forms, and not twice under Its objects,
 *  nor beside the panel where the zone keeps that panel (`drawn`: the
 *  addresses the zone draws already, exact or live). */
export function shownOf(list: PostObjectEntry[], show: Show, kinds?: string[], drawn?: ReadonlySet<string>): PostObjectEntry[] {
  const byKey = new Map(list.map((o) => [o.key, o]))
  const took = new Map(list.map((o) => [o.key, shows(o, show, kinds)]))
  const taken = (o: PostObjectEntry) => !!took.get(o.key)
    || (!!drawn && (drawn.has(o.address.live) || drawn.has(o.address.exact)))
  const held = (o: PostObjectEntry): boolean => {
    const seen = new Set<string>()
    for (let p = o.parent; p !== null && !seen.has(p); ) {
      seen.add(p)
      const up = byKey.get(p)
      if (!up) return false
      if (taken(up)) return true
      p = up.parent
    }
    return false
  }
  return list.filter((o) => !!took.get(o.key) && !held(o))
}

/* -- a section: what was Placed, and what its feed brings in ---------------- */

/** What was PLACED in a section, by what draws it: objects (Present),
 *  requests (NeedsYou), 3D Brain entries (BrainKept). Every item, in order:
 *  Show narrows the feed, never what was placed. */
export function placedOf(items: string[]) {
  return {
    live: items.filter((a) => !isAsk(a) && !isBrainRef(a)),
    asks: items.filter(isAsk),
    brain: items.filter(isBrainRef),
  }
}

/** A section's two lanes, in the order they are drawn -- Placed first, then
 *  what the reading feed brings in, less what is placed already (it is drawn
 *  there once). Only the reading/post feed lists objects here: What needs you
 *  and a registry feed draw their own. */
export function sectionLanes(slot: Slot, listed: string[]): { placed: ReturnType<typeof placedOf>; feed: string[] } {
  const placed = placedOf(slot.items)
  const reads = slot.follow && !slot.feed && slot.show !== 'needs-you'
  const here = new Set(placed.live)
  return { placed, feed: reads ? listed.filter((a) => !here.has(a)) : [] }
}

/** Each Show in a caption's few words ("Notes · Following #12 · Media"). */
export const SHOW_WORD: Record<Show, string> = {
  objects: 'Objects', everything: 'Words and objects', sections: 'Blocks', media: 'Media', files: 'Files',
  forms: 'Forms', fillable: 'Things to fill in', kinds: 'Some kinds', 'needs-you': 'What needs you',
}
const kindNames = (kinds?: string[]) => (kinds ?? []).map((k) => KINDS.find((x) => x.id === k)?.name ?? k)
/** What a Show narrows to, in words: the kinds by name when it is some kinds. */
export const showWord = (show: Show, kinds?: string[]): string =>
  show === 'kinds' && kinds?.length ? kindNames(kinds).join(', ') : SHOW_WORD[show]

/** A registry source as a caption or menu names it. */
export interface FeedSource { show: string; name: string; scope?: 'home' | 'conversation' | 'anywhere' }

/** WHAT A SECTION'S CAPTION SAYS: what it actually holds -- the feed, what
 *  that is narrowed to, and how much was placed -- after its name. */
export function captionOf({ slot, number, root, source }: {
  slot: Slot
  /** the post it shows now, if it is numbered */
  number: number | null
  /** a post is being read (or held on) */
  root: boolean
  /** the registry source `slot.feed` names, when registered */
  source?: FeedSource
}): { words: string[]; placed: number } {
  const feed = feedOf(slot)
  const words: string[] = []
  if (feed === 'reading') words.push(number != null ? `Following #${number}` : root ? 'Following' : 'Follows the post you read')
  else if (feed === 'post') words.push(number != null ? `Stays on #${number}` : 'Stays on one post')
  else if (feed) words.push(source ? (source.scope === 'conversation' ? `${source.name} · this conversation` : source.name) : feed)
  if ((feed === 'reading' || feed === 'post') && slot.show !== 'objects') words.push(showWord(slot.show, slot.kinds))
  if (!feed && !slot.items.length) words.push('Holds what you place here')
  return { words, placed: slot.items.length }
}
export const captionText = (name: string, c: { words: string[]; placed: number }) =>
  [name, ...c.words, ...(c.placed ? [`Placed · ${c.placed}`] : [])].join(' · ')

/** What an empty reading feed says of the post it read: what it found
 *  nothing of, not that the section is empty (what was placed may fill it). */
export function nothingFrom(number: number | null, show: Show, kinds?: string[]): string {
  const n = number != null ? `#${number}` : 'This post'
  if (show === 'objects' || show === 'everything') return `${n} is text: it's in the conversation.`
  return `Nothing from ${n} matches ${showWord(show, kinds)}.`
}

/* -- the section menu's Brings in, as data ------------------------------------ */

/** The five a conversation section can bring in, in the order offered. */
const CONVERSATION_ORDER = ['actions', 'media', 'brief', 'followups', 'guidance']

export interface FeedChoice {
  /** what `withFeed` is given */
  to: string | null
  label: string
  /** the menu's own rows, This conversation ›, or More › */
  group: 'main' | 'conversation' | 'more'
  on: boolean
  /** offered but not choosable now, and why */
  off?: string
  says?: string
}

/** BRINGS IN: what a section may bring in besides what was placed in it --
 *  nothing, what is read, one post, this conversation's views, Home's
 *  collections -- and which it brings in now. */
export function feedChoices(slot: Slot, reading: { number: number | null; reply: boolean } | null, sources: readonly FeedSource[]): FeedChoice[] {
  const now = feedOf(slot)
  const rank = (s: FeedSource) => { const i = CONVERSATION_ORDER.indexOf(s.show); return i < 0 ? CONVERSATION_ORDER.length : i }
  const conv = sources.filter((s) => s.scope === 'conversation').sort((a, b) => rank(a) - rank(b))
  const more = sources.filter((s) => s.scope !== 'conversation')
  return [
    { to: null, label: 'Nothing', group: 'main', on: now === null, says: 'Only what is placed here' },
    { to: 'reading', label: "Follow what I'm reading", group: 'main', on: now === 'reading' },
    { to: 'post', label: `Stay on ${reading?.number != null ? `#${reading.number}` : 'this post'}`, group: 'main', on: now === 'post',
      off: !slot.pin && !reading ? 'Read a post first: this section stays on the post it shows' : undefined,
      says: reading ? `${heldOn(reading.number, reading.reply, 'This post')}, whatever you read next` : undefined },
    ...conv.map((s): FeedChoice => ({ to: s.show, label: s.name, group: 'conversation', on: now === s.show })),
    ...more.map((s): FeedChoice => ({ to: s.show, label: s.name, group: 'more', on: now === s.show })),
  ]
}
