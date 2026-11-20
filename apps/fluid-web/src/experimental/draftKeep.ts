/* A HALF-MADE ANSWER IS ONLY EVER FOR THE QUESTION IT WAS MADE AGAINST.
 *
 * A decision's draft (what is chosen and typed, not yet sent) lives IN MEMORY,
 * for the page: it survives the form being drawn again -- a panel closing,
 * a reference opened and come back from -- and nothing else. It is never
 * written to the browser's storage, so a reload starts every form empty, and
 * nothing about it depends on which Brain is answering.
 *
 * A host that shows the same question again later (Quiet Chat's Needs you:
 * `DraftKeepContext`) asks for two cheap protections on top:
 *
 *   - the draft is remembered together with a signature of what it was made
 *     against -- what is expected, the question's words, and every option in
 *     order with what choosing it does -- and with the LABEL of the option
 *     chosen. If the question now reads otherwise, or the option at that
 *     place no longer has that label, the draft is discarded, never applied;
 *   - a draft whose question is closed (answered or withdrawn, here or
 *     anywhere) is dropped.
 *
 * Every other drawing of the decision form -- legacy Fluid's -- behaves
 * exactly as before. Nothing here sends anything, and what an answer records
 * is untouched. Pure (`tests/draft_keep_unit.ts`). */
import { createContext } from 'react'

/** Whether the host asks for the protections above (Quiet's Needs you does). */
export const DraftKeepContext = createContext(false)

/** A short, stable signature of what a draft was made against (FNV-1a over
 *  its canonical JSON). Not a secret: only "is this still the same thing". */
export function signature(of: unknown): string {
  const s = JSON.stringify(of ?? null)
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0 }
  return `${s.length.toString(36)}.${h.toString(36)}`
}

interface OptionLike { label: string; consequence?: string; selections?: Record<string, string>; findings?: { ref: string }[] }
export interface AskLike { id: string; expects: string; question?: string | null; options?: OptionLike[] | null; form?: string }
export type PickLike =
  | { kind: 'option'; option: number; findings?: Record<string, string> }
  | { kind: 'own' }
  | { kind: 'withdraw' }

/** What a question's draft is made against: what it expects, its words, and
 *  every option in order with what choosing it does. */
export function askSignature(a: AskLike): string {
  return signature([a.expects, a.form ?? null, a.question ?? null,
    (a.options ?? []).map((o) => [o.label, o.consequence ?? null, o.selections ?? null, (o.findings ?? []).map((f) => f.ref)])])
}

/** What a draft was made against: the question's signature, and the label of
 *  the option chosen (null for own words, a withdrawal, or nothing chosen). */
export interface Made { sig: string; label: string | null }

export function madeAgainst(a: AskLike, pick: PickLike | undefined): Made {
  return { sig: askSignature(a), label: pick?.kind === 'option' ? a.options?.[pick.option]?.label ?? null : null }
}

/** Whether a draft made against `made` is still for this question as it now
 *  reads: the same signature, and the chosen option still at its place under
 *  the label it was chosen by. Anything else: discard it. */
export function stillFor(made: Made | undefined, a: AskLike, pick: PickLike | undefined): boolean {
  if (!made || made.sig !== askSignature(a)) return false
  if (pick?.kind !== 'option') return true
  const now = a.options?.[pick.option]
  return !!now && now.label === made.label
}

/* -- where the drafts are held -------------------------------------------------
   In memory, by the form's key: `<form>|picks` and `<form>|texts`, each by
   ask id (experimental/types/decision.tsx `useDraft` reads and writes them).
   Here, apart from the form, so that a host can drop the drafts of questions
   that are no longer asked without the form being on screen. */
export const drafts = new Map<string, Record<string, unknown>>()
/** where a host asks: what each question's draft was made against, by `<form>|<ask>` */
export const madeFor = new Map<string, Made>()
export const draftsTold = new Set<() => void>()

/** Something is typed, and not sent, in any answer held here (a choice alone is not typed). */
export function anyTyped(): boolean {
  for (const [key, held] of drafts) {
    if (key.endsWith('|texts') && Object.values(held).some((t) => typeof t === 'string' && !!t.trim())) return true
  }
  return false
}

/** Every question something is typed for and not sent: its id and the words. */
export function typedAll(): { ask: string; text: string }[] {
  const out: { ask: string; text: string }[] = []
  for (const [key, held] of drafts) {
    if (!key.endsWith('|texts')) continue
    for (const [ask, t] of Object.entries(held)) if (typeof t === 'string' && t.trim()) out.push({ ask, text: t })
  }
  return out
}

/** WHAT WAS TYPED FOR ONE QUESTION AND NOT SENT, in any form that holds it: so a page that can
 *  no longer send it (the server now serves another Brain) still shows the owner their words. */
export function typedFor(ask: string): string[] {
  const out: string[] = []
  for (const [key, held] of drafts) {
    if (!key.endsWith('|texts')) continue
    const t = held[ask]
    if (typeof t === 'string' && t.trim()) out.push(t)
  }
  return out
}

/** DROP THE DRAFT OF EVERY QUESTION THAT IS NO LONGER ASKED (`asked`: the ids
 *  asked now). Only drafts a keeping host remembered (`madeFor`) are touched:
 *  a question answered or withdrawn anywhere leaves the list, and its
 *  half-made answer goes with it rather than waiting for a form to notice. */
export function dropNotAsked(asked: string[]): void {
  let any = false
  for (const k of [...madeFor.keys()]) {
    const cut = k.lastIndexOf('|')
    const form = k.slice(0, cut), ask = k.slice(cut + 1)
    if (asked.includes(ask)) continue
    madeFor.delete(k)
    for (const part of ['|picks', '|texts']) {
      const held = drafts.get(form + part)
      if (!held || !(ask in held)) continue
      const rest = Object.fromEntries(Object.entries(held).filter(([id]) => id !== ask))
      if (Object.keys(rest).length) drafts.set(form + part, rest); else drafts.delete(form + part)
    }
    any = true
  }
  if (any) draftsTold.forEach((f) => f())
}
