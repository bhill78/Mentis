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
console.log('8 assertions passed')
