/* QUIET 2'S PICTURE STRIP, FOR WHAT A RUN RETURNED (not what a person
 * attached): `returnedItemOf` classifies one `returned_with` entry the same
 * way `itemOf` reads a part when neither carries a verified treatment
 * (quiet/media/view.ts); `adapt` (quiet2/real.ts) folds those into the same
 * `pictures`/`attachments` a composer's own attachments get, and leaves out
 * one already placed inline on its own line in the body. */
import assert from 'node:assert/strict'
import test from 'node:test'
import { returnedItemOf } from '../src/quiet/media/view.ts'
import { adapt } from '../src/quiet2/real.ts'
import type { HeldState, Turn } from '../src/api.ts'

const heldImage = (ref: string, extra: Partial<HeldState> = {}): HeldState => ({
  ref, state: 'held', url: `/api/artifacts/${ref}`, name: 'shot.png',
  claimed_media_type: 'image/png', size: 2048, ...extra,
})

const base = (parts: Turn['parts'], returned_with?: HeldState[], text = ''): Turn => ({
  id: 'ent-turn', number: 1, parts: text ? [{ type: 'text', text }, ...parts] : parts,
  returned_with, author: 'ent-a', author_alias: '@Caretaker', written_by: 'claude/x',
  at: 1700000000, addressees: [], topics: [], answering: null, replies: [],
})

test("a returned artifact that isn't held draws nothing", () => {
  assert.equal(returnedItemOf({ ref: 'adm-1', state: 'not-held' }), null)
})
test('a returned artifact claimed as a picture reads as an image', () => {
  const item = returnedItemOf(heldImage('adm-2'))
  assert.equal(item?.kind, 'image')
  assert.equal(item?.url, '/api/artifacts/adm-2')
})
test('a returned artifact that is not a picture reads by its claim or name', () => {
  assert.equal(returnedItemOf(heldImage('adm-3', { claimed_media_type: 'text/plain', name: 'log.txt' }))?.kind, 'text')
  assert.equal(returnedItemOf(heldImage('adm-4', { claimed_media_type: 'application/zip', name: 'bundle.zip' }))?.kind, 'file')
})

test("one picture a run returned draws as the post's figure, like an attached one", () => {
  const post = adapt(base([], [heldImage('adm-10')]), 'ent-c', () => undefined)
  assert.equal(post.blocks.some((b) => b.kind === 'figure'), true)
  assert.equal(post.attachments.length, 0)
})
test('two or more pictures a run returned draw as the compact gallery', () => {
  const post = adapt(base([], [heldImage('adm-11'), heldImage('adm-12')]), 'ent-c', () => undefined)
  const wide = post.blocks.find((b) => b.kind === 'wide') as { images: unknown[] } | undefined
  assert.equal(wide?.images.length, 2)
})
test('a non-image a run returned is a file attachment, not a picture', () => {
  const post = adapt(base([], [heldImage('adm-13', { claimed_media_type: 'application/zip', name: 'bundle.zip' })]), 'ent-c', () => undefined)
  assert.equal(post.blocks.some((b) => b.kind === 'figure' || b.kind === 'wide'), false)
  assert.equal(post.attachments.length, 1)
  assert.equal(post.attachments[0].name, 'bundle.zip')
})
test('a returned picture already placed inline on its own line is not drawn twice', () => {
  const post = adapt(base([], [heldImage('adm-00000000000e')], '![a screenshot](adm-00000000000e)'), 'ent-c', () => undefined)
  assert.equal(post.blocks.some((b) => b.kind === 'figure' || b.kind === 'wide'), false)
  assert.equal(post.attachments.length, 0)
})
test('a composer attachment and a returned picture both draw, together', () => {
  const parts: Turn['parts'] = [{
    type: 'image', ref: 'ent-p',
    artifact: { ref: 'adm-p', state: 'held', url: '/api/artifacts/adm-p', name: 'mine.png', size: 10, claimed_media_type: 'image/png' },
  }]
  const post = adapt(base(parts, [heldImage('adm-15')]), 'ent-c', () => undefined)
  const wide = post.blocks.find((b) => b.kind === 'wide') as { images: unknown[] } | undefined
  assert.equal(wide?.images.length, 2)
})
