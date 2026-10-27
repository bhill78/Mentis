import type { Row } from '../Register'
import type { GovFilters } from '../../address'

/** How one field is asked for, as the Kind's `form` declares it. */
export interface FieldForm {
  label?: string
  help?: string
  input?: 'text' | 'line' | 'capabilities' | 'refs' | 'list' | 'participant' | 'persona' | 'activities'
  rows?: number
}

const INPUTS = new Set(['text', 'line', 'capabilities', 'refs', 'list', 'participant', 'persona', 'activities'])

/** ONE ROW OF AN `activities` INPUT, as the entry body stores it. Who carries
 *  it, the Disciplines its delegated work is given, when it is done, and
 *  whether carrying it out takes the coordinate grant. No order beyond the
 *  list's, and nothing that says what comes next. */
export interface ActivityRow {
  key: string
  what: string
  who?: { persona?: string; participant?: string; role?: string }
  disciplines?: string[]
  done_when?: string
  coordinates?: boolean
}

/** A row group's value read from the form's text (JSON), never trusted. */
export function activityRows(raw: string): ActivityRow[] {
  try {
    const v = JSON.parse(raw || '[]')
    return Array.isArray(v) ? v.filter((r) => r && typeof r === 'object') : []
  } catch {
    return []
  }
}

/** A row as stored: empty parts are left out rather than written as blanks. */
export function storedRow(r: ActivityRow): ActivityRow {
  const who = Object.fromEntries(Object.entries(r.who ?? {}).filter(([, v]) => typeof v === 'string' && v.trim()))
  return {
    key: (r.key ?? '').trim(),
    what: r.what ?? '',
    ...(Object.keys(who).length ? { who } : {}),
    ...(r.disciplines?.length ? { disciplines: r.disciplines } : {}),
    ...(r.done_when?.trim() ? { done_when: r.done_when } : {}),
    ...(r.coordinates ? { coordinates: true } : {}),
  }
}

/** A Kind's `form` declaration, read as far as it can be: a description, so
 *  it is never trusted to be well formed. A non-object form is no form (the
 *  fallback applies); a field spec that is not an object is ignored; a label
 *  or help that is not a string is dropped, an unknown input asks for a
 *  paragraph, and rows outside 1-40 take the default. Never throws. */
export function formOf(raw: unknown): Record<string, FieldForm> | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const out: Record<string, FieldForm> = {}
  for (const [field, spec] of Object.entries(raw as Record<string, unknown>)) {
    if (!spec || typeof spec !== 'object' || Array.isArray(spec)) continue
    const s = spec as Record<string, unknown>
    out[field] = {
      ...(typeof s.label === 'string' && s.label.trim() ? { label: s.label } : {}),
      ...(typeof s.help === 'string' && s.help.trim() ? { help: s.help } : {}),
      ...(typeof s.input === 'string' && INPUTS.has(s.input) ? { input: s.input as FieldForm['input'] } : {}),
      ...(typeof s.rows === 'number' && Number.isInteger(s.rows) && s.rows >= 1 && s.rows <= 40 ? { rows: s.rows } : {}),
    }
  }
  return out
}

/** The inputs whose value is a LIST in the entry body; every other input is a string. */
export const LIST_INPUTS = new Set(['capabilities', 'refs', 'list'])

export interface KindAuthoring {
  kind: string
  fields: string[]
  meaning: string
  standing_apt: boolean | null
  expects_falsifier: boolean | null
  /** the Kind's own declaration of how each field is asked for; null where it declares none */
  form?: unknown
  /** what the server makes of the Kind's `authoring` declaration, or of the
   *  fallback for the Kinds this surface has always known (`declared` false) */
  authoring: null | {
    section: string
    section_label?: string
    door: 'instruction' | 'persona' | 'entry'
    placeable: boolean
    persona_placeable?: boolean
    basis?: boolean
    declared?: boolean
    placement_directs_work: boolean
    standing_apt: boolean | null
    expects_falsifier: boolean | null
  }
}

/** THE TABS: Start, then every section some Kind is authored under. The
 *  three this surface has always had keep their order and words; a section
 *  only a declaration names follows them, in its declared words. Derived, so
 *  a Kind added later brings its tab with it. */
export const KNOWN_TABS: [string, string][] = [['instructions', 'Instructions'], ['personas', 'Personas'], ['rules', 'Rules & decisions']]
/** Importing an archive is the surface's own act, not a section of material:
 *  its tab comes after every declared section, never among them. */
export const IMPORT_TAB: [string, string] = ['import', 'Import Archive']
export function tabsOf(kinds: KindAuthoring[]): [string, string][] {
  const declared = new Map<string, string>()
  for (const k of kinds) {
    const a = k.authoring
    if (a && !declared.has(a.section)) declared.set(a.section, a.section_label || a.section)
  }
  // the three are always there, as they always were, whatever loads
  const known = KNOWN_TABS
  const added = [...declared.entries()].filter(([s]) => !KNOWN_TABS.some(([k]) => k === s))
    .sort((a, b) => a[1].localeCompare(b[1]))
  return [['start', 'Start'], ...known, ...added]
}

/** One field's value as the entry body stores it. */
export function fieldValue(raw: string, input?: FieldForm['input']): string | string[] | ActivityRow[] {
  if (input === 'activities') return activityRows(raw).map(storedRow)
  if (!input || !LIST_INPUTS.has(input)) return raw
  const parts = input === 'refs' ? raw.split(/[\s,]+/) : raw.split(/\r?\n/)
  return parts.map(x => x.trim()).filter(Boolean)
}

/** And back, for a form showing a stored value. */
export function fieldText(value: unknown, input?: FieldForm['input']): string {
  if (input === 'activities') return JSON.stringify(Array.isArray(value) ? value : [])
  return Array.isArray(value) ? value.map(String).join('\n') : String(value ?? '')
}

/** Does this placement apply in that Conversation? A whole-Brain placement
 *  applies in every one, so it counts as here wherever "here" is. */
export function placedHere(p: { conversation: string; whole_brain?: boolean }, conversation: string): boolean {
  return p.conversation === conversation || Boolean(p.whole_brain)
}

export function inConversation(r: Row, conversation: string) {
  return r.placed_at.some(p => placedHere(p, conversation)) ||
    r.proposed_by.some(p => p.conversation === conversation) ||
    (r.state === 'candidate' && Boolean(r.proposed_reach?.includes(conversation)))
}

/** Standing material with a challenge still OPEN against it -- not set aside,
 *  not withdrawn, as `ladder.challenges_of` resolves it -- and not already
 *  covered by an ask: what "Waiting on you" shows and counts. A challenge that
 *  was answered or taken back waits on nobody, though it stays in
 *  `disputed_by` and in the item's history. */
export function waitingChallenges<R extends Pick<Row, 'entry' | 'state' | 'open_disputes'>>(
  rows: R[], covered: (entry: string) => boolean = () => false): R[] {
  return rows.filter(r => r.state === 'stands' && (r.open_disputes?.length ?? 0) > 0 && !covered(r.entry))
}

export function filterRows(rows: Row[], kinds: KindAuthoring[], section: string,
  filters: GovFilters, conversation: string | null, conversationFilter = '') {
  const eligible = new Set(kinds.filter(k => k.authoring?.section === section).map(k => k.kind))
  return rows.filter(r => eligible.has(r.kind) &&
    (!conversation || inConversation(r, conversation)) &&
    (!conversationFilter || inConversation(r, conversationFilter)) &&
    (!filters.kind || filters.kind === r.kind) &&
    (!filters.q || filters.q.toLowerCase().split(/\s+/).filter(Boolean).every(token =>
      [r.summary, r.secondary, r.entry, r.author_alias ?? '',
        ...r.placed_at.map(p => p.name ?? '')].join(' ').toLowerCase().includes(token))) &&
    (!filters.state || filters.state === 'any' ||
      (filters.state === 'standing' && r.state === 'stands') ||
      (filters.state === 'proposed' && r.state === 'candidate') ||
      (filters.state === 'history' && (r.state === 'ended' || r.state === 'replaced')) ||
      (filters.state === 'disputed' && r.disputed_by.length > 0)) &&
    (!filters.applies || (filters.applies === 'placed' ? r.placed_at.length > 0 : r.placed_at.length === 0)))
}
