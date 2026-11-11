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

/** The four choices, in the composer's words: PERMISSION MODE, in the
 *  owner's wording (round 3). Same values, same meaning; the never-wait
 *  choice is kept as it was. */
export const CONSENT_MODES: { mode: ConsentMode; words: string }[] = [
  { mode: 'ask', words: 'Ask for permission' },
  { mode: 'task', words: 'Allow routine operations' },
  { mode: 'deny', words: 'Never wait for me (refuses what would be asked)' },
  { mode: 'all', words: 'Allow all operations' },
]

export const CONSENT_TIP = 'Which operations need asking. Routine work inside the task\'s workspaces may proceed; '
  + 'anything outside them is still asked, or refused when it would never wait for you. '
  + 'This is not side work: whether discovered side work may be pursued is Task Gravity, set on its own.'

/** The chip's and a run line's few words; nothing for "ask", the default. */
export const consentShort = (mode?: string | null): string | null =>
  mode === 'task' ? 'routine work proceeds' : mode === 'deny' ? 'never waits' : mode === 'all' ? 'approves all' : null

/** Said wherever Approve All is chosen or in force. */
export const APPROVE_ALL_RISK = 'Approve all: every permission the runtime asks for is granted without asking you, '
  + "including deleting files, network access, Git pushes, installs, and reading or writing a Brain, MARS's data "
  + 'and credentials, for this task and the work it delegates. Each one is recorded. It grants no Mentis authority. '
  + 'Change it at any time during the run.'

/** The button's word for each mode. */
export const consentButton = (mode: string): string =>
  mode === 'ask' ? 'ask' : mode === 'task' ? 'routine proceeds' : mode === 'deny' ? 'never wait' : 'approve all'

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
  all: 'approve all (your choice for this task)',
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

/** THE EXECUTION MODE A RUN HAS (round 3), as `GET /api/runs/<run>/consent`
 *  says it: what applies, whether the owner selected it or it is the
 *  runtime's default, the runtime's mechanism, the isolation MARS reports,
 *  and how Permission is enforced in it. Absent from an older server. */
export interface RunExecution {
  mode: string
  source: 'selected' | 'runtime-default'
  mechanism: string | null
  isolation: 'sandbox' | 'host' | 'none-reported'
  permission_enforcement: string | null
  acknowledged: { act: string; at: number } | null
  applied_by_mars: boolean
}

export interface ConsentRead {
  run: string
  consent: RunConsent | null
  operations: Answered[]
  applied?: RunConsent['applied']
  execution?: RunExecution | null
}

const MODE_WORDS: Record<string, string> = { sandboxed: 'Sandboxed', 'unrestricted-host': 'Unrestricted Host', container: 'Container' }
const ISOLATION_WORDS: Record<string, string> = { sandbox: 'in a sandbox', host: 'directly on this machine', 'none-reported': 'no isolation reported' }

/** The run panel's Execution line: "Execution: Unrestricted Host (selected)
 *  · directly on this machine · agent-full-access", and "not confirmed by
 *  MARS" where MARS did not report applying it. */
export function executionLine(x: RunExecution): string {
  return [
    `Execution: ${MODE_WORDS[x.mode] ?? x.mode} (${x.source === 'selected' ? 'selected' : "runtime's default"})`,
    ISOLATION_WORDS[x.isolation] ?? x.isolation,
    x.mechanism,
    x.applied_by_mars ? null : 'not confirmed by MARS',
  ].filter(Boolean).join(' · ')
}

/** Workspaces as typed: one per line, or comma-separated; blanks dropped. */
export const workspacesOf = (text: string): string[] =>
  text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)

/** Not an absolute directory, as either side of a Windows machine writes one. */
export const notAbsolute = (dirs: string[]): string[] =>
  dirs.filter((d) => !/^(?:[A-Za-z]:[\\/]|[\\/])/.test(d))
