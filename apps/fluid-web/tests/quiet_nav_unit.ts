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
 *     centre column, so Back and Forward keep walking the same entries;
 *   - UNSAVED GOVERNANCE AUTHORING (owner, ent-406244084c3e): what a Brain
 *     record form holds, what the question about it says, and which moves of
 *     the browser's own Back and Forward are asked about first;
 *   - WHAT SETTING UP A SOURCE HOLDS (holding.ts, after review
 *     ent-96bc70094ba1): the rule every setup flow uses, including what a run
 *     in flight means -- looking at a source answers the page, taking it
 *     answers the Brain, and the two are not said the same way;
 *   - after review ent-d960d458078c: a question already open when the browser
 *     moves AGAIN (H1); which move between the source pages keeps the page
 *     that holds the typing (moving.ts, S1); what importing an archive holds
 *     before it is staged (importing.ts, I1); and which column hears a form,
 *     so a working column's close asks and a conversation press does not (W1).
 *
 * What is NOT checked here (it needs a browser): that the Conversations rail
 * is above the browser card's veil (quiet2.css `.q2-browsing`), and the
 * scroll the conversation is put back to. Both were checked by hand. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ANYWAY, DISCARD, LOST_RECORD, STAY, authoring, forgetUnfinished, leaving, tell, unfinished, written, type Standing } from '../src/quiet2/leaving'
import { askFirst, plan, unasked } from '../src/quiet2/centreHistory'
import { ACT_WORDS, actUnsaved, writingUnsaved } from '../src/surfaces/governance/acting'
import { LANDS, LOOKING, PAGE, TAKING, adding, type Held } from '../src/quiet2/sources/holding'
import { keepsSetup } from '../src/quiet2/sources/moving'
import type { SourceMainState } from '../src/quiet2/sources/SourceMain'
import {
  LANDS as IMPORT_LANDS, LOST as IMPORT_LOST, PAGE as IMPORT_PAGE, READING as IMPORT_READING,
  STAGING as IMPORT_STAGING, importing, type Importing,
} from '../src/quiet2/brain/importing'

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

  /* WHERE IT LANDS, where the page knows: "it carries on" on its own leaves
     the reader wondering what becomes of it (review ent-96bc70094ba1) */
  const lands = 'What it takes is added to the Brain either way.'
  const said = leaving({ what: 'Notes', run: { what: 'Refreshing Notes', interrupted: false, lands } })
  eq(said.note, `Refreshing Notes carries on. Leaving does not stop it. ${lands}`, 'what carries on, and where it lands')
  const asked = leaving({ what: 'Notes', dirty: true, run: { what: 'Refreshing Notes', interrupted: false, lands } })
  eq(asked.ask!.lines[1], `Refreshing Notes carries on either way. Leaving does not stop it. ${lands}`, 'and the same in the question')
}

/* -- WHAT SETTING UP A SOURCE HOLDS (holding.ts) --------------------------
   THE DEFECT THIS ANSWERS (independent review ent-96bc70094ba1): the question
   was asked from the STEP the flow said it was on, so a name typed on the
   first step and a path typed into the picker and not yet used were lost
   without a word; and a take that ended after the reader had gone said its
   answer would "land nowhere" and then reopened the source over the
   conversation they had chosen. */
{
  const nothing: Held = { typed: false, preview: false, run: null, done: false }
  eq(leaving(adding(nothing)), { ask: null, note: null }, 'a setup with nothing in it is never asked about')
  eq(adding(nothing)!.what, PAGE, 'and it names itself as the reader knows it')

  /* a name on the first step, a path typed into the picker: both are "typed",
     and neither has a step to be past */
  const typed = leaving(adding({ ...nothing, typed: true }))
  ok(typed.ask, 'anything typed into the setup is asked about, at any step')
  eq([typed.ask!.stay, typed.ask!.leave], [STAY, DISCARD], 'Stay, or discard and switch')
  eq(typed.ask!.lines, ['What you have filled in here is not saved anywhere.'], 'and it says so in one line')
  ok(leaving(adding({ ...nothing, preview: true })).ask, 'a preview in hand, with nothing typed since, is asked about too')
  eq(adding({ typed: true, preview: true, run: null, done: true }), null,
    'once the source has been taken there is nothing unfinished here')

  /* LOOKING at the source answers THIS PAGE, which is about to go */
  const looking = adding({ ...nothing, typed: true, run: 'plan' })!
  eq(looking.run, { what: LOOKING, interrupted: true }, 'a preview in flight loses its answer')
  ok(/land nowhere/.test(leaving(looking).ask!.lines.join(' ')), 'so that is what the question says')

  /* TAKING the source answers THE BRAIN: it is not this page's to lose */
  const taking = adding({ typed: true, preview: true, run: 'sweep', done: false })!
  eq(taking.run, { what: TAKING, interrupted: false, lands: LANDS }, 'a take is never called interrupted')
  eq(taking.dirty, false, 'what was filled in is in the server’s hands, not lost by leaving')
  eq(taking.preview, false, 'and the preview is being applied, not abandoned')
  const go = leaving(taking)
  eq(go.ask, null, 'so a take in flight holds nobody, and asks nothing')
  eq(go.note, `${TAKING} carries on. Leaving does not stop it. ${LANDS}`, 'it is said instead, with where it lands')
  ok(!/land(s)? nowhere/.test(go.note!), 'and never that its answer lands nowhere: the source is added')
  ok(/added to the Brain/.test(LANDS), 'the reader is told what actually becomes of it')
}

/* -- a page says what is unfinished only while it is on the page ----------
   THE REAL REGISTRY, not a copy of it (review ent-96bc70094ba1 found the old
   check built its own Set and so could not have caught a page that never
   registered at all). `tell` is the whole of what `useUnfinished` does,
   apart from being bound to a component's life. */
{
  forgetUnfinished()
  eq(unfinished(), null, 'no page: nothing unfinished')
  let held: Standing | null = { what: 'Add a source', dirty: true }
  const forget = tell(() => held)
  eq(unfinished(), held, 'while it is on the page it is asked')
  held = { what: 'Add a source', dirty: false }
  eq(unfinished(), null, 'a page with nothing unfinished is passed over')
  held = { what: 'Add a source', preview: true }
  eq(unfinished(), held, 'a preview alone is enough to be asked about')
  forget()
  eq(unfinished(), null, 'off the page, it is asked no more')
}

/* -- WHERE THE WORK IS DECIDES WHAT TAKES IT AWAY -------------------------
   THE DEFECT THIS ANSWERS (independent review ent-d960d458078c, W1): a
   record challenge typed BESIDE a conversation went with the press that
   closed that column, and nothing was said. It must not hold a conversation
   press up -- switching conversations leaves it open, so nothing is lost --
   but its own column's close takes it away, and asks. */
{
  forgetUnfinished()
  const beside = authoring('this challenge')
  const forget = tell(() => beside, 's1')
  eq(unfinished(), null, 'a form beside the conversation never holds a conversation press up')
  eq(unfinished('s1'), beside, 'but its own column’s close is told about it')
  eq(unfinished('s2'), null, 'and the other column’s close is not: it holds nothing')
  ok(leaving(unfinished('s1')).ask, 'so closing that column asks before the words go')
  eq(leaving(unfinished()).ask, null, 'and the conversation press still goes at once')
  const centre = tell(() => authoring('this revision'))
  ok(leaving(unfinished()).ask, 'a form in the reading area is asked about there')
  forget(); centre()
  eq(unfinished('s1'), null, 'closed, the column holds nothing')
  eq(unfinished(), null, 'and so does the reading area')
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

/* -- a Brain record being written is never lost without a question --------
   THE DEFECT THIS ANSWERS (owner, ent-406244084c3e): a half-written Brain
   record went with the press that left it, and nothing was said. */
{
  const a = leaving(authoring('this new rule'))
  ok(a.ask, 'a record being written is asked about before the page is left')
  eq(a.ask!.title, 'Leave this new rule unfinished?', 'the record is named as the reader would name it')
  eq([a.ask!.stay, a.ask!.leave], [STAY, DISCARD], 'the owner’s own two answers, here too')
  eq(a.ask!.lines, [LOST_RECORD], 'one line, and it says where the words are not: in the Brain')
  ok(/not been recorded/.test(LOST_RECORD) && /nothing of it is in the Brain/.test(LOST_RECORD),
    'a record is written, not “filled in”: the words say what it would cost')
  /* reading one is not writing one */
  eq(leaving({ what: 'a Brain record' }), { ask: null, note: null }, 'merely reading a record never asks')

  /* A FORM SAYS WHAT IT HOLDS AND NOTHING MORE: where it is drawn, and so
     which way out asks about it, is its column's business (`LeavingPlace`,
     checked above). */
  eq(written('this challenge', true), authoring('this challenge'), 'a form in hand is told')
  eq(written('this challenge', false), null, 'and an untouched form holds nobody anywhere')
}

/* -- what a record form holds, and what it is called ---------------------- */
{
  /* opening a form holds nothing: only what was typed into it does */
  eq(actUnsaved({ open: 'delete', typed: false }, { act: null, typed: false }), null,
    'Delete… opened and left alone stops nobody')
  eq(actUnsaved({ open: 'edit', typed: true }, { act: null, typed: false }), 'this revision',
    'a revision with words in it is named')
  eq(actUnsaved({ open: null, typed: false }, { act: 'dispute', typed: true }), 'this challenge',
    'and so is an act dialog that was written in')
  eq(actUnsaved({ open: null, typed: false }, { act: 'establish', typed: false }), null,
    'an act dialog opened and not written in holds nothing')
  eq(actUnsaved({ open: 'edit', typed: true }, { act: 'dispute', typed: true }), 'this revision',
    'the form the reader is looking at is the one named')
  eq(actUnsaved({ open: 'invented-act', typed: true }, { act: null, typed: false }), 'this change',
    'an act these words do not know is still named something, never nothing')
  for (const [act, words] of Object.entries(ACT_WORDS)) {
    ok(/^this /.test(words), `${act} is named as a thing, not as a button: “${words}”`)
  }
}

/* -- a record being written, in the builder ------------------------------- */
{
  const none = { created: false, typed: ['', '  '], basis: '', basisGiven: '' }
  eq(writingUnsaved(none), false, 'an untouched builder holds nothing')
  eq(writingUnsaved({ ...none, typed: ['', 'The rule'] }), true, 'words typed into any field are held')
  /* "Propose a rule from it…" fills the basis in for the reader */
  eq(writingUnsaved({ ...none, basis: 'ent-1', basisGiven: 'ent-1' }), false,
    'a reference the door itself supplied is not something the reader wrote')
  eq(writingUnsaved({ ...none, basis: 'ent-1 ent-2', basisGiven: 'ent-1' }), true, 'one they added is')
  /* the worst thing to lose: the record exists, its remaining acts do not */
  eq(writingUnsaved({ ...none, created: true }), true,
    'a record created whose citation or placement has not completed is unfinished work')
}

/* -- the browser's own Back and Forward -----------------------------------
   The page's own controls ask before they move. The browser's cannot: by the
   time it says it moved, it has. So the question is put on the way in, and
   only for moves that would actually lose something. */
{
  type Place = { brain?: { entry: string } }
  const rec: Place = { brain: { entry: 'ent-1' } }
  const other: Place = { brain: { entry: 'ent-2' } }
  eq(askFirst(false, true, rec, null), true, 'the reader’s own Back, off a record page: asked first')
  eq(askFirst(false, true, null, rec), true, 'and their Forward, back onto one')
  eq(askFirst(true, true, rec, null), false,
    'a move this page asked for was guarded by whoever asked for it: never questioned twice')
  eq(askFirst(false, false, rec, null), false, 'an entry that is not this page’s is not ours to hold')
  eq(askFirst(false, true, rec, rec), false, 'landing on the same place loses nothing')
  eq(askFirst(false, true, rec, other), true, 'another record takes the centre: the first one’s form goes with it')
}

/* -- BACK AND FORWARD WHILE THE QUESTION IS STILL OPEN --------------------
   THE DEFECT THIS ANSWERS (independent review ent-d960d458078c, H1): Back
   put the question up; Forward, pressed before answering it, took the
   browser back to the entry the reader was on; Stay then asked the browser
   to move somewhere it already was, and the walk that never happened ate
   the reader's NEXT Back. History said one page, the screen showed another.
   The reader's own Forward has answered the question: it goes. */
{
  eq(unasked(true, true, 2, 2), true,
    'their Forward undid the Back they were asked about: nothing is being left, so nothing is asked')
  eq(unasked(true, true, 1, 2), false, 'somewhere else: the same question still stands, for that move')
  eq(unasked(false, true, 2, 2), false, 'with no question open there is none to take away')
  eq(unasked(true, false, null, 2), false, 'an entry that is not this page’s answers nothing')
}

/* -- WHICH MOVE BETWEEN SOURCE PAGES KEEPS THE PAGE (moving.ts) -----------
   THE DEFECT THIS ANSWERS (independent review ent-d960d458078c, S1): three
   real presses went straight to the browser's history, around the question:
   the preview's "Add the repository as its own collection", "Back to the
   conversation", and Add a source's own header Back. Asking about every move
   would be worse: reading a held file in place keeps the source's page
   mounted underneath, with the scope draft exactly as it was. */
{
  const srcA = (reading: unknown = null) => ({ view: { page: 'source', col: 'col-a' }, reading } as SourceMainState)
  const srcB = { view: { page: 'source', col: 'col-b' }, reading: null } as SourceMainState
  const add = (connector: string | null = 'folder') => ({ view: { page: 'add', connector }, reading: null } as SourceMainState)

  eq(keepsSetup(srcA(), srcA({ at: 'object', col: 'col-a', key: 'readme.md' })), true,
    'reading a held file in place keeps the source’s page under it: nothing to ask')
  eq(keepsSetup(srcA({ at: 'object', col: 'col-a', key: 'readme.md' }), srcA()), true,
    'and coming back from the file finds the same page, with what was typed in it')
  eq(keepsSetup(srcA(), srcB), false, 'another source takes this one’s page away')
  eq(keepsSetup(srcA(), add()), false,
    'Add a source, offered from a preview, takes the source’s page and its unapplied preview with it')
  eq(keepsSetup(add(), srcA()), false, 'and opening a source takes the setup away')
  /* ANOTHER KIND keeps the page and loses the FLOW: AddSourcePage keys its
     flow on the descriptor, so the name, the place and the preview in it go.
     Read the other way at dac52ce, and the re-review (ent-c7013fe14e59) was
     right: the live path is the preview's own "Add the repository as its own
     collection", which reads as an addition rather than a discard, and the
     kind cards are disabled while a preview is in hand. */
  eq(keepsSetup(add('folder'), add('git')), false,
    'another kind unmounts the flow with the name, the place and the unapplied preview in it')
  eq(keepsSetup(add('folder'), add('folder')), true, 'the same kind changes nothing and asks nothing')
  eq(keepsSetup(add(null), add('folder')), false, 'and choosing the first kind is a kind change like any other')
  eq(keepsSetup(null, srcA()), true, 'arriving from the conversation leaves nothing behind')
}

/* -- WHAT IMPORTING AN ARCHIVE HOLDS (importing.ts) -----------------------
   THE DEFECT THIS ANSWERS (independent review ent-d960d458078c, I1): an
   archive chosen and read, its itemised plan on the screen, lived only in
   the page and went with the press that left it. The owner's rule is
   explicit: a completed but unapplied preview is unfinished setup. What has
   been STAGED is on disk and is read back, so leaving it loses nothing. */
{
  const nothing: Importing = { chosen: false, preview: false, run: null, done: false }
  eq(leaving(importing(nothing)), { ask: null, note: null }, 'an import page with nothing chosen never asks')
  const chosen = leaving(importing({ ...nothing, chosen: true }))
  ok(chosen.ask, 'an archive chosen and not staged is asked about')
  eq([chosen.ask!.stay, chosen.ask!.leave], [STAY, DISCARD], 'Stay, or discard and switch')
  eq(chosen.ask!.lines, [IMPORT_LOST], 'in one line, saying nothing of it is in the Brain')
  eq(chosen.ask!.title, `Leave ${IMPORT_PAGE} unfinished?`, 'and naming the work as the reader knows it')
  ok(leaving(importing({ ...nothing, chosen: true, preview: true })).ask,
    'a completed but unapplied plan is unfinished setup')
  eq(importing({ chosen: true, preview: true, run: null, done: true }), null,
    'staged, there is nothing unfinished here: the payload is on disk')
  eq(leaving(importing({ chosen: true, preview: true, run: null, done: true })), { ask: null, note: null },
    'so leaving a staged import is a no-loss transition and asks nothing')

  /* READING the archive answers this page; STAGING it answers the Brain */
  const reading = importing({ ...nothing, chosen: true, run: 'reading' })!
  eq(reading.run, { what: IMPORT_READING, interrupted: true }, 'a reading in flight loses its answer')
  const staging = importing({ chosen: true, preview: true, run: 'staging', done: false })!
  eq(staging.run, { what: IMPORT_STAGING, interrupted: false, lands: IMPORT_LANDS }, 'a staging is never called interrupted')
  eq(staging.dirty, false, 'what was chosen is in the server’s hands, not lost by leaving')
  const go = leaving(staging)
  eq(go.ask, null, 'so a staging in flight holds nobody')
  eq(go.note, `${IMPORT_STAGING} carries on. Leaving does not stop it. ${IMPORT_LANDS}`, 'it is said, with where it lands')
}

/* -- every setup flow actually SAYS what it holds -------------------------
   The decision above is only as good as what reaches it. These read the
   pages themselves, because the review's two blocking findings were not
   wrong decisions but things the decision was never told: a name at step 1,
   a path typed into the picker, and a take that ended after the reader had
   gone. (A mounted-component check would be better still and needs a test
   renderer this app does not have: recorded as discovered work.) */
{
  const src = (p: string) => readFileSync(new URL('../src/' + p, import.meta.url), 'utf8')
  const add = src('quiet2/sources/AddSourcePage.tsx')
  const pick = src('surfaces/sources/pick/PickSource.tsx')
  const sql = src('surfaces/sources/sqlite/SqliteFlow.tsx')
  const page = src('quiet2/sources/SourcePage.tsx')

  ok(!/useUnfinished\([^)]*step\s*>/.test(add), 'Add a source no longer decides what it holds from the step it is on')
  ok(/adding\(/.test(add) && /adding\(/.test(add.slice(add.indexOf('FolderFlow'))),
    'both of its flows go through the one rule (holding.adding)')
  ok(/onHolding/.test(sql) && /onHolding=\{/.test(add), 'the database flow says what it holds, and the page listens')
  ok(/onTyping/.test(pick), 'the picker says what has been typed into it and not yet used')
  for (const [what, text] of [['Add a source', add], ['a source’s page', page]] as const)
    ok(/onTyping=\{/.test(text), `${what} listens to a path typed into its picker`)
  /* the late answer: nothing that opens a source may sit after an await
     without first asking whether the reader is still here */
  const take = add.slice(add.indexOf('const take ='), add.indexOf('const why ='))
  ok(/here\.current/.test(take) && take.indexOf('here.current') < take.indexOf('onOpenSource'),
    'a take asks whether the reader is still on the page before it opens anything')
  ok(/here\.current = true; return \(\) => \{ here\.current = false \}/.test(add),
    'and the page knows when it has gone -- and when it has come back, so a remount does not leave it for dead')
}

console.log(`quiet_nav_unit: ${checks} checks passed`)
