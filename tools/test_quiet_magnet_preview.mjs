import assert from 'node:assert/strict'
import { readOnlyRequest } from './quiet-magnet-preview.mjs'

let passed = 0
for (const [method, url, expected] of [
  ['GET', '/fluid/api/magnets/mag-fixture/read?mode=summary', true],
  ['HEAD', '/api/brain?identity=1', true],
  ['OPTIONS', '/api/brain', true],
  ['POST', '/fluid/api/magnets/mag-fixture/conversation', false],
  ['POST', '/fluid/api/arrangements/ent-fixture', false],
  ['PUT', '/api/anything', false],
  ['DELETE', '/api/anything', false],
  ['GET', '/api/capacity', false],
  ['GET', '/api/capacity?all=1', false],
  ['GET', '/api/%63apacity', false],
  ['GET', '/api/capacity/anything', false],
  ['HEAD', '/api/capacity', false],
  ['GET', '/api/%', false],
]) {
  assert.equal(readOnlyRequest(method, url), expected, `${method} ${url}`)
  passed++
}
console.log(`${passed} passed, 0 failed, 0 skipped, 0 errors`)
