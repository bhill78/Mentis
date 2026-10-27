/* EXPERIMENTAL: the reading half of helper (drawn in ../types/helper.tsx). */
import type { TypeSpec } from './api'

export const helperSpec: TypeSpec<{ scope: 'player' | 'dm' }> = {
  type: 'helper',
  summary: 'A short conversation with a local-model Dungeon Helper; Mentis resolves, renders and pins what it picks.',
  attrs: {
    scope: { req: 'required', choices: ['player', 'dm'], says: 'what material this helper may use: player (revealed only) or dm (everything)' },
    title: { req: 'optional', says: 'a heading' },
  },
  body: 'nothing',
  parse(_b, a) {
    return { scope: a.scope as 'player' | 'dm' }
  },
}
