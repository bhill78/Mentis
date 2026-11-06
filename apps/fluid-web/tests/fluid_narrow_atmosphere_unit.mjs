/* The narrow (phone/tablet) atmosphere treatments used to be keyed on
 * `.workspace.phone` / `.workspace.tablet`, which no live component in
 * either Fluid or /quiet ever renders (ent-b965c587db4a): every one of
 * those rules was dead, including Hail Mary's tall picture and every
 * reading veil meant for a narrow canvas. This checks the fix directly on
 * the two files it touches: atmosphere.css now reaches narrow viewports
 * through a plain `max-width` media query, with no component needing to
 * write any class or attribute for this; picture/store.ts's cssFor()
 * (a custom look's own CSS) uses the same mechanism, "the same selectors
 * atmosphere.css uses" as its own comment promises.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const here = fileURLToPath(new URL('.', import.meta.url))
const css = readFileSync(here + '../src/atmosphere.css', 'utf8')

let checks = 0
const ok = (cond, what) => { assert.ok(cond, what); checks++ }

// -- the rewritten section: the dead class selectors are gone ---------------
//
// Scoped to the section this package rewrote (the per-atmosphere narrow
// treatments), not the whole file: atmosphere.css:279's unrelated
// `.workspace.phone .rail` rule is the same dead class, but it styles `.rail`
// (a legacy, non-atmosphere-specific class this package does not own an
// equivalent for in either app) and is reported as discovered work rather
// than fixed here.

const cssNoComments = css.replace(/\/\*[\s\S]*?\*\//g, '')
const sectionStart = css.indexOf('NARROW VIEWPORTS: PHONE AND TABLET')
const sectionEnd = css.indexOf('Nothing here animates, and nothing should start to')
ok(sectionStart > 0 && sectionEnd > sectionStart, 'the narrow-viewport section exists')
const section = css.slice(sectionStart, sectionEnd)
const narrowStart = cssNoComments.indexOf('@media (max-width: 1024px)')
const sectionNoComments = cssNoComments.slice(
  narrowStart,
  cssNoComments.indexOf('@media (prefers-reduced-motion: reduce)', narrowStart),
)
ok(!sectionNoComments.includes('.workspace'), 'no .workspace class selector remains in the rewritten section')
ok(!/\.phone\b/.test(sectionNoComments) && !/\.tablet\b/.test(sectionNoComments),
  'no .phone / .tablet class selector remains there')

// -- the narrow block lives behind a plain viewport media query ------------

const narrowBlock = section.match(/@media \(max-width: 1024px\) \{([\s\S]*?)\n\}\n@media \(max-width: 760px\)/)
ok(narrowBlock, 'a @media (max-width: 1024px) block holds the phone+tablet atmospheres')
const inNarrow = narrowBlock[1]

for (const id of ['tidewater', 'nightfall', 'shoal', 'downland', 'monolith', 'hailmary']) {
  ok(new RegExp(`:root\\[data-atmosphere='${id}'\\]\\s*\\{`).test(inNarrow),
    `${id}'s narrow treatment is inside the 1024px block`)
}

// Hail Mary's narrow picture and veil survive the rewrite unchanged.
ok(inNarrow.includes("url('/atmospheres/hailmary-tall.jpg')"), "hailmary's tall picture is still named")
ok(inNarrow.includes('rgba(16, 12, 12, 0.82)'), "hailmary's narrow reading veil keeps its value")

// Mist is phone-only (never had a tablet rule) and sits at the tighter breakpoint.
const mistBlock = css.match(/@media \(max-width: 760px\) \{([\s\S]*?)\n\}/)
ok(mistBlock, 'a @media (max-width: 760px) block holds Mist alone')
ok(/:root\[data-atmosphere='mist'\]\s*\{/.test(mistBlock[1]), "mist's narrow treatment is inside the 760px block")
ok(!inNarrow.includes("data-atmosphere='mist'"), 'mist is not duplicated into the 1024px block')

// The wide (unguarded) rule for each narrow atmosphere still exists outside
// any media query -- the narrow rewrite only changed how the narrow variant
// is reached, not Fluid's wide-screen appearance.
const beforeNarrowBlock = css.slice(0, css.indexOf('@media (max-width: 1024px)'))
for (const id of ['tidewater', 'nightfall', 'shoal', 'downland', 'monolith', 'hailmary']) {
  ok(new RegExp(`:root\\[data-atmosphere='${id}'\\]\\s*\\{`).test(beforeNarrowBlock),
    `${id}'s wide (unguarded) rule is untouched, outside the narrow media query`)
}

// -- picture/store.ts: cssFor() uses the same mechanism ---------------------

const { registerHooks } = await import('node:module')
const { existsSync } = await import('node:fs')
const ts = (await import('../node_modules/typescript/lib/typescript.js')).default
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
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
      }).outputText,
    }
    return next(url, context)
  },
})
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
const { cssFor } = await import('../src/picture/store.ts')

const theme = {
  scheme: 'dark',
  backdrop: 'picture',
  wide: { '--canvas-image': "url('wide.jpg')" },
  tall: { '--canvas-image': "url('tall.jpg')" },
  swatch: ['#000', '#000', '#000'],
  measured: { wide: 5, tall: 5, rail: 5 },
  floor: 0,
  veil: 0,
}
const out = cssFor('look-abc123def456', theme)

ok(!out.includes('.workspace'), "cssFor()'s output carries no .workspace class selector")
ok(out.includes("@media (max-width: 1024px) {\n:root[data-atmosphere='look-abc123def456'] {"),
  "cssFor() wraps the tall block in the same 1024px media query atmosphere.css uses")
ok(out.includes("url('wide.jpg')") && !out.match(/@media[\s\S]*wide\.jpg/),
  "the wide block sits outside the media query")
ok(!!out.match(/@media[\s\S]*tall\.jpg/), 'the tall block sits inside the media query')

console.log(`fluid narrow atmosphere: ${checks} checks passed`)
