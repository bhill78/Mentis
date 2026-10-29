import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { establishInstructionBody, instructionGroups, instructionsPath, type ConversationInstructionRow } from '../src/fluid/conversation/instructionsModel'

const here = 'ent-conversation'
const row = (entry: string, local = true): ConversationInstructionRow => ({
  entry, kind: 'conversation-instruction', text: entry, written_by: '@owner',
  placed: local ? ['conversation'] : ['whole-brain'],
})

const current = row('current')
current.proposed = { successors: { items: [{ entry: 'edit', summary: 'pending edit', by_alias: '@owner' }] } }
const groups = instructionGroups({
  conversation: here,
  governing: [current, row('brain-wide', false)],
  candidates: [row('proposal')],
  ended: [row('ended')],
  replaced: [row('replaced')],
})
assert.deepEqual(groups.current.map((x) => x.entry), ['current'], 'only standing instructions scoped here are current')
assert.deepEqual(groups.pending.map((x) => x.entry), ['proposal', 'edit'], 'direct proposals and proposed edits are visibly not current')
assert.deepEqual(groups.history.map((x) => x.entry), ['ended', 'replaced'], 'ended and replaced instructions remain visible as history')

assert.equal(instructionsPath(here), '/api/conversations/ent-conversation/governs')
assert.deepEqual(establishInstructionBody('  Keep answers short.  ', 'ent-owner'), {
  text: 'Keep answers short.', attributed_to: 'ent-owner', establish: true,
}, 'the conversation write explicitly establishes the instruction immediately')

const root = fileURLToPath(new URL('../src/', import.meta.url))
const topBar = readFileSync(root + 'fluid/frame/TopBar.tsx', 'utf8')
const surface = readFileSync(root + 'fluid/conversation/Instructions.tsx', 'utf8')
assert.match(topBar, /view === 'conversation'.*conversation-instructions/s, 'the Instructions door is in the conversation header')
assert.match(surface, /\/api\/conversations\/\$\{encodeURIComponent\(conversation\)\}\/instructions/, 'the surface writes through the conversation instruction endpoint')
assert.match(surface, /separate from rules that govern the whole Brain/, 'the surface states the conversation/Brain scope boundary')

console.log('fluid_instructions_unit: ok')
