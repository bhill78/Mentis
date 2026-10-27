/* EXPERIMENTAL: the reading half of ref (drawn in ../types/ref.tsx). */
import type { TypeSpec } from './api'

export const MENTIS_REF = /^(ent|def)-[0-9a-f]{6,}$/

export interface Decl {
  refs: { token: string; malformed: boolean }[]
  presentation: 'compact' | 'expanded'
  /** A grant for providers that need one (a helper session). Written by Mentis, not by a model. */
  via: string | null
}

export const refSpec: TypeSpec<Decl> = {
  type: 'ref',
  summary: 'Any Mentis material by reference. The record says what it is; this only asks how to present it.',
  attrs: {
    id: { req: 'optional', says: 'one reference (ent-… or def-…); or put one per line in the body' },
    presentation: { req: 'optional', choices: ['compact', 'expanded'], says: 'compact (default) or expanded' },
    title: { req: 'optional', says: 'a heading for several references' },
    via: { req: 'optional', says: 'the helper session that grants campaign references (Mentis writes this)' },
  },
  body: 'optional: one reference per line (a leading "- " is allowed)',
  parse(body, a, c) {
    const tokens = [
      ...(a.id ? [a.id] : []),
      ...body.split('\n').map((l) => l.trim().replace(/^[-*]\s+/, '').split(/\s+/)[0]).filter(Boolean),
    ]
    if (!tokens.length) c.err('id', 'Name at least one reference: id=ent-… , or one per line in the body.')
    const refs = tokens.map((t) => {
      const scheme = /^[a-z][a-z0-9+.-]*:/i.test(t)
      const malformed = !MENTIS_REF.test(t) && !scheme
      if (malformed) c.warn(t, `“${t}” is not a reference this renderer can read (Mentis references look like ent-3f2a… or def-3f2a…). It is shown as such.`,
        /^adm-/.test(t)
          ? `ref takes only ent-/def- ids. For an image, write ![caption](${t}) on a line of its own (blank lines around it) instead of this block; name any other artifact in the text.`
          : `Replace “${t}” with an existing ent-… or def-… id found with the tools, or remove it.`)
      return { token: t, malformed }
    })
    return { refs, presentation: (a.presentation as Decl['presentation']) ?? 'compact', via: a.via ?? null }
  },
}
