/* GOVERNANCE IN FLUID: what an item page is, and where an item opens.
 *
 * An item opened from Governance is a page beside This post (`nav.openItemPage`),
 * addressed `gov:<entry>` so the workspace knows to draw the item there rather
 * than an object. It opens beside the conversation it was PROPOSED FROM: the
 * Turn the record's `material-proposed` act names (the register row's
 * `proposed_by`), else the entry's own provenance. Where the record names no
 * Turn but the item is placed in exactly one conversation, it opens beside that
 * one, and says so. Where it names neither, nothing is invented: the item opens
 * on Governance's own Stage. */

import { read, type Id } from '../../api'
import type { Row } from '../../surfaces/Register'

export const GOV_OBJECT = 'gov:'
export const isGovObject = (o: string) => o.startsWith(GOV_OBJECT)
export const govObject = (entry: Id) => GOV_OBJECT + entry
export const govEntry = (o: string) => o.slice(GOV_OBJECT.length)

/** Where an item opens beside. `turn` null: the conversation it is placed in,
 *  with no Turn named, read at the reader's own place there. */
export interface Source {
  conversation: Id
  conversationName: string | null
  turn: Id | null
  /** how the record relates it: proposed in that Turn, or only placed there */
  why: 'proposed' | 'placed'
}

export interface OpenHint {
  title: string
  source: Source | null
}

const clip = (s: string, n: number) => {
  const t = (s || '').replace(/\s+/g, ' ').trim()
  return t.length <= n ? t : t.slice(0, n - 1).trimEnd() + '…'
}
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

/** "Rule · Verify at the end, within scope" -- the tab's words. */
export const itemTitle = (kind: string | null | undefined, text: string) =>
  `${cap(kind || 'Entry')} · ${clip(text.split(/(?<=[.!?])\s/)[0] || text, 48)}`

/** From a register row, which already carries everything needed. */
export function hintOfRow(r: Row): OpenHint {
  const p = r.proposed_by.find((x) => x.conversation && x.turn)
  const placed = r.placed_at.filter((x) => !x.whole_brain)
  return {
    title: itemTitle(r.kind, r.summary),
    source: p
      ? { conversation: p.conversation!, conversationName: p.conversation_name, turn: p.turn, why: 'proposed' }
      : placed.length === 1
        ? { conversation: placed[0].conversation, conversationName: placed[0].name, turn: null, why: 'placed' }
        : null,
  }
}

interface EntryRead {
  id: Id
  missing?: boolean
  kind: string | null
  fields: string[]
  body: Record<string, unknown>
  provenance?: { produced_by?: { conversation?: Id | null; turn?: Id | null; act_type?: string }[] }
  governance_actions?: { placements?: { where: Id; name: string | null; whole_brain: boolean; persona?: boolean }[] }
  originating?: { conversation?: Id | null; conversation_name?: string | null; turn?: Id | null } | null
  recorded_by?: { conversation?: Id | null; conversation_name?: string | null; turn?: Id | null } | null
}

/** For an item reached any other way (a link in a record, a new version):
 *  read once, from the same entry read the record panel uses. */
export async function readHint(entry: Id): Promise<OpenHint> {
  const d = await read<EntryRead>('/api/entries/' + encodeURIComponent(entry))
  if (d.missing) throw new Error(`this Brain does not hold ${entry}`)
  const text = d.fields.map((f) => d.body[f]).find((v) => typeof v === 'string' && v.trim()) as string | undefined
  const made = d.provenance?.produced_by?.find((p) => p.conversation && p.turn)
  const orig = d.originating?.conversation
    ? d.originating
    : d.recorded_by?.conversation
      ? d.recorded_by
      : null
  const placed = (d.governance_actions?.placements ?? []).filter((p) => !p.whole_brain && !p.persona)
  return {
    title: itemTitle(d.kind, text ?? entry),
    source: made
      ? { conversation: made.conversation!, conversationName: null, turn: made.turn!, why: 'proposed' }
      : orig?.conversation
        ? { conversation: orig.conversation, conversationName: orig.conversation_name ?? null, turn: orig.turn ?? null, why: 'proposed' }
        : placed.length === 1
          ? { conversation: placed[0].where, conversationName: placed[0].name, turn: null, why: 'placed' }
          : null,
  }
}
