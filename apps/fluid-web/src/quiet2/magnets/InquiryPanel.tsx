import { useEffect, useState, useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import { perspectivesOf, PERSPECTIVE_DISCLOSURE, PERSPECTIVE_BLOCK_REASON, type PerspectiveStore } from './perspectives'
import { miniComposerDraft, saveMiniComposer } from './conversation'

/** Copy the fresh saved question; preserve any existing Composer draft and send choices. */
export async function discussSelectedQuestion(resource: MagnetResource, store: PerspectiveStore) {
  const context = await store.ordinaryContext()
  if (!context) throw new Error('Select a Perspective before discussing its saved question.')
  const draft = miniComposerDraft(resource)
  if (draft.text.trim() && draft.text !== context.question)
    throw new Error('The Conversation Composer already has a different draft. Open it to keep or clear those words before copying the saved question.')
  saveMiniComposer(resource, { ...draft, text: context.question })
  resource.update({ tab: 'Conversation', expanded: true, pinned: true })
  return context
}

export function LensSelector({ resource, canWrite }: { resource: MagnetResource; canWrite: boolean }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const [error, setError] = useState('')
  useEffect(() => { void store.read() }, [store])
  return <div className="q2-magnet-lens"><label>Active Perspective<select aria-label="Active Perspective" value={s.selected ?? ''} disabled={!canWrite || s.loading || !!s.pending} onChange={(e) => { setError(''); void store.select(e.target.value || null).catch((e) => setError(e.message)) }}><option value="">No Perspective ? ordinary Conversation</option>{s.rows.filter((p) => !p.retired || p.perspective === s.selected).map((p) => <option key={p.perspective} value={p.perspective}>{p.name}</option>)}</select></label>{s.listNext && <button type="button" className="q2-magnet-link" onClick={() => void store.read(s.listNext!)}>More Perspectives</button>}{(error || s.error) && <p role="status">{error || s.error}</p>}</div>
}

export default function Perspectives({ resource, canWrite, onEvidence }: { resource: MagnetResource; canWrite: boolean; onEvidence(ref: string): void }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const [name, setName] = useState(''), [newQuestion, setNewQuestion] = useState('')
  const [question, setQuestion] = useState(''), [reason, setReason] = useState('')
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const viewed = s.viewedDetail, saved = viewed?.current_question
  useEffect(() => { if (!s.viewed && s.selected) void store.view(s.selected).catch((e) => setMessage(e.message)) }, [s.viewed, s.selected, store])
  useEffect(() => { setQuestion(saved?.text ?? '') }, [viewed?.perspective, saved?.revision])
  const run = async (fn: () => Promise<unknown>) => { if (busy) return; setBusy(true); setMessage(''); try { await fn() } catch (e) { setMessage((e as Error).message) } finally { setBusy(false) } }
  const act = async (kind: string, data: Record<string, unknown>) => {
    await store.lifecycle(kind, data)
    setMessage(store.snapshot().error ?? 'Inquiry action saved. No agent or collection was started.')
  }
  return <section className="q2-magnet-config" aria-label="Perspectives">
    <h3>Perspectives</h3><p>Save a question or hypothesis and discuss it with the Magnet's agent. Switching the lens never changes collection or starts work.</p><p role="status">{PERSPECTIVE_BLOCK_REASON}</p>
    <LensSelector resource={resource} canWrite={canWrite && !busy} />
    {s.selectedDetail?.current_question && <section aria-label="Selected saved question"><h4>Selected saved question</h4><p>{s.selectedDetail.current_question.text}</p><p>Revision: {s.selectedDetail.current_question.revision}</p></section>}
    <button type="button" className="q2-magnet-primary" disabled={!canWrite || !s.selected || busy || !!s.pending} onClick={() => void run(async () => { await discussSelectedQuestion(resource, store); setMessage('Saved question placed in the shared Composer. Choose an Ask option to start ordinary discussion.') })}>Discuss selected question</button>
    <label>View inquiry history<select aria-label="View inquiry history" value={s.viewed ?? s.selected ?? ''} disabled={busy} onChange={(e) => { if (e.target.value) void run(() => store.view(e.target.value)) }}><option value="">Choose a Perspective</option>{s.rows.map((p) => <option key={p.perspective} value={p.perspective}>{p.name}{p.retired ? ' (retired)' : ''}</option>)}</select></label>
    <details open><summary>Create a Perspective</summary><fieldset disabled={!canWrite || busy || !!s.pending}><label>Perspective name<input value={name} onChange={(e) => setName(e.target.value)} /></label><label>New question or hypothesis<textarea value={newQuestion} onChange={(e) => setNewQuestion(e.target.value)} /></label><button type="button" disabled={!name.trim() || !newQuestion.trim()} onClick={() => void run(() => act('create', { name, question: newQuestion, reason }))}>Create and select Perspective</button></fieldset></details>
    {viewed && <details open><summary>Edit saved question</summary><p>Viewing {viewed.name}; this does not select it as the current lens.</p><p>Saved wording: {saved?.text}</p><p>Saved revision: {saved?.revision}</p><fieldset disabled={!canWrite || busy || !!s.pending}><label>Question or hypothesis<textarea aria-label="Edit saved question" value={question} onChange={(e) => setQuestion(e.target.value)} /></label><p>{question !== saved?.text ? 'Unsaved edits' : 'Matches saved current question'}</p><label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} /></label><button type="button" disabled={!question.trim() || question === saved?.text} onClick={() => void run(() => act('question', { text: question, reason }))}>Save question revision</button><button type="button" disabled={!question.trim()} onClick={() => void run(() => act('challenge', { text: question, reason }))}>Record challenge</button><button type="button" disabled={!name.trim() || !question.trim()} onClick={() => void run(() => act('branch', { name, question, reason }))}>Branch inquiry</button><button type="button" onClick={() => void run(() => act(viewed.retired ? 'resume' : 'retire', { reason }))}>{viewed.retired ? 'Resume Perspective' : 'Retire Perspective'}</button></fieldset></details>}
    {s.pending && <p role="status">Uncertain {s.pending.kind} action for {s.pending.target ?? 'new Perspective'}; its original wording, target and operation key are kept. <button type="button" disabled={!canWrite || busy} onClick={() => void run(async () => { await store.retryPending(); setMessage(store.snapshot().error ?? 'Original inquiry action saved.') })}>Retry unchanged inquiry action</button></p>}
    <h4>Inquiry history</h4><p>Historical revisions are separate from the saved current question. Earlier evidence and answers are raw history, with no current qualification.</p><button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void run(async () => { await store.read(); if (s.viewed ?? s.selected) await store.view((s.viewed ?? s.selected)!) })}>Refresh inquiry history</button><ul className="q2-magnet-items">{s.events.map((e) => <li key={e.post}><strong>{e.event}</strong>{typeof e.data.text === 'string' && <p>{e.data.text}</p>}<details><summary>Immutable revision and provenance</summary><button type="button" className="q2-magnet-link" onClick={() => onEvidence(e.snapshot.ref)}>Inspect raw historical revision</button><p>{e.snapshot.ref} ? {e.snapshot.digest}</p>{e.data.answer?.ref && <button type="button" onClick={() => onEvidence(e.data.answer.ref)}>Inspect raw historical answer</button>}</details></li>)}</ul>{s.next && <button type="button" disabled={busy} onClick={() => void run(() => store.history(s.next!))}>More inquiry history</button>}
    <p>{PERSPECTIVE_DISCLOSURE}</p><p>Inquiry history and immutable answer artifacts have no automatic knowledge standing.</p>{message && <p role="status">{message}</p>}
  </section>
}
