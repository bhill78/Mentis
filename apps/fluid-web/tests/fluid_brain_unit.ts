import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { SPACE_HASH, atSpace } from '../src/surfaces/space/navigation'
import { sourcesPath } from '../src/surfaces/sources/navigation'
import { goHome, kindWord } from '../src/fluid/brain/address'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const here = fileURLToPath(new URL('.', import.meta.url))
const readSrc = (file: string) => readFileSync(here + '../src/' + file, 'utf8')

/* -- the address: Mark IV's, beside Manage Sources' ----------------------- */
eq(SPACE_HASH, '#/brain/space', 'the 3D Brain keeps Mark IV\'s address')
ok(atSpace('#/brain/space') && atSpace('#/brain/space/'), 'the 3D Brain is addressable')
ok(!atSpace('#/brain/sources') && !atSpace('') && !atSpace('#/brain'), 'another Brain surface is not the 3D Brain')
eq(sourcesPath(SPACE_HASH), null, 'the 3D Brain is not read as Manage Sources')

/* -- where a thing lives -------------------------------------------------- */
const went: string[] = []
const doors = { openPost: (c: string, p: string) => went.push(`post ${c} ${p}`), openConversation: (c: string) => went.push(`conv ${c}`) }
ok(goHome({ entry: 't1', kind: 'contribution', conversation: 'c1' }, doors), 'a Turn has a home')
ok(goHome({ entry: 'c2', kind: 'conversation', conversation: 'c2' }, doors), 'a Conversation is its own home')
ok(goHome({ entry: 'd1', kind: 'decision', conversation: 'c3' }, doors), 'a Decision lives in its Conversation')
ok(!goHome({ entry: 'p1', kind: 'participant', conversation: null }, doors), 'what the record places nowhere goes nowhere')
eq(went, ['post c1 t1', 'conv c2', 'conv c3'], 'each goes where it lives')
eq(kindWord({ kind: 'contribution' }), 'turn', 'a contribution is called a turn')
eq(kindWord({ kind: 'decision' }), 'decision', 'any other kind keeps its own name')

/* -- the wiring: reached from the Brain menu, loaded only when gone to ---- */
const shell = readSrc('fluid/Shell.tsx')
ok(/lazy\(\(\) => import\('\.\/brain\/BrainPlace'\)\)/.test(shell), 'the 3D Brain is loaded lazily, outside the main bundle')
ok(!/^import .*surfaces\/space\/SpaceSurface/m.test(shell), 'the Shell never imports the drawing itself')
ok(/onSpace=\{openSpace\}/.test(shell), 'the Shell hands the Brain menu its door')
ok(/atSpace=\{view === 'space'\}/.test(readSrc('fluid/frame/TopBar.tsx')), 'the Brain menu says when you are in the 3D Brain')
ok(/onSpace=\{onSpace\}/.test(readSrc('fluid/frame/BarControls.tsx')), 'the Brand passes the door to the Brain menu')

console.log(`brain: ${checks} checks passed`)
