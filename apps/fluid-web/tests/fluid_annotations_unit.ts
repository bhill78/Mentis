import assert from 'node:assert/strict'
import { commentEditorHeight, commentsOldestFirst, submitsComment } from '../src/fluid/conversation/annotated'

assert.deepEqual(commentsOldestFirst(['new', 'old', 'middle'], (id) => ({ old: 10, middle: 20, new: 30 })[id]), ['old', 'middle', 'new'])
assert.deepEqual(commentsOldestFirst(['first', 'loading', 'last'], (id) => ({ first: 10, last: 30 })[id]), ['first', 'loading', 'last'])

assert.equal(submitsComment({ key: 'Enter' }), false, 'plain Enter writes Markdown')
assert.equal(submitsComment({ key: 'Enter', ctrlKey: true }), true, 'Ctrl+Enter submits')
assert.equal(submitsComment({ key: 'Enter', metaKey: true }), true, 'Cmd+Enter submits')
assert.equal(submitsComment({ key: 'x', ctrlKey: true }), false)

assert.equal(commentEditorHeight(40), 112, 'editor starts large')
assert.equal(commentEditorHeight(180), 180, 'editor grows with content')
assert.equal(commentEditorHeight(900), 320, 'editor stops growing and scrolls')

console.log('annotations: 9 checks passed')
