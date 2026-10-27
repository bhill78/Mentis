/* THE BAR'S RIGHT END AND ITS MARK (#190 header; #188 shell "⌕ ☆ ◐ ⋯";
 * #181 "search, notifications and look folded into its right end"; #442
 * area 5: the Mentis main-menu hover).
 *
 * Quiet at rest: each control is a mark, named on hover and to a screen
 * reader, and each opens a choice sheet anchored under it (frame/Sheet).
 *
 *   the mark   production's Brain menu (surfaces/BrandMenu), on hover or press
 *   Search     the record's own search (search.ts, `/api/references`): a turn
 *              opens at its post, a conversation opens; nothing invented
 *   Notifications  what waits on you, ONE ENTRY PER FORM (P11: each open
 *              decision form and each block waiting for your input, counted
 *              "2 decisions, 1 input", opening the asking post at the form),
 *              what is working, and what Classic last told you
 *   Look       light / dark / the system's, and the atmosphere, for this
 *              conversation or the whole Brain
 *   (chat)     a slot kept first in the right end for the conversation's
 *              chat mark and unread count (A7), filled with `<BarChat>` */

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { ago, CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import { Prose } from '../../prose'
import { excerpt, footing, groups, isTurn, pendingNote, useSearch, type Hit } from '../../search'
import BrandMenu from '../../surfaces/BrandMenu'
import { classicHref } from '../../shellSwitch'
import { store, type Id } from '../store'
import { useList } from '../conversation/hooks'
import { trace } from '../workspace/from'
import { LookBody, LookMaker } from './LookSheet'
import { bellOpen, useKept } from './notifications'
import { Who } from '../identity/Who'
import { itemLine, itemWords, landOn, type NeedsItem, type NeedsItems } from '../../needsItems'
import { closeSheet, openSheet, Sheet, useOpenSheet, useSheetEscape } from './Sheet'
import CapacityControl from './CapacityControl'
import './bar.css'

export const SEARCH = 'search'
export const ACTIVITY = 'notifications'
export const LOOK = 'look'
export const FOLD = 'more'

/* -- marks ---------------------------------------------------------------- */

const I = ({ children }: { children: ReactNode }) => (
  <svg className="fb-icon" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor"
    strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
)
export const HomeMark = () => <I><circle cx="10" cy="10" r="7" /><circle cx="10" cy="10" r="2.6" /></I>
const PlusMark = () => <I><path d="M10 4v12M4 10h12" /></I>
const SearchMark = () => <I><circle cx="8.5" cy="8.5" r="5" /><path d="M12.5 12.5L17 17" /></I>
const BellMark = () => <I><path d="M5 14V9a5 5 0 0 1 10 0v5l1.5 1.5h-13z" /><path d="M8.5 17.5a1.6 1.6 0 0 0 3 0" /></I>
const LookMark = () => <I><circle cx="10" cy="10" r="7" /><path d="M10 3a7 7 0 0 0 0 14z" fill="currentColor" stroke="none" /></I>
const MoreMark = () => <I><circle cx="4.5" cy="10" r="1.2" fill="currentColor" /><circle cx="10" cy="10" r="1.2" fill="currentColor" /><circle cx="15.5" cy="10" r="1.2" fill="currentColor" /></I>
/** Arrange, as a mark, where the bar is too narrow for its word. */
export const ArrangeMark = () => <I><rect x="3" y="4" width="14" height="12" rx="1.5" /><path d="M10 4v12M10 10h7" /></I>

/** A quiet control: the mark, its name shown on hover / focus (and always
 *  to a screen reader), the sheet it opens anchored under it. */
function Ctl({ id, label, mark, badge, onOpen, current, className }: {
  id?: string; label: string; mark: ReactNode; badge?: ReactNode; onOpen: (el: HTMLElement) => void; current?: boolean; className?: string
}) {
  const open = useOpenSheet()
  return (
    <button className={'fb-ctl' + (className ? ' ' + className : '')} aria-label={label}
      aria-expanded={id ? open?.id === id : undefined} aria-current={current || undefined} data-ctl={id ?? label.toLowerCase()}
      onClick={(e) => onOpen(e.currentTarget)}>
      {mark}<span className="fb-name">{label}</span>{badge}
    </button>
  )
}

/* -- the mark: production's Brain menu ------------------------------------ */

export function Brand({ brain, atHome, onHome, onManage, conversation = null }: { brain: { name: string | null; whyNot?: string | null; path?: string | null }; atHome: boolean; onHome: () => void; onManage?: () => void; conversation?: Id | null }) {
  /* Each row leaves for its place in Classic, as Classic (the way out) does; Brain home is
     this page's own Home (#190: Home is opened from the Mentis mark), and
     Manage Brain this page's own Governance where the page has one -- so
     its way out leads back here. */
  const go = (hash: string) => () => { location.assign('/' + hash) }
  return (
    <span className="fb-brand">
      <BrandMenu name={brain.name} whyNot={brain.whyNot} path={brain.path} atBrain={atHome}
        onBrainHome={onHome} onManage={onManage ?? go('#/gov/standing')} onSources={go('#/brain/sources')} onSpace={go('#/brain/space')}
        switchTo={{ name: 'Classic', run: () => location.assign(classicHref(conversation)) }} />
    </span>
  )
}

/* -- Home and New: two actions, always in the bar (#190) ------------------- */

export function HomeAndNew({ atHome, onHome, onNew, busy }: { atHome: boolean; onHome: () => void; onNew: () => void; busy: boolean }) {
  return (
    <>
      <button className={'fb-ctl fb-home fw-home-link' + (atHome ? ' on' : '')} aria-label="Home"
        aria-current={atHome ? 'page' : undefined} data-ctl="home" onClick={onHome}><HomeMark /><span className="fb-name">Home</span></button>
      <button className="fb-ctl fb-new fw-new-conv" aria-label="New conversation"
        data-ctl="new" disabled={busy} onClick={onNew}><PlusMark /><span className="fb-name">New conversation</span></button>
    </>
  )
}

/* -- the chat slot (A7) ---------------------------------------------------- */

/* KEPT FOR THE CONVERSATION'S CHAT MARK AND ITS UNREAD COUNT (A7, D3). The
   bar keeps its place, first in the right end before Search; whoever draws
   the mark renders `<BarChat>` wherever it lives, and the bar shows what it
   holds there. Nothing is drawn, and no room taken, while nobody fills it. */
let chat: ReactNode = null
const chatHeard = new Set<() => void>()
const useChat = () => useSyncExternalStore((fn) => { chatHeard.add(fn); return () => { chatHeard.delete(fn) } }, () => chat)

/** Put `children` in the bar's chat slot for as long as this is mounted. */
export function BarChat({ children }: { children: ReactNode }) {
  useEffect(() => {
    chat = children
    chatHeard.forEach((fn) => fn())
  }, [children])
  useEffect(() => () => { chat = null; chatHeard.forEach((fn) => fn()) }, [])
  return null
}

/* -- what needs you, item by item (P11) ----------------------------------- */

/** The bell's items, read once and then as Needs you moves. */
function useNeedsItems(): NeedsItems | null {
  const sub = useCallback((fn: () => void) => store.subscribe('needs-items', fn), [])
  const got = useSyncExternalStore(sub, () => store.needsItems)
  useEffect(() => { if (store.needsItems === null) void store.loadNeedsItems().catch(() => {}) }, [])
  return got
}

/** Open the asking post, then land on its form there. */
export function openItem(it: NeedsItem, onOpenPost: (c: Id, p: Id) => void, here: Id | null) {
  if (!it.post) return
  openTurn(it.conversation, it.post, onOpenPost, here)
  void landOn(it)
}

/* -- the right end -------------------------------------------------------- */

export function BarEnd({ conversation, onOpenPost, onPick }: {
  conversation: Id | null
  onOpenPost: (conversation: Id, post: Id) => void
  onPick: (conversation: Id) => void
}) {
  /* THE COUNT IS OPEN FORMS AND INPUTS, NOT CONVERSATIONS (P11): one per
     decision form, one per block waiting for input, said by kind. */
  const needs = useNeedsItems()
  const waiting = needs?.counts?.total ?? 0
  const words = itemWords(needs?.counts ?? null)
  /* Toasts offered since the bell was last opened: a quiet dot, not a count
     (the count is what waits on you). */
  const unseen = useKept().filter((n) => n.unseen).length
  const bellBadge = waiting > 0 ? <span className="fb-badge" data-needs-count={waiting} aria-label={`${words} waiting on you`} title={`${words} waiting on you`}>{waiting}</span>
    : unseen > 0 ? <span className="fb-unseen" aria-label={`${unseen} new`} /> : null
  const chatMark = useChat()
  /* "/" opens search, as it does in many places; never while typing. */
  const searchBtn = useRef<HTMLSpanElement | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return
      if (t && (t.matches?.('input, textarea, select') || t.isContentEditable)) return
      const b = searchBtn.current?.querySelector('button')
      if (!b) return
      e.preventDefault()
      openSheet(SEARCH, b, 'end')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  return (
    <span className="fb-end">
      <CapacityControl />
      {chatMark && <span className="fb-wrap fb-chat" data-slot="chat">{chatMark}</span>}
      <span ref={searchBtn} className="fb-wrap">
        <Ctl id={SEARCH} label="Search" mark={<SearchMark />} onOpen={(el) => openSheet(SEARCH, el, 'end')} />
      </span>
      <Ctl id={ACTIVITY} label="Notifications" mark={<BellMark />} onOpen={(el) => openSheet(ACTIVITY, el, 'end')} badge={bellBadge} />
      <Ctl id={LOOK} label="Look" mark={<LookMark />} onOpen={(el) => openSheet(LOOK, el, 'end')} />
      {/* NARROW (#568 6): Notifications, Look and Classic fold into this one
          mark; the bar shows it only below 600px (bar.css). */}
      <Ctl id={FOLD} label="More" className="fb-fold" mark={<MoreMark />} onOpen={(el) => openSheet(FOLD, el, 'end')} badge={bellBadge} />
      <Sheet id={SEARCH} label="search" className="fb-sheet fb-search"><SearchBody here={conversation} onOpenPost={onOpenPost} onPick={onPick} /></Sheet>
      <Sheet id={ACTIVITY} label="notifications" className="fb-sheet fb-activity"><ActivityBody here={conversation} onPick={onPick} onOpenPost={onOpenPost} /></Sheet>
      <Sheet id={LOOK} label="look" className="fb-sheet fb-look"><LookBody /></Sheet>
      <Sheet id={FOLD} label="more" className="fb-sheet fb-foldsheet"><FoldBody waiting={waiting} words={words} conversation={conversation} /></Sheet>
      <LookMaker />
    </span>
  )
}

/** The folded right end: each row opens its own sheet under the same mark. */
function FoldBody({ waiting, words, conversation }: { waiting: number; words: string; conversation: Id | null }) {
  const at = () => document.querySelector<HTMLElement>(`.fx-bar [data-ctl='${FOLD}']`)
  const open = (id: string) => () => { const el = at(); if (el) openSheet(id, el, 'end') }
  return (
    <>
      <button className="fx-row" data-fold="notifications" onClick={open(ACTIVITY)}>
        <span>Notifications</span>{waiting > 0 && <small>{words} waiting on you</small>}
      </button>
      <button className="fx-row" data-fold="look" onClick={open(LOOK)}><span>Look</span></button>
      <a className="fx-row" data-fold="exit" href={classicHref(conversation)}><span>Switch to Classic</span></a>
    </>
  )
}

/* -- search --------------------------------------------------------------- */

/** A turn found in this conversation is read where it is, a reply inside its
 *  thread -- the same step "from #N" takes, so one Back returns. One in
 *  ANOTHER conversation is opened by its address, as a link to it is: read
 *  in context there, its header in view, the address naming it
 *  (opr-1dc1f4d4ed5a: traced, it was "Reading #187" with the column left at
 *  the newest posts). Unreadable, it is opened by address too. */
function openTurn(conversation: Id | null | undefined, id: Id, byAddress: (c: Id, p: Id) => void, here: Id | null) {
  const fall = () => { const c = conversation ?? store.posts.get(id)?.home; if (c) byAddress(c, id) }
  /* From Home or the Stream there is no conversation on screen: by address. */
  const go = () => {
    const post = store.posts.get(id)
    if (here && post && (conversation ?? post.home) === here) trace(id); else fall()
  }
  if (store.posts.has(id)) go()
  else void store.loadPosts([id]).then(go, fall)
}

function SearchBody({ here, onOpenPost, onPick }: { here: Id | null; onOpenPost: (c: Id, p: Id) => void; onPick: (c: Id) => void }) {
  const [q, setQ] = useState('')
  const input = useRef<HTMLInputElement | null>(null)
  useEffect(() => { const t = setTimeout(() => input.current?.focus(), 30); return () => clearTimeout(t) }, [])
  const { session, loading, more, error, asked, typed, loadMore } = useSearch(q, here)
  const nameOf = (id: Id) => store.conversations.get(id)?.name ?? null
  const convs = (session?.rows ?? []).filter((h) => h.what === 'conversation')
  const grouped = session ? groups(session, nameOf) : []
  const others = (session?.rows ?? []).filter((h) => !isTurn(h) && h.what !== 'conversation')
  /* The rows a key can reach, in the order they are drawn. */
  const rows: { hit: Hit; go: () => void }[] = useMemo(() => [
    ...convs.map((h) => ({ hit: h, go: () => onPick(h.ref) })),
    ...grouped.flatMap((g) => g.turns.map((h) => ({ hit: h, go: () => openTurn(h.conversation, h.ref, onOpenPost, here) }))),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [session])
  /* THE SELECTION IS A ROW, NOT A POSITION (production's SearchResults):
     More results adds rows below and never moves it; a new question starts
     it, and any preview, afresh. */
  const [atRef, setAtRef] = useState<string | null>(null)
  const [preview, setPreview] = useState<Hit | null>(null)
  useEffect(() => { setAtRef(null); setPreview(null) }, [asked])
  const at = Math.max(0, rows.findIndex((r) => r.hit.ref === atRef))
  const move = (by: number) => {
    if (!rows.length) return
    const next = rows[Math.min(rows.length - 1, Math.max(0, at + by))]
    setAtRef(next.hit.ref)
    requestAnimationFrame(() => document.querySelector(`.fb-results [data-ref="${CSS.escape(next.hit.ref)}"]`)?.scrollIntoView({ block: 'nearest' }))
  }
  const pick = (r: { go: () => void } | undefined) => { if (!r) return; closeSheet(); r.go() }
  /* PREVIEW BEFORE GOING (#568 1.3; production FE #311): Alt+Enter, or a
     row's ◫, shows the whole of what was found beside the results without
     leaving them -- the words, the selection and the list's scroll stay as
     they were. The first Esc closes the preview; the next, the search. */
  const peek = (h: Hit) => { setAtRef(h.ref); setPreview((p) => (p?.ref === h.ref ? null : h)) }
  const closePreview = useCallback(() => { if (!preview) return false; setPreview(null); input.current?.focus(); return true }, [preview])
  useSheetEscape(preview ? closePreview : null)
  const fresh = !!typed && typed === asked
  const pending = pendingNote(session?.last.pending)
  let i = -1
  const peekBtn = (h: Hit) => (
    <span className="fb-peek" role="button" tabIndex={-1} aria-label="Preview (Alt+Enter)" title="Preview (Alt+Enter)" aria-pressed={preview?.ref === h.ref}
      onClick={(e) => { e.stopPropagation(); peek(h) }}>◫</span>
  )
  return (
    <div className={'fb-searchbody' + (preview ? ' previewing' : '')}>
      <input ref={input} type="search" placeholder="Search Mentis: words, a turn number, or an ent- reference" aria-label="Search Mentis"
        value={q} onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); move(1) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
          else if (e.key === 'Enter' && fresh && !e.nativeEvent.isComposing) {
            e.preventDefault()
            // Alt+Enter previews, as it does in production's search
            if (e.altKey) { const r = rows[at]; if (r) peek(r.hit) } else pick(rows[at])
          }
        }} />
      {q.trim().length > 0 && q.trim().length < 2 && <p className="fx-none fx-faint">Type at least two characters.</p>}
      {(loading || (typed && typed !== asked)) && !session && <p className="fx-none fx-faint" aria-busy="true">Searching…</p>}
      {error && <p className="fx-none fb-err" role="alert">{error.kind === 'more' ? 'Could not load more' : 'Search failed'}: {error.message}</p>}
      {session && (
        <div className="fb-split">
          <div className="fb-results" aria-busy={loading || undefined}>
            <p className="fx-none fx-faint fb-foot">{footing(session)}{loading ? ' · searching…' : ''}</p>
            {pending && <p className="fx-none fx-faint">{pending}</p>}
            {convs.length > 0 && <div className="fx-sec">Conversations</div>}
            {convs.map((h) => {
              i++
              const k = i
              return (
                <button key={h.ref} className={'fx-row fb-hit' + (k === at ? ' on' : '') + (preview?.ref === h.ref ? ' previewed' : '')} data-hit="conversation" data-ref={h.ref}
                  onMouseEnter={() => setAtRef(h.ref)} onClick={() => pick(rows[k])}>
                  <span>{h.name ?? nameOf(h.ref) ?? h.ref}</span><small>open</small>{peekBtn(h)}
                </button>
              )
            })}
            {grouped.map((g) => (
              <div key={g.conversation} className="fb-group">
                <div className="fx-sec">{g.name} <span className="fb-n">{g.turns.length}{g.exact ? '' : '+'}</span></div>
                {g.turns.map((h) => {
                  i++
                  const k = i
                  const ex = excerpt(h.said ?? h.name ?? '', session.q, 140)
                  return (
                    <button key={h.ref} className={'fx-row fb-hit fb-turn' + (k === at ? ' on' : '') + (preview?.ref === h.ref ? ' previewed' : '')} data-hit="turn" data-ref={h.ref}
                      onMouseEnter={() => setAtRef(h.ref)} onClick={() => pick(rows[k])}>
                      <span className="fb-num">{h.number != null ? `#${h.number}` : ''}</span>
                      <span className="fb-ex">{ex.before}<mark>{ex.hit}</mark>{ex.after}</span>{peekBtn(h)}
                    </button>
                  )
                })}
              </div>
            ))}
            {others.length > 0 && (
              <p className="fx-none fx-faint">
                Also {others.length} {others.length === 1 ? 'topic, person or link' : 'topics, people and links'}: <a href="/" className="fb-link">find them in Classic ↗</a>
              </p>
            )}
            {session.rows.length === 0 && <p className="fx-none fx-faint">Nothing matches “{session.q}”.</p>}
            {!session.done && (
              <button className="fx-row fb-more" disabled={more} onClick={loadMore}><span>{more ? 'Loading…' : 'More results'}</span></button>
            )}
          </div>
          {/* Keyed by the reference: a preview never shows another row's read
              while its own is still out. */}
          {preview && (
            <SearchPreview key={preview.ref} hit={preview} q={session.q} nameOf={nameOf}
              onOpen={() => pick(rows.find((r) => r.hit.ref === preview.ref))} onClose={closePreview} />
          )}
        </div>
      )}
    </div>
  )
}

/** What `/api/references?ref=` says about one reference (production's
 *  SearchResults reads the same). */
interface Resolved {
  known: boolean
  why_not?: string
  reason?: string
  recorded_at?: number
  author_alias?: string | null
  said?: string
  name?: string
  alias?: string
  about?: string
  turns?: number
  participants?: { participant: Id; alias: string | null }[]
}

/** THE PREVIEW: the whole of what was found, without leaving the search. */
function SearchPreview({ hit, q, nameOf, onOpen, onClose }: { hit: Hit; q: string; nameOf: (id: Id) => string | null; onOpen: () => void; onClose: () => void }) {
  const [got, setGot] = useState<Resolved | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    fluidFetch(`/api/references?ref=${encodeURIComponent(hit.ref)}`, { headers: { ...CLIENT_HEADERS } })
      .then(async (r) => { if (!r.ok) throw new Error(`${r.status}`); return r.json() as Promise<Resolved> })
      .then((d) => { if (live) setGot(d) }, (e: Error) => { if (live) setFailed(e.message) })
    return () => { live = false }
  }, [hit.ref])
  const turn = isTurn(hit)
  const conv = hit.conversation_name || (hit.conversation ? nameOf(hit.conversation) : null)
  /* UNKNOWN IS AN ANSWER: nothing to open, and the excerpt the search gave
     is said to be only that. */
  const gone = got?.known === false ? got : null
  const read = got && !gone ? got : null
  return (
    <aside className="fb-preview" aria-label="Preview" data-ref={hit.ref}>
      <div className="fb-pv-head">
        <button className="fb-pv-back" onClick={onClose}>‹ Results</button>
        <span className="fb-pv-where">{conv}{turn && hit.number != null && <b> #{hit.number}</b>}</span>
        <button className="fb-pv-open" disabled={!!gone} onClick={onOpen}>Open ↵</button>
      </div>
      <div className="fb-pv-body">
        {!got && !failed && <p className="fx-none fx-faint">Reading…</p>}
        {failed && <p className="fx-none fb-err">Could not read it: {failed}</p>}
        {gone && (
          <p className="fx-none fb-err">Unavailable: the record does not hold this now ({gone.why_not ?? gone.reason ?? 'no such entry'}).
            {(hit.said || hit.name) && <span className="fx-faint"> The search said: “{hit.said || hit.name}”</span>}</p>
        )}
        {read && turn && (
          <>
            <p className="fb-pv-meta">
              {read.author_alias && <span className="fb-pv-who">{read.author_alias}</span>}
              {read.recorded_at && <span>{new Date(read.recorded_at * 1000).toLocaleString()}</span>}
            </p>
            <div className="fb-pv-text turn-body"><Prose src={read.said ?? hit.said ?? ''} scope={`fluid-search-preview/${hit.ref}`} /></div>
          </>
        )}
        {read && !turn && (
          <>
            <h4 className="fb-pv-title">{read.name ?? read.alias ?? hit.name ?? hit.ref}</h4>
            {read.about && <p className="fb-pv-about">{read.about}</p>}
            <p className="fb-pv-meta">
              {read.turns != null && <span>{read.turns} {read.turns === 1 ? 'post' : 'posts'}</span>}
              {read.participants && read.participants.length > 0 && <span>{read.participants.map((p) => p.alias ?? p.participant).join(', ')}</span>}
            </p>
          </>
        )}
      </div>
      <p className="fb-pv-keys">{gone ? 'nothing to open' : 'Enter opens'} · Esc closes the preview · “{q}”</p>
    </aside>
  )
}

/* -- activity ------------------------------------------------------------- */

function ActivityBody({ here, onPick, onOpenPost }: { here: Id | null; onPick: (c: Id) => void; onOpenPost: (c: Id, p: Id) => void }) {
  const list = useList()
  useEffect(() => { void store.loadList() }, [])
  /* What waits on you, read afresh each time the bell opens. */
  const items = useNeedsItems()
  useEffect(() => { void store.loadNeedsItems().catch(() => {}) }, [])
  /* What was offered as a toast, here or in Classic: one history per Brain
     on this device (notifications.ts). Opening the bell sees it. */
  const notes = useKept().slice(0, 8)
  useEffect(() => { bellOpen(true); return () => bellOpen(false) }, [])
  const all = (list ?? []).filter((c) => c.id !== 'home')
  const working = all.filter((c) => c.working > 0 && !(c.needs_you ?? 0))
  const go = (fn: () => void) => () => { closeSheet(); fn() }
  const words = itemWords(items?.counts ?? null)
  return (
    <>
      <div className="fx-sec" data-needs-words={words || undefined}>Waiting on you{words ? <span className="fb-n"> · {words}</span> : null}</div>
      {items?.unknown && <p className="fx-none fx-faint">Unknown: this brain names no owner, so what waits on you can't be read.</p>}
      {items && !items.unknown && items.items.length === 0 && <p className="fx-none fx-faint">Nothing is waiting on you.</p>}
      {!items && <p className="fx-none fx-faint" aria-busy="true">Reading…</p>}
      {(items?.items ?? []).map((it) => {
        const { kind, what } = itemLine(it)
        const where = `${it.conversation_name ?? 'a conversation'}${it.post_number != null ? ` · #${it.post_number}` : ''}`
        return (
          <button key={it.key} className="fx-row fb-hit fb-item" data-act="needs" data-item={it.key} data-kind={it.kind}
            disabled={!it.post} title={it.post ? `Opens ${where} at the form. Records nothing.` : 'Not on a post yet'}
            onClick={go(() => openItem(it, onOpenPost, here))}>
            <span className="fb-item-line">
              <span className="fb-dot needs" aria-hidden="true" />
              <span className="fb-item-body">
                <span className="fb-item-what"><b className="fb-item-kind">{kind}</b> {what}</span>
                <small className="fb-where">{where}</small>
              </span>
            </span>
            {it.at != null && <small>{ago(it.at)}</small>}
          </button>
        )
      })}
      <div className="fx-sec">Working now</div>
      {working.length === 0 && <p className="fx-none fx-faint">Nobody is working.</p>}
      {working.map((c) => (
        <button key={c.id} className="fx-row fb-hit" data-act="working" onClick={go(() => onPick(c.id))}>
          <span><span className="fb-dot live" aria-hidden="true" />{c.name}</span>
          <small>{c.working} working</small>
        </button>
      ))}
      {notes.length > 0 && (
        <>
          <div className="fx-sec">Recently</div>
          {notes.map((n) => (
            <button key={n.key} className={'fx-row fb-hit fb-note' + (n.unseen ? ' unseen' : '')} data-kind={n.kind}
              onClick={go(() => (n.turn ? openTurn(n.conversation, n.turn, onOpenPost, here) : onPick(n.conversation)))}>
              <span className="fb-note-line">
                {n.actor && n.actorAlias && <Who id={n.actor} name={n.actorAlias} show="avatar" size={18} />}
                <span>{n.headline}<small className="fb-where"> · {n.convName || n.where}</small></span>
              </span>
              <small>{ago(n.at / 1000)}</small>
            </button>
          ))}
        </>
      )}
    </>
  )
}
