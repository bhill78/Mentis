/* Unit tests for the `#` palette's rows (Stage 1a, hashRows):
 * 1. the Topic rows and "Create topic" come from the Topic lookup alone,
 *    while the full search is still out
 * 2. the full search's posts and files are added below the Topics when it comes
 * 3. Enter waits only for the answer that decides the first row: the Topic
 *    lookup for a word, the full search for a bare number
 * 4. "Create" is not offered for a name a Topic already has, anywhere
 * 5. a bare number never offers "Create" and never asks the Topic lookup
 */
import assert from 'node:assert/strict'
import { hashAsks, hashRows, hashWaits, topicAsks, type Found, type TopicHit } from '../src/fluid/composer/hashRows'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const HERE = [{ id: 'ent-t1', name: 'Planning' }, { id: 'ent-t2', name: 'Release' }]
const ELSEWHERE: TopicHit[] = [{ ref: 'ent-t9', name: 'Plane spotting', conversation: 'ent-c2', conversation_name: 'Hobbies' }]
const FOUND: Found[] = [
  { what: 'turn', ref: 'ent-p1', number: 12, conversation_name: 'Ops', said: 'we **plan** the move' },
  { what: 'participant', ref: 'ent-u1', name: '@Planner' },
  { what: 'topic', ref: 'ent-t9', name: 'Plane spotting', conversation_name: 'Hobbies' },
]
const base = { topics: HERE, conversation: 'ent-c1', canCreate: true, creating: false }
const keys = (rows: { key: string }[]) => rows.map((r) => r.key)

// 1. topic answer in, full search out: Topics and Create, no wait
{
  const rows = hashRows({ ...base, q: 'plan', topicHits: ELSEWHERE, found: null })
  eq(keys(rows), ['ent-t1', 'ent-t9', 'create'], 'Topics here, Topics elsewhere, then Create, before the full search')
  ok(rows[1].note!.includes('Hobbies'), 'a Topic of another conversation says where it is')
  eq(hashWaits('plan', ELSEWHERE, null), false, 'Enter does not wait for the full search once Topics answered')
}
// 1b. both out: only this conversation's Topics, no Create, Enter waits
{
  const rows = hashRows({ ...base, q: 'plan', topicHits: null, found: null })
  eq(keys(rows), ['ent-t1'], 'no Create before the Topic lookup answers')
  eq(hashWaits('plan', null, null), true, 'Enter waits for the Topic lookup')
  eq(hashWaits('plan', null, FOUND), true, 'the full search alone does not decide a word')
}
// 1c. nothing matches: Create alone is takeable at once
{
  const rows = hashRows({ ...base, q: 'zebra', topicHits: [], found: null })
  eq(keys(rows), ['create'], 'Create alone')
  eq(rows[0].label, 'Create topic "Zebra"', 'Create names the Topic')
  eq(hashWaits('zebra', [], null), false, 'Create is takeable without the full search')
}
// 2. full search arrives: posts below Topics, above Create; nothing twice; no people
{
  const rows = hashRows({ ...base, q: 'plan', topicHits: ELSEWHERE, found: FOUND })
  eq(keys(rows), ['ent-t1', 'ent-t9', 'ent-p1', 'create'], 'the post is added below the Topics')
  eq(rows[2].label, '#12 · Ops', 'a Turn reads as its coordinate and room')
  eq(rows[2].note, 'we plan the move', 'markup stripped from the excerpt')
  // a Topic only the full search found (the lookup's page was full) is still offered as a Topic
  const more = hashRows({ ...base, q: 'plan', topicHits: [], found: FOUND })
  eq(more.find((r) => r.key === 'ent-t9')?.pick, { kind: 'topic', id: 'ent-t9', name: 'Plane spotting' }, 'a found Topic files the post')
}
// 4. Create is withheld for an existing name, here or elsewhere, any case
{
  eq(keys(hashRows({ ...base, q: 'planning', topicHits: [], found: null })), ['ent-t1'], 'existing here')
  eq(keys(hashRows({ ...base, q: 'PLANE SPOTTING', topicHits: ELSEWHERE, found: null })).includes('create'), false, 'existing elsewhere')
  eq(keys(hashRows({ ...base, canCreate: false, q: 'zebra', topicHits: [], found: null })), [], 'not offered when creating is not possible')
}
// 5. a bare number: a coordinate
{
  eq(topicAsks('12'), false, 'a number never asks the Topic lookup')
  eq(hashAsks('12'), true, 'a number asks the full search')
  eq(hashWaits('12', [], null), true, 'Enter waits for the full search on a number')
  eq(hashWaits('12', [], FOUND), false, 'and not once it has come')
  eq(keys(hashRows({ ...base, q: '12', topicHits: [], found: [] })).includes('create'), false, 'never Create for a number')
}
// one character: nothing asked, nothing waited for
{
  eq(hashAsks('p'), false, 'one letter asks nothing')
  eq(hashWaits('p', [], []), false, 'and waits for nothing')
}

console.log(`fluid_hash_rows_unit: ${checks} checks passed`)
