/* THE OWNER'S HALF-WRITTEN ADOPTION DECISION, KEPT FOR EXACTLY ONE REQUEST.
 *
 * Edited wording here can be ESTABLISHED ("Adopt with this wording"), so a
 * kept draft must never come back onto anything but what it was written
 * against. It is bound to
 *   the Brain answering NOW (needs/brainScope.ts: asked afresh, never the
 *     identity the page read when it loaded),
 *   the record,
 *   the adoption request (its id: a record asked about again is another request),
 *   and a signature of what that request proposes (its wording and body).
 * A draft for another request of the same record is removed when this one is
 * read. It is kept in the tab's session storage (experimental/draftKeep.ts),
 * so a reload does not lose it; `stored` says whether it really was, and
 * where it was not the page still asks before leaving (BrainDecision.tsx).
 *
 * Apart from React (`tests/draft_keep_unit.ts`). */
import { drop, keep, kept, keyOf as storageKey, signature, type Storageish } from '../../experimental/draftKeep'

export interface AdoptionDraft { editOpen: boolean; editedText: string | null; because: string; scope: string; falsifier: string }
/** `brain` is the Brain that answered NOW (needs/brainScope.ts), or null where
 *  that is not known; `mount` is this showing of the decision. With no Brain
 *  known the draft lives in this showing alone: nothing kept is restored. */
export interface AdoptionKey { brain: string | null; mount: string; entry: string; request: string; sig: string }
interface Req { request: string; kind?: string; wording: { proposed: string; proposed_body?: Record<string, unknown> } }

const NONE: AdoptionDraft = { editOpen: false, editedText: null, because: '', scope: '', falsifier: '' }
const WHAT = 'adopt'

export function createAdoptionDrafts(st?: Storageish | null) {
  const mem = new Map<string, AdoptionDraft>()
  const wrote = new Map<string, boolean>()
  const told = new Set<() => void>()
  const tell = () => told.forEach((f) => f())
  const memKey = (k: AdoptionKey) => `${k.brain ?? '?' + k.mount}|${k.entry}|${k.request}|${k.sig}`
  const id = (k: AdoptionKey) => `${k.entry}|${k.request}`
  /** drafts kept in this Brain for the same record under ANOTHER request */
  const dropOthers = (k: AdoptionKey) => {
    const s = (st !== undefined ? st : (() => { try { return typeof sessionStorage === 'undefined' ? null : sessionStorage } catch { return null } })()) as (Storageish & { length?: number; key?: (i: number) => string | null }) | null
    if (!k.brain || !s || typeof s.key !== 'function' || typeof s.length !== 'number') return
    const head = storageKey(k.brain, WHAT, `${k.entry}|`)
    const mine = storageKey(k.brain, WHAT, id(k))
    try {
      const gone: string[] = []
      for (let i = 0; i < s.length; i++) { const x = s.key(i); if (x && x.startsWith(head) && x !== mine) gone.push(x) }
      for (const x of gone) s.removeItem(x)
    } catch { /* nothing to remove */ }
  }
  return {
    NONE,
    keyOf: (brain: string | null, entry: string, req: Req, mount = ''): AdoptionKey => ({
      brain, mount, entry, request: req.request,
      sig: signature([req.request, req.kind ?? null, req.wording.proposed, req.wording.proposed_body ?? null]),
    }),
    subscribe: (f: () => void) => { told.add(f); return () => { told.delete(f) } },
    read(k: AdoptionKey): AdoptionDraft {
      const m = memKey(k)
      if (!mem.has(m)) {
        dropOthers(k)
        const got = kept<Partial<AdoptionDraft>>(k.brain, WHAT, id(k), k.sig, st)
        mem.set(m, got ? { ...NONE, ...got } : NONE)
        wrote.set(m, true)
      }
      return mem.get(m)!
    },
    /** whether what is held for this request is really in the tab's storage */
    stored: (k: AdoptionKey): boolean => wrote.get(memKey(k)) ?? true,
    write(k: AdoptionKey, patch: Partial<AdoptionDraft>) {
      const m = memKey(k)
      const next = { ...(mem.get(m) ?? NONE), ...patch }
      mem.set(m, next)
      wrote.set(m, keep(k.brain, WHAT, id(k), k.sig, next, st))
      tell()
    },
    forget(k: AdoptionKey) {
      mem.delete(memKey(k)); wrote.delete(memKey(k))
      drop(k.brain, WHAT, id(k), st)
      tell()
    },
  }
}

export const adoptionDraft = createAdoptionDrafts()
