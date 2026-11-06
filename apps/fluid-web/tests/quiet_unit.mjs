import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

// The same TS loader as the other client unit suites; no browser or API mock.
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

const { conversationPath, flowTurns, href, postingBody, settlingKey, submissionKey } = await import('../src/quiet/model.ts')
const { readAddress } = await import('../src/address.ts')
const root = { id: 'ent-root', number: 1, author: 'ent-agent', root: 'ent-root', answering: null }
const reply = { id: 'ent-reply', number: 200, author: 'ent-agent', root: 'ent-root', answering: 'ent-root' }

test('conversation, topic and reply use the existing address round trip', () => {
  const url = href('ent-c', 'ent-topic', reply.id)
  const address = readAddress(url)
  assert.equal(address.conversation, 'ent-c')
  assert.equal(address.topic, 'ent-topic')
  assert.equal(address.turn, reply.id)
  assert.equal(href('ent-other'), '#/c/ent-other')
})
test('history asks for the server batch in the selected topic', () => {
  const path = conversationPath('ent-c', 'ent-topic', { before: 201 })
  assert.equal(path, '/api/conversations/ent-c?batch=30&topic=ent-topic&before=201')
  assert.equal(conversationPath('ent-c', null, { after: 30 }), '/api/conversations/ent-c?batch=30&after=30')
})
test('unfocused flow never promotes a reply whose parent is outside the batch', () => {
  assert.deepEqual(flowTurns({ turns: [root, reply], focus_topic: null }), [root])
})
test('topic flow retains filed replies and their original relationships', () => {
  assert.deepEqual(flowTurns({ turns: [reply], focus_topic: 'ent-topic' }), [reply])
  assert.equal(reply.answering, 'ent-root')
})
test('older servers without root metadata still keep replies out of the flow', () => {
  assert.deepEqual(flowTurns({ turns: [{ ...root, root: undefined }, { ...reply, root: undefined }], focus_topic: null }), [{ ...root, root: undefined }])
})
test('new posts preserve author, conversation and explicit topic', () => {
  const body = postingBody('  Words  ', 'record-only', 'ent-owner', 'ent-c', 'ent-topic', null, 'op-1')
  assert.equal(body.author, 'ent-owner')
  assert.equal(body.conversation, 'ent-c')
  assert.deepEqual(body.parts, [{ type: 'text', text: 'Words' }])
  assert.deepEqual(body.topics, ['ent-topic'])
  assert.equal(body.action, 'record-only')
  assert.deepEqual(body.dispatch, [])
  assert.equal(body.replies_to, undefined)
  assert.equal(body.op, 'op-1')
})
test('replies answer the selected reply itself, not the root', () => {
  const body = postingBody('Reply', 'record-only', 'ent-owner', 'ent-c', null, reply, 'op-2')
  assert.equal(body.replies_to, reply.id)
  assert.deepEqual(body.addressed_to, ['ent-agent'])
  assert.deepEqual(body.topics, [])
})
test('a reply to oneself adds no other addressee', () => {
  assert.deepEqual(postingBody('Reply', 'record-only', 'ent-agent', 'ent-c', null, reply, 'op').addressed_to, [])
})
test('Ask Mentis is the existing action without invented direct dispatch', () => {
  const body = postingBody('@Ada #Planning', 'ask-mentis', 'ent-owner', 'ent-c', null, null, 'op')
  assert.equal(body.action, 'ask-mentis')
  assert.deepEqual(body.addressed_to, [])
  assert.deepEqual(body.topics, [])
  assert.deepEqual(body.dispatch, [])
})
test('an unchanged failed submission retains the supplied settling key', () => {
  const args = ['Message', 'record-only', 'ent-owner', 'ent-c', null, null, 'stable-key']
  assert.deepEqual(postingBody(...args), postingBody(...args))
})
test('words, action and reply target together are what one submission is', () => {
  const same = submissionKey('Words', 'record-only', null)
  assert.equal(submissionKey('Words', 'record-only', null), same)
  assert.notEqual(submissionKey('Words ', 'record-only', null), same)
  assert.notEqual(submissionKey('Words', 'ask-mentis', null), same)
  assert.notEqual(submissionKey('Words', 'record-only', reply), same)
  assert.notEqual(submissionKey('Words', 'record-only', root),
                  submissionKey('Words', 'record-only', reply))
})
test('typing a failed attempt away and back asks with its original key', () => {
  const attempt = { submission: submissionKey('Words', 'record-only', null), op: 'op-sent' }
  // the draft has minted a fresh key per keystroke on the way there and back
  assert.equal(settlingKey(submissionKey('Words', 'record-only', null), 'op-typed', attempt), 'op-sent')
})
test('a changed submission, and a draft with nothing behind it, ask anew', () => {
  const attempt = { submission: submissionKey('Words', 'record-only', null), op: 'op-sent' }
  assert.equal(settlingKey(submissionKey('Other words', 'record-only', null), 'op-typed', attempt), 'op-typed')
  assert.equal(settlingKey(submissionKey('Words', 'ask-mentis', null), 'op-typed', attempt), 'op-typed')
  assert.equal(settlingKey(submissionKey('Words', 'record-only', reply), 'op-typed', attempt), 'op-typed')
  assert.equal(settlingKey(submissionKey('Words', 'record-only', null), 'op-fresh', undefined), 'op-fresh')
})
