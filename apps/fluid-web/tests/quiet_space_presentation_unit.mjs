/* ------------------------------------------------------------------------ *
 * HOW THE 3D BRAIN IS OFFERED AND HOW IT IS DRAWN -- the owner's revision of
 * 2026-11-18 (ent-46aecf919fe8), driven as behaviour rather than matched as
 * source text.
 *
 * The owner rejected the TEST candidate on three things:
 *   "A 3D icon should be near the manage sources and knowledge for the 3d
 *    brain."                                         -> the icon, below
 *   "The brain should always open consistently as well. Not sometimes in a
 *    different column workspace and then sometimes full screen."
 *                            -> tests/quiet_space_nav_unit.ts, "ONE PLACE"
 *   "It should work with the full screen and use the same canvas background
 *    the user is on, not the document vewer like overlay."
 *                                                     -> the stage, below
 *
 * The REAL components are mounted over the small hook runtime the repository
 * already has (space_react_stub.mjs), and what they render is read from the
 * tree. Nothing here is a regular expression over a component's characters --
 * except where the subject IS a stylesheet, which is said where it happens.
 *
 * WHAT IT DOES NOT CLAIM: anything about painted pixels, real layout or a real
 * browser. The graph module itself is deferred and stands unloaded here: what
 * it draws is its own tests' business (space_travel_unit.mjs), and this is
 * about the frame around it.
 * ------------------------------------------------------------------------ */

import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'

const stub = new URL('./space_react_stub.mjs', import.meta.url).href

registerHooks({
  resolve(specifier, context, next) {
    /* REACT IS THE ONLY THING STOOD IN FOR. Everything else is the real file. */
    if (specifier === 'react' || specifier === 'react/jsx-runtime') return { url: stub, shortCircuit: true }
    if (specifier.startsWith('.')) {
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url))
      return {
        format: 'module',
        shortCircuit: true,
        source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
          compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
        }).outputText,
      }
    return next(url, context)
  },
})

/* ---- the little of a browser these components actually touch ------------- */

let frames = []
globalThis.requestAnimationFrame = (fn) => { frames.push(fn); return frames.length }
globalThis.cancelAnimationFrame = () => {}
globalThis.document = {
  activeElement: null,
  addEventListener() {},
  removeEventListener() {},
  querySelector: () => null,
}
globalThis.window = {
  addEventListener() {},
  removeEventListener() {},
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (id) => clearTimeout(id),
  innerWidth: 1200,
  innerHeight: 900,
  /* `matchMedia` is deliberately absent: the Brain menu asks for it and must
     cope without one, which is also the path `clickOnly` takes. */
}

const R = await import('./space_react_stub.mjs')
const { jsx } = R
const { default: BrandMenu } = await import('../src/surfaces/BrandMenu.tsx')
const { default: Markers } = await import('../src/quiet2/Markers.tsx')
const { default: SpaceStage } = await import('../src/quiet2/space/SpaceStage.tsx')
const { BrainGlyph, SourcesGlyph, SpaceGlyph } = await import('../src/surfaces/PlaceIcons.tsx')

let checks = 0
const eq = (a, b, what) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a, what) => { assert.ok(a, what); checks++ }

/* ---- reading what was rendered ------------------------------------------ */

/** every node of the rendered tree, in order, as { type, props }. */
function nodes(from = R.rendering()) {
  const got = []
  const seek = (n) => {
    if (!n || typeof n !== 'object') return
    if (Array.isArray(n)) return n.forEach(seek)
    if (n.type !== undefined) got.push(n)
    seek(n.out)
  }
  seek(from)
  return got
}
const classesIn = (from) => nodes(from).map((n) => n.props?.className).filter((c) => typeof c === 'string')
/** the host element whose className holds `name`, with everything under it */
const byClass = (name, from) => nodes(from).find((n) => typeof n.props?.className === 'string'
  && n.props.className.split(/\s+/).includes(name))
const kids = (node) => nodes(node)

/* ======================================================================== *
 * 1. THE 3D BRAIN IS SEEN, NOT READ -- an icon, beside Manage Sources
 * ======================================================================== *
 * THE DEFECT: in the Brain menu the 3D Brain was a row of plain text after
 * Manage Sources, with no glyph at all -- the same weight as the sentence
 * under it, and nothing to recognise the place by. */
{
  let opened = 0
  R.render(jsx(BrandMenu, {
    name: 'a brain', atBrain: false, clickOnly: true,
    onBrainHome: () => {}, onManage: () => {},
    onSources: () => {}, atSources: false,
    onSpace: () => { opened += 1 }, atSpace: false,
  }))
  /* the menu opens on a press, as it does for a reader */
  const opener = byClass('brand-menu-open')
  ok(opener, 'the Brain menu has its opener')
  R.act(() => opener.props.onClick({}))

  const rows = nodes().filter((n) => n.props?.['data-row'])
  eq(rows.map((r) => r.props['data-row']), ['home', 'manage', 'sources', 'space', 'change'],
    'the 3D Brain sits with Manage Sources in the Brain-level group, directly after it')

  const iconOf = (key) => {
    const row = rows.find((r) => r.props['data-row'] === key)
    const slot = byClass('brand-row-icon', row)
    return slot ? kids(slot).find((n) => typeof n.type === 'function') : null
  }
  /* THE OWNER'S OWN WORDS: a 3D icon, near the Manage Sources one */
  eq(iconOf('space')?.type, SpaceGlyph, 'the 3D Brain row carries the 3D glyph')
  eq(iconOf('sources')?.type, SourcesGlyph, 'Manage Sources carries the sources store it is known by')
  eq(iconOf('home')?.type, BrainGlyph, 'and the Brain its own, so the three read as one group')

  /* IT IS AN ICON IN FACT: a drawn shape, not a character or a placeholder */
  R.unmount()
  R.render(jsx(SpaceGlyph, { size: 18 }))
  const svg = nodes().find((n) => n.type === 'svg')
  ok(svg, 'the 3D glyph draws an svg')
  eq(nodes().filter((n) => n.type === 'path').length, 3,
    'a cube seen in space: its outline and the three edges meeting at the near corner')
  eq(svg.props['aria-hidden'], true, 'and it is decoration beside a control that already has a name')
  R.unmount()

  /* AND THE ROW STILL DOES WHAT IT DID: an icon was added, nothing replaced */
  R.render(jsx(BrandMenu, { name: 'a brain', atBrain: false, clickOnly: true, onSources: () => {}, onSpace: () => { opened += 1 } }))
  R.act(() => byClass('brand-menu-open').props.onClick({}))
  const space = nodes().find((n) => n.props?.['data-row'] === 'space')
  R.act(() => space.props.onClick({}))
  eq(opened, 1, 'pressing the 3D Brain row opens the 3D Brain')
  R.unmount()
}

/* THE SAME GLYPH WHERE MANAGE SOURCES IS ALSO OFFERED BY ONE: the rail that
   carries Brain and Sources carries the 3D Brain too, in the same group. */
{
  let opened = 0
  R.render(jsx(Markers, {
    label: 'Conversations', items: [], current: null, side: 'left', onPick: () => {},
    onBrain: () => {}, brainLabel: 'Brain', onSources: () => {},
    onSpace: () => { opened += 1 }, spaceOn: false,
  }))
  const places = byClass('q2-rail-places')
  ok(places, 'the rail keeps its group of Brain-level places')
  const buttons = kids(places).filter((n) => n.type === 'button')
  eq(buttons.map((b) => b.props['aria-label']), ['Brain', 'Sources', '3D Brain'],
    'and the 3D Brain stands in it, beside Sources')
  eq(kids(buttons[2]).find((n) => typeof n.type === 'function')?.type, SpaceGlyph,
    'by the same glyph the Brain menu shows: one shape, one place')
  R.act(() => buttons[2].props.onClick({}))
  eq(opened, 1, 'and it opens the 3D Brain')
  R.unmount()
}

/* ======================================================================== *
 * 2. IT IS DRAWN ON THE CANVAS, NOT IN THE DOCUMENT VIEWER
 * ======================================================================== *
 * THE DEFECT: the graph was mounted inside the generic viewer frame (q2v,
 * q2v-max) in the maximised layer that frosts the page away behind a rounded,
 * shadowed sheet -- the document viewer's overlay, around a place. */
{
  let closed = 0
  R.render(jsx(SpaceStage, { sessionId: 'sp7', onClose: () => { closed += 1 }, openedBy: null }))
  const stage = byClass('q2-space-stage')
  ok(stage, 'the 3D Brain has a stage of its own')
  eq(stage.props.role, 'dialog', 'focus still belongs in it while the page behind is inert')
  eq(String(stage.props['aria-modal']), 'true', 'as it did before: that is behaviour, not chrome')
  eq(stage.props['aria-label'], '3D Brain', 'and it is named for what it is')

  /* NOT THE DOCUMENT VIEWER: none of the frame's chrome is anywhere in it */
  const seen = classesIn()
  eq(seen.filter((c) => /\bq2v\b|\bq2v-|q2-max-layer/.test(c)), [],
    'no viewer frame, no maximised document layer, no header bar around it')

  /* THE EXISTING RENDERER, UNCHANGED, hosted full screen: the host is deferred
     (its module is large) and is handed the session and the placement. */
  const host = nodes().find((n) => typeof n.type === 'function' && n.type.loads)
  ok(host, 'the graph host is mounted, deferred as its own module')
  eq(host.props.sessionId, 'sp7', 'bound to the session the page holds, never a new graph')
  eq(host.props.placement, 'max', 'and hosted full screen')

  /* ONE CONTROL OVER THE FIELD: the way out. The graph draws its own title and
     tools; nothing of them is duplicated here. */
  const buttons = nodes().filter((n) => n.type === 'button')
  eq(buttons.length, 1, 'one control over the field')
  eq(buttons[0].props['aria-label'], 'Close the 3D Brain', 'and it is the way out')
  R.act(() => buttons[0].props.onClick({}))
  eq(closed, 1, 'which closes the 3D Brain through the page’s own one release path')
  let prevented = 0
  R.act(() => stage.props.onKeyDown({ key: 'Escape', defaultPrevented: false, preventDefault: () => { prevented += 1 } }))
  eq(closed, 2, 'Escape leaves it too')
  eq(prevented, 1, 'taking the key rather than letting it fall through')
  R.unmount()
}

/* THE GROUND IT IS DRAWN ON. The subject here IS a stylesheet, so this reads
   one -- there is no other way to state a background without a browser, and
   the browser check belongs to whoever verifies the candidate. */
{
  const css = readFileSync(new URL('../src/quiet2/space/space-stage.css', import.meta.url), 'utf8')
  const rule = css.slice(css.indexOf('.q2-space-stage {'), css.indexOf('}', css.indexOf('.q2-space-stage {')))
  ok(/background:\s*var\(--canvas\)/.test(rule),
    'the stage is the same canvas the reader is already on')
  ok(!/backdrop-filter|border-radius|box-shadow|border:/.test(rule),
    'and not a frosted, rounded, shadowed sheet laid over the page')
  const viewer = readFileSync(new URL('../src/quiet2/viewer/viewer.css', import.meta.url), 'utf8')
  ok(/\.q2-max-layer\s*{[^}]*backdrop-filter/.test(viewer),
    'the document viewer’s own layer still frosts the page, for documents')
}

console.log(`quiet_space_presentation_unit: ${checks} checks passed`)
