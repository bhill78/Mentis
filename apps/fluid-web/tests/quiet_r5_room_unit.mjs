/* PACKAGE L's unit suite (round 5), without a browser.
 *
 * What a DOM-less Node test can actually decide here: the arithmetic the room
 * is drawn from, and the rules its two stylesheets have to carry for the
 * claims to be true. The geometry itself -- the work area opening on the
 * right, the separator moving it, the one-surface fallback, focus and the
 * reading surviving a change of room -- is a live-browser claim and is
 * asserted in tests/test_quiet_r5_room_browser.py against a real page.
 *
 * F21: this suite is .mjs and is not typechecked; typecheck:tests keeps to
 * its existing explicit .ts list.
 */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
      for (const suffix of ['', '.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (suffix && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.css$/.test(url)) return { format: 'module', shortCircuit: true, source: 'export {}' }
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

const room = await import('../src/quiet/workspace/WorkspaceRoom.tsx')
const ROOM_CSS = readFileSync(new URL('../src/quiet/workspace/room.css', import.meta.url), 'utf8')
const LAYOUT_CSS = readFileSync(new URL('../src/quiet/layout.css', import.meta.url), 'utf8')
const BOUNDARY = readFileSync(new URL('../src/fluid/workspace/Boundary.tsx', import.meta.url), 'utf8')
const BOUNDARIES_CSS = readFileSync(new URL('../src/fluid/workspace/boundaries.css', import.meta.url), 'utf8')
const QUIET_CHAT = readFileSync(new URL('../src/quiet/QuietChat.tsx', import.meta.url), 'utf8')

/* -- what the room is drawn from ------------------------------------------- */

test('the room exports the component the contract declares', async () => {
  const { ENTRIES } = await import('../src/quiet/contract.ts')
  const entry = ENTRIES.find((e) => e.path === './workspace/WorkspaceRoom.tsx')
  assert.ok(entry, 'the room is not in the seam manifest')
  assert.equal(entry.package, 'R5-L')
  assert.equal(typeof room.default, 'function')
})

test('the three minima are the ones F12 and Fluid name', () => {
  assert.equal(room.READING_MIN, 330, "the reading's floor is Fluid's READABLE")
  assert.equal(room.READING_MAX, 760, "the reading's ceiling is Quiet's measure")
  assert.equal(room.TOOLS_MIN, 240, 'the tools keep 240 CSS px (F12)')
  assert.equal(room.WORK_MIN, 300, 'the working area keeps 300 CSS px')
})

test("the repeated work minimum still agrees with Fluid's own", async () => {
  const { WORKSPACE_MIN } = await import('../src/fluid/workspace/Boundary.tsx')
  assert.equal(room.WORK_MIN, WORKSPACE_MIN,
    'WorkspaceRoom.WORK_MIN has drifted from Boundary.WORKSPACE_MIN')
})

test('three surfaces cost their minima plus the real gaps and the gutter', () => {
  const fit = { available: 0, gap: 18, gutter: 12 }
  assert.equal(room.requiredWidth(fit), 330 + 240 + 300 + 18 * 3 + 12)
  assert.equal(room.requiredWidth(fit), 936)
})

test('901px cannot hold three surfaces, and a wide window can', () => {
  const costs = { gap: 18, gutter: 12 }
  // 901px viewport, less the two 16px gutters the frame draws.
  assert.equal(room.roomFits({ ...costs, available: 901 - 32 }), false,
    'the fallback must be in force at 901px, as F12 says in so many words')
  assert.equal(room.roomFits({ ...costs, available: 1440 - 32 }), true)
  // 1024/1025, the other boundary this package is asked about: both hold
  // three surfaces, so nothing changes across it.
  assert.equal(room.roomFits({ ...costs, available: 1024 - 32 }), true)
  assert.equal(room.roomFits({ ...costs, available: 1025 - 32 }), true)
  // WHERE THE FALLBACK ACTUALLY TURNS, to the pixel: 968px of viewport
  // unpinned, because 936 of room is exactly what the three minima, the
  // three gaps and the separator cost.
  assert.equal(room.roomFits({ ...costs, available: 968 - 32 }), true)
  assert.equal(room.roomFits({ ...costs, available: 967 - 32 }), false)
  // A PINNED TOOLBAR MOVES THAT LINE, which is why the room measures rather
  // than trusting a breakpoint: 1024px with the strip pinned does NOT hold
  // three surfaces, and is drawn as one.
  assert.equal(room.roomFits({ ...costs, available: 1024 - 32 - 60 }), false)
  assert.equal(room.roomFits({ ...costs, available: 1028 - 32 - 60 }), true)
})

test('nothing is ever squeezed under its minimum: the reading gives way first', () => {
  const costs = { gap: 18, gutter: 12 }
  // 1440: the ceiling is Quiet's measure, not the room's whole width.
  assert.equal(room.readingCeiling({ ...costs, available: 1440 - 32 }), 760)
  // Pinned, the reading loses exactly the width the strip took.
  assert.equal(room.readingCeiling({ ...costs, available: 1440 - 32 - 60 }), 742)
  // At the narrowest width three surfaces fit at all, the reading is at its
  // floor and the other two are at theirs: nothing is compressed.
  const tight = { ...costs, available: room.requiredWidth(costs) }
  assert.equal(room.readingCeiling(tight), 330)
  // Narrower still, the ceiling never falls below the floor.
  assert.equal(room.readingCeiling({ ...costs, available: 400 }), 330)
})

test('the dragged width is clamped into the band, never outside it', () => {
  assert.equal(room.clampReading(1000, 760), 760)
  assert.equal(room.clampReading(100, 760), 330)
  assert.equal(room.clampReading(640.4, 760), 640)
  assert.equal(room.clampReading(640, 500), 500)
  // A ceiling below the floor cannot push the reading under READABLE.
  assert.equal(room.clampReading(640, 100), 330)
})

test('panes opens near 640px and the board near the readable minimum', () => {
  assert.equal(room.initialReading('panes', 760), 640)
  assert.equal(room.initialReading('board', 760), 330)
  // Clamped against the room actually available.
  assert.equal(room.initialReading('panes', 480), 480)
  assert.equal(room.initialReading('board', 480), 330)
})

/* -- F3: the scope writes nothing of Fluid's ------------------------------- */

/** Boundary.tsx's `Scoped` function, from its declaration to the one before
 *  it ends -- read as text, because "this path writes no nav" is a claim
 *  about what the source may contain. */
function scopedSource() {
  const start = BOUNDARY.indexOf('function Scoped(')
  assert.ok(start > 0, 'Boundary.tsx has no Scoped separator')
  const rest = BOUNDARY.slice(start)
  const end = rest.indexOf('\n}\n')
  assert.ok(end > 0, "Scoped's body could not be bounded")
  return rest.slice(0, end)
}

test('Boundary takes a controlled scope with exactly F3\'s fields', () => {
  const declared = BOUNDARY.slice(BOUNDARY.indexOf('export interface BoundaryScope'))
    .slice(0, BOUNDARY.slice(BOUNDARY.indexOf('export interface BoundaryScope')).indexOf('\n}\n'))
  for (const field of ['root', 'workspace', 'minConversation', 'allowRail', 'value',
    'onDrag', 'commit', 'label', 'announce'])
    assert.ok(new RegExp(`^\\s+${field}[?]?:`, 'm').test(declared), `BoundaryScope has no ${field}`)
  assert.ok(/scope[?]: BoundaryScope/.test(BOUNDARY), 'Boundary does not accept a scope')
  assert.ok(/if \(scope\) return <Scoped scope=\{scope\} \/>/.test(BOUNDARY),
    'a supplied scope must take the scoped path before either existing one')
})

test('the scoped separator writes neither nav nor the place, by any path', () => {
  const source = scopedSource()
  /* `workspace.quiet(...)` is the place write the other two boundaries make;
     `scope.workspace` is only the element on the far side of this one. */
  for (const forbidden of ['nav.', 'workspace.quiet', 'sizeConvPx', 'setThreadPx', 'useNav',
    'PRESET', 'railPx', 'snapshot(', 'keep()'])
    assert.ok(!source.includes(forbidden),
      `the scoped separator mentions ${forbidden}: this scope must write no Fluid state`)
  // Every width it decides goes out through the scope's own two callbacks.
  assert.ok(/live\.current\.onDrag\(/.test(source), 'the preview is not reported')
  assert.ok(/live\.current\.commit\(/.test(source), 'nothing is committed')
  // Cancellation reports the starting width and commits nothing.
  assert.ok(/const cancel = \(\) => \{ stop\(\); live\.current\.onDrag\(s0\) \}/.test(source),
    'a cancelled drag must report the width it started at and commit nothing')
  assert.ok(!/cancel[\s\S]{0,80}commit/.test(source), 'a cancellation must not commit')
})

test('rail snapping is off unless the scope asks for it', () => {
  const source = scopedSource()
  assert.ok(/s\.allowRail \? 0 : s\.minConversation/.test(source),
    'the floor must be minConversation unless allowRail says otherwise')
  assert.ok(/live\.current\.allowRail && to < least - SNAP/.test(source),
    'the snap affordance must be gated on allowRail')
})

test('Quiet asks for no rail and for the readable floor', () => {
  const source = readFileSync(new URL('../src/quiet/workspace/WorkspaceRoom.tsx', import.meta.url), 'utf8')
  assert.ok(/allowRail: false/.test(source), 'Quiet must disable rail snapping')
  assert.ok(/minConversation: READING_MIN/.test(source))
  /* COMMITTED CLAMPED, by both channels (review finding 1): the separator's
     own ceiling is how far it may travel, measured on the room beside it, and
     that can reach past Quiet's measure -- so what the bookmark is given is
     what the room DRAWS. Still only the reading width, and still nothing
     else. */
  assert.ok(/commit: \(px: number\) => onRoom\(\{ readingPx: clampReading\(px, ceiling\) \}\)/.test(source),
    'commit must patch only the room bookmark\'s reading width, clamped as it is drawn')
  assert.ok(/onDrag: \(px: number\) => setPreview\(clampReading\(px, ceiling\)\)/.test(source),
    'the preview must be clamped the same way the committed width is')
  assert.ok(source.includes('Conversation width: drag or use arrow keys to resize'), 'F3\'s label')
  assert.ok(/Conversation \$\{px\} px; working area \$\{/.test(source), 'F3\'s announcement')
})

test("Fluid's own gutter stylesheet is not what Quiet restyles", () => {
  assert.ok(!/qw-|qc-/.test(BOUNDARIES_CSS),
    'boundaries.css carries a Quiet selector: it must stay Fluid\'s and unmodified')
  assert.ok(/\.qw-room > \.fx-gutter \{/.test(ROOM_CSS),
    'Quiet\'s own gutter rule belongs in room.css (F3)')
})

/* -- the stylesheets' own share of the claims ------------------------------ */

test('one shared column template still runs through header, heading and work', () => {
  assert.ok(/--qc-columns: var\(--qc-nav\) minmax\(0, var\(--qc-measure\)\) var\(--qc-rail\);/.test(LAYOUT_CSS),
    'the shared template is not the one round four drew')
  assert.ok(/\.qc-global, \.qc-heading \{/.test(LAYOUT_CSS))
  assert.ok(/grid-template-columns: var\(--qc-columns\);/.test(LAYOUT_CSS), 'the header rows use it')
  assert.ok(/\.qw-room \{[\s\S]*?grid-template-columns: var\(--qc-columns\);/.test(ROOM_CSS),
    'the work row must use the SAME template, or the reading column stops at the header')
  /* AND THE HEADING GOES WITH ITS COLUMN. Expanded, the reading is the room's
     FIRST column, so the heading's own first track is the one its block sits
     in -- keyed off the room it is the previous sibling of, because that is
     the only thing in the document that knows which room is drawn. */
  assert.ok(/\.qc-heading:has\(\+ \.qw-room\[data-mode='panes'\]\)/.test(LAYOUT_CSS),
    'the heading does not follow the expanded room')
  assert.ok(/\.qc-heading:has\(\+ \.qw-room\[data-mode='board'\]\)/.test(LAYOUT_CSS))
  assert.ok(/\.qc-heading:has\(\+ \.qw-room\[data-one\]\) \{ grid-template-columns: minmax\(0, 1fr\); \}/
    .test(LAYOUT_CSS), 'one surface at a time gives the heading the whole width too')
  assert.ok(/grid-template-columns: minmax\(0, var\(--qc-measure\)\) minmax\(0, 1fr\);/.test(LAYOUT_CSS),
    "the expanded heading keeps Quiet's measure")
  assert.ok(/\.qc-heading:has\(\+ \.qw-room\[data-one\]\) > div \{ grid-column: 1; \}/.test(LAYOUT_CSS),
    'the heading block must be in the reading\'s own column')
  assert.ok(/--qc-measure: 760px;/.test(LAYOUT_CSS), "Single chat's measure is unchanged")
  assert.ok(/--qc-nav: minmax\(0, 300px\);/.test(LAYOUT_CSS), "Single chat's tracks are unchanged")
  assert.ok(/--qc-rail: minmax\(0, 340px\);/.test(LAYOUT_CSS))
})

test('the slots are placed, never reparented: the containers carry no content box', () => {
  assert.ok(/\.qc-work \{ display: contents; \}/.test(LAYOUT_CSS),
    'the work row keeps its class and lets the room place its children')
  assert.ok(/\.qw-room > \.qw-conversation \{ display: contents; \}/.test(ROOM_CSS))
  for (const slot of ['qw-tools', 'qw-conversation', 'qw-working', 'qw-page-controls'])
    assert.ok(ROOM_CSS.includes(slot), `room.css does not place the ${slot} slot`)
})

test('expanded, the work area is on the right and the tools immediately left of it', () => {
  const expanded = ROOM_CSS.slice(ROOM_CSS.indexOf("[data-mode='panes'],"))
  assert.ok(/\.qc-reading \{ grid-column: 1;/.test(expanded), 'the conversation does not slide left')
  assert.ok(/> \.fx-gutter \{ grid-column: 2;/.test(expanded), 'the separator is not between them')
  assert.ok(/> \.qw-tools \{ grid-column: 3;/.test(expanded), 'the tools are not left of the work area')
  assert.ok(/\.qc-margin \{ grid-column: 3;/.test(expanded), 'the contextual readings leave the tools column')
  assert.ok(/> \.qw-working \{ grid-column: 4;/.test(expanded), 'the work area is not on the right')
  assert.ok(/minmax\(240px, var\(--qw-tools-max\)\)/.test(expanded), 'the tools column may fall under 240px')
  assert.ok(/minmax\(300px, 1fr\)/.test(expanded), 'the work area may fall under 300px')
})

test('the room measures itself by a rule that no reflow beside it can move', () => {
  const source = readFileSync(new URL('../src/quiet/workspace/WorkspaceRoom.tsx', import.meta.url), 'utf8')
  assert.ok(/className="qw-measure" aria-hidden="true"/.test(source),
    'the measuring rule must carry no accessible name of its own')
  assert.ok(/watch\.observe\(node, \{ box: 'content-box' \}\)/.test(source))
  assert.ok(/if \(!box \|\| box\.width === last\) return/.test(source),
    'a height that moved must report nothing: the room is as wide as it was')
  assert.ok(/requestAnimationFrame\(\(\) => set\(width\)\)/.test(source),
    'the width must be applied outside the resize notification')
  const rule = ROOM_CSS.slice(ROOM_CSS.indexOf('.qw-room > .qw-measure'))
  assert.ok(/grid-column: 1 \/ -1;/.test(rule.slice(0, 200)), "the rule spans the room's whole content box")
  assert.ok(/height: 0;/.test(rule.slice(0, 200)), 'the rule must have no height to change')
  assert.ok(/\.qw-room\[data-one\] > \.qw-measure \{[^}]*margin-bottom: -20px/.test(ROOM_CSS),
    'the rule must not add a gap to the one-surface stack')
})

test('a pinned toolbar is reserved in an expanded room and nowhere else', () => {
  assert.ok(/\.qc\[data-pin-toolbar='true'\] \.qw-room\[data-mode='panes'\]/.test(ROOM_CSS))
  assert.ok(/padding-right: calc\(var\(--qc-gutter\) \+ var\(--qw-toolbar\)\);/.test(ROOM_CSS))
  assert.ok(!/\.qc\[data-pin-toolbar='true'\] \.qw-room\[data-mode='single'\]/.test(ROOM_CSS),
    "Single chat's reading column must keep its alignment with the header")
})

test('a parked surface is gone from sight and from the focus order', () => {
  assert.ok(/\.qw-room \[hidden\] \{\n  display: none;\n\}/.test(ROOM_CSS),
    'the hidden rule must survive, and be last so it wins')
  assert.ok(ROOM_CSS.lastIndexOf('[hidden]') > ROOM_CSS.indexOf("[data-mode='panes'],"),
    'the hidden rule must come after every placement it has to beat')
  const parked = ROOM_CSS.slice(ROOM_CSS.indexOf("[data-showing='tools']"))
  assert.ok(/display: none;/.test(parked.slice(0, 400)), 'a parked surface is not display:none')
})

test('F25 is reserved: the clipping and stacking O draws inside are untouched', () => {
  assert.ok(/overflow-x: clip;/.test(LAYOUT_CSS), "`.qc`'s horizontal clip is reserved for O")
  assert.ok(/isolation: isolate;/.test(LAYOUT_CSS), "`.qc`'s isolation is reserved for O")
  assert.ok(/z-index: 4;/.test(LAYOUT_CSS), "the dock's z-index 4 is reserved for O")
  const stage = ROOM_CSS.slice(ROOM_CSS.indexOf("O'S RESERVED SEAM"))
  assert.ok(/z-index: 1;/.test(stage) && /isolation: isolate;/.test(stage),
    'the working stage needs its own stacking context, below the dock')
  assert.ok(/overflow: visible;/.test(stage), 'the stage must not clip a float\'s own orbit')
  assert.ok(!/contain:/.test(stage) && !/clip-path:/.test(stage),
    'containment or a clip path here would cut O\'s floats')
})

/* -- the gap this package also closed (ent-55cfd945a1b6) ------------------- */

test('the tools slot is rendered BEFORE the conversation slot', () => {
  const source = readFileSync(new URL('../src/quiet/workspace/WorkspaceRoom.tsx', import.meta.url), 'utf8')
  const tools = source.indexOf('data-slot="tools"')
  const conversation = source.indexOf('data-slot="conversation"')
  assert.ok(tools > 0 && conversation > 0, 'both slots must be rendered')
  assert.ok(tools < conversation,
    'the tools must precede the conversation, or the frozen ARIA baseline reorders')
  // All four, unconditionally.
  for (const slot of ['tools', 'conversation', 'working', 'pageControls'])
    assert.ok(source.includes(`data-slot="${slot}"`), `the ${slot} slot is not mounted`)
})

test('the shell passes both tools into the tools slot, each exactly once', () => {
  const slot = QUIET_CHAT.slice(QUIET_CHAT.indexOf('tools={<>'), QUIET_CHAT.indexOf('conversation={<div'))
  assert.ok(/<RailTools rail=\{rail\} choose=\{setRail\} \/>/.test(slot),
    'RailTools is not in the tools slot')
  assert.ok(/<div className="qc-cell-nav"><ConversationNav /.test(slot),
    'the conversation navigation cell is not in the tools slot')
  assert.ok(/<RailTools[\s\S]*<div className="qc-cell-nav">/.test(slot),
    'the reading switches must precede the conversation list, as the baseline holds them')
  assert.equal(QUIET_CHAT.match(/<RailTools /g).length, 1, 'RailTools is mounted more than once')
  assert.equal(QUIET_CHAT.match(/<ConversationNav /g).length, 1, 'ConversationNav is mounted more than once')
  // Neither is conditional: no `&&` or `?` guard on their own line.
  for (const line of slot.split('\n').filter((l) => /RailTools|ConversationNav/.test(l)))
    assert.ok(!/&&|\?/.test(line), `a conditional mount: ${line.trim()}`)
})

test('the mode control is the room\'s own, with F15\'s exact three choices', () => {
  const source = readFileSync(new URL('../src/quiet/workspace/WorkspaceRoom.tsx', import.meta.url), 'utf8')
  assert.ok(/role="group" aria-label="Workspace layout"/.test(source))
  assert.ok(/type="radio"/.test(source), 'the modes are radios')
  const names = [...source.matchAll(/name: '([^']+)' \}/g)].map((m) => m[1])
  assert.deepEqual(names, ['Single chat', 'Chat and panes', 'Workspace board'])
  assert.ok(/id: 'single', name: 'Single chat'/.test(source), 'Single chat must be the first mode')
})

test('the narrow choice is drawing state, and the saved room is mode and width alone', () => {
  const source = readFileSync(new URL('../src/quiet/workspace/WorkspaceRoom.tsx', import.meta.url), 'utf8')
  assert.ok(/useState<Showing>\('conversation'\)/.test(source),
    'which surface a narrow room shows must be local state (F9)')
  for (const written of source.match(/onRoom\(\{[^}]*\}/g) ?? [])
    assert.ok(!/showing|surface/.test(written), `the bookmark is written drawing state: ${written}`)
  assert.ok(/Return to conversation</.test(source), 'the named return control is missing')
})
