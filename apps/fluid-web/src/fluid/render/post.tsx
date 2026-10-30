/* WHAT A POST IS DRAWN AS, wherever it is placed.
 *
 * A post -- or a reply -- is drawn the same way in the conversation column,
 * in the thread beside it (its root and its replies), on Home's conversation
 * column and full screen: its identity line (face, @author, time, #N), its
 * words through the Markdown renderer, what it carries, its decisions, its
 * action chips, on-stage mark and annotations. WHERE it is placed -- the
 * card's own element, reading it on a click, scrolling it into view, its
 * selection, a tall post's row -- belongs to the place (conversation/
 * PostCard.tsx, Sheets.tsx, Full.tsx), not to this module.
 *
 * `context` says which place asks, and so how dense it is drawn:
 *   post   a card in a conversation column (its head is the drag handle)
 *   reply  a reply in a thread: its words a step smaller
 *   root   the post a thread answers, at the thread's head
 *   full   a post full screen: its whole text, every attachment, the full time
 * Everything here was lifted from PostCard.tsx and Full.tsx as it was; the
 * DOM, its classes and what each place shows are unchanged. */

import { createContext, useCallback, useContext, useRef, useState, type HTMLAttributes, type ReactNode, type RefObject } from 'react'
import { ago, exportTurn } from '../../api'
import { Prose } from '../../prose'
import { turnPartScope } from '../../experimental/renderable'
import { BlockGripContext } from '../../experimental/renderable'
import { gripsFor, TextGrips } from '../conversation/Grip'
import { namesFor } from '../../experimental/objects'
import * as nav from '../nav'
import { store, type Id, type Placement, type Post } from '../store'
import { useAfterReads } from '../conversation/hooks'
import { Who } from '../identity/Who'
import { closeSheet, openSheet, Sheet, useOpenSheet } from '../frame/Sheet'
import { AddressPop, Addressees, addressSheet } from '../conversation/Addressing'
import { bare, inlinePart, said, textOf } from '../conversation/text'
import { aliasOf, workKey, type Working } from '../conversation/working'
import { OnStageTag } from '../workspace/origin'
import Annotations, { Annotate } from '../conversation/Annotations'
import PostDecisions from '../conversation/Decisions'
import { formatPillText, useWorkByTurn } from '../../surfaces/WorkPill'
import type { WorkItem } from '../../work/contract'
import WorkDrawer, { claimDrawer, releaseDrawer } from '../../work/WorkDrawer'
import { ObjectRefs } from './ObjectRefPart'
import { ObjectActions } from '../objects/ObjectActions'

/** Which place a post is drawn in. */
export type PostContext = 'post' | 'reply' | 'root' | 'full'

/** What a card can do besides being read, provided by the shell. */
export interface PostActions {
  /** the conversation shown, or null in the Stream */
  here: Id | null
  /** what `nav.read` is told the post is read in: the conversation, or 'stream' */
  readIn: Id
  selectMode: boolean
  selected: Set<Id>
  toggleSelect: (id: Id) => void
  startSelect: (id: Id) => void
  reply?: (id: Id) => void
  goHome: (conversation: Id, post: Id) => void
  include?: (id: Id) => void
  remove?: (id: Id) => void
  busy: boolean
}
export const Actions = createContext<PostActions | null>(null)
export const useActions = () => useContext(Actions)!

/* -- the identity line ------------------------------------------------------ */

/** Where a post lives: its number, and its home's name when that is elsewhere. */
export function Where({ post, here }: { post: Post; here: Id | null }) {
  const a = useActions()
  const away = post.home !== here
  const convName = post.home_name || (post.home ? store.conversations.get(post.home)?.name : null)
  const content = (
    <>
      {away && convName ? <span className="fw-where-home">{convName} · </span> : ''}
      {post.number != null && <span className="fw-num">#{post.number}</span>}
    </>
  )
  if (!post.home) return <span className="fw-where fx-num">{content}</span>
  return (
    <a className="fw-where fx-num" href={a.selectMode ? undefined : `/fluid?c=${encodeURIComponent(post.home)}&t=${encodeURIComponent(post.id)}`}
      title={a.selectMode ? undefined : convName ? `Go to ${convName}` : 'Go to conversation'}
      onClick={(e) => {
        e.stopPropagation()
        if (a.selectMode) { e.preventDefault(); a.toggleSelect(post.id); return }
        if (!e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); a.goHome(post.home!, post.id) }
      }}>
      {content}
    </a>
  )
}

/** When it was written, as a post says it: how long ago, the full time on
 *  hover. A reply says it the same way wherever it is drawn (A9). Full
 *  screen says it once, in full. */
export function When({ at, full }: { at: number; full?: boolean }) {
  const d = new Date(at * 1000)
  if (full) return <time className="fx-when" dateTime={d.toISOString()}>{d.toLocaleString()}</time>
  return <time className="fw-time fx-when" dateTime={d.toISOString()} title={d.toLocaleString()}>{ago(at)}</time>
}

/** The select-mode checkbox in a post's head. */
export interface Check { checked: boolean; toggle: () => void; label: string }

/** A POST'S IDENTITY LINE: the checkbox while selecting, the author, when
 *  (and edited), what the place says beside it (`meta`), and where it lives.
 *  A card's head is a `header` whose time and meta are one `.fx-stamp` (in a
 *  narrow column, the line under the face); elsewhere it is a plain row. */
export function PostHead({ post, context, here, check, meta, ...rest }: {
  post: Post; context: PostContext; here: Id | null
  check?: Check | null
  meta?: ReactNode
} & HTMLAttributes<HTMLElement>) {
  const box = check && (
    <input type="checkbox" className="fw-card-checkbox" checked={check.checked}
      onChange={check.toggle} onClick={(e) => e.stopPropagation()} aria-label={check.label} />
  )
  const who = <Who id={post.author} name={post.author_name} show="line" size={24} className="fx-who fw-author" />
  if (context === 'post') {
    return (
      <header className="fw-head fx-head" {...rest}>
        {box}
        {who}
        <span className="fx-stamp">
          <When at={post.at} />
          {post.edited_at && <span className="fw-meta">edited</span>}
          {meta}
        </span>
        <Where post={post} here={here} />
      </header>
    )
  }
  return (
    <div className="fx-head fw-head" {...rest}>
      {box}
      {who}
      {/* Full screen says its time once, in full (the head said it again as "5d ago"). */}
      <When at={post.at} full={context === 'full'} />
      {context !== 'full' && post.edited_at && <span className="fw-meta">edited</span>}
      {meta}
      <Where post={post} here={here} />
    </div>
  )
}

/* -- the body: words, and full screen's whole post -------------------------- */

/** The post's words: its Markdown without the blocks This post draws. A
 *  form stays in the words and is drawn and answered here, keyed by its own
 *  text part with that part's names, exactly as This post and Classic key
 *  it, so every copy is the same form with the same answers (P5a). */
export function Words({ post, size }: { post: Post; size?: 'reply' }) {
  if (post.deleted) return <Deleted post={post} />
  const part = inlinePart(post)
  const { words } = said(post, part !== null)
  if (!words) return null
  const scope = turnPartScope(post.id, part ?? 0)
  return (
    /* `turn-body` is where the shared renderers' styles are scoped (app.css). */
    <div className={'fw-body turn-body fx-text' + (size === 'reply' ? ' fx-text-reply' : '')}>
      {/* its words taken out as they are: a grip per run of text (Grip.tsx) */}
      <TextGrips post={post} />
      <BlockGripContext.Provider value={gripsFor(post)}>
        <Prose src={words} scope={scope} names={part !== null ? namesFor(post.parts[part].text ?? '', scope) : undefined} />
      </BlockGripContext.Provider>
    </div>
  )
}

function Deleted({ post }: { post: Post }) {
  return <p className="fw-deleted fx-text">Deleted{post.deleted!.because ? `: ${post.deleted!.because}` : ''}</p>
}

/** The parts a post carries that are files: drawn whole full screen. */
export const filesOf = (post: Post) =>
  post.parts.filter((p) => p.type !== 'text' && p.ref && !['turn', 'topic', 'conversation', 'acquired', 'object'].includes(p.type))

/** The post drawn whole (full screen): its words with every block the
 *  shared renderers draw, and its attachments. */
export function Whole({ post }: { post: Post }) {
  if (post.deleted) return <Deleted post={post} />
  const files = filesOf(post)
  return (
    <>
      <div className="fw-body turn-body fx-text fx-full-text">
        <BlockGripContext.Provider value={gripsFor(post)}><Prose src={textOf(post)} scope={turnPartScope(post.id, 0)} /></BlockGripContext.Provider>
      </div>
      <ObjectRefs post={post} />
      {files.length > 0 && (
        <div className="fx-full-files">
          {files.map((p, i) => {
            const mt = String((p as { media_type?: string }).media_type ?? '')
            const name = String(p.alt ?? p.name ?? p.ref)
            return p.type === 'image' || mt.startsWith('image/')
              ? <img key={i} src={`/api/artifacts/${p.ref}`} alt={name} loading="lazy" />
              : <a key={i} className="fx-chip" href={`/api/artifacts/${p.ref}`} target="_blank" rel="noopener">{name}</a>
          })}
        </div>
      )}
    </>
  )
}

/** What the post says: whom it is addressed to, its words, its decisions --
 *  or, full screen, the whole of it. `lead` is the place's relationship
 *  line ("Replying to #3", "↳ replying to #7"), said before it. */
export function PostBody({ post, context, lead }: { post: Post; context: PostContext; lead?: ReactNode }) {
  if (context === 'full') return <><Whole post={post} /><PostDecisions post={post} /></>
  return (
    <>
      {lead}
      <Addressees post={post} />
      <Words post={post} size={context === 'reply' ? 'reply' : undefined} />
      {/* the objects it references, each the original under its provenance (W4) */}
      <ObjectRefs post={post} />
      <PostDecisions post={post} />
    </>
  )
}

/* THE POST'S TOOLBAR (A6; production's TurnActions as the reference): a
 * compact bar of marks, shown on hover or keyboard focus, each saying its
 * words on hover and its whole name to a screen reader -- and on a touch
 * screen, which cannot hover, the words beside the marks. The everyday ones
 * are marks; what applies only sometimes (Include here, Remove from here,
 * Open in its home) appears only then; the rest is under More.
 *
 * Only what Fluid can already do is here. React, Comment and Deep dive are
 * drawn by Annotate, beside Address (Annotations.tsx); Edit, Delete and
 * Topic have their places kept (`LATER`), drawn by nothing until their
 * writes exist. Include here and Remove from here say what they will do,
 * and do it only when that is confirmed (#187 #4). */

/** Where the actions still to come go, in production's order, once Fluid
 *  can do them: Topic on the bar beside Address, Edit and Delete under More.
 *  None is drawn yet. */
export const LATER = { bar: ['topic'], more: ['edit', 'delete'] } as const

export const moreSheet = (post: Id) => 'post-more:' + post

export function MoreChips({ post, place }: { post: Post; place?: Placement }) {
  const a = useActions()
  const [asking, setAsking] = useState<null | 'include' | 'remove'>(null)
  const sheetNow = useOpenSheet()
  if (a.selectMode) return null
  const included = place?.via === 'linked' || (post.memberships ?? []).some((m) => m.conversation === a.here && m.via === 'linked')
  const away = !a.here || post.home !== a.here
  const num = post.number != null ? `#${post.number}` : 'this post'
  const homeName = post.home_name || (post.home ? store.conversations.get(post.home)?.name : null) || 'its own conversation'
  const hereName = (a.here && store.conversations.get(a.here)?.name) || 'this conversation'
  if (asking) {
    return (
      <span className="fx-more fx-confirm" role="group" aria-label="confirm" onClick={(e) => e.stopPropagation()}>
        <span className="fx-consequence">
          {asking === 'include'
            ? <>Include {num} here? It stays in <b>{homeName}</b>; {hereName} shows it too. Nothing is moved or copied.</>
            : <>Remove {num} from {hereName}? It stays in <b>{homeName}</b>; only its inclusion here ends. Nothing is deleted.</>}
        </span>
        <button className="fx-chip go" disabled={a.busy} onClick={() => { setAsking(null); (asking === 'include' ? a.include : a.remove)?.(post.id) }}>
          {asking === 'include' ? 'Include here' : 'Remove from here'}
        </button>
        <button className="fx-chip more" onClick={() => setAsking(null)}>Cancel</button>
      </span>
    )
  }
  const details = () => nav.openDetail({ kind: 'post-details', id: post.id, anchor: { kind: 'post', id: post.id }, mode: 'aside' })
  const full = () => nav.openDetail({ kind: 'full', of: 'post', id: post.id, anchor: { kind: 'post', id: post.id }, mode: 'over' })
  const copy = async (what: 'text' | 'link') => {
    closeSheet()
    const link = post.home ? `${location.origin}/fluid?c=${encodeURIComponent(post.home)}&t=${encodeURIComponent(post.id)}` : ''
    try {
      await navigator.clipboard.writeText(what === 'link' ? link : [`@${bare(post.author_name)} · ${num}`, '', textOf(post).trim(), ''].join('\n'))
      nav.toast({ text: what === 'link' ? `A link to ${num} is copied.` : `${num} is copied.` })
    } catch (e) {
      /* A denied clipboard is the browser's answer, said, not swallowed. */
      nav.toast({ text: `Could not copy: ${(e as Error).message}` })
    }
  }
  const canAddress = !post.deleted && !!(a.here ?? post.home)
  /* One mark: its words on hover and to a screen reader, beside it on touch. */
  const mark = (cls: string, glyph: string, label: string, aria: string, title: string, run: (el: HTMLElement) => void, extra?: { act?: string; disabled?: boolean; pressed?: boolean }) => (
    <button className={'fx-chip more fx-act ' + cls} data-act={extra?.act} aria-label={aria} title={title} disabled={extra?.disabled}
      aria-expanded={extra?.pressed} onClick={(e) => { e.stopPropagation(); run(e.currentTarget) }}>
      <span className="fx-act-glyph" aria-hidden="true">{glyph}</span><span className="fx-act-label">{label}</span>
    </button>
  )
  const more = moreSheet(post.id), addr = addressSheet(post.id)
  return (
    <span className="fx-more fx-postbar" role="toolbar" aria-label={`${num}: actions`}>
      {a.reply && !post.deleted && mark('fw-reply-to', '↩', 'Reply', `Reply to ${num}`, "Reply in this post's thread, with the thread's own composer", () => a.reply!(post.id), { act: 'reply' })}
      {/* Opening is already the card's click/Enter action. Keep the two
          distinct object actions here; secondary post actions live in More. */}
      <ObjectActions compact className="fx-post-acts" only={['peek', 'focus']}
        target={{ address: 'post:' + post.id, kind: 'post', title: num, ...(post.home_name ? { from: `${post.home_name} · ${num}` } : {}) }} />
      {canAddress && mark('fx-address', '@', 'Address', `Address ${num} to someone`, 'Address: ask someone to respond to this post', (el) => openSheet(addr, el), { act: 'address', pressed: sheetNow?.id === addr })}
      {/* react, comment, deep dive on the whole post, beside Address where
          production has them (Annotations.tsx) */}
      <Annotate post={post} />
      {away && post.home && (
        <a className="fx-chip more fx-act fw-card-open" href={`/fluid?c=${encodeURIComponent(post.home)}&t=${encodeURIComponent(post.id)}`}
          title={`Open in ${post.home_name ?? 'its conversation'}`} aria-label={`Open post in ${post.home_name || 'home conversation'}`} data-act="open-in"
          onClick={(e) => {
            e.stopPropagation()
            if (!e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); a.goHome(post.home!, post.id) }
          }}>
          <span className="fx-act-glyph" aria-hidden="true">⇱</span><span className="fx-act-label">Open in {post.home_name ?? 'its conversation'}</span>
        </a>
      )}
      {included && a.remove && mark('fw-card-remove', '⊖', 'Remove from here…', `Remove ${num} from here…`, `Remove from here: end its inclusion here; it stays in ${homeName}`, () => setAsking('remove'), { act: 'remove', disabled: a.busy })}
      {!included && a.include && a.here && post.home && post.home !== a.here &&
        mark('fw-card-include', '⊕', 'Include here…', `Include ${num} here…`, `Include here: show it here too; it stays in ${homeName}`, () => setAsking('include'), { act: 'include', disabled: a.busy })}
      {mark('fx-more-menu', '⋯', 'More', `More for ${num}`, 'More: details, full screen, select, copy, a link, Classic', (el) => openSheet(more, el), { act: 'more', pressed: sheetNow?.id === more })}
      {sheetNow?.id === addr && <AddressPop post={post} here={a.here} />}
      {sheetNow?.id === more && (
        <Sheet id={more} label={`more for ${num}`} className="fx-post-more">
          <button className="fx-opt" data-act="details" onClick={() => { closeSheet(); details() }}>Details <small>who wrote it, what was asked, the runs</small></button>
          <button className="fx-opt" data-act="full" onClick={() => { closeSheet(); full() }}>Full screen <small>enlarge the post; Esc returns</small></button>
          <button className="fx-opt" data-act="select" onClick={() => { closeSheet(); a.startSelect(post.id) }}>Select <small>keep or include posts elsewhere</small></button>
          <button className="fx-opt" data-act="copy" onClick={() => void copy('text')}>Copy <small>its words, with who and #</small></button>
          {post.home && <button className="fx-opt" data-act="copy-link" onClick={() => void copy('link')}>Copy link <small>to {num} in Fluid</small></button>}
          <button className="fx-opt" data-act="export" onClick={() => { closeSheet(); void exportTurn(post.id) }}>
            Export turn <small>download as a .zip archive</small>
          </button>
        </Sheet>
      )}
    </span>
  )
}

/** WHICH POST THIS IS, in a tall post's row once its head has scrolled out
 *  of view: "#N · name", shortened with "…" where the row has no room. */
export function PinTag({ post }: { post: Post }) {
  const what = `${post.number != null ? `#${post.number}` : 'This post'} · ${bare(post.author_name)}`
  return <span className="fx-pin-tag" title={what} aria-hidden="true">{what}</span>
}

/** THE POST'S ROW OF CHIPS: what the place puts first (`before`: what it
 *  carries, its replies), which post this is once a tall one's head is out
 *  of view, the place's status, then the toolbar. */
export function PostChips({ post, context, place, headAway, before, status }: {
  post: Post; context: PostContext; place?: Placement; headAway?: boolean
  before?: ReactNode; status?: ReactNode
}) {
  return (
    <div className={'fx-chips' + (context === 'post' ? '' : ' fx-chips-reply')}>
      {before}
      {headAway && <PinTag post={post} />}
      {status}
      <MoreChips post={post} place={place} />
    </div>
  )
}

/* THE WORK A POST STARTED (item 11): Classic's work pills, kept. The
 * conversation's work is read once, by the pills' own reader
 * (`useWorkByTurn`), and each card looks itself up by the post the work
 * started from. Its words are the pills' (`formatPillText`): objective met
 * only when the record says so, and ended work keeps its "not marked
 * complete". Who is running now, by `/api/activity`, says it is working. */
const WorkByTurn = createContext<Map<Id, WorkItem> | null>(null)

export function WorkStatusProvider({ conversation, children }: { conversation: Id; children: React.ReactNode }) {
  /* Asked once the conversation's own posts are read (`useAfterReads`). */
  const { itemsByTurn } = useWorkByTurn(useAfterReads(conversation))
  return <WorkByTurn.Provider value={itemsByTurn}>{children}</WorkByTurn.Provider>
}

/** ONE STATUS PER POST, IN ITS FOOTER, left of its tools: the work it
 *  started, and who is working on it or in its thread now (#568 4.6; A3).
 *  Nothing when it started no work and nobody is working there. */
export function WorkStatusPill({ post, workers, under }: { post: Post; workers: Working[]; under: Working[] }) {
  const item = useContext(WorkByTurn)?.get(post.id)
  const live = [...workers, ...under.filter((u) => !workers.some((w) => workKey(w) === workKey(u)))]
  /* THE WORK'S DETAILS ARE ONE CLICK AWAY: the pill opens the Work drawer
     (its Workflow, origin, progress and history among them) -- the same
     drawer Classic's pills opened, under the one-drawer rule. */
  const me = store.me
  const [open, setOpen] = useState(false)
  const opener = useRef<HTMLButtonElement | null>(null)
  const close = useCallback(() => { releaseDrawer(close); setOpen(false) }, [])
  if (!item && !live.length) return null
  const pill = <StatusPillBody item={item} live={live} workers={workers} />
  if (!item) return pill
  return <>
    <button type="button" className="fx-status-open" ref={opener} aria-label={`Work details: ${item.status_words}`}
      onClick={(e) => { e.stopPropagation(); claimDrawer(close); setOpen(true) }}>{pill}</button>
    {open && <WorkDrawer expectation={item.expectation} viewer={me} returnFocus={opener} onClose={close} />}
  </>
}

function StatusPillBody({ item, live, workers }: { item: WorkItem | undefined; live: Working[]; workers: Working[] }) {
  const words = item ? formatPillText(item) : null
  const met = item?.objective_met === true
  const state = met ? 'met' : live.length ? 'working' : words!.status === 'ended' ? 'ended' : words!.status === 'not started' ? 'not-started' : 'in-flight'
  const where = workers.length ? '' : ' in its thread'
  const who = live.length === 1 ? `${aliasOf(live[0])} working${where}` : `${live.length} working${where}`
  const title = [
    item && `Work: ${item.status_words}${item.title ? ` (${item.title})` : ''}`,
    live.length > 0 && `Working now: ${live.map((w) => `${aliasOf(w)} since ${new Date(w.working_on!.since * 1000).toLocaleTimeString()}`).join('; ')}`,
  ].filter(Boolean).join('\n')
  return (
    <span className={'fx-status-pill fx-status-' + state} role="status" data-work-state={state} title={title}>
      {state === 'working'
        ? live.slice(0, 2).map((w) => <Who key={workKey(w)} id={w.participant} name={w.alias} show="avatar" size={14} working />)
        : <span className="fx-status-glyph" aria-hidden="true">{met ? '✓' : state === 'ended' ? '◌' : state === 'not-started' ? '○' : '◐'}</span>}
      <span className="fx-status-words">
        {state === 'working' ? who : words!.status}
        {words?.decisions && <> · <span className="fx-status-owed">{words.decisions}</span></>}
        {state !== 'working' && words?.extra && <> · {words.extra}</>}
      </span>
    </span>
  )
}

/** WHO IS WORKING ON THIS POST, OR IN ITS THREAD (#568 4.6; A3): their
 *  faces with the live ring, and the words -- on the post itself, or on a
 *  reply under it ("in its thread") -- since when. Nothing when nobody is.
 *  Drawn in the thread's sheet; a post card says it in its footer. */
export function WorkOn({ num, on, under }: { num: string; on: Working[]; under: Working[] }) {
  const all = [...on, ...under.filter((u) => !on.some((o) => workKey(o) === workKey(u)))]
  if (!all.length) return null
  const one = all[0]
  const where = on.length ? '' : ' in its thread'
  const since = (w: Working) => `${aliasOf(w)} ${on.includes(w) ? `on ${num}` : `on ${w.working_on?.number != null ? `#${w.working_on.number}, a reply` : 'a reply'} in the thread of ${num}`}, since ${new Date(w.working_on!.since * 1000).toLocaleTimeString()}`
  return (
    <span className={'fx-work' + (on.length ? '' : ' fx-work-under')} role="status" title={`Working now: ${all.map(since).join('; ')}`}>
      {all.slice(0, 2).map((w) => <Who key={workKey(w)} id={w.participant} name={w.alias} show="avatar" size={16} working />)}
      <span className="fx-work-words">{all.length === 1 ? `${aliasOf(one)} working${where}` : `${all.length} working${where}`}</span>
    </span>
  )
}

/** A POST, DRAWN: its identity line, what it says, its chips, whether it is
 *  on stage, and its annotations -- inside whatever element its place gives
 *  it. Full screen draws no chips, on-stage mark or annotations, as before.
 *  `card` is the place's element, for the annotations' gutter and wash;
 *  without it (the thread's root) none are drawn. */
export function PostView({ post, context, here, head, check, meta, lead, chips, onStage, card, selecting }: {
  post: Post; context: PostContext; here: Id | null
  /** attributes for the head (a card's head is its drag handle) */
  head?: HTMLAttributes<HTMLElement>
  check?: Check | null
  meta?: ReactNode
  lead?: ReactNode
  chips?: { place?: Placement; headAway?: boolean; before?: ReactNode; status?: ReactNode }
  /** the on-stage mark (workspace/origin.tsx `useOnStage`); full screen has none */
  onStage?: number | null
  card?: RefObject<HTMLElement | null>
  selecting?: boolean
}) {
  return (
    <>
      <PostHead post={post} context={context} here={here} check={check} meta={meta} {...head} />
      <PostBody post={post} context={context} lead={lead} />
      {context !== 'full' && <PostChips post={post} context={context} {...chips} />}
      {context !== 'full' && <OnStageTag n={onStage ?? null} />}
      {/* ANNOTATIONS (Annotations.tsx): marks in the card's right gutter,
          the passages' wash, and the bar beside a selection in its words */}
      {card && !selecting && <Annotations post={post} card={card} />}
    </>
  )
}
