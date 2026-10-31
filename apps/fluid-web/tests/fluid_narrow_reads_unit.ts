/* Unit tests for stage 1c, the composer's narrow reads:
 * 1. the composer's people and Topics come from `?fields=`, never `?batch=0`
 * 2. a notification names somewhere else from a batch of names
 * 3. `@` beyond this conversation searches `/fluid/api/participants?q=`,
 *    keeping what each name declared runs its work
 * 4. the `/` Workflows read is one ask while one is out, and waits a pause;
 *    the Use... panel's search waits a pause and reads the Kinds once
 * 5. the unused `useWorkingCount` is gone
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { addressablePath, personOfRow, ADDRESSABLE_LIMIT } from '../src/fluid/composer/useAddressable'
import { PAUSE_MS } from '../src/fluid/composer/useDebounced'
import { reread, heldWorkflows, WORKFLOWS_PATH } from '../src/fluid/composer/useWorkflows'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (p: string) => readFileSync(src + p, 'utf8')

// 1. the composer reads the people and Topics only
const composer = read('fluid/Composer.tsx')
const facts = read('fluid/conversation/facts.ts')
ok(composer.includes('usePeopleAndTopics(conversation ?? made.current'), 'the composer reads the narrow facts')
ok(!/\buseFacts\(/.test(composer), 'the composer never reads the full facts')
ok(!composer.includes('refreshFacts('), 'bringing somebody in or opening a Topic rereads the narrow facts')
ok(facts.includes("?fields=${PEOPLE_AND_TOPICS}"), 'the narrow read asks ?fields=')
ok(/PEOPLE_AND_TOPICS = 'name,participants,topics'/.test(facts), 'only the name, people and Topics')
const column = read('fluid/conversation/Column.tsx')
for (const fn of ['function WhoStrip(', 'function TopicsControl(', 'function TopicFlow(']) {
  const body = column.slice(column.indexOf(fn), column.indexOf(fn) + 300)
  ok(body.includes('usePeopleAndTopics(id)'), `${fn.slice(9, -1)} reads the people and Topics only`)
}
ok(read('fluid/conversation/Addressing.tsx').includes('usePeopleAndTopics(here ?? post.home, false)'), 'the addressing sheet reads the people only')

// 2. the toast names its place from a batch of names
const notes = read('fluid/frame/notifications.ts')
ok(!notes.includes('?batch=0'), 'no notification reads a whole conversation')
ok(notes.includes('/fluid/api/names?ids='), 'a notification asks for names by id')

// 3. `@` searches the names
eq(addressablePath('ali ce'), `/fluid/api/participants?q=ali%20ce&limit=${ADDRESSABLE_LIMIT}&runtimes=1`, 'searched, bounded, with runtimes')
eq(personOfRow({ id: 'ent-a', alias: '@Alice', default_runtime: 'claude', runtime_mode: 'default' }),
  { participant: 'ent-a', alias: '@Alice', about: undefined, default_runtime: 'claude', runtime_mode: 'default' }, 'a row read as a Person')
eq(personOfRow({ id: 'ent-b', alias: '@Bob' }).default_runtime, null, 'nothing declared reads as none')
ok(!composer.includes('usePeople('), "the composer's `@` no longer lists everybody")
ok(composer.includes("useAddressable(trigger && trigger.sigil === '@' ? trigger.query : '')"), '`@` searches what is typed')
ok(read('fluid/composer/useAddressable.ts').includes('useDebounced(q)'), '`@` asks once typing pauses')

// 4. the Workflows read, and the Use... panel
eq(PAUSE_MS, 250, 'the pause is the `#` palette\'s')
let asked: string[] = []
let release: (v: unknown) => void = () => {}
const get = (p: string) => { asked.push(p); return new Promise<never>((r) => { release = r as (v: unknown) => void }) }
const first = reread(get)
const second = reread(get)
eq(asked, [WORKFLOWS_PATH], 'a second ask while one is out asks nothing more')
ok(first === second, 'and is answered by the first')
release({ groups: { standing: [{ entry: 'ent-sw', kind: 'workflow', summary: 'Software change', governs: true }] } })
await first
eq(heldWorkflows(), [{ entry: 'ent-sw', name: 'Software change' }], 'what came back is held')
asked = []
const third = reread(get)
eq(asked, [WORKFLOWS_PATH], 'once answered, the next opening asks again')
release({}); await third
const hook = read('fluid/composer/useWorkflows.ts')
ok(hook.includes('setTimeout(() => { void reread() }, PAUSE_MS)'), 'the palette opening asks after a pause')
ok(hook.includes('return () => clearTimeout(t)'), 'and asks nothing if it closed within it')
const use = composer.slice(composer.indexOf('function UsePanel('))
ok(use.includes('const asked = useDebounced(q.trim())'), 'Use... searches once typing pauses')
ok(use.includes('}, [asked, kinds])') && !use.includes('}, [q])'), 'never on each keystroke')
ok(/useEffect\(\(\) => \{ setKinds\(getJson<[^\n]*'\/fluid\/api\/governance\/authoring'\)\) \}, \[\]\)/.test(use), 'the Kinds are read once per opening')

// 5. dead code
ok(!read('composer/execution.ts').includes('useWorkingCount'), 'useWorkingCount is gone')

console.log(`fluid narrow reads: ${checks} checks passed`)
