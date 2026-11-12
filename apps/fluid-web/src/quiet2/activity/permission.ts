/* A RUN'S PERMISSION MODE IN QUIET CHAT (item 5.7): the choices, what each means (said on
 * hover and keyboard focus, never as standing prose), and how a change reaches THIS run --
 * applied, pending (and when), unsupported or unknown -- in the server's words
 * (`GET`/`POST /api/runs/<run>/consent` `effect`, `mentis/web/permissions.change_effect`).
 *
 * The state is the server's, never the button just pressed: Quiet Chat says what the server
 * says reached the run, and nothing when it says nothing. */

import { APPROVE_ALL_RISK, CONSENT_MODES } from '../../fluid/runs/consent'

/** The four modes, in the owner's wording. The never-wait choice keeps its words; what it
 *  refuses is said in its help, not in its label. */
export const PERMISSION_OPTIONS: { mode: string; words: string; help: string }[] = CONSENT_MODES.map((m) => ({
  mode: m.mode,
  words: m.mode === 'deny' ? 'Never wait for me' : m.words,
  help: m.mode === 'ask' ? 'Each operation the run\'s grant does not cover is asked of you.'
    : m.mode === 'task' ? 'Routine work inside the task\'s approved workspaces proceeds without asking; anything else is still asked.'
    : m.mode === 'deny' ? 'Routine work inside the task\'s workspaces proceeds; anything that would be asked is refused at once, never waiting for you.'
    : APPROVE_ALL_RISK,
}))

/** What a change does, said as help on the group (hover and focus). */
export const CHANGE_HELP = 'Applies to this run\'s operations from now on, and to work this task delegates; nothing already '
  + 'answered changes. A request waiting for you is decided again under the new mode. How it reaches this run is said beside it.'

/** Why Execution is not a choice here, said as its help. */
export const EXECUTION_HELP = 'Execution Mode is separate from Permission Mode: it is fixed when the run starts and cannot be '
  + 'changed while it works.'

/** `effect` as the server answers it. */
export interface ChangeEffect {
  state: 'applied' | 'pending' | 'unsupported' | 'unknown'
  at: 'next-request' | 'next-run' | 'session-open' | 'restart' | null
  words: string
  answered_now?: { form?: string | null; answer?: string | null; by?: string | null; summary?: string | null }[]
}

/** The compact badge beside the control: a glyph that is not colour alone, a few words, and
 *  the server's full words for its help. */
export function effectBadge(e: ChangeEffect | null | undefined): { state: string; glyph: string; short: string; words: string } | null {
  if (!e || !e.state) return null
  const when = e.at === 'next-request' ? 'next request'
    : e.at === 'next-run' ? 'from its next run'
    : e.at === 'session-open' ? 'when its session opens'
    : e.at === 'restart' ? 'restarting fresh'
    : null
  const answered = (e.answered_now ?? []).filter((a) => a && a.answer)
  const now = answered.length
    ? ` · waiting request ${answered.every((a) => a.answer === 'allowed') ? 'allowed' : answered.every((a) => a.answer === 'refused') ? 'refused' : 'answered'}`
    : ''
  switch (e.state) {
    case 'applied': return { state: 'applied', glyph: '●', short: `Applied${when ? ` · ${when}` : ''}${now}`, words: e.words }
    case 'pending': return { state: 'pending', glyph: '◷', short: `Pending${when ? ` · ${when}` : ''}${now}`, words: e.words }
    case 'unsupported': return { state: 'unsupported', glyph: '⊘', short: 'Not enforced by this runtime', words: e.words }
    default: return { state: 'unknown', glyph: '?', short: 'Not known here', words: e.words }
  }
}
