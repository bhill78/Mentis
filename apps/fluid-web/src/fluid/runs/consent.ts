/* EXECUTION CONSENT, SAID THE SAME WAY EVERYWHERE (docs/run-consent.md).
 *
 * Which OPERATIONS of authorized work need the owner's asking: the composer's
 * choice, the addressee's chip, a run's line and its panel all word it here,
 * so the consent asked with and the consent shown cannot drift apart.
 *
 * NOT TASK GRAVITY. `follow_up` says whether side work may be pursued;
 * consent says which operations of this work need asking. Neither implies
 * the other, and each is said on its own. */

import type { ConsentMode } from '../../composer/draft'
import type { RunConsent } from '../../composer/execution'

/** The three choices, in the composer's words. */
export const CONSENT_MODES: { mode: ConsentMode; words: string }[] = [
  { mode: 'ask', words: 'Each operation is asked' },
  { mode: 'task', words: 'Routine work in the task proceeds' },
  { mode: 'deny', words: 'Never wait for me (refuses what would be asked)' },
]

export const CONSENT_TIP = 'Which operations need asking. Routine work inside the task\'s workspaces may proceed; '
  + 'anything outside them is still asked, or refused when it would never wait for you. '
  + 'This is not side work: whether discovered side work may be pursued is Task Gravity, set on its own.'

/** The chip's and a run line's few words; nothing for "ask", the default. */
export const consentShort = (mode?: string | null): string | null =>
  mode === 'task' ? 'routine work proceeds' : mode === 'deny' ? 'never waits' : null

/** The run panel's line: the server's label, how many workspaces, the tools
 *  allowed for this run. Anything unreadable is "ask", as the server reads it. */
export function consentLine(c: RunConsent): string {
  const label = c.label || CONSENT_MODES.find((m) => m.mode === c.mode)?.words || CONSENT_MODES[0].words
  const n = c.workspaces?.length ?? 0
  return [label, c.mode !== 'ask' && n ? `${n} workspace${n === 1 ? '' : 's'}` : null].filter(Boolean).join(' · ')
}

/** Who answered an operation, in words. */
export const BY_WORDS: Record<string, string> = {
  grant: 'the run\'s grant',
  task: 'the task\'s consent',
  tool: 'a tool allowed for this run',
  owner: 'you',
  deny: 'refused: never waits',
  research: 'web research your request asked for',
  unanswered: 'nobody answered',
}

/** One operation answered, as `GET /api/runs/<run>/consent` lists it. */
export interface Answered {
  at: number
  operation: { summary?: string; category?: string; tool?: string; within?: boolean; command?: string }
  answer: 'allowed' | 'refused'
  by: string
}

export interface ConsentRead {
  run: string
  consent: RunConsent | null
  operations: Answered[]
  applied?: RunConsent['applied']
}

/** Workspaces as typed: one per line, or comma-separated; blanks dropped. */
export const workspacesOf = (text: string): string[] =>
  text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)

/** Not an absolute directory, as either side of a Windows machine writes one. */
export const notAbsolute = (dirs: string[]): string[] =>
  dirs.filter((d) => !/^(?:[A-Za-z]:[\\/]|[\\/])/.test(d))
