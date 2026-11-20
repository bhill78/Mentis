/* THE OWNER'S HALF-WRITTEN ADOPTION DECISION, KEPT FOR EXACTLY ONE REQUEST.
 *
 * Edited wording here can be ESTABLISHED ("Adopt with this wording"), so a
 * kept draft must never come back onto anything but what it was written
 * against. It is held by
 *   the record,
 *   the adoption request (its id: a record asked about again is another request),
 *   and a signature of what that request proposes (its Kind, wording and body).
 * A request for the same record asked again, or proposing other words, starts
 * empty, and the draft written for the earlier one is dropped.
 *
 * IN MEMORY, FOR THE PAGE, AND NOWHERE ELSE: it survives leaving the record to
 * read what supports it and coming back, in the same tab. It is never written
 * to the browser's storage; a reload starts the decision empty.
 *
 * Apart from React (`tests/draft_keep_unit.ts`). */
import { signature } from '../../experimental/draftKeep'

export interface AdoptionDraft { editOpen: boolean; editedText: string | null; because: string; scope: string; falsifier: string }
export interface AdoptionKey { entry: string; request: string; sig: string }
interface Req { request: string; kind?: string; wording: { proposed: string; proposed_body?: Record<string, unknown> } }

const NONE: AdoptionDraft = { editOpen: false, editedText: null, because: '', scope: '', falsifier: '' }

export function createAdoptionDrafts() {
  /** by record: the one draft held for it, and what it was written against */
  const mem = new Map<string, { request: string; sig: string; draft: AdoptionDraft }>()
  const told = new Set<() => void>()
  const tell = () => told.forEach((f) => f())
  const mine = (k: AdoptionKey) => { const m = mem.get(k.entry); return m && m.request === k.request && m.sig === k.sig ? m : null }
  return {
    NONE,
    keyOf: (entry: string, req: Req): AdoptionKey => ({
      entry, request: req.request,
      sig: signature([req.request, req.kind ?? null, req.wording.proposed, req.wording.proposed_body ?? null]),
    }),
    subscribe: (f: () => void) => { told.add(f); return () => { told.delete(f) } },
    /** the draft written against exactly this request and wording, else empty.
     *  One written against another request or wording of the record is dropped. */
    read(k: AdoptionKey): AdoptionDraft {
      const m = mem.get(k.entry)
      if (m && !mine(k)) mem.delete(k.entry)
      return mine(k)?.draft ?? NONE
    },
    write(k: AdoptionKey, patch: Partial<AdoptionDraft>) {
      mem.set(k.entry, { request: k.request, sig: k.sig, draft: { ...(mine(k)?.draft ?? NONE), ...patch } })
      tell()
    },
    forget(k: AdoptionKey) { if (mine(k)) { mem.delete(k.entry); tell() } },
    /** something is written in a decision not yet made: a reason, a falsifier or edited wording
     *  (a scope chosen alone is not writing anything) */
    /** what is written in every decision not yet made, as one comparable string */
    written(): string {
      return JSON.stringify([...mem.entries()].map(([entry, m]) => [entry, m.request, m.draft.because, m.draft.falsifier, m.draft.editedText]))
    },
    anyWritten(): boolean {
      for (const { draft: d } of mem.values()) if (d.because.trim() || d.falsifier.trim() || d.editedText !== null) return true
      return false
    },
  }
}

export const adoptionDraft = createAdoptionDrafts()
