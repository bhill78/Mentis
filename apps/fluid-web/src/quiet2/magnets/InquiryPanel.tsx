/** PERSPECTIVES: a place to ask something and keep thinking about it.
 *
 *  Rebuilt to the approved round-3 design (owner ent-a24ec84c8176; mockups
 *  `02-compact-current`, `05-future-answer`, `06-future-support`,
 *  `07-future-expanded`, `08-history`, `09-current-help`,
 *  `10-current-discussion`). The design is CSS, not a picture: it is ported in
 *  `design.css` as `mgd-` classes and this view COMPOSES from it. Anything
 *  added here is arrangement, not a second type scale.
 *
 *  **Five states, and nothing else on the resting surface.**
 *  1. ASKING -- eyebrow, `Explore a question`, `Past questions ▾`, one muted
 *     sentence, the compose box, `TRY ASKING`, a divider, and the one line that
 *     pairs `AVAILABLE NOW` with what ordinary Conversation does. That sentence
 *     is said ONCE here, not three times (owner).
 *  2. A QUESTION AND WHAT IS UNDERSTOOD OF IT -- the state line, the question in
 *     a chat bubble, the record's own understanding against the gold rule, the
 *     follow-up compose box, one hint.
 *  3. SUPPORTING ITEMS (`SupportingItems`) -- opened from the answer block and
 *     given straight back.
 *  4. PAST QUESTIONS (`PastQuestions`) -- the list to return through, and the
 *     only route to everything that administers a question.
 *  5. WITH ROOM -- the same content in two columns, from the frame's
 *     `--magnet-room`, never from a viewport media query.
 *
 *  **A PERSISTENT QUESTION, NOT A SECOND CONVERSATION SYSTEM** (owner
 *  ent-901ef1a816bb). A Perspective is one question that is kept, and what is
 *  understood of it may change as the Magnet collects more. So the question
 *  surface tells the answer STANDING NOW apart from the answers it follows,
 *  keeps every earlier one readable at its own recorded version under
 *  `Earlier answers`, and offers both halves of refresh: the owner's own read
 *  (`READ_AGAIN`) beside the answer, and one automatic read when -- and only
 *  when -- the Magnet reports a different collected batch. Discussion stays in
 *  the Conversation, which is why nothing here grows a thread of its own.
 *
 *  **Ordinary question language.** The owner's language review
 *  (ent-3191baeb33d2 §2) governs every word: no control, option, label or
 *  message here says "inquiry".
 *
 *  **What went, and why.** The `About <name> question — Remove` administrative
 *  row, the standing `Your question` label, the lecture under `Current
 *  understanding`, and every repetition of "discussion does not read your
 *  collected items" after the first. Nothing was removed from the store: every
 *  verb this panel had -- revising, challenging, renaming, retiring, resuming,
 *  the durable lens, the wording history and its pagination -- is still here,
 *  behind `Past questions ▾`, which is where the owner asked history and
 *  provenance to live.
 *
 *  **A QUESTION GETS A REAL ANSWER NOW** (plan §3 Part F). Asking records an
 *  answer written from this Magnet's collected rows, kept against the question
 *  and superseding -- never overwriting -- the one before it. So the mockups'
 *  `FUTURE CONCEPT` mark is gone from the supporting items, the hint that said
 *  answering was not available is gone, and so is the permanently disabled
 *  "Answer from selected evidence" press and the server reason it carried: the
 *  owner's correction `ent-d85254fe5e1b` is enforced at the one door (Part A,
 *  `mentis/magnet/scope.py`), the gate is open, and a panel still saying it was
 *  shut would be the interface claiming something untrue.
 *
 *  What every answer DOES still say is what it was grounded in. Grounded in
 *  this collection and explored outside it are rendered as different things,
 *  from Part A's own `explored_outside` field, and an answer that cannot state
 *  what it reached is not shown as grounded.
 *
 *  Selection is durable -- a `selected` event, not UI state -- and `canWrite` is
 *  passed through exactly as it is given: no box, press or editor here offers a
 *  write the server would refuse. */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import {
  answerHistory, answerText, derivedPerspectiveName, grounding, pastQuestions, perspectivesOf,
  provenanceOf, questionSubtitle, recordedUnderstanding, restampAttachedQuestion, showPerspectiveContext, stampAttachedQuestion,
  CHECKED_NEW, CHECKED_SAME, COLLECTION_MOVED, EVENT_WORDS,
  NOTHING_RECORDED_YET, PERSPECTIVE_DISCLOSURE, SUPPORTING_WHY, WRITTEN_BY_MENTIS,
  type InquiryEvent, type PerspectiveStore,
} from './perspectives'
import { agentWritten, Briefing, offeredQuestions, readStandingBriefing, withWords } from './Summary'
import { retainedItems, resultPreview, resultTitle, rowByline, usePeople } from './EvidenceViews'
import { Linked } from './links'
import { focusMiniComposer, miniComposerDraft, saveMiniComposer } from './conversation'
import { goTab, setOpen } from './places'
import {
  clearRenameDraft, clearRevisionDraft, clearQuestionDraft, panelAt, panelDrafts,
  setQuestionDraft, setReasonDraft, setRenameDraft, setRevisionDraft, subscribePanelDrafts,
} from './panelDrafts'
import './design.css'
import './configuration.css'
import './summary.css'
import './perspectives.css'

/** Discussing a saved question is ordinary discussion of the question: the
 *  answer kept against it is written from the collection, and what is said in
 *  the Conversation is said by whoever says it. */
export const DISCUSS_IS_ORDINARY = 'Ordinary discussion of the saved question, in this Magnet’s own Conversation. The answer kept against the question is the one grounded in the collected records.'

/** The one sentence about what discussion reads, said once on the resting
 *  surface and nowhere else (owner: not three times). */
export const DISCUSSION_READS = 'Asking keeps an answer written from your collected records; discussing it is ordinary conversation.'
/** The chips, where the mockups put them. */
export const AVAILABLE_NOW = 'AVAILABLE NOW', CURRENT_MODE = 'CURRENT MODE'
export const ORDINARY_CONVERSATION = 'Ordinary Conversation', ORDINARY_DISCUSSION = 'Ordinary discussion'
/** `09-current-help`: the one "what can I do today" panel, opened by a link. */
export const HELP_TITLE = 'What can I do today?'
export const HELP_WORDS = 'You can discuss a question now, or browse collected items yourself. Discussion does not read those items to form its answer.'
/** `02-compact-current`: something to ask when nothing has been asked. It is
 *  no longer one hardcoded demonstration sentence about releases -- which was a
 *  made-up question about a subject no Magnet necessarily holds -- but a
 *  question built out of what THIS Magnet has actually collected, through the
 *  same `offeredQuestions` the Summary offers. With nothing collected it is
 *  that function's own empty-collection question, which is about getting
 *  started rather than about anything the record does not hold. */
export const tryAsking = (resource: MagnetResource): string =>
  offeredQuestions(resource.snapshot())[0] ?? 'What can this Magnet collect at the moment?'
/** The manual half of refreshing a kept question (owner ent-901ef1a816bb:
 *  "support manual or automatic refresh"). It reads the record again; it forms
 *  no answer, which is why it is worded as a read. */
export const READ_AGAIN = 'Read this question again'
/** The heading the kept answer and the ones before it live under. */
export const EARLIER_ANSWERS = 'Earlier answers'
/** THE ONE DISCLOSURE THE ANSWER'S APPARATUS LIVES BEHIND (owner
 *  `ent-15a36a065eb8`: secondary actions and provenance through progressive
 *  disclosure, not permanently on screen and not hidden). What it holds is the
 *  grounding statement, who wrote the answer, the recorded answer itself, and
 *  the presses that act on the answer rather than read it. */
export const ABOUT_THIS_ANSWER = 'About this answer'
/** ONE PRESS FROM A QUESTION INTO THE MAGNET'S CONVERSATION (owner
 *  `opr-85178afc5f3a`), folded in here rather than left as separate polish.
 *  The question being viewed is made the active one if it is not already --
 *  one durable write, because the owner pressed for it -- and then its own
 *  saved words are copied into the Conversation's Composer, with the chip
 *  stamped at the exact version this card is showing. */
export const TAKE_TO_CONVERSATION = 'Discuss this in the Conversation'
export async function takeToConversation(resource: MagnetResource, store: PerspectiveStore) {
  const s = store.snapshot()
  const viewed = s.viewed ?? s.selected
  if (!viewed) throw new Error('Open a question before taking it into the Conversation.')
  if (s.selected !== viewed) await store.select(viewed)
  return discussSelectedQuestion(resource, store)
}
/** AN AGENT-WRITTEN ANSWER, ASKED FROM THIS QUESTION. `ANSWER_FROM_COLLECTION`
 *  writes an answer from this Magnet's own collected rows alone; this press
 *  is the other kind -- the words are frozen as this Perspective's immutable
 *  input package (`store.prepare`, which revises the saved question to these
 *  exact words first), and the frozen intent then travels through the
 *  Conversation's own composer and its `beforeRequest` hook, which attaches
 *  it to the actual request so the server can bind and reconcile it. Nothing
 *  is dispatched from here: the owner still chooses the recipient and presses
 *  Send in the Conversation, exactly as `TAKE_TO_CONVERSATION` already hands
 *  off there. */
export const ASK_AN_AGENT = 'Ask an agent about this'
export async function askAnAgent(resource: MagnetResource, store: PerspectiveStore, text: string) {
  const s = store.snapshot()
  const topic = s.viewed ?? s.selected
  if (!topic) throw new Error('Open a question before asking it of an agent.')
  if (!text.trim()) throw new Error('Write a question before asking an agent.')
  const held = miniComposerDraft(resource)
  if (held.text.trim() && held.text !== text) throw new Error('The Conversation Composer already has a different draft. Keep or clear it before asking an agent.')
  if (s.selected !== topic) await store.select(topic)
  const prepared = await store.prepare(text, `perspective-ask:${topic}:${crypto.randomUUID()}`)
  const context = await store.ordinaryContext()
  if (!context || context.perspective !== topic || context.revision !== prepared.question?.ref)
    throw new Error('The saved question no longer matches the frozen request. The request is kept; nothing was sent.')
  const now = miniComposerDraft(resource)
  if (now.text !== held.text && now.text.trim() && now.text !== text)
    throw new Error('The Conversation Composer now holds different words. Keep or clear them before continuing; the frozen request is kept.')
  showPerspectiveContext(resource, topic, context.name)
  restampAttachedQuestion(resource, topic, prepared.question)
  saveMiniComposer(resource, { ...now, text: prepared.text })
  focusMiniComposer()
  goTab(resource, 'Conversation')
  setOpen(resource, true)
  return context
}
/** What the answer block says about who wrote the answer standing now. */
export const ANSWER_WRITTEN_BY = (e: InquiryEvent | null): string =>
  agentWritten(e) ? 'Written by an agent' : typeof e?.data?.written_by === 'string' ? e.data.written_by : WRITTEN_BY_MENTIS

/** WHAT AN ANSWER WAS GROUNDED IN (Part A's `explored_outside`, unchanged).
 *  Grounded-in-the-collection and explored-outside are rendered as different
 *  things, and an answer that records neither is shown as neither. */
export function AnswerGrounding({ answer }: { answer: InquiryEvent | null }) {
  const g = grounding(provenanceOf(answer))
  if (!answer) return null
  return <div className={`q2p-grounding${g.outside ? ' q2p-outside' : ''}`}>
    <span className={g.outside ? 'mgd-future' : 'mgd-today'}>{g.label.toUpperCase()}</span>
    <span className="mgd-small mgd-muted">{g.detail}</span>
    {!!g.reached.length && <ul className="q2-magnet-items" aria-label="What this answer reached outside the collection">
      {g.reached.map((what) => <li key={what}>{what}</li>)}</ul>}
  </div>
}

/** THE COLLECTION THIS MAGNET NOW HOLDS, watched for change, because that
 *  change is the only thing that can alter what is understood of a kept
 *  question. Tolerates a resource that publishes no subscription (the panel's
 *  own fixtures): then nothing is watched and only manual reading is offered,
 *  rather than the panel failing to render. */
function useCollectedMark(resource: MagnetResource): string | null {
  const subscribe = useMemo(() => (fn: () => void) =>
    typeof resource.subscribe === 'function' ? resource.subscribe(fn) : () => {}, [resource])
  const read = useMemo(() => () => resource.snapshot().activation?.artifact.ref ?? null, [resource])
  return useSyncExternalStore(subscribe, read, read)
}

/** Copy the fresh saved question; preserve any existing Composer draft and send choices. */
export async function discussSelectedQuestion(resource: MagnetResource, store: PerspectiveStore) {
  const context = await store.ordinaryContext()
  if (!context) throw new Error('Select a Perspective before discussing its saved question.')
  const draft = miniComposerDraft(resource)
  if (draft.text.trim() && draft.text !== context.question)
    throw new Error('The Conversation Composer already has a different draft. Open it to keep or clear those words before copying the saved question.')
  // These words are one exact saved version: an attached chip that states no
  // version is made to state this one. Nothing is attached or un-suppressed.
  stampAttachedQuestion(resource, store.snapshot().selectedDetail)
  saveMiniComposer(resource, { ...draft, text: context.question })
  focusMiniComposer()
  goTab(resource, 'Conversation')
  setOpen(resource, true)
  return context
}

/** The durable lens: which question the Conversation follows. It is the quiet
 *  one -- the list in `PastQuestions` is how a question is returned to -- so it
 *  lives among the administrative verbs rather than on the resting surface. */
export function LensSelector({ resource, canWrite }: { resource: MagnetResource; canWrite: boolean }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const [error, setError] = useState('')
  useEffect(() => { void store.read() }, [store])
  return <div className="q2-magnet-lens"><label>Active question<select aria-label="Active question" value={s.selected ?? ''} disabled={!canWrite || s.loading || !!s.pending} onChange={(e) => { setError(''); void store.select(e.target.value || null).catch((e) => setError(e.message)) }}><option value="">No question — ordinary Conversation</option>{s.rows.filter((p) => !p.retired || p.perspective === s.selected).map((p) => <option key={p.perspective} value={p.perspective}>{p.name}</option>)}</select></label>{s.listNext && <button type="button" className="mgd-link mgd-small" onClick={() => void store.read(s.listNext!)}>More questions</button>}{(error || s.error) && <p role="status">{error || s.error}</p>}</div>
}

/** The wording an event carries, if it carries one. */
const wordingOf = (e: InquiryEvent) => typeof e.data.text === 'string' ? e.data.text : typeof e.data.name === 'string' ? e.data.name : null

/** THE LOADING STATE, PLAINLY UNFINISHED AT A GLANCE (approved mockup round 4,
 *  `05-perspectives-loading.png`): an explicit message, a visible spinner, an
 *  indeterminate progress track and skeleton lines -- in place of the one
 *  static sentence ("The recorded answer is being checked before display.")
 *  that, at a glance, read as a finished, empty card rather than as work in
 *  progress (owner `ent-b328aed7a160`). Shown while an agent-written answer is
 *  recorded on the event but its words have not yet been read (`agentWritten`
 *  true, `answerText` still empty) -- the same moment Summary's own `frozen`
 *  read covers for its Briefing. */
function BuildingOverview() {
  return <div className="q2p-building" role="status" aria-live="polite">
    <div className="mgd-row q2p-building-head">
      <span className="q2p-building-spinner" aria-hidden="true" />
      <b>Building your overview…</b>
    </div>
    <div className="q2p-building-track" aria-hidden="true"><span /></div>
    <div className="q2p-skeleton" aria-hidden="true">
      <span className="q2p-skeleton-head" /><span className="q2p-skeleton-line" /><span className="q2p-skeleton-line short" />
      <span className="q2p-skeleton-head" /><span className="q2p-skeleton-line" /><span className="q2p-skeleton-line short" />
    </div>
  </div>
}

/** Run one action with the panel's one busy flag and one status line. */
function useAction() {
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true); setMessage('')
    try { await fn() } catch (e) { setMessage((e as Error).message) } finally { setBusy(false) }
  }
  return { message, setMessage, busy, run }
}

/** THE SUPPORTING ITEMS (`06-future-support`, which is not a future any more).
 *  The Magnet's own collected records, listed against the question so the owner
 *  can read them THEMSELVES. The answer standing against the question names
 *  the records it was written from; these are all of them, and the closing
 *  block says which is which. */
export function SupportingItems({ resource, question, onOpen, onBack }: {
  resource: MagnetResource
  /** The question these are offered against, in its own saved words. */
  question: string
  onOpen(ref: string): void
  onBack(): void
}) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const named = usePeople()
  const { posts, files } = retainedItems(resource)
  const items = [...posts, ...files]
  return <section className="q2p-supporting" aria-label="Supporting items">
    <div className="mgd-row mgd-spread">
      <button type="button" className="mgd-link mgd-small" onClick={onBack}>← Back to answer</button>
    </div>
    <h3 className="mgd-h2">Supporting items</h3>
    <p className="mgd-p mgd-muted">{question ? <>For “{question}”</> : 'For the question being explored'}</p>
    {items.length ? items.map((r) => <div className="mgd-item" key={`${r.kind}:${r.id}`}>
      <div className="mgd-row mgd-spread"><b>{resultTitle(r)}</b><span className="mgd-subtle">{rowByline(r, named)}</span></div>
      {resultPreview(r) && <p>“{resultPreview(r)}”</p>}
      <button type="button" className="mgd-link mgd-small" onClick={() => onOpen(r.id)}>Open item ↗</button>
    </div>)
      : <p className="mgd-p mgd-muted">{s.activation ? 'Nothing is collected here to explore this question against yet.'
        : 'This Magnet has collected nothing yet. Choose sources in Settings, then collect.'}</p>}
    <div className="mgd-space" />
    <div className="mgd-shade">
      <b>Why these?</b>
      <p className="mgd-small mgd-muted">{SUPPORTING_WHY}</p>
    </div>
  </section>
}

/** PAST QUESTIONS (`08-history`), and the one route to everything that only
 *  ADMINISTERS a question: the durable lens, revising, challenging, renaming,
 *  retiring, resuming, and the recorded wording history with its pagination and
 *  its provenance. Each is shut until it is asked for; none of it was removed
 *  to make the resting surface quiet. */
export function PastQuestions({ resource, canWrite, onEvidence, onNew, onOpened }: {
  resource: MagnetResource
  canWrite: boolean
  onEvidence(ref: string): void
  /** Leave for the compose box with nothing asked. */
  onNew(): void
  /** A question was chosen: the working area goes back to it. */
  onOpened(): void
}) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const at = useMemo(() => panelAt(resource), [resource])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const { message, setMessage, busy, run } = useAction()
  const [editor, setEditor] = useState<'revision' | 'rename' | null>(null)
  const [find, setFind] = useState('')
  const viewed = s.viewedDetail, saved = viewed?.current_question
  const topic = viewed?.perspective ?? ''
  // Each draft slot is its own; an absent slot shows the durable wording, and
  // typing into one never reaches another Perspective's slot or the message draft.
  const question = topic in drafts.revisions ? drafts.revisions[topic] : saved?.text ?? ''
  const rename = topic in drafts.renames ? drafts.renames[topic] : viewed?.name ?? ''
  const history = [...s.events].reverse()        // the durable events, newest first
  const past = pastQuestions(s.rows, find)
  const mayWrite = canWrite && !busy && !s.pending
  const act = async (kind: string, data: Record<string, unknown>) => {
    await store.lifecycle(kind, data)
    setMessage(store.snapshot().error ?? 'Saved. No agent or collection was started.')
  }
  /** Escape closes the editor it is pressed in and keeps its words. */
  const suspend = (e: { key: string; stopPropagation(): void }) => { if (e.key === 'Escape') { e.stopPropagation(); setEditor(null) } }

  return <div className="q2p-past">
    <div className="mgd-row mgd-spread">
      <span className="mgd-eyebrow">Perspectives</span>
      <button type="button" className="mgd-link mgd-small" onClick={onNew}>＋ New question</button>
    </div>
    <h3 className="mgd-h2">Past questions</h3>
    <p className="mgd-p mgd-muted">Return to a question and continue the conversation.</p>
    {s.rows.length > 0 && <input type="search" className="mgd-search" aria-label="Find a question" placeholder="Find a question" value={find} onChange={(e) => setFind(e.target.value)} />}
    {past.length ? <ul className="q2p-rows">{past.map((p) => <li key={p.perspective}>
      <button type="button" className="mgd-item q2p-row" aria-current={p.perspective === (s.viewed ?? s.selected) ? 'true' : undefined} disabled={busy} onClick={() => void run(async () => { await store.view(p.perspective); onOpened() })}>
        <span className="q2p-row-text"><b>{p.current_question?.text || p.name}</b><span className="mgd-subtle">{questionSubtitle(p, s.selected)}</span></span>
        <span className="mgd-link" aria-hidden="true">→</span>
      </button>
    </li>)}</ul>
      : <p className="mgd-p mgd-muted">{s.rows.length ? 'No saved question matches those words.' : 'No questions saved here yet.'}</p>}
    {s.listNext && <button type="button" className="mgd-link mgd-small" disabled={busy} onClick={() => void run(() => store.read(s.listNext!))}>More questions</button>}
    <div className="mgd-space" />
    <p className="mgd-subtle">Open a question to revisit its conversation. <button type="button" className="mgd-link" onClick={onOpened}>Back to current →</button></p>

    {s.pending && <p role="status">Uncertain {s.pending.kind} action for {s.pending.target ?? 'a new question'}; its original wording, target and operation key are kept. <button type="button" disabled={!canWrite || busy} onClick={() => void run(async () => { await store.retryPending(); setMessage(store.snapshot().error ?? 'Original question action saved.') })}>Retry unchanged question action</button></p>}
    {(message || s.error) && <p role="status">{message || s.error}</p>}

    <details className="q2-magnet-secondary-actions q2-magnet-config" aria-label="Manage this question" onKeyDown={suspend}>
      <summary>{viewed ? <>More about “{viewed.name}”</> : 'More about a question'}</summary>
      <LensSelector resource={resource} canWrite={canWrite && !busy} />
      {viewed && <>
        <p className="mgd-muted">Viewing this question does not select it as the active Perspective.</p>
        <p>Saved wording: {saved?.text}</p>
        <p className="mgd-muted">Saved revision: {saved?.revision}</p>
        <fieldset disabled={!mayWrite}>
          {editor === 'revision'
            ? <><label>Question or hypothesis<textarea aria-label="Edit saved question" value={question} onChange={(e) => setRevisionDraft(at, topic, e.target.value)} /></label>
              <p>{question !== saved?.text ? 'Unsaved edits' : 'Matches saved current question'}</p>
              <label>Reason<input aria-label="Revision reason" value={drafts.reason} onChange={(e) => setReasonDraft(at, e.target.value)} /></label>
              <button type="button" disabled={!question.trim() || question === saved?.text} onClick={() => void run(async () => { await act('question', { text: question, reason: drafts.reason }); if (!store.snapshot().pending) clearRevisionDraft(at, topic) })}>Save question revision</button>
              <button type="button" disabled={!question.trim()} onClick={() => void run(() => act('challenge', { text: question, reason: drafts.reason }))}>Record challenge</button>
              <button type="button" onClick={() => { clearRevisionDraft(at, topic); setEditor(null) }}>Cancel question edit</button></>
            : <button type="button" onClick={() => setEditor('revision')}>Edit saved question{topic in drafts.revisions && drafts.revisions[topic] !== saved?.text ? ' (unsaved edits kept)' : ''}</button>}
          {editor === 'rename'
            ? <><label>Perspective name<input aria-label="Perspective name" value={rename} onChange={(e) => setRenameDraft(at, topic, e.target.value)} /></label>
              <p className="mgd-muted">A name is a label only. The question, its saved identity and the durable selection do not change, and earlier names stay in history.</p>
              <button type="button" disabled={!rename.trim() || rename === viewed.name} onClick={() => void run(async () => { await act('rename', { name: rename }); if (!store.snapshot().pending) clearRenameDraft(at, topic) })}>Save name</button>
              <button type="button" onClick={() => { clearRenameDraft(at, topic); setEditor(null) }}>Cancel rename</button></>
            : <button type="button" onClick={() => setEditor('rename')}>Rename this Perspective{topic in drafts.renames && drafts.renames[topic] !== viewed.name ? ' (unsaved name kept)' : ''}</button>}
          <button type="button" onClick={() => void run(() => act(viewed.retired ? 'resume' : 'retire', { reason: drafts.reason }))}>{viewed.retired ? 'Resume Perspective' : 'Retire Perspective'}</button>
        </fieldset>
      </>}
    </details>

    <details className="q2-magnet-secondary-actions q2-magnet-config" aria-label="Wording history">
      <summary>Wording history{history.length ? ` (${history.length}${s.next ? '+' : ''})` : ''}</summary>
      <p className="mgd-muted">Newest first. These are earlier wordings and names only: they do not change what is currently saved, and they carry no current qualification.</p>
      <button type="button" className="mgd-link mgd-small" disabled={busy} onClick={() => void run(async () => { await store.read(); if (s.viewed ?? s.selected) await store.view((s.viewed ?? s.selected)!) })}>Refresh wording history</button>
      <ul className="q2-magnet-items">{history.map((e) => <li key={e.post}><strong>{EVENT_WORDS[e.event] ?? e.event}</strong>{wordingOf(e) !== null && <p>{wordingOf(e)}</p>}<details><summary>The exact version, and where it came from</summary><button type="button" className="mgd-link mgd-small" onClick={() => onEvidence(e.snapshot.ref)}>View this earlier wording as it was recorded</button><p>{e.snapshot.ref} · {e.snapshot.digest}</p>{e.data.answer?.ref && <button type="button" onClick={() => onEvidence(e.data.answer.ref)}>View the recorded answer</button>}</details></li>)}</ul>
      {s.next && <button type="button" disabled={busy} onClick={() => void run(() => store.history(s.next!))}>More wording history</button>}
      {!s.next && s.historyComplete && <p className="mgd-muted">All recorded wording for this Perspective is shown.</p>}
    </details>

    {/* THE PERMANENTLY DISABLED "Answer from selected evidence" PRESS IS GONE,
        with the server reason it carried. Answering works, and the press that
        does it sits beside the question it answers. What remains here is the
        disclosure: what an answer is grounded in, and what a recorded answer
        is not. */}
    <details className="q2-magnet-secondary-actions q2-magnet-config" aria-label="What an answer here is grounded in">
      <summary>What an answer here is grounded in</summary>
      <p className="mgd-muted">{PERSPECTIVE_DISCLOSURE}</p>
      <p className="mgd-muted">Earlier wordings and recorded answers have no automatic knowledge standing.</p>
    </details>
  </div>
}

export default function Perspectives({ resource, canWrite, onEvidence }: { resource: MagnetResource; canWrite: boolean; onEvidence(ref: string): void }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const at = useMemo(() => panelAt(resource), [resource])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const { message, setMessage, busy, run } = useAction()
  // One place at a time: asking and its answer, the items that could inform it,
  // or the questions already asked. Each gives the working area straight back.
  const [place, setPlace] = useState<'current' | 'support' | 'past'>('current')
  const [helping, setHelping] = useState(false)
  const ask = useRef<HTMLTextAreaElement>(null)
  const suggested = derivedPerspectiveName(drafts.question)
  const suggestion = tryAsking(resource)
  // The list is what makes `Past questions ▾` offerable at all, so this view
  // asks for it itself rather than depending on a control that may not be open.
  useEffect(() => { void store.read() }, [store])
  useEffect(() => { if (!s.viewed && s.selected) void store.view(s.selected).catch((e) => setMessage(e.message)) }, [s.viewed, s.selected, store, setMessage])
  const told = recordedUnderstanding(s.events)   // what the record holds, derived from nothing
  const recordedAnswers = answerHistory(s.events)
  const [frozenAnswers, setFrozenAnswers] = useState<Record<string, { post: string; words: string }>>({})
  useEffect(() => {
    let live = true
    const events = [recordedAnswers.current, ...recordedAnswers.superseded].filter((e): e is InquiryEvent => !!e && agentWritten(e))
    setFrozenAnswers({})
    for (const event of events) void readStandingBriefing(store, event)
      .then((got) => { if (live) setFrozenAnswers((old) => ({ ...old, [event.post]: got })) })
      .catch((e: Error) => { if (live) setMessage(`Could not display the recorded answer: ${e.message}`) })
    return () => { live = false }
  }, [s.events, store, setMessage])
  const displayAnswer = (e: InquiryEvent | null) => {
    if (!e || !agentWritten(e)) return e
    const unread = { ...e, data: { ...e.data, text: '' } }
    return withWords(unread, frozenAnswers[e.post] ?? null)
  }
  const answers = {
    current: displayAnswer(recordedAnswers.current),
    superseded: recordedAnswers.superseded.map((e) => displayAnswer(e)!),
  }
  const viewed = s.viewedDetail
  const asked = viewed?.current_question?.text ?? (s.viewed === s.selected ? s.selectedDetail?.current_question?.text : '') ?? ''
  const mayWrite = canWrite && !busy && !s.pending

  const act = async (kind: string, data: Record<string, unknown>) => {
    await store.lifecycle(kind, data)
    setMessage(store.snapshot().error ?? 'Saved. No agent or collection was started.')
  }
  /** What a press in the compose box records. A first question is created; a
   *  follow-up is a question branched from the one being explored. Both are the
   *  verbs this panel already used, with their existing keys and retries. */
  const record = () => asked
    ? act('branch', { name: derivedPerspectiveName(drafts.question), question: drafts.question, reason: drafts.reason })
    : act('create', { name: suggested, question: drafts.question })
  /** READING THE KEPT QUESTION AGAIN -- the manual and the automatic refresh
   *  are the same one read, and say which of them asked for it. */
  const [readAgain, setReadAgain] = useState('')
  const reread = async (automatic = false) => {
    const found = await store.recheck()
    setReadAgain(found === 'none' ? '' : found === 'changed' ? CHECKED_NEW : automatic ? COLLECTION_MOVED : CHECKED_SAME)
  }
  /* AUTOMATIC REFRESH, ONCE PER CHANGE OF THE COLLECTION. The collected batch
     is the only thing that can change what is understood of a kept question,
     so the panel reads again exactly when the Magnet reports a different one,
     and does nothing at all while it reports the same one. This is not a
     timer, a poll or a retry: one read per observed change, and the first
     value observed is only remembered, never read against. */
  const seen = useRef<{ mark: string | null } | null>(null)
  const collected = useCollectedMark(resource)
  useEffect(() => {
    if (!seen.current) { seen.current = { mark: collected }; return }
    if (seen.current.mark === collected) return
    seen.current = { mark: collected }
    void run(() => reread(true))
    // Only the collected mark may start this: adding the panel's own changing
    // state here would read again for reasons that are not new evidence.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collected])
  /** Save the question, freeze its evidence, and hand it to the Conversation
   *  for the owner to address to an agent. */
  const sendAsk = () => void run(async () => {
    const words = drafts.question
    const existing = miniComposerDraft(resource).text
    if (existing.trim() && existing !== words) throw new Error('The Conversation Composer already has a different draft. Keep or clear it before asking an agent.')
    await record()
    if (store.snapshot().pending) return
    await askAnAgent(resource, store, words)
    clearQuestionDraft(at)
    setMessage('Choose a recipient and press Send in the Conversation to answer this question.')
  })
  /** Ask the saved question of the collection again, without revising it. */
  const answerAgain = () => void run(async () => {
    await askAnAgent(resource, store, asked)
    setMessage('Choose a recipient and press Send in the Conversation to answer this question.')
  })

  /* `q2p-open-past` is the hook the wide layout drops this on: once the aside
     stands beside the work, the list it leads to is already on the surface
     (07-future-expanded.png shows no such link), so offering it again is one
     of the redundant disclosures the owner asked to be rid of. */
  const openPast = <button type="button" className="mgd-link mgd-small q2p-open-past" onClick={() => { setPlace('past'); setHelping(false) }}>Past questions ▾</button>
  const toAsk = () => { setPlace('current'); setHelping(false); setTimeout(() => ask.current?.focus(), 0) }

  /* 06 -- THE SUPPORTING ITEMS TAKE THE WORKING AREA, and give it straight
     back. Opening one goes through the card's one inspection. */
  if (place === 'support') return <section className="q2-magnet-perspectives" aria-label="Perspectives">
    <SupportingItems resource={resource} question={asked} onOpen={onEvidence} onBack={() => setPlace('current')} />
  </section>

  /* 08 -- PAST QUESTIONS, and everything that only administers a question. */
  if (place === 'past') return <section className="q2-magnet-perspectives" aria-label="Perspectives">
    <PastQuestions resource={resource} canWrite={canWrite} onEvidence={onEvidence}
      onNew={toAsk} onOpened={() => setPlace('current')} />
  </section>

  /* THE COMPOSE BOX (`02`, `05`, `09`, `10`). The frame's pinned footer composer
     renders on the Conversation place only, so this box is the panel's own --
     the same ask and send path, in the body where the design puts it. */
  const compose = <fieldset className="q2p-compose-field" disabled={!mayWrite}>
    <div className="mgd-compose">
      <textarea ref={ask} aria-label={asked ? 'Ask a follow-up' : 'Question or hypothesis'}
        placeholder={asked ? 'Ask a follow-up or explore an idea…' : 'What would you like to explore?'}
        value={drafts.question} onChange={(e) => setQuestionDraft(at, e.target.value)} />
      <div className="mgd-row mgd-spread q2p-compose-foot">
        <span className="mgd-subtle">{drafts.question.trim()
          ? <>It will be listed as “{asked ? derivedPerspectiveName(drafts.question) : suggested}”, taken from the question.</>
          : asked ? ORDINARY_DISCUSSION : 'Question or hypothesis'}</span>
        <span className="mgd-row">
          {/* Keeping a question without starting a discussion: offered only
              once there are words to keep, so the resting box is the mockup's. */}
          {drafts.question.trim() && <button type="button" className="mgd-link mgd-small" onClick={() => void run(async () => {
            await record()
            if (!store.snapshot().pending) clearQuestionDraft(at)
          })}>Save for later</button>}
          <button type="button" className="mgd-button" disabled={!drafts.question.trim()} onClick={sendAsk}>{asked ? 'Send ↑' : 'Ask →'}</button>
        </span>
      </div>
    </div>
  </fieldset>

  /* 07 -- THE QUESTIONS ALREADY ASKED, beside the work where there is room. */
  const aside = <aside className="q2p-aside" aria-label="Questions already asked">
    <div className="mgd-row mgd-spread">
      <h4 className="mgd-h3">Past questions</h4>
      <button type="button" className="mgd-link mgd-small" onClick={() => setPlace('past')}>All →</button>
    </div>
    {s.rows.length ? s.rows.slice(0, 4).map((p) => <div className="mgd-item" key={p.perspective}>
      <button type="button" className="q2p-aside-row" disabled={busy} onClick={() => void run(() => store.view(p.perspective))}>
        <b>{p.current_question?.text || p.name}</b>
        <span className="mgd-subtle">{questionSubtitle(p, s.selected)}</span>
      </button>
    </div>) : <p className="mgd-small mgd-muted">No questions saved here yet.</p>}
    <div className="mgd-space" />
    <button type="button" className="mgd-link mgd-small" onClick={toAsk}>＋ Ask something new</button>
    <div className="mgd-divider" />
    <span className="mgd-subtle">{DISCUSSION_READS}</span>
  </aside>

  /* 02 / 05 / 09 / 10 -- THE CURRENT QUESTION, or the invitation to ask one. */
  return <section className="q2-magnet-perspectives" aria-label="Perspectives">
    <div className="q2p-cols">
      <div className="q2p-main">
        {asked ? <>
          {/* 05 / 10: the way back, then one state line saying what this is. */}
          <div className="mgd-row mgd-spread">
            <span />
            {openPast}
          </div>
          <div className="mgd-chatbubble">
            <b className="q2p-asked">{asked}</b>
          </div>
          {/* WHAT IS UNDERSTOOD OF A QUESTION THAT STAYS. One answer stands
              now; the ones it follows are kept under it, never replaced. */}
          <div className="mgd-answer">
            {answers.current || told.challenges.length ? <>
              {answers.current && <>
                {/* THE ANSWER STANDING NOW, DRAWN BY THE ONE RENDERER THERE IS
                    FOR AN ANSWER (owner `ent-bce57ba67f38`: "Use the existing
                    Markdown renderer and display the final answer"). This split
                    the words on newlines and laid every line out as a
                    statement, so an agent's written briefing arrived here as a
                    stack of one-line paragraphs with its `##` headings, its
                    table pipes and its citation tokens as literal text, while
                    the Summary -- reading the same recorded answer -- drew it
                    as the document it is. `Briefing` is that reading: prose for
                    a written document, the statement-and-quotation layout for a
                    statement-per-line synthesis, citations as numbers with a
                    Sources list, and in both cases the recorded characters. */}
                {answerText(answers.current)
                  ? <>
                      <Briefing resource={resource} answer={answers.current} />
                      {/* THE SAME ICON-ONLY FOOTER TREATMENT AS SUMMARY
                          (approved mockup round 4, `06-perspectives-finished.png`),
                          below a hairline divider: view the records this answer
                          rests on, or discuss it, rather than the permanent
                          "Explore supporting items ↗" text link this answer
                          used to carry on the surface. */}
                      <div className="mgd-divider" />
                      <div className="mgd-row mgd-spread q2p-answer-icons">
                        <span className="mgd-subtle">{readAgain}</span>
                        <span className="mgd-row">
                          <button type="button" className="q2-magnet-icon" aria-label="Explore supporting items" title="Explore supporting items"
                            onClick={() => setPlace('support')}><span aria-hidden="true">👁</span></button>
                          <button type="button" className="q2-magnet-icon" aria-label="Discuss this in the Conversation" title="Discuss this in the Conversation"
                            disabled={busy || !mayWrite} onClick={() => void run(() => takeToConversation(resource, store))}><span aria-hidden="true">💬</span></button>
                        </span>
                      </div>
                    </>
                  : agentWritten(answers.current) ? <BuildingOverview /> : <p className="mgd-p">An answer is recorded against this question.</p>}
              </>}
              {told.challenges.map((e) => <p key={`c:${e.post}`}><span className="mgd-subtle">Recorded challenge · </span><Linked text={wordingOf(e) ?? ''} /></p>)}
            </> : <>
              <p>{NOTHING_RECORDED_YET}</p>
              <button type="button" className="mgd-button" disabled={!mayWrite} onClick={answerAgain}>Ask an agent to answer</button>
            </>}
            {answers.superseded.length > 0 && <details className="q2p-answer-history">
              <summary>{EARLIER_ANSWERS} ({answers.superseded.length})</summary>
              <ol className="q2p-answers">{answers.superseded.map((e, i) => <li key={`s:${e.post}`}>
                <span className="mgd-subtle">{EARLIER_ANSWERS} {answers.superseded.length - i}</span>
                {/* An earlier answer is a whole answer. It is read exactly as
                    the one standing now, by the same renderer, and is still the
                    characters that were recorded. */}
                {answerText(e)
                  ? <Briefing resource={resource} answer={e} />
                  : <p className="mgd-p">{agentWritten(e) ? 'The recorded answer is being checked before display.' : 'An answer is recorded against this question.'}</p>}
                <button type="button" className="mgd-link mgd-small" onClick={() => onEvidence(e.data.answer?.ref ?? e.snapshot.ref)}>View it as it was recorded</button>
              </li>)}</ol>
            </details>}
            {/* EVERYTHING SECONDARY TO READING THE ANSWER IS BEHIND ONE
                DISCLOSURE (owner `ent-15a36a065eb8`: "Keep secondary actions
                and provenance available through progressive disclosure").
                What stands on the surface is the question, the answer, and the
                one press that goes to the records the answer rests on. What
                opens here is what a reader asks for only when they want it:
                what the answer was grounded in, who wrote it, the recorded
                answer itself, and the three presses that act on it -- answering
                again, reading the question again, and taking it to the
                Conversation. Nothing was deleted; each is the same press, with
                the same guard, in one place instead of three rows. */}
            <details className="q2p-about q2-magnet-disclosure">
              <summary><span className="mgd-link mgd-small">{ABOUT_THIS_ANSWER} ▾</span></summary>
              <div aria-label="What this answer rests on, and what can be done with it">
                {!!answers.current && <>
                  <AnswerGrounding answer={answers.current} />
                  <p className="mgd-small mgd-muted">{ANSWER_WRITTEN_BY(answers.current)}
                    {answers.current.data.answer?.ref && <> <button type="button" className="mgd-link mgd-small" onClick={() => onEvidence(answers.current!.data.answer.ref)}>View the recorded answer</button></>}</p>
                  {/* Asking the saved question of the collection again, beside
                      the answer it would supersede. */}
                  <button type="button" className="mgd-link mgd-small" disabled={!mayWrite} onClick={answerAgain}>Answer again from this collection</button>
                </>}
                {/* The manual half of refresh, beside the answer it refreshes. */}
                <button type="button" className="mgd-link mgd-small" disabled={busy} onClick={() => void run(() => reread())}>{READ_AGAIN}</button>
                {/* ONE PRESS FROM THIS QUESTION INTO THE MAGNET'S CONVERSATION
                    (owner `opr-85178afc5f3a`): it makes this question the
                    active one if it is not, and copies its own saved words into
                    the Conversation's Composer at the version this card is
                    showing. It was a filled button standing permanently under
                    the answer; it is the same press, offered here. */}
                <button type="button" className="mgd-link mgd-small" disabled={busy || !mayWrite} onClick={() => void run(() => takeToConversation(resource, store))}>{TAKE_TO_CONVERSATION} →</button>
              </div>
            </details>
          </div>
          <div className="mgd-space" />
          {compose}
          <p className="mgd-hint">{DISCUSSION_READS}</p>
        </> : <>
          {/* 02 / 09: nothing asked yet. THE PLACE NAME IS SAID ONCE: the
              card's own tab bar already reads `Perspectives`, so the eyebrow
              that repeated it under the tab is one of the redundant headings
              the owner asked to be rid of (`ent-15a36a065eb8`). What leads the
              surface is what the reader is here to do. */}
          <div className="mgd-row mgd-spread q2p-head">
            <h3 className="mgd-h2">Explore a question</h3>
            {openPast}
          </div>
          <p className="mgd-p mgd-muted">Ask a question or share an idea to discuss.</p>
          {compose}
          <div className="mgd-space" />
          {helping
            ? <div className="mgd-help">
              <div className="mgd-row mgd-spread"><b>{HELP_TITLE}</b><button type="button" className="mgd-link" aria-label="Close what I can do today" onClick={() => setHelping(false)}>×</button></div>
              <p className="mgd-small">{HELP_WORDS}</p>
              <div className="mgd-row">
                <button type="button" className="mgd-button mgd-secondary" onClick={() => goTab(resource, 'All')}>Browse collection →</button>
                <button type="button" className="mgd-link mgd-small" onClick={() => setHelping(false)}>Continue here</button>
              </div>
            </div>
            : <>
              <div className="mgd-subtle">TRY ASKING</div>
              <p className="mgd-example">{suggestion} <button type="button" className="mgd-link" aria-label={`Ask: ${suggestion}`} disabled={!mayWrite} onClick={() => { setQuestionDraft(at, suggestion); setTimeout(() => ask.current?.focus(), 0) }}>↗</button></p>
              <div className="mgd-divider" />
              <div className="mgd-row">
                <span className="mgd-today">{AVAILABLE_NOW}</span>
                <span className="mgd-subtle">{ORDINARY_CONVERSATION}</span>
              </div>
              <p className="mgd-small mgd-muted">{DISCUSSION_READS} <button type="button" className="mgd-link" onClick={() => setHelping(true)}>What can I do?</button></p>
            </>}
        </>}
        {s.pending && <p role="status">Uncertain {s.pending.kind} action for {s.pending.target ?? 'a new question'}; its original wording, target and operation key are kept. <button type="button" disabled={!canWrite || busy} onClick={() => void run(async () => { await store.retryPending(); setMessage(store.snapshot().error ?? 'Original question action saved.') })}>Retry unchanged question action</button></p>}
        {(message || s.error) && <p role="status">{message || s.error}</p>}
      </div>
      {aside}
    </div>
  </section>
}
