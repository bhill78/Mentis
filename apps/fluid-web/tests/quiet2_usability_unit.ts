/* QUIET CHAT MARK 2 USABILITY CORRECTIONS (2026-11-12), checked without a
 * browser:
 *
 *  5.4 a post's time: relative for the first twelve hours ("just now",
 *      "5m ago", "2h ago"), then a date and time (Today / Yesterday / a date,
 *      with the year once it is not this one); the exact moment in full; the
 *      shared clock runs only while something uses it; no reading time is
 *      drawn on a post.
 *  5.5 Quiet Chat's composer is collapsible, and collapsing never touches
 *      the draft (words, attachments, addressees and their settings).
 *  5.6 the newest activity: the post recorded last in the conversation,
 *      replies included (record number first, time without one), weighing
 *      the server's Latest read against the posts this page holds.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JUST_NOW, RELATIVE_FOR, TICK_MS, whenExact, whenSaid } from '../src/quiet2/when'
import { activityOf, newer, newestOf } from '../src/quiet2/latest'

const src = (p: string) => readFileSync(new URL('../src/' + p, import.meta.url), 'utf8')
const L = 'en-US'
/* a fixed local moment: 2026-11-12 15:30:00 local time */
const now = new Date(2026, 10, 12, 15, 30, 0).getTime() / 1000

/* -- 5.4 relative while recent ------------------------------------------- */
assert.equal(whenSaid(now, now, L), 'just now')
assert.equal(whenSaid(now - (JUST_NOW - 1), now, L), 'just now')
assert.equal(whenSaid(now + 90, now, L), 'just now', 'a clock a little ahead is still just now')
assert.equal(whenSaid(now - JUST_NOW, now, L), '1m ago', 'never 0m')
assert.equal(whenSaid(now - 5 * 60, now, L), '5m ago')
assert.equal(whenSaid(now - 59 * 60 - 59, now, L), '59m ago')
assert.equal(whenSaid(now - 3600, now, L), '1h ago')
assert.equal(whenSaid(now - 2 * 3600 - 59 * 60, now, L), '2h ago', 'whole hours, rounded down')
assert.equal(whenSaid(now - RELATIVE_FOR + 1, now, L), '11h ago')
assert.equal(RELATIVE_FOR, 12 * 3600)

/* -- then a date and time ------------------------------------------------- */
const at = (y: number, m: number, d: number, h: number, min: number) => new Date(y, m, d, h, min).getTime() / 1000
/* twelve hours or more, the same day */
const lateNow = at(2026, 10, 12, 23, 0)
assert.equal(whenSaid(at(2026, 10, 12, 9, 14), lateNow, L), 'Today, 9:14 AM')
assert.equal(whenSaid(at(2026, 10, 11, 9, 14), now, L), 'Yesterday, 9:14 AM')
assert.equal(whenSaid(at(2026, 10, 3, 14, 5), now, L), 'Nov 3, 2:05 PM')
assert.equal(whenSaid(at(2025, 11, 30, 8, 0), now, L), 'Dec 30, 2025, 8:00 AM', 'the year once it is not this one')
/* across midnight, still relative inside twelve hours */
assert.equal(whenSaid(at(2026, 10, 11, 23, 0), at(2026, 10, 12, 1, 30), L), '2h ago')
/* a time far in the future is a date, never "in …" */
assert.match(whenSaid(at(2026, 10, 20, 9, 0), now, L), /^Nov 20, 9:00 AM$/)

/* -- the exact moment ----------------------------------------------------- */
const exact = whenExact(at(2026, 10, 3, 14, 5), L)
assert.match(exact, /Tuesday, November 3, 2026/, exact)
assert.match(exact, /2:05:00\s?PM/, exact)
assert.match(exact, /[A-Z]{2,5}|GMT|UTC/, 'a time zone is named')
assert.ok(TICK_MS <= 60_000, 'relative minutes move at least once a minute')

/* -- drawn as one: in the byline, with no reading time -------------------- */
const post = src('quiet2/Post.tsx')
assert.doesNotMatch(post, /min read/, 'no estimated reading time on a post')
assert.doesNotMatch(post, /readMinutes/, 'the reading-time estimate is gone')
assert.match(post, /<time className="q2-time"[^>]*tabIndex=\{0\}/, 'the time is reachable by keyboard')
assert.match(post, /data-exact=\{exact\}/, 'its exact moment rides on it for hover and focus')
const css = src('quiet2/quiet2.css')
assert.match(css, /\.q2-time:hover::after, \.q2-time:focus-visible::after/, 'shown on hover and on focus')

/* -- 5.5 collapse keeps the draft --------------------------------------- */
const dock = src('quiet2/Dock.tsx')
assert.match(dock, /operations collapsible \/>/, "Quiet Chat's composer is the collapsible one")
const composer = src('fluid/Composer.tsx')
const collapseBody = /const collapse = \(\) => \{([\s\S]*?)\n {2}\}/.exec(composer)?.[1] ?? ''
assert.ok(collapseBody.includes('setFolded(true)'), 'collapse folds')
assert.doesNotMatch(collapseBody, /setDraft|dropDraft|saveDraft|emptyDraft/, 'collapse never changes the draft')
assert.match(composer, /const foldedNow = !!collapsible && folded && kept/, 'only a composer asked to be collapsible folds')

/* -- 5.6 the newest activity ---------------------------------------------- */
const act = (id: string, number: number | null, at: number | null, root: string | null = null) => ({ id, number, at, root })
/* a reply deep in an old thread is newer than every later top-level post */
const oldRoot = act('A', 1, 1000, 'A'), deepReply = act('A1a-x', 17, 1700, 'A'), lateRoot = act('G', 13, 1300, 'G')
assert.equal(newestOf([oldRoot, lateRoot, deepReply])?.id, 'A1a-x')
assert.equal(newestOf([deepReply, lateRoot, oldRoot])?.id, 'A1a-x', 'order of the candidates does not matter')
/* the server's read and the posts held are weighed together: a reply just made here wins */
assert.equal(newestOf([act('server', 17, 1700), act('held', 18, 1800)])?.id, 'held')
assert.equal(newestOf([act('server', 17, 1700), act('held-older', 9, 900)])?.id, 'server')
/* the number is the record's order; the time decides only without one */
assert.equal(newestOf([act('n5', 5, 9999), act('n6', 6, 1)])?.id, 'n6', 'number before time')
assert.equal(newestOf([act('t1', null, 100), act('t2', null, 200)])?.id, 't2')
assert.ok(newer(act('x', 2, null), act('y', 1, null)) && !newer(act('y', 1, null), act('x', 2, null)))
assert.equal(newestOf([null, undefined]), null, 'nothing known: nothing offered')
assert.equal(newestOf([act('same', 3, 3), act('same-again', 3, 3)])?.id, 'same', 'a tie keeps the first')
/* a held post becomes activity with its thread's top */
const held = activityOf({ id: 'r', number: 7, atTime: 70, root: 'A', replyTo: 'A1', by: { id: 'p', name: '@p' }, at: '', weight: 'brief', blocks: [] } as never)
assert.deepEqual(held, { id: 'r', number: 7, at: 70, root: 'A' })
assert.equal(activityOf({ id: 't', by: { id: 'p', name: '@p' }, at: '', weight: 'brief', blocks: [] } as never).root, 't', 'a top-level post is its own thread')
/* the page reads it from the server's existing Latest read, agent work kept */
const latestSrc = src('quiet2/latest.ts')
assert.match(latestSrc, /\/fluid\/api\/latest\?conversation=\$\{encodeURIComponent\(conversation\)\}&limit=1&agent_work=1/)

console.log('quiet2 usability: ok')
