/* The workspace's zones (Fluid completion, stream A). Every zone is one the
 * reader shapes (TreeView.tsx): it FOLLOWS what is read -- the post's objects
 * and its replies', narrowed by its Show filter -- or KEEPS what was put in
 * it, or both: a following zone shows what was kept in it first, and that
 * stays while other posts are read. The zone sheet (⋯) says which, and what
 * it shows (#188), how it presents it (Show as) and how it looks
 * (Appearance) -- both kept in the zone's slot, so saved arrangements and
 * named layouts carry them. What a zone holds is drawn through the one seam,
 * ../present (the A/C contract). SELECTION (F5) still splits off beside
 * This post while posts are selected.
 *
 * (F6's fixed mounts -- This post, the auto-created Kept column, the page
 * zone -- are gone: #448, no mandatory Kept column.) */

import { useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type HTMLAttributes, type ReactNode } from 'react'
import { Prose } from '../../prose'
import { turnPartScope } from '../../experimental/renderable'
import * as nav from '../nav'
import { liveRoot, repliesOf, store, type Id, type Post, type PostObjectEntry, type SelectionCollection } from '../store'
import { Actions } from '../conversation/PostCard'
import { AppearancePicker, Present, PresentPicker, readAppearance, useBox, zoneAppearanceStyle, DEFAULT_APPEARANCE, PRESENT_MODES, type Appearance, type ObjectRef } from '../present'
import { lookWords, ModeIcon } from '../present/Pickers'
import Grouped, { byKind, drawnGrouping, GROUPINGS, GroupSwitch, useGrouping, useSwitchRoom, type Grouping } from '../present/Grouped'
import { Glyph } from '../present/marks'
import { useScheme } from '../frame/look'
import { ASK, isAsk, NeedsYou } from '../present/NeedsYou'
import { isBrainRef } from '../brain/address'
import BrainKept from '../brain/BrainKept'
import { trace } from './from'
import { captionOf, captionText, feedChoices, heldOn, KINDS, nothingFrom, sectionLanes, shownOf, useCollection, useNav, usePost, useSelection, useThreadObjects, type FeedChoice, type FeedSource } from './hooks'
import * as registry from '../sections'
import type { Chrome, SectionBodyProps, SectionDef } from '../sections'
import { askKeep, carries, dropOn, keepInZone, useHinted, useKeeping, useLanded } from './keep'
import { flickOnDrop } from './flick'
import { handleObjectDrop } from '../focus/drag'
import { openObject } from './open'
import { treeOf, useArr, withTree, workspace } from './place'
import { Opt, Sec, Sheet } from '../frame/Sheet'
import { ZoneTools, type ZoneCtl } from './TreeView'
import { SearchButton, useFocusSearch } from '../search-in/FocusSearch'
import { anyIn, type Matcher } from '../search-in/match'
import { feedOf, unkeep, updateZone, withFeed, zones, type Rect, type Show, type Slot, type Zone } from './tree'
import { useWorkingOn } from './working'
import { Who } from '../identity/Who'
import { SectionSpin, useSectionLoad } from '../../loading'

const at = (name: string) => '@' + name.replace(/^@/, '')
const REFERENCE = new Set(['turn', 'topic', 'conversation', 'acquired'])
const wordsOf = (post: Post) =>
  post.parts.filter((p) => p.type === 'text' || REFERENCE.has(p.type)).map((p) => p.text ?? '').join('')

/* -- the selection zone's visibility: presentation, this page only -------- */

/* The Selection zone is there WHILE SELECTING (opr-005ddf2f48f8): Done
   closes it, and it never follows into another conversation. A selection
   held after Done comes back where the reader asks for it (Arrange › Show
   the selection), in that place only; selecting again brings it back too. */
let shownIn: string | null = null
let closed = false
const hidden = new Set<() => void>()
const emitShown = () => hidden.forEach((fn) => fn())
/** Is the held selection shown here, outside selecting? */
export const selectionShown = () => !closed && shownIn !== null && shownIn === nav.snapshot().conversation
export function showSelection(on: boolean) {
  shownIn = on ? nav.snapshot().conversation : null
  closed = !on
  emitShown()
}
const shownWord = () => (closed ? 'closed' : selectionShown() ? 'here' : 'held')
/** 'here': shown in this place; 'held': not, unless selecting; 'closed': not even then. */
export const useSelectionShown = () => useSyncExternalStore((fn) => {
  hidden.add(fn)
  const off = nav.subscribe(fn)
  return () => { hidden.delete(fn); off() }
}, shownWord)

/* -- what a following zone shows -------------------------------------------- */

/** One post's objects as read so far, in its order. */
const readOf = (id: Id): PostObjectEntry[] => (store.postObjects.get(id)?.addresses ?? []).flatMap((a) => {
  const st = store.objects.get(a)
  return st && 'object' in st ? [st.object] : []
})

/** What a zone shows of one post's listing, by address, in order: an
 *  address not read yet stays (it is drawn as it resolves). `drawn` is what
 *  the zone keeps: a block inside one of those is drawn there already. */
function shownAddresses(id: Id, show: Show, kinds?: string[], drawn?: ReadonlySet<string>): string[] {
  const shown = new Set(shownOf(readOf(id), show, kinds, drawn).map((o) => o.address.live))
  return (store.postObjects.get(id)?.addresses ?? []).filter((a) => {
    const st = store.objects.get(a)
    return !st || !('object' in st) || shown.has(a)
  })
}

/** Every object address of these posts the zone shows, in order: one
 *  subscription over each post's listing. `null` until all are read. */
function useAddresses(ids: Id[], show: Show, kinds?: string[], kept?: string[]): string[] | null {
  const key = ids.join(',')
  const kk = (kinds ?? []).join(',')
  const held = (kept ?? []).join('\n')
  const sub = useCallback((fn: () => void) => {
    const offs = key ? key.split(',').map((id) => store.subscribe('objects:' + id, fn)) : []
    return () => offs.forEach((off) => off())
  }, [key])
  const read = () => {
    if (!key) return ''
    const list = key.split(',')
    if (!list.every((id) => store.postObjects.has(id))) return '\u0000'
    const ks = kk ? kk.split(',') : []
    const drawn = new Set(held ? held.split('\n') : [])
    return list.flatMap((id) => shownAddresses(id, show, ks, drawn)).join('\n')
  }
  const got = useSyncExternalStore(sub, read)
  return useMemo(() => (got === '\u0000' ? null : got ? got.split('\n') : []), [got])
}

/** What is read -- or the post the zone is held on (`pin`) -- its thread's
 *  objects and how reading them went. */
function useFollowed(show: Show, kinds: string[] | undefined, on: boolean, pin?: Id, kept?: string[]) {
  const n = useNav()
  const root = on ? pin ?? n.reading : null
  const post = usePost(root ?? '')
  const known = !!post
  const isReply = !!post?.reply_to
  /* A reply remains one highlighted row in its whole thread.  Reading it no
     longer collapses every following section to that reply alone. */
  let threadRoot = post
  for (let up = store.posts.get(threadRoot?.reply_to ?? ''); up; up = store.posts.get(up.reply_to ?? '')) threadRoot = up
  const followedRoot = threadRoot?.id ?? root
  /* A READ THAT FAILS SAYS SO, with Retry (F6 final fix round). */
  const [failed, setFailed] = useState<{ root: Id; why: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!root) return
    let live = true
    const fail = (e: unknown) => { if (live) setFailed({ root, why: String((e as Error)?.message ?? e) }) }
    /* The objects of the post's whole thread come with it, each captioned
       with the reply it is from, in ONE request (F6). A reply read on its
       own shows its own. */
    if (!known) {
      if (!store.posts.has(root)) store.loadPosts([root]).then(() => { if (live && !store.posts.has(root)) fail('the post could not be read') }, fail)
    } else {
      store.loadThreadObjects(followedRoot!).then(() => { if (live) setFailed(null) }, fail)
    }
    return () => { live = false }
  }, [root, followedRoot, known, attempt])
  const tob = useThreadObjects(followedRoot ?? '')
  const ids = useMemo(() => (!root || !known ? [] : tob ? tob.posts : []), [root, known, tob])
  const waiting = known && !tob
  const listed = useAddresses(ids, show, kinds, kept)
  return {
    n, root, post, isReply, waiting, ids,
    /* the thread's older replies its read left out (THREAD_MAX) */
    omitted: tob ? tob.omitted : 0,
    addresses: waiting ? null : listed,
    failed: failed && failed.root === root ? failed.why : null,
    retry: () => { setFailed(null); setAttempt((a) => a + 1) },
  }
}

/** The read post's words as the first card (rail, or a reply). Its
 *  blocks are cards of their own just after it, so they are not drawn twice.
 *  C3: it says why it is here -- it is not one of the Show choices, but the
 *  words the conversation has no room to show -- and Everything, which
 *  shows the words itself, does not get them twice. */
function Words({ post, why }: { post: Post; why: string }) {
  const text = wordsOf(post).replace(/^(`{3,})[^\n]*\n[\s\S]*?^\1[ \t]*$/gm, '').replace(/\n{3,}/g, '\n\n')
  return (
    <div className="wk-obj wk-prose" data-joined={post.id} title={why}>
      <span className="wk-wordswhy">{why}</span>
      <h4><Who id={post.author} name={post.author_name} show="line" size={18} live meta={post.number != null ? `#${post.number}` : null} /></h4>
      {text.trim() ? <div className="turn-body"><Prose src={text} scope={turnPartScope(post.id, 0)} /></div> : <p className="wk-quiet">No words.</p>}
    </div>
  )
}

/* -- the zone sheet (⋯) ------------------------------------------------------ */

/** Would "Its blocks" (`sections`) show anything other than "Its objects" for these
 *  posts? Sections (marked blocks) are some of its objects; where they are
 *  all of them, the choice changes nothing and is not offered (#568 3.4).
 *  What a section IS stays as it is: that is the owner's (D2). */
function sectionsDiffer(ids: Id[]): boolean {
  let objects = 0, sections = 0
  for (const id of ids) {
    const read = readOf(id)
    objects += shownOf(read, 'objects').length
    sections += shownOf(read, 'sections').length
  }
  return objects !== sections
}

/* WHAT EACH SHOW CHOICE SHOWS, IN A LINE (C3, as the Lab's FOLLOWS says it).
   The stored keys are unchanged; only the words are. "Everything, with the
   words" said what it added, not what it was: it is the post's own words
   and then its objects. The difference between the three that overlap:
   OBJECTS is everything in the post that is not its running text; SECTIONS
   is only the blocks its author wrote; the WORDS are its running text.
   What a section is stays the owner's open question (D2): the line says
   what it is today. */
export const SHOW_ROWS: { show: Show; label: string; says: string; glyph: string }[] = [
  { show: 'objects', label: 'Its objects', glyph: 'objects',
    says: 'The tables, charts, pictures, files and links in it and in its replies; not its running text' },
  { show: 'everything', label: 'Its words and objects', glyph: 'everything',
    says: 'Its running text first, then every object in it' },
  /* "Its blocks": a Fluid section is now the thing on the page, so the
     stored word `sections` is shown by another name. */
  { show: 'sections', label: 'Its blocks', glyph: 'section',
    says: 'Only the blocks its author wrote (tables, charts, checklists\u2026); no pictures, files or links' },
  { show: 'media', label: 'Media', glyph: 'media', says: 'Pictures, video and sound, YouTube links too' },
  { show: 'files', label: 'Files', glyph: 'file', says: 'Attached and returned files: documents, data, code, PDFs' },
  { show: 'forms', label: 'Forms', glyph: 'form', says: 'Its forms, those inside a panel too' },
  { show: 'fillable', label: 'Things to fill in', glyph: 'fillable',
    says: 'Forms, checklists, tables with columns to edit or rows to choose, and pads' },
  { show: 'kinds', label: 'Only some kinds\u2026', glyph: 'kinds', says: 'Just the kinds you pick below' },
  { show: 'needs-you', label: 'What needs you', glyph: 'needs-you', says: 'Decisions and inputs on it waiting for you; with nothing read, everything waiting' },
]
const SHOW_ROW = (s: Show) => SHOW_ROWS.find((r) => r.show === s) ?? SHOW_ROWS[0]

/* What a conversation section may bring in (sections/registry `sources`):
   every source with a body of its own -- not the conversation, which Home
   docks, nor Kept, which is what Placed now is. */
export const feedSources = (): readonly SectionDef[] =>
  registry.sources('conversation').filter((d) => !!d.body && !d.conversation && !d.kept)

/** A row that opens what is under it, in the sheet itself: the frame's
 *  sheets have no submenus. `value` says what is chosen there now. */
function Disclose({ open, on, onToggle, value, children }: { open: boolean; on?: boolean; onToggle: () => void; value?: string; children: ReactNode }) {
  return (
    <button className={'wk-opt wk-disclose' + (on ? ' on' : '') + (open ? ' open' : '')} role="menuitem" aria-expanded={open} onClick={onToggle}>
      <span className="wk-tick" aria-hidden="true">{on ? '✓' : ''}</span>
      <span>{children}{value && <small className="wk-says">{value}</small>}</span>
      <span className="wk-chev" aria-hidden="true">{'›'}</span>
    </button>
  )
}

function ZoneSheet({ z, slot, page, ctl, setSlot, close, placeLook, ids, groupable, groupWord, reading, sources, tidy, useLookForPlace, search }: {
  z: Zone; slot: Slot; page: string; ctl: ZoneCtl; setSlot: (f: (s: Slot) => Slot, words?: string) => void; close: () => void
  /** the post it shows now and its number: what Stay on holds it on */
  reading: { id: Id; number: number | null; reply: boolean } | null
  /** the place's default look, which this zone shows unless it has its own */
  placeLook: Appearance
  /** the posts it follows now */
  ids: Id[]
  /** what it brings in is grouped by post: Look offers the grouping */
  groupable?: boolean
  /** the grouping it is drawn in now, in words */
  groupWord?: string
  /** the registry feeds it may bring in */
  sources: readonly FeedSource[]
  /** A floated zone's one menu also owns the action for all floating places. */
  tidy?: () => void
  useLookForPlace?: (look: Appearance) => void
  search?: () => void
}) {
  const name = z.name ?? 'This section'
  const rows = SHOW_ROWS.filter(({ show: s }) => s !== 'sections' || slot.show === 'sections' || sectionsDiffer(ids))
  const feed = feedOf(slot)
  const choices = feedChoices(slot, reading, sources)
  const inGroup = (g: FeedChoice['group']) => choices.filter((c) => c.group === g)
  const [opened, setOpened] = useState<'conversation' | 'more' | 'look' | null>(choices.find((c) => c.on && c.group !== 'main')?.group as 'conversation' | 'more' | undefined ?? null)
  const toggle = (k: 'conversation' | 'more' | 'look') => setOpened((o) => (o === k ? null : k))
  const placed = slot.items.length
  /* CHOOSING WHAT IT BRINGS IN never touches what was placed (withFeed). */
  const bring = (c: FeedChoice) => {
    if (c.on || c.off) { close(); return }
    const words = c.to === null
      ? `${name} holds only what is placed here${placed ? ` (${placed})` : ': drag an object onto it, or ◆ keep one and choose it'}.`
      : c.to === 'reading' ? `${name} follows what you read${placed ? ', below what is placed in it' : ''}.`
      : c.to === 'post' ? `${name} stays on ${heldOn(reading?.number ?? null, !!reading?.reply)}.`
      : `${name} brings in ${c.label}${c.group === 'conversation' ? ' from this conversation' : ''}.`
    setSlot((s) => withFeed(s, c.to, reading?.id), words)
    close()
  }
  const opt = (c: FeedChoice) => (
    <Opt key={c.to ?? 'nothing'} on={c.on} off={!!c.off} why={c.off} says={c.says} onPick={() => bring(c)}>{c.label}</Opt>
  )
  const group = (g: 'conversation' | 'more', label: string) => {
    const list = inGroup(g)
    if (!list.length) return null
    const chosen = list.find((c) => c.on)
    return (
      <>
        <Disclose open={opened === g} on={!!chosen} value={chosen?.label} onToggle={() => toggle(g)}>{label}</Disclose>
        {opened === g && <div className="wk-subopts" role="group" aria-label={label}>{list.map(opt)}</div>}
      </>
    )
  }
  /* Show as is offered only where it changes something: What needs you
     draws its own cards, and a registry feed lays out its own. */
  const presents = ((!!feed && !slot.feed && slot.show !== 'needs-you') || slot.items.some((a) => !isAsk(a)))
  const lookNow = [presents ? PRESENT_MODES.find((p) => p.mode === slot.present)?.label : null, groupable ? groupWord : null,
    lookWords(readAppearance(slot.appearance, placeLook))].filter(Boolean).join(' · ')
  return (
    <>
      <Sec>{name}</Sec>
      {search && <Opt onPick={() => { close(); search() }}>Search in {name}&hellip;</Opt>}
      {/* BRINGS IN: what it shows besides what was placed in it. Stay on
          (P10b) holds it on one post and its replies -- a reply, only
          itself -- whatever is read next, until it is told to follow again. */}
      <Sec>Brings in</Sec>
      {inGroup('main').map(opt)}
      {group('conversation', 'This conversation')}
      {group('more', 'More')}
      {(feed === 'reading' || feed === 'post') && (
        <>
          <Sec>Narrow to</Sec>
          <p className="wk-note">What it brings in; what is placed here is always shown</p>
          {rows.map(({ show: s, label, says }) => (
            <Opt key={s} on={slot.show === s} says={says} onPick={() => setSlot((x) => ({ ...x, show: s, ...(s === 'kinds' && !x.kinds?.length ? { kinds: ['table', 'chart'] } : {}) }))}>{label}</Opt>
          ))}
          {slot.show === 'kinds' && (
            <div className="wk-kinds" role="group" aria-label="kinds this zone shows">
              {KINDS.map((k) => {
                const on = !!slot.kinds?.includes(k.id)
                return (
                  <button key={k.id} className={'wk-kind' + (on ? ' on' : '')} aria-pressed={on} data-kind={k.id}
                    onClick={() => setSlot((x) => {
                      const now = x.kinds ?? []
                      const next = on ? now.filter((y) => y !== k.id) : [...now, k.id]
                      return { ...x, kinds: next.length ? next : undefined, show: next.length ? 'kinds' : 'objects' }
                    })}>{k.name}</button>
                )
              })}
            </div>
          )}
        </>
      )}
      {/* LOOK: one row saying how it looks now, opening the detail. */}
      <Sec>Look</Sec>
      <Disclose open={opened === 'look'} value={lookNow} onToggle={() => toggle('look')}>How it looks</Disclose>
      {opened === 'look' && (
        <div className="wk-subopts wk-look" role="group" aria-label="Look">
          {presents && <PresentPicker mode={slot.present} onMode={(m) => setSlot((x) => ({ ...x, present: m }))} />}
          {groupable && (
            <div className="pz-gswitchsheet">
              <Sec>Group</Sec>
              <GroupSwitch zone={z.id} name={z.name ?? 'Zone'} mode={slot.present} />
            </div>
          )}
          <AppearancePicker value={readAppearance(slot.appearance, placeLook)}
            onChange={(a) => setSlot((x) => ({ ...x, appearance: a }))}
            onReset={() => setSlot((x) => ({ ...x, appearance: undefined }), `${name} takes this place's look again.`)}
            isDefault={!slot.appearance} resetLabel={["Back to this place's look", "This place's look"]} />
          {slot.appearance && (
            <Opt onPick={() => {
              /* One step: the place takes this look, and this zone stops overriding it. */
              const look = readAppearance(slot.appearance, placeLook)
              if (useLookForPlace) useLookForPlace(look)
              else workspace.edit((a) => ({ ...withTree(a, page, updateZone(treeOf(a, page)!, z.id, (x) => ({ ...x, slot: { ...(x.slot ?? slot), appearance: undefined } }))), appearance: look }),
                `Every section here without a look of its own now looks like ${name}.`)
              close()
            }} title="Make this the place's default look: every section without its own takes it">Use this look for every section here</Opt>
          )}
        </div>
      )}
      <Sec>Arrange</Sec>
      {tidy && <Opt onPick={() => { close(); tidy() }}>Tidy floating windows</Opt>}
      {ctl.focus && <Opt onPick={() => { close(); ctl.focus?.() }}>Make primary</Opt>}
      {ctl.float && <Opt onPick={() => { close(); ctl.float?.() }}>Float this section</Opt>}
      <Opt on={ctl.fit} onPick={() => { close(); ctl.toggleFit() }}>{ctl.fit ? 'Take its share again' : 'Fit to content'}</Opt>
      <Opt off={!ctl.canSplitRow} why={ctl.whyNoSplitRow} onPick={() => { close(); ctl.split('row') }}>Split side by side</Opt>
      <Opt off={!ctl.canSplitCol} why={ctl.whyNoSplitCol} onPick={() => { close(); ctl.split('col') }}>Split top and bottom</Opt>
      <Opt off={!ctl.canMerge} onPick={() => { close(); ctl.merge() }}>Merge with the zone beside it</Opt>
      <Opt off={!ctl.canClose} onPick={() => { close(); ctl.close() }}>Close this zone</Opt>
      {slot.items.length > 0 && (
        <Opt onPick={() => { close(); setSlot((s) => ({ ...s, items: [] }), `Nothing is placed in ${name} now.`) }}>Remove what is placed here ({slot.items.length})</Opt>
      )}
      {page !== 'this-post' && (
        <>
          <Sec>This page</Sec>
          <Opt onPick={() => { close(); nav.closePage(page) }}>Close this page</Opt>
        </>
      )}
    </>
  )
}

/* -- what a zone shows, on hover (C4) ----------------------------------------- */

/* A ZONE SAYS WHAT IT SHOWS WHEN IT IS LOOKED AT (C4): beside its menu,
   while the zone is pointed at or has focus, two or three quiet drawings --
   what it shows (or that it keeps), which kinds, and how it lays them out --
   in the text's own colour. The words are in its title and its accessible
   name; pressing it opens the zone's sheet, where each can be changed. */
function ZoneHint({ slot, reply, caption, onOpen }: { slot: Slot; reply: boolean; caption: string; onOpen: (el: HTMLElement) => void }) {
  const row = SHOW_ROW(slot.show)
  const kinds = slot.show === 'kinds' ? (slot.kinds ?? []).map((k) => KINDS.find((x) => x.id === k)?.name ?? k) : []
  const mode = PRESENT_MODES.find((p) => p.mode === slot.present)
  const feed = feedOf(slot)
  const reads = feed === 'reading' || feed === 'post'
  /* It says what it holds (the caption's words), then how a reading feed
     is narrowed, and how it is laid out where that is its own. */
  const narrowed = reads
    ? ` ${slot.pin ? (reply ? 'Stays on one reply. ' : 'Stays on one post and its replies. ') : ''}Brings in ${row.label.toLowerCase()}${kinds.length ? ` (${kinds.join(', ')})` : ''}: ${row.says.charAt(0).toLowerCase() + row.says.slice(1)}${slot.items.length ? ', below what is placed' : ''}.`
    : ''
  const laid = mode && (reads ? slot.show !== 'needs-you' : slot.items.some((a) => !isAsk(a)))
  const said = `${caption}.${narrowed}${laid ? ` Shown as ${mode.label.toLowerCase()}.` : ''}`
  return (
    <button className="wk-zhint" data-show={reads ? slot.show : feed ?? 'kept'} title={said} aria-label={said}
      onClick={(e) => onOpen(e.currentTarget)}>
      <Glyph name={reads ? row.glyph : feed ?? 'kept'} />
      {reads && kinds.length > 0 && <span className="wk-zhintn" aria-hidden="true">{kinds.length}</span>}
      {laid && <ModeIcon mode={mode.mode} />}
    </button>
  )
}

/* FOCUS SEARCH IN ONE-AT-A-TIME LAYOUTS (search-in/): Slides and Focused item
   draw one object, so the bar counts what is drawn and says how many of the
   others may also match -- read from what the store holds of them (title,
   name, kind, source), as nothing of theirs is on screen. Present keeps its
   current item to itself, so the bar cannot step to them; ‹ › can. */
function undrawnMatches(body: { current: HTMLElement | null }, items: ObjectRef[], mode: string) {
  if (mode !== 'slides' && mode !== 'focus') return undefined
  return (m: Matcher): string | null => {
    const el = body.current
    if (!el) return null
    const n = items.filter((it) => {
      if (el.querySelector(`.wk-obj[data-address="${CSS.escape(it.address)}"]`)) return false
      const st = store.objects.get(it.address)
      const o = st && 'object' in st ? st.object : null
      return !!o && anyIn([o.title, o.name, o.type, o.block?.body, o.link?.label, o.link?.url], m)
    }).length
    if (!n) return null
    const what = mode === 'slides' ? (n === 1 ? 'slide' : 'slides') : (n === 1 ? 'item' : 'items')
    return `${n} other ${what} may match`
  }
}

/* -- a registry feed in a section --------------------------------------------- */

/* The section draws its own caption, so a feed's chrome is only its body --
   with the feed's own filters (Work's states, the Briefing's period) and
   tools above it, where it has them, as they would be lost otherwise. */
const inSection: Chrome = ({ filters, tools, children }) => (
  <>{(filters || tools) && <div className="wk-feedbar">{filters}{tools}</div>}{children}</>
)

/** A REGISTRY FEED in a workspace section: the section's body, as Home and
 *  the About slide-out draw it, reading the conversation of the place the
 *  section is in. Its options are kept in the slot's feed. */
function FeedBody({ z, feed, source, setSlot }: {
  z: Zone; feed: NonNullable<Slot['feed']>; source: SectionDef | undefined
  setSlot: (f: (s: Slot) => Slot, words?: string) => void
}) {
  const n = useNav()
  if (!source?.body) return <p className="wk-quietline">Nothing called &ldquo;{feed.source}&rdquo; can be brought in here.</p>
  const options = feed.options ?? {}
  /* `conversation` and `inSection` are the contract's (sections/registry.ts). */
  const contract: Partial<SectionBodyProps> = { conversation: n.conversation ?? null, inSection: true }
  return (
    <div className="wk-feed" data-feed={feed.source}>
      <source.body z={{ ...z, show: source.show, options }} options={registry.sectionOptions(source, options)}
        setOption={(key, value) => setSlot((s) => (s.feed ? { ...s, feed: { ...s.feed, options: { ...s.feed.options, [key]: value } } } : s))}
        setSlot={setSlot} onOpenPost={(c, p) => nav.read(c, p, null)} chrome={inSection} {...contract} />
    </div>
  )
}

/* -- one zone ---------------------------------------------------------------- */

export interface FloatingZoneHead {
  from?: ReactNode
  beforeMenu?: ReactNode
  afterMenu?: ReactNode
  tidy?: () => void
  props?: HTMLAttributes<HTMLDivElement>
  /** A float is outside the page tree, so its slot is edited in that place. */
  setSlot?: (fn: (slot: Slot) => Slot, words?: string) => void
  useLookForPlace?: (look: Appearance) => void
}

export function WorkspaceZone({ z, r, ctl, page, first, floating }: { z: Zone; r: Rect; ctl: ZoneCtl; page: string; first: boolean; floating?: FloatingZoneHead }) {
  const slot: Slot = z.slot ?? { follow: true, show: 'objects', items: [], present: 'cards' }
  /* WHAT WAS PLACED HERE is drawn first, in its own lane, whatever the feed
     and its Show; a block inside one of those is drawn by it, so it is not
     brought in again as a card of its own. */
  const kept = useMemo(() => slot.items.filter((a) => !isAsk(a) && !isBrainRef(a)), [slot.items])
  const feed = feedOf(slot)
  /* A registry feed (Actions, Media, Work...) is that section's own body. */
  const source = slot.feed ? registry.sectionOf(slot.feed.source) : undefined
  /* What was brought in from the 3D Brain is kept by reference and drawn by
     the Brain's own card (brain/BrainKept.tsx), as requests are by NeedsYou. */
  const fromBrain = slot.items.filter(isBrainRef)
  const f = useFollowed(slot.show, slot.kinds, slot.follow, slot.pin ?? undefined, kept)
  const { n, root, post, isReply } = f
  const [menuAt, setMenuAt] = useState<HTMLElement | null>(null)
  const close = useCallback(() => setMenuAt(null), [])
  const [over, setOver] = useState(false)
  /* The body's own size, which is what Present lays out in; and the look
     the slot stores (the default until the reader chooses one). */
  const zbody = useRef<HTMLDivElement | null>(null)
  const box = useBox(zbody)
  const scheme = useScheme()
  /* The place's default look (#188), which this zone shows unless it has its own. */
  const placeLook = readAppearance(useArr().appearance, DEFAULT_APPEARANCE)
  const appearance = readAppearance(slot.appearance, placeLook)
  const look = zoneAppearanceStyle(appearance, scheme)
  const setSlot = (fn: (s: Slot) => Slot, words?: string) => floating?.setSlot
    ? floating.setSlot(fn, words)
    : workspace.edit((a) => withTree(a, page, updateZone(treeOf(a, page)!, z.id, (x) => ({ ...x, slot: fn(x.slot ?? slot) }))), words)
  /* "now #N" for 1.4s after every change of what is read. */
  const [now, setNow] = useState(false)
  const was = useRef<Id | null>(null)
  useEffect(() => {
    const prev = was.current
    was.current = root
    if (!prev || !root || !slot.follow) return
    setNow(true)
    const t = setTimeout(() => setNow(false), 1400)
    return () => clearTimeout(t)
  }, [root, slot.follow])
  /* WHAT NEEDS YOU (#576): requests kept here, and -- shown -- what on the
     post read needs the owner, drawn by present/NeedsYou rather than Present. */
  const needs = slot.show === 'needs-you'
  const asks = slot.items.filter(isAsk).map((a) => a.slice(ASK.length))
  /* A request another zone on this page keeps is shown there, not twice. */
  const pageTree = treeOf(useArr(), page)
  const elsewhere = pageTree
    ? zones(pageTree).filter((x) => x.id !== z.id).flatMap((x) => x.slot?.items ?? []).filter(isAsk).map((a) => a.slice(ASK.length))
    : []
  const followed = sectionLanes(slot, f.addresses ?? []).feed
  const placedItems: ObjectRef[] = kept.map((address) => ({ address, kept: true, zone: z.id, page }))
  const fedItems: ObjectRef[] = followed.map((address) => ({ address, zone: z.id, page }))
  const items: ObjectRef[] = [...placedItems, ...fedItems]
  /* GROUPED BY POST (adm-f3a36808b64f): what a following zone shows of a
     thread -- every Show but What needs you, which draws its own cards --
     is a row per post by reply, the words first by kind, or as it was. */
  /* By reply draws each row in the zone's layout; where the layout fills the
     zone with one object (Slides, Focused item) it is drawn as now. */
  const grouping = drawnGrouping(useGrouping(z.id), slot.present)
  const groupable = slot.follow && !needs
  const byReply = groupable && grouping === 'reply'
  const fedShown = groupable && grouping === 'kind' ? byKind(fedItems) : fedItems
  const shownItems = [...placedItems, ...fedShown]
  /* Slides and Focused item fill the section with one object: what was
     placed and what the post read brings in stay one run, placed first, so
     ‹ › steps from one to the other. Elsewhere each lane lays out its own. */
  const oneRun = (slot.present === 'slides' || slot.present === 'focus') && !slot.feed && !byReply
  const hasFeed = !!feed
  const onOpen = (it: ObjectRef, from?: HTMLElement | null) => openObject(it.address, from ?? null)
  const onKeep = (it: ObjectRef, from?: HTMLElement | null) => askKeep(it, from)
  const onRemove = (it: ObjectRef) => workspace.edit((a) => withTree(a, page, unkeep(treeOf(a, page)!, z.id, it.address)), `${name} no longer keeps it.`)
  /* A zone held on a post (P10b) names that post, never the one read. */
  const number = post?.number ?? (slot.pin ? null : n.readingNumber)
  /* Only the rail cannot show the post read: a narrow column draws it in
     full, so copying it here too drew it three times with an object aside
     (opr-895b6c5c8041). */
  /* The rail's words are the READ post's (P10b): a zone held on another post
     carries them only where every following zone is held (Workspace.tsx),
     and says whose they are. */
  const read = usePost(n.reading ?? '')
  const elsewhereRead = !!slot.pin && !!read && read.id !== root
  const railWords = slot.follow && !needs && first && n.width === 'rail' && read
    && (elsewhereRead || slot.show !== 'everything') ? read : null
  const ownWords = slot.follow && !needs && slot.show !== 'everything' && post && isReply && post.id !== railWords?.id ? post : null
  const joins = !!(railWords || ownWords)
  const railWhy = elsewhereRead
    ? `The post you are reading${read?.number != null ? `, #${read.number}` : ''}, while the conversation is too narrow to show it`
    : 'Its words, while the conversation is too narrow to show them'
  const wordsWhy = isReply ? 'The words of this reply' : railWhy
  const name = z.name ?? 'Zone'
  const held = store.postObjects.get(root ?? '')
  /* THE CAPTION SAYS WHAT IT HOLDS: what it brings in, narrowed to what,
     and how much was placed ("Notes · Following #12 · Media · Placed · 2"). */
  const said = captionOf({ slot, number: number ?? null, root: !!root, source, name })
  const caption = <>{name}{said.words.map((w) => <span key={w}> &middot; {w}</span>)}
    {said.placed ? <> &middot; <span className="wk-keptmark" aria-hidden="true">{'◆'}</span>Placed &middot; {said.placed}</> : null}</>
  const replyCount = post ? repliesOf(post) : 0
  /* While an object is being kept, a zone that keeps what is put in it shows
     itself as a place for it; the one a Keep choice names is lit (#568 3.3). */
  const keeping = useKeeping()
  const hinted = useHinted() === z.id
  const landed = useLanded(z.id)
  useEffect(() => {
    if (!landed) return
    /* It arrived: show where (#568 3.1: keeping, then locating). */
    const t = setTimeout(() => {
      const el = zbody.current?.querySelector(`[data-address="${CSS.escape(landed.address)}"]`) as HTMLElement | null
      if (!el) return
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      el.classList.add('wk-born')
      setTimeout(() => el.classList.remove('wk-born'), 700)
    }, 80)
    return () => clearTimeout(t)
  }, [landed])
  /* An agent working on a post this zone shows: its content may change (#568 4.6). */
  const watched = useMemo(() => [...new Set([...(slot.follow ? f.ids : []), ...kept.map((a) => liveRoot(a)).filter((x): x is Id => !!x)])], [slot.follow, f.ids, kept])
  const workers = useWorkingOn(watched)
  /* WHAT THIS ZONE IS READING, said to the page's loader (package B): a
     following zone is loading until the post read and its objects are in
     hand, and failed when that read failed (with its Retry). */
  const loads = slot.follow && !needs && !!root
  const loadId = loads ?`fluid:zone:${page}:${z.id}` : null
  const listedNow = post && f.addresses ? f.addresses : null
  const zoneLoad = useSectionLoad(loadId, name, { loading: !f.failed && !listedNow, error: f.failed, data: listedNow, retry: f.retry })
  const cap = useRef<HTMLDivElement | null>(null)
  const room = useSwitchRoom(cap, `${name}|${number}|${root}|${slot.items.length}|${workers.length}`, true)
  const isNarrow = room !== 'full' || (r.w > 0 && r.w < 380)
  /* FOCUS SEARCH (search-in/): find within what this zone shows; the bar
     opens under its caption and searches the zone body. */
  const search = useFocusSearch(() => zbody.current, undefined, z.id, undrawnMatches(zbody, shownItems, slot.present))
  return (
    <section className={'wk-zone wk-panel ' + look.className + (slot.follow ? ' wk-follow' : ' wk-keep') + (over || hinted ? ' wk-drop' : '')
      + (keeping && !slot.follow ? ' wk-target' : '') + (ctl.closing ? ' wk-closing' : '')}
      style={look.style} data-look={slot.appearance ? 'own' : 'place'} data-working={workers.length ? '' : undefined}
      data-zone={slot.follow ? 'following' : 'kept'} data-zone-name={name} aria-label={`${name} zone`}
      data-present={slot.present} data-feed={slot.feed?.source} aria-busy={zoneLoad === 'loading' || undefined}
      onDragOver={(e) => { if (!carries(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = e.ctrlKey ? 'copy' : 'move'; if (!over) setOver(true) }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false) }}
      onDrop={(e) => { setOver(false); if (handleObjectDrop(e, z.id)) return; if (flickOnDrop(e, z.id)) { e.preventDefault(); return } dropOn(e, page, z.id) }}>
      <div className={'wk-zcap' + (floating ? ' fl-head' : '')} ref={cap} {...floating?.props}>
        <span className={floating ? 'wk-what zc-name' : 'wk-what'}>{floating ? name : caption}</span>
        {floating?.from}
        {!floating && <>
        <SectionSpin id={loadId} label={name} />
        <ZoneHint slot={slot} reply={isReply} caption={captionText(name, said)} onOpen={setMenuAt} />
        {workers.length > 0 && (
          <span className="wk-working" role="status"
            title={workers.map((w) => `${at(w.alias)} is working on #${w.number ?? '?'}`).join('\n') + `: what ${name} shows may change`}>
            {workers.length === 1
              ? <Who id={workers[0].participant} name={workers[0].alias} show="line" size={16} working meta="is working" />
              : <>{workers.slice(0, 3).map((w) => <Who key={w.key} id={w.participant} name={w.alias} show="avatar" size={16} working />)}{`${workers.length} working`}</>}
          </span>
        )}
        {slot.follow && !slot.pin && <span className={'wk-now' + (now ? ' on' : '')} aria-hidden={!now}>now #{number}</span>}
        {groupable && room !== 'menu' && <GroupSwitch zone={z.id} name={name} mode={slot.present} compact={room === 'compact'} />}
        </>}
        <span className="wk-grow" />
        {floating?.beforeMenu}
        {!floating && <ZoneTools ctl={ctl} name={name} compact={isNarrow}
          search={<SearchButton onOpen={() => search.setOpen(true)} label={`Search in ${name}`} />} />}
        <button className={'wk-zmenu' + (floating ? ' fl-btn' : '')} aria-label={`${name} zone menu`} aria-expanded={!!menuAt}
          onClick={(e) => setMenuAt(e.currentTarget)}>{'⋯'}</button>
        {floating?.afterMenu}
      </div>
      {search.bar}
      <div className="wk-zbody" key={slot.feed ? 'feed:' + slot.feed.source : slot.follow ? root ?? 'none' : 'kept'} ref={zbody}>
        {/* THE PLACED LANE: what was put here, above whatever is brought in,
            never narrowed by Show. Named only where something else follows it. */}
        {(asks.length > 0 || fromBrain.length > 0 || (placedItems.length > 0 && !oneRun)) && (
          <div className={'wk-placed' + (hasFeed ? ' wk-placed-lane' : '') + (byReply ? ' pz-gkept' : '')}
            data-placed={slot.items.length} data-kept-group={byReply ? '' : undefined}>
            {hasFeed && <p className={'wk-placedhead' + (byReply ? ' pz-gkepthead' : '')}><span className="wk-keptmark" aria-hidden="true">{'◆'}</span>Placed &middot; {slot.items.length}</p>}
            {asks.length > 0 && (
              <NeedsYou post={null} number={number ?? null} kept={asks} zone={z.id} page={page}
                onKeep={(id) => keepInZone(ASK + id, page, z.id, undefined, true)}
                onRemove={(id) => workspace.edit((a) => withTree(a, page, unkeep(treeOf(a, page)!, z.id, ASK + id)), `${name} no longer keeps it.`)} />
            )}
            {fromBrain.length > 0 && <BrainKept refs={fromBrain} zone={z.id} page={page}
              onRemove={(a) => workspace.edit((x) => withTree(x, page, unkeep(treeOf(x, page)!, z.id, a)), `${name} no longer keeps it.`)} />}
            {placedItems.length > 0 && !oneRun && (
              <Present items={placedItems} mode={slot.present} appearance={appearance}
                width={Math.max(0, (box.w || r.w) - 28)} height={Math.max(0, ((box.h || r.h) - 18) / (slot.feed ? 2 : 1))}
                onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
            )}
          </div>
        )}
        {/* WHAT IT BRINGS IN: a registry feed draws its own body ... */}
        {slot.feed && <FeedBody z={z} feed={slot.feed} source={source} setSlot={setSlot} />}
        {/* ... the post read (or held on), its words and objects. */}
        {railWords && <Words post={railWords} why={railWords.id === root && isReply ? wordsWhy : railWhy} />}
        {ownWords && <Words post={ownWords} why={wordsWhy} />}
        {slot.follow && needs && (
          <NeedsYou post={root} everywhere={!root} number={number ?? null} kept={asks} drawKept={false} elsewhere={elsewhere} zone={z.id} page={page}
            onKeep={(id) => keepInZone(ASK + id, page, z.id, undefined, true)}
            onRemove={(id) => workspace.edit((a) => withTree(a, page, unkeep(treeOf(a, page)!, z.id, ASK + id)), `${name} no longer keeps it.`)} />
        )}
        {f.failed && slot.follow && !needs && (
          <p className="wk-quietline wk-failed" role="alert">
            Couldn't read {post?.number != null ? `#${post.number}'s objects` : 'this post'} ({f.failed}).{' '}
            <button className="wk-retry" onClick={f.retry}>Retry</button>
          </p>
        )}
        {!byReply && (oneRun ? items : fedShown).length > 0 && (
          <Present items={oneRun ? shownItems : fedShown} mode={slot.present} appearance={appearance}
            width={Math.max(0, (box.w || r.w) - 28)} height={Math.max(0, (box.h || r.h) - 18)}
            onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
        )}
        {byReply && followed.length > 0 && (
          <Grouped zone={z.id} items={fedItems} posts={f.ids} mode={slot.present}
            highlight={isReply ? root : null}
            width={Math.max(0, (box.w || r.w) - 28)} height={Math.max(0, (box.h || r.h) - 18)}
            onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
        )}
        {slot.follow && held?.deleted && <p className="wk-quietline">This post was deleted.</p>}
        {/* A THREAD PAST ITS LIMIT SAYS SO (P10a): the read holds the newest
            replies, and this many older ones are not shown. */}
        {slot.follow && !needs && f.omitted > 0 && (
          <p className="wk-quietline wk-omitted" data-omitted={f.omitted}>
            {f.omitted} older {f.omitted === 1 ? 'reply is' : 'replies are'} not shown here: only the newest are read.
          </p>
        )}
        {slot.follow && !needs && isReply && post && (
          <p className="wk-quietline">#{post.number ?? '?'} is a reply{post.reply_to_number != null ? ` to #${post.reply_to_number}` : ''}</p>
        )}
        {/* AN EMPTY FEED SAYS WHAT IT FOUND NOTHING OF, in one quiet line --
            beside what was placed, never claiming the section is empty. */}
        {slot.follow && !needs && post && !isReply && !joins && f.addresses && !f.waiting && followed.length === 0 && !held?.deleted && (
          <p className={'wk-quietline' + (slot.items.length ? ' wk-feedempty' : '')}>
            {nothingFrom(post.number ?? null, slot.show, slot.kinds)}
            {replyCount > 0 ? ` It has ${replyCount} ${replyCount === 1 ? 'reply' : 'replies'}.` : ''}
          </p>
        )}
        {/* EMPTY, IT SAYS HOW TO FILL IT, and only while empty (#568 3.3). A
            request kept from What needs you counts as something placed (#576). */}
        {!hasFeed && slot.items.length === 0 && (
          <div className="wk-empty" data-empty="kept">
            <span className="wk-empty-mark" aria-hidden="true">{'◆'}</span>
            <span>{keeping ? `Into ${name}` : 'Nothing is placed here yet: drag an object in, or ◆ keep one from a post or a card.'}</span>
            {!keeping && <button className="wk-quietlink" onClick={() => setSlot((s) => withFeed(s, 'reading'), `${name} follows what you read.`)}>Follow what I'm reading instead</button>}
          </div>
        )}
      </div>
      {menuAt && (
        <Sheet anchor={menuAt} onClose={close} label={`${name} zone`}>
          <ZoneSheet z={z} slot={slot} page={page} ctl={ctl} setSlot={setSlot} close={close} placeLook={placeLook} ids={f.ids}
            reading={root ? { id: root, number: number ?? null, reply: isReply } : null} sources={feedSources()}
            groupable={groupable} groupWord={GROUPINGS.find((g) => g.g === grouping)?.label ?? (grouping as Grouping)}
            tidy={floating?.tidy} useLookForPlace={floating?.useLookForPlace}
            search={floating ? () => search.setOpen(true) : undefined} />
        </Sheet>
      )}
    </section>
  )
}

/* -- SELECTION, split off to the right while posts are selected ------------ */

function SelectedPost({ id, known }: { id: Id; known: boolean }) {
  const post = usePost(id)
  if (!known || !post)
    return (
      <div className="wk-obj wk-selection-item fw-selection-item" data-post={id}>
        <span className="wk-quiet">Unknown post {id}</span>
        <button className="wk-x" onClick={() => store.toggleSelect(id)} title="Remove from selection" aria-label="Remove from selection">{'✕'}</button>
      </div>
    )
  const text = wordsOf(post).replace(/\s+/g, ' ').trim()
  return (
    <div className="wk-obj wk-selection-item fw-selection-item" data-post={id} onClick={() => trace(id)} title="Read this post">
      <div className="wk-shead">
        <Who id={post.author} name={post.author_name} show="line" size={16} live className="wk-who" />
        {post.number != null && <span className="wk-quiet">#{post.number}</span>}
        {post.home_name && post.home !== nav.snapshot().conversation && <span className="wk-quiet">{post.home_name}</span>}
        <button className="wk-x" onClick={(e) => { e.stopPropagation(); store.toggleSelect(id) }}
          title="Remove from selection" aria-label="Remove from selection">{'✕'}</button>
      </div>
      <p className="wk-clamp">{text || 'No words.'}</p>
    </div>
  )
}

function Selection() {
  const coll = useCollection('selection') as SelectionCollection | undefined
  const selected = useSelection()
  useEffect(() => { void store.loadSelection().catch(() => {}) }, [])
  const items = (coll?.items ?? []).filter((i) => selected.has(i.id))
  /* The bulk actions are the frame's selection bar, shown while selecting:
     a selection held from before is acted on by selecting again. */
  const actions = useContext(Actions)
  const resume = actions && !actions.selectMode && selected.size > 0
    ? () => actions.startSelect(selected.values().next().value as Id) : null
  const [menuAt, setMenuAt] = useState<HTMLElement | null>(null)
  const close = useCallback(() => setMenuAt(null), [])
  return (
    <section className="wk-zone wk-panel wk-selection fw-zone-selection" data-zone="selection" aria-label="selection">
      <div className="wk-zcap">
        <span className="wk-what">Selection &middot; {selected.size} {selected.size === 1 ? 'post' : 'posts'}</span>
        <button className="wk-zmenu" aria-label="selection zone menu" aria-expanded={!!menuAt} onClick={(e) => setMenuAt(e.currentTarget)}>{'⋯'}</button>
      </div>
      <div className="wk-zbody">{items.map((i) => <SelectedPost key={i.id} id={i.id} known={i.known} />)}</div>
      {menuAt && (
        <Sheet anchor={menuAt} onClose={close} label="selection zone">
          <Sec>This zone</Sec>
          {resume && <Opt onPick={() => { close(); resume() }}>Keep, include or remove these posts&hellip; (each says what it will do first)</Opt>}
          <Opt onPick={() => { close(); store.clearSelection() }}>Clear the selection</Opt>
          <Sec>Arrange</Sec>
          <Opt onPick={() => { close(); showSelection(false) }}>Close (the selection stays)</Opt>
        </Sheet>
      )}
    </section>
  )
}

/** The Selection column beside This post, while selecting (or where the
 *  reader asked to see a held selection). */
export function Side(): ReactNode {
  const selected = useSelection()
  const selShown = useSelectionShown()
  const selecting = !!useContext(Actions)?.selectMode
  /* Selecting again opens it again; Done closes it. */
  const was = useRef(selecting)
  useEffect(() => {
    if (selecting && !was.current) { closed = false; emitShown() }
    if (!selecting && was.current) showSelection(false)
    was.current = selecting
  }, [selecting])
  const hasSel = selected.size > 0 && (selecting ? selShown !== 'closed' : selShown === 'here')
  return (
    <div className={'wk-side' + (hasSel ? ' show' : '')} aria-hidden={!hasSel}>
      <div className={'wk-slot' + (hasSel ? ' show' : '')}>{selected.size > 0 && <Selection />}</div>
    </div>
  )
}
