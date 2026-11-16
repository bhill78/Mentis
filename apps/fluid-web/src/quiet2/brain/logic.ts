/* MANAGE BRAIN'S SMALL DECISIONS, kept apart from the components that draw
 * them so each is checkable without a browser (`tests/brain_unit.ts`): what a
 * compact row says, what the list's foot says, what can be made, when the
 * owner's decision may be sent, and what Back is called. Pure: no React, no
 * reads. */
import type { Id } from '../../api'
import type { LadderAdoptionRequest } from '../../fluid/governance/ladderTypes'
import type { KindAuthoring } from '../../surfaces/governance/r2Model'
import { compactWords, statusWord, type BrainFilter, type BrainRecordSummary } from './data'

/** The Ladder word and the short plain words a compact row shows beside the
 *  Kind (DESIGN-r2.md, "The record, at rest"), from the record's own status. */
export function compactStanding(r: Pick<BrainRecordSummary, 'status' | 'kind'>): { status: string; words: string; off: boolean } {
  return { status: statusWord(r.status), ...compactWords(r.status, r.kind) }
}

export const kindWords = (k: string) => (k ? k.charAt(0).toUpperCase() + k.slice(1).replace(/[-_]/g, ' ') : 'Record')

/** "50 of 213 records · newest first", or the whole count where it is all
 *  shown: a short page is never mistaken for a short record. */
export function footWords(shown: number, total: number, view: BrainFilter): string {
  const of = shown < total ? `${shown} of ${total}` : String(total)
  return `${of} ${total === 1 ? 'record' : 'records'}${view === 'needs-you' ? '' : ' · newest first'}`
}

/** What a section of the old page is called when one is made here. */
export function creationChoices(kinds: KindAuthoring[]): { kind: string; label: string }[] {
  const out: { kind: string; label: string }[] = []
  const seen = new Set<string>()
  for (const k of kinds) {
    const section = k.authoring?.section
    if (!section || seen.has(section)) continue
    seen.add(section)
    const first = kinds.find((x) => x.authoring?.section === section && x.authoring?.door !== 'entry') ?? k
    const label = section === 'instructions' ? 'Instruction for a conversation'
      : section === 'personas' ? 'Persona'
        : section === 'rules' ? 'Rule, decision or lesson'
          : section === 'disciplines' ? 'Discipline'
            : section === 'workflows' ? 'Workflow'
              : (k.authoring?.section_label ?? kindWords(first.kind))
    out.push({ kind: first.kind, label })
  }
  return out
}

/** Why Decline is not offered yet, or null: a decline is recorded with its
 *  reason, always. Pure, so the rule is checkable without a browser. */
export function declineRefusal(because: string): string | null {
  return because.trim() ? null : 'Say why first: a decline is recorded with its reason.'
}

/** Why Adopt is not offered yet, or null. */
export function adoptRefusal(req: Pick<LadderAdoptionRequest, 'expects_falsifier' | 'kind'>, falsifier: string): string | null {
  return req.expects_falsifier && !falsifier.trim() ? `A ${req.kind} is adopted with a falsifier: say what would show it wrong.` : null
}

export type BrainMainView =
  | { page: 'record'; entry: Id }
  | { page: 'new'; kind: string; basis?: Id }
  | { page: 'import' }

/** Where the reader came into the Brain from, so Back names it. */
export type BrainOrigin =
  | { from: 'browser'; label: string }
  | { from: 'post'; post: Id; label: string }
  | { from: 'link' }

export interface BrainMainState { stack: BrainMainView[]; origin: BrainOrigin }

/** What Back says: the record before this one while there is one, else where
 *  the reader came in from. Pure, so the words are checkable. */
export function backWords(state: BrainMainState): string {
  if (state.stack.length > 1) {
    const prev = state.stack[state.stack.length - 2]
    return prev.page === 'record' ? 'Back to the record before' : prev.page === 'import' ? 'Back to Import' : 'Back'
  }
  if (state.origin.from === 'browser') return `Brain · ${state.origin.label}`
  if (state.origin.from === 'post') return state.origin.label
  return 'Back to the conversation'
}

