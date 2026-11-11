/* Execution Mode in the composer (round 3): the dispatch spec carries
 * `execution_mode` only when chosen, and Unrestricted Host only with the
 * notice it was accepted under; Permission and Execution never change each
 * other; a runtime that cannot run the chosen mode clears it with a reason;
 * the chip says both modes in a few words; the run panel's line; and a 401
 * OwnerAuthRequired sends the app to the owner login page. */
import assert from 'node:assert/strict'
import { bodyOf, emptyDraft, type Addressee } from '../src/composer/draft'
import type { ExecutionInfo, ExecutionModes } from '../src/composer/execution'
import { tokenOf } from '../src/fluid/composer/words'
import { acceptUnrestricted, ackIsCurrent, availability, chooseExecution, effectiveExecution, enforcementNote, fitExecution, modesWords } from '../src/fluid/composer/execmode'
import { executionLine } from '../src/fluid/runs/consent'
import { fluidFetch, ownerLoginTarget } from '../src/fluid/http'

const NOTICE = { id: 'unrestricted-host/v1', text: 'The agent may technically access files outside its workspace, local credentials, network services and local processes.' }
const CODEX_HOST = 'Codex does not ask in this mode: Permission Mode is recorded but not enforced by the runtime'
const codexModes: ExecutionModes = {
  default: 'sandboxed',
  modes: {
    sandboxed: { state: 'supported', mechanism: 'workspace-write', permission_enforcement: 'Codex asks before acting outside the sandbox', why: null },
    'unrestricted-host': { state: 'supported', mechanism: 'agent-full-access', permission_enforcement: CODEX_HOST, why: null },
    container: { state: 'unsupported', mechanism: null, permission_enforcement: '', why: 'not available yet' },
  },
}
const localModes: ExecutionModes = {
  default: 'sandboxed',
  modes: {
    sandboxed: { state: 'supported', mechanism: null, permission_enforcement: 'Mentis answers each request', why: null },
    'unrestricted-host': { state: 'unverified', mechanism: null, permission_enforcement: '', why: 'no host mode verified for this runtime' },
  },
}
const rt = (kind: string, execution_modes?: ExecutionModes) =>
  ({ kind, present: true, version: null, capabilities: [], notes: [], models: [], ...(execution_modes ? { execution_modes } : {}) })
const info: ExecutionInfo = { workspace: 'C:/w', runtimes: [rt('codex', codexModes), rt('local', localModes), rt('claude')], unrestricted_host_notice: NOTICE }
const older: ExecutionInfo = { workspace: 'C:/w', runtimes: [rt('codex'), rt('claude')] }

const who: Addressee = { participant: 'p1', alias: '@Orbit', dispatch: true, runtime: 'codex' }
const spec = (a: Addressee) => bodyOf({ ...emptyDraft(), text: 'go', to: [a] }, 'p-me', []).dispatch[0] as Record<string, unknown>

// --- draft -> body --------------------------------------------------------
// nothing chosen: no field (the runtime's default)
assert.equal('execution_mode' in spec(who), false)
assert.equal('execution_mode_ack' in spec(who), false)
// sandboxed chosen explicitly (not the default somewhere): the mode, no ack
assert.deepEqual([spec({ ...who, executionMode: 'sandboxed' }).execution_mode, 'execution_mode_ack' in spec({ ...who, executionMode: 'sandboxed' })], ['sandboxed', false])
// unrestricted with its accepted notice: both
const host = acceptUnrestricted(who, NOTICE.id)
assert.equal(spec(host).execution_mode, 'unrestricted-host')
assert.equal(spec(host).execution_mode_ack, NOTICE.id)
// unrestricted WITHOUT an ack is never sent
assert.equal('execution_mode' in spec({ ...who, executionMode: 'unrestricted-host' }), false)
// an ack never travels on another mode
assert.equal('execution_mode_ack' in spec({ ...who, executionMode: 'sandboxed', executionAck: NOTICE.id }), false)
// record-only dispatches nothing at all
assert.deepEqual(bodyOf({ ...emptyDraft(), text: 'x', action: 'record-only', to: [host] }, 'p-me', []).dispatch, [])
// Permission and Execution are independent: each keeps the other
const both = { ...host, consent: { mode: 'task' as const, workspaces: ['C:/w'] } }
assert.deepEqual(spec(both).consent, { mode: 'task', workspaces: ['C:/w'] })
assert.equal(spec(both).execution_mode, 'unrestricted-host')
assert.deepEqual(chooseExecution(both, 'sandboxed', codexModes).consent, both.consent)
assert.deepEqual(acceptUnrestricted({ ...who, consent: { mode: 'all', workspaces: [] } }, NOTICE.id).consent, { mode: 'all', workspaces: [] })

// --- choosing ------------------------------------------------------------
// choosing the runtime's default sends nothing, and drops a stale ack
assert.deepEqual(chooseExecution(host, 'sandboxed', codexModes), who)
assert.equal(availability(codexModes, 'container').ok, false)
assert.equal(availability(codexModes, 'container').why, 'not available yet')
assert.deepEqual(availability(localModes, 'unrestricted-host'), { ok: false, why: 'no host mode verified for this runtime' })
assert.equal(ackIsCurrent(host, info), true)
assert.equal(ackIsCurrent({ ...host, executionAck: 'unrestricted-host/v0' }, info), false)

// --- switching runtime: an unsupported mode is cleared, visibly ------------
const kept = fitExecution(host, 'codex', info)
assert.deepEqual([kept.who, kept.cleared], [host, null])
const toLocal = fitExecution({ ...host, runtime: 'local' }, 'local', info)
assert.equal(toLocal.who.executionMode, undefined)
assert.equal(toLocal.who.executionAck, undefined)
assert.equal('execution_mode' in spec(toLocal.who), false)
assert.match(toLocal.cleared!, /^Unrestricted Host cleared: on local, no host mode verified for this runtime\. Now Sandboxed, its default\.$/)
// a runtime whose modes are unknown (older server, or Mentis picks) clears too
const toClaude = fitExecution({ ...host, runtime: 'claude' }, 'claude', info)
assert.equal(toClaude.who.executionMode, undefined)
assert.match(toClaude.cleared!, /its Execution Modes are not known/)
assert.match(fitExecution({ ...host, runtime: undefined }, null, info).cleared!, /a runtime Mentis picks/)
// nothing chosen: nothing to clear
assert.deepEqual(fitExecution({ ...who, runtime: 'local' }, 'local', info).cleared, null)

// --- round 4: four states, each said as itself ----------------------------
// a runtime that cannot take work now: what it supports is temporarily unavailable, with why
const downModes: ExecutionModes = {
  default: 'sandboxed',
  modes: {
    sandboxed: { state: 'temporarily-unavailable', mechanism: 'workspace-write', permission_enforcement: 'x', why: 'not signed in' },
    'unrestricted-host': { state: 'temporarily-unavailable', mechanism: 'agent-full-access', permission_enforcement: CODEX_HOST, why: 'not signed in' },
    container: { state: 'unsupported', mechanism: null, permission_enforcement: '', why: 'not available yet' },
  },
}
assert.deepEqual(availability(downModes, 'unrestricted-host'), { ok: false, why: 'temporarily unavailable: not signed in' })
assert.deepEqual(availability({ ...downModes, modes: { ...downModes.modes, sandboxed: { ...downModes.modes.sandboxed!, why: null } } }, 'sandboxed'),
  { ok: false, why: 'temporarily unavailable' })
// Claude's Sandboxed stays unverified, said as unverified, never as temporarily unavailable
const claudeModes: ExecutionModes = {
  default: 'unrestricted-host',
  modes: {
    sandboxed: { state: 'unverified', mechanism: null, permission_enforcement: 'forwarded', why: null },
    'unrestricted-host': { state: 'supported', mechanism: 'host', permission_enforcement: 'forwarded', why: null },
  },
}
assert.deepEqual(availability(claudeModes, 'sandboxed'), { ok: false, why: 'not verified on this runtime' })
// a temporarily unavailable mode already chosen is cleared visibly and never sent
const downInfo: ExecutionInfo = { ...info, runtimes: [rt('codex', downModes)] }
const down = fitExecution(host, 'codex', downInfo)
assert.equal(down.who.executionMode, undefined)
assert.equal('execution_mode' in spec(down.who), false)
assert.match(down.cleared!, /^Unrestricted Host cleared: on codex, temporarily unavailable: not signed in\. Now Sandboxed, its default\.$/)

// --- the chip -------------------------------------------------------------
assert.equal(modesWords(who, 'codex', info), 'ask · sandboxed')
assert.equal(modesWords({ ...host, consent: { mode: 'task', workspaces: [] } }, 'codex', info), 'routine · host')
// an older server: Permission only, no Execution word
assert.equal(modesWords(who, 'codex', older), 'ask')
// unaccepted unrestricted is said as the default, as it would be sent
assert.equal(modesWords({ ...who, executionMode: 'unrestricted-host' }, 'codex', info), 'ask · sandboxed')
assert.equal(tokenOf({ ...host, consent: { mode: 'task', workspaces: [] } }, [], undefined, undefined, info), 'codex · asks before side work · routine · host')
assert.equal(tokenOf({ ...who, runtime: undefined }, [{ participant: 'p1', default_runtime: 'codex' }], undefined, undefined, info),
  'codex · default · asks before side work · ask · sandboxed')
assert.equal(tokenOf({ ...who, dispatch: false }, [], undefined, undefined, info), 'addressed only')
// the enforcement note: only where it matters (outside the sandbox), in the server's words
assert.equal(enforcementNote(host, 'codex', info), CODEX_HOST)
assert.equal(enforcementNote(who, 'codex', info), null)
assert.deepEqual(effectiveExecution(who, 'codex', info)?.source, 'runtime-default')
assert.deepEqual(effectiveExecution(host, 'codex', info)?.source, 'selected')

// --- the run panel's line --------------------------------------------------
assert.equal(executionLine({ mode: 'unrestricted-host', source: 'selected', mechanism: 'agent-full-access', isolation: 'host',
  permission_enforcement: CODEX_HOST, acknowledged: { act: 'a1', at: 1 }, applied_by_mars: true }),
  'Execution: Unrestricted Host (selected) · directly on this machine · agent-full-access')
assert.equal(executionLine({ mode: 'sandboxed', source: 'runtime-default', mechanism: null, isolation: 'none-reported',
  permission_enforcement: null, acknowledged: null, applied_by_mars: false }),
  "Execution: Sandboxed (runtime's default) · no isolation reported · not confirmed by MARS")

// --- owner authentication -------------------------------------------------
const at = { pathname: '/fluid/c/abc', search: '?x=1', hash: '#t2' }
const need = { error: 'owner authentication required', kind: 'OwnerAuthRequired', login: '/owner/login' }
assert.equal(ownerLoginTarget(401, need, at), '/owner/login?next=' + encodeURIComponent('/fluid/c/abc?x=1#t2'))
assert.equal(ownerLoginTarget(401, { error: 'x' }, at), null)
assert.equal(ownerLoginTarget(403, need, at), null)
assert.equal(ownerLoginTarget(401, need, { pathname: '/owner/login', search: '', hash: '' }), null)
// through the central fetch: a 401 OwnerAuthRequired navigates once, the caller still gets the 401
{
  const went: string[] = []
  const g = globalThis as unknown as { window?: unknown; fetch: typeof fetch }
  const realFetch = g.fetch
  g.window = { location: { ...at, assign: (u: string) => { went.push(u) } } }
  // any other 401 navigates nowhere
  g.fetch = (async () => new Response(JSON.stringify({ error: 'nope' }), { status: 401 })) as typeof fetch
  await fluidFetch('/api/x')
  assert.equal(went.length, 0)
  g.fetch = (async () => new Response(JSON.stringify(need), { status: 401, headers: { 'Content-Type': 'application/json' } })) as typeof fetch
  const res = await fluidFetch('/api/owner-only', { method: 'POST', body: '{}' })
  assert.equal(res.status, 401)
  assert.equal((await res.json()).kind, 'OwnerAuthRequired')
  await fluidFetch('/api/owner-only')
  assert.deepEqual(went, ['/owner/login?next=' + encodeURIComponent('/fluid/c/abc?x=1#t2')])
  g.fetch = realFetch
  delete g.window
}

console.log('fluid execution mode: ok')
