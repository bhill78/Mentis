/* FLUID'S MANAGE SOURCES PAGE KEEPS ITS WIDTH, WHATEVER ORDER THE BUILD LOADS
 * ITS STYLESHEETS IN.
 *
 * The page is `<main class="fx-main fx-sources-main">` (fluid/Shell.tsx). The
 * stage rule `.fx-main { display: flex }` lives in fluid/frame/frame.css; the
 * page's own `display: block` lives in surfaces/sources/sources.css. Those
 * two files are built into DIFFERENT stylesheet chunks (sources.css is shared
 * with Quiet Chat through the reference chips), and since Fluid became a
 * lazily loaded entry the chunk holding sources.css loads FIRST. With one
 * class each, the later `.fx-main` won and the page became a shrunken flex
 * child, 44px wide. So the page's rule must OUTWEIGH the stage rule by
 * specificity, never by position. This reads the sources; no build needed. */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const src = fileURLToPath(new URL('../src/', import.meta.url))
const css = (path) => readFileSync(src + path, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
/* every `selector { body }` of a stylesheet, at-rule wrappers flattened */
const rules = (text) => [...text.matchAll(/([^{}]+)\{([^{}]*)\}/g)].flatMap((m) =>
  m[1].split(',').map((sel) => ({ sel: sel.trim(), body: m[2] })))
/* [ids, classes+attributes+pseudo-classes, elements] -- enough for these selectors */
const weight = (sel) => [
  (sel.match(/#[\w-]+/g) ?? []).length,
  (sel.match(/\.[\w-]+|\[[^\]]*\]|:(?!:)[\w-]+/g) ?? []).length,
  (sel.replace(/[.#:[][^\s>+~]*/g, ' ').match(/[a-z][\w-]*/gi) ?? []).length,
]
const heavier = (a, b) => { for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] > b[i]; return false }
const display = (body) => (body.match(/(?:^|;)\s*display\s*:\s*([\w-]+)/) ?? [])[1]
/* a selector whose SUBJECT (last compound) is the page's <main> itself */
const onMain = (sel) => { const last = sel.split(/[\s>+~]+/).pop(); return /\.fx-main\b/.test(last) || /\.fx-sources-main\b/.test(last) }

let checks = 0
const ok = (cond, what) => { assert.ok(cond, what); checks++ }

const shell = readFileSync(src + 'fluid/Shell.tsx', 'utf8')
ok(/className="fx-main fx-sources-main"/.test(shell), 'the Sources page is the stage element with both classes (fluid/Shell.tsx)')

const frame = rules(css('fluid/frame/frame.css')).concat(rules(css('fluid/fluid.css')), rules(css('fluid/conversation/conversation.css')))
const page = rules(css('surfaces/sources/sources.css'))

const blocks = page.filter((r) => onMain(r.sel) && /\.fx-sources-main\b/.test(r.sel) && display(r.body) === 'block')
ok(blocks.length === 1, 'sources.css says once that the Sources page is a block')
const mine = weight(blocks[0].sel)

/* every rule of Fluid's own sheets that sets `display` on the stage element
 * and could match the Sources page (no attribute/state the page never has
 * is assumed: all of them are counted) */
const stage = frame.filter((r) => onMain(r.sel) && display(r.body) !== undefined && r.sel.split(/[\s>+~]+/).length === 1)
ok(stage.some((r) => r.sel === '.fx-main' && display(r.body) === 'flex'), 'the stage is a flex row (frame.css) -- the rule the page must outweigh')
for (const r of stage)
  ok(heavier(mine, weight(r.sel)), `"${blocks[0].sel}" outweighs "${r.sel}" by specificity, so stylesheet order cannot undo it`)

ok(!page.some((r) => r.sel === '.fx-sources-main' && display(r.body) !== undefined),
  'no single-class `.fx-sources-main { display }` is left to depend on chunk order')

console.log(`fluid sources layout unit: ok (${checks} checks)`)
