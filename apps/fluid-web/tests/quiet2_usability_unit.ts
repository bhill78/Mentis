/* QUIET CHAT MARK 2 USABILITY CORRECTIONS (2026-11-12), checked without a
 * browser:
 *
 *  5.4 a post's time: relative for the first twelve hours ("just now",
 *      "5m ago", "2h ago"), then a date and time (Today / Yesterday / a date,
 *      with the year once it is not this one); the exact moment in full; the
 *      shared clock runs only while something uses it; no reading time is
 *      drawn on a post.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JUST_NOW, RELATIVE_FOR, TICK_MS, whenExact, whenSaid } from '../src/quiet2/when'

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

console.log('quiet2 usability: ok')
