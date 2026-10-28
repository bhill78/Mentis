/* Object references and drag-to-link (W4; fluid-arrange DROP.md): the part
 * the composer and the drop targets build, the words every place says, and
 * what a draft sends. */
import assert from 'node:assert/strict'
import {
  agentLine, captionOf, confirmWords, isObjectPart, linkReplyBody, liveOf, objectRefPart, provenance, referencePostBody,
  refusalOf, turnRefPart, type LinkTarget, type Words,
} from '../src/fluid/render/objectRef'
import { bodyOf, chosenBody, emptyDraft, isEmpty, refParts, withRef, type Draft } from '../src/composer/draft'
import { said, textOf } from '../src/fluid/conversation/text'
import { sourceOf } from '../src/fluid/conversation/annotated'
import { picturesOf } from '../src/fluid/conversation/Carries'
import type { Post, PostObjectEntry } from '../src/fluid/store'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const flat = (w: Words) => w.map((x) => (typeof x === 'string' ? x : x.b)).join('')

/* -- the part ---------------------------------------------------------------- */

const chart: PostObjectEntry = {
  key: 'ent-d4:p0:chart:xp', part: 0, kind: 'block', type: 'chart', title: 'Adjusted XP', name: 'xp',
  identity: 'declared', stable: true, declared: true, parent: null, page: null, line: 1, end: 5,
  address: { exact: 'exact:ent-d4v2:0:ent-d4:p0:chart:xp', live: 'live:ent-d4:ent-d4:p0:chart:xp' },
  post: 'ent-d4', version: 'ent-d4v2',
}
const d4 = { home: 'conv-dnd', home_name: 'Dungeons and Dragons', number: 4, author_name: '@claude' }
const part = objectRefPart(chart, d4)
eq(part, {
  type: 'object', ref: 'ent-d4', key: 'ent-d4:p0:chart:xp', exact: 'exact:ent-d4v2:0:ent-d4:p0:chart:xp', text: 'Adjusted XP',
  about: { kind: 'chart', title: 'Adjusted XP', home: 'conv-dnd', home_name: 'Dungeons and Dragons', number: 4, by: '@claude' },
}, 'the part is the contract shape: the post, the key, the exact version seen, and a caption')
eq(liveOf(part), 'live:ent-d4:ent-d4:p0:chart:xp', 'its identity is the live address of its post and key')
ok(isObjectPart(part) && !isObjectPart({ type: 'turn', ref: 'x' }), 'an object part is told from other references')
const long = objectRefPart({ ...chart, title: 'x'.repeat(500) }, d4)
ok(long.text.length <= 300 && (long.about.title ?? '').length <= 200, 'what it says stays inside the server bounds')
eq(objectRefPart(chart, null).about.home_name, null, 'a post not read yet leaves where it lives unsaid, never guessed')
eq(turnRefPart({ id: 'ent-d4', number: 4, home_name: 'Dungeons and Dragons' }, 'conv-s8', 'conv-dnd'),
  { type: 'turn', ref: 'ent-d4', text: 'Dungeons and Dragons #4' }, 'a whole post from elsewhere is named with its home')

/* -- the words ----------------------------------------------------------------- */

eq(provenance(part), '▥ Adjusted XP · from Dungeons and Dragons #4 · claude', 'the provenance header')
eq(provenance(part, false), '▥ Chart · Adjusted XP — from Dungeons and Dragons #4 · claude · no longer available',
  'an unavailable reference still reads, from its caption, and says so')

const reply5: LinkTarget = { kind: 'post', post: { id: 'ent-s5', number: 5, home: 'conv-s8', home_name: 'Session 8 planning', reply_to: 'ent-s4', author: 'p-maya', author_name: '@Maya' }, here: 'conv-s8' }
const post3: LinkTarget = { kind: 'post', post: { id: 'ent-s3', number: 3, home: 'conv-s8', home_name: 'Session 8 planning', reply_to: null, author: 'p-priya', author_name: '@Priya' } }
const s8: LinkTarget = { kind: 'conversation', conversation: 'conv-s8', name: 'Session 8 planning' }
eq(captionOf(reply5), 'Link to #5 · reply', 'over a reply: what letting go means')
eq(captionOf(post3), 'Link to #3 · post', 'over a post')
eq(captionOf(s8), 'Include in Session 8 planning', 'over a conversation')

const obj = { kind: 'object' as const, part }
eq(flat(confirmWords(obj, reply5, 'Session 8 planning')),
  'Link Adjusted XP (chart) to #5 in Session 8 planning? A reply is added to #5 that shows this chart. The chart itself stays in Dungeons and Dragons, #4 — nothing is copied.',
  "the reply confirmation is the owner's wording")
eq(confirmWords(obj, reply5, 'Session 8 planning').filter((x) => typeof x !== 'string'),
  [{ b: 'Adjusted XP' }, { b: '#5 in Session 8 planning' }, { b: 'Dungeons and Dragons, #4' }], 'what is linked, where, and where it remains are said in bold')
eq(flat(confirmWords(obj, s8)),
  'Bring Adjusted XP (chart) into Session 8 planning? Include its post adds Dungeons and Dragons, #4 here. Post a reference here adds a post that shows this chart. The chart itself stays in Dungeons and Dragons, #4 — nothing is copied.',
  'the conversation confirmation offers both, naming where the original remains')
ok(!flat(confirmWords(obj, { kind: 'conversation', conversation: 'conv-dnd', name: 'Dungeons and Dragons' })).includes('Include its post'),
  'its own home is not offered its own post')
eq(agentLine('@claude', part), "Claude will be given this chart (Adjusted XP, as of #4's current version) — nothing else from #4.",
  'the agent line, when the reply asks an agent')

const own: LinkTarget = { kind: 'post', post: { id: 'ent-d4', number: 4, home: 'conv-dnd', home_name: 'Dungeons and Dragons', reply_to: null, author: 'p-claude', author_name: '@claude' } }
eq(refusalOf(obj, own), 'Not linked: that is the post it is in.', 'dropped on its own post: refused in words')
eq(refusalOf(obj, reply5), null, 'anywhere else it may be linked')
const wholePost = { kind: 'post' as const, post: { id: 'ent-d4', number: 4, home: 'conv-dnd', home_name: 'Dungeons and Dragons' } }
eq(refusalOf(wholePost, { kind: 'conversation', conversation: 'conv-dnd', name: 'Dungeons and Dragons' }),
  'Not included: that is the conversation it was written in.', "a post into its own conversation: the server's refusal, said first")
eq(flat(confirmWords(wholePost, s8)), 'Include #4 from Dungeons and Dragons in Session 8 planning? It stays in Dungeons and Dragons; Session 8 planning shows it too. Nothing is moved or copied.',
  'a whole post is Include in…')

/* -- what is written ------------------------------------------------------------ */

const body = linkReplyBody(part, { id: 'ent-s5', author: 'p-maya', home: 'conv-s8' }, 'p-me', 'conv-s8', 'op-1')
eq({ replies_to: body.replies_to, conversation: body.conversation, action: body.action, dispatch: body.dispatch, addressed_to: body.addressed_to, parts: body.parts },
  { replies_to: 'ent-s5', conversation: 'conv-s8', action: 'record-only', dispatch: [], addressed_to: ['p-maya'], parts: [part] },
  'a confirmed drop on a post is one reply to it, carrying the reference, recording only')
const asked = linkReplyBody(part, { id: 'ent-s5', author: 'p-claude', home: 'conv-s8' }, 'p-me', 'conv-s8', 'op-2', true)
eq([asked.action, asked.dispatch.map((d) => d.participant)], ['ask-participant', ['p-claude']], 'Link and ask asks that author, and only them')
eq(linkReplyBody(part, { id: 'ent-s5', author: 'p-me', home: 'conv-s8' }, 'p-me', 'conv-s8', 'op-3').addressed_to, [], 'never addressed to yourself')
const ref = referencePostBody(part, 'p-me', 'conv-s8', 'op-4')
eq([ref.conversation, 'replies_to' in ref, ref.parts, ref.action], ['conv-s8', false, [part], 'record-only'], 'Post a reference here is one new post, no reply')

/* -- the draft: a chip until Send ------------------------------------------------ */

const d0: Draft = emptyDraft()
ok(isEmpty(d0) && !isEmpty({ ...d0, refs: [{ part }] }), 'a draft holding only a reference is something to send')
const refs = withRef(withRef([], { part }), { part: { ...part } })
eq(refs.length, 1, 'the same object dropped twice is one chip')
eq(withRef(refs, { part: { type: 'turn', ref: 'ent-d4', text: '#4' } }).length, 2, 'the post it is in is a different reference')
eq(bodyOf({ ...d0, refs }, 'p-me', []).parts, [part], 'only a reference: the post is that part')
eq(bodyOf({ ...d0, text: 'Which ambush fits?', refs }, 'p-me', []).parts,
  [{ type: 'text', text: 'Which ambush fits?' }, { type: 'text', text: '\n\n' }, part], 'after the words, on its own line')
eq(refParts('', [{ part }, { part: { type: 'turn', ref: 'ent-d4', text: '#4' } }]),
  [part, { type: 'text', text: '\n\n' }, { type: 'turn', ref: 'ent-d4', text: '#4' }], 'several, each on its own line')
eq(bodyOf({ ...d0, text: 'x' }, 'p-me', []).parts, [{ type: 'text', text: 'x' }], 'a draft with no references is unchanged')
ok(chosenBody({ ...d0, refs }, { label: 'Ambush A' }, 0, 'exp-1').parts.some((p) => p.type === 'object'), 'an answer by choice keeps its references')

/* -- it reads as a reference, never as an attachment ------------------------------ */

const post = { id: 'ent-r1', parts: [{ type: 'text', text: 'see ' }, part] } as unknown as Post
eq(textOf(post), 'see Adjusted XP', 'its characters are in the words, as any reference')
eq(said(post).kinds, [], 'it is not counted as something the post carries')
eq(sourceOf(post).text, 'see Adjusted XP', 'annotations read the same words, offset for offset')
eq(picturesOf(post), [], 'never drawn as a picture of the post')

console.log(`fluid refs: ${checks} checks passed`)
