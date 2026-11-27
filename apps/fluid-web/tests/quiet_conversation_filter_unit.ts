import assert from 'node:assert/strict'
import { adapt } from '../src/quiet2/real'
import { showConversationPost } from '../src/quiet2/conversationFilter'
import type { Turn } from '../src/api'
const work = { kind: 'finding' as const, why: 'finding', to: null, to_name: null }
const turn = { id: 'work', author: 'agent', author_alias: '@agent', at: 1, parts: [], topics: [], number: 561, agent_work: work } as unknown as Turn
const post = adapt(turn, 'conversation', () => undefined)
assert.deepEqual(post.agentWork, work)
assert.equal(showConversationPost(post, false), false)
assert.equal(showConversationPost(post, true), true)
assert.equal(showConversationPost(post, false, 'work'), true)
assert.equal(showConversationPost({ ...post, id: 'other' }, false, 'work'), false)
assert.equal(showConversationPost({ ...post, agentWork: null }, false), true)
assert.equal(showConversationPost({ ...post, agentWork: undefined }, false), true)
assert.equal(showConversationPost({ ...post, replyTo: 'root' }, false), false)

/* A MAGNET'S OWN BOOKKEEPING FOLDS THE SAME WAY (owner, 2026-11-27,
   ent-de11a0235181): the server calls it `mechanics` and its author is the
   owner, which the fold no longer keeps visible. */
const mech = { kind: 'mechanics' as const, why: 'Perspective reconciled', to: null, to_name: null }
const bookkeeping = adapt({ id: 'persp', author: 'owner', author_alias: '@brian', at: 2, parts: [],
  topics: [], number: 562, agent_work: mech } as unknown as Turn, 'conversation', () => undefined)
assert.deepEqual(bookkeeping.agentWork, mech)
assert.equal(showConversationPost(bookkeeping, false), false)
assert.equal(showConversationPost(bookkeeping, true), true)
assert.equal(showConversationPost(bookkeeping, false, 'persp'), true)
/* and the substantive answer, which the server leaves unclassified, stays */
const answer = adapt({ id: 'answer', author: 'owner', author_alias: '@brian', at: 3, parts: [],
  topics: [], number: 563, agent_work: null } as unknown as Turn, 'conversation', () => undefined)
assert.equal(showConversationPost(answer, false), true)
console.log('14 assertions passed')
