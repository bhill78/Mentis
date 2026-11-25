/** The Perspectives view: a place to ask a question and develop an
 *  understanding of it, and the one approved home of the lens selector.
 *
 *  **Ordinary question language.** The owner's language review of the whole
 *  interface (ent-3191baeb33d2 §2, "Question rather than inquiry wording")
 *  governs every word this panel shows: no control, option, label or message
 *  here says "inquiry". A Perspective is still a Perspective where that is what
 *  it is, because it is the owner's own word; what the owner switches between,
 *  creates, branches and reads the history of is a question.
 *
 *  **What occupies the working area** (owner ent-068c167fa7e6 §3, over the
 *  approved round-3 mockups ent-1c71c6d681ea). The question being explored, the
 *  current understanding of it, and the next useful things to do with it --
 *  ask a follow-up, discuss it, look at what could inform it. Those are the
 *  only things rendered open.
 *
 *  **What is reachable but not occupying it.** Past questions, the supporting
 *  items, everything that only *administers* a question (revising,
 *  challenging, renaming, retiring) and the recorded wording history are each
 *  behind a disclosure or an "on request" press, as the mockups open them.
 *  Nothing was removed to make the room: every verb this panel had, it still
 *  has, in the same one-door store.
 *
 *  **The question still comes first** where there is no question yet: with
 *  nothing selected the panel opens on the box you write one in, and one press
 *  turns it into a Perspective. There is no name field, because the client
 *  derives the suggested name from the question and sends both to the existing
 *  create route, which requires a name. There is no separate question-shaping
 *  screen either: revising is an inline editor among the demoted controls, and
 *  a follow-up is a question branched from this one.
 *
 *  Selection is durable -- it is a `selected` event, not UI state -- and the
 *  wording history below is read from the durable events, newest first, and
 *  labelled as wording only.
 *
 *  Renaming is optional and durable: it is H6's `rename` verb, which appends an
 *  event and changes the display name only. The Topic identity, the question and
 *  the durable selection are untouched by it.
 *
 *  Grounded synthesis stays refused. The affordance is rendered disabled with
 *  the server's own reason, as the Summary does; nothing here implies an agent
 *  read the collected material, and the one place this panel shows the shape of
 *  that future state it is marked "future concept" and says so (`FUTURE_CONCEPT`,
 *  `GROUNDED_NOT_YET`). */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import {
  derivedPerspectiveName, pastQuestions, perspectivesOf, questionSubtitle, recordedUnderstanding,
  stampAttachedQuestion, EVENT_WORDS, FUTURE_CONCEPT, GROUNDED_NOT_YET, NOTHING_RECORDED_YET,
  PERSPECTIVE_DISCLOSURE, PERSPECTIVE_BLOCK_REASON, type PerspectiveStore,
} from './perspectives'
import { SupportingItems } from './EvidenceViews'
import { miniComposerDraft, saveMiniComposer } from './conversation'
import { goTab, setOpen } from './places'
import {
  clearRenameDraft, clearRevisionDraft, clearQuestionDraft, panelAt, panelDrafts,
  setQuestionDraft, setReasonDraft, setRenameDraft, setRevisionDraft, subscribePanelDrafts,
} from './panelDrafts'
import './configuration.css'
import './summary.css'
import './perspectives.css'

/** Discussing a saved question is ordinary discussion of the question. While a
 *  Perspective is selected the Composer keeps the reading choice ordinary, so
 *  say that here rather than let the owner infer the collection was read. */
export const DISCUSS_IS_ORDINARY = 'Ordinary discussion of the saved question. The collected records are not read to answer it: grounded Perspective answering is unavailable.'

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

/** The future state the mockups show, marked as what it is. It states the
 *  absence; it never stands in for an answer. */
function FutureMark() {
  return <p className="q2-magnet-future">
    <span className="q2-magnet-future-badge">{FUTURE_CONCEPT}</span>
    <span className="q2-magnet-muted">{GROUNDED_NOT_YET}</span>
  </p>
}

export function LensSelector({ resource, canWrite }: { resource: MagnetResource; canWrite: boolean }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const [error, setError] = useState('')
  useEffect(() => { void store.read() }, [store])
  return <div className="q2-magnet-lens"><label>Active question<select aria-label="Active question" value={s.selected ?? ''} disabled={!canWrite || s.loading || !!s.pending} onChange={(e) => { setError(''); void store.select(e.target.value || null).catch((e) => setError(e.message)) }}><option value="">No question — ordinary Conversation</option>{s.rows.filter((p) => !p.retired || p.perspective === s.selected).map((p) => <option key={p.perspective} value={p.perspective}>{p.name}</option>)}</select></label>{s.listNext && <button type="button" className="q2-magnet-link" onClick={() => void store.read(s.listNext!)}>More questions</button>}{(error || s.error) && <p role="status">{error || s.error}</p>}</div>
}

export default function Perspectives({ resource, canWrite, onEvidence }: { resource: MagnetResource; canWrite: boolean; onEvidence(ref: string): void }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const at = useMemo(() => panelAt(resource), [resource])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const [editor, setEditor] = useState<'revision' | 'rename' | null>(null)
  // Opened on request, and only one of them at a time: the supporting items
  // take the working area the way the mockups open them, and give it back.
  const [opened, setOpened] = useState<'support' | null>(null)
  const [find, setFind] = useState(''), [browsing, setBrowsing] = useState(false)
  const ask = useRef<HTMLTextAreaElement>(null)
  const viewed = s.viewedDetail, saved = viewed?.current_question
  const topic = viewed?.perspective ?? ''
  // Each draft slot is its own; an absent slot shows the durable wording, and
  // typing into one never reaches another Perspective's slot or the message draft.
  const question = topic in drafts.revisions ? drafts.revisions[topic] : saved?.text ?? ''
  const rename = topic in drafts.renames ? drafts.renames[topic] : viewed?.name ?? ''
  const suggested = derivedPerspectiveName(drafts.question)
  useEffect(() => { if (!s.viewed && s.selected) void store.view(s.selected).catch((e) => setMessage(e.message)) }, [s.viewed, s.selected, store])
  const run = async (fn: () => Promise<unknown>) => { if (busy) return; setBusy(true); setMessage(''); try { await fn() } catch (e) { setMessage((e as Error).message) } finally { setBusy(false) } }
  const act = async (kind: string, data: Record<string, unknown>) => {
    await store.lifecycle(kind, data)
    setMessage(store.snapshot().error ?? 'Saved. No agent or collection was started.')
  }
  /** Escape closes the editor it is pressed in and keeps its words. */
  const suspend = (e: { key: string; stopPropagation(): void }) => { if (e.key === 'Escape') { e.stopPropagation(); setEditor(null) } }
  const history = [...s.events].reverse()        // the durable events, newest first
  const wording = (e: typeof s.events[number]) => typeof e.data.text === 'string' ? e.data.text : typeof e.data.name === 'string' ? e.data.name : null
  const told = recordedUnderstanding(s.events)   // what the record holds, derived from nothing
  const past = pastQuestions(s.rows, find)
  const asked = viewed?.current_question?.text ?? (s.viewed === s.selected ? s.selectedDetail?.current_question?.text : '') ?? ''

  /* THE SUPPORTING ITEMS TAKE THE WORKING AREA WHILE THEY ARE OPEN, and give it
     straight back (mockup 06). Opening one of them goes through the card's one
     inspection, which is where an item is read with its one way back. */
  if (opened === 'support') return <section className="q2-magnet-config q2-magnet-perspectives" aria-label="Perspectives">
    <div className="q2-magnet-section-title">
      <button type="button" className="q2-magnet-link" onClick={() => setOpened(null)}>← Back to the question</button>
    </div>
    <SupportingItems resource={resource} question={asked} onOpen={onEvidence} />
  </section>

  return <section className="q2-magnet-config q2-magnet-perspectives" aria-label="Perspectives">
    <div className="q2-magnet-section-title">
      <div><p className="q2-magnet-eyebrow">Perspectives</p><h3 id="inquiry-title" tabIndex={-1}>{browsing ? 'Past questions' : asked ? 'Your question' : 'Explore a question'}</h3></div>
      {s.rows.length > 0 && <button type="button" className="q2-magnet-link" onClick={() => setBrowsing(!browsing)}>{browsing ? 'Back to current ?' : 'Past questions ?'}</button>}
    </div>

    <div className="q2-magnet-work">
      {!browsing && <div className="q2-magnet-work-main">

        {/* THE QUESTION BEING EXPLORED, and what is understood of it so far. */}
        {asked ? <>
          <section className="q2-magnet-asked" aria-label="Selected saved question">
            <p className="q2-magnet-eyebrow">You asked</p>
            <p className="q2-magnet-asked-text">{asked}</p>
          </section>
          <section className="q2-magnet-current" aria-label="Current understanding">
            <h4>Current understanding</h4>
            {told.answers.length || told.challenges.length ? <ul className="q2-magnet-items">
              {told.answers.map((e) => <li key={`a:${e.post}`}><strong>Recorded answer</strong>{wording(e) !== null && <p>{wording(e)}</p>}
                {e.data.answer?.ref && <button type="button" className="q2-magnet-link" onClick={() => onEvidence(e.data.answer.ref)}>View the recorded answer</button>}</li>)}
              {told.challenges.map((e) => <li key={`c:${e.post}`}><strong>Recorded challenge</strong>{wording(e) !== null && <p>{wording(e)}</p>}</li>)}
            </ul> : <p className="q2-magnet-muted">{NOTHING_RECORDED_YET}</p>}
            {s.next && <button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void run(() => store.history(s.next!))}>Load earlier answers and history</button>}
            <FutureMark />
            <button type="button" className="q2-magnet-link" onClick={() => setOpened('support')}>Explore supporting items ↗</button>
          </section>
          {/* The one action that carries this question into the Conversation. */}
          <button type="button" className="q2-magnet-primary" disabled={!canWrite || !viewed || viewed.retired || busy || !!s.pending} onClick={() => void run(async () => { if (viewed && viewed.perspective !== s.selected) await store.select(viewed.perspective); await discussSelectedQuestion(resource, store); setMessage('Saved question placed in the shared Composer. Choose an Ask option to start ordinary discussion.') })}>Discuss this question ?</button>
          <p className="q2-magnet-muted">Discussion does not read your collected items.</p>
        </> : <section className="q2-magnet-start" aria-label="Where to start">
          <h4>Explore what you’ve collected</h4>
          <p className="q2-magnet-muted">Ask a question or put a hypothesis in your own words. It is kept with this Magnet, so you can come back to it and to whatever was said about it.</p>
          {/* What discussing a question will and will not do, said once, before
              there is a question to offer it on. */}
          <p className="q2-magnet-muted">Discussion does not read your collected items.</p>
        </section>}

        {/* ASK: one box, one press, no name and no configuration. With a
            question open it is where a follow-up is written. */}
        <section className="q2-magnet-ask" aria-label="Create a Perspective">
          <h4>{viewed ? 'Ask a follow-up' : 'Ask a question'}</h4>
          <fieldset disabled={!canWrite || busy || !!s.pending}>
            <label>New question or hypothesis<textarea ref={ask} aria-label="New question or hypothesis" placeholder={viewed ? 'Ask a follow-up or explore an idea…' : 'Ask a question or explore a hypothesis…'} value={drafts.question} onChange={(e) => setQuestionDraft(at, e.target.value)} /></label>
            <p className="q2-magnet-muted">{drafts.question.trim() ? <>It will be listed as “{suggested}”, taken from the question. You are not asked for a separate name.</> : 'The question is the Perspective. Its name is taken from the question when you create it.'}</p>
            <div className="q2-magnet-ask-actions">
              <button type="button" className="q2-magnet-primary" disabled={!drafts.question.trim()} onClick={() => void run(async () => {
                await act('create', { name: suggested, question: drafts.question })
                if (!store.snapshot().pending) { clearQuestionDraft(at); await discussSelectedQuestion(resource, store) }
              })}>Ask ?</button>
              <button type="button" disabled={!drafts.question.trim()} onClick={() => void run(async () => {
                await act('create', { name: suggested, question: drafts.question })
                if (!store.snapshot().pending) clearQuestionDraft(at)
              })}>Save for later</button>
              {/* A follow-up IS a question branched from this one: the same verb,
                  offered where a follow-up is written rather than under the
                  administrative heading. */}
              {viewed && <button type="button" disabled={!drafts.question.trim()} onClick={() => void run(() => act('branch', { name: derivedPerspectiveName(drafts.question), question: drafts.question, reason: drafts.reason }))}>Branch a new question from this one</button>}
            </div>
          </fieldset>
        </section>
      </div>}

      {/* PAST QUESTIONS, beside the work where there is room and under it where
          there is not. Returning to one is a press; which one is durably active
          stays the lens's own choice. */}
      {browsing && <aside className="q2-magnet-past" aria-label="Past questions">
        <p className="q2-magnet-muted">Return to a question and see what was recorded.</p>
        {s.rows.length > 0 && <label>Find a question<input type="search" aria-label="Find a question" value={find} onChange={(e) => setFind(e.target.value)} /></label>}
        {past.length ? <ul className="q2-magnet-past-list">{past.map((p) => <li key={p.perspective}>
          <button type="button" className="q2-magnet-past-row" aria-current={p.perspective === (s.viewed ?? s.selected) ? 'true' : undefined} disabled={busy} onClick={() => void run(async () => { await store.view(p.perspective); setBrowsing(false) })}>
            <span className="q2-magnet-row-text"><strong>{p.current_question?.text || p.name}</strong><small className="q2-magnet-muted">{questionSubtitle(p, s.selected)}</small></span>
            <span aria-hidden="true">→</span>
          </button>
        </li>)}</ul>
          : <p className="q2-magnet-muted">{s.rows.length ? 'No saved question matches those words.' : 'No questions saved here yet.'}</p>}
        {s.listNext && <button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void run(() => store.read(s.listNext!))}>More questions</button>}
        <button type="button" className="q2-magnet-link" onClick={() => { setBrowsing(false); setTimeout(() => ask.current?.focus(), 0) }}>+ Ask something new</button>
        </aside>}
    </div>

    {s.pending && <p role="status">Uncertain {s.pending.kind} action for {s.pending.target ?? 'a new question'}; its original wording, target and operation key are kept. <button type="button" disabled={!canWrite || busy} onClick={() => void run(async () => { await store.retryPending(); setMessage(store.snapshot().error ?? 'Original question action saved.') })}>Retry unchanged question action</button></p>}
    {(message || s.error) && <p role="status">{message || s.error}</p>}

    {/* BELOW THE WORK: what only administers a question, and the wording it
        has had. Both are shut until they are asked for; nothing was removed. */}
    <details className="q2-magnet-secondary-actions" aria-label="Manage this question" onKeyDown={suspend}>
      <summary>{viewed ? <>More about “{viewed.name}”</> : 'More about a question'}</summary>
      <LensSelector resource={resource} canWrite={canWrite && !busy} />
      {viewed && <>
        <p className="q2-magnet-muted">Viewing this question does not select it as the active Perspective.</p>
        <p>Saved wording: {saved?.text}</p>
        <p className="q2-magnet-muted">Saved revision: {saved?.revision}</p>
        <fieldset disabled={!canWrite || busy || !!s.pending}>
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
              <p className="q2-magnet-muted">A name is a label only. The question, its saved identity and the durable selection do not change, and earlier names stay in history.</p>
              <button type="button" disabled={!rename.trim() || rename === viewed.name} onClick={() => void run(async () => { await act('rename', { name: rename }); if (!store.snapshot().pending) clearRenameDraft(at, topic) })}>Save name</button>
              <button type="button" onClick={() => { clearRenameDraft(at, topic); setEditor(null) }}>Cancel rename</button></>
            : <button type="button" onClick={() => setEditor('rename')}>Rename this Perspective{topic in drafts.renames && drafts.renames[topic] !== viewed.name ? ' (unsaved name kept)' : ''}</button>}
          <button type="button" onClick={() => void run(() => act(viewed.retired ? 'resume' : 'retire', { reason: drafts.reason }))}>{viewed.retired ? 'Resume Perspective' : 'Retire Perspective'}</button>
        </fieldset>
      </>}
    </details>

    <details className="q2-magnet-secondary-actions" aria-label="Wording history">
      <summary>Wording history{history.length ? ` (${history.length}${s.next ? '+' : ''})` : ''}</summary>
      <p className="q2-magnet-muted">Newest first. These are earlier wordings and names only: they do not change what is currently saved, and they carry no current qualification.</p>
      <button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void run(async () => { await store.read(); if (s.viewed ?? s.selected) await store.view((s.viewed ?? s.selected)!) })}>Refresh wording history</button>
      <ul className="q2-magnet-items">{history.map((e) => <li key={e.post}><strong>{EVENT_WORDS[e.event] ?? e.event}</strong>{wording(e) !== null && <p>{wording(e)}</p>}<details><summary>The exact version, and where it came from</summary><button type="button" className="q2-magnet-link" onClick={() => onEvidence(e.snapshot.ref)}>View this earlier wording as it was recorded</button><p>{e.snapshot.ref} · {e.snapshot.digest}</p>{e.data.answer?.ref && <button type="button" onClick={() => onEvidence(e.data.answer.ref)}>View the recorded answer</button>}</details></li>)}</ul>
      {s.next && <button type="button" disabled={busy} onClick={() => void run(() => store.history(s.next!))}>More wording history</button>}
      {!s.next && s.historyComplete && <p className="q2-magnet-muted">All recorded wording for this Perspective is shown.</p>}
    </details>

    <details className="q2-magnet-secondary-actions" aria-label="What this cannot do yet">
      <summary>What this cannot do yet</summary>
      <div className="q2-magnet-grounding">
        <button type="button" className="q2-magnet-secondary" disabled aria-describedby="inquiry-grounded-status">Answer from selected evidence</button>
        <span id="inquiry-grounded-status" className="q2-magnet-muted" role="status">{PERSPECTIVE_BLOCK_REASON}</span>
      </div>
      <p className="q2-magnet-muted">{PERSPECTIVE_DISCLOSURE}</p>
      <p className="q2-magnet-muted">Earlier wordings and recorded answers have no automatic knowledge standing.</p>
    </details>
  </section>
}
