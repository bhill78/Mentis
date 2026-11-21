/* ------------------------------------------------------------------------ *
 * WHEN THE SAVED PERMISSION DEFAULT IS FILLED IN -- DRIVEN, NOT READ.
 *
 * This mounts the REAL lifecycle (src/fluid/composer/useDefault.ts) over the
 * small hook runtime (tests/space_react_stub.mjs), with a real draft, the
 * real Brain binding and the real browser store, and runs its real render
 * bodies and effects. Nothing here matches source text.
 *
 * WHY IT EXISTS. The independent review of the first implementation
 * (adm-232c2d36269e) found four defects that every check in the suite missed,
 * because every check about the composer's lifecycle was a regular expression
 * over Composer.tsx's characters and the expressions matched the broken code
 * exactly (N3). The defects were all about WHEN, not what:
 *
 *   B1  a default filled in for one Brain and owner was still in the draft,
 *       and still in the body, after the page was reloaded on another Brain
 *       or by another owner -- the draft is kept by WHERE it is written, and
 *       a conversation id is the same id in a copy of a Brain;
 *   B2  choosing to reply kept the fresh-Work default and handed it to
 *       whoever was addressed next;
 *   B3  a draft restored from before the preference existed was filled in
 *       with the saved default, changing what sending it does with no edit;
 *   B4  an explicit "Ask for permission" or "Asks before pursuing side work"
 *       chosen while the Brain was still being answered was overwritten when
 *       the answer arrived, because both of those say what they say by being
 *       absent.
 *
 * So each is driven here as behaviour, both ways round: the default IS filled
 * into new Work that is this Brain's and this owner's and started here, and
 * it is NOT filled into, or carried into, anything else.
 *
 * WHAT IT DOES NOT CLAIM. Nothing about pixels, CSS or real browser
 * scheduling, and nothing about the chrome around the lifecycle -- which
 * prop the composer passes it, and where the permission entry is drawn, are
 * the composer's own (permission_default_unit checks those at the seam, and
 * browser evidence belongs to whoever verifies the candidate).
 * ------------------------------------------------------------------------ */

import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'

const stub = new URL('./space_react_stub.mjs', import.meta.url).href

registerHooks({
  resolve(specifier, context, next) {
    /* REACT IS THE ONLY THING STOOD IN FOR. Everything else is the real file. */
    if (specifier === 'react' || specifier === 'react/jsx-runtime') return { url: stub, shortCircuit: true }
    if (specifier.startsWith('.')) {
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url))
      return {
        format: 'module',
        shortCircuit: true,
        source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
          compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
        }).outputText,
      }
    return next(url, context)
  },
})

const R = await import('./space_react_stub.mjs')
const { usePermissionDefault, UNPLACED_SEND } = await import('../src/fluid/composer/useDefault.ts')
const { createBinding } = await import('../src/brainBinding.ts')
const { saveDefault, seedAddressees, withDecision } = await import('../src/fluid/composer/permissionDefault.ts')
const { bodyOf, emptyDraft } = await import('../src/composer/draft.ts')

let checks = 0
const is = (a, b, what) => { assert.strictEqual(a, b, what); checks += 1 }
const eq = (a, b, what) => { assert.deepEqual(a, b, what); checks += 1 }
const ok = (a, what) => { assert.ok(a, what); checks += 1 }
const no = (a, what) => { assert.ok(!a, what); checks += 1 }

/* ---- the little of a browser this needs --------------------------------- */

/** A store of the shape the page uses; nothing here touches a real browser. */
function bag(seed = {}) {
  const held = { ...seed }
  return {
    held,
    get length() { return Object.keys(held).length },
    clear() { for (const k of Object.keys(held)) delete held[k] },
    getItem: (k) => (k in held ? held[k] : null),
    key: (i) => Object.keys(held)[i] ?? null,
    removeItem: (k) => { delete held[k] },
    setItem: (k, v) => { held[k] = String(v) },
  }
}

const BRAIN_A = 'corpus-1@a1b2c3d4e5f60718'
const BRAIN_B = 'corpus-1@9f8e7d6c5b4a3921'
const OWNER_A = 'ent-owner-a'
const OWNER_B = 'ent-owner-b'
const SCOPE_A = `${BRAIN_A}|${OWNER_A}`
const ALL = { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, followUp: 1 }
const TASK = { consent: { mode: 'task', workspaces: ['C:\\Work\\MARS'] } }
const worker = (over = {}) => ({ participant: 'ent-worker', alias: '@Worker', dispatch: true, ...over })

/* ---- the lifecycle, mounted --------------------------------------------- */

/** WHAT THE COMPOSER IS, around this lifecycle: a draft kept in state, and
 *  every change to it going through the one seam that hands a copy of the
 *  draft's selections to whoever is newly marked for work -- which is exactly
 *  what Composer.tsx's `setDraft` does (`seedAddressees`, checked at the seam
 *  in permission_default_unit). Everything else about the composer is absent
 *  on purpose: this is a test of when the default moves. */
function mount({ draft = emptyDraft(), enabled = true, fresh = true, owner = OWNER_A, binding, confirm, storage }) {
  const seen = { renders: 0 }
  const Composing = (props) => {
    const [held, setHeld] = R.useState(() => props.draft)
    const setDraft = (fn) => setHeld((d) => seedAddressees(typeof fn === 'function' ? fn(d) : fn, props.enabled && props.fresh))
    const got = usePermissionDefault({
      enabled: props.enabled, fresh: props.fresh, owner: props.owner, draft: held, setDraft,
      binding: props.binding, confirm: props.confirm, storage: props.storage,
    })
    seen.renders += 1
    seen.draft = held
    seen.sending = got.forSending(held)
    /* WHAT PRESSING SEND ACTUALLY GOES THROUGH (Composer.tsx, `placed`):
       asked for the draft as it is, and answered once the page can say where
       the submission would be recorded. */
    seen.place = got.sending
    seen.scope = got.scope
    seen.saved = got.saved
    seen.preference = got.preferenceFor(held.askMentis ?? {})
    seen.edit = setDraft
    return null
  }
  const props = { draft, enabled, fresh, owner, binding, confirm, storage }
  const show = (over = {}) => {
    Object.assign(props, over)
    R.act(() => { R.render(R.createElement(Composing, { ...props })) })
    return seen
  }
  show()
  return { seen, show, edit: (fn) => { R.act(() => seen.edit(fn)); return seen } }
}

/** What the submission would carry for Ask Mentis, from the draft the
 *  composer would actually send (`forSending`). */
const sent = (seen) => bodyOf(seen.sending, OWNER_A, []).ask_mentis

/* ======================================================================== *
 * 1. THE APPROVED BEHAVIOUR: new Work, this Brain, this owner, started here
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  const { seen, show } = mount({ storage, binding })
  /* NOTHING BEFORE THE PAGE CAN SAY WHICH BRAIN IT IS ON. */
  is(seen.scope, undefined, 'the scope is unanswered, not none, while the Brain is still being asked')
  no(seen.draft.seeded, 'and nothing is filled in on an unanswered question')
  is(sent(seen), undefined, 'so a submission made in that moment carries no permissions')
  is(seen.preference, undefined, 'and there is nowhere to save a default yet')
  /* THE BRAIN ANSWERS, after the composer mounted. */
  R.act(() => { binding.saw(BRAIN_A) })
  is(seen.scope, SCOPE_A, 'once the Brain answers, the scope is that Brain and this owner')
  ok(seen.draft.seeded, 'and the fresh draft is filled in')
  eq(seen.draft.askMentis, ALL, 'with exactly what was saved')
  is(seen.draft.seededIn, SCOPE_A, 'marked with the Brain and owner it was filled in for')
  eq(sent(seen), { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, follow_up: { depth: 1 } },
    'and the submission carries the three concrete values')
  ok(seen.preference && seen.preference.matches, 'the panel can say that what is saved is what is chosen')
  /* FILLED IN ONCE: the owner clears a setting and it stays cleared. */
  const after = mount({ storage, binding: (() => { const b = createBinding(); b.saw(BRAIN_A); return b })() })
  after.edit((d) => ({ ...d, askMentis: { ...d.askMentis, coordinate: undefined, decided: ['coordinate'] } }))
  is(after.seen.draft.askMentis.coordinate, undefined, 'a setting the owner clears is not filled in again')
  ok(after.seen.draft.seeded, 'the draft stays settled')
}

/* ======================================================================== *
 * 2. B1 -- IT DOES NOT CROSS TO ANOTHER OWNER
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  binding.saw(BRAIN_A)
  const { seen, show } = mount({ storage, binding })
  eq(seen.draft.askMentis, ALL, 'filled in for the owner acting')
  /* THE SAME BROWSER, THE SAME PAGE, ANOTHER OWNER: nothing of the first
     owner's is used, and this owner has saved nothing. */
  show({ owner: OWNER_B })
  is(seen.scope, `${BRAIN_A}|${OWNER_B}`, 'the scope is the other owner now')
  is(seen.draft.askMentis, undefined, 'the first owner\'s filled-in default is taken out of the draft')
  no(seen.draft.seeded, 'and the draft is no longer marked as filled in')
  is(seen.draft.seededIn, undefined, 'nor marked with the scope it was filled in for')
  is(sent(seen), undefined, 'so the submission carries none of it: no Allow All reaches another owner\'s Work')
  /* and this owner's own default, where they have one, fills it in once */
  saveDefault(`${BRAIN_A}|${OWNER_B}`, TASK, storage, 1001)
  show({ owner: OWNER_A })
  show({ owner: OWNER_B })
  eq(seen.draft.askMentis, TASK, 'the owner acting gets their own saved default, not the other\'s')
}

/* ======================================================================== *
 * 3. B1 -- IT DOES NOT CROSS TO ANOTHER BRAIN, ACROSS A RELOAD
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  /* the draft the tab kept: the same conversation id, the words the owner
     left, and the default that was filled in for Brain A */
  const kept = { ...emptyDraft(), text: 'look at the overnight run', restored: true, seeded: true, seededIn: SCOPE_A, askMentis: { ...ALL } }
  /* RELOADED, and the server now serves a copy of that Brain. */
  const binding = createBinding()
  binding.saw(BRAIN_B)
  const { seen } = mount({ storage, binding, draft: kept })
  is(seen.scope, `${BRAIN_B}|${OWNER_A}`, 'the page is bound to the Brain it was reloaded on')
  is(seen.draft.text, 'look at the overnight run', 'the words the owner left are theirs and are kept')
  is(seen.draft.askMentis, undefined, 'the default filled in for the other Brain is taken out')
  is(sent(seen), undefined, 'and the submission carries none of it')
  no(seen.draft.seeded, 'the draft is not marked as filled in for this Brain either')
  /* A RESTORED DRAFT IS NOT REFILLED, even now that it holds no permissions:
     it is what the owner left, and what they did not choose is part of it. */
  saveDefault(`${BRAIN_B}|${OWNER_A}`, ALL, storage, 1002)
  const again = mount({ storage, binding, draft: { ...kept } })
  is(again.seen.draft.askMentis, undefined, 'and this Brain\'s own default does not fill a restored draft in')
}

/* ======================================================================== *
 * 4. B1 -- A PAGE THAT HAS MOVED TO ANOTHER BRAIN CARRIES NOTHING
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  binding.saw(BRAIN_A)
  const { seen } = mount({ storage, binding })
  eq(seen.draft.askMentis, ALL, 'filled in while the page was on its own Brain')
  R.act(() => { binding.saw(BRAIN_B) })
  ok(binding.moved(), 'another Brain answered: the page has moved')
  is(seen.scope, null, 'a moved page has no scope at all')
  is(seen.draft.askMentis, undefined, 'what was filled in is taken out')
  is(sent(seen), undefined, 'and nothing decided here is carried to the Brain the server serves now')
  is(seen.preference, undefined, 'nor is there anywhere to save a default from a moved page')
}

/* ======================================================================== *
 * 5. B2 -- CHOOSING TO REPLY TAKES THE DEFAULT BACK OUT
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  binding.saw(BRAIN_A)
  const { seen, show, edit } = mount({ storage, binding })
  eq(seen.draft.askMentis, ALL, 'a fresh post is filled in')
  /* somebody marked for work takes a copy of it, as they should on new Work */
  edit((d) => ({ ...d, to: [worker()] }))
  eq(seen.draft.to[0].consent, ALL.consent, 'whoever is marked for work takes a copy')
  ok(seen.draft.to[0].seeded, 'marked as having taken it')
  /* THE OWNER CHOOSES REPLY. A reply carries the permissions already
     recorded for what it continues; this default was for new Work. */
  show({ fresh: false })
  is(seen.draft.askMentis, undefined, 'the fresh-Work default is taken out of the draft')
  is(seen.draft.to[0].consent, undefined, 'and out of the recipient that had taken a copy of it')
  is(seen.draft.to[0].coordinate, undefined, 'including the authority')
  is(seen.draft.to[0].followUp, undefined, 'and the side-work permission')
  no(seen.draft.to[0].seeded, 'who is no longer marked as having taken anything')
  /* AND THE NEXT RECIPIENT ADDRESSED IN A REPLY IS HANDED NOTHING. */
  edit((d) => ({ ...d, to: [...d.to, { participant: 'ent-other', alias: '@Quill', dispatch: true }] }))
  is(seen.draft.to[1].consent, undefined, 'a recipient addressed in a reply acquires no Permission Mode')
  is(seen.draft.to[1].coordinate, undefined, 'no authority')
  is(seen.draft.to[1].followUp, undefined, 'and no side-work permission')
  is(bodyOf(seen.sending, OWNER_A, []).dispatch.filter((x) => x.consent).length, 0,
    'so nothing in the reply\'s dispatch carries the default')
  /* WHAT THE OWNER DECIDED BY HAND IS THEIRS, and is not taken out. */
  const kept = mount({ storage, binding })
  kept.edit((d) => ({ ...d, askMentis: withDecision({ ...d.askMentis, coordinate: false }, 'coordinate') }))
  kept.show({ fresh: false })
  eq(kept.seen.draft.askMentis, { coordinate: false, decided: ['coordinate'] }, 'a choice the owner made by hand survives the boundary')
}

/* ======================================================================== *
 * 6. B3 -- A RESTORED DRAFT IS NOT FILLED IN
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  binding.saw(BRAIN_A)
  /* written before this preference existed, or before anything was saved:
     text, and no permission selections at all */
  const old = { ...emptyDraft(), text: 'half a thought', restored: true }
  const { seen } = mount({ storage, binding, draft: old })
  is(seen.draft.askMentis, undefined, 'a draft the owner left is not filled in from what is saved now')
  no(seen.draft.seeded, 'and is not marked as filled in')
  is(sent(seen), undefined, 'what it sends is what it sent before: the permissions it implies by saying nothing')
  /* a draft the tab kept that holds NOTHING is still a fresh one */
  const blank = mount({ storage, binding, draft: { ...emptyDraft(), restored: true } })
  eq(blank.seen.draft.askMentis, ALL, 'a kept but wholly empty draft is a fresh one and is filled in')
  /* a draft with somebody addressed in it is being written, and is not */
  const started = mount({ storage, binding, draft: { ...emptyDraft(), restored: true, to: [worker()] } })
  is(started.seen.draft.askMentis, undefined, 'a restored draft with somebody already addressed is not filled in')
  is(started.seen.draft.to[0].consent, undefined, 'and nobody in it is handed a Permission Mode')
}

/* ======================================================================== *
 * 7. B4 -- AN EXPLICIT ASK SURVIVES THE ANSWER ARRIVING LATE
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  const { seen, edit } = mount({ storage, binding, confirm: async () => null })
  is(seen.scope, undefined, 'the Brain has not answered yet')
  /* the owner marks somebody for work and chooses, by hand, the two
     selections that say what they say by being ABSENT */
  edit((d) => ({ ...d, to: [withDecision(withDecision(worker(), 'consent'), 'followUp')] }))
  /* ... and the answer arrives now */
  R.act(() => { binding.saw(BRAIN_A) })
  eq(seen.draft.askMentis, ALL, 'the draft itself is filled in when the answer arrives')
  is(seen.draft.to[0].consent, undefined, 'the explicit "Ask for permission" stands: it is not filled in')
  is(seen.draft.to[0].followUp, undefined, 'and so does "Asks before pursuing side work"')
  is(seen.draft.to[0].coordinate, true, 'what the owner said nothing about is filled in, as populate does')
  const one = bodyOf(seen.sending, OWNER_A, []).dispatch[0]
  no('consent' in one, 'so the dispatch asks for permission, as the owner chose')
  no('follow_up' in one, 'and asks before pursuing side work')
  is(one.coordinate, true, 'while carrying what was filled in')
  /* AN EXPLICIT "DOES THIS WORK ONLY" IS A VALUE, and is equally kept. */
  const narrow = mount({ storage, binding, draft: { ...emptyDraft(), to: [withDecision(worker({ coordinate: false }), 'coordinate')] } })
  is(narrow.seen.draft.to[0].coordinate, false, 'the owner narrowing authority is never widened by the default')
}

/* ======================================================================== *
 * 8. B5 -- A COMPOSER ON A PAGE THAT DOES NOT BIND ITSELF
 *    (a workspace's ask is drawn by the older Fluid shell, which binds to no
 *     Brain -- and a preference kept per Brain cannot be read without one)
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  let asks = 0
  const confirm = async () => { asks += 1; binding.saw(BRAIN_A); return true }
  const { seen } = mount({ storage, binding, confirm })
  is(asks, 1, 'the composer asks which Brain the server serves, once')
  is(seen.scope, SCOPE_A, 'and so has a scope on a page that never bound itself')
  eq(seen.draft.askMentis, ALL, 'new Work started from there is filled in like any other')
  eq(sent(seen), { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, follow_up: { depth: 1 } },
    'and its submission carries the three concrete values')
  /* NOT ASKED WHERE IT WOULD BE POINTLESS OR UNWANTED */
  const bound = createBinding()
  bound.saw(BRAIN_A)
  let more = 0
  mount({ storage, binding: bound, confirm: async () => { more += 1; return true } })
  is(more, 0, 'a page that has already bound itself is not asked again')
  const off = createBinding()
  let never = 0
  mount({ storage, binding: off, enabled: false, confirm: async () => { never += 1; return true } })
  is(never, 0, 'and a composer that offers none of these controls asks nothing')
  is(off.bound(), null, 'leaving that page exactly as it was')
}

/* ======================================================================== *
 * 9. WITH NOTHING SAVED, EVERY PATH IS EXACTLY AS IT WAS
 * ======================================================================== */
{
  const storage = bag()
  const binding = createBinding()
  binding.saw(BRAIN_A)
  const { seen, edit } = mount({ storage, binding })
  is(seen.saved.state, 'none', 'nothing is saved for this Brain and owner')
  no(seen.draft.seeded, 'so nothing is filled in')
  is(seen.draft.askMentis, undefined, 'and the draft holds no selections')
  edit((d) => ({ ...d, text: 'do the thing', to: [worker()] }))
  const body = bodyOf(seen.sending, OWNER_A, [])
  no('ask_mentis' in body, 'the submission is what it was before any of this existed')
  eq(body.dispatch[0].consent, undefined, 'and nobody marked for work is handed a Permission Mode')
  is(body.dispatch[0].coordinate, false, 'nobody coordinates unless the owner grants it')
}

/* ======================================================================== *
 * 10. SAVING AND CLEARING FROM THE PANEL
 * ======================================================================== */
{
  const storage = bag()
  const binding = createBinding()
  binding.saw(BRAIN_A)
  const { seen, edit } = mount({ storage, binding })
  edit((d) => ({ ...d, seeded: true, seededIn: SCOPE_A, askMentis: { ...TASK, decided: ['consent'] } }))
  R.act(() => { seen.preference.save() })
  is(seen.saved.state, 'saved', 'what the panel chose is saved for this Brain and owner')
  eq(seen.saved.saved, TASK, 'as the three selections and nothing else: a decision is not part of a saved configuration')
  ok(seen.preference.matches, 'and the panel says that what is saved is what is chosen')
  R.act(() => { seen.preference.clear() })
  is(seen.saved.state, 'none', 'and clearing it leaves nothing saved')
  is(storage.getItem('mentis.fluid.permission-default'), null, 'nothing of it is left in the browser')
}

/* ======================================================================== *
 * 11. B1 -- SEND PRESSED BEFORE THE PAGE CAN SAY WHERE IT IS GOING
 *
 * THE DEFECT THE FOCUSED RE-REVIEW REPRODUCED (adm-871e7b570a26). Taking the
 * filled-in default back out of the DRAFT when the answer arrives is not
 * enough: the Brain is answered after the composer mounts, Send can be
 * pressed while that answer is pending, and the body is built and serialised
 * THEN. The page's write guard waits for the binding and names the Brain in
 * a header it adds to that already built body -- so the write left naming
 * one Brain and carrying the other's Allow All, coordination and side-work
 * depth, in the generic, the named and the workspace cases alike.
 *
 * So a submission asks where it is going BEFORE it is built, and is placed
 * against the answer. Each case here holds the answer pending, presses Send
 * in that window, and releases it afterwards.
 * ======================================================================== */
{
  /** A BRAIN ANSWER THE TEST RELEASES ITSELF. Every ask the page makes is
   *  pending until `answer`, and asks made after it are answered at once --
   *  which is what a server that was slow and then replied does. `brain` null
   *  is a server that cannot say which Brain it serves. */
  const held = (binding, brain) => {
    let open = false
    let waiting = []
    let asks = 0
    const say = () => { if (brain) binding.saw(brain); return brain ? true : null }
    const confirm = () => {
      asks += 1
      if (open) return Promise.resolve(say())
      return new Promise((res) => { waiting.push(() => res(say())) })
    }
    const answer = () => { open = true; const w = waiting; waiting = []; w.forEach((f) => f()) }
    return { confirm, answer, asked: () => asks }
  }
  /** SEND, in the window before the answer: the submission is asked for, the
   *  answer is released, and what it came to is settled. */
  const send = async (seen, answer, draft) => {
    const asked = seen.place(draft ?? seen.draft)
    answer()
    const ready = await asked
    R.act(() => {})
    return ready
  }
  const WORDS = 'look at the overnight run'
  /** the draft the tab kept, filled in on Brain A and reloaded on another */
  const keptOnA = (over = {}) => ({
    ...emptyDraft(), text: WORDS, restored: true, seeded: true, seededIn: SCOPE_A, askMentis: { ...ALL }, ...over,
  })

  /* -- GENERIC (Ask Mentis): another Brain answers while Send is pressed --- */
  {
    const storage = bag()
    saveDefault(SCOPE_A, ALL, storage, 1000)
    const binding = createBinding()
    const brain = held(binding, BRAIN_B)
    const { seen } = mount({ storage, binding, draft: keptOnA(), confirm: brain.confirm })
    is(seen.scope, undefined, 'the page cannot yet say which Brain it is on')
    eq(seen.draft.askMentis, ALL, 'and the draft still holds what was filled in on the Brain it was written on')
    const ready = await send(seen, brain.answer)
    ok(ready.ok, 'the submission is placed once the page can say where it is going')
    is(ready.scope, `${BRAIN_B}|${OWNER_A}`, 'against the Brain and owner it is actually recorded for')
    is(bodyOf(ready.draft, OWNER_A, []).ask_mentis, undefined,
      'and carries no Allow All, no coordination and no side-work depth into that Brain\'s Work')
    is(ready.draft.text, WORDS, 'the words the owner wrote are sent as they were')
    is(seen.draft.text, WORDS, 'and are still in the draft')
  }

  /* -- NAMED: a recipient that took a copy carries none of it either ------- */
  {
    const storage = bag()
    saveDefault(SCOPE_A, ALL, storage, 1000)
    const binding = createBinding()
    const brain = held(binding, BRAIN_B)
    const draft = keptOnA({ to: [worker({ ...ALL, seeded: true })] })
    const { seen } = mount({ storage, binding, draft, confirm: brain.confirm })
    eq(seen.draft.to[0].consent, ALL.consent, 'the named recipient still holds the copy it took on the other Brain')
    const ready = await send(seen, brain.answer)
    ok(ready.ok, 'the named submission is placed too')
    const one = bodyOf(ready.draft, OWNER_A, []).dispatch[0]
    no('consent' in one, 'and what it asks of that recipient carries no Permission Mode')
    no('follow_up' in one, 'no side-work permission')
    is(one.coordinate, false, 'and no authority to coordinate')
    is(ready.draft.to[0].alias, '@Worker', 'while the recipient themselves is untouched')
  }

  /* -- THE SAME SCOPE STANDS: a late answer is not a reason to narrow ------ */
  {
    const storage = bag()
    saveDefault(SCOPE_A, ALL, storage, 1000)
    const binding = createBinding()
    const brain = held(binding, BRAIN_A)
    const { seen } = mount({ storage, binding, draft: keptOnA(), confirm: brain.confirm })
    const ready = await send(seen, brain.answer)
    ok(ready.ok, 'the answer names the Brain the draft was filled in on')
    is(ready.scope, SCOPE_A, 'which is where this submission is recorded')
    eq(bodyOf(ready.draft, OWNER_A, []).ask_mentis,
      { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, follow_up: { depth: 1 } },
      'so what the owner has been looking at is exactly what is sent')
  }

  /* -- NO ANSWER AT ALL: NOT SENT, and nothing of the owner's is lost ----- */
  {
    const storage = bag()
    saveDefault(SCOPE_A, ALL, storage, 1000)
    const binding = createBinding()
    const brain = held(binding, null)
    const { seen } = mount({ storage, binding, draft: keptOnA(), confirm: brain.confirm })
    const ready = await send(seen, brain.answer)
    no(ready.ok, 'a submission the page cannot place is not sent')
    is(ready.why, UNPLACED_SEND, 'and says so, rather than being sent to whichever Brain answers next')
    is(seen.draft.text, WORDS, 'the words the owner wrote are kept')
    is(seen.draft.askMentis, undefined, 'and what was filled in is taken out of the draft as it is refused')
    no(seen.draft.seeded, 'so the controls say what the next send would carry')
    /* and that next send goes, carrying nothing of anybody's default */
    const again = await send(seen, brain.answer)
    ok(again.ok, 'pressing Send again sends what the controls now say')
    is(bodyOf(again.draft, OWNER_A, []).ask_mentis, undefined, 'which is no permission selection at all')
  }

  /* -- A PAGE THAT HAS MOVED places nothing, and asks nobody -------------- */
  {
    const storage = bag()
    saveDefault(SCOPE_A, ALL, storage, 1000)
    const binding = createBinding()
    binding.saw(BRAIN_A)
    const brain = held(binding, BRAIN_A)
    const { seen } = mount({ storage, binding, confirm: brain.confirm })
    eq(seen.draft.askMentis, ALL, 'filled in while the page was on its own Brain')
    R.act(() => { binding.saw(BRAIN_B) })
    const ready = await seen.place(seen.draft)
    R.act(() => {})
    ok(ready.ok, 'what the draft holds after moving is sent: it holds nothing of the default')
    is(bodyOf(ready.draft, OWNER_A, []).ask_mentis, undefined, 'so the submission carries none of it')
    /* AND A DRAFT THE PAGE HAS NOT CAUGHT UP WITH IS NOT SENT AT ALL: a moved
       page has no Brain to place anything against. */
    const stale = await seen.place(keptOnA())
    R.act(() => {})
    no(stale.ok, 'a submission still holding what was filled in is not sent from a moved page')
    is(stale.why, UNPLACED_SEND, 'and says why')
    is(brain.asked(), 0, 'while the server is asked nothing to know any of it')
  }

  /* -- NOTHING FILLED IN: sent as it always was, and nothing is asked ----- */
  {
    const storage = bag()
    const binding = createBinding()
    const brain = held(binding, BRAIN_A)
    const { seen, edit } = mount({ storage, binding, confirm: brain.confirm })
    edit((d) => ({ ...d, text: 'do the thing' }))
    const asks = brain.asked()
    const ready = await seen.place(seen.draft)
    R.act(() => {})
    ok(ready.ok, 'a draft nothing was filled into is sent')
    no('ask_mentis' in bodyOf(ready.draft, OWNER_A, []), 'exactly as it was sent before any of this existed')
    is(brain.asked(), asks, 'and the server is asked nothing to establish that')
  }
}

R.unmount()
console.log(`permission default lifecycle: ${checks} checks ok`)
