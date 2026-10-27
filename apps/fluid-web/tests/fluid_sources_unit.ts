import assert from 'node:assert/strict'
import { sourcesHash, sourcesPath } from '../src/surfaces/sources/navigation'
import { readRoute, writeRoute } from '../src/surfaces/sources/route'
import { docOf } from '../src/experimental/objectkinds'
import { documentUrl } from '../src/fluid/workspace/ObjectBody'

assert.equal(sourcesPath('#/brain/sources'), '', 'the Sources overview is addressable')
assert.equal(sourcesPath('#/brain/sources/v/adm-123/at/5-9'), 'v/adm-123/at/5-9', 'a file observation address survives')
assert.equal(sourcesPath('#/brain'), null, 'another Brain surface is not Sources')
assert.equal(sourcesHash('folder/o/notes%2Ftoday.md'), '#/brain/sources/folder/o/notes%2Ftoday.md')

const object = { at: 'object' as const, col: 'collection one', key: 'notes/today.md' }
assert.deepEqual(readRoute(writeRoute(object)), object, 'collection and file keys round-trip without losing slashes')
assert.equal(docOf('text/markdown', 'notes.md'), 'markdown', 'Markdown opens as content in Details')
assert.equal(docOf('text/plain', 'notes.txt'), 'plain', 'plain text opens as content in Details')
assert.equal(docOf('application/pdf', 'paper.pdf'), null, 'binary files keep the file card')
assert.equal(documentUrl('adm-one/two'), '/fluid/api/document?ref=adm-one%2Ftwo', 'Details asks the bounded document endpoint safely')

console.log('sources: navigation, routes, and Detail document selection passed')
