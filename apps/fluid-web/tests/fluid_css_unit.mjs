/* Fluid ships only what it renders: every class selector in a stylesheet the
 * app imports must be constructible from src/**.{ts,tsx}. A class counts as
 * used when its full name appears as a word in any source (a className
 * string, a template, a selector literal), or when it starts with a prefix a
 * source composes ('fw-run-' + state, `rb-matrix-${kind}` keep .fw-run-* and
 * .rb-matrix-*). Element, attribute, :root and custom-property rules carry no
 * class selectors and are out of scope here.
 *
 * The ALLOW list names the classes sources build in ways this scan cannot
 * see; each entry says why. */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const here = fileURLToPath(new URL('.', import.meta.url))
const src = here + '../src/'

const ALLOW = new Map([
  // decide.tsx composes 'rb-cmp-mark rb-cmp-m' + 'p' | 'm' | 'q' | 'n': a
  // class prefix with no trailing dash, which the prefix rule cannot see.
  ['rb-cmp-mp', "decide.tsx: 'rb-cmp-m' + 'p'"],
  ['rb-cmp-mm', "decide.tsx: 'rb-cmp-m' + 'm'"],
  ['rb-cmp-mq', "decide.tsx: 'rb-cmp-m' + 'q'"],
  ['rb-cmp-mn', "decide.tsx: 'rb-cmp-m' + 'n'"],
])

const walk = (dir, out = []) => {
  for (const name of readdirSync(dir)) {
    const path = dir + name
    if (statSync(path).isDirectory()) walk(path + '/', out)
    else out.push(path)
  }
  return out
}

/* -- what the sources can build ------------------------------------------- */

const sources = walk(src).filter((f) => /\.tsx?$/.test(f))
const text = sources.map((f) => readFileSync(f, 'utf8')).join('\n')
const words = new Set(text.match(/[A-Za-z_][\w-]*/g) ?? [])
const prefixes = new Set()
/* 'a b fw-run-' + state and `pz-panel-${panel}`: a dashed word ending in '-'
 * just before a closing quote that is concatenated, or just before '${'. */
for (const m of text.matchAll(/([A-Za-z][\w]*(?:-[\w]+)*-)['"`]\s*\+/g)) prefixes.add(m[1])
for (const m of text.matchAll(/([A-Za-z][\w]*(?:-[\w]+)*-)\$\{/g)) prefixes.add(m[1])

const used = (name) =>
  ALLOW.has(name) || words.has(name) || [...prefixes].some((p) => name.startsWith(p))

/* -- the stylesheets Fluid imports ----------------------------------------- */

const files = walk(src)
const stylesheets = files.filter((f) => f.endsWith('.css')).filter((f) => {
  const dir = f.slice(0, f.lastIndexOf('/') + 1)
  const base = f.slice(dir.length)
  return sources.some((s) => {
    const body = readFileSync(s, 'utf8')
    if (!body.includes(base)) return false
    const from = s.slice(0, s.lastIndexOf('/') + 1)
    const spec = rel(from, dir) + base
    return body.includes("'" + spec + "'") || body.includes('"' + spec + '"')
  })
})

function rel(fromDir, toDir) {
  const a = fromDir.split('/').filter(Boolean)
  const b = toDir.split('/').filter(Boolean)
  while (a.length && b.length && a[0] === b[0]) { a.shift(); b.shift() }
  const down = b.join('/')
  if (!a.length) return './' + (down ? down + '/' : '')
  return '../'.repeat(a.length) + (down ? down + '/' : '')
}

/* Parse a stylesheet's selector preludes, skipping @keyframes bodies and
 * declaration blocks; return every class name its selectors use. */
function classesIn(css) {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const classes = []
  const stack = []
  let prelude = ''
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i]
    if (ch === '"' || ch === "'") {
      for (i++; i < clean.length && clean[i] !== ch; i++) if (clean[i] === '\\') i++
      continue
    }
    if (ch === '{') {
      const head = prelude.trim()
      prelude = ''
      const skip = stack[stack.length - 1] === 'skip' || /^@(-\w+-)?keyframes\b/.test(head) || /^@(font-face|property|page|counter-style|viewport)\b/.test(head)
      if (!skip && head && !head.startsWith('@')) {
        for (const sel of splitSelectors(head))
          for (const m of sel.replace(/\[[^\]]*\]/g, ' ').matchAll(/\.([A-Za-z_][\w-]*)/g)) classes.push(m[1])
      }
      stack.push(skip ? 'skip' : 'open')
    } else if (ch === '}') {
      stack.pop()
      prelude = ''
    } else if (ch === ';') prelude = ''
    else prelude += ch
  }
  return classes
}

function splitSelectors(list) {
  const out = []
  let depth = 0, start = 0
  for (let i = 0; i < list.length; i++) {
    const ch = list[i]
    if (ch === '(' || ch === '[') depth++
    else if (ch === ')' || ch === ']') depth--
    else if (ch === ',' && depth === 0) { out.push(list.slice(start, i)); start = i + 1 }
  }
  out.push(list.slice(start))
  return out
}

/* -- the check -------------------------------------------------------------- */

const dead = new Map()
for (const file of stylesheets) {
  for (const name of new Set(classesIn(readFileSync(file, 'utf8'))))
    if (!used(name)) {
      if (!dead.has(file)) dead.set(file, new Set())
      dead.get(file).add(name)
    }
}

for (const [file, names] of dead)
  console.log(file.slice(src.length) + '\n  ' + [...names].sort().join(', '))
assert.equal(
  [...dead.values()].reduce((n, s) => n + s.size, 0),
  0,
  'class selectors no src/**.{ts,tsx} can build (see list above)',
)
console.log('ok fluid_css: ' + stylesheets.length + ' stylesheets, every class selector reachable from src')
