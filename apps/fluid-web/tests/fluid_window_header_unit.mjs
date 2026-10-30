import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (path) => readFileSync(src + path, 'utf8').replace(/\r\n/g, '\n')
const zones = read('fluid/workspace/Zones.tsx')
const threads = read('fluid/conversation/ThreadWindow.tsx')
const floats = read('fluid/focus/Floats.tsx')
const header = read('fluid/focus/FloatingHeader.tsx')
const css = read('fluid/focus/floats.css')
const chrome = read('fluid/surface/SurfaceChrome.tsx')
const hosts = read('fluid/surface/chromeHosts.ts')

assert.match(header, /export function FloatingHeader/, 'the shared floating header is exported once')
/* Surface Tension P4: the header is the one surface chrome; Minimise is Collapse/Expand (I-1), lent as the window's host */
assert.match(header, /<(SurfaceChrome|LegacySurfaceChromeBar) /, 'the shared header draws the surface chrome (header-only until surface composition package 2)')
for (const control of ['fl-drag-grip', 'wk-zmenu fl-btn', 'fl-close']) {
  assert.ok(chrome.includes(control), `the shared chrome carries ${control}`)
}
assert.match(hosts, /h\.collapse = \{ run: w\.minimise\.run/, "the window's minimise is its Collapse")
assert.match(floats, /<FloatingHeader name=\{name\}/, 'conversation and run floats use the shared header')
assert.match(zones, /floating \? <FloatingHeader/, 'workspace floats use the shared header')
assert.match(threads, /floating \? <FloatingHeader/, 'thread floats use the shared header')
assert.doesNotMatch(floats, /FocusSplit|ObjectActions|<Grip\b/, 'duplicate and content-specific actions are absent from float headers')
assert.match(floats, /<MinimizedTabs floats=\{floats\}/, 'minimized floats have one bottom tab strip')
assert.match(floats, /className="fl-body fq-float-body"/, 'float bodies remain mounted while minimized')
assert.match(css, /min-width:\s*220px/, 'the minimum floating width remains explicit')
assert.match(css, /\.wk-float \.fl-head \.wk-zmenu[^{}]*\{[^}]*opacity:\s*1[^}]*pointer-events:\s*auto/s, 'the settings gear stays visible and interactive in every float')

console.log('fluid_window_header_unit: ok')
