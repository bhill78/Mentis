/* WHAT THE CREATION FORM DECIDES BEFORE IT WRITES, apart from React, so it is
 * checkable (`tests/brain_repairs_unit.ts`) and so Quiet Chat and Fluid, which
 * host the same form (`R2Forms.tsx`), cannot decide it two ways.
 *
 * THE DEFECTS THESE ANSWER (Quiet UI audit, 2026-11-18):
 *   - a lesson could not be created at all: its Kind declares `requires_basis`
 *     and the create request did not carry the basis, which the form attached
 *     only afterwards, to a record the server had already refused to write;
 *   - a new persona and a new conversation instruction started as "I am
 *     establishing this as owner". Writing something confers nothing: every
 *     Kind that standing applies to starts proposed, and establishing is a
 *     choice the owner makes on the form. */
import type { Id } from '../../api'
import type { KindAuthoring } from './r2Model'

/** Material that standing applies to starts PROPOSED, through whichever door
 *  it is written (the generic one, the Persona's, the instruction's). */
export const startsProposed = (k?: KindAuthoring | null): boolean => k?.authoring?.standing_apt === true

/** Whether recording one of this Kind needs what it was concluded from. Read
 *  from the Kind's own definition, as the server reads it; only the generic
 *  door takes a basis with the write. */
export const requiresBasis = (k?: KindAuthoring | null): boolean =>
  k?.requires_basis === true && k.authoring?.door === 'entry'

/** The references typed into a basis field: split, trimmed, each once. */
export const basisIds = (typed: string): string[] => [...new Set(typed.split(/[\s,]+/).filter(Boolean))]

/** Said in the form, before anything is sent, where a basis is owed. */
export const BASIS_NEEDED = 'Name at least one held reference this was concluded from. A record of this Kind cannot be recorded without one.'

/** Why this draft cannot be sent yet, as far as its basis goes; null where it can. */
export const basisRefusal = (k: KindAuthoring | null | undefined, typed: string): string | null =>
  requiresBasis(k) && !basisIds(typed).length ? BASIS_NEEDED : null

/** WHAT `POST /api/entries` IS SENT. A Kind that requires a basis carries its
 *  references IN the create (`basis`), where the server checks and writes
 *  them with the record; the separate `derive-from` act is then not sent, or
 *  the same basis would be linked twice. A Kind whose basis is optional keeps
 *  the order it always had: create, then `derive-from` with its reason. */
export function entryCreateBody(x: {
  k: KindAuthoring; body: Record<string, unknown>; me: Id; establishes: boolean
  falsifier: string; context: string; sources: string[]
}): Record<string, unknown> {
  return {
    kind: x.k.kind, body: x.body, attributed_to: x.me,
    // Cite the basis before conferring standing: never established in the
    // same act as a create that names sources.
    establish: x.sources.length ? false : x.establishes, falsifier: x.falsifier,
    links: x.context.trim() ? [{ relation: 'in-context', to: x.context.trim() }] : [],
    ...(requiresBasis(x.k) ? { basis: x.sources } : {}),
  }
}

/** Whether the basis still has to be cited by `derive-from` after creating. */
export const citesAfterCreate = (k: KindAuthoring, sources: string[]): boolean =>
  sources.length > 0 && !requiresBasis(k)

/** WHAT IS HELD BY AN ACT THAT HAS JUST BEEN RECORDED: nothing. The hosted
 *  record forms say what they hold from their last render, and a successful
 *  save moves on to the new version BEFORE the next render, so the page's
 *  leave question read the stale "this revision" and asked about work that
 *  was already in the Brain. A host keeps `settled` from the moment the save
 *  answers until the form has drawn again. */
export const heldAfterSave = (unsaved: string | null, settled: boolean): string | null => (settled ? null : unsaved)
