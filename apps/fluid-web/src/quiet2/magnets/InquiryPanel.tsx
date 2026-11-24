/** The Perspectives view: question-first inquiry, and the one approved home of
 *  the lens selector.
 *
 *  A Perspective is created by writing the question (§5-H5-5). There is no name
 *  field: the client derives the suggested name from the question and sends both
 *  to the existing create route, which requires a name. Selection is durable --
 *  it is a `selected` event, not UI state -- and the wording history below is
 *  read from the durable events, newest first, and labelled as wording only.
 *
 *  Renaming is optional and durable: it is H6's `rename` verb, which appends an
 *  event and changes the display name only. The Topic identity, the question and
 *  the durable selection are untouched by it.
 *
 *  Grounded synthesis stays refused. The affordance is rendered disabled with
 *  the server's own reason, as the Summary does; nothing here implies an agent
 *  read the collected material. */
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import { derivedPerspectiveName, perspectivesOf, PERSPECTIVE_DISCLOSURE, PERSPECTIVE_BLOCK_REASON, type PerspectiveStore } from './perspectives'
import { miniComposerDraft, saveMiniComposer } from './conversation'
import { goTab, setOpen } from './places'
import {
  clearRenameDraft, clearRevisionDraft, clearQuestionDraft, panelAt, panelDrafts,
  setQuestionDraft, setReasonDraft, setRenameDraft, setRevisionDraft, subscribePanelDrafts,
} from './panelDrafts'
import './configuration.css'

/** Copy the fresh saved question; preserve any existing Composer draft and send choices. */
export async function discussSelectedQuestion(resource: MagnetResource, store: PerspectiveStore) {
  const context = await store.ordinaryContext()
  if (!context) throw new Error('Select a Perspective before discussing its saved question.')
  const draft = miniComposerDraft(resource)
  if (draft.text.trim() && draft.text !== context.question)
    throw new Error('The Conversation Composer already has a different draft. Open it to keep or clear those words before copying the saved question.')
  saveMiniComposer(resource, { ...draft, text: context.question })
  goTab(resource, 'Conversation')
  setOpen(resource, true)
  return context
}

export function LensSelector({ resource, canWrite }: { resource: MagnetResource; canWrite: boolean }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const [error, setError] = useState('')
  useEffect(() => { void store.read() }, [store])
  return <div className="q2-magnet-lens"><label>Active Perspective<select aria-label="Active Perspective" value={s.selected ?? ''} disabled={!canWrite || s.loading || !!s.pending} onChange={(e) => { setError(''); void store.select(e.target.value || null).catch((e) => setError(e.message)) }}><option value="">No Perspective — ordinary Conversation</option>{s.rows.filter((p) => !p.retired || p.perspective === s.selected).map((p) => <option key={p.perspective} value={p.perspective}>{p.name}</option>)}</select></label>{s.listNext && <button type="button" className="q2-magnet-link" onClick={() => void store.read(s.listNext!)}>More Perspectives</button>}{(error || s.error) && <p role="status">{error || s.error}</p>}</div>
}

export default function Perspectives({ resource, canWrite, onEvidence }: { resource: MagnetResource; canWrite: boolean; onEvidence(ref: string): void }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const at = useMemo(() => panelAt(resource), [resource])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const [editor, setEditor] = useState<'revision' | 'rename' | null>(null)
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
    setMessage(store.snapshot().error ?? 'Inquiry action saved. No agent or collection was started.')
  }
  /** Escape closes the editor it is pressed in and keeps its words. */
  const suspend = (e: { key: string; stopPropagation(): void }) => { if (e.key === 'Escape') { e.stopPropagation(); setEditor(null) } }
  const history = [...s.events].reverse()        // the durable events, newest first
  const wording = (e: typeof s.events[number]) => typeof e.data.text === 'string' ? e.data.text : typeof e.data.name === 'string' ? e.data.name : null

  return <section className="q2-magnet-config" aria-label="Perspectives">
    <div className="q2-magnet-section-title"><h3 id="inquiry-title" tabIndex={-1}>Perspectives</h3></div>
    <p>Write a question or hypothesis and discuss it with the Magnet's agent. Switching the lens never changes collection or starts work.</p>
    <LensSelector resource={resource} canWrite={canWrite && !busy} />
    {s.selectedDetail?.current_question && <section aria-label="Selected saved question"><h4>Selected saved question</h4><p>{s.selectedDetail.current_question.text}</p><p>Revision: {s.selectedDetail.current_question.revision}</p></section>}
    <button type="button" className="q2-magnet-primary" disabled={!canWrite || !s.selected || busy || !!s.pending} onClick={() => void run(async () => { await discussSelectedQuestion(resource, store); setMessage('Saved question placed in the shared Composer. Choose an Ask option to start ordinary discussion.') })}>Discuss selected question</button>

    <section aria-label="Create a Perspective">
      <h4>Ask a new question</h4>
      <fieldset disabled={!canWrite || busy || !!s.pending}>
        <label>New question or hypothesis<textarea aria-label="New question or hypothesis" value={drafts.question} onChange={(e) => setQuestionDraft(at, e.target.value)} /></label>
        <p className="q2-magnet-muted">{drafts.question.trim() ? <>It will be listed as “{suggested}”, taken from the question. You are not asked for a separate name.</> : 'The question is the Perspective. Its name is taken from the question when you create it.'}</p>
        <label>Reason (optional)<input aria-label="Reason" value={drafts.reason} onChange={(e) => setReasonDraft(at, e.target.value)} /></label>
        <button type="button" disabled={!drafts.question.trim()} onClick={() => void run(async () => {
          await act('create', { name: suggested, question: drafts.question, reason: drafts.reason })
          if (!store.snapshot().pending) clearQuestionDraft(at)
        })}>Create and select Perspective</button>
      </fieldset>
    </section>

    <label>View inquiry history<select aria-label="View inquiry history" value={s.viewed ?? s.selected ?? ''} disabled={busy} onChange={(e) => { if (e.target.value) void run(() => store.view(e.target.value)) }}><option value="">Choose a Perspective</option>{s.rows.map((p) => <option key={p.perspective} value={p.perspective}>{p.name}{p.retired ? ' (retired)' : ''}</option>)}</select></label>

    {viewed && <section aria-label="Viewed Perspective" onKeyDown={suspend}>
      <h4>{viewed.name}</h4>
      <p>Viewing {viewed.name}; this does not select it as the current lens.</p>
      <p>Saved wording: {saved?.text}</p>
      <p>Saved revision: {saved?.revision}</p>
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
            <p className="q2-magnet-muted">A name is a label only. The question, the inquiry identity and the durable selection do not change, and earlier names stay in history.</p>
            <button type="button" disabled={!rename.trim() || rename === viewed.name} onClick={() => void run(async () => { await act('rename', { name: rename }); if (!store.snapshot().pending) clearRenameDraft(at, topic) })}>Save name</button>
            <button type="button" onClick={() => { clearRenameDraft(at, topic); setEditor(null) }}>Cancel rename</button></>
          : <button type="button" onClick={() => setEditor('rename')}>Rename this Perspective{topic in drafts.renames && drafts.renames[topic] !== viewed.name ? ' (unsaved name kept)' : ''}</button>}
        <button type="button" disabled={!drafts.question.trim()} onClick={() => void run(() => act('branch', { name: derivedPerspectiveName(drafts.question), question: drafts.question, reason: drafts.reason }))}>Branch inquiry from the new question</button>
        <button type="button" onClick={() => void run(() => act(viewed.retired ? 'resume' : 'retire', { reason: drafts.reason }))}>{viewed.retired ? 'Resume Perspective' : 'Retire Perspective'}</button>
      </fieldset>
    </section>}

    {s.pending && <p role="status">Uncertain {s.pending.kind} action for {s.pending.target ?? 'new Perspective'}; its original wording, target and operation key are kept. <button type="button" disabled={!canWrite || busy} onClick={() => void run(async () => { await store.retryPending(); setMessage(store.snapshot().error ?? 'Original inquiry action saved.') })}>Retry unchanged inquiry action</button></p>}

    <section aria-label="Wording history">
      <h4>Wording history</h4>
      <p>Newest first. These are earlier wordings and names only: they do not change what is currently saved, and they carry no current qualification.</p>
      <button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void run(async () => { await store.read(); if (s.viewed ?? s.selected) await store.view((s.viewed ?? s.selected)!) })}>Refresh wording history</button>
      <ul className="q2-magnet-items">{history.map((e) => <li key={e.post}><strong>{e.event === 'rename' ? 'Earlier name' : e.event === 'question' ? 'Earlier wording' : e.event}</strong>{wording(e) !== null && <p>{wording(e)}</p>}<details><summary>Immutable revision and provenance</summary><button type="button" className="q2-magnet-link" onClick={() => onEvidence(e.snapshot.ref)}>Inspect raw historical revision</button><p>{e.snapshot.ref} · {e.snapshot.digest}</p>{e.data.answer?.ref && <button type="button" onClick={() => onEvidence(e.data.answer.ref)}>Inspect raw historical answer</button>}</details></li>)}</ul>
      {s.next && <button type="button" disabled={busy} onClick={() => void run(() => store.history(s.next!))}>More wording history</button>}
      {!s.next && s.historyComplete && <p className="q2-magnet-muted">All recorded wording for this Perspective is shown.</p>}
    </section>

    <div className="q2-magnet-grounding">
      <button type="button" className="q2-magnet-secondary" disabled aria-describedby="inquiry-grounded-status">Answer from selected evidence</button>
      <span id="inquiry-grounded-status" className="q2-magnet-muted" role="status">{PERSPECTIVE_BLOCK_REASON}</span>
    </div>
    <p>{PERSPECTIVE_DISCLOSURE}</p><p>Wording history and immutable answer artifacts have no automatic knowledge standing.</p>{message && <p role="status">{message}</p>}
  </section>
}
