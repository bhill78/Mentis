/* MANAGE BRAIN'S SMALL DECISIONS, kept apart from the components that draw
 * them so each is checkable without a browser (`tests/brain_unit.ts`): what a
 * compact row says, what the list's foot says, what can be made, when the
 * owner's decision may be sent, and what Back is called. Pure: no React, no
 * reads. */
import type { Id } from '../../api'
import { returnedItemOf, type HeldBytes, type ViewerItem } from '../../quiet/media/view'
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
  /** AN ENTRY THAT IS NOT A RECORD TO MANAGE: a topic, a participant, a piece
   *  of the record's substrate, acquired material. Read read-only by the
   *  existing entry inspector rather than dressed as governance (3D Brain
   *  integration, addendum §4). */
  | { page: 'entry'; entry: Id }

/** Where the reader came into the Brain from, so Back names it. */
export type BrainOrigin =
  | { from: 'browser'; label: string }
  | { from: 'post'; post: Id; label: string }
  | { from: 'link' }
  /** from the 3D Brain, which is parked while this is read and comes back
   *  exactly as it was (addendum §3) */
  | { from: 'space' }

export interface BrainMainState { stack: BrainMainView[]; origin: BrainOrigin }

/** What Back says: the record before this one while there is one, else where
 *  the reader came in from. Pure, so the words are checkable. */
export function backWords(state: BrainMainState): string {
  if (state.stack.length > 1) {
    const prev = state.stack[state.stack.length - 2]
    return prev.page === 'record' ? 'Back to the record before' : prev.page === 'import' ? 'Back to Import' : prev.page === 'entry' ? 'Back to what was read before' : 'Back'
  }
  if (state.origin.from === 'browser') return `Brain · ${state.origin.label}`
  if (state.origin.from === 'post') return state.origin.label
  if (state.origin.from === 'space') return BACK_TO_SPACE
  return 'Back to the conversation'
}

/** THE WAY BACK TO THE GRAPH, in the one wording every return uses: the
 *  reader's in-page control, the record page's Back, and the notice when a
 *  view has gone (3D Brain integration, addendum §3). */
export const BACK_TO_SPACE = 'Back to 3D Brain'


/** WHERE A HELD ADMISSION'S BYTES ARE (`mentis/web` `/api/artifacts/<ref>`),
 *  the address the inspector's own thumbnail already uses. */
export const heldBytesUrl = (entry: Id) => `/api/artifacts/${encodeURIComponent(entry)}`

/** THE BYTES BEHIND A HELD ADMISSION, AS THE EXISTING VIEWER READS THEM
 *  (addendum §4, the Admission row; independent review R4).
 *
 *  THE DEFECT THIS ANSWERS: the entry page gave the inspector no way to open
 *  held bytes, so a held text file could be inspected -- its name, its type,
 *  its size -- and never read. `HeldThing` is a description, not a reader.
 *
 *  Nothing new draws them: this is the same `ViewerItem` Quiet Chat's own
 *  viewer takes for a returned artifact, classified by the same rules
 *  (`quiet/media/view.ts`), so a text file opens in the reader a text file
 *  already opens in and a PDF in the PDF one.
 *
 *  Null where there is nothing to open: no answer yet, or bytes Mentis no
 *  longer holds. Those keep the inspector's existing states, and no opener is
 *  offered for an address there is nothing behind. Pure. */
export function heldItem(entry: Id, about: Omit<HeldBytes, 'ref' | 'url'> | null | undefined): ViewerItem | null {
  if (!about) return null
  return returnedItemOf({ ...about, ref: entry, url: heldBytesUrl(entry) })
}

/** The next page joined to the rows already shown: each record once, in the
 *  order read (a record that moved between two reads is not shown twice). */
export function appendPage<T extends { id: string }>(shown: T[], next: T[]): T[] {
  const have = new Set(shown.map((r) => r.id))
  return [...shown, ...next.filter((r) => !have.has(r.id))]
}
