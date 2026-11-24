import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, confirmBrain, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import { matchesBinding } from './managementApi'
import type { MagnetResource, SearchEntry, SearchSource } from './contract'
import { remember, setOpen } from './places'

export const PERSPECTIVE_ANSWERS_ENABLED = false
export const PERSPECTIVE_BLOCK_REASON = 'Grounded Perspective answers are blocked: existing execution controls do not enforce use of only the Magnet’s configured and selected evidence.'
export const PERSPECTIVE_DISCLOSURE = 'Selected collection evidence is recorded separately from agent access. Accessible unrelated Brain records and acquired files are outside this Magnet’s collection scope.'
export interface Perspective { perspective: string; name: string; retired: boolean; question: Artifact | null; current_question?: { text: string; revision: string } | null; events: number }
export interface Artifact { ref: string; digest: string; size: number; media_type: string }
export interface InquiryEvent { seq: number; post: string; event: string; perspective: string | null; snapshot: Artifact; data: Record<string, any> }
export interface PreparedInquiry { intent: string; perspective: string; brain: string; question: Artifact; manifest: Artifact; records: Artifact; artifacts: Artifact[]; parts: { type: 'file'; ref: string; media_type: string; alt: string }[]; reach: 'work'; request_op: string; text: string; closure: { count: number; bytes: number }; disclosure: string }
export interface OrdinaryContext { perspective: string; name: string; question: string; revision: string }
export interface PendingAction { brain: string; magnet: string; kind: string; target: string | null; tail: string; data: Record<string, unknown>; op: string; result?: any; selectOp: string }
export interface InquirySnapshot { pending?: PendingAction; viewedDetail?: Perspective; selectedDetail?: Perspective; rows: Perspective[]; selected: string | null; viewed?: string | null; loading: boolean; error?: string; events: InquiryEvent[]; next: string | null; listNext: string | null; historyComplete: boolean; priors: string[]; continuation: boolean; selections: Record<string, 'supporting' | 'contradicting' | 'context'>; declared: string[]; active?: PreparedInquiry; receipt?: any; answer?: any }
const stores = new WeakMap<MagnetResource, PerspectiveStore>()
const uuid = (kind: string) => `perspective-${kind}-${crypto.randomUUID()}`

/** A durable lens choice is also an explicit composer-context choice. Like
 * "Discuss this evidence", selecting one may replace an attached chip and
 * clears suppression. Choosing ordinary Conversation removes only a
 * Perspective chip; removing the chip itself never changes the active lens. */
export function showPerspectiveContext(resource: MagnetResource, perspective: string | null, name?: string | null): void {
  if (perspective) {
    resource.update({ context: { ref: perspective, kind: 'perspective', label: name || perspective }, contextSuppressed: false })
  } else if (resource.snapshot().context?.kind === 'perspective') {
    resource.update({ context: null, contextSuppressed: false })
  }
}

/** Question-first creation (§5-H5-5). The create route requires a name, so the
 *  client derives the one it suggests from the question itself and the owner is
 *  never asked for a second field. The approved rule: the question unchanged
 *  through 52 characters, otherwise its first 49 plus an ellipsis -- counted in
 *  characters, so an emoji is one character and is never cut in half. */
export const PERSPECTIVE_NAME_KEEP = 52
export const PERSPECTIVE_NAME_HEAD = 49
export function derivedPerspectiveName(question: string): string {
  const words = question.trim().replace(/\s+/g, ' ')
  const chars = Array.from(words)
  return chars.length <= PERSPECTIVE_NAME_KEEP ? words : chars.slice(0, PERSPECTIVE_NAME_HEAD).join('') + '…'
}

/** Every page is bounded and frozen by the server cursor, so walking one to
 *  exhaustion is bounded too -- provided a cursor that does not advance is
 *  treated as a defect and not as a loop. This is the one guard; both
 *  `completeHistory()` and `perspectiveSource.complete()` use it. */
export async function walkPages(read: (cursor?: string) => Promise<string | null>): Promise<void> {
  const seen = new Set<string>()
  let cursor = await read(undefined)
  while (cursor) {
    if (seen.has(cursor)) throw new Error('The question history did not advance. Nothing was sent.')
    seen.add(cursor)
    cursor = await read(cursor)
  }
}
export class PerspectiveStore {
  private state: InquirySnapshot = { rows: [], selected: null, loading: false, events: [], next: null, listNext: null, historyComplete: false, priors: [], continuation: false, selections: {}, declared: [] }
  private listeners = new Set<() => void>()
  private version = 0
  private brain = page.bound()
  private lensVersion = 0
  private historyVersion = 0
  constructor(readonly resource: MagnetResource) {
    try {
      const raw = globalThis.localStorage?.getItem(this.storageKey())
      if (raw && raw.length <= 300000) {
        const pending = JSON.parse(raw) as PendingAction
        if (pending.brain === this.brain && pending.magnet === resource.saved.id &&
            typeof pending.op === 'string' && typeof pending.selectOp === 'string' &&
            typeof pending.kind === 'string' && typeof pending.tail === 'string' &&
            pending.tail === (pending.kind === 'create' ? '' : pending.kind === 'selected' ? '/selected' : `/${pending.target}/${pending.kind}`) &&
            pending.data && typeof pending.data === 'object') this.state.pending = pending
      }
    } catch { /* An unreadable browser record never becomes a new write. */ }
  }
  private storageKey() { return `mentis:perspective-action:${this.resource.brainKey}:${this.brain}:${this.resource.saved.id}` }
  private keep(pending?: PendingAction) {
    // Persist before sending. A failed browser write must not discard uncertainty.
    if (globalThis.localStorage) {
      if (pending) globalThis.localStorage.setItem(this.storageKey(), JSON.stringify(pending))
      else globalThis.localStorage.removeItem(this.storageKey())
    }
    this.update({ pending })
  }
  snapshot = () => this.state
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  update = (v: Partial<InquirySnapshot>) => {
    if ('selected' in v && v.selected !== this.state.selected) {
      this.lensVersion++
      v = { selectedDetail: undefined, active: undefined, receipt: undefined, answer: undefined, ...v }
    }
    this.state = { ...this.state, ...v }; this.listeners.forEach((f) => f())
  }
  private path = (tail = '') => `/fluid/api/magnets/${encodeURIComponent(this.resource.saved.id)}/perspectives${tail}`
  async get(tail = ''): Promise<any> {
    if (!matchesBinding(this.resource.brainKey)) throw new Error('This Perspective belongs to another Brain instance. Reload before continuing.')
    if (this.brain && page.bound() !== this.brain) throw new Error('This question was opened on a different Brain instance. Reopen it after reloading.')
    this.brain ??= page.bound()
    const expected = page.bound(), r = await fetch(this.path(tail), { headers: CLIENT_HEADERS, cache: 'no-store' }), v = await r.json().catch(() => null)
    if (!r.ok || !v || v.error) throw new Error(v?.error ?? 'Perspective records are unavailable.')
    if (page.bound() !== expected || page.moved() || v.brain !== expected) throw new Error('A late Perspective response from a different Brain was refused.')
    return v
  }
  async write(tail: string, data: Record<string, unknown>, op = uuid('write')): Promise<any> {
    if (await confirmBrain() !== true || !matchesBinding(this.resource.brainKey)) throw new Error('Confirm the Brain before changing this question.')
    if (this.brain && page.bound() !== this.brain) throw new Error('The Brain instance changed. The original intent was not sent to its replacement.')
    this.brain ??= page.bound()
    const brain = page.bound()!, r = await fluidFetch(this.path(tail), { method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: brain, 'Content-Type': 'application/json' }, body: JSON.stringify({ ...data, brain, op }) }), v = await r.json().catch(() => null)
    if (refusedAsOtherBrain(r.status, v)) page.move()
    if (!r.ok || !v || v.error) throw Object.assign(new Error(v?.error ?? 'The outcome of that question action is unknown. Retry the same action and key.'), { refused: !!v?.refused, details: v })
    if (page.bound() !== brain || page.moved() || v.brain !== brain) throw new Error('A late response from another Brain was refused.')
    return v
  }
  private detail(v: any, topic: string): Perspective {
    const q = v.current_question
    if (v.magnet !== this.resource.saved.id || v.perspective !== topic || typeof v.name !== 'string' ||
        !q || typeof q.text !== 'string' || typeof q.revision !== 'string' || q.revision !== v.question?.ref)
      throw new Error('The saved current question did not match this Perspective.')
    return v
  }
  private merged(rows: Perspective[], row?: Perspective) {
    return row ? [...rows.filter((r) => r.perspective !== row.perspective), row] : rows
  }
  async read(cursor?: string) {
    const mine = ++this.version, lens = this.lensVersion; this.update({ loading: true, error: undefined })
    try {
      const v = await this.get('?' + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
      const selected = v.selected ?? null
      const detail = selected ? this.detail(await this.get(`/${selected}`), selected) : undefined
      if (detail && (detail as any).selected !== selected) throw new Error('The active Perspective changed during refresh.')
      if (mine !== this.version || lens !== this.lensVersion) return
      this.update({ rows: this.merged(cursor ? [...this.state.rows, ...v.perspectives] : v.perspectives, detail), selected, selectedDetail: detail, listNext: v.next ?? null })
    } catch (e) { if (mine === this.version) this.update({ error: (e as Error).message }) }
    finally { if (mine === this.version) this.update({ loading: false }) }
  }
  /** Read the durable lens and exact saved question afresh, never from history or editor state. */
  async ordinaryContext(): Promise<OrdinaryContext | null> {
    if (this.state.pending) throw new Error('Resolve the unchanged question action before discussing its saved question.')
    const lens = this.lensVersion
    const v = await this.get('?limit=1'), topic = v.selected ?? null
    const detail = topic ? this.detail(await this.get(`/${topic}`), topic) : undefined
    const check = await this.get('?limit=1')
    if (lens !== this.lensVersion || (check.selected ?? null) !== topic || detail && (detail as any).selected !== topic)
      throw new Error('The active Perspective changed while its saved question was being read. Nothing was sent.')
    if (detail) {
      const latest = this.detail(await this.get(`/${topic}`), topic!)
      if (lens !== this.lensVersion || this.state.pending || (latest as any).selected !== topic || latest.current_question?.revision !== detail.current_question?.revision)
        throw new Error('The active Perspective or saved question changed while it was being read. Nothing was sent.')
    }
    this.update({ selected: topic, selectedDetail: detail, rows: this.merged(this.state.rows, detail) })
    if (!detail) return null
    return { perspective: topic!, name: detail.name, question: detail.current_question!.text, revision: detail.current_question!.revision }
  }
  async history(cursor?: string) {
    const selected = this.state.viewed ?? this.state.selected, mine = ++this.historyVersion
    if (!selected) { this.update({ events: [], next: null, historyComplete: true }); return }
    const v = await this.get(`/${selected}/history?` + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
    if (mine !== this.historyVersion || (this.state.viewed ?? this.state.selected) !== selected) return
    if (v.perspective !== selected || v.magnet !== this.resource.saved.id) throw new Error('History answered for another Perspective.')
    this.update({ events: cursor ? [...this.state.events, ...v.events] : v.events, next: v.next ?? null, historyComplete: !v.next })
  }
  async select(perspective: string | null, op = uuid('select')) {
    return this.action('selected', { perspective }, null, op)
  }
  async lifecycle(kind: string, data: Record<string, unknown>, op = uuid('action')) {
    return this.action(kind, data, this.state.viewed ?? this.state.selected, op)
  }
  private async action(kind: string, data: Record<string, unknown>, target: string | null, op: string) {
    if (this.state.pending) throw new Error('An earlier question action has an unknown outcome. Retry that unchanged action first.')
    if (kind !== 'create' && kind !== 'selected' && !target) throw new Error('View a Perspective first.')
    const brain = this.brain
    if (!matchesBinding(this.resource.brainKey) || !brain || brain !== page.bound()) throw new Error('Confirm the original Brain before changing this question.')
    this.lensVersion++
    this.keep({ brain, magnet: this.resource.saved.id, kind, target,
      tail: kind === 'create' ? '' : kind === 'selected' ? '/selected' : `/${target}/${kind}`,
      data: structuredClone(data), op, selectOp: `${op}-select` })
    return this.retryPending()
  }
  async retryPending() {
    const pending = this.state.pending
    if (!pending) return
    if (pending.brain !== page.bound() || page.moved() || pending.magnet !== this.resource.saved.id) throw new Error('The original question action belongs to another Brain. It was not sent.')
    let v: any
    try {
      v = pending.result ?? await this.write(pending.tail, pending.data, pending.op)
      // Create and selection are separate keyed writes; retain the acknowledged create.
      if (pending.kind === 'create' || pending.kind === 'branch') {
        if (typeof v.perspective !== 'string') throw new Error('The saved question did not return its identity. Retry the original key.')
        this.keep({ ...pending, result: v })
        await this.write('/selected', { perspective: v.perspective }, pending.selectOp)
      }
    } catch (e) { if ((e as any).refused) this.keep(); throw e }
    this.keep()
    const chosen = pending.kind === 'selected' ? pending.data.perspective as string | null :
      pending.kind === 'create' || pending.kind === 'branch' ? v.perspective : this.state.selected
    const chosenName = chosen ? (typeof v?.name === 'string' ? v.name
      : typeof pending.data.name === 'string' ? pending.data.name
      : this.state.rows.find((row) => row.perspective === chosen)?.name) : null
    this.version++; this.historyVersion++
    this.update({ selected: chosen, viewed: pending.kind === 'selected' ? chosen : v.perspective ?? pending.target,
      viewedDetail: undefined, events: [], next: null, historyComplete: false, active: undefined, receipt: undefined, answer: undefined })
    showPerspectiveContext(this.resource, chosen, chosenName)
    // An acknowledged write stays acknowledged even if its follow-up read fails.
    try {
      await this.read()
      if (this.state.error) throw new Error(this.state.error)
      const target = this.state.viewed ?? this.state.selected
      if (target) await this.view(target)
      const selected = this.state.rows.find((row) => row.perspective === this.state.selected)
      if (this.state.selected && selected) showPerspectiveContext(this.resource, this.state.selected, selected.name)
    } catch (e) { this.update({ error: `Question action saved. Refresh failed: ${(e as Error).message}` }) }
    return v
  }
  async view(perspective: string) {
    const mine = ++this.historyVersion
    this.update({ viewed: perspective, viewedDetail: undefined, events: [], next: null, historyComplete: false, active: undefined, receipt: undefined, answer: undefined })
    const v = this.detail(await this.get(`/${perspective}`), perspective)
    if (mine !== this.historyVersion || this.state.viewed !== perspective) return
    this.update({ viewedDetail: v, rows: this.merged(this.state.rows, v) })
    await this.history()
  }
  /** Every page is bounded and frozen by the server cursor. Before a new
   * request, inspect durable unresolved intents even when browser state was lost. */
  async completeHistory() {
    await walkPages(async (cursor) => { await this.history(cursor); return this.state.next })
  }
  async prepare(text: string, op: string): Promise<PreparedInquiry> {
    if (!PERSPECTIVE_ANSWERS_ENABLED) throw new Error(PERSPECTIVE_BLOCK_REASON)
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
    if (!PERSPECTIVE_ANSWERS_ENABLED) throw new Error(PERSPECTIVE_BLOCK_REASON)
    const receipt = await this.write(`/${prepared.perspective}/reconcile`, { intent: prepared.intent, purpose, ...(execution ? { execution } : {}), declared_context: this.state.declared })
    this.update({ receipt }); return receipt
  }
}
export function perspectivesOf(resource: MagnetResource) {
  let store = stores.get(resource)
  if (!store) { store = new PerspectiveStore(resource); stores.set(resource, store) }
  return store
}

/** Open a Perspective, or one of its earlier wordings, in the Perspectives tab. */
export function openPerspective(resource: MagnetResource, perspective: string, item?: string) {
  remember(resource)
  resource.update({ tab: 'Perspectives', overlay: null,
    searchTarget: { kind: 'Perspectives', lens: perspective, ...(item ? { item } : {}) } })
  setOpen(resource, true)
}

/** The wording an inquiry event carries, if it carries one. */
const wordingOf = (e: InquiryEvent): string | null =>
  typeof e.data?.text === 'string' ? e.data.text : typeof e.data?.name === 'string' ? e.data.name : null
const EVENT_WORDS: Record<string, string> = {
  question: 'Earlier wording', created: 'Original wording', branch: 'Branched wording',
  challenge: 'Recorded challenge', rename: 'Earlier name',
}

/** H5's contribution to the universal index (§4). `entries()` is what the panel
 *  has already read; `complete()` owes every Perspective and every earlier
 *  wording of each, so the search is over what the Magnet holds and not over
 *  whichever page happened to be open. It reads through the store's `get`,
 *  which never writes, so searching cannot move the owner's viewed lens. */
export function perspectiveSource(resource: MagnetResource): SearchSource {
  const store = perspectivesOf(resource)
  let stopped: string | null = null
  const rowEntry = (row: Perspective): SearchEntry => ({
    key: `perspective:${row.perspective}`, kind: 'Perspectives',
    title: `${row.name}${row.retired ? ' (retired)' : ''}`,
    text: [row.name, row.current_question?.text ?? ''].filter(Boolean).join(' · '),
    open: () => openPerspective(resource, row.perspective),
  })
  const wordingEntry = (row: Perspective, e: InquiryEvent): SearchEntry | null => {
    const text = wordingOf(e)
    return text === null ? null : {
      key: `wording:${row.perspective}:${e.post}`, kind: 'Perspectives',
      title: `${EVENT_WORDS[e.event] ?? e.event} · ${row.name}`,
      text, open: () => openPerspective(resource, row.perspective, e.post),
    }
  }
  const unique = (rows: (SearchEntry | null)[]): SearchEntry[] => {
    const by = new Map<string, SearchEntry>()
    for (const row of rows) if (row && !by.has(row.key)) by.set(row.key, row)
    return [...by.values()]
  }
  return {
    entries(): SearchEntry[] {
      const s = store.snapshot()
      const viewed = s.rows.find((p) => p.perspective === (s.viewed ?? s.selected))
      return unique([
        ...s.rows.map(rowEntry),
        ...(viewed ? s.events.map((e) => wordingEntry(viewed, e)) : []),
      ])
    },
    async complete(_query, signal): Promise<SearchEntry[]> {
      stopped = null
      const out: (SearchEntry | null)[] = []
      try {
        const rows: Perspective[] = []
        await walkPages(async (cursor) => {
          if (signal?.aborted) throw new Error('The search was abandoned before it finished.')
          const v = await store.get('?' + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
          if (Array.isArray(v.perspectives)) rows.push(...v.perspectives)
          return v.next ?? null
        })
        for (const row of rows) {
          out.push(rowEntry(row))
          await walkPages(async (cursor) => {
            if (signal?.aborted) throw new Error('The search was abandoned before it finished.')
            const v = await store.get(`/${row.perspective}/history?` + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
            if (v.perspective !== row.perspective) throw new Error('History answered for another Perspective.')
            for (const e of Array.isArray(v.events) ? v.events : []) out.push(wordingEntry(row, e))
            return v.next ?? null
          })
        }
      } catch (e) {
        // Say what was reached, rather than claim a complete search.
        stopped = `Perspectives and their wording history were searched only as far as they could be read: ${(e as Error).message}`
      }
      return unique(out)
    },
    queryDependent: false,
    bound: () => stopped,
  }
}
/** Preserve the shared Composer's addressing, runtime, reply and Work choices. */
export function perspectiveRequest(post: Record<string, unknown>, prepared: PreparedInquiry) {
  if (!PERSPECTIVE_ANSWERS_ENABLED) throw new Error(PERSPECTIVE_BLOCK_REASON)
  return { ...post, text: prepared.text, topics: [...new Set([...(Array.isArray(post.topics) ? post.topics : []), prepared.perspective])],
    parts: [{ type: 'text', text: prepared.text }, ...(Array.isArray(post.parts) ? post.parts.filter((p: any) => p.type !== 'text') : []), ...prepared.parts],
    _magnetPerspective: prepared,
    dispatch: (Array.isArray(post.dispatch) ? post.dispatch : []).map((spec: any) => ({ ...spec, reach: 'work', requires: [...new Set([...(spec.requires ?? []), 'call_mentis_tools'])], work: `Use the attached frozen Perspective records, manifest and evidence. Read them with read_artifact. Reconstruct the inquiry by its Topic ${prepared.perspective}, distinguish original support from interpretations and conflicting evidence, cite the exact versions/ranges, and answer the frozen question. ${PERSPECTIVE_DISCLOSURE}` })) }
}
