/* Home's section registry (sections/), held in Node against the registered
   sections themselves (no server, no browser, no build):

     * every stored `show` word Home accepted before the registry (the old
       COLLECTIONS list) is registered, under the same word and the same
       display name, offered in the same order;
     * the flags Home draws by stand: the conversation docks (and has no
       body -- Home draws the column itself), kept holds kept items, and
       each collection has a body;
     * a section's option reader reads its zone's stored options as its body
       takes them (Work's tab as its state, the Briefing's period), defaults
       applied;
     * a section registered at runtime is offered by the picker's list
       (sections()) and found by Home's body lookup (sectionOf()) -- a new
       section without editing Home.

   Run by tests/run.mjs. */
import assert from 'node:assert/strict'
import { registerSection, sectionOf, sectionOptions, sections, type SectionDef } from '../src/fluid/sections'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (v: unknown, what: string) => { assert.ok(v, what); checks++ }

/* -- every word Home accepted before is registered --------------------------- */

/* The COLLECTIONS list Home.tsx carried before the registry: word and name,
   in the picker's order. */
const BEFORE: [string, string][] = [
  ['conversation', 'Conversation'],
  ['briefing', 'Daily Briefing'],
  ['work', 'Work'],
  ['needs-you', 'Needs you'],
  ['for-you', 'For you'],
  ['activity', 'Activity'],
  ['kept', 'Kept'],
]

eq(sections().map((s) => s.show), BEFORE.map(([show]) => show), 'the picker offers every word Home accepted, in the same order')
eq(sections().map((s) => s.name), BEFORE.map(([, name]) => name), 'under the same display names')
for (const [show, name] of BEFORE) eq(sectionOf(show)?.name, name, `Home's body lookup finds ${show} (${name})`)

eq(sectionOf('choose'), undefined, 'a zone still asking what to show names no section')
eq(sectionOf('stage'), undefined, 'nor does a word none names')

/* -- the flags Home draws by -------------------------------------------------- */

const byShow = Object.fromEntries(sections().map((s) => [s.show, s])) as Record<string, SectionDef>
eq(byShow['conversation'].conversation, true, 'the conversation docks')
eq(byShow['conversation'].body, undefined, 'and Home draws the column itself: no body')
eq(byShow['kept'].kept, true, 'kept holds kept items')
ok(byShow['kept'].body, 'kept has a body (what it keeps, drawn through present)')
for (const show of ['briefing', 'work', 'needs-you', 'for-you', 'activity']) {
  ok(byShow[show].body, `${show} has a body`)
  eq(byShow[show].conversation, undefined, `${show} does not dock`)
  eq(byShow[show].kept, undefined, `${show} keeps nothing`)
}

/* -- option readers: Work's tab, the Briefing's period ------------------------ */

const work = byShow['work']
eq(work.defaults, { tab: 'all' }, "Work's default tab is all")
eq(sectionOptions(work, {}), { state: 'all' }, 'a Work zone with nothing chosen shows all')
eq(sectionOptions(work, { tab: 'in-flight' }), { state: 'in-flight' }, "a Work zone's stored tab is its state")
eq(sectionOptions(work, { tab: 'in-flight', home: 2 }), { state: 'in-flight' }, "the zone's own marks (home: 2) are not the body's options")

const briefing = byShow['briefing']
eq(briefing.defaults, { period: null }, "the Briefing's default period is the period it is now")
eq(sectionOptions(briefing, {}), { period: null }, 'a Briefing zone with nothing chosen follows the clock')
eq(sectionOptions(briefing, { period: 'evening' }), { period: 'evening' }, 'a chosen period stands')

/* A section with defaults and no reader: the registry merges them. */
eq(sectionOptions({ show: 'x', name: 'X', defaults: { a: 1 } }, {}), { a: 1 }, 'defaults apply when nothing was chosen')
eq(sectionOptions({ show: 'x', name: 'X', defaults: { a: 1 } }, { a: 2, b: 3 }), { a: 2, b: 3 }, 'what was chosen stands over the defaults')
eq(sectionOptions({ show: 'x', name: 'X' }, { a: 2 }), { a: 2 }, 'no defaults, no reader: the stored options as they are')

/* -- a section registered at runtime, without editing Home -------------------- */

const before = sections().length
const TestBody = () => null
registerSection({ show: 'test-thing', name: 'Test thing', body: TestBody })
eq(sections().length, before + 1, 'the registry took the new section')
eq(sections()[sections().length - 1].show, 'test-thing', 'the picker offers it (after the built-ins)')
eq(sectionOf('test-thing'), { show: 'test-thing', name: 'Test thing', body: TestBody }, "Home's body lookup finds it")
ok(sectionOf('test-thing')?.body, 'and it has a body to draw')

/* Re-registering a word replaces it in place: one entry, where it was. */
registerSection({ show: 'test-thing', name: 'Test thing, again' })
eq(sections().length, before + 1, 'registering the same word again adds nothing')
eq(sections().findIndex((s) => s.show === 'test-thing'), before, 'nor moves it')
eq(sectionOf('test-thing')?.name, 'Test thing, again', 'the new registration stands')

console.log(`fluid sections: ${checks} checks passed`)
