import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import { perspectivesOf, PERSPECTIVE_DISCLOSURE, PERSPECTIVE_ANSWERS_ENABLED, PERSPECTIVE_BLOCK_REASON, type Artifact, type InquiryEvent, type PreparedInquiry } from './perspectives'
import { createMiniConversation, miniComposerDraft, saveMiniComposer } from './conversation'
import { capturedText } from './Inspection'
import { CLIENT_HEADERS } from '../../api'

export function LensSelector({ resource, canWrite }: { resource: MagnetResource; canWrite: boolean }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const [error, setError] = useState('')
  useEffect(() => { void store.read() }, [store])
  return <div className="q2-magnet-lens"><label>Active Perspective<select aria-label="Active Perspective" value={s.selected ?? ''} disabled={!canWrite || s.loading} onChange={(e) => { setError(''); void store.select(e.target.value || null).catch((e) => setError(e.message)) }}><option value="">No Perspective · ordinary Conversation</option>{s.rows.filter((p) => !p.retired).map((p) => <option key={p.perspective} value={p.perspective}>{p.name}</option>)}</select></label>{s.listNext && <button type="button" className="q2-magnet-link" onClick={() => void store.read(s.listNext!)}>More Perspectives</button>}{(error || s.error) && <p role="status">{error || s.error}</p>}</div>
}

export default function Perspectives({ resource, canWrite, onEvidence }: { resource: MagnetResource; canWrite: boolean; onEvidence(ref: string): void }) {
  const store = perspectivesOf(resource), s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const [name, setName] = useState(''), [question, setQuestion] = useState(''), [reason, setReason] = useState('')
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const [request, setRequest] = useState(''), [answerPost, setAnswerPost] = useState('')
  const [frozenBatches, setFrozenBatches] = useState<Artifact[]>([])
  const [available, setAvailable] = useState<{ id: string; text: string; requests: { id: string; text: string }[]; agent: boolean }[]>([])
  const pending = useRef<{ kind: string; data: Record<string, unknown>; op: string } | null>(null)
  const viewed = s.rows.find((p) => p.perspective === (s.viewed ?? s.selected))
  useEffect(() => { if (!s.viewed && s.selected) void store.view(s.selected).catch((e) => setMessage(e.message)) }, [s.viewed, s.selected, store])
  const run = async (fn: () => Promise<unknown>) => { if (busy) return; setBusy(true); setMessage(''); try { await fn() } catch (e) { setMessage((e as Error).message) } finally { setBusy(false) } }
  const act = async (kind: string, data: Record<string, unknown>) => {
    pending.current ??= { kind, data, op: `perspective-action-${crypto.randomUUID()}` }
    const intent = pending.current
    try { await store.lifecycle(intent.kind, intent.data, intent.op); pending.current = null; setMessage('Inquiry history saved. No agent or collection was started.') }
    catch (e) { if ((e as any).refused) pending.current = null; throw e }
  }
  const openIntent = async (event: InquiryEvent) => {
    const topic = event.perspective
    if (!topic) return
    const v = await store.get(`/${topic}/intents/${event.post}`)
    store.update({ active: v.prepared, receipt: undefined, answer: undefined })
    setRequest(v.binding?.request ?? '')
    const mini = createMiniConversation({ resource, canWrite: false })
    try { await mini.read(); const m = mini.snapshot(); setAvailable(m.posts.map((p) => ({ id: p.id, text: p.text, agent: p.agent, requests: p.work.map((w) => ({ id: w.expectation, text: w.expects })) }))) }
    finally { mini.dispose() }
    setMessage(v.binding ? 'Original frozen request recovered from durable records.' : 'Frozen intent recovered. If its send outcome is unknown, link the original recorded request; do not start a different question.')
  }
  const active = s.active
  useEffect(() => {
    let alive = true; setFrozenBatches([])
    if (active) void store.manifest(active).then((v) => { if (alive) setFrozenBatches(v.batches ?? []) }).catch((e) => { if (alive) setMessage(e.message) })
    return () => { alive = false }
  }, [active?.intent, store])
  const inspectAnswer = async (event: InquiryEvent) => {
    if (!PERSPECTIVE_ANSWERS_ENABLED) throw new Error(PERSPECTIVE_BLOCK_REASON)
    const data = event.data, topic = event.perspective
    if (!topic || !data.intent) throw new Error('This answer does not identify its original frozen inquiry.')
    const v = await store.get(`/${topic}/intents/${data.intent}`), prepared = v.prepared as PreparedInquiry
    const receipt = await store.reconcile(prepared, 'display', data.execution)
    if (receipt.status !== 'qualified') throw new Error('This answer remains an ordinary reply: its current evidence reconciliation is pending or incomplete.')
    const ref = typeof data.answer === 'string' ? data.answer : data.answer?.ref
    if (!ref) throw new Error('The original immutable answer is unavailable.')
    const r = await fetch(`/api/artifacts/${encodeURIComponent(ref)}`, { headers: CLIENT_HEADERS, cache: 'no-store' })
    if (!r.ok) throw new Error('The original answer bytes are unavailable; no current text was substituted.')
    const answer = await r.json(); store.update({ active: prepared, answer })
  }
  const useQuestion = () => { const draft = miniComposerDraft(resource); saveMiniComposer(resource, { ...draft, text: question }); resource.update({ tab: 'Conversation', expanded: true, pinned: true }); setMessage('Question placed in the shared Composer. Choose an agent and its Ask send option to start work.') }
  return <section className="q2-magnet-config" aria-label="Perspectives">
    <h3>Perspectives</h3><p>A durable inquiry into this Magnet’s retained evidence. Switching the lens never changes collection or starts work.</p><p role="status">{PERSPECTIVE_BLOCK_REASON}</p>
    <LensSelector resource={resource} canWrite={canWrite} />
    <label>View inquiry history<select aria-label="View inquiry history" value={s.viewed ?? s.selected ?? ''} disabled={busy} onChange={(e) => void run(() => store.view(e.target.value))}><option value="">Choose an inquiry</option>{s.rows.map((p) => <option key={p.perspective} value={p.perspective}>{p.name}{p.retired ? ' · retired' : ''}</option>)}</select></label>
    <details><summary>Create or refine an inquiry</summary><fieldset disabled={!canWrite || busy || !!pending.current}><label>Perspective name<input value={name} maxLength={160} onChange={(e) => setName(e.target.value)} /></label><label>Question or hypothesis<textarea aria-label="Question or hypothesis" value={question} maxLength={65536} onChange={(e) => setQuestion(e.target.value)} /></label><label>Reason or challenge context<textarea value={reason} maxLength={65536} onChange={(e) => setReason(e.target.value)} /></label><button type="button" className="q2-magnet-primary" disabled={!name.trim() || !question.trim()} onClick={() => void run(() => act('create', { name, question, reason }))}>Create Perspective</button>{viewed && <><button type="button" disabled={!question.trim()} onClick={() => void run(() => act('question', { text: question, reason }))}>Save question revision</button><button type="button" disabled={!question.trim()} onClick={() => void run(() => act('challenge', { text: question, reason }))}>Record challenge</button><button type="button" disabled={!name.trim() || !question.trim()} onClick={() => void run(() => act('branch', { name, question, reason }))}>Branch inquiry</button><button type="button" onClick={() => void run(() => act(viewed.retired ? 'resume' : 'retire', { reason }))}>{viewed.retired ? 'Resume Perspective' : 'Retire Perspective'}</button></>}</fieldset>{pending.current && <button type="button" disabled={busy} onClick={() => void run(() => act(pending.current!.kind, pending.current!.data))}>Retry unchanged inquiry action</button>}<button type="button" className="q2-magnet-primary" disabled={!PERSPECTIVE_ANSWERS_ENABLED || !question.trim() || !s.selected || busy} onClick={useQuestion}>Use question in Conversation composer</button></details>
    <details><summary>Evidence and continuation</summary><p>All captured text is selected when no individual items are chosen. Whole batch artifacts still count toward the limit. A single oversized batch requires narrower configuration and a new manual collection.</p><ul className="q2-magnet-items">{resource.snapshot().results.filter((r) => r.kind === 'post' || (r as any).via === 'held-source').map((r) => <li key={`${(r as any).capturedSourceKey}:${r.id}`}><label>{(r.value as any)?.path || capturedText(r).slice(0, 90) || `Collected post ${r.number ?? ''}`}<select aria-label={`Evidence stance for ${r.id}`} value={s.selections[r.id] ?? ''} onChange={(e) => { const selections = { ...s.selections }; if (e.target.value) selections[r.id] = e.target.value as any; else delete selections[r.id]; store.update({ selections }) }}><option value="">Not individually selected</option><option value="supporting">Supporting</option><option value="contradicting">Contradicting</option><option value="context">Context</option></select></label></li>)}</ul><label><input type="checkbox" checked={s.continuation} onChange={(e) => store.update({ continuation: e.target.checked })} />Continue with durable inquiry history and inherited dependencies</label><p>At most 32 distinct artifacts and 8 MiB, including manifests and prior interpretations. Prior interpretations do not become independent corroboration.</p>{s.events.filter((e) => e.event === 'answered').map((e) => { const ref = typeof e.data.answer === 'string' ? e.data.answer : e.data.answer?.ref; return ref && <label key={e.post}><input type="checkbox" checked={s.priors.includes(ref)} onChange={(v) => store.update({ priors: v.target.checked ? [...s.priors, ref] : s.priors.filter((r) => r !== ref) })} />Include earlier interpretation #{e.seq}</label> })}</details>
    <h4>Inquiry history</h4><button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void run(() => store.history())}>Refresh inquiry history</button><ul className="q2-magnet-items">{s.events.map((e) => <li key={e.post}><strong>{e.event}</strong>{typeof e.data.text === 'string' && <p>{e.data.text}</p>}<details><summary>Immutable revision and provenance</summary><button type="button" className="q2-magnet-link" onClick={() => onEvidence(e.snapshot.ref)}>Inspect revision evidence</button><p>{e.snapshot.ref} · {e.snapshot.digest}</p></details>{e.event === 'prepared' || e.event === 'prepare' ? <button type="button" disabled={busy} onClick={() => void run(() => openIntent(e))}>Open frozen inquiry</button> : null}{e.event === 'answered' && <button type="button" disabled={busy} onClick={() => void run(() => inspectAnswer(e))}>Inspect original answer and evidence</button>}</li>)}</ul>{s.next && <button type="button" disabled={busy} onClick={() => void run(() => store.history(s.next!))}>More inquiry history</button>}
    {active && <section aria-label="Frozen inquiry"><h4>Frozen inquiry</h4><p>{active.closure.count} artifacts · {active.closure.bytes.toLocaleString()} bytes</p><p>{active.text}</p><button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void run(async () => { const batch = frozenBatches[0]; if (batch) { await resource.selectBatch?.(batch); onEvidence(batch.ref) } else onEvidence(active.manifest.ref) })}>Inspect frozen evidence</button><label>Original recorded request<select value={request} onChange={(e) => setRequest(e.target.value)}><option value="">Choose the original request</option>{available.flatMap((p) => p.requests.map((w) => <option key={w.id} value={w.id}>{w.text || p.text.slice(0, 90)}</option>))}</select></label><button type="button" disabled={busy || !canWrite || !request} onClick={() => void run(() => store.bind(active, request))}>Link original recorded request</button><button type="button" disabled={busy || !canWrite} onClick={() => void run(() => store.reconcile(active, 'display'))}>Check actual evidence reach</button>{s.receipt && <><p role="status">{s.receipt.status === 'qualified' ? 'Declared evidence is reconciled for this execution.' : s.receipt.status === 'pending' ? 'Reconciliation pending; no qualified synthesis.' : 'Ordinary reply only; declared evidence is incomplete.'}</p>{s.receipt.reachable_not_declared?.map((a: any) => <label key={a.ref}><input type="checkbox" checked={s.declared.includes(a.ref)} onChange={(e) => store.update({ declared: e.target.checked ? [...s.declared, a.ref] : s.declared.filter((r) => r !== a.ref), receipt: undefined })} />Declare reachable context: {a.ref} ({a.because})</label>)}{s.receipt.required_unavailable?.length > 0 && <p>Required evidence unavailable: {s.receipt.required_unavailable.join(', ')}. No replacement was substituted.</p>}</>}<label>Agent reply to preserve<select value={answerPost} onChange={(e) => setAnswerPost(e.target.value)}><option value="">Choose an actual reply</option>{available.filter((p) => p.agent).map((p) => <option key={p.id} value={p.id}>{p.text.slice(0, 100)}</option>)}</select></label><button type="button" disabled={!PERSPECTIVE_ANSWERS_ENABLED || busy || !canWrite || !answerPost || !s.receipt?.execution} onClick={() => void run(async () => { await store.write(`/${active.perspective}/finalize`, { intent: active.intent, execution: s.receipt.execution, answer: answerPost }); await store.history(); setMessage('Immutable answer version recorded without Brain material or adoption.'); })}>Preserve versioned synthesis</button></section>}
    {s.answer && <section aria-label="Versioned Perspective answer"><h4>Earlier answer</h4><p>{PERSPECTIVE_DISCLOSURE}</p><pre className="q2-magnet-post-text">{s.answer.parts?.filter((p: any) => p.type === 'text').map((p: any) => p.text).join('\n\n') ?? 'This immutable answer has no retained text.'}</pre></section>}
    <p>{PERSPECTIVE_DISCLOSURE}</p><p>Neither configured retention option is delivered. Inquiry history and immutable answer artifacts have no automatic knowledge standing.</p>{message && <p role="status">{message}</p>}
  </section>
}
