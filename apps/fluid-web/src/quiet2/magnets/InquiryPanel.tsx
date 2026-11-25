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
 *  **Grounded synthesis stays refused.** Nothing here implies an agent read the
 *  collected material. The supporting items carry the `FUTURE CONCEPT` mark and
 *  say in their own block that choosing and citing support is part of grounded
 *  answering, which does not work yet; the question surface carries one hint
 *  saying so once. The disabled affordance keeps the server's own reason
 *  (`PERSPECTIVE_BLOCK_REASON`).
 *
 *  Selection is durable -- a `selected` event, not UI state -- and `canWrite` is
 *  passed through exactly as it is given: no box, press or editor here offers a
 *  write the server would refuse. */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import {
  derivedPerspectiveName, pastQuestions, perspectivesOf, questionSubtitle, recordedUnderstanding,
  stampAttachedQuestion, EVENT_WORDS, FUTURE_CONCEPT, GROUNDED_NOT_YET, NOTHING_RECORDED_YET,
  PERSPECTIVE_DISCLOSURE, PERSPECTIVE_BLOCK_REASON, SUPPORTING_WHY,
  type InquiryEvent, type PerspectiveStore,
} from './perspectives'
import { retainedItems, resultPreview, resultTitle, rowByline, usePeople } from './EvidenceViews'
import { miniComposerDraft, saveMiniComposer } from './conversation'
import { goTab, setOpen } from './places'
import {
  clearRenameDraft, clearRevisionDraft, clearQuestionDraft, panelAt, panelDrafts,
  setQuestionDraft, setReasonDraft, setRenameDraft, setRevisionDraft, subscribePanelDrafts,
} from './panelDrafts'
import './design.css'
import './configuration.css'
import './summary.css'
import './perspectives.css'

/** Discussing a saved question is ordinary discussion of the question. While a
 *  Perspective is selected the Composer keeps the reading choice ordinary, so
 *  say that here rather than let the owner infer the collection was read. */
export const DISCUSS_IS_ORDINARY = 'Ordinary discussion of the saved question. The collected records are not read to answer it: grounded Perspective answering is unavailable.'

/** The one sentence about what discussion reads, said once on the resting
 *  surface and nowhere else (owner: not three times). */
export const DISCUSSION_READS = 'Discussion does not read your collected items.'
/** The chips, where the mockups put them. */
export const AVAILABLE_NOW = 'AVAILABLE NOW', CURRENT_MODE = 'CURRENT MODE'
export const ORDINARY_CONVERSATION = 'Ordinary Conversation', ORDINARY_DISCUSSION = 'Ordinary discussion'
/** `09-current-help`: the one "what can I do today" panel, opened by a link. */
export const HELP_TITLE = 'What can I do today?'
export const HELP_WORDS = 'You can discuss a question now, or browse collected items yourself. Discussion does not read those items to form its answer.'
/** `02-compact-current`: something to ask when nothing has been asked. */
export const TRY_ASKING = 'What might be slowing our releases?'

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

/** THE SUPPORTING ITEMS (`06-future-support`). The Magnet's own collected
 *  records, listed against the question so the owner can read them THEMSELVES.
 *  The `FUTURE CONCEPT` mark and the closing block say what this is not: no
 *  agent chose these, and nothing read them to answer anything. */
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
      <span className="mgd-future">{FUTURE_CONCEPT.toUpperCase()}</span>
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

    <details className="q2-magnet-secondary-actions q2-magnet-config" aria-label="What this cannot do yet">
      <summary>What this cannot do yet</summary>
      <div className="q2-magnet-grounding">
        <button type="button" className="mgd-button mgd-secondary" disabled aria-describedby="inquiry-grounded-status">Answer from selected evidence</button>
        <span id="inquiry-grounded-status" className="mgd-muted" role="status">{PERSPECTIVE_BLOCK_REASON}</span>
      </div>
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
  // The list is what makes `Past questions ▾` offerable at all, so this view
  // asks for it itself rather than depending on a control that may not be open.
  useEffect(() => { void store.read() }, [store])
  useEffect(() => { if (!s.viewed && s.selected) void store.view(s.selected).catch((e) => setMessage(e.message)) }, [s.viewed, s.selected, store, setMessage])
  const told = recordedUnderstanding(s.events)   // what the record holds, derived from nothing
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
  /** The one press that asks: record the question, then carry its own saved
   *  words into the Conversation, which is where discussion happens. */
  const sendAsk = () => void run(async () => {
    await record()
    if (store.snapshot().pending) return
    clearQuestionDraft(at)
    await discussSelectedQuestion(resource, store)
  })

  const openPast = <button type="button" className="mgd-link mgd-small" onClick={() => { setPlace('past'); setHelping(false) }}>Past questions ▾</button>
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
    <span className="mgd-subtle">{GROUNDED_NOT_YET}</span>
  </aside>

  /* 02 / 05 / 09 / 10 -- THE CURRENT QUESTION, or the invitation to ask one. */
  return <section className="q2-magnet-perspectives" aria-label="Perspectives">
    <div className="q2p-cols">
      <div className="q2p-main">
        {asked ? <>
          {/* 05 / 10: the way back, then one state line saying what this is. */}
          <div className="mgd-row mgd-spread">
            <span className="mgd-eyebrow">Perspectives</span>
            {openPast}
          </div>
          <div className="mgd-row q2p-state">
            <span className="mgd-today">{CURRENT_MODE}</span>
            <span className="mgd-subtle">{ORDINARY_DISCUSSION}</span>
          </div>
          <div className="mgd-chatbubble">
            <span className="mgd-subtle">You asked</span>
            <b className="q2p-asked">{asked}</b>
          </div>
          <div className="mgd-answer">
            <b>Current understanding</b>
            {told.answers.length || told.challenges.length ? <>
              {told.answers.map((e) => <p key={`a:${e.post}`}>{wordingOf(e) ?? 'An answer is recorded against this question.'}
                {e.data.answer?.ref && <> <button type="button" className="mgd-link mgd-small" onClick={() => onEvidence(e.data.answer.ref)}>View the recorded answer</button></>}</p>)}
              {told.challenges.map((e) => <p key={`c:${e.post}`}><span className="mgd-subtle">Recorded challenge · </span>{wordingOf(e) ?? ''}</p>)}
            </> : <p>{NOTHING_RECORDED_YET}</p>}
            <button type="button" className="mgd-link mgd-small" onClick={() => setPlace('support')}>Explore supporting items ↗</button>
          </div>
          <div className="mgd-space" />
          {compose}
          <p className="mgd-hint">{GROUNDED_NOT_YET}</p>
        </> : <>
          {/* 02 / 09: nothing asked yet. */}
          <div className="mgd-row mgd-spread q2p-head">
            <div>
              <div className="mgd-eyebrow">Perspectives</div>
              <h3 className="mgd-h2">Explore a question</h3>
            </div>
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
              <p className="mgd-example">{TRY_ASKING} <button type="button" className="mgd-link" aria-label={`Ask: ${TRY_ASKING}`} disabled={!mayWrite} onClick={() => { setQuestionDraft(at, TRY_ASKING); setTimeout(() => ask.current?.focus(), 0) }}>↗</button></p>
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
