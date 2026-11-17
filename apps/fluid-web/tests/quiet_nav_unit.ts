/* CONVERSATION NAVIGATION IN QUIET CHAT, checked without a server or a
 * browser. The owner's rule (2026-11-17): a conversation press always begins
 * going to that conversation; it is never refused and the reader is never
 * held in a management view.
 *
 * What is checked here:
 *   - leaving.ts: when leaving asks first and when it goes at once, what it
 *     says, and that a run is never presented as cancelled;
 *   - the teller registry: a page says what is unfinished only while it is
 *     on the page;
 *   - centreHistory.plan for the step a conversation press takes out of the
 *     centre column, so Back and Forward keep walking the same entries.
 *
 * What is NOT checked here (it needs a browser): that the Conversations rail
 * is above the browser card's veil (quiet2.css `.q2-browsing`), and the
 * scroll the conversation is put back to. Both were checked by hand. */
import assert from 'node:assert/strict'
import { ANYWAY, DISCARD, STAY, forgetUnfinished, leaving, unfinished, type Standing } from '../src/quiet2/leaving'
import { plan } from '../src/quiet2/centreHistory'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/* -- nothing unsaved: the switch happens at once -------------------------- */
{
  eq(leaving(null), { ask: null, note: null }, 'nothing on the page: nothing asked, nothing said')
  /* "Merely viewing a source, file, Brain record, or management page must
     never block navigation." */
  eq(leaving({ what: 'Notes' }), { ask: null, note: null }, 'merely viewing a source never asks')
  eq(leaving({ what: 'Notes', dirty: false, preview: false, run: null }), { ask: null, note: null }, 'nothing unfinished never asks')
}

/* -- an unfinished setup: Stay, or discard and switch --------------------- */
{
  const a = leaving({ what: 'Add a source', dirty: true })
  ok(a.ask, 'an unfinished setup with unsaved changes is asked about')
  eq(a.ask!.title, 'Leave Add a source unfinished?', 'the page is named in the question')
  eq([a.ask!.stay, a.ask!.leave], [STAY, DISCARD], 'the owner’s own two answers')
  eq(a.ask!.lines, ['What you have filled in here is not saved anywhere.'], 'what would be lost, in one line')
  eq(a.note, null, 'nothing is said afterwards: it was asked instead')
}

/* -- a completed but unapplied preview counts as unfinished setup --------- */
{
  const p = leaving({ what: 'Add a source', dirty: false, preview: true })
  ok(p.ask, 'a preview in hand is unfinished setup, even with nothing typed since')
  eq(p.ask!.leave, DISCARD, 'and losing it is discarding changes')
  eq(p.ask!.lines, ['The preview you have in hand has not been applied: nothing has been added to the Brain.'],
    'it says plainly that nothing has entered the Brain')
  const both = leaving({ what: 'Add a source', dirty: true, preview: true })
  eq(both.ask!.lines.length, 2, 'what was filled in and the preview are said apart')
}

/* -- a running operation is explained, and never silently cancelled ------- */
{
  /* the server's own refresh: it carries on, so it never holds anybody here */
  const on = leaving({ what: 'Notes', run: { what: 'Refreshing Notes', interrupted: false } })
  eq(on.ask, null, 'a refresh that carries on does not hold the reader')
  eq(on.note, 'Refreshing Notes carries on. Leaving does not stop it.', 'it is said, so leaving never looks like cancelling it')

  /* a preview whose answer would land on a page that is gone */
  const off = leaving({ what: 'Add a source', run: { what: 'Looking at the source', interrupted: true } })
  ok(off.ask, 'a run whose answer would be lost is asked about')
  eq(off.ask!.leave, ANYWAY, 'nothing was filled in, so it is not called discarding changes')
  eq(off.ask!.lines, ['Looking at the source is still running. Leaving does not cancel it, but its answer would land nowhere and you would ask for it again.'],
    'it says it is not cancelled, and what leaving actually costs')

  /* asked for another reason, a run that carries on is still explained */
  const with_ = leaving({ what: 'Notes', dirty: true, run: { what: 'Refreshing Notes', interrupted: false } })
  eq(with_.ask!.lines[1], 'Refreshing Notes carries on either way. Leaving does not stop it.', 'and it is said in the question too')
  ok(!/cancel(led)?\b/.test(with_.ask!.lines.join(' ').replace('does not cancel', '')), 'nothing anywhere says a run is cancelled')
}

/* -- a page says what is unfinished only while it is on the page ---------- */
{
  forgetUnfinished()
  eq(unfinished(), null, 'no page: nothing unfinished')
  let held: Standing | null = { what: 'Add a source', dirty: true }
  /* the hook's own body, without React: register, be asked, go away */
  const tellers = new Set<() => Standing | null>()
  const teller = () => held
  tellers.add(teller)
  const ask = () => { for (const t of tellers) { const s = t(); if (s && (s.dirty || s.preview || s.run)) return s } return null }
  eq(ask(), held, 'while it is on the page it is asked')
  held = { what: 'Add a source', dirty: false }
  eq(ask(), null, 'a page with nothing unfinished is passed over')
  held = { what: 'Add a source', preview: true }
  eq(ask(), held, 'a preview alone is enough to be asked about')
  tellers.delete(teller)
  eq(ask(), null, 'off the page, it is asked no more')
  eq(unfinished(), null, 'and the real registry is still empty')
}

/* -- the step a conversation press takes out of the centre column ---------
   `arrive` leaves the centre through `centre.go(null)`: where the
   conversation is behind, that is the BROWSER's own Back, so Back and
   Forward keep walking the same entries and the address is never touched. */
{
  type Place = { source?: { col: string }; brain?: { entry: string } }
  const src: Place = { source: { col: 'c1' } }
  const file: Place = { source: { col: 'c1' } }
  const rec: Place = { brain: { entry: 'ent-1' } }
  eq(plan<Place>([null], 0, null), 0, 'from the conversation, a press is already there: no entry either way')
  eq(plan([null, src], 1, null), -1, 'from a source: one entry back, and Forward returns to the source')
  eq(plan([null, src, file], 2, null), -2, 'from a file read in place: back past the source too')
  eq(plan([null, rec], 1, null), -1, 'from a Brain record: the same one step')
  eq(plan([null, src, null, rec], 3, null), -1, 'the nearest conversation behind, not the first')
  eq(plan([undefined, src] as (Place | null | undefined)[], 1, null), null,
    'after a reload what is behind is unknown: an entry is pushed, never guessed, so Back still stays in Quiet Chat')
}

console.log(`quiet_nav_unit: ${checks} checks passed`)
