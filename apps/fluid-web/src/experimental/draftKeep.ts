/* A HALF-MADE ANSWER, KEPT FOR THE TAB -- AND ONLY FOR WHAT IT WAS MADE FOR.
 *
 * Looking at what a decision names can leave the page, so a draft may be kept
 * in the tab's session storage. A kept draft is dangerous exactly where it
 * could come back onto something else: another Brain behind the same address
 * (a restored or copied Brain reuses ids), a question whose words or options
 * are not the ones it was made against, a request that was answered elsewhere
 * or asked again. So every kept draft is bound to
 *
 *   the Brain it was made in (`scopeOf`: the Brain's id and where it is),
 *   the exact thing it answers (an ask's id; a record and its adoption request),
 *   and a signature of what was on screen (`signature`): the question and
 *     every option in order, or the proposed wording.
 *
 * It is handed back only when all three still match, and a chosen option only
 * while the option at that place still has the label it was chosen under.
 * Anything else is thrown away, never applied. With no Brain identity nothing
 * is stored at all.
 *
 * OPT-IN. Only a host that asks keeps drafts this way (Quiet Chat's Needs
 * you: `DraftKeepContext`). Every other drawing of the decision form --
 * legacy Fluid's -- behaves exactly as before: a draft in memory, for the
 * page. Nothing here sends anything, and what an answer records is untouched.
 *
 * Pure but for the storage handed in (`tests/draft_keep_unit.ts`). */
import { createContext } from 'react'

/** The Brain a draft is kept for; null while it is not known (nothing is stored). */
export const DraftKeepContext = createContext<string | null>(null)

export interface Storageish {
  getItem(k: string): string | null
  setItem(k: string, v: string): void
  removeItem(k: string): void
}

export const PREFIX = 'mentis.draft.v2|'

/** Which Brain this is, for keeping: its id and where it is. Null where the
 *  server did not say: an unknown Brain keeps nothing. */
export function scopeOf(b: { corpus_id?: string | null; corpus_path?: string | null } | null | undefined): string | null {
  const id = (b?.corpus_id ?? '').trim()
  return id ? `${id}@${(b?.corpus_path ?? '').trim()}` : null
}

/** A short, stable signature of what a draft was made against (FNV-1a over
 *  its canonical JSON). Not a secret: only "is this still the same thing". */
export function signature(of: unknown): string {
  const s = JSON.stringify(of ?? null)
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0 }
  return `${s.length.toString(36)}.${h.toString(36)}`
}

export const keyOf = (scope: string, what: string, id: string) => `${PREFIX}${what}|${scope}|${id}`

function storage(given?: Storageish | null): Storageish | null {
  if (given !== undefined) return given
  try { return typeof sessionStorage === 'undefined' ? null : sessionStorage } catch { return null }
}

/** Keep `draft` for exactly this. Says whether it was really stored. */
export function keep(scope: string | null, what: string, id: string, sig: string, draft: unknown, st?: Storageish | null): boolean {
  const s = storage(st)
  if (!scope || !s) return false
  try { s.setItem(keyOf(scope, what, id), JSON.stringify({ sig, draft })); return true } catch { return false }
}

/** The draft kept for exactly this, or null. One kept against anything else
 *  (another signature) is removed, not returned. */
export function kept<T>(scope: string | null, what: string, id: string, sig: string, st?: Storageish | null): T | null {
  const s = storage(st)
  if (!scope || !s) return null
  try {
    const raw = s.getItem(keyOf(scope, what, id))
    if (!raw) return null
    const got = JSON.parse(raw) as { sig?: unknown; draft?: unknown } | null
    if (!got || got.sig !== sig || got.draft == null || typeof got.draft !== 'object') { s.removeItem(keyOf(scope, what, id)); return null }
    return got.draft as T
  } catch { return null }
}

export function drop(scope: string | null, what: string, id: string, st?: Storageish | null): void {
  const s = storage(st)
  if (!scope || !s) return
  try { s.removeItem(keyOf(scope, what, id)) } catch { /* nothing kept */ }
}

/* -- a decision's question -------------------------------------------------- */

interface OptionLike { label: string; consequence?: string; selections?: Record<string, string>; findings?: { ref: string }[] }
export interface AskLike { id: string; expects: string; question?: string | null; options?: OptionLike[] | null; form?: string }
export type PickLike =
  | { kind: 'option'; option: number; findings?: Record<string, string> }
  | { kind: 'own' }
  | { kind: 'withdraw' }

/** What a question's draft was made against: what it expects, its words, and
 *  every option in order with what choosing it does. */
export function askSignature(a: AskLike): string {
  return signature([a.expects, a.form ?? null, a.question ?? null,
    (a.options ?? []).map((o) => [o.label, o.consequence ?? null, o.selections ?? null, (o.findings ?? []).map((f) => f.ref)])])
}

interface KeptAnswer { pick?: PickLike; label?: string | null; text?: string }

/** Keep one question's draft; nothing chosen and nothing typed keeps nothing. */
export function keepAnswer(scope: string | null, a: AskLike, pick: PickLike | undefined, text: string, st?: Storageish | null): boolean {
  if (!pick && !text) { drop(scope, 'ask', a.id, st); return true }
  const label = pick?.kind === 'option' ? a.options?.[pick.option]?.label ?? null : null
  return keep(scope, 'ask', a.id, askSignature(a), { pick, label, text } satisfies KeptAnswer, st)
}

/** The draft kept for this question AS IT NOW READS, or null. A chosen
 *  option comes back only while the option at that place still has the label
 *  it was chosen under; otherwise the whole draft is discarded. */
export function keptAnswer(scope: string | null, a: AskLike, st?: Storageish | null): { pick: PickLike | undefined; text: string } | null {
  const got = kept<KeptAnswer>(scope, 'ask', a.id, askSignature(a), st)
  if (!got) return null
  const pick = got.pick
  if (pick?.kind === 'option') {
    const now = a.options?.[pick.option]
    if (!now || now.label !== got.label) { drop(scope, 'ask', a.id, st); return null }
  }
  return { pick, text: typeof got.text === 'string' ? got.text : '' }
}

export const dropAnswer = (scope: string | null, ask: string, st?: Storageish | null) => drop(scope, 'ask', ask, st)

/** Remove every draft kept in this Brain for `what` whose id is not in
 *  `still`: what is no longer asked keeps no draft. Other Brains' are left. */
export function sweep(scope: string | null, what: string, still: string[], st?: Storageish | null): void {
  const s = storage(st) as (Storageish & { length?: number; key?: (i: number) => string | null }) | null
  if (!scope || !s || typeof s.key !== 'function' || typeof s.length !== 'number') return
  const head = keyOf(scope, what, '')
  try {
    const gone: string[] = []
    for (let i = 0; i < s.length; i++) {
      const k = s.key(i)
      if (k && k.startsWith(head) && !still.includes(k.slice(head.length))) gone.push(k)
    }
    for (const k of gone) s.removeItem(k)
  } catch { /* nothing to remove */ }
}
