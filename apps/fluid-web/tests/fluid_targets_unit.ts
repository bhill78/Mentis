import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { keepSlot, minSize, place, zones, type Node, type Zone } from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const here = fileURLToPath(new URL('.', import.meta.url))
const readSrc = (file: string) => readFileSync(here + '../src/' + file, 'utf8')
const z = (id: string, name = id): Zone => ({ type: 'zone', id, show: 'objects', name, slot: keepSlot() })

/* 1. Multi-section split geometry and thresholds on tablets (820px, 1024px) */
const twoRow: Node = { type: 'split', dir: 'row', sizes: [0.5, 0.5], kids: [z('a'), z('b')] }
const threeRow: Node = { type: 'split', dir: 'row', sizes: [0.33, 0.33, 0.34], kids: [z('a'), z('b'), z('c')] }
const twoCol: Node = { type: 'split', dir: 'col', sizes: [0.5, 0.5], kids: [z('a'), z('b')] }

// Two zones in row require 240 + 12 + 240 = 492px
eq(minSize(twoRow, 'w'), 492, '2 sections side-by-side require 492px minimum')
// Three zones in row require 240 * 3 + 12 * 2 = 744px
eq(minSize(threeRow, 'w'), 744, '3 sections side-by-side require 744px minimum')
// Two zones in column require 240px width and 140 * 2 + 12 = 292px height
eq(minSize(twoCol, 'w'), 240, '2 vertical sections require 240px width')
eq(minSize(twoCol, 'h'), 292, '2 vertical sections require 292px height')

// In narrow sheet on iPad Air (820px viewport, 804px content width):
const tablet820w = 804
ok(tablet820w >= minSize(twoRow, 'w'), '820px tablet width accommodates 2 sections side-by-side')
ok(tablet820w >= minSize(threeRow, 'w'), '820px tablet width accommodates 3 sections side-by-side')

const placed2 = place(twoRow, { x: 0, y: 0, w: tablet820w, h: 700 })
const rA = placed2.get(zones(twoRow)[0])!
const rB = placed2.get(zones(twoRow)[1])!
ok(rA.w > 390 && rB.w > 390, 'two zones split available width cleanly without stacking')
eq(rA.y, rB.y, 'two zones sit on the same row')

const placed3 = place(threeRow, { x: 0, y: 0, w: tablet820w, h: 700 })
eq(zones(threeRow).map((k) => placed3.get(k)?.y), [0, 0, 0], 'three zones sit side-by-side on tablet without wrapping/stacking')

/* 2. Theme tokens */
const themeCss = readSrc('theme.css')
ok(themeCss.includes('--touch-target: 44px;'), 'theme.css defines --touch-target: 44px for coarse pointer hit area baseline')

/* 3. Tree caption tools touch targets and affordances */
const treeCss = readSrc('fluid/workspace/tree.css')
ok(treeCss.includes('@media (hover: none)') && treeCss.includes('.wt-tools { opacity: 0.85; pointer-events: auto; }'),
  'tree.css shows .wt-tools quietly at rest under (hover: none)')
ok(treeCss.includes('@media (pointer: coarse)') && treeCss.includes('min-width: var(--touch-target, 44px);'),
  'tree.css expands .wt-tools buttons to 44px min-width/height under pointer: coarse')
ok(treeCss.includes('[data-act="drag-zone"]') && treeCss.includes('@container (max-width: 380px)'),
  'tree.css hides drag-zone at narrow container width so only most-used controls remain')

/* 4. Workspace zone caption menu and hints */
const workspaceCss = readSrc('fluid/workspace/workspace.css')
ok(workspaceCss.includes('@media (hover: none)') && workspaceCss.includes(':is(.wk, .wk-zone) .wk-zmenu { opacity: .85; pointer-events: auto; }'),
  'workspace.css reveals .wk-zmenu at rest under (hover: none)')
ok(workspaceCss.includes('@media (pointer: coarse)') && workspaceCss.includes(':is(.wk, .wk-zone) .wk-zmenu') && workspaceCss.includes('min-width: var(--touch-target, 44px);'),
  'workspace.css provides 44px hit target for .wk-zmenu under pointer: coarse')

/* 5. Float controls (header buttons, resize corner, dock pads) */
const floatsCss = readSrc('fluid/focus/floats.css')
ok(floatsCss.includes('@media (pointer: coarse)') && floatsCss.includes('.fl-head button') && floatsCss.includes('min-width: var(--touch-target, 44px);'),
  'floats.css provides >= 44px touch targets for float buttons')
ok(floatsCss.includes('.fl-resize') && floatsCss.includes('width: var(--touch-target, 44px);'),
  'floats.css provides 44x44px hit area for resize corner')
ok(floatsCss.includes('.pad') && floatsCss.includes('width: var(--touch-target, 44px);') && floatsCss.includes('margin-left: -4px;'),
  'floats.css expands dock pads to 44x44px and centers them cleanly')

/* 6. Focus search bar on phones and coarse pointer */
const searchCss = readSrc('fluid/search-in/search-in.css')
ok(searchCss.includes('@media (hover: none)') && searchCss.includes('.wk-zcap .fs-open {'),
  'search-in.css ensures search open button is reachable under (hover: none)')
ok(searchCss.includes('@media (pointer: coarse)') && searchCss.includes('.fs-btn') && searchCss.includes('min-width: var(--touch-target, 44px);'),
  'search-in.css ensures search buttons maintain >= 44px hit targets')
ok(searchCss.includes('@media (max-width: 480px)'),
  'search-in.css ensures search bar row fits 390px screens')

/* 7. Conversation tools and grips */
const convCss = readSrc('fluid/conversation/conversation.css')
ok(convCss.includes('@media (hover: none)') && convCss.includes('.fx-conv-tools { opacity: 0.85; }'),
  'conversation.css reveals .fx-conv-tools under (hover: none)')

const gripCss = readSrc('fluid/conversation/grip.css')
ok(gripCss.includes('@media (hover: none)') && gripCss.includes('.fw-card .fx-text-grips > .fx-grip { opacity: .7; }'),
  'grip.css shows text grips quietly at rest under (hover: none)')
ok(gripCss.includes('@media (pointer: coarse)') && gripCss.includes('.fx-grip::after') && gripCss.includes('width: var(--touch-target, 44px);'),
  'grip.css provides 44x44px pseudo-element hit target for grips')
ok(gripCss.includes('.fx-text-grips {') && gripCss.includes('gap: 16px;'),
  'grip.css spaces adjacent text grips so 44px targets do not overlap')

console.log(`fluid targets: ${checks} checks passed`)
