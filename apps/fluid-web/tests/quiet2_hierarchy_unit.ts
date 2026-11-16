/* EXECUTION HIERARCHY IN QUIET CHAT'S WORKING VIEW, checked without a server
 * or a browser: a native worker's calls nest under it and nothing else does;
 * a call a stopped run left open is never said as pending; a worker's line
 * says only what the runtime reported; usage names the context reading apart
 * from consumption; a Mentis delegation follows the open run it came from.
 * The shapes are the ones measured through MARS (claude-agent-acp 0.97.0). */
import assert from 'node:assert/strict'
import type { FeedEntry } from '../src/fluid/runs/feed'
import { callState, feedTree, nativeWorkerLimit, orderWork, recordedEntries, reportsNativeWorkers, tokens, usageLines, workerLine } from '../src/quiet2/activity/hierarchy'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const tool = (id: string, seq: number, more: Partial<FeedEntry> = {}): FeedEntry => ({ id: 'tool-' + id, seq, kind: 'tool', at: seq, started_at: seq, title: id, ...more })

/* -- the feed as a tree ----------------------------------------------------- */
const feed: FeedEntry[] = [
  tool('c1', 3, { parent: 'tool-a1', status: 'completed' }),
  tool('c2', 4, { parent: 'tool-a2', status: 'in_progress' }),
  tool('own', 5, { status: 'completed' }),
  { id: 'permission-1', seq: 6, kind: 'permission', at: 6, title: 'echo hi', parent: 'tool-a2', outcome: 'selected' },
  /* the workers changed last, so they come last by seq: their calls still nest */
  tool('a1', 7, { started_at: 1, status: 'completed', worker: { model: 'claude-sonnet-5', duration_ms: 32869, tool_calls: 1, context_tokens: 29229 } }),
  tool('a2', 8, { started_at: 2, status: 'in_progress', worker: { requested_model: 'haiku', elapsed_s: 30 } }),
]
const tree = feedTree(feed)
eq(tree.map((n) => n.entry.id), ['tool-own', 'tool-a1', 'tool-a2'], 'only entries that name no parent are at the top')
eq(tree[1].children.map((n) => n.entry.id), ['tool-c1'], "a worker's call is under it")
eq(tree[2].children.map((n) => n.entry.id), ['tool-c2', 'permission-1'], 'and so is the permission it asked for, oldest first')
ok(tree.every((n) => !n.orphan), 'nothing is an orphan while its parent is held')

const lost = feedTree([tool('c9', 1, { parent: 'tool-gone' })])
eq([lost.length, lost[0].orphan], [1, true], 'a call whose worker the feed dropped stays listed, said as that')
const flat = feedTree([tool('x', 1), tool('y', 2)])
eq(flat.map((n) => n.children.length), [0, 0], 'a runtime that names no parents gives a flat list')
const loop = feedTree([tool('p', 1, { parent: 'tool-q' }), tool('q', 2, { parent: 'tool-p' })])
eq(loop.length + loop.reduce((n, t) => n + t.children.length, 0), 2, 'a cycle loses nobody and nests nobody twice')
const nested = feedTree([tool('a', 1, { worker: {} }), tool('b', 2, { worker: {}, parent: 'tool-a' }), tool('c', 3, { parent: 'tool-b' })])
eq(nested[0].children[0].children[0].entry.id, 'tool-c', 'a worker started by a worker nests one deeper')

/* -- a call's state ---------------------------------------------------------- */
const live = { ended: false, cancelled: false }
eq(callState('in_progress', live), 'running', 'in progress is running')
eq(callState(undefined, live), 'pending', 'no status yet is pending while the run works')
eq(callState('pending', { ended: true, cancelled: true }), 'cancelled with its run', 'a stopped run never leaves a call pending')
eq(callState('in_progress', { ended: true, cancelled: false }), 'no end reported', 'an ended run says the runtime reported no end')
eq(callState('completed', { ended: true, cancelled: true }), 'completed', 'what completed before the stop stays completed')
eq(callState('failed', live), 'failed', 'failed is failed')
eq(callState('pending', live, true), 'no end reported', 'the record saying it was open at the end is enough')

/* -- a worker's line ---------------------------------------------------------- */
eq(workerLine('alpha count', { model: 'claude-sonnet-5', duration_ms: 32869, tool_calls: 1, context_tokens: 29229 }, 'completed'),
  'Native sub-agent · alpha count · claude-sonnet-5 · completed · took 33 s · 1 tool call · context reached 29.2k', 'an ended worker, as reported')
eq(workerLine('beta sum', { requested_model: 'haiku', elapsed_s: 30 }, 'running', 2),
  'Native sub-agent · beta sum · haiku asked for · running · 30 s so far · 2 tool calls seen', 'a running one says what was asked, never a resolved model')
eq(workerLine(null, {}, 'pending'), 'Native sub-agent · pending', 'nothing reported: nothing claimed')
ok(!workerLine('x', { context_tokens: 100 }, 'completed').includes('used'), 'its context size is never called usage')

/* -- usage --------------------------------------------------------------------- */
eq(tokens(999), '999', 'small counts whole')
eq(tokens(40266), '40.3k', 'thousands')
eq(tokens(1000000), '1M', 'millions')
const used = usageLines([
  { id: 'usage', seq: 1, kind: 'usage', at: 1, usage: { used: 38728, size: 1000000, cost_amount: 0.119, cost_currency: 'USD' } },
  { id: 'turn-usage', seq: 2, kind: 'turn_usage', at: 2, turn: { tokens: { total: 76707 }, tokens_cover: 'main-loop',
    by_model: [{ model: 'claude-haiku-5-5', tokens: { total: 66798 } }, { model: 'claude-sonnet-5', tokens: { total: 130182 } }], cost: { amount: 0.119, currency: 'USD' } } },
])
eq(used, [
  'Context window: 38.7k of 1M full (its size now, not what was spent)',
  'Tokens this turn, as the runtime reported: 76.7k in its main conversation (native sub-agents not counted)',
  'By model, native sub-agents included: claude-haiku-5-5 66.8k · claude-sonnet-5 130k',
  "Cost, the runtime's own figure: $0.12",
], 'each figure named for what it is')
eq(usageLines([{ id: 'usage', seq: 1, kind: 'usage', at: 1, usage: { used: 1200, size: 8000 } }]),
  ['Context window: 1.2k of 8k full (its size now, not what was spent)'], 'a runtime that reports only context shows only context')
eq(usageLines([]), [], 'nothing reported, nothing shown')

/* -- an ended run, from its record ---------------------------------------------- */
const rec = recordedEntries({ ended_at: 9, stop_reason: 'cancelled', context_used: 5,
  tool_calls: [{ id: 'a1', title: 'beta sum', status: 'pending', worker: {}, open_at_end: true }, { id: 'c1', title: 'sleep 9', status: 'pending', parent: 'a1', open_at_end: true }] })
const recTree = feedTree(rec)
eq(recTree.filter((n) => n.entry.kind === 'tool').map((n) => [n.entry.id, n.children.map((c) => c.entry.id)]), [['tool-a1', ['tool-c1']]], 'the recorded calls nest as the live ones did')
eq(callState(rec[0].status, { ended: true, cancelled: true }, rec[0].open_at_end), 'cancelled with its run', 'and a cancelled worker is said as cancelled')
eq(rec.filter((e) => e.kind === 'turn_usage').length, 0, 'no turn usage is drawn where none was recorded')

/* -- Mentis delegations under the run they came from ------------------------------ */
const row = (key: string, from?: string | null) => ({ key, run: { run: key, delegated_from: from === undefined ? null : { run: from, by_name: 'Caretaker' } } })
eq(orderWork([row('review', 'care'), row('other'), row('care'), row('verify', 'care')]).map((o) => [o.e.key, o.depth]),
  [['other', 0], ['care', 0], ['review', 1], ['verify', 1]], 'delegated runs follow their open origin, one level in')
eq(orderWork([row('review', null)]).map((o) => o.depth), [0], 'a delegation whose origin is not open stays at the top')
eq(orderWork([row('a', 'b'), row('b', 'a')]).length, 2, 'a cycle in the record leaves nobody out')
eq(orderWork([{ key: 'p-1', run: null }, row('care')]).map((o) => o.e.key), ['p-1', 'care'], 'a live execution with no run keeps its place')

/* -- which runtimes report native workers ------------------------------------------ */
ok(reportsNativeWorkers('claude'), 'Claude Code does')
ok(!reportsNativeWorkers('codex') && !reportsNativeWorkers('antigravity') && !reportsNativeWorkers(null), 'the others are not assumed to')
eq(nativeWorkerLimit('claude'), null, 'Claude needs no limit said')
ok(nativeWorkerLimit('codex')!.includes('started and completed'), 'Codex says what it reports')
ok(nativeWorkerLimit('antigravity')!.includes('parent conversation only'), 'Antigravity says its usage is the parent only')
ok(nativeWorkerLimit('kimi-k3')!.includes('not exposed'), 'an unmeasured runtime claims nothing')
for (const state of ['running', 'pending', 'no end reported', 'cancelled with its run']) {
  eq(workerLine('Task A Worker', { event: 'launched' }, state), 'Native sub-agent · Task A Worker · launched · its progress and end are not reported by this runtime', `a launch-only worker is never said as ${state}`)
}
eq(workerLine('Start subagent alpha', { event: 'started' }, 'running'), 'Native sub-agent · Start subagent alpha · running', 'a worker whose end will be reported is running until then')
eq(workerLine('Start subagent alpha', { event: 'started', duration_ms: 27800 }, 'completed'), 'Native sub-agent · Start subagent alpha · completed · took 28 s', 'a reported completion is a completion')

console.log(`quiet2_hierarchy_unit: ${checks} checks passed`)
