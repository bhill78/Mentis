import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, confirmBrain, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import { conversationSeed } from '../../fluid/surface/magnet/choices'
import type { SavedMagnet } from './contract'
import { unsupportedMagnet } from './read'

export const entryId = (v: unknown): v is string => typeof v === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v)
export const resourceCorpus = (key: string) => key.split('|').at(-1) ?? ''
export function matchesBinding(key: string) {
  return !!key && !page.moved() && page.bound()?.split('@')[0] === resourceCorpus(key)
}
export interface ConversationChoice { id: string; name: string }
export async function listMagnets(signal?: AbortSignal): Promise<SavedMagnet[]> {
  const r = await fetch('/fluid/api/magnets', { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
  const v = await r.json().catch(() => null)
  if (!r.ok || !Array.isArray(v?.magnets)) throw new Error(v?.error ?? 'Magnets unavailable.')
  return v.magnets.flatMap((row: { id?: unknown; name?: unknown; config?: unknown; reason?: unknown }) => {
    if (typeof row.id !== 'string' || !/^mag-[a-zA-Z0-9_-]{1,60}$/.test(row.id) || typeof row.name !== 'string') return []
    const reason = typeof row.reason === 'string' ? row.reason : row.config ? unsupportedMagnet(row.config, row.id) : 'The Magnet definition is unavailable.'
    return [{ id: row.id as `mag-${string}`, name: row.name, ...(row.config ? { config: row.config as SavedMagnet['config'] } : {}), ...(reason ? { reason } : {}) }]
  })
}
export async function conversationChoices(q: string, cursor: string | null, signal: AbortSignal): Promise<{ rows: ConversationChoice[]; next: string | null }> {
  const params = new URLSearchParams({ activity: '1', limit: '40', state: 'active' })
  if (q.trim()) params.set('q', q.trim())
  if (cursor) params.set('cursor', cursor)
  const r = await fetch('/fluid/api/conversations?' + params, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
  const v = await r.json()
  if (!r.ok || !Array.isArray(v?.conversations)) throw new Error(v?.error ?? 'Conversations unavailable.')
  return { rows: v.conversations.filter((c: ConversationChoice) => entryId(c.id) && typeof c.name === 'string').map((c: ConversationChoice) => ({ id: c.id, name: c.name })), next: typeof v.next === 'string' ? v.next : null }
}
/** Existing atomic create-and-place door. No whole arrangement save or own-C creation.
 *
 *  `source` MAY BE EMPTY. A Magnet is an idea first: it is created with a name and
 *  no configured source, conversed with, and told what to collect afterwards
 *  (request §4). An empty `source` sends a seed whose `sources` is the empty list,
 *  which is exactly what is kept: no source is substituted, and the answer is
 *  checked against what was asked either way. */
/** ONE SENTENCE IN, A PROPOSAL OUT (Part G1's contract,
 *  `docs/magnets/part-b-collection-api.md` "The proposal").
 *
 *  Everything in `words` and `listed` is already in ordinary words, and
 *  everything in `seed`, `change` and `cadence` has already passed the Magnet
 *  schema on the server. The client renders the first and sends back the
 *  second; it does not compose a configuration of its own, and it never
 *  decides which source kinds are available -- that is derived on the server
 *  from the source registry and the activation contract, at the moment the
 *  proposal is asked for. */
export interface MagnetProposal {
  sentence: string
  name: string
  sources: { kind: string }[]
  selection: Record<string, unknown>
  cadence: { mode: string; schedule?: string }
  words: { sources: string; collect: string; cadence: string }
  listed: { title: string; says: string }[]
  seed: Record<string, unknown>
  change: Record<string, unknown>
  unavailable: { title: string; kind: string; why: string }[]
}
const words = (v: unknown): string => typeof v === 'string' ? v : ''
const rows = (v: unknown): { title: string; says: string }[] => Array.isArray(v)
  ? v.flatMap((r) => r && typeof r === 'object' && typeof (r as { title?: unknown }).title === 'string'
    ? [{ title: (r as { title: string }).title, says: words((r as { says?: unknown }).says) }] : []) : []
/** Ask what following this would look like. Reads only: nothing is written by
 *  this, on the server or here, so it may be asked as often as it is retyped. */
export async function proposeMagnet(sentence: string, magnet?: string, signal?: AbortSignal): Promise<MagnetProposal> {
  if (!sentence.trim()) throw new Error('Say in one sentence what you want this Magnet to follow.')
  const r = await fetch('/fluid/api/magnets/propose', {
    method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' }, signal, cache: 'no-store',
    body: JSON.stringify({ sentence: sentence.trim(), ...(magnet ? { magnet } : {}) }),
  })
  const v = await r.json().catch(() => null)
  const p = v?.proposal
  if (!r.ok || !p || typeof p.name !== 'string' || !Array.isArray(p.sources) || !p.seed || !p.change)
    throw new Error(v?.error ?? `A proposal is unavailable just now (${r.status}).`)
  return {
    sentence: words(p.sentence) || sentence.trim(), name: p.name, sources: p.sources,
    selection: p.selection ?? {}, cadence: p.cadence ?? { mode: 'one-time' },
    words: { sources: words(p.words?.sources), collect: words(p.words?.collect), cadence: words(p.words?.cadence) },
    listed: rows(p.listed), seed: p.seed, change: p.change,
    unavailable: Array.isArray(p.unavailable) ? p.unavailable : [],
  }
}

/** WHAT ONE ACCEPTANCE DID, in the words the owner is shown where the results
 *  would be. `collected` is null where no collection was attempted at all. */
export interface AcceptedMagnet { saved: SavedMagnet; collected: number | null; words: string; refreshing: boolean }
/** No sources is an answer, not a fault (#521 §4) -- but it is not a silent
 *  screen either, so it says the one thing to do about it. */
export const NOTHING_TO_COLLECT_YET = 'This Magnet has no sources yet, so there was nothing to collect. Add a source in Settings and it will collect from it.'
const collectedWords = (n: number, cadence: string) => n > 0
  ? `Collected ${n} ${n === 1 ? 'item' : 'items'}. ${cadence || 'It will look again on its own'}.`
  : `Nothing was collected from these sources yet — they hold nothing this Magnet reads. Open Sources to change what it follows; ${(cadence || 'it will look again').toLowerCase()}, so new information arrives on its own.`

async function owner(): Promise<string> {
  const r = await fetch('/fluid/api/participants?limit=1', { headers: CLIENT_HEADERS, cache: 'no-store' })
  const v = await r.json().catch(() => null)
  if (!r.ok || !entryId(v?.me)) throw new Error('The server did not identify the owner, so nothing was collected.')
  return v.me
}

/** ONE ACCEPTANCE: APPLY, COLLECT, AND BE LOOKING AT THE RESULTS.
 *
 *  The owner's correction `ent-8a4357b5f7fc` and amendment §4: purpose-driven
 *  creation leads directly to activation and useful results, with no tour of
 *  configuration screens. So this press does all three, through the doors that
 *  already exist (no new agent path, no new accept door):
 *
 *    1. `arrangements/<key>/magnets`  -- the proposal's seed becomes the Magnet
 *    2. `magnets/<id>/activate`       -- its first collection runs
 *    3. `.../reconfigure`             -- the cadence, so refresh is on from the start
 *
 *  THE CADENCE LANDS LAST, AND ONLY WITH A SOURCE TO REFRESH. This build's
 *  manual activation requires `collection.mode = one-time`
 *  (`mentis.magnet.activation._cannot_run_code`), so a definition carrying the
 *  cadence cannot be collected by hand; the first collection therefore runs
 *  from the one-time facets and the cadence is applied immediately after it, in
 *  the same press. With no source there is nothing to refresh, so no cadence is
 *  sent and the words say what to do instead.
 *
 *  A FAILED STEP IS SAID, NOT THROWN AWAY. Once the Magnet exists it is
 *  returned whatever the later steps did, with what happened in plain words:
 *  an empty or failed first collection must not leave a silent screen. */
export async function acceptProposal(at: { key: string; arrangement: string; proposal: MagnetProposal; op: string; manual?: boolean }): Promise<AcceptedMagnet> {
  const saved = await makeMagnet({ key: at.key, arrangement: at.arrangement, source: '', name: at.proposal.name, op: at.op, manual: at.manual, seed: at.proposal.seed })
  const cadence = at.proposal.words.cadence
  if (!saved.config?.sources.length) return { saved, collected: null, words: NOTHING_TO_COLLECT_YET, refreshing: false }
  let collected: number | null = null, said = ''
  try {
    const me = await owner()
    const r = await fluidFetch(`/fluid/api/magnets/${encodeURIComponent(saved.id)}/activate`, {
      method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: page.bound()!, 'Content-Type': 'application/json' },
      body: JSON.stringify({ author: me, op: `${at.op}-collect` }),
    })
    const v = await r.json().catch(() => null)
    if (refusedAsOtherBrain(r.status, v)) page.move()
    if (!r.ok || !v?.artifact?.ref || v.magnet !== saved.id) throw new Error(v?.error ?? `The first collection's outcome is unknown (${r.status}).`)
    if (v.conversation && saved.config) saved.config.conversation = v.conversation
    const got = typeof v.page?.results === 'number' ? v.page.results : 0
    collected = got
    said = collectedWords(got, cadence)
  } catch (e) {
    said = `${(e as Error).message} Open Sources to check what this Magnet follows; ${(cadence || 'it will look again').toLowerCase()}, so it will try again on its own.`
  }
  let refreshing = false
  if (at.proposal.cadence.mode === 'scheduled' && at.proposal.cadence.schedule) {
    try {
      const config = await reconfigure({ key: at.key, arrangement: at.arrangement, magnet: saved.id, change: { collection: at.proposal.cadence }, op: `${at.op}-cadence` })
      saved.config = config; saved.reason = unsupportedMagnet(config, saved.id); refreshing = true
    } catch { /* The Magnet is configured and has collected; the cadence can be set in Settings. */ }
  }
  return { saved, collected, words: said, refreshing }
}

/** The existing reconfigure door, addressed through a saved location, which is
 *  where its operation key is kept. Nothing about the change depends on that
 *  location: the definition belongs to no arrangement. */
async function reconfigure(at: { key: string; arrangement: string; magnet: string; change: Record<string, unknown>; op: string }): Promise<SavedMagnet['config']> {
  if (!matchesBinding(at.key)) throw new Error('The Brain changed before the cadence was applied.')
  const r = await fluidFetch(`/fluid/api/arrangements/${encodeURIComponent(at.arrangement)}/magnets/${encodeURIComponent(at.magnet)}/reconfigure`, {
    method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: page.bound()!, 'Content-Type': 'application/json' },
    body: JSON.stringify({ change: at.change, op: at.op }),
  })
  const v = await r.json().catch(() => null)
  if (refusedAsOtherBrain(r.status, v)) page.move()
  if (!r.ok || v?.magnet?.id !== at.magnet) throw new Error(v?.error ?? `The cadence was not applied (${r.status}).`)
  return v.magnet as SavedMagnet['config']
}

export async function makeMagnet(at: { key: string; arrangement: string; source: string; name: string; op: string; manual?: boolean; seed?: Record<string, unknown> }): Promise<SavedMagnet> {
  if ((at.arrangement !== 'home' && !entryId(at.arrangement)) || (at.source !== '' && !entryId(at.source)) || !at.name.trim() || at.name.length > 80) throw new Error('Give the Magnet a name of at most 80 characters, and either one source Conversation or none.')
  if (await confirmBrain() !== true || !matchesBinding(at.key)) throw new Error('Creation unavailable: this page cannot confirm its Brain. Your choices are kept.')
  const path = `/fluid/api/arrangements/${encodeURIComponent(at.arrangement)}`
  const existing = await fetch(path, { headers: CLIENT_HEADERS, cache: 'no-store' })
  const saved = await existing.json().catch(() => null)
  if (!existing.ok || !saved || !('layout' in saved)) throw new Error('The saved arrangement is unavailable. Nothing was created.')
  // A PROPOSAL'S SEED IS SENT AS THE SERVER BUILT IT (Part G1). It is a whole
  // definition the Magnet schema has already checked, so nothing here composes
  // one or substitutes a facet; only the name is written in, exactly as a
  // name-only creation writes it.
  const seed: Record<string, any> = at.seed ? { ...at.seed } : conversationSeed(at.source)
  // The Magnet's own name goes in the definition, so it is the Magnet's wherever
  // it is drawn, not the zone's. The zone is still named the same, so a build
  // that does not read `identity` shows what it always showed.
  seed.identity = { name: at.name.trim() }
  if (!at.seed && !at.source) seed.sources = []
  // Opening never activates; Collect explicitly runs the supported manual extraction.
  // The established read-only fixture proxy deliberately grants no activation.
  if (at.manual === false) { delete seed.activation; delete seed.processing }
  const r = await fluidFetch(`/fluid/api/arrangements/${encodeURIComponent(at.arrangement)}/magnets`, {
    method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: page.bound()!, 'Content-Type': 'application/json' },
    body: JSON.stringify({ seed, op: at.op, attach: {
      zone: { type: 'zone', show: 'magnet', name: at.name.trim() },
      ...(saved.layout === null ? { base: { format: 'mentis.fluid-arrangement', version: 2, tree: { type: 'zone', id: 'quiet-objects', show: 'objects' } } } : {}),
    } }),
  })
  const v = await r.json().catch(() => null)
  if (refusedAsOtherBrain(r.status, v)) page.move()
  if (!r.ok || !v?.magnet || v.error) throw new Error(v?.error ?? `Creation outcome unavailable (${r.status}). Refresh the list before trying again.`)
  const config = v.magnet
  if (typeof config.id !== 'string' || !/^mag-[a-zA-Z0-9_-]{1,60}$/.test(config.id)) throw new Error('Creation answered without a usable Magnet identity. Refresh the list before trying again.')
  // THE ANSWER IS CHECKED AGAINST WHAT WAS ASKED, whichever creation this was:
  // a proposal's own sources, exactly one named Conversation, or none.
  const wanted = JSON.stringify(seed.sources ?? [])
  const asked = at.seed
    ? JSON.stringify(config.sources ?? []) === wanted
    : at.source
      ? config.sources?.length === 1 && config.sources[0]?.kind === 'conversation' && config.sources[0]?.conversation === at.source
      : config.sources?.length === 0
  if (!matchesBinding(at.key) || !asked) throw new Error('Creation answered for a different Brain or source. Refresh the list to check the result; nothing was opened.')
  return { id: config.id, name: at.name.trim(), config, reason: unsupportedMagnet(config, config.id) }
}
