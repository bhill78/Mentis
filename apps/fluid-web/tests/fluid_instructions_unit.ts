import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { establishInstructionBody, instructionGroups, instructionsPath, type ConversationInstructionRow } from '../src/fluid/conversation/instructionsModel'

const here = 'ent-conversation'
const row = (entry: string, state: ConversationInstructionRow['state'], group: ConversationInstructionRow['group'], conversation = here): ConversationInstructionRow => ({
  entry, kind: 'instruction', state, group, summary: entry, author_alias: '@owner',
  placed_at: state === 'stands' || state === 'ended' ? [{ conversation }] : [],
  proposed_by: state === 'candidate' ? [{ conversation }] : [],
})

const groups = instructionGroups({ groups: {
  standing: [row('current', 'stands', 'standing'), row('elsewhere', 'stands', 'standing', 'ent-other')],
  proposed: [row('proposal', 'candidate', 'proposed')],
  recorded: [row('recorded', 'candidate', 'recorded')],
  history: [row('ended', 'ended', 'history')],
}}, here)
assert.deepEqual(groups.current.map((x) => x.entry), ['current'], 'only standing instructions scoped here are current')
assert.deepEqual(groups.pending.map((x) => x.entry), ['proposal', 'recorded'], 'proposed and recorded candidates are visibly not current')
assert.deepEqual(groups.history.map((x) => x.entry), ['ended'], 'ended instructions remain visible as history')

assert.equal(instructionsPath, '/api/governed?kind=instruction&limit=500')
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
