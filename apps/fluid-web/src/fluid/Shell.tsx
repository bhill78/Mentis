/* THE FLUID SHELL, at /fluid, in the owner-approved #184 demo's frame (F6).
 *
 * One bar; under it, with 12px gutters showing the atmosphere's picture, the
 * conversation column, the sheet that slides out beside it (replies, post
 * details) and the workspace. Navigation is `nav.ts`: reading a post, Back
 * that names where it goes, Esc that unwinds a detail to its anchor. The
 * boundaries between them are dragged (workspace/Boundary.tsx).
 *
 * WHAT THE DEMO DOES NOT SHOW, AND WHERE IT WENT. Home and the Stream are in
 * the switcher (the conversation name's sheet), with New conversation. Reply,
 * Select, Include here / Remove from here, Open in its home and Details are
 * on a post's hover chips; the selection bar appears only while selecting.
 * Save... for an unnamed conversation sits beside its name, only then.
 *
 * THE PRODUCTION CONVERSATION COMPONENTS ARE NOT USED. The Markdown renderers
 * are shared. Every write goes through Fluid's own command door (store.ts). */

import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Home from './Home'
import * as nav from './nav'
import { brainIdentity, store, newOp, type Id } from './store'
import { exportTurn } from '../api'
import { Actions, type PostActions } from './conversation/PostCard'
import { ConversationColumn, SelectionBar, StreamColumn, WIDTHS, Welcome } from './conversation/Column'
import { ThreadPanel, useClosing } from './conversation/Sheets'
import Full from './conversation/Full'
import { ask, drawnBy, focused, inThread, pinsOf, activate as showPinned, setFocused, setTarget, useThreads } from './conversation/threads'
import Switcher, { SWITCHER } from './conversation/Switcher'
import HomeColumn, { useHomeConversation } from './conversation/HomeColumn'
import { useCollection, useConversation, useError, useList, useNav, useSelection } from './conversation/hooks'
import { Layer } from './frame/layer'
import { useLook } from './frame/look'
import { closeSheet, openSheet, sheetOpen } from './frame/Sheet'
import { dismissToast, useToast } from './frame/toasts'
import TopBar, { titleButton } from './frame/TopBar'
import Notices from './frame/Notices'
import WorkspaceSlot from './frame/WorkspaceSlot'
import Boundary, { WORKSPACE_MIN as WORKSPACE_LEAST } from './workspace/Boundary'
import { workspace } from './workspace/place'
import { FocusView, MediaViewerHost } from './present'
import { Hosted } from './focus/hosts'
import ColumnPlace from './focus/ColumnPlace'
import Floats from './focus/Floats'
import DockLayer from './focus/DockLayer'
import { CONVERSATION_ID } from './focus/types'
import './focus/focus.css'
import NarrowHead, { NarrowOpen } from './frame/NarrowHead'
import { closeSheetPane, useNarrow, useSheetPane } from './frame/narrow'
import { GovContext, type GovNav } from './governance/context'
import GovFollow from './governance/Follow'
import GovPage from './governance/GovPage'
import { stageAfterOpenGov } from './governance/ladderTypes'
import { govObject, isGovObject, readHint, type OpenHint, type Source } from './governance/model'
import SourcesSurface from '../surfaces/sources/SourcesSurface'
import { SOURCES_EVENT } from '../surfaces/sources/route'
import { sourcesHash, sourcesPath as readSourcesPath } from '../surfaces/sources/navigation'
import { SPACE_HASH, atSpace } from '../surfaces/space/navigation'
/* The 3D Brain is loaded only when somebody goes there (brain/BrainPlace.tsx). */
const BrainPlace = lazy(() => import('./brain/BrainPlace'))

/* -- the address: /fluid?c=<conversation>&t=<open thread> -----------------
   Governance is /fluid?gov=1&s=<section>, beside Home and the Stream. */

interface Address { c: Id | null; t: Id | null; home: boolean; stream: boolean; from: Id | null; gov?: boolean; s?: string | null }

const GOV_SECTION = /^[a-z][a-z0-9-]{0,39}$/

function readAddress(): Address {
  const q = new URLSearchParams(location.search)
  const isGov = q.has('gov') || q.get('view') === 'governance'
  const isHome = !isGov && (q.has('home') || q.get('view') === 'home')
  const isStream = !isGov && (q.has('stream') || q.get('view') === 'stream' || q.get('stream') === '1')
  const rawFrom = q.get('from')
  const from = rawFrom === 'stream' || rawFrom === 'home' ? null : rawFrom
  const sec = q.get('s')
  return { c: q.get('c'), t: q.get('t'), home: isHome, stream: isStream, from, gov: isGov, s: sec && GOV_SECTION.test(sec) ? sec : null }
}
function govUrl(a: { s?: string | null; from?: Id | null }) {
  const q = new URLSearchParams({ gov: '1' })
  if (a.s) q.set('s', a.s)
  if (a.from) q.set('from', a.from)
  return '/fluid?' + q.toString()
}
function writeAddress(a: Address) {
  if (a.gov) { history.replaceState(history.state, '', govUrl(a)); return }
  const q = new URLSearchParams()
  if (a.home) {
    q.set('home', '1')
    if (a.from) q.set('from', a.from)
  } else if (a.stream) {
    q.set('stream', '1')
    if (a.t) q.set('t', a.t)
    if (a.from) q.set('from', a.from)
  } else {
    if (a.c) q.set('c', a.c)
    if (a.t) q.set('t', a.t)
  }
  const s = q.toString()
  history.replaceState(null, '', '/fluid' + (s ? '?' + s : ''))
}

/* -- where the reader left off: the Returning entry ----------------------- */

/* RELOADING KEEPS THE PLACE (F6 final fix round). Every address carries
   `?c=`, so a reload once went to the conversation's newest post. The place
   is kept with the thread open in it (a reply read inside a thread comes
   back read inside it), the pages and the width, and a reload of the same
   conversation -- or of plain /fluid -- comes back there, saying so. */
const LAST = 'mentis:fluid:last'
interface Last {
  c: Id; post: Id; number: number | null
  thread?: Id | null
}
function readLast(): Last | null {
  try {
    const v = JSON.parse(localStorage.getItem(LAST) ?? 'null')
    return v && typeof v.c === 'string' && typeof v.post === 'string' ? v : null
  } catch { return null }
}
function writeLast(v: Last | null) {
  try {
    if (v) localStorage.setItem(LAST, JSON.stringify(v))
    else localStorage.removeItem(LAST)
  } catch { /* the place is a convenience, not a record */ }
}

const STREAM = 'stream'

/* THE GOVERNANCE SECTION LAST SHOWN, so "Back to Governance" -- after a
   reload, from an item opened beside its conversation -- returns to the list
   it was opened from. A convenience, not a record. */
const GOV_LAST = 'mentis:fluid:gov-section'
const lastSection = (): string | null => {
  try { const v = localStorage.getItem(GOV_LAST); return v && GOV_SECTION.test(v) ? v : null } catch { return null }
}
const keepSection = (s: string) => { try { localStorage.setItem(GOV_LAST, s) } catch { /* convenience only */ } }

/** Where a visit to Governance was entered from: a conversation, at the post
 *  read there, or (null) Home. */
type GovFrom = { c: Id; post: Id | null; number: number | null } | null
interface Visit {
  from: GovFrom
  /** the item tabs it opened (their objects), which leaving it closes */
  pages: Set<string>
  /** it has pushed its one history entry; every later move replaces it */
  pushed: boolean
  /** that entry sits over the origin's own, so the browser's Back reaches it */
  overOrigin: boolean
}

/** Words typed into an act or a form on an item's page: a draft not to lose. */
const draftIn = (page: string) => [...document.querySelectorAll<HTMLTextAreaElement | HTMLInputElement>(
  `.wk-page[data-page="${CSS.escape(page)}"] .fg-act-slot :is(textarea, input:not([type]), input[type="text"])`)].some((el) => el.value.trim() !== '')

function ToastView() {
  const t = useToast()
  const [shown, setShown] = useState<typeof t>(null)
  useEffect(() => { if (t) setShown(t) }, [t])
  const on = !!t
  const v = t ?? shown
  return (
    <div className={'fx-toast' + (on ? ' on' : '')} id="toast" role="status" aria-hidden={!on}>
      <span id="toastMsg">{v?.text}</span>
      {v?.action && <button id="toastAct" onClick={() => { const run = v.action!.run; dismissToast(); run() }}>{v.action.label}</button>}
    </div>
  )
}

export default function Shell() {
  const [boot] = useState(() => {
    const a = readAddress()
    const atSources = readSourcesPath(location.hash) !== null || atSpace(location.hash)
    const plain = !atSources && !a.c && !a.home && !a.stream && !a.gov
    const saved = readLast()
    /* Plain /fluid, or this conversation's own address (with the thread that
       was open, if one was): where the reader was is where they come back. */
    const last = saved && !atSources && !a.home && !a.stream && !a.gov && (plain || (saved.c === a.c && (!a.t || (saved.thread ?? null) === a.t)))
      ? saved : null
    /* Its pages and widths come back with its place (workspace/place.ts),
       entered now so the first paint already has them. */
    const at = plain && last ? last.c : a.c
    if (at && !a.home) workspace.enter(a.stream ? 'stream' : at, a.stream ? 'stream' : 'conversation')
    /* A FIRST VISIT OPENS ON HOME (#190: "On a first visit, you open on
       Home"): nowhere left off yet, so Home, not the picker. */
    if (plain && !last) {
      history.replaceState({ view: 'home', from: null }, '', '/fluid?home=1')
      return { a: { ...a, home: true }, last, first: false }
    }
    return { a: plain && last ? { ...a, c: last.c, t: last.thread ?? null } : a, last, first: false }
  })
  const [addr, setAt] = useState<Address>(boot.a)
  const [sourcesPath, setSourcesPath] = useState<string | null>(() => readSourcesPath(location.hash))
  const [space, setSpace] = useState(() => atSpace(location.hash))
  const { c, home: isHome, stream: isStream, from: fromConv } = addr
  const isGov = !!addr.gov
  const [first, setFirst] = useState(boot.first)
  const s = useNav()
  const selected = useSelection()
  /* A selection kept from before (it is held for the tab) is shown, never
     held out of sight (#568 2.1). */
  const [selectMode, setSelectMode] = useState(() => store.selected.size > 0)
  const [saving, setSaving] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [autoFocusComposer, setAutoFocusComposer] = useState(false)
  const [replyTo, setReplyTo] = useState<Id | null>(null)
  const [me, setMe] = useState<Id | null>(null)
  const [authorError, setAuthorError] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pickingDestination, setPickingDestination] = useState(false)
  const [brain, setBrain] = useState('Mentis')
  const [brainInfo, setBrainInfo] = useState<{ name: string | null; whyNot?: string | null; path?: string | null } | undefined>()

  const busyRef = useRef(false)
  const heldOpRef = useRef<{ key: string; sig: string } | null>(null)
  /** what to read when a conversation arrives: the thread named, the place left */
  /* A RELOAD ARRIVES AT THE CURRENT DISCUSSION (#568 1.1): the post last
     read is read again while it is among the newest posts (or inside the
     thread that was open); one far back gives way to the newest. */
  const target = useRef<{ c: Id; post: Id | null; thread: Id | null; restored?: boolean } | null>(
    boot.a.c ? { c: boot.a.c, post: boot.last?.post ?? boot.a.t ?? null, thread: boot.a.t, restored: !boot.a.t && !!boot.last?.post } : null)
  const lastRead = useRef(new Map<Id, Id>())
  const greeted = useRef(false)
  /** the place left was far back, and the newest was read instead (#568 1.1) */
  const gaveWay = useRef(false)
  const [settled, setSettled] = useState(0)
  /** a conversation entered empty: its first post, when it comes, is read */
  const fresh = useRef<Id | null>(null)

  const conv = useConversation(c)
  /* The conversation Home's column holds (D1): read there, it is where the
     reader is, and Home stays (below). */
  const homeConv = useHomeConversation()
  const fromConvObj = useConversation(fromConv)
  const list = useList()
  const error = useError()
  const view: 'conversation' | 'home' | 'stream' | 'gov' | 'sources' | 'space' = sourcesPath !== null ? 'sources' : space ? 'space' : isGov ? 'gov' : isHome ? 'home' : isStream ? 'stream' : 'conversation'
  const scheme = useLook(view === 'conversation' ? c : null, view === 'conversation' ? conv?.name ?? null : null)

  /* -- operation keys: a retry after a lost answer is the same operation -- */
  const getOp = (sig: string): string => {
    if (heldOpRef.current && heldOpRef.current.sig === sig) return heldOpRef.current.key
    const key = newOp()
    heldOpRef.current = { key, sig }
    return key
  }
  const runWithOp = async <T,>(sig: string, fn: (opKey: string) => Promise<T>): Promise<T> => {
    const key = getOp(sig)
    try {
      const res = await fn(key)
      heldOpRef.current = null
      return res
    } catch (err: any) {
      if (err?.serverAnswer || err?.status != null || err?.error || err?.refused || err?.items) heldOpRef.current = null
      throw err
    }
  }

  const ensureAuthor = async (): Promise<Id | null> => {
    if (me) return me
    try {
      const author = await store.loadMe()
      setMe(author)
      setAuthorError(null)
      return author
    } catch (err: any) {
      const msg = String(err.message ?? err)
      setAuthorError(msg)
      setRefusal(`Cannot determine author: ${msg}`)
      return null
    }
  }

  useEffect(() => {
    store.follow()
    void store.loadList()
    store.loadMe()
      .then((m) => { setMe(m); setAuthorError(null) })
      .catch((err: Error) => setAuthorError(err.message))
    /* The brand names the brain, as its own manifest does. */
    void brainIdentity().then((b) => {
      const name = b?.corpus_name ?? b?.corpus_role
      if (typeof name === 'string' && name) setBrain(name)
      if (b) setBrainInfo({ name: b.corpus_name ?? null, whyNot: b.corpus_name_why_not ?? null, path: b.corpus_path ?? null })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const onPopState = (e: PopStateEvent) => {
      setSourcesPath(readSourcesPath(location.hash))
      setSpace(atSpace(location.hash))
      const q = new URLSearchParams(location.search)
      const govActive = q.has('gov') || e.state?.view === 'gov'
      if (govActive) {
        const sec = q.get('s')
        setAt((p) => ({ ...p, gov: true, home: false, stream: false, s: sec && GOV_SECTION.test(sec) ? sec : null, from: q.get('from') || p.from }))
        return
      }
      const homeActive = q.has('home') || q.get('view') === 'home' || e.state?.view === 'home'
      const streamActive = q.has('stream') || q.get('view') === 'stream' || q.get('stream') === '1' || e.state?.view === 'stream'
      const rawFrom = q.get('from') || (e.state?.from as string) || null
      const from = rawFrom === 'stream' || rawFrom === 'home' ? null : rawFrom
      const nextC = q.get('c') || (e.state?.c as string) || null
      const nextT = q.get('t') || (e.state?.t as string) || null
      /* BACK OUT OF GOVERNANCE leaves all of it (the owner, 2026-10-23): the
         visit's one entry is left, its item tabs close, and the conversation
         it was entered from is read at the post the reader was at. */
      const left = leaving.current ?? (govVisit.current ? govVisit.current.from : undefined)
      leaving.current = undefined
      if (govVisit.current) endVisit.current()
      const at = left && nextC === left.c ? left : null
      /* The address moved: whatever was still arriving no longer is (D1). */
      arrival.current += 1
      /* Forward onto an item opened from Home arrives as the click did, Home
         beneath it: every Back from it goes to Home (opr-18ce7867fa89). */
      const homeItem = e.state?.fromHome === true && !!nextC && !homeActive && !streamActive
      fromHome.current = homeItem
      if (nextC) target.current = { c: nextC, post: at?.post ?? nextT ?? (homeItem ? lastRead.current.get(nextC) ?? null : null), thread: nextT }
      setAt({ c: nextC, t: nextT, home: homeActive, stream: streamActive, from, gov: false })
      /* Already the conversation nav holds (an item opened beside it): no
         arrival will read the post, so it is read here. */
      if (at && nav.snapshot().conversation === at.c) {
        nav.showPage('this-post')
        if (at.post) nav.read(at.c, at.post, at.number ?? store.posts.get(at.post)?.number ?? null)
      }
      if (at?.post) reveal.current(at.post)
      if (homeItem && target.current) {
        const want = target.current
        nav.arrive(want.c, want.post, want.post ? store.posts.get(want.post)?.number ?? null : null, { from: nav.HOME })
        clicked.current = { want, detail: nav.snapshot().detail, escapes: escapes.current }
      }
    }
    /* Esc while an opened post is still arriving is the owner's: the thread
       it would have opened round the post stays closed (D1). */
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') escapes.current += 1 }
    window.addEventListener('popstate', onPopState)
    window.addEventListener('keydown', onEsc, true)
    return () => {
      window.removeEventListener('popstate', onPopState)
      window.removeEventListener('keydown', onEsc, true)
    }
  }, [])

  const openSources = useCallback((path = '') => {
    history.pushState({ view: 'sources' }, '', location.pathname + location.search + sourcesHash(path))
    setSourcesPath(path)
    setSpace(false)
  }, [])

  /* THE 3D BRAIN (brain/BrainPlace.tsx) is a place of its own over whatever
     address was open, as Manage Sources is: Back returns there. */
  const openSpace = useCallback(() => {
    if (!atSpace(location.hash)) history.pushState({ view: 'space' }, '', location.pathname + location.search + SPACE_HASH)
    setSourcesPath(null)
    setSpace(true)
  }, [])
  /* Every other door out of it pushes an address of its own, without the
     hash: wherever that was is where the reader now is. */
  useEffect(() => { setSpace(atSpace(location.hash)) }, [addr])

  /* Reference chips can open an exact observation from anywhere.  It is a
     history movement, so Back returns to the conversation and post. */
  useEffect(() => {
    const onSources = (e: Event) => openSources((e as CustomEvent<string>).detail ?? '')
    const onHash = () => { setSourcesPath(readSourcesPath(location.hash)); setSpace(atSpace(location.hash)) }
    window.addEventListener(SOURCES_EVENT, onSources)
    window.addEventListener('hashchange', onHash)
    return () => {
      window.removeEventListener(SOURCES_EVENT, onSources)
      window.removeEventListener('hashchange', onHash)
    }
  }, [openSources])

  useEffect(() => {
    if (c && c !== STREAM && !store.conversations.has(c)) void store.loadConversations([c])
    if (fromConv && !store.conversations.has(fromConv)) void store.loadConversations([fromConv])
  }, [c, fromConv])

  /* -- a conversation arrives: read the post named, or where the reader was,
        or its newest. Reading it is the step Back will retrace. -----------
     ONLY WHEN THE ADDRESS MOVED. When nav moved -- Back or Forward into
     another conversation -- nav already holds where the reader is there, and
     the shell follows it (below). Reading "where the reader was" in the
     conversation still shown would pull nav back, the shell would follow,
     and the two would chase each other until React gave up (the F6 review's
     hang, error #185). `arrived` is the conversation this effect last
     settled; it acts again only for another one, or for a target named. */
  const coll = useConversationItems(view === 'conversation' ? c : null)
  const arrived = useRef<Id | null>(null)
  /* OPENED FROM ELSEWHERE, NAV MOVES IN THE CLICK (D1). `handleOpenPost`
     reads the post at once, so nothing drawn meanwhile -- the thread panel,
     the address, the place kept -- still describes where the reader was.
     This effect only finishes that arrival, adding no step: the thread that
     draws the post is opened round it. `clicked` is that click's target and
     what nav held after it. Each arrival has a number; an answer that comes
     back after another arrival, a Back, the owner reading something else or
     pressing Esc is dropped -- what they did meanwhile is what they get. */
  const arrival = useRef(0)
  const started = useRef<typeof target.current>(null)
  const clicked = useRef<{ want: NonNullable<typeof target.current>; detail: nav.Detail | null; escapes: number } | null>(null)
  const escapes = useRef(0)
  /** the conversation shown was opened from Home: Back to Home is the browser's Back */
  const fromHome = useRef(false)
  /** the visit to Governance under way, if one is (below) */
  const govVisit = useRef<Visit | null>(null)
  /** where the way out of Governance is going, while the browser's Back takes it there */
  const leaving = useRef<GovFrom | undefined>(undefined)
  const reveal = useRef<(post: Id) => void>(() => {})
  useEffect(() => {
    const want = target.current?.c === c ? target.current : null
    if (view !== 'conversation' || !c || !coll) return
    /* A conversation entered empty: its first post, once it arrives, is read
       -- the Reading box and This post follow it (F6 final fix round). It is
       not a step: there was nothing read before it to go back to. */
    if (fresh.current === c && s.conversation === c && !s.reading && !want && coll.items.length) {
      fresh.current = null
      const p = coll.items[coll.items.length - 1]
      nav.read(c, p.id, store.posts.get(p.id)?.number ?? p.number ?? null)
      return
    }
    if (s.conversation === c && !want) { arrived.current = c; return }
    if (arrived.current === c && !want) return
    const items = coll.items
    arrived.current = c
    /* Nothing to read (a new conversation): it starts clean, carrying nothing in. */
    if (!items.length) { target.current = null; fresh.current = c; nav.enter(c); return }
    /* This arrival is already under way: the posts coming in do not start it again. */
    if (want && started.current === want) return
    started.current = want
    const seq = ++arrival.current
    const mine = want && clicked.current?.want === want ? clicked.current : null
    const stale = () => {
      if (arrival.current !== seq) return true
      if (!mine) return false
      const n = nav.snapshot()
      return n.conversation !== c || n.reading !== mine.want.post || n.detail !== mine.detail || escapes.current !== mine.escapes
    }
    const drop = () => {
      if (target.current === want) target.current = null
      if (clicked.current === mine) clicked.current = null
      setSettled((x) => x + 1)
    }
    const far = !!want?.restored && !items.some((x) => x.id === want.post)
    if (far) gaveWay.current = true
    const id = (far ? null : want?.post) ?? lastRead.current.get(c) ?? items[items.length - 1].id
    const go = (post: Id) => {
      if (stale()) { drop(); return }
      const p = store.posts.get(post)
      const n = p?.number ?? items.find((x) => x.id === post)?.number ?? null
      if (!want?.thread) {
        target.current = null
        setSettled((x) => x + 1)
        if (mine) nav.arrive(c, post, n); else nav.read(c, post, n)
        return
      }
      /* The thread that draws it here: a reply's is the thread of the post it
         answers, with the reply read inside it -- never an empty thread of
         its own (the review's "#184 . 0 replies", opr-49f1f943b6a9). */
      void drawnBy(c, want.thread).then((root) => {
        if (stale()) { drop(); return }
        target.current = null
        if (clicked.current === mine) clicked.current = null
        setSettled((x) => x + 1)
        if (mine) nav.arrive(c, post, n, { root })
        else nav.openDetail({ kind: 'replies', root, anchor: { kind: 'post', id: root }, mode: 'aside' },
          { read: { conversation: c, post, number: n } })
      })
    }
    if (store.posts.has(id) || items.some((x) => x.id === id)) go(id)
    else void store.loadPosts([id]).then(() => go(store.posts.has(id) ? id : items[items.length - 1].id))
  }, [view, c, coll, s.conversation])

  /* -- Back across conversations: the shell follows where nav went -------- */
  const navConv = useRef(s.conversation)
  useEffect(() => {
    const was = navConv.current
    navConv.current = s.conversation
    if (!s.conversation || s.conversation === was) return
    if (s.conversation === nav.HOME) {
      /* Back to Home from what was opened there (D1): the browser's own Back,
         so the item's entry stays in history to go Forward to. */
      if (isHome) return
      if (fromHome.current) { fromHome.current = false; history.back() } else openHome()
      return
    }
    if (s.conversation === STREAM) {
      if (!isStream) setAt((p) => ({ ...p, stream: true, home: false, t: null }))
    } else if (isHome && s.conversation === homeConv) {
      /* Reading in Home's own column is reading on Home. */
      return
    } else if (isStream || isHome || s.conversation !== c) {
      setAt((p) => ({ ...p, c: s.conversation, t: null, stream: false, home: false, gov: false }))
    }
  }, [s.conversation, c, isStream, isHome, homeConv])

  /* -- the address follows: the conversation, and the thread open in it --- */
  const convSheet = nav.sheetOf(s)
  const openThread = convSheet?.kind === 'replies' ? convSheet.root : null
  useEffect(() => {
    if (view === 'sources' || view === 'space') return
    /* On the way back to Home (D1) the entry left is not rewritten. */
    if (s.conversation === nav.HOME && view !== 'home') return
    /* A thread still arriving keeps the address that named it (D1). */
    const arriving = view === 'conversation' && target.current?.c === c ? target.current.thread : null
    writeAddress({ ...addr, t: view === 'home' || view === 'gov' ? null : openThread ?? arriving })
    /* The entry of an item opened from Home keeps saying so, for Forward onto
       it to arrive with Home beneath (opr-18ce7867fa89). On Home it is left,
       and on Governance, which is no item opened from Home: its own entry
       keeps its own state, and Back onto the item's entry says so again. */
    if (view === 'home' || view === 'gov') fromHome.current = false
    else if (fromHome.current) history.replaceState({ fromHome: true }, '', location.href)
  }, [addr, openThread, view, s.conversation, settled])

  /* -- where the reader is, kept for the Returning entry ------------------- */
  useEffect(() => {
    if (!s.conversation || s.conversation === STREAM || !s.reading || view === 'home') return
    lastRead.current.set(s.conversation, s.reading)
    writeLast({ c: s.conversation, post: s.reading, number: s.readingNumber, thread: openThread })
  }, [s.conversation, s.reading, s.readingNumber, openThread, view])

  /* -- Returning: "Back where you left off", once, with Start fresh --------
     Said once the arrival is settled, and only when it is true: a place far
     back gave way to the newest, and the words say that instead. */
  useEffect(() => {
    if (greeted.current || !boot.last || s.conversation !== boot.last.c || !conv) return
    if (target.current?.c === s.conversation) return
    greeted.current = true
    const was = boot.last.number != null ? `#${boot.last.number}` : 'Where you were'
    nav.toast({
      text: gaveWay.current
        ? `Back in ${conv.name}, at the newest posts. ${was} was further back.`
        : `Back where you left off: ${conv.name}, reading ${s.readingNumber != null ? `#${s.readingNumber}` : 'your place'}.`,
      action: { label: 'Start fresh', run: () => { writeLast(null); location.assign('/fluid') } },
    })
  }, [s.conversation, s.readingNumber, conv, boot.last, settled])

  /* -- First visit: the picker opens under the title ---------------------- */
  useEffect(() => {
    if (!first) return
    const t = setTimeout(() => { const el = titleButton(); if (el) openSheet(SWITCHER, el) }, 300)
    return () => clearTimeout(t)
  }, [first])

  /* -- keys: Esc unwinds, Alt+Left goes back (room is given by dragging) -- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.matches?.('input, textarea, select') || el.isContentEditable)) return
      if (e.key === 'Escape') {
        if (sheetOpen()) { closeSheet(); return }
        const d = nav.snapshot().detail
        const inFocus = focused() && !!document.querySelector('.fx-main.fx-focus')
        /* Esc unwinds what can be seen (#184). Focus steps the workspace back,
           and an object detail is drawn in it: Esc leaves Focus first, and the
           object is still open when the workspace comes back. */
        if (d && inFocus && d.kind === 'object') { e.preventDefault(); setFocused(false); return }
        if (d) { e.preventDefault(); nav.closeDetail(); return }
        /* At a narrow width, Esc with nothing open in it closes the sheet. */
        if (closeSheetPane()) { e.preventDefault(); return }
        /* Conversation focus is the last thing Esc unwinds: the workspace
           comes back as it was, the reader's place kept (Column.tsx). */
        if (inFocus) { e.preventDefault(); setFocused(false) }
        return
      }
      if (e.altKey && e.key === 'ArrowLeft') { e.preventDefault(); nav.back(); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /* -- the reply target belongs to the conversation it was chosen in -------
     A reply to a post that lives elsewhere, chosen HERE, is deliberate and
     is written here, saying so ("Replying to Local LLM Prelim #222, in ...")
     -- 866dced's anchored reply. It never travels: moving to another
     conversation by any door (switcher, a link, Open in its home, Back)
     clears it, so a composer never silently carries the last one's target. */
  const here = c && c !== STREAM ? c : null
  /* The conversation whose posts are acted on: the one shown, or on Home the
     one in Home's column -- its posts do there what they do in it. */
  const place = view === 'home' ? homeConv : view === 'conversation' || view === 'space' ? here : null
  const replyHere = useRef(here)
  useEffect(() => {
    if (replyHere.current === here) return
    replyHere.current = here
    setReplyTo(null)
  }, [here])

  /* -- moving between places ---------------------------------------------- */
  /* Every other way out of Governance leaves all of it: choosing a
     conversation, Home, the Stream, a post opened from anywhere. */
  const pick = (id: Id) => {
    endVisit.current()
    /* Chosen from the 3D Brain: the Brain stays one Back behind. */
    if (atSpace(location.hash)) history.pushState(null, '', location.pathname + location.search)
    setFirst(false)
    target.current = { c: id, post: lastRead.current.get(id) ?? null, thread: null }
    setAt({ c: id, t: null, home: false, stream: false, from: fromConv, gov: false })
    setPickingDestination(false)
    setAutoFocusComposer(false)
    setReplyTo(null)
  }
  /* A conversation opened over the 3D Brain is the one shown, without
     leaving the Brain: no step in history, and the Brain's address kept. */
  const showOverBrain = (id: Id) => {
    if (id === here) return
    target.current = { c: id, post: lastRead.current.get(id) ?? null, thread: null }
    setAt((p) => ({ ...p, c: id, t: null, home: false, stream: false, gov: false }))
    setReplyTo(null)
  }
  const fromHere = () => here || fromConv || (list && list.length ? list[0].id : null)
  const openHome = () => {
    endVisit.current()
    const from = fromHere()
    setAt((prev) => ({ ...prev, home: true, stream: false, gov: false, from }))
    history.pushState({ view: 'home', from }, '', '/fluid?home=1' + (from ? `&from=${encodeURIComponent(from)}` : ''))
  }
  const openStream = () => {
    endVisit.current()
    const from = fromHere()
    setAt((prev) => ({ ...prev, stream: true, home: false, gov: false, from }))
    history.pushState({ view: 'stream', from }, '', '/fluid?stream=1' + (from ? `&from=${encodeURIComponent(from)}` : ''))
  }
  const returnToConv = () => {
    const to = fromConv || (list && list.length ? list[0].id : null)
    if (!to) return
    target.current = { c: to, post: lastRead.current.get(to) ?? null, thread: null }
    setAt({ c: to, t: null, home: false, stream: false, from: null, gov: false })
    history.pushState({ c: to, t: null }, '', `/fluid?c=${encodeURIComponent(to)}`)
  }
  const handleOpenPost = useCallback((convId: Id, postId: Id) => {
    const prev = (isStream || isHome || isGov ? fromConv : c) || null
    const realFrom = prev && prev !== STREAM ? prev : null
    endVisit.current()
    setFirst(false)
    const want = { c: convId, post: postId, thread: postId }
    target.current = want
    setAt({ c: convId, t: postId, home: false, stream: false, from: realFrom, gov: false })
    history.pushState({ c: convId, t: postId, from: realFrom, ...(isHome ? { fromHome: true } : {}) }, '',
      `/fluid?c=${encodeURIComponent(convId)}&t=${encodeURIComponent(postId)}`)
    /* Nav moves now, with the address (D1). From Home it is no step: Back goes to Home. */
    arrival.current += 1
    fromHome.current = isHome
    const n = store.posts.get(postId)?.number ?? null
    if (isHome) nav.arrive(convId, postId, n, { from: nav.HOME }); else nav.read(convId, postId, n)
    clicked.current = { want, detail: nav.snapshot().detail, escapes: escapes.current }
  }, [isStream, isHome, isGov, fromConv, c])

  /* -- Governance (owner's decision, Turn #365) ---------------------------
     A page beside Home and the Stream. An item opens beside the conversation
     it was proposed from: the column switches there, reading that Turn, and
     the item opens as a tab next to This post. Where the record names no
     conversation, it opens on Governance's own Stage. */
  const sources = useRef(new Map<Id, Source | null>())
  const edits = useRef(new Set<Id>())
  const [govFocus, setGovFocus] = useState<Id | null>(null)
  /** the adoption card For adoption brings into view, when one was asked for */
  const [govCard, setGovCard] = useState<Id | null>(null)
  const pendingItem = useRef<{ entry: Id; object: string; title: string; c: Id; post: Id | null } | null>(null)
  const [pendingTick, setPendingTick] = useState(0)
  const [editNonce, setEditNonce] = useState(0)
  const [, setVisitTick] = useState(0)
  /* The Turn it came from is brought into view in the column, once the
     conversation's first-arrival scroll to its newest post has run. */
  const revealReading = (want?: Id) => {
    /* Asked again while a slow conversation's arrival may still scroll to its
       newest post -- but only for the post it was asked for, and never once
       the reader has moved anything themselves. */
    const post = want ?? nav.snapshot().reading
    let stopped = false
    const inputs = ['wheel', 'touchstart', 'keydown', 'mousedown'] as const
    const stop = () => { stopped = true; inputs.forEach((ev) => window.removeEventListener(ev, stop)) }
    inputs.forEach((ev) => window.addEventListener(ev, stop, { passive: true }))
    window.setTimeout(stop, 2600)
    ;[450, 1200, 2500].forEach((ms) => window.setTimeout(() => {
      if (stopped || nav.snapshot().reading !== post) return
      /* Within the column's own scroller only: scrollIntoView would also move
         the page around it where the column is stacked (a phone). Only ever
         when the read post is out of view. */
      const el = document.querySelector<HTMLElement>('.fx-conv .fx-post.reading')
      const box = el?.closest<HTMLElement>('.fx-conv-scroll')
      if (!el || !box) return
      const r = el.getBoundingClientRect(), b = box.getBoundingClientRect()
      if (r.top >= b.top && r.top < b.bottom - 40) return
      box.scrollTop += r.top - b.top - Math.max(0, (b.height - r.height) / 2)
    }, ms))
  }
  reveal.current = revealReading

  /* -- ONE WAY OUT (the owner, 2026-10-23: "Governance is VERY hard to get
     out of"). A VISIT to Governance remembers where it was entered from: the
     conversation and the post being read there, or Home where there was no
     conversation. The bar's Back says that place, "Back to <name>", on the
     Governance page, on an item, with an act half-written, and takes the
     reader there in one click; "Back to Governance" is only an item's way
     back to the list. Within a visit every move -- the list, an item beside
     its conversation, back to the list -- replaces the visit's one history
     entry, so the browser's Back leaves it too. However it is left (that
     Back, choosing a conversation, Home, the Stream, a post opened), the item
     tabs the visit opened close; one with an act half-written in it stays, so
     its draft is there as it was. */
  const endVisit = useRef(() => {})
  endVisit.current = () => {
    const v = govVisit.current
    if (!v) return
    govVisit.current = null
    setGovFocus(null)
    const was = pendingItem.current
    if (was) edits.current.delete(was.entry)
    pendingItem.current = null
    /* On a phone the item was the sheet: the conversation has the screen again. */
    if (closeVisitPages(v)) closeSheetPane()
    setVisitTick((n) => n + 1)
  }
  /** the visit's item tabs in the conversation nav holds, closed: not one
   *  that was there before the visit, nor one holding a half-written act */
  const closeVisitPages = (v: Visit) => {
    let closed = 0
    for (const p of nav.snapshot().pages)
      if ('object' in p && p.object && v.pages.has(p.object) && !draftIn(p.id)) { v.pages.delete(p.object); nav.closePage(p.id); closed++ }
    return closed
  }
  /** Begin a visit, unless one is under way: where the reader is now is where its way out goes. */
  const startVisit = (): Visit => {
    if (govVisit.current) return govVisit.current
    const n = nav.snapshot()
    const from: GovFrom = view === 'conversation' && here
      ? { c: here, post: n.conversation === here ? n.reading : lastRead.current.get(here) ?? null, number: n.conversation === here ? n.readingNumber : null }
      : fromConv && fromConv !== STREAM ? { c: fromConv, post: lastRead.current.get(fromConv) ?? null, number: null } : null
    /* Its entry goes over the origin's own only when it is entered from it:
       from Home with a conversation before it, Home's entry is beneath. */
    const v: Visit = { from, pages: new Set(), pushed: false, overOrigin: view === 'conversation' ? !!here : view === 'home' && !from }
    govVisit.current = v
    setVisitTick((x) => x + 1)
    return v
  }
  /** The visit's history: its first move pushes its one entry, every other replaces it. */
  const visitEntry = (state: unknown, url: string) => {
    const v = startVisit()
    if (v.pushed) history.replaceState(state, '', url)
    else { v.pushed = true; history.pushState(state, '', url) }
  }
  /** Where the way out goes: the visit's start; without one (a reload, Forward
   *  onto Governance), the conversation named, or the one an item is open in. */
  const visitFrom = (): GovFrom => govVisit.current ? govVisit.current.from
    : view === 'conversation' && here ? { c: here, post: s.conversation === here ? s.reading : null, number: s.conversation === here ? s.readingNumber : null }
    : fromConv && fromConv !== STREAM ? { c: fromConv, post: lastRead.current.get(fromConv) ?? null, number: null } : null
  const leaveGov = () => {
    const v = govVisit.current
    const to = visitFrom()
    /* Its entry is over the origin's: the browser's own Back, which the
       popstate above finishes, so history holds no Governance to come back to. */
    if (v && v.pushed && v.overOrigin) { leaving.current = to; history.back(); return }
    endVisit.current()
    if (!to) {
      setAt((prev) => ({ ...prev, home: true, stream: false, gov: false, from: null }))
      history.replaceState({ view: 'home', from: null }, '', '/fluid?home=1')
      return
    }
    if (view === 'conversation' && here === to.c) {
      /* An item open beside this very conversation: This post, at the post. */
      nav.showPage('this-post')
      if (to.post) nav.read(to.c, to.post, to.number ?? store.posts.get(to.post)?.number ?? null)
    } else {
      setFirst(false)
      target.current = { c: to.c, post: to.post, thread: null }
      setAt({ c: to.c, t: null, home: false, stream: false, from: null, gov: false })
    }
    history.replaceState({ c: to.c, t: null }, '', `/fluid?c=${encodeURIComponent(to.c)}`)
    if (to.post) revealReading(to.post)
  }
  const openGov = (section?: string, opts?: { card?: Id | null }) => {
    /* A SECTION NAMED IS THE SECTION SHOWN: the item open on Governance's
       Stage would otherwise stay drawn over it (GovPage draws its tabs only
       with nothing focused). Opened with no section, as an item opening on
       Stage does, the focus is left alone. */
    if (section) {
      const next = stageAfterOpenGov({ focus: govFocus, card: govCard }, section, opts?.card)
      setGovFocus(next.focus)
      setGovCard(next.card)
    }
    const was = pendingItem.current
    if (was) edits.current.delete(was.entry)
    pendingItem.current = null
    const v = startVisit()
    const from = v.from?.c ?? null
    const sec = section ?? addr.s ?? lastSection()
    setAt((prev) => ({ ...prev, gov: true, home: false, stream: false, s: sec, from }))
    visitEntry({ view: 'gov', from }, govUrl({ s: sec, from }))
  }
  /** read a post in the column: here if it is this conversation, else there */
  const readPost = (conversation: Id, post: Id | null) => {
    if (view === 'conversation' && here === conversation) {
      if (!post) return Promise.resolve()
      const show = () => nav.read(conversation, post, store.posts.get(post)?.number ?? null)
      if (store.posts.has(post)) { show(); return Promise.resolve() }
      return store.loadPosts([post]).then(show).catch(() => {})
    }
    setFirst(false)
    /* Moving on within a visit, its tabs in the conversation left close:
       nothing of it is left behind there. */
    const v = govVisit.current
    if (v && view === 'conversation') closeVisitPages(v)
    target.current = { c: conversation, post: post ?? lastRead.current.get(conversation) ?? null, thread: null }
    setAt({ c: conversation, t: null, home: false, stream: false, gov: false, from: v ? v.from?.c ?? null : here ?? fromConv })
    if (v) visitEntry({ c: conversation, t: null }, `/fluid?c=${encodeURIComponent(conversation)}`)
    else history.pushState({ c: conversation, t: null }, '', `/fluid?c=${encodeURIComponent(conversation)}`)
    return null
  }
  /** Its tab opens, counted as the visit's unless it was already open. */
  const openItemPage = (object: string, title: string) => {
    const v = startVisit()
    if (!nav.snapshot().pages.some((p) => 'object' in p && p.object === object)) v.pages.add(object)
    nav.openItemPage(object, title)
  }
  const openItem = (entry: Id, hint?: OpenHint | null, opts?: { edit?: boolean }) => {
    if (opts?.edit) { edits.current.add(entry); setEditNonce((n) => n + 1) }
    const go = (h: OpenHint) => {
      const src = h.source
      sources.current.set(entry, src)
      startVisit()
      if (!src) {
        /* Nothing to open beside: it opens on Governance's own Stage, never
           as a tab beside a conversation it has nothing to do with. */
        setGovFocus(entry)
        if (view !== 'gov') openGov()
        return
      }
      const object = govObject(entry)
      const here_ = readPost(src.conversation, src.turn)
      if (here_) { void here_.then(() => { openItemPage(object, h.title); revealReading() }); return }
      pendingItem.current = { entry, object, title: h.title, c: src.conversation, post: src.turn }
      setPendingTick((n) => n + 1)
    }
    if (hint?.source) go(hint)
    else void readHint(entry).then((h) => go({ title: hint?.title ?? h.title, source: h.source }))
      .catch((err: Error) => { if (hint) go(hint); else { edits.current.delete(entry); setRefusal(`Could not open ${entry}: ${err.message}`) } })
  }
  /* The item's tab opens once its conversation has arrived and the Turn it
     came from is being read (or, with no Turn named, the reader's place). */
  useEffect(() => {
    const p = pendingItem.current
    if (!p) return
    /* Somewhere else now (Back, Home, another conversation): it is not opened later. */
    if (view !== 'conversation' || c !== p.c) { edits.current.delete(p.entry); pendingItem.current = null; return }
    if (s.conversation !== p.c) return
    if (p.post && (!s.reading || (s.reading !== p.post && target.current))) return
    pendingItem.current = null
    openItemPage(p.object, p.title)
    revealReading()
  }, [s.conversation, s.reading, view, c, pendingTick])
  /* CLOSING AN ITEM (its Close, its tab's ×) returns to where it was opened
     from: during a visit, the Governance list -- never This post of a
     conversation with Governance still half there. A tab kept from before
     closes as it always did, This post staying. */
  const closeItem = (page: string) => {
    const n = nav.snapshot()
    const p = n.pages.find((x) => x.id === page)
    const object = p && 'object' in p ? p.object : undefined
    const v = govVisit.current
    nav.closePage(page)
    closeSheetPane()
    if (v && object && v.pages.delete(object) && n.page === page) openGov()
  }
  const govNav: GovNav = {
    me,
    owner: me ? store.owner : null,
    openItem,
    openGov,
    closeItem,
    readTurn: (conversation, turn) => { void readPost(conversation, turn) },
    takeEdit: (entry) => edits.current.delete(entry),
    sourceOf: (entry) => sources.current.get(entry),
    editNonce,
  }
  useEffect(() => { if (view === 'gov' && addr.s) keepSection(addr.s) }, [view, addr.s])
  const shownPage = s.pages.find((p) => p.id === s.page)
  const onGovPage = view === 'conversation' && !!shownPage && 'object' in shownPage && !!shownPage.object && isGovObject(shownPage.object)
  /* Governance may be mounted -- its page, or an item tab kept beside a
     conversation -- so it follows the record on Fluid's own pulse
     (governance/Follow.tsx), rereading only while that content is on screen. */
  const govMounted = view === 'gov' || (view === 'conversation' && s.pages.some((p) => 'object' in p && !!p.object && isGovObject(p.object)))
  const govOnScreen = view === 'gov' || onGovPage

  /* -- writes, each through Fluid's command door, each refusal said -------- */
  const formatRefusal = (err: any): string => {
    if (!err) return 'Operation failed'
    const items = Array.isArray(err.items) ? err.items : (Array.isArray(err.refused) ? err.refused : null)
    const details = items ? (items as any[]).map((r) => r.error ?? `Post ${r.post} refused`).join('; ') : ''
    if (details) return `${err.error || err.message || 'Refused'}: ${details}`
    return err.error || err.message || String(err)
  }
  const guarded = async (fn: () => Promise<void>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try { await fn() } finally { busyRef.current = false; setBusy(false) }
  }

  /* + in the bar: a new, unnamed conversation, opened. (Home's own starter
     box went with D1: Home's conversation column is where one starts there.) */
  const handleNewConversation = () => guarded(async () => {
    try {
      const author = await ensureAuthor()
      if (!author) return
      const sig = JSON.stringify({ action: 'createConversation', author })
      const got = await runWithOp(sig, (op) => store.createConversation(author, op))
      endVisit.current()
      setFirst(false)
      setAt({ c: got.conversation, t: null, home: false, stream: false, from: fromConv })
      store.clearSelection()
      setSelectMode(false)
      setPickingDestination(false)
      setAutoFocusComposer(true)
    } catch (e: any) {
      setRefusal(e.message || String(e))
    }
  })

  const handleSaveConversation = (e: React.FormEvent) => {
    e.preventDefault()
    if (!saveName.trim() || !here) return
    void guarded(async () => {
      try {
        const author = await ensureAuthor()
        if (!author) return
        const name = saveName.trim()
        const sig = JSON.stringify({ action: 'renameConversation', conversation: here, author, name })
        await runWithOp(sig, (op) => store.renameConversation(here, author, name, op))
        setSaving(false)
        setSaveName('')
      } catch (err: any) {
        setRefusal(err.message || String(err))
      }
    })
  }

  const handleKeepAsConversation = () => {
    if (selected.size === 0) return
    void guarded(async () => {
      try {
        const author = await ensureAuthor()
        if (!author) return
        const posts = Array.from(selected).sort()
        const sig = JSON.stringify({ action: 'groupConversations', author, posts })
        const got = await runWithOp(sig, (op) => store.groupConversations(author, posts, undefined, op))
        store.clearSelection()
        setSelectMode(false)
        setPickingDestination(false)
        setAt({ c: got.conversation, t: null, home: false, stream: false, from: fromConv })
      } catch (err: any) {
        setRefusal(formatRefusal(err))
      }
    })
  }

  const handleConfirmInclude = (targetCid: Id) => {
    if (selected.size === 0) return
    void guarded(async () => {
      try {
        const author = await ensureAuthor()
        if (!author) return
        const add = Array.from(selected).sort()
        const sig = JSON.stringify({ action: 'modifyMembers', conversation: targetCid, author, add })
        const got = await runWithOp(sig, (op) => store.modifyMembers(targetCid, author, add, undefined, op))
        setPickingDestination(false)
        store.clearSelection()
        setSelectMode(false)
        if (got.refused && got.refused.length > 0)
          setRefusal(`Some posts could not be included: ${got.refused.map((r) => r.error ?? `Post ${r.post} refused`).join('; ')}`)
      } catch (err: any) {
        setPickingDestination(false)
        setRefusal(formatRefusal(err))
      }
    })
  }

  const handleRemoveSelected = () => {
    if (!place || selected.size === 0) return
    void guarded(async () => {
      try {
        const author = await ensureAuthor()
        if (!author) return
        const end = Array.from(selected).sort()
        const sig = JSON.stringify({ action: 'modifyMembers', conversation: place, author, end })
        const got = await runWithOp(sig, (op) => store.modifyMembers(place, author, undefined, end, op))
        store.clearSelection()
        if (got.refused && got.refused.length > 0)
          setRefusal(`Some posts could not be removed: ${got.refused.map((r) => r.error ?? `Post ${r.post} refused`).join('; ')}`)
      } catch (err: any) {
        setRefusal(formatRefusal(err))
      }
    })
  }

  const member = (id: Id, how: 'add' | 'end') => {
    if (!place) return
    void guarded(async () => {
      try {
        const author = await ensureAuthor()
        if (!author) return
        const sig = JSON.stringify({ action: 'modifyMembers', conversation: place, author, [how]: [id] })
        const got = await runWithOp(sig, (op) =>
          how === 'add' ? store.modifyMembers(place, author, [id], undefined, op) : store.modifyMembers(place, author, undefined, [id], op))
        if (got.refused && got.refused.length > 0)
          setRefusal(`Could not ${how === 'add' ? 'include' : 'remove'} post: ${got.refused.map((r) => r.error ?? `Post ${r.post} refused`).join('; ')}`)
      } catch (err: any) {
        setRefusal(formatRefusal(err))
      }
    })
  }

  /* REPLY GOES TO THE THREAD'S OWN COMPOSER (#188, #448; completion stream
     B): in the open or pinned thread that holds the post, it becomes that
     composer's target; otherwise the post's own thread slides out with its
     composer ready. The conversation's composer is never redirected, so each
     composer's line always says where its post goes. */
  const replyInThread = (id: Id) => {
    if (!place) return
    const sheet = nav.sheetOf(nav.snapshot())
    const open = sheet?.kind === 'replies' && inThread(id, sheet.root) ? sheet.root : null
    const p = pinsOf(place)
    const pinned = open ? null : [p.active, ...p.pinned].find((r) => r && inThread(id, r)) ?? null
    const root = open ?? pinned ?? id
    if (pinned) { if (sheet) nav.closeAll(); showPinned(place, pinned) }
    else if (!open) nav.openDetail({ kind: 'replies', root: id, anchor: { kind: 'post', id }, mode: 'aside' })
    setTarget(root, id)
    ask(root)
  }

  const actions: PostActions = useMemo(() => ({
    here: place,
    readIn: view === 'stream' ? STREAM : place ?? here ?? STREAM,
    selectMode,
    selected,
    toggleSelect: (id) => store.toggleSelect(id),
    startSelect: (id) => { setSelectMode(true); if (!store.isSelected(id)) store.toggleSelect(id) },
    reply: place ? replyInThread : undefined,
    goHome: handleOpenPost,
    include: place ? (id) => member(id, 'add') : undefined,
    remove: place ? (id) => member(id, 'end') : undefined,
    busy,
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [view, here, place, selectMode, selected, busy, handleOpenPost, me])

  /* -- the frame ------------------------------------------------------------ */
  const errorText = refusal ?? authorError ?? error
  const errorView = errorText && (
    <span className="fw-error fx-error" role="status">
      <span>{errorText}</span>
      <button className="fw-error-dismiss" title="Dismiss" aria-label="dismiss error"
        onClick={() => { setRefusal(null); setAuthorError(null); store.setError(null) }}>×</button>
    </span>
  )
  /* In Governance -- its page, an item, a visit under way -- Back is the one
     way out, naming where it goes. */
  const inGov = view === 'gov' || onGovPage || (view === 'conversation' && !!govVisit.current)
  const outTo = inGov ? visitFrom() : null
  const outName = outTo ? store.conversations.get(outTo.c)?.name ?? (outTo.c === fromConv ? fromConvObj?.name : null) ?? 'the conversation' : null
  const back = view === 'sources' || view === 'space'
    ? { label: 'Back', disabled: false, run: () => history.back(), returns: true }
    : inGov
    ? { label: outName ? `Back to ${outName}` : 'Back to Home', disabled: false, run: leaveGov, returns: !!outTo }
    : view === 'conversation' || (view === 'stream' && s.conversation === STREAM && s.backLabel)
    ? { label: s.backLabel ?? 'Back', disabled: !s.backLabel, run: () => nav.back(), returns: false }
    : { label: `Back to ${fromConvObj?.name || (fromConv ? 'the conversation' : 'Mentis')}`, disabled: !fromConv && !(list && list.length), run: returnToConv, returns: true }
  const title = view === 'sources' ? 'Manage Sources' : view === 'space' ? '3D Brain' : view === 'gov' ? 'Governance' : view === 'home' ? 'Home' : view === 'stream' ? 'Stream' : first ? 'Choose a conversation' : conv?.name ?? '…'
  const save = view === 'conversation' && conv?.provisional && (
    <div className="fw-save-wrap">
      <button className="fw-save fx-ctl" disabled={busy} onClick={() => setSaving((v) => !v)} aria-expanded={saving}>Save…</button>
      {saving && (
        <div className="fw-panel fw-save-panel fx-savepanel" role="dialog" aria-label="save conversation">
          <form onSubmit={handleSaveConversation}>
            <input autoFocus placeholder="Conversation name…" value={saveName} onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Escape') setSaving(false) }} />
            <div className="fw-save-actions">
              <button type="submit" className="fw-save-confirm" disabled={busy || !saveName.trim()}>Save</button>
              <button type="button" className="fw-save-cancel" onClick={() => setSaving(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )

  /* The sheet beside the conversation stays open beneath an object detail;
     the panel also stays for the threads pinned in this conversation. */
  useThreads()
  /* NARROW (frame/narrow.ts): one column, and one sheet for the rest. */
  const narrow = useNarrow()
  const pane = useSheetPane()
  /* CONVERSATION FOCUS TAKES THE ROOM (A2, a defect): the conversation is
     as wide as Focus makes it, so it draws itself wide whatever width it was
     dragged to outside Focus -- that width is not in force here, and reading
     it clamped every post to two small lines while the area stayed put. */
  const inFocus = view === 'conversation' && focused() && !narrow
  /* An object detail moved aside gives it room: a wide conversation is
     narrowed for as long as it is open, until the reader sizes it. Its AREA
     narrows; its words keep their size (A2: it once drew the clamped narrow
     column). The boundary drags from this same drawn width (nav.drawnConvPx). */
  const width = inFocus ? 'wide' : nav.squeezed(s) ? 'rail' : s.width
  const convPx = inFocus ? s.convPx : nav.drawnConvPx(s)
  /* THE ROOM THE STAGE LEAVES IT. The workspace takes what the conversation
     and the replies leave and gives way down to its least (.wk's 300px);
     past that the column shrank (boundaries.css), to a sliver. What the
     conversation can have is what it is drawn at plus what the workspace has
     beyond its least -- the same whether the column is drawn open or as the
     rail, since the workspace takes up the difference. Under READABLE it is
     drawn as the rail (nav.drawnConvPx). Not in Focus, at a narrow width or
     on Home or Governance, where nothing is shared beside it. */
  const sharing = view !== 'home' && view !== 'gov' && view !== 'sources' && view !== 'space' && !inFocus && !narrow
  useEffect(() => {
    if (!sharing) { nav.setConvRoom(null); return }
    const main = document.getElementById('main')
    if (!main) return
    const measure = () => {
      const conv = main.querySelector<HTMLElement>(':scope > .fq-col .fx-conv'), wk = main.querySelector<HTMLElement>(':scope > .wk')
      if (!conv || !wk) { nav.setConvRoom(null); return }
      nav.setConvRoom(conv.getBoundingClientRect().width + wk.getBoundingClientRect().width - WORKSPACE_LEAST)
    }
    const ro = new ResizeObserver(measure)
    ro.observe(main)
    for (const el of main.querySelectorAll(':scope > .fq-col .fx-conv, :scope > .fx-thread, :scope > .wk')) ro.observe(el)
    measure()
    return () => ro.disconnect()
  }, [sharing, view, s.conversation, first])
  /* On Home, what opens out of Home's column -- a thread, a post's details,
     About, a post full screen -- opens there, beside Home's arrangement; what
     was open in another conversation stays with it. Governance's page has
     no sheet beside it. */
  const homeReading = view === 'home' && !!homeConv && s.conversation === homeConv
  /* Over the 3D Brain the conversation opened there keeps its sheet, beside
     it in its surface (brain/BrainPlace.tsx). */
  const sheetHere = (view !== 'home' && view !== 'gov' && view !== 'sources') || homeReading
  const pinnedHere = (view === 'conversation' || homeReading) && pinsOf(place).pinned.length > 0
  const sheet = useClosing(convSheet && sheetHere ? convSheet : null)
  const sheetOpenNow = (!!convSheet && sheetHere) || pinnedHere
  const full = s.detail?.kind === 'full' && sheetHere ? s.detail : null

  /* -- what opens in the workspace is shown (#184: every detail opens visibly
     out of its anchor). Focus steps the workspace back, and objects and pages
     are drawn in it: one opened while in Focus -- a page tab, "→ This post",
     Media, Back onto an object -- leaves Focus, the reader's place kept
     (Column.tsx), rather than opening where it cannot be seen. One already
     open when Focus was entered stays behind it; Esc's order is unchanged.
     ANOTHER CONVERSATION starts on This post: that is not something opened.
     But one returned to -- Back onto its object or a page of its own -- shows
     that, and Focus is left there too (opr-1ee25895426f). */
  const shownInWorkspace = useRef({ conversation: s.conversation, detail: s.detail, page: s.page })
  useEffect(() => {
    const was = shownInWorkspace.current
    shownInWorkspace.current = { conversation: s.conversation, detail: s.detail, page: s.page }
    if (!focused() || narrow || view !== 'conversation') return
    const object = s.detail?.kind === 'object' && s.detail !== was.detail
    const page = s.conversation !== was.conversation ? s.page !== 'this-post' : s.page !== was.page
    if (object || page) setFocused(false)
  }, [s.conversation, s.detail, s.page, narrow, view])

  const handleExportSelected = async () => {
    for (const id of selected) {
      await exportTurn(id)
    }
    store.clearSelection()
    setSelectMode(false)
  }

  const selection = (selectMode || pickingDestination) && (
    <SelectionBar selected={selected} busy={busy} here={place}
      onKeep={handleKeepAsConversation} onInclude={() => selected.size && setPickingDestination(true)}
      onRemove={place ? handleRemoveSelected : undefined}
      onExport={handleExportSelected}
      onCancel={() => { store.clearSelection(); setSelectMode(false); setPickingDestination(false) }}
      picking={pickingDestination} onCancelPick={() => setPickingDestination(false)} onConfirmInclude={handleConfirmInclude} />
  )

  return (
    <Actions.Provider value={actions}>
    <GovContext.Provider value={govNav}>
      <div className={'fw-shell fx' + (view === 'gov' || onGovPage ? ' fg-on' : '') + (onGovPage ? ' fg-item-on' : '')} data-scheme={scheme}>
        {govMounted && <GovFollow on={govOnScreen} />}
        <TopBar brain={brain} brainInfo={brainInfo} view={view} title={title} first={first && view === 'conversation'} back={back} extra={save} error={errorView}
          here={here} busy={busy} onHome={openHome} onNew={() => void handleNewConversation()} onOpenPost={handleOpenPost} onPick={pick}
          onManage={() => { setGovFocus(null); openGov() }} onSources={() => openSources('')} onSpace={openSpace} />
        {view === 'space' ? (
          <main className="fx-main fx-space-main" id="main">
            <Suspense fallback={<p className="fx-none fx-faint" aria-busy="true">Reading the Brain…</p>}>
              <BrainPlace doors={{ openPost: handleOpenPost, openConversation: pick }}
                conversation={{
                  id: here, name: conv?.name ?? null, show: showOverBrain,
                  /* THE REAL CONVERSATION, drawn once and moved into the
                     Brain's surface (focus/hosts.tsx), as a float shows it. */
                  column: () => here && (
                    <Hosted id={CONVERSATION_ID}>
                      <ConversationColumn id={here} name={conv?.name ?? ''} width="wide" replyTo={replyTo} setReplyTo={setReplyTo}
                        autoFocusComposer={autoFocusComposer} onAutoFocused={() => setAutoFocusComposer(false)} selection={selection} />
                    </Hosted>
                  ),
                  thread: sheetOpenNow && here ? <ThreadPanel here={here} sheet={sheet} /> : null,
                }} />
            </Suspense>
          </main>
        ) : view === 'sources' ? (
          <main className="fx-main fx-sources-main" id="main">
            <SourcesSurface path={sourcesPath ?? ''} me={me}
              nameOf={(id) => id ? [...store.posts.values()].find((p) => p.author === id)?.author_name ?? id : 'unknown'}
              onGo={openSources} onChanged={() => { void store.loadList() }} />
          </main>
        ) : view === 'home' ? (
          <main className={'fx-main fx-home-main' + (sheetOpenNow ? ' fx-thread-open' : '')}
            style={{ ['--tw' as string]: Math.min(s.threadPx, 480) + 'px' }}>
            <section className="fx-home-panel">
              <Home onOpenPost={handleOpenPost} onOpenGovernance={() => { setGovFocus(null); openGov() }}
                conversation={({ px, tools, railTools, widen, across }) => <HomeColumn px={px} tools={tools} railTools={railTools} widen={widen} across={across} selection={selection} onOpen={pick} />} />
            </section>
            {sheetOpenNow && (
              <section className="fx-thread fx-panel fx-home-thread" id="thread">
                <div className="fx-thread-inner">
                  <ThreadPanel here={place} sheet={sheet} />
                </div>
              </section>
            )}
          </main>
        ) : view === 'gov' ? (
          <main className="fx-main fg-main" id="main" style={{ ['--cw' as string]: WIDTHS[width === 'rail' ? 'narrow' : width] + 'px' }}>
            <GovPage section={addr.s ?? 'start'} onSection={(sec) => { keepSection(sec); setAt((p) => ({ ...p, s: sec })) }}
              focus={govFocus} onFocus={setGovFocus} card={govCard} onCard={setGovCard} onOpenPost={handleOpenPost} />
          </main>
        ) : (
          <main className={'fx-main' + (sheetOpenNow ? ' fx-thread-open' : '') + (inFocus ? ' fx-focus' : '') + (onGovPage ? ' fg-item-open' : '')} id="main"
            data-width={width} data-narrow={narrow ? '' : undefined} data-sheet={narrow && pane ? pane : undefined}
            style={{ ['--cw' as string]: convPx + 'px', ['--tw' as string]: s.threadPx + 'px' }}>
            {narrow && pane && <NarrowHead here={view === 'conversation' ? here : null} threadOpen={!!convSheet || pinnedHere} />}
            {narrow && !pane && !first && <NarrowOpen threadOpen={!!convSheet || pinnedHere} />}
            {view === 'stream'
              ? <StreamColumn width={width} selection={selection} />
              : first || !here
                ? <Welcome width={width} />
                : <>
                    {/* Drawn once and moved to whichever place shows it
                        (focus/hosts.tsx): the column, a section or a float. */}
                    <Hosted id={CONVERSATION_ID}>
                      <ConversationColumn id={here} name={conv?.name ?? ''} width={width} replyTo={replyTo} setReplyTo={setReplyTo}
                        autoFocusComposer={autoFocusComposer} onAutoFocused={() => setAutoFocusComposer(false)} selection={selection} />
                    </Hosted>
                    <ColumnPlace width={width} />
                  </>}
            {/* In Focus there is nothing beside the conversation to share
                room with until its replies are open. */}
            {(!inFocus || sheetOpenNow) && <Boundary which="conversation" focus={inFocus} />}
            <section className="fx-thread fx-panel" id="thread" aria-hidden={!sheetOpenNow}>
              <div className="fx-thread-inner">
                <ThreadPanel here={view === 'conversation' ? here : null} sheet={sheet} />
              </div>
            </section>
            {sheetOpenNow && <Boundary which="replies" focus={inFocus} />}
            <WorkspaceSlot />
            {/* Fluid Focus: surfaces floating over the conversation and its
                workspace, and where a drag can land (focus/). */}
            {view === 'conversation' && !narrow && <Floats />}
          </main>
        )}
        {full && <Full d={full} />}
        <Switcher current={here} first={first} view={view === 'sources' || view === 'space' ? 'home' : view} busy={busy} onPick={pick} onHome={openHome} onStream={openStream}
          onGovernance={() => { setGovFocus(null); openGov() }} onNew={() => void handleNewConversation()} />
        <ToastView />
        {/* Results and requests for you from elsewhere (D2; frame/notifications.ts). */}
        <Notices me={me} here={view === 'conversation' ? here : null}
          onOpen={(n) => (n.turn ? handleOpenPost(n.conversation, n.turn) : pick(n.conversation))} />
        <MediaViewerHost />
        <FocusView />
        {view === 'conversation' && !narrow && <DockLayer />}
        <div id="fx-layer"><Layer /></div>
      </div>
    </GovContext.Provider>
    </Actions.Provider>
  )
}

/** The conversation's placements, once read. */
const useConversationItems = (c: Id | null) => useCollection('conversation:' + (c ?? ''))
