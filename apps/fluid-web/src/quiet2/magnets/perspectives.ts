import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, confirmBrain, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import { matchesBinding } from './managementApi'
import type { MagnetResource } from './contract'

export const PERSPECTIVE_ANSWERS_ENABLED = false
export const PERSPECTIVE_BLOCK_REASON = 'Grounded Perspective answers are blocked: existing execution controls do not enforce use of only the Magnet’s configured and selected evidence.'
export const PERSPECTIVE_DISCLOSURE = 'Selected collection evidence is recorded separately from agent access. Accessible unrelated Brain records and acquired files are outside this Magnet’s collection scope.'
export interface Perspective { perspective: string; name: string; retired: boolean; question: Artifact | null; events: number }
export interface Artifact { ref: string; digest: string; size: number; media_type: string }
export interface InquiryEvent { seq: number; post: string; event: string; perspective: string | null; snapshot: Artifact; data: Record<string, any> }
export interface PreparedInquiry { intent: string; perspective: string; brain: string; question: Artifact; manifest: Artifact; records: Artifact; artifacts: Artifact[]; parts: { type: 'file'; ref: string; media_type: string; alt: string }[]; reach: 'work'; request_op: string; text: string; closure: { count: number; bytes: number }; disclosure: string }
export interface InquirySnapshot { rows: Perspective[]; selected: string | null; viewed?: string | null; loading: boolean; error?: string; events: InquiryEvent[]; next: string | null; listNext: string | null; historyComplete: boolean; priors: string[]; continuation: boolean; selections: Record<string, 'supporting' | 'contradicting' | 'context'>; declared: string[]; active?: PreparedInquiry; receipt?: any; answer?: any }
const stores = new WeakMap<MagnetResource, PerspectiveStore>()
const uuid = (kind: string) => `perspective-${kind}-${crypto.randomUUID()}`
export class PerspectiveStore {
  private state: InquirySnapshot = { rows: [], selected: null, loading: false, events: [], next: null, listNext: null, historyComplete: false, priors: [], continuation: false, selections: {}, declared: [] }
  private listeners = new Set<() => void>()
  private version = 0
  private brain = page.bound()
  constructor(readonly resource: MagnetResource) {}
  snapshot = () => this.state
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  update = (v: Partial<InquirySnapshot>) => { this.state = { ...this.state, ...v }; this.listeners.forEach((f) => f()) }
  private path = (tail = '') => `/fluid/api/magnets/${encodeURIComponent(this.resource.saved.id)}/perspectives${tail}`
  async get(tail = ''): Promise<any> {
    if (!matchesBinding(this.resource.brainKey)) throw new Error('This Perspective belongs to another Brain instance. Reload before continuing.')
    if (this.brain && page.bound() !== this.brain) throw new Error('This inquiry was opened on a different Brain instance. Reopen it after reloading.')
    this.brain ??= page.bound()
    const expected = page.bound(), r = await fetch(this.path(tail), { headers: CLIENT_HEADERS, cache: 'no-store' }), v = await r.json().catch(() => null)
    if (!r.ok || !v || v.error) throw new Error(v?.error ?? 'Perspective records are unavailable.')
    if (page.bound() !== expected || page.moved() || v.brain && v.brain !== expected) throw new Error('A late Perspective response from a different Brain was refused.')
    return v
  }
  async write(tail: string, data: Record<string, unknown>, op = uuid('write')): Promise<any> {
    if (await confirmBrain() !== true || !matchesBinding(this.resource.brainKey)) throw new Error('Confirm the Brain before changing this inquiry.')
    if (this.brain && page.bound() !== this.brain) throw new Error('The inquiry Brain instance changed. The original intent was not sent to its replacement.')
    this.brain ??= page.bound()
    const brain = page.bound()!, r = await fluidFetch(this.path(tail), { method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: brain, 'Content-Type': 'application/json' }, body: JSON.stringify({ ...data, brain, op }) }), v = await r.json().catch(() => null)
    if (refusedAsOtherBrain(r.status, v)) page.move()
    if (!r.ok || !v || v.error) throw Object.assign(new Error(v?.error ?? 'The inquiry action outcome is unknown. Retry the same action and key.'), { refused: !!v?.refused, details: v })
    if (page.bound() !== brain || page.moved() || v.brain && v.brain !== brain) throw new Error('A late inquiry response from another Brain was refused.')
    return v
  }
  async read(cursor?: string) {
    const mine = ++this.version; this.update({ loading: true, error: undefined })
    try {
      const v = await this.get('?' + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
      if (mine !== this.version) return
      this.update({ rows: cursor ? [...this.state.rows, ...v.perspectives] : v.perspectives, selected: v.selected ?? null, listNext: v.next ?? null })
    } catch (e) { if (mine === this.version) this.update({ error: (e as Error).message }) }
    finally { if (mine === this.version) this.update({ loading: false }) }
  }
  async history(cursor?: string) {
    const selected = this.state.viewed ?? this.state.selected
    if (!selected) { this.update({ events: [], next: null, historyComplete: true }); return }
    const v = await this.get(`/${selected}/history?` + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
    if ((this.state.viewed ?? this.state.selected) !== selected) return
    this.update({ events: cursor ? [...this.state.events, ...v.events] : v.events, next: v.next ?? null, historyComplete: !v.next })
  }
  async select(perspective: string | null, op = uuid('select')) {
    await this.write('/selected', { perspective }, op)
    this.version++; this.update({ selected: perspective, viewed: perspective, events: [], next: null, historyComplete: false, priors: [], selections: {}, active: undefined, receipt: undefined, answer: undefined })
    await this.history()
  }
  async lifecycle(kind: string, data: Record<string, unknown>, op: string) {
    const target = this.state.viewed ?? this.state.selected
    const tail = kind === 'create' ? '' : `/${target}/${kind}`
    if (kind !== 'create' && !target) throw new Error('Select a Perspective first.')
    const v = await this.write(tail, data, op)
    await this.read()
    if (kind === 'create' && v.perspective) await this.select(v.perspective)
    else if (target) await this.view(target)
    return v
  }
  async view(perspective: string) { this.update({ viewed: perspective, events: [], next: null, historyComplete: false, receipt: undefined, answer: undefined }); await this.history() }
  /** Every page is bounded and frozen by the server cursor. Before a new
   * request, inspect durable unresolved intents even when browser state was lost. */
  async completeHistory() {
    await this.history()
    const seen = new Set<string>()
    while (this.state.next) {
      const cursor = this.state.next
      if (seen.has(cursor)) throw new Error('Inquiry history did not advance. Nothing was sent.')
      seen.add(cursor); await this.history(cursor)
    }
  }
  async prepare(text: string, op: string): Promise<PreparedInquiry> {
    const topic = this.state.selected
    if (!topic) throw new Error('Choose a Perspective before preparing an inquiry.')
    const row = this.state.rows.find((p) => p.perspective === topic)
    if (row?.retired) throw new Error('Resume this Perspective before asking a new question.')
    this.update({ viewed: topic })
    await this.completeHistory()
    if (this.state.selected !== topic) throw new Error('The active Perspective changed while history was being read. Nothing was sent.')
    const prepares = this.state.events.filter((e) => ['prepare', 'prepared'].includes(e.event))
    const last = prepares.at(-1)
    if (last) {
      const held = await this.get(`/${topic}/intents/${last.post}`)
      if (this.state.selected !== topic) throw new Error('The active Perspective changed while recovering the original intent. Nothing was sent.')
      if (!held.binding || !(held.answers?.length)) {
        if (held.prepared?.text === text && held.prepared?.brain === page.bound()) { this.update({ active: held.prepared }); return held.prepared }
        throw new Error('An earlier frozen inquiry has no accepted answer. Resolve or explicitly resume that original request in inquiry history before sending a different question.')
      }
    }
    const question = await this.write(`/${topic}/question`, { text }, `${op}-question`)
    const batch = this.resource.snapshot().activation?.artifact.ref
    if (!batch) throw new Error('Select a retained collection before asking a Perspective question.')
    const selected = this.resource.snapshot().results.filter((r) => this.state.selections[r.id])
    const selections = selected.flatMap((r) => {
      const value = r.value as any, source = (r as any).capturedSourceKey
      if (!source) throw new Error('The selected item lacks captured source provenance.')
      const base = { batch, source, item: r.id, version: r.version, start: 0, stance: this.state.selections[r.id] }
      if ((r as any).via === 'held-source') return [{ ...base, part: 0, end: value.end }]
      let body = value?.body ?? value
      if (typeof value?.body_json === 'string') body = JSON.parse(value.body_json)
      const parts = Array.isArray(body?.parts) ? body.parts : [{ type: 'text', text: body?.text ?? '' }]
      return parts.flatMap((p: any, part: number) => p.type === 'text' && typeof p.text === 'string' ? [{ ...base, part, end: Array.from(p.text).length }] : [])
    })
    const prepared = await this.write(`/${topic}/prepare`, { question: question.question.ref, batches: [batch], selections, priors: this.state.priors, declared_context: this.state.declared, continuation: this.state.continuation }, `${op}-prepare`) as PreparedInquiry
    if (this.state.selected !== topic || prepared.perspective !== topic || prepared.brain !== page.bound()) throw new Error('The lens or Brain changed during preparation. The original frozen intent is retained; it was not sent under a new selection.')
    this.update({ active: prepared }); return prepared
  }
  async bind(prepared: PreparedInquiry, request: string) { return this.write(`/${prepared.perspective}/bind`, { intent: prepared.intent, request }, `${prepared.request_op}-bind`) }
  async manifest(prepared: PreparedInquiry): Promise<any> {
    if (prepared.brain !== page.bound()) throw new Error('This frozen inquiry belongs to a different Brain instance.')
    const r = await fetch(`/api/artifacts/${encodeURIComponent(prepared.manifest.ref)}`, { headers: CLIENT_HEADERS, cache: 'no-store' })
    if (!r.ok) throw new Error('The original frozen manifest is unavailable. No current collection was substituted.')
    const raw = new Uint8Array(await r.arrayBuffer())
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map((n) => n.toString(16).padStart(2, '0')).join('')
    if (raw.byteLength !== prepared.manifest.size || digest !== prepared.manifest.digest || prepared.brain !== page.bound()) throw new Error('The original manifest did not verify for this Brain.')
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw))
  }
  async reconcile(prepared: PreparedInquiry, purpose: 'display' | 'resume' | 'reuse' | 'attach', execution?: string) {
    const receipt = await this.write(`/${prepared.perspective}/reconcile`, { intent: prepared.intent, purpose, ...(execution ? { execution } : {}), declared_context: this.state.declared })
    this.update({ receipt }); return receipt
  }
}
export function perspectivesOf(resource: MagnetResource) {
  let store = stores.get(resource)
  if (!store) { store = new PerspectiveStore(resource); stores.set(resource, store) }
  return store
}
/** Preserve the shared Composer's addressing, runtime, reply and Work choices. */
export function perspectiveRequest(post: Record<string, unknown>, prepared: PreparedInquiry) {
  return { ...post, text: prepared.text, topics: [...new Set([...(Array.isArray(post.topics) ? post.topics : []), prepared.perspective])],
    parts: [{ type: 'text', text: prepared.text }, ...(Array.isArray(post.parts) ? post.parts.filter((p: any) => p.type !== 'text') : []), ...prepared.parts],
    _magnetPerspective: prepared,
    dispatch: (Array.isArray(post.dispatch) ? post.dispatch : []).map((spec: any) => ({ ...spec, reach: 'work', requires: [...new Set([...(spec.requires ?? []), 'call_mentis_tools'])], work: `Use the attached frozen Perspective records, manifest and evidence. Read them with read_artifact. Reconstruct the inquiry by its Topic ${prepared.perspective}, distinguish original support from interpretations and conflicting evidence, cite the exact versions/ranges, and answer the frozen question. ${PERSPECTIVE_DISCLOSURE}` })) }
}
