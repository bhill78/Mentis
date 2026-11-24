/* THE PERSISTENT COMPOSER, in the card's footer slot.
 *
 * The approved hybrid card can be written in from wherever the owner is: the
 * bar is present on all six tabs and in the search overlay, and absent only in
 * settings (the frame decides that, by not rendering this slot there). It is
 * the real `fluid/Composer` through the `miniAsking()` adapter, so addressing,
 * the split send, Work permissions and the five keyboard conventions are the
 * app's own and are not re-implemented here.
 *
 * What this file owns: where the composer sits, the discussion reference chip,
 * the "What Mentis reads" choice, and what happens when a message is sent --
 * the real request, the return route, and the move to the Conversation.
 *
 * Nothing here is a second posting system: every write goes through the same
 * store, the same `POST /fluid/api/requests` (or the posting door for a
 * record-only message), and the same single client-only `_magnetAssistance`
 * marker that `evidence.ts` strips before sending. */

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { ReactNode, RefObject } from 'react'
import Composer from '../../fluid/Composer'
import { useBrainBound } from '../../brainBinding'
import type { MagnetCarried, MagnetContext, MagnetResource } from './contract'
import { miniAsking } from './asking'
import {
  NO_OWN_CONVERSATION, attachContext, miniAttempt, miniConversationOf, removeContext, retireContext,
} from './conversation'
import { place, remember, route, writePlace } from './places'
import { perspectivesOf } from './perspectives'
import './conversation.css'
import './composer.css'

/** The one line that stays under the bar. The rest of what used to sit beside
 *  the composer moved: the Perspective disclosure to the Conversation view's
 *  header, and the reading choice's explanation into its own menu group. */
export const COMPOSER_STATUS = 'Ordinary help works before collecting. Grounded Perspective execution is disabled.'

export const READS_HEADING = 'What Mentis reads'
export const ORDINARY_READ = 'Ordinary configuration and inquiry help'
export const RETAINED_READ = 'Discuss retained collection · ordinary reply'
export const READS_SCOPE = 'This choice is kept for this Magnet.'
export const RETAINED_BLOCKED_BY_LENS = 'A Perspective is selected, so this message is ordinary inquiry help about its saved question.'
export const RETAINED_BLOCKED_BY_SEND = 'A send from this card is unresolved, so what it reads cannot be changed under it.'

/** A scroll past the end of the Conversation: the frame's one scroll container
 *  clamps it, which is how "pinned to the bottom" stays true once a message
 *  has been added to the page. */
export const PIN_TO_BOTTOM = 1e7

/** The chip's words. The reference is the chip: the label is only what the
 *  owner could already see in the view they attached it from. */
export const contextWords = (c: MagnetContext): string => `${c.label || c.ref}`

/** THE CANDIDATE, from where the owner actually is. The inspected item of the
 *  current place, else the selected Perspective when the Perspectives view (or
 *  a Perspectives search result) is what is open. Nothing else volunteers one,
 *  and a candidate is never content -- it is the reference the view is showing. */
export function contextCandidate(resource: MagnetResource, lensName?: string | null): MagnetContext | null {
  const s = resource.snapshot()
  const here = place(s)
  if (here.inspected) {
    const ref = here.inspected
    const row = s.results.find((r) => r.id === ref)
    const kind: MagnetContext['kind'] = row?.kind === 'post' ? 'post'
      : row?.kind === 'image' ? 'image'
      : /^adm-/.test(ref) ? 'file' : 'post'
    const value = row?.value as { title?: unknown } | undefined
    const title = typeof value?.title === 'string' && value.title ? value.title : ''
    return { ref, kind, label: title || ref }
  }
  const onPerspectives = s.overlay === null ? s.tab === 'Perspectives' : s.searchTarget?.kind === 'Perspectives'
  if (onPerspectives && s.lens) return { ref: s.lens, kind: 'perspective', label: lensName || s.lens }
  return null
}

/** WHAT A RECORDED MESSAGE DOES TO THE CARD, as one act so it can be checked
 *  without a browser. Sending from anywhere but the Conversation saves the way
 *  back first and then goes to the Conversation; sending from the Conversation
 *  stays there and saves nothing (there is nowhere to return to). The message
 *  is the newest, so the Conversation is pinned to its bottom. The attached
 *  reference went with those words, so it is let go here, and suppression with
 *  it. Nothing here touches the draft: that is the store's, settled with the
 *  attempt even when the card that sent it is gone.
 *
 *  `carried` is what that send took with it, noted under its key when it went
 *  out (`carryContext`). This act may run long after the press -- the answer
 *  can land while the footer is unmounted, and then it is this bar's first act
 *  on mounting -- so the way back and the reference to let go are read from
 *  there and not from where the card is now. Without one (a direct call in a
 *  check) it behaves as before, from the card's current place. */
export function afterSent(resource: MagnetResource, carried: MagnetCarried | null = null): void {
  retireContext(resource, carried)
  if (!carried) remember(resource)
  const from = carried?.from ?? route(resource.snapshot())
  if (from.tab !== 'Conversation' || from.overlay) {
    resource.update({ returnRoute: from, tab: 'Conversation', overlay: null, searchTarget: null })
  }
  writePlace(resource, 'Conversation', { scroll: PIN_TO_BOTTOM, inspected: null, inspectScroll: 0 })
}

export interface ReadsMenuProps {
  mode: 'ordinary' | 'retained'
  /** why the retained item cannot be chosen now, or null when it can */
  retainedWhy: string | null
  /** a send in flight: neither item is chosen under it */
  sending: boolean
  choose(mode: 'ordinary' | 'retained'): void
  close(): void
}

/** "WHAT MENTIS READS": the reading choice, kept for this Magnet.
 *
 *  §5-H2-8 of the plan puts this as a second radio group inside the app's own
 *  split-send menu. That menu is in `src/fluid/Composer.tsx`, which §4 of the
 *  same plan assigns to **nobody** -- it is every composer's send semantics --
 *  so the group is this bar's own menu instead, with the approved menu's
 *  semantics: a labelled group, `menuitemradio` items, the existing honest
 *  wording, the disabled item's reason shown, and its own scope note saying
 *  this choice is kept rather than per message. No `<select>`, which the
 *  approved frame has nowhere in the composer. */
export function ReadsMenu({ mode, retainedWhy, sending, choose, close }: ReadsMenuProps) {
  return <div className="q2-magnet-reads-menu" role="menu" aria-label={READS_HEADING}
    onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); close() } }}>
    <p className="q2-mini-muted q2-magnet-reads-head">{READS_HEADING}</p>
    <button type="button" role="menuitemradio" aria-checked={mode === 'ordinary'} disabled={sending}
      onClick={() => { choose('ordinary'); close() }}>
      {ORDINARY_READ}<small>Configuration, capabilities and how to ask; it works before anything is collected.</small>
    </button>
    <button type="button" role="menuitemradio" aria-checked={mode === 'retained'} disabled={!!retainedWhy}
      onClick={() => { choose('retained'); close() }}>
      {RETAINED_READ}<small>The retained batch is attached to this message and read before answering; the reply is still an ordinary one.</small>
    </button>
    {retainedWhy && <p className="q2-mini-muted" role="status">{retainedWhy}</p>}
    <p className="q2-mini-muted">{READS_SCOPE}</p>
  </div>
}

export interface ComposerBarProps {
  resource: MagnetResource
  canWrite: boolean
}

export default function ComposerBar({ resource, canWrite }: ComposerBarProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const bound = useBrainBound()
  const inquiries = useMemo(() => perspectivesOf(resource), [resource])
  const lens = useSyncExternalStore(inquiries.subscribe, inquiries.snapshot, inquiries.snapshot)
  const { at, store } = miniConversationOf(resource, canWrite, bound)
  const mini = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  /* One adapter per store: the Composer's place key must not change between
     renders, or the draft it is holding would be a different draft. */
  const ask = useMemo(() => miniAsking(resource, store), [resource, store])
  const [reads, setReads] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const typed = useRef<string>(mini.draft.trim())

  /* The assistance hooks belong to the send, so they are installed by the one
     component that sends. Their bodies are `MiniConversation`'s unchanged: the
     frozen Perspective check, the fresh durable question, the single
     `_magnetAssistance` marker and the inquiry binding afterwards. */
  at.canWrite = canWrite
  at.contextKey = () => {
    const current = inquiries.snapshot(), row = current.rows.find((p) => p.perspective === current.selected)
    return `${current.selected ?? ''}:${row?.question?.ref ?? ''}:${resource.snapshot().assistanceMode ?? 'ordinary'}`
  }
  at.beforeRequest = async (post, op) => {
    const previous = miniAttempt(resource)
    if (previous?.perspective && ['in-flight', 'uncertain', 'malformed'].includes(previous.state)) throw new Error('Resolve the original frozen Perspective request before sending a different question.')
    const perspective = await inquiries.ordinaryContext()
    if (resource.snapshot().assistanceMode === 'retained' && !perspective) return { post, op }
    return { post: { ...post, _magnetAssistance: { magnet: resource.saved.id,
      configuration: resource.saved.config, perspective,
      supported_sources: ['Conversations', 'exact held UTF-8 filesystem files'],
      collection: 'manual Collect now; opening and saving do not collect',
      unsupported: ['web search', 'Topic/post-specific adapters', 'Git/SQLite Magnet adapters', 'connected services', 'automatic collection'],
      grounded_perspective_execution: 'disabled; configured-source agent access is not enforced',
    } }, op }
  }
  at.afterRecorded = async (attempt, answer) => {
    if (!attempt.perspective) return
    const requests = answer.expectations
    if (!Array.isArray(requests) || requests.length !== 1 || typeof requests[0] !== 'string') throw new Error('A Perspective question needs exactly one actual agent request. Its frozen intent is kept.')
    await inquiries.bind(attempt.perspective, requests[0])
    inquiries.update({ active: attempt.perspective })
  }

  useEffect(() => { void store.prepare() }, [store])

  /* THE CHIP ATTACHES ON THE FIRST MEANINGFUL KEYSTROKE, not on arrival in a
     view and not on every change: the draft going from nothing typed to
     something typed is the moment, and `attachContext` itself refuses to
     replace an attached chip or to defeat the owner's suppression. */
  const draft = mini.draft.trim()
  useEffect(() => {
    const before = typed.current
    typed.current = draft
    if (before || !draft) return
    const candidate = contextCandidate(resource, lens.rows.find((p) => p.perspective === lens.selected)?.name)
    if (candidate) attachContext(resource, candidate)
  }, [draft, resource, lens.rows, lens.selected])

  /* WHAT SENDING DOES TO THE CARD, ONCE, WHENEVER THIS BAR CAN NEXT DO IT. The
     footer is not mounted in settings or while the card is closed, and that is
     exactly when a held answer can land: the send's own note (`carried`, in the
     Magnet's working state) is what says there is still an act owing and what
     that act is about. Settling consumes the note, so a remount, a re-render or
     the same key answered twice cannot do it again -- and a reference the owner
     has attached since belongs to the message they are writing now, not to
     this one. */
  useEffect(() => {
    const owed = s.carried, done = mini.sent
    if (!owed || !done || owed.op !== done.op) return
    afterSent(resource, owed)
  }, [mini.sent?.op, s.carried?.op, resource])

  const blocked = !!mini.identity
  const lensSelected = !!lens.selected

  return <ComposerBarView
    canWrite={canWrite}
    unavailable={mini.unavailable}
    chip={s.context}
    suppressed={s.contextSuppressed}
    onRemoveChip={() => removeContext(resource)}
    replyTo={mini.replyTo}
    onReplyToConversation={() => store.replyTo(null)}
    mode={lensSelected ? 'ordinary' : s.assistanceMode ?? 'ordinary'}
    retainedWhy={lensSelected ? RETAINED_BLOCKED_BY_LENS : (mini.sending || mini.uncertain) ? RETAINED_BLOCKED_BY_SEND : null}
    onMode={(pick) => resource.update({ assistanceMode: pick })}
    reads={reads}
    onReads={setReads}
    frozen={blocked || !bound || mini.sending || mini.uncertain}
    sending={mini.sending}
    creating={mini.creating}
    identity={mini.identity}
    contextError={mini.contextError}
    sendError={mini.sendError}
    uncertain={mini.uncertain}
    canRetry={!mini.sending && !blocked && !!bound}
    onRetry={() => {
      const attempt = miniAttempt(resource)
      if (attempt?.request) void store.submit(attempt.request.body, attempt.op, attempt.brain).catch(() => {})
      else void store.send()
    }}
    sent={mini.sent}
    box={box}
    composer={<Composer key={ask.where} conversation={store.conversation}
      asking={{ ...ask, key: `${ask.key}:${mini.replyTo?.id ?? ''}` }}
      replyTo={mini.replyTo?.id ?? null} onClearReply={() => store.replyTo(null)} operations />}
  />
}

export interface ComposerBarViewProps {
  canWrite: boolean
  unavailable?: string
  chip: MagnetContext | null
  suppressed: boolean
  onRemoveChip(): void
  replyTo: { id: string; number: number | null; alias: string } | null
  onReplyToConversation(): void
  mode: 'ordinary' | 'retained'
  retainedWhy: string | null
  onMode(mode: 'ordinary' | 'retained'): void
  reads: boolean
  onReads(open: boolean): void
  /** the whole composer is held while a send is unresolved or the page has moved */
  frozen: boolean
  sending: boolean
  creating: boolean
  identity?: string
  contextError?: string
  sendError?: string
  uncertain: boolean
  canRetry: boolean
  onRetry(): void
  sent?: { post: string; number: number | null; replayed: boolean }
  box?: RefObject<HTMLDivElement | null>
  /** the real `fluid/Composer`, supplied so what this bar draws around it can
   *  be asserted without a browser: the Composer itself is client-only. */
  composer: ReactNode
}

/** EVERYTHING THE BAR DRAWS AROUND THE COMPOSER. It holds no state and reaches
 *  nothing, so it is the whole of what can be checked without a DOM; the real
 *  Composer inside it is the app's own and is driven by the browser suite. */
export function ComposerBarView(p: ComposerBarViewProps) {
  if (!p.canWrite) {
    return <div className="q2-magnet-composer q2-magnet-composer-readonly">
      <p className="q2-mini-muted q2-mini-nowrite">Sending is unavailable for this Magnet here. Nothing in this card writes to the record.</p>
    </div>
  }
  return <div className="q2-magnet-composer" ref={p.box}>
    {p.unavailable === NO_OWN_CONVERSATION && <p className="q2-mini-muted" role="status">
      This Magnet has no Conversation of its own yet. Sending makes one and records the message in it.
    </p>}
    {p.unavailable && p.unavailable !== NO_OWN_CONVERSATION && <p className="q2-mini-alert" role="status">{p.unavailable}</p>}
    {p.chip && <p className="q2-magnet-chip">
      <span className="q2-magnet-chip-label">Discussing <b>{contextWords(p.chip)}</b> <small>{p.chip.kind} · {p.chip.ref}</small></span>
      <button type="button" className="q2-mini-link" aria-label={`Remove ${contextWords(p.chip)} from this message`}
        onClick={p.onRemoveChip}>Remove</button>
    </p>}
    {p.suppressed && !p.chip && <p className="q2-mini-muted">This message carries no reference. Open an item and choose “Discuss this evidence” to attach one.</p>}
    {p.replyTo && <p className="q2-mini-replying">
      <span>Replying to {p.replyTo.alias}{p.replyTo.number !== null ? ` #${p.replyTo.number}` : ''}</span>
      <button type="button" className="q2-mini-link" onClick={p.onReplyToConversation}>Reply to the Conversation instead</button>
    </p>}
    <div className="q2-magnet-reads">
      <button type="button" className="q2-mini-link" aria-haspopup="menu" aria-expanded={p.reads}
        onClick={() => p.onReads(!p.reads)}>{READS_HEADING}: {p.mode === 'retained' ? RETAINED_READ : ORDINARY_READ}</button>
      {p.reads && <ReadsMenu mode={p.mode} retainedWhy={p.retainedWhy} sending={p.sending}
        choose={p.onMode} close={() => p.onReads(false)} />}
    </div>
    <fieldset className="q2-mini-composer-controls" disabled={p.frozen}>{p.composer}</fieldset>
    <p className="q2-mini-muted q2-magnet-composer-status">{COMPOSER_STATUS}</p>
    {p.uncertain && <button type="button" className="q2-mini-send" disabled={!p.canRetry}
      onClick={p.onRetry}>Send again under the same key</button>}
    {p.contextError && <p className="q2-mini-alert" role="status">{p.contextError}</p>}
    {p.identity && <p className="q2-mini-alert" role="status">{p.identity}</p>}
    {p.sendError && <p className={p.uncertain ? 'q2-mini-alert q2-mini-uncertain' : 'q2-mini-alert'} role="status">{p.sendError}</p>}
    {p.creating && <p className="q2-mini-muted" role="status">Creating this Magnet’s Conversation…</p>}
    {p.sent && <p className="q2-mini-sent" role="status">
      {p.sent.replayed
        ? 'That post was already recorded under this key; nothing was recorded a second time.'
        : `Recorded${p.sent.number !== null ? ` as #${p.sent.number}` : ''}.`}
    </p>}
  </div>
}
