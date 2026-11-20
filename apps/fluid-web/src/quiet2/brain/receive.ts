/* WHAT AN AGENT WOULD BE GIVEN, AS AN OUTLINE: the pure part of Quiet Chat's
 * preview (`ReceivePreview.tsx`), checked without a browser
 * (`tests/quiet_receive_unit.ts`).
 *
 * `/api/context` answers with one flat list: every piece a run started here
 * would be handed, each with the engine's own `scope` (how it reaches) and
 * `tier` (what standing it is delivered with). This file sorts that list
 * into the outline a person reads: three sections by WHY a piece is given
 * (it must be followed; it is knowledge matched to the work; it is what any
 * run is sent), and inside each, groups by WHERE it comes from (the Persona,
 * named for this run, this conversation, the whole Brain). One line per
 * piece; the full words stay on the piece and are shown on request.
 *
 * NOTHING IS DROPPED AND NOTHING IS SHOWN TWICE: every component of the
 * answer lands in exactly one group, including a scope or tier this file has
 * never heard of ("other"), and `text` is carried through untouched.
 *
 * THE WORDS HERE ARE FOR A PERSON. The engine's own sentences ("durable
 * material placed on the whole Brain") are what delivery records keep and
 * are not changed; they are read from `scope`, never re-worded in place, and
 * a reason this file does not recognise is shown as the engine wrote it. */
import { kindWords } from './logic'

export interface ReceiveTrailer {
  why?: string | null
  why_holds?: string | null
  supports?: string[] | null
  outcomes_total?: number | null
  status?: string | null
  limits?: string | null
  recorded_by?: {
    alias?: string | null; runtime?: string | null; model?: string | null; persona_name?: string | null; conversation?: string | null
    conversation_name?: string | null; number?: number | null; at?: number | null
  } | null
  basis?: Array<{
    ref?: string; label?: string | null; relation?: string | null; kind?: string | null; cite?: string | null
    artifact?: { name?: string | null } | null; range?: [number, number] | null; excerpt?: string | null
  }> | null
  outcomes?: Array<{ id?: string; result?: string | null; text?: string | null; attempted?: boolean | null; in_context?: string | null; recorded_at?: number | null }> | null
  challenges?: Array<{ by?: string | null; by_alias?: string | null; because?: string | null }> | null
}

export interface ReceiveComponent {
  source_kind: string
  source_id: string | null
  scope: string
  text: string
  why: string
  about?: string
  title?: string
  also?: string[]
  tier?: string | null
  trailer?: ReceiveTrailer | null
}

export interface ReceiveWithheld {
  source_kind: string | null
  source_id: string | null
  scope?: string
  why: string
  tier?: string
  rank?: number
  superseded_by?: string
  delivered_instead?: string
}

export interface ReceiveAnswer {
  scope?: 'conversation' | 'brain'
  work?: string
  components: ReceiveComponent[]
  withheld: ReceiveWithheld[]
  conflicts?: Array<{ about: string; components: string[] }>
  payload_chars?: number
}

export type SectionKey = 'governing' | 'knowledge' | 'also' | 'unknown'
export type GroupKey =
  | 'persona' | 'named' | 'conversation' | 'brain' | 'governing-other'
  | 'adopted' | 'experience'
  | 'sent'
  /** a tier this file does not know, kept by its raw name */
  | `tier:${string}`

export interface OutlineItem {
  /** stable within one answer: the record's id where it has one */
  key: string
  component: ReceiveComponent
  kind: string
  title: string
  because: string
  /** the record to open, or null where the piece is not a record */
  record: string | null
}
export interface OutlineGroup { key: GroupKey; label: string; hint: string; items: OutlineItem[] }
type KnownGroup = Exclude<GroupKey, `tier:${string}`>
export interface OutlineSection { key: SectionKey; label: string; hint: string; count: number; groups: OutlineGroup[] }

/** What the lookups an outline needs are called by: a Persona's name by its
 *  id, and whether the preview is taken in a conversation. */
export interface OutlineNames { personas?: Record<string, string>; inConversation?: boolean }

const SECTIONS: Record<SectionKey, { label: string; hint: string }> = {
  governing: { label: 'Governing', hint: 'Adopted by the owner. The agent is told to follow these.' },
  knowledge: { label: 'Knowledge', hint: 'Matched to the work described above. Told to the agent; it does not bind it.' },
  also: { label: 'Also sent', hint: 'Not Brain records: what any run here is sent alongside them.' },
  unknown: { label: 'Other', hint: 'Given on a standing this page does not know. Shown as the server described it; read each one before relying on it.' },
}

const GROUPS: Record<KnownGroup, { section: SectionKey; label: string; hint: string }> = {
  persona: { section: 'governing', label: 'From the Persona', hint: 'The Persona itself and what it carries. They reach this run because it is started as this Persona.' },
  named: { section: 'governing', label: 'Named for this run', hint: 'Records given to this one run by name, on top of what is placed.' },
  conversation: { section: 'governing', label: 'Placed on this conversation', hint: 'Given to every agent that works in this conversation.' },
  brain: { section: 'governing', label: 'Placed on the whole Brain', hint: 'Given to every agent: in every conversation, and in work done outside any conversation.' },
  'governing-other': { section: 'governing', label: 'Other governing records', hint: 'Governing records that reach this run another way.' },
  adopted: { section: 'knowledge', label: 'Adopted knowledge', hint: 'The Brain’s working position. The agent is told to use it, within its limits.' },
  experience: { section: 'knowledge', label: 'Relevant experience', hint: 'Recorded by agents and not adopted. The agent is told to weigh it as evidence, not follow it.' },
  sent: { section: 'also', label: 'Orientation and request', hint: 'Where the agent is and what is being asked, worked out at the time.' },
}

const ORDER: KnownGroup[] = ['persona', 'named', 'conversation', 'brain', 'governing-other', 'adopted', 'experience', 'sent']

const NOT_RECORDS = new Set(['orientation', 'brain-orientation', 'request', 'invocation'])

/** Which group a piece belongs to: its tier first (what standing it is
 *  delivered with), then its scope (how it reaches). Total: every component
 *  gets exactly one answer. */
export function groupOf(c: ReceiveComponent): GroupKey {
  if (c.tier === 'adopted') return 'adopted'
  if (c.tier === 'experience') return 'experience'
  if (c.tier === 'governing') {
    const s = c.scope ?? ''
    if (s === 'invocation:persona' || s.startsWith('persona:')) return 'persona'
    if (s === 'invocation:named') return 'named'
    if (s.startsWith('conversation:')) return 'conversation'
    if (s === 'whole-brain') return 'brain'
    return 'governing-other'
  }
  // ON NO TIER, AND NOT A RECORD: the orientation, the request, text for one
  // run. Anything else -- a tier this file has never heard of, or a record
  // the answer put on no tier -- is NOT filed under "not Brain records": it
  // keeps the tier the server gave it, said as the server said it.
  if (c.tier == null && (!c.source_id || NOT_RECORDS.has(c.source_kind))) return 'sent'
  return `tier:${c.tier ?? 'none'}`
}

const groupWords = (g: GroupKey): { section: SectionKey; label: string; hint: string } => {
  if (!g.startsWith('tier:')) return GROUPS[g as KnownGroup]
  const raw = g.slice('tier:'.length)
  return raw === 'none'
    ? { section: 'unknown', label: 'No tier stated', hint: 'Records the server gave without saying whether they govern or are knowledge.' }
    : { section: 'unknown', label: `Tier “${raw}”`, hint: 'The server’s own name for this standing. This page does not know what it asks of the agent.' }
}

const KIND_WORDS: Record<string, string> = {
  orientation: 'Orientation',
  'brain-orientation': 'Orientation',
  request: 'Request',
  invocation: 'Text for this run',
  'conversation-instruction': 'Conversation instruction',
}
export const kindOf = (c: { source_kind: string | null }): string =>
  KIND_WORDS[c.source_kind ?? ''] ?? kindWords(c.source_kind ?? '')

const TITLE_MAX = 110

/** The first sentence of a text, on one line: up to the first full stop,
 *  question or exclamation mark that ends a sentence, or the first line
 *  break, and never longer than a line can hold. A cut is marked with an
 *  ellipsis; the whole text is still on the piece. */
export function firstSentence(text: string, max = TITLE_MAX): string {
  const flat = (text ?? '').trim()
  if (!flat) return ''
  const line = flat.split(/\r?\n/).find((l) => l.trim())?.trim() ?? ''
  const m = /^(.+?[.!?])(?=\s|$)/.exec(line)
  let s = (m ? m[1] : line).replace(/\s+/g, ' ')
  if (s.length > max) {
    const cut = s.slice(0, max)
    const at = cut.lastIndexOf(' ')
    s = (at > max * 0.6 ? cut.slice(0, at) : cut).replace(/[\s,;:.\-]+$/, '') + '…'
  }
  return s
}

/** One readable line for a piece: a Persona by its name, a record whose Kind
 *  has a name of its own (a Workflow, a Discipline) by that name, anything
 *  else by its first sentence. */
export function titleOf(c: ReceiveComponent, names: OutlineNames = {}): string {
  if (c.source_kind === 'persona' && c.source_id && names.personas?.[c.source_id]) return names.personas[c.source_id]
  if (c.source_kind === 'orientation') return 'Where this conversation stands'
  if (c.source_kind === 'brain-orientation') return 'What this Brain holds: names and counts'
  const named = (c.title ?? '').trim()
  if (named) return firstSentence(named.split(/\s+[—–]\s+/)[0] || named)
  return firstSentence(c.text) || kindOf(c)
}

function alsoWords(also: string[] | undefined): string {
  const said: string[] = []
  for (const s of also ?? []) {
    if (s === 'whole-brain') said.push('also placed on the whole Brain')
    else if (s === 'invocation:named') said.push('also named for this run')
    else if (s.startsWith('conversation:')) said.push('also placed on this conversation')
    else if (s.startsWith('persona:') || s === 'invocation:persona') said.push('also carried by the Persona')
    // A PATH THIS FILE DOES NOT KNOW IS STILL A PATH: said as the engine wrote it
    else if (s) said.push(`also “${s}”`)
  }
  return said.length ? '; ' + said.join('; ') : ''
}

/** Why a piece is given, in plain words, read from how the engine scoped it.
 *  A scope this file does not know is answered with the engine's own
 *  sentence rather than a guess. */
export function becauseOf(c: ReceiveComponent, names: OutlineNames = {}): string {
  const s = c.scope ?? ''
  const tail = alsoWords(c.also)
  if (c.tier === 'adopted') return 'adopted knowledge that matches the work'
  if (c.tier === 'experience') {
    return /^concluded from /i.test(c.why ?? '')
      ? 'not adopted; concluded from a record that matches the work'
      : 'not adopted; recorded experience that matches the work'
  }
  if (s === 'invocation:persona') return 'the Persona this agent is started as' + tail
  if (s.startsWith('persona:')) {
    const name = names.personas?.[s.slice('persona:'.length)]
    return (name ? `carried by the Persona ${name}` : 'carried by the Persona') + tail
  }
  if (s === 'invocation:named') {
    const replaced = /which it supersedes/.test(c.why ?? '')
    return 'named for this run' + (replaced ? ', in place of the earlier version it replaces' : '') + tail
  }
  if (c.source_kind === 'orientation' || c.source_kind === 'brain-orientation') return 'worked out now, not a record'
  if (c.source_kind === 'request') return 'what is being asked'
  if (c.source_kind === 'invocation') return 'text supplied for this run only'
  if (s.startsWith('conversation:')) return 'placed on this conversation' + tail
  if (s === 'whole-brain') return 'placed on the whole Brain' + tail
  return ((c.why ?? '').trim() || 'given to this run') + tail
}

const STOCK_WHY = [
  /^the participant is operating as /,
  /^carried by the Persona .* this participant is operating as$/,
  /^named explicitly for this invocation$/,
  /^durable material placed at this conversation$/,
  /^durable material placed on the whole Brain$/,
  /^supplied for this invocation only$/,
  /^compact orientation, computed now$/,
  /^compact brain orientation, computed now; names and counts only$/,
  /^what is being asked now$/,
]

/** The engine's own reason, where it says more than `becauseOf` did (which
 *  record a finding was concluded from, which version a named record
 *  replaced). Null where the plain words already say all of it. */
export function engineReason(c: ReceiveComponent): string | null {
  const why = (c.why ?? '').trim()
  if (!why || STOCK_WHY.some((r) => r.test(why))) return null
  return why
}

/** The outline: sections in reading order, each with its groups, each group
 *  with one item per piece, in the order the engine gave them. Empty groups
 *  are left out; the three sections are always there, so an empty one can
 *  say that it is empty. A fourth, "Other", appears only for a tier this
 *  file does not know, so such a piece is never filed as something it is not. */
export function outline(components: ReceiveComponent[], names: OutlineNames = {}): OutlineSection[] {
  const by = new Map<GroupKey, OutlineItem[]>()
  const seen = new Map<string, number>()
  components.forEach((c, i) => {
    const base = c.source_id ? `${c.source_id}|${c.scope}` : `${c.source_kind}|${c.scope}|${i}`
    const n = seen.get(base) ?? 0
    seen.set(base, n + 1)
    const g = groupOf(c)
    const item: OutlineItem = {
      key: n ? `${base}|${n}` : base,
      component: c,
      kind: kindOf(c),
      title: titleOf(c, names),
      because: becauseOf(c, names),
      record: c.source_id && !NOT_RECORDS.has(c.source_kind) ? c.source_id : null,
    }
    by.set(g, [...(by.get(g) ?? []), item])
  })
  const order: GroupKey[] = [...ORDER, ...[...by.keys()].filter((g) => g.startsWith('tier:'))]
  const all = (['governing', 'knowledge', 'also', 'unknown'] as SectionKey[]).map((key) => {
    const groups = order.filter((g) => groupWords(g).section === key && by.has(g)).map((g) => {
      const w = groupWords(g)
      const hint = g === 'conversation' && names.inConversation === false ? 'Given to every agent that works in that conversation.' : w.hint
      return { key: g, label: w.label, hint, items: by.get(g)! }
    })
    return { key, ...SECTIONS[key], count: groups.reduce((n, g) => n + g.items.length, 0), groups }
  })
  // the fourth section exists only when the answer has something for it
  return all.filter((s) => s.key !== 'unknown' || s.count > 0)
}

export const countItems = (sections: OutlineSection[]): number => sections.reduce((n, s) => n + s.count, 0)

export const plural = (n: number, one: string, many = one + 's'): string => `${n} ${n === 1 ? one : many}`

/** One line of detail under a piece: words, and the records it names, each
 *  to be opened by its exact id. */
export interface DetailLine { text: string; warn?: boolean; refs?: { id: string; label: string }[] }

const isRecord = (id: string | null | undefined): id is string => !!id && id.startsWith('ent-')

/** The details a piece carries beyond its words, each as one plain line: its
 *  subject, why it holds and what supports it, who recorded it and from
 *  what, its limits, how it has gone (saying so when only the latest few of
 *  more outcomes are shown), its standing, and any open challenge.
 *  What the answer says about a piece in words is said; the internal ids of
 *  who recorded it (participant, turn, execution) are not listed, and the
 *  record itself, one press away, has them. */
export function trailerLines(c: ReceiveComponent, when: (ts: number) => string = (ts) => new Date(ts * 1000).toLocaleDateString()): DetailLine[] {
  const t = c.trailer
  const out: DetailLine[] = []
  const about = (c.about ?? '').trim()
  if (about && !(c.title ?? '').includes(about)) out.push({ text: `Subject: ${about}` })
  if (!t) return out
  const governing = c.tier === 'governing'
  const holds = t.why ?? t.why_holds
  if (holds) out.push({ text: /^why this holds/i.test(holds) ? holds.charAt(0).toUpperCase() + holds.slice(1) : `Why this holds: ${holds}` })
  const supports = (t.supports ?? []).filter(Boolean)
  if (supports.length > 0) {
    out.push({ text: `Supported by ${plural(supports.length, 'record')}`, refs: supports.filter(isRecord).map((id, i) => ({ id, label: `supporting record ${i + 1}` })) })
  }
  const rb = t.recorded_by
  if (rb?.alias) {
    let who = `Recorded by ${rb.alias.replace(/^@/, '')}`
    if (rb.persona_name) who += ` as ${rb.persona_name}`
    if (rb.runtime) who += ` on ${rb.runtime}${rb.model ? ` (${rb.model})` : ''}`
    if (rb.conversation_name || rb.conversation) who += ` in ${rb.conversation_name ?? rb.conversation}${rb.number != null ? ` #${rb.number}` : ''}`
    if (rb.at != null) who += `, ${when(rb.at)}`
    out.push({ text: who })
  }
  const basis = t.basis ?? []
  if (basis.length > 0) {
    out.push({
      text: `Rests on: ${basis.map(basisWords).join('; ')}`,
      refs: basis.filter((b) => isRecord(b.ref)).map((b) => ({ id: b.ref!, label: firstSentence(b.label || 'the source', 48) })),
    })
  } else if (!governing) out.push({ text: 'No basis recorded.' })
  if (t.limits) out.push({ text: `Limits: ${t.limits}` })
  const outcomes = t.outcomes ?? []
  if (outcomes.length > 0 || (t.outcomes_total ?? 0) > 0) {
    // A COUNT IS SAID ONLY WHERE THE ANSWER GIVES ONE. A governing record's
    // trailer carries its latest few outcomes and no total (the total is in
    // its "why this holds" sentence, above); calling those few "N recorded
    // outcomes" would contradict that sentence whenever there are more.
    const total = t.outcomes_total == null ? null : Math.max(t.outcomes_total, outcomes.length)
    const head = total == null ? 'The latest outcomes shown here'
      : total > outcomes.length ? `Showing the latest ${outcomes.length} of ${plural(total, 'recorded outcome')}` : plural(total, 'recorded outcome')
    const said = outcomes.map((o) => outcomeWords(o, when)).join('; ')
    const refs = outcomes.filter((o) => isRecord(o.id)).map((o, i) => ({ id: o.id!, label: `outcome ${i + 1}` }))
    outcomes.forEach((o, i) => { if (isRecord(o.in_context)) refs.push({ id: o.in_context, label: `where outcome ${i + 1} happened` }) })
    out.push({ text: said ? `${head}: ${said}` : head, refs })
  }
  if (t.status && !governing) out.push({ text: t.status === 'adopted' ? 'Adopted.' : t.status === 'recorded' ? 'Recorded, not adopted.' : `${t.status.replace(/_/g, ' ')}, not adopted.` })
  const ch = t.challenges ?? []
  if (ch.length > 0) {
    const said = ch.map((x) => `${(x.by_alias ?? x.by ?? 'somebody').replace(/^@/, '')}: “${x.because ?? ''}”`).join('; ')
    out.push({ warn: true, text: governing ? `${plural(ch.length, 'open challenge')} (${said}). Still in effect.` : `Challenged (${said}).` })
  }
  return out
}

/** One outcome as it was recorded: its result, whether it was actually
 *  tried, when, and its words. */
function outcomeWords(o: NonNullable<ReceiveTrailer['outcomes']>[number], when: (ts: number) => string): string {
  const bits = [o.result ?? 'observed']
  if (o.attempted === true) bits.push('attempted')
  else if (o.attempted === false) bits.push('not attempted')
  if (o.recorded_at != null) bits.push(when(o.recorded_at))
  return bits.join(', ') + (o.text ? ` (${o.text})` : '')
}

/** One thing a record rests on: its name, how it rests on it, the place in
 *  it that is cited, and the words cited where the answer carries them. */
function basisWords(b: NonNullable<ReceiveTrailer['basis']>[number]): string {
  let s = b.label || b.artifact?.name || b.ref || 'a source'
  if (b.artifact?.name && b.artifact.name !== s) s += `, ${b.artifact.name}`
  const how = [b.relation ? b.relation.replace(/-/g, ' ') : '', b.cite ? `cited: ${b.cite}` : '', b.range ? `bytes ${b.range[0]}–${b.range[1]}` : ''].filter(Boolean)
  if (how.length) s += ` (${how.join('; ')})`
  if (b.excerpt) s += ` “${b.excerpt}”`
  return s
}

/** A scope in plain words where this file knows it, and as the engine wrote
 *  it where it does not. */
export function scopeWords(scope: string, names: OutlineNames = {}): string {
  if (scope === 'whole-brain') return 'placed on the whole Brain'
  if (scope === 'invocation:named') return 'named for this run'
  if (scope === 'invocation:persona') return 'the Persona this agent is started as'
  if (scope.startsWith('conversation:')) return 'placed on this conversation'
  if (scope.startsWith('persona:')) {
    const name = names.personas?.[scope.slice('persona:'.length)]
    return name ? `carried by the Persona ${name}` : 'carried by the Persona'
  }
  return `“${scope}”`
}

/** What else the answer says about something left out, beside the reason:
 *  which tier it was considered for and where it ranked, how it would have
 *  reached the run, and the record given in its place. */
export function withheldMeta(w: ReceiveWithheld, names: OutlineNames = {}): DetailLine | null {
  const parts: string[] = []
  if (w.tier) parts.push(w.tier === 'adopted' ? 'considered as adopted knowledge' : w.tier === 'experience' ? 'considered as relevant experience' : `considered on the tier “${w.tier}”`)
  if (w.rank != null) parts.push(`ranked ${w.rank}`)
  if (w.scope) parts.push(`would have reached this run as: ${scopeWords(w.scope, names)}`)
  const next = w.delivered_instead ?? w.superseded_by
  const refs = isRecord(next) ? [{ id: next, label: w.delivered_instead ? 'the version given instead' : 'the version that replaced it' }] : []
  if (next && !refs.length) parts.push(`replaced by ${next}`)
  if (!parts.length && !refs.length) return null
  return { text: parts.join(' · '), refs }
}

/** The pieces that speak to one subject, each named and, where it is a
 *  record, openable by its exact id. A member the answer names only by its
 *  kind (it has no id) is said by that kind. */
export function conflictMembers(members: string[], components: ReceiveComponent[], names: OutlineNames = {}): { id: string | null; kind: string; title: string }[] {
  return members.map((m) => {
    const c = components.find((x) => x.source_id === m)
    if (c) return { id: isRecord(m) && !NOT_RECORDS.has(c.source_kind) ? m : null, kind: kindOf(c), title: titleOf(c, names) }
    return isRecord(m) ? { id: m, kind: 'Record', title: 'A record' } : { id: null, kind: kindOf({ source_kind: m }), title: '' }
  })
}

/** Why something was left out, in plain words; the engine's own sentence
 *  where it is already one. */
export function withheldReason(w: ReceiveWithheld): string {
  const why = (w.why ?? '').trim()
  if (why === 'superseded') return w.delivered_instead ? 'replaced; the newer version is given instead' : 'replaced by a newer version'
  if (why === 'not established') return 'proposed, not established yet'
  if (why === 'not in this record') return 'not found in this Brain'
  return why || 'left out'
}
