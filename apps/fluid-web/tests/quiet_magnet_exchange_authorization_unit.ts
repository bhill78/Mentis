import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement, type ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import MagnetAuthorization, { authorizeMessage, noOutside, type OutsideChoice } from '../src/fluid/composer/MagnetAuthorization'
import { miniAsking } from '../src/quiet2/magnets/asking'
import type { MagnetResource } from '../src/quiet2/magnets/contract'
import type { MiniConversation, MiniSnapshot } from '../src/quiet2/magnets/conversation'

const authored = { action: 'ask-mentis', text: 'My exact question', parts: [{ type: 'text', text: 'My exact question' }] }

test('default and next exchange carry no authority; explicit sources never become authored words', () => {
  assert.equal(authorizeMessage(authored, noOutside, true), authored)
  const got = authorizeMessage(authored, { web: true, collection: ' col-extra ' }, true)
  assert.deepEqual(got.magnet_authorization, { opens: [{ kind: 'runtime-web-search' }, { kind: 'collection', collection: 'col-extra' }] })
  assert.equal(got.text, authored.text)
  assert.equal(got.parts, authored.parts)
  assert.equal('turn' in (got.magnet_authorization as object), false)
  assert.equal('magnet_authorization' in authorizeMessage(authored, noOutside, true), false)
  assert.equal('magnet_authorization' in authored, false)
})

test('saved questions and record-only sends cannot silently consume an outside choice', () => {
  assert.throws(() => authorizeMessage(authored, { web: true, collection: '' }, false), /grounded/)
  assert.throws(() => authorizeMessage({ ...authored, action: 'record-only' }, { web: false, collection: 'col-one' }, true), /record only/)
  assert.equal(authorizeMessage({ ...authored, action: 'record-only' }, noOutside, false).action, 'record-only')
})

test('control interaction sends only the checkbox and named collection the owner chose', () => {
  let choice: OutsideChoice = noOutside
  type Props = { children?: ReactElement<Props>[]; onChange?(e: { target: { checked: boolean; value: string } }): void }
  const view = () => MagnetAuthorization({ value: choice, change: (v) => { choice = v }, allowed: true, busy: false })
  const inputs = (view().props.children as ReactElement<Props>[]).filter((c) => c?.type === 'label')
    .map((label) => (label.props.children as ReactElement<Props>[]).find((c) => c?.type === 'input')!)
  inputs[0].props.onChange!({ target: { checked: true, value: '' } })
  assert.deepEqual(choice, { web: true, collection: '' })
  const labels = (view().props.children as ReactElement<Props>[]).filter((c) => c?.type === 'label')
  const collection = (labels[1].props.children as ReactElement<Props>[]).find((c) => c?.type === 'input')!
  collection.props.onChange!({ target: { checked: false, value: 'col-extra' } })
  assert.deepEqual(authorizeMessage(authored, choice, true).magnet_authorization,
    { opens: [{ kind: 'runtime-web-search' }, { kind: 'collection', collection: 'col-extra' }] })
  const html = renderToStaticMarkup(createElement(MagnetAuthorization, { value: choice, change: () => {}, allowed: false, busy: true }))
  assert.match(html, /fieldset disabled=""/)
  assert.match(html, /Saved questions use collected information only/)
  assert.match(html, /Clear outside sources/)
  assert.match(html, /next exchange starts with no outside sources allowed/)
})

function fixture() {
  let state = { context: null }
  let snapshot: Partial<MiniSnapshot> = {}
  const calls: string[] = []
  const resource = { brainKey: 'fixture', saved: { id: 'mag-fixtureA' },
    snapshot: () => state, update: (v: object) => { state = { ...state, ...v } } } as unknown as MagnetResource
  const conversation = { conversation: null, snapshot: () => snapshot,
    createOwn: async () => { calls.push('create'); conversation.conversation = 'ent-own' },
    submit: async (body: unknown, op: string) => { calls.push('submit'); sent = body; snapshot = { sent: { op, post: 'ent-asking', number: 1, replayed: false } } },
  } as unknown as MiniConversation
  let sent: unknown
  return { resource, conversation, calls, body: () => sent,
    refuse: () => { conversation.submit = async () => { snapshot = { sendError: 'refused', uncertain: true } } } }
}

test('Magnet adapter creates its Conversation first and submits authorization in the one asking write', async () => {
  const f = fixture(), ask = miniAsking(f.resource, f.conversation)
  const body = authorizeMessage(authored, { web: true, collection: '' }, true)
  assert.equal(ask.magnetAuthorization?.allowed(), true)
  await ask.send(body, 'op-1', 'fixture@instance')
  assert.deepEqual(f.calls, ['create', 'submit'])
  assert.deepEqual(f.body(), body)
})

test('refused or uncertain writes throw, so the Composer keeps its explicit choice', async () => {
  const f = fixture(), ask = miniAsking(f.resource, f.conversation)
  f.refuse()
  await assert.rejects(() => ask.send(authorizeMessage(authored, { web: true, collection: '' }, true), 'op-1', 'fixture@instance'), /refused/)
})

test('failure to create the Conversation sends nothing and authorizes nothing', async () => {
  const f = fixture(), ask = miniAsking(f.resource, f.conversation)
  f.conversation.createOwn = async () => {}
  await assert.rejects(() => ask.send(authorizeMessage(authored, { web: true, collection: '' }, true), 'op-1', 'fixture@instance'), /Conversation/)
  assert.deepEqual(f.calls, [])
})
