import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (path) => readFileSync(src + path, 'utf8').replace(/\r\n/g, '\n')

const post = read('fluid/render/post.tsx')
const theme = read('theme.css')
const floats = read('fluid/focus/floats.css')
const conversation = read('fluid/conversation/conversation.css')
const decisions = read('experimental/types/data.css')
const top = read('fluid/frame/TopBar.tsx')
const bar = read('fluid/frame/BarControls.tsx')

// Top-bar marks remain direct because each opens a distinct scope.
for (const control of ['HomeAndNew', 'LatestControl', 'id="settings"', 'BarEnd'])
  assert.ok(top.includes(control), `top bar keeps unique ${control}`)
for (const control of ['CapacityControl', 'label="Search"', 'label="Notifications"'])
  assert.ok(bar.includes(control), `bar end keeps unique ${control}`)

// The card itself opens the post. Secondary post actions stay reachable in More.
assert.match(post, /only=\{\['peek', 'focus'\]\}/, 'post row keeps only unique direct object actions')
for (const action of ['details', 'full', 'select'])
  assert.match(post, new RegExp(`<button className="fx-opt" data-act="${action}"`), `${action} moved into More`)
assert.doesNotMatch(post, /mark\('(?:fx-details|fx-fullchip|fw-select-chip)'/, 'moved actions are not duplicated as direct marks')

// Front windows, selected posts, and decision cards share one quiet edge.
assert.match(theme, /--selection-edge:/, 'theme defines the shared selection edge')
assert.match(floats, /\.wk-float\.front[\s\S]*outline:\s*1px solid var\(--float-border-front, var\(--selection-edge\)\)/, 'front float uses the shared edge')
assert.match(conversation, /\.fx-post\.fw-selected[\s\S]*outline:\s*1px solid var\(--selection-edge\)/, 'selected post uses the shared edge')
assert.match(decisions, /\.rb-decision \{[\s\S]*border:\s*1px solid var\(--selection-edge/, 'decision card uses the shared edge')
assert.doesNotMatch(decisions, /\.rb-decision \{[\s\S]*?border-left:\s*3px solid/, 'decision card has no bright left rail')
assert.doesNotMatch(decisions, /\.rb-decision \.rb-dec-option\.recorded \{[^}]*border:\s*2px solid var\(--ok/, 'recorded option has no bright green frame')

console.log('fluid_icon_simplification_unit: ok')
