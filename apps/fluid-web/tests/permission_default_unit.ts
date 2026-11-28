/* ONE SAVED PERMISSION CONFIGURATION, IN THIS BROWSER (owner approval
 * ent-89b5beaf5e39 over the narrowed proposal ent-84bcc33c26bb and its
 * independent review ent-4a7b44c21acb), checked without a browser:
 *
 *   - saved, read back, replaced and cleared, scoped to this Brain AND this
 *     owner, with another scope's configuration left exactly as it was;
 *   - MALFORMED SAVED DATA IS UNAVAILABLE and never widens anything: no
 *     reading failure ever produces "Allow all operations";
 *   - A FAILED SAVE IS REPORTED, including the store that accepts a write
 *     and keeps nothing;
 *   - POPULATE, NEVER OVERRIDE, in independent copies per recipient;
 *   - the submission seam: `ask_mentis` carries the existing consent shape,
 *     three-valued `coordinate` and `follow_up`, only under Ask Mentis, and a
 *     draft that holds none of it posts exactly what it posted before;
 *   - a draft holding only permissions is kept for the tab yet still has
 *     nothing to send;
 *   - and the composer's wiring, read from its source: the Brain and the
 *     owner are subscribed to rather than read once, populating happens once
 *     on a fresh non-reply draft, and the generic entry opens the same panel.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  DEFAULT_LIMITS, NOTHING_TO_SAVE_WHY, NOT_BOUND_WHY, OTHER_VERSION_WHY, PERMISSION_DEFAULT_KEY, UNREADABLE_WHY,
  askOf, chosenWords, clearDefault, decidedOn, forScope, holdsNothing, leftFreshWork, onlyDecided, populate,
  readDefault, readable, sameAs, saveDefault, savedOf, says, scopeOf, seedAddressees, seedInto, seedable, withDecision,
  type SavedPermissions,
} from '../src/fluid/composer/permissionDefault'
import { askMentisSpec, bodyOf, consentSpec, emptyDraft, isEmpty, type Addressee, type Draft, type PermissionField } from '../src/composer/draft'
import { dropDraft, keptDraft, loadDraft, saveDraft } from '../src/fluid/composer/drafts'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = (p: string) => readFileSync(new URL('../src/' + p, import.meta.url), 'utf8')

/* A store of the shape the page uses, so nothing here touches a real browser. */
interface Bag extends Storage { bag: Record<string, string> }
function store(seed: Record<string, string> = {}): Bag {
  const bag: Record<string, string> = { ...seed }
  return {
    bag,
    get length() { return Object.keys(bag).length },
    clear() { for (const k of Object.keys(bag)) delete bag[k] },
    getItem: (k: string) => (k in bag ? bag[k] : null),
    key: (i: number) => Object.keys(bag)[i] ?? null,
    removeItem: (k: string) => { delete bag[k] },
    setItem: (k: string, v: string) => { bag[k] = String(v) },
  } as Bag
}
const kept = (s: Bag) => (s.bag[PERMISSION_DEFAULT_KEY] ? JSON.parse(s.bag[PERMISSION_DEFAULT_KEY]) : null)

const BRAIN = 'corpus-1@a1b2c3d4e5f60718'
const OTHER_BRAIN = 'corpus-1@9f8e7d6c5b4a3921'
const ME = 'ent-owner'
const SCOPE = scopeOf(BRAIN, ME)!
const ALL: SavedPermissions = { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, followUp: 1 }
/** somebody marked for work, as a draft holds them */
const worker = (over: Partial<Addressee> = {}): Addressee => ({ participant: 'ent-worker', alias: '@Worker', dispatch: true, ...over })
/** which fields the owner decided, as the subject carries them */
const byHand = (...fields: PermissionField[]): PermissionField[] => fields

/* -- WHERE A CONFIGURATION BELONGS ---------------------------------------- */
eq(SCOPE, `${BRAIN}|${ME}`, 'the Brain the page is bound to and the owner acting')
eq(scopeOf(null, ME), null, 'no Brain confirmed: no scope, so nothing is read or saved')
eq(scopeOf(BRAIN, null), null, 'no owner known yet: no scope')
eq(scopeOf('', ''), null, 'and nothing at all is not a scope')
eq(readDefault(null, store()), { state: 'none' }, 'with no scope there is no default, whatever is in the browser')

/* -- SAVED, READ BACK, REPLACED, CLEARED ---------------------------------- */
{
  const s = store()
  eq(readDefault(SCOPE, s), { state: 'none' }, 'nothing saved: no default, and the composer is as it was')
  eq(saveDefault(SCOPE, ALL, s, 1000), { ok: true }, 'the owner saves what they chose')
  const read = readDefault(SCOPE, s)
  eq(read, { state: 'saved', saved: ALL, at: 1000 }, 'and it reads back exactly, with when it was saved')
  eq(kept(s).version, 1, 'kept under a version')
  /* ANOTHER BRAIN, OR ANOTHER OWNER, IS NOT THIS ONE */
  eq(readDefault(scopeOf(OTHER_BRAIN, ME), s), { state: 'none' }, 'a copy of the Brain served from elsewhere has no default here')
  eq(readDefault(scopeOf(BRAIN, 'ent-someone-else'), s), { state: 'none' }, 'nor another owner')
  /* REPLACED, the other scope untouched */
  const otherScope = scopeOf(OTHER_BRAIN, ME)!
  eq(saveDefault(otherScope, { coordinate: false }, s, 1001), { ok: true }, 'another Brain saves its own')
  eq(saveDefault(SCOPE, { followUp: 'unrestricted' }, s, 1002), { ok: true }, 'and this one is replaced')
  eq((readDefault(SCOPE, s) as { saved: SavedPermissions }).saved, { followUp: 'unrestricted' }, 'this scope holds only the newer configuration')
  eq((readDefault(otherScope, s) as { saved: SavedPermissions }).saved, { coordinate: false }, "and the other scope's is exactly as it was")
  /* CLEARED, the other scope untouched */
  eq(clearDefault(SCOPE, s), { ok: true }, 'cleared')
  eq(readDefault(SCOPE, s), { state: 'none' }, 'and there is no default again')
  eq((readDefault(otherScope, s) as { saved: SavedPermissions }).saved, { coordinate: false }, 'clearing one scope leaves the other')
  eq(clearDefault(SCOPE, s), { ok: true }, 'clearing what is already clear is the state asked for, not a failure')
  eq(clearDefault(otherScope, s), { ok: true }, 'the last one goes too')
  eq(kept(s), null, 'and nothing is left behind in the browser')
}

/* -- MALFORMED SAVED DATA IS UNAVAILABLE, NEVER WIDENED ------------------- */
{
  const unreadable = (raw: string, what: string, why = UNREADABLE_WHY) => {
    const r = readDefault(SCOPE, store({ [PERMISSION_DEFAULT_KEY]: raw }))
    eq(r, { state: 'unreadable', why }, what)
  }
  const wrapped = (saved: unknown) => JSON.stringify({ version: 1, by: { [SCOPE]: { saved, at: 1 } } })
  unreadable('{not json', 'what is not JSON at all')
  unreadable('"a string"', 'what is not an object')
  unreadable('[]', 'an array')
  unreadable(JSON.stringify({ version: 1 }), 'a payload with no configurations in it')
  unreadable(JSON.stringify({ version: 1, by: [] }), 'configurations that are not keyed')
  unreadable(JSON.stringify({ version: 2, by: { [SCOPE]: { saved: ALL } } }), 'a later version of this page', OTHER_VERSION_WHY)
  unreadable(JSON.stringify({ by: { [SCOPE]: { saved: ALL } } }), 'no version at all')
  unreadable(JSON.stringify({ version: 1, by: { [SCOPE]: ALL } }), 'an entry of the wrong shape')
  unreadable(wrapped({}), 'a configuration that says nothing')
  unreadable(wrapped({ consent: { mode: 'everything', workspaces: [] } }), 'a Permission Mode that is not one')
  unreadable(wrapped({ consent: { mode: 'ask', workspaces: [] } }), 'a saved "ask", which is the absence of a consent')
  unreadable(wrapped({ consent: { mode: 'all' } }), 'a consent with no workspaces field')
  unreadable(wrapped({ consent: { mode: 'all', workspaces: 'C:\\Work' } }), 'workspaces that are not a list')
  unreadable(wrapped({ consent: { mode: 'all', workspaces: [7] } }), 'a workspace that is not text')
  unreadable(wrapped({ consent: { mode: 'all', workspaces: ['src'] } }), 'a workspace that is not an absolute directory')
  unreadable(wrapped({ consent: { mode: 'task', workspaces: [], extra: ['rm -rf'] } }), 'a category nobody offers')
  unreadable(wrapped({ consent: { mode: 'task', workspaces: [], extra: 'network' } }), 'categories that are not a list')
  unreadable(wrapped({ coordinate: 'yes' }), 'an authority that is not a yes or a no')
  unreadable(wrapped({ followUp: 0 }), 'a side-work depth of nothing')
  unreadable(wrapped({ followUp: 1.5 }), 'a depth that is not a whole number')
  unreadable(wrapped({ followUp: 'everything' }), 'a side-work permission that is not one')
  /* THE POINT OF ALL OF THAT: nothing unreadable ever arrives as a permission */
  for (const raw of ['{not json', wrapped({ consent: { mode: 'all', workspaces: ['src'] } }), wrapped({ consent: { mode: 'everything', workspaces: [] } })]) {
    const r = readDefault(SCOPE, store({ [PERMISSION_DEFAULT_KEY]: raw }))
    eq(r.state, 'unreadable', 'unreadable')
    ok(!('saved' in r), 'and carries no configuration at all: a fresh draft is populated with nothing')
  }
  /* readable() itself, which is what both directions go through */
  eq(readable({ consent: { mode: 'task', workspaces: [' C:\\Work\\Mentis ', ''], extra: ['network', 'network'] } }),
    { consent: { mode: 'task', workspaces: ['C:\\Work\\Mentis'], extra: ['network'] } },
    'a workspace is trimmed, a blank line dropped, a category counted once')
  eq(readable({ consent: { mode: 'deny', workspaces: ['/srv/mentis'] } }), { consent: { mode: 'deny', workspaces: ['/srv/mentis'] } },
    'an absolute directory the other way round is one too')
  eq(readable({ coordinate: false }), { coordinate: false }, '"does this work only" is a value, not an absence')
  eq(says({}), false, 'a configuration that says nothing says nothing')
  eq(says({ coordinate: false }), true, 'and saying "no" is saying something')
}

/* -- A FAILED SAVE IS REPORTED -------------------------------------------- */
{
  const s = store()
  const bad = saveDefault(SCOPE, { consent: { mode: 'all', workspaces: ['relative/dir'] } }, s)
  eq(bad.ok, false, 'a workspace that is not absolute is refused before it is written')
  ok(!bad.ok && /relative\/dir/.test(bad.why), 'and the owner is told which one')
  eq(kept(s), null, 'nothing was written')
  const nothing = saveDefault(SCOPE, {}, s)
  eq(nothing, { ok: false, why: NOTHING_TO_SAVE_WHY }, 'there is nothing to save in the defaults themselves')
  eq(saveDefault(null, ALL, s), { ok: false, why: NOT_BOUND_WHY },
    'and with no Brain confirmed nothing is saved, said in so many words')
  ok(/which Brain/.test(NOT_BOUND_WHY), 'which says which Brain is the thing it cannot say')
  /* a store that refuses */
  const refuses = store()
  refuses.setItem = () => { throw new Error('QuotaExceededError') }
  const full = saveDefault(SCOPE, ALL, refuses)
  eq(full.ok, false, 'a browser that will not keep it is a failure')
  ok(!full.ok && /QuotaExceededError/.test(full.why), 'reported with what it said')
  /* THE QUIET ONE: a store that accepts the write and keeps nothing */
  const drops = store()
  drops.setItem = () => {}
  eq(saveDefault(SCOPE, ALL, drops).ok, false, 'a store that accepts a write and keeps nothing is caught by reading it back')
  eq(readDefault(SCOPE, drops), { state: 'none' }, 'and no default is claimed')
  /* clearing an unreadable payload removes the whole of it */
  const corrupt = store({ [PERMISSION_DEFAULT_KEY]: '{not json' })
  eq(clearDefault(SCOPE, corrupt), { ok: true }, 'what cannot be read can still be cleared')
  eq(kept(corrupt), null, 'and all of it goes')
  /* saving over an unreadable payload replaces it rather than being stuck */
  const over = store({ [PERMISSION_DEFAULT_KEY]: '{not json' })
  eq(saveDefault(SCOPE, ALL, over, 5), { ok: true }, 'and saving over it works')
  eq((readDefault(SCOPE, over) as { saved: SavedPermissions }).saved, ALL, 'with the new configuration readable')
}

/* -- POPULATE, NEVER OVERRIDE, IN INDEPENDENT COPIES ---------------------- */
{
  const saved: SavedPermissions = { consent: { mode: 'task', workspaces: ['C:\\Work\\Mentis'], extra: ['network'] }, coordinate: true, followUp: 2 }
  const fresh = populate<Addressee>({ participant: 'ent-a', alias: '@Vera', dispatch: true }, saved)
  eq(fresh.consent, saved.consent, 'somebody newly marked for work is populated with the saved consent')
  eq([fresh.coordinate, fresh.followUp], [true, 2], 'with the authority and the side-work permission')
  ok(fresh.consent !== saved.consent, 'as its own copy')
  ok(fresh.consent!.workspaces !== saved.consent!.workspaces, 'and its own workspaces: two recipients never share one list')
  fresh.consent!.workspaces.push('C:\\Work\\MARS')
  eq(saved.consent!.workspaces, ['C:\\Work\\Mentis'], 'so editing one changes nothing else')
  /* WHAT THE OWNER HAS DECIDED STAYS DECIDED */
  const edited = populate<Addressee>({ participant: 'ent-b', alias: '@Quill', dispatch: true, consent: { mode: 'deny', workspaces: [] }, coordinate: false, followUp: undefined }, saved)
  eq(edited.consent, { mode: 'deny', workspaces: [] }, 'an explicit Permission Mode is not replaced by the default')
  eq(edited.coordinate, false, '"does this work only" is an answer and is kept')
  eq(edited.followUp, 2, 'and only what was never chosen is filled in')
  /* an addressee only addressed is not dispatched work; the composer decides
     that, and `populate` is only ever handed what it should fill in */
  eq(populate<Addressee>({ participant: 'ent-c', alias: '@Mo', dispatch: true }, {}), { participant: 'ent-c', alias: '@Mo', dispatch: true },
    'a configuration that says nothing populates nothing')
  /* what the panel hands back to be saved: the three selections and no more */
  eq(savedOf({ ...(fresh as SavedPermissions) }), { consent: { mode: 'task', workspaces: ['C:\\Work\\Mentis', 'C:\\Work\\MARS'], extra: ['network'] }, coordinate: true, followUp: 2 },
    'saving takes the permissions off whatever holds them')
  eq(savedOf({ consent: { mode: 'all', workspaces: [], extra: [] } }), { consent: { mode: 'all', workspaces: [] } }, 'an empty category list is nothing said')
  ok(sameAs({ consent: { mode: 'all', workspaces: [], extra: [] } }, { consent: { mode: 'all', workspaces: [] } }), 'and the two are the same configuration')
  ok(!sameAs(ALL, { ...ALL, coordinate: false }), 'a different authority is a different configuration')
  const into = seedInto(emptyDraft(), saved, SCOPE)
  eq(into.askMentis, saved, 'a fresh draft takes the same three for ordinary Ask Mentis')
  ok(into.askMentis !== saved, 'as its own copy')
  ok(into.askMentis!.consent !== saved.consent, 'with its own workspaces, shared with nothing')
}

/* -- WHAT THE CONTROL SAYS IT CARRIES ------------------------------------- */
eq(chosenWords({}), 'Ask for permission · asks before side work', 'nothing chosen is said as what it is, never as blank')
eq(chosenWords(ALL), 'Allow all operations · may coordinate · side work 1 generation deep', 'and what is chosen is said in the same words the rows use')
eq(chosenWords({ consent: { mode: 'deny', workspaces: [] }, coordinate: false }), 'Never wait for me · this work only · asks before side work',
  'with the mode\'s parenthetical left to the row that explains it')
ok(/this browser only/.test(DEFAULT_LIMITS) && /backup will not bring it back/.test(DEFAULT_LIMITS), 'the browser-local limits are said, not hidden')

/* -- THE SUBMISSION SEAM: body.ask_mentis --------------------------------- */
{
  const d = (over: Partial<Draft> = {}): Draft => ({ ...emptyDraft(), ...over })
  /* EXISTING BEHAVIOUR IS UNTOUCHED: a draft that holds no selections */
  const plain = bodyOf(d({ text: 'do the thing' }), 'ent-owner', [])
  ok(!('ask_mentis' in plain), 'a draft with no permission selections posts exactly what it posted before')
  eq(plain.action, 'ask-mentis', 'and still asks Mentis')
  /* the three selections, in the shapes a dispatch already uses */
  const chose = { consent: { mode: 'all' as const, workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, followUp: 1 }
  const body = bodyOf(d({ text: 'do it', askMentis: chose }), 'ent-owner', []) as Record<string, unknown>
  eq(body.ask_mentis, { consent: consentSpec(chose.consent), coordinate: true, follow_up: { depth: 1 } },
    'Ask Mentis carries the existing consent shape, the authority and the side-work permission')
  eq((body.ask_mentis as { consent: unknown }).consent, { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, 'the consent is the one a named dispatch sends')
  /* THE SAME STRUCTURES AS A NAMED DISPATCH, not a second shape */
  const named = bodyOf(d({ text: 'do it', to: [{ participant: 'ent-a', alias: '@Vera', dispatch: true, ...chose }] }), 'ent-owner', []) as Record<string, unknown>
  const one = (named.dispatch as Record<string, unknown>[])[0]
  eq((body.ask_mentis as Record<string, unknown>).consent, one.consent, 'the consent a named request sends and the one Ask Mentis sends are one shape')
  eq((body.ask_mentis as Record<string, unknown>).follow_up, one.follow_up, 'and so is the side-work permission')
  ok(!('ask_mentis' in named), 'and a named request carries none of it: each dispatch carries its own')
  /* THREE-VALUED AUTHORITY */
  const absent = bodyOf(d({ text: 'x', askMentis: { consent: chose.consent } }), 'ent-owner', []) as Record<string, unknown>
  ok(!('coordinate' in (absent.ask_mentis as object)), 'nothing said about authority sends nothing: Ask Mentis organises work as it always has')
  const off = bodyOf(d({ text: 'x', askMentis: { coordinate: false } }), 'ent-owner', []) as Record<string, unknown>
  eq(off.ask_mentis, { coordinate: false }, 'and the owner narrowing it is sent, not read as nothing chosen')
  eq(askMentisSpec({ followUp: 'unrestricted' }), { follow_up: 'unrestricted' }, 'side work with no limit, as a request already says it')
  eq(askMentisSpec({}), {}, 'nothing chosen is an empty selection')
  /* A REPLY MAY CHANGE PERMISSIONS (owner, 2026-11-28): "Ask", chosen there,
     narrows what the continued work carried, so it is said; on new Work it
     stays unsaid, as before. */
  const asked: PermissionField[] = ['consent', 'followUp']
  eq(askMentisSpec({ decided: asked }), {}, 'on new Work a chosen Ask is unsaid')
  eq(askMentisSpec({ decided: asked }, true), { consent: { mode: 'ask', workspaces: [] }, follow_up: 'ask' },
    'on a reply a chosen Ask is sent')
  eq(askMentisSpec({}, true), {}, 'and on a reply nothing chosen is still nothing sent')
  const narrowed = bodyOf(d({ text: 'x', to: [{ participant: 'ent-a', alias: '@Vera', dispatch: true, decided: asked }] }),
    'ent-owner', [], 'record-only', { continuing: true }) as { dispatch: Record<string, unknown>[] }
  eq([narrowed.dispatch[0].consent, narrowed.dispatch[0].follow_up], [{ mode: 'ask', workspaces: [] }, 'ask'],
    'a named continuation carries the Ask the owner chose')
  const widened = bodyOf(d({ text: 'x', to: [{ participant: 'ent-a', alias: '@Vera', dispatch: true, followUp: 2,
    consent: { mode: 'task', workspaces: ['C:\w'] } }] }), 'ent-owner', [], 'record-only', { continuing: true }) as { dispatch: Record<string, unknown>[] }
  eq([widened.dispatch[0].consent, widened.dispatch[0].follow_up], [{ mode: 'task', workspaces: ['C:\w'] }, { depth: 2 }],
    'and a wider choice exactly as on new Work')
  /* ONLY UNDER ASK MENTIS */
  const recorded = bodyOf(d({ text: 'x', action: 'record-only', askMentis: chose }), 'ent-owner', [])
  ok(!('ask_mentis' in recorded), 'record-only sends none of it: nothing is owed and nothing runs')
  eq(recorded.dispatch, [], 'as it dispatches nothing')
  const toSomebody = bodyOf(d({ text: 'x', askMentis: chose, to: [{ participant: 'ent-a', alias: '@Vera', dispatch: true }] }), 'ent-owner', [])
  ok(!('ask_mentis' in toSomebody), 'somebody marked for work is asked instead, and the Ask Mentis selections are not sent')
  const seeded = bodyOf(d({ text: 'x', seeded: true, askMentis: {} }), 'ent-owner', [])
  ok(!('ask_mentis' in seeded), 'a draft populated with nothing sends nothing: unsaid stays unsaid')
  /* WHAT THE COMPOSER KEEPS FOR ITSELF IS NEVER SENT. Which Brain and owner a
     default was filled in for, which fields the owner decided, whether a
     draft was restored and who has taken a copy are all how the composer
     decides what to show; the submission carries the same concrete fields it
     carried before (the contract the intake seam reads). */
  const bare = bodyOf(d({ text: 'x', askMentis: chose, to: [worker()] }), 'ent-owner', [])
  const marked = bodyOf(d({
    text: 'x', restored: true, seeded: true, seededIn: SCOPE,
    askMentis: { ...chose, decided: byHand('consent') },
    to: [worker({ seeded: true, decided: byHand('coordinate') })],
  }), 'ent-owner', [])
  eq(Object.keys(marked).sort(), Object.keys(bare).sort(), 'a marked-up draft posts the same fields as a bare one')
  eq(marked.dispatch, bare.dispatch, 'and the same dispatch, exactly')
  eq(Object.keys(marked.dispatch[0] as object).filter((k) => /decided|seeded|restored/.test(k)), [],
    'no bookkeeping of the composer\'s reaches a dispatch')
}

/* -- A DRAFT HOLDING ONLY PERMISSIONS ------------------------------------- */
{
  const bag = store()
  ;(globalThis as { sessionStorage?: Storage }).sessionStorage = bag
  const where = 'conversation:ent-conv'
  const only: Draft = { ...emptyDraft(), seeded: true, askMentis: { consent: { mode: 'all', workspaces: [] }, coordinate: true } }
  ok(isEmpty(only), 'a draft holding only permissions still has nothing to send: Send stays disabled and the composer stays closed')
  saveDraft(where, only)
  ok(bag.bag['mentis:fluid:draft:' + where], 'it is kept for the tab all the same')
  dropDraft(where)
  ;(globalThis as { sessionStorage?: Storage }).sessionStorage = store({ ['mentis:fluid:draft:' + where]: JSON.stringify(only) })
  const back = loadDraft(where)
  eq([back.seeded, back.askMentis], [true, only.askMentis], 'so a reload restores what it was populated with, rather than taking whatever is saved now')
  saveDraft(where, emptyDraft())
  eq(loadDraft(where), emptyDraft(), 'and an empty draft keeps nothing, as before')
  delete (globalThis as { sessionStorage?: Storage }).sessionStorage
}

/* -- WHAT THE OWNER DECIDED BY HAND (review adm-232c2d36269e, B4) ---------
   Two of the three selections say what they say by being ABSENT, so which of
   them the owner decided is kept beside them -- otherwise a default arriving
   after the choice reads the choice as "nothing chosen". */
{
  const asked = withDecision<Addressee>(worker(), 'consent')
  ok(decidedOn(asked, 'consent'), 'choosing a Permission Mode row records that the owner decided it')
  ok(!decidedOn(asked, 'followUp'), 'and records nothing about a row they did not touch')
  eq(withDecision(asked, 'consent'), asked, 'deciding the same field twice is the same subject')
  eq(withDecision(asked, 'followUp').decided, ['consent', 'followUp'], 'and each decision is added to the others')
  /* AN EXPLICIT ASK IS NEVER FILLED IN, and nor is an explicit "asks before
     side work"; what the owner said nothing about still is. */
  const kept = populate<Addressee>(withDecision(withDecision(worker(), 'consent'), 'followUp'), ALL)
  eq(kept.consent, undefined, 'an explicit "Ask for permission" stands against the saved default')
  eq(kept.followUp, undefined, 'and so does an explicit "Asks before pursuing side work"')
  eq(kept.coordinate, true, 'while what was never decided is filled in')
  eq(populate<Addressee>(worker(), ALL).consent, ALL.consent, 'and an untouched subject takes the whole of it')
  /* TAKEN BACK OUT: what the default filled in goes, what the owner chose stays */
  eq(onlyDecided({ ...ALL, decided: byHand('coordinate') }), { coordinate: true, decided: ['coordinate'] },
    'only what the owner decided survives the default being taken out')
  eq(onlyDecided({ ...ALL }), {}, 'and a wholly filled-in subject keeps nothing of it')
  eq(onlyDecided({ decided: byHand('consent') }), { decided: ['consent'] }, 'an explicit Ask is a decision and is kept as one')
  /* WHAT IS KEPT IN THE DRAFT AND WHAT IS SAVED ARE NOT THE SAME THING */
  eq(askOf({ ...ALL, decided: byHand('consent') }), { ...ALL, decided: ['consent'] }, 'the draft keeps which fields the owner decided')
  eq(savedOf({ ...ALL, decided: byHand('consent') } as SavedPermissions), ALL, 'a saved configuration holds no decisions: everything in it was chosen')
}

/* -- WHAT A DRAFT DOES WITH THE DEFAULT, each rule on its own --------------
   The lifecycle that calls these -- when the Brain answers, when a reply is
   chosen, when a draft is restored -- is driven as behaviour over the real
   hook in tests/permission_lifecycle_unit.mjs; these are the rules it calls. */
{
  const d = (over: Partial<Draft> = {}): Draft => ({ ...emptyDraft(), ...over })
  const filled = (over: Partial<Draft> = {}): Draft => d({ seeded: true, seededIn: SCOPE, askMentis: { ...ALL }, ...over })
  /* WHEN: ONCE, AND INTO A DRAFT STARTED HERE */
  ok(holdsNothing(d()), 'a draft with nothing in it holds nothing')
  ok(!holdsNothing(d({ text: 'half a thought' })), 'words are something')
  ok(!holdsNothing(d({ to: [worker()] })), 'and so is somebody addressed')
  ok(!holdsNothing(d({ topics: ['ent-topic'] })), 'and a Topic chosen')
  ok(!holdsNothing(filled()), 'and permissions already in it')
  ok(seedable(d()), 'a draft started here is filled in')
  ok(!seedable(filled()), 'a draft already filled in is not filled in again')
  ok(!seedable(d({ restored: true, text: 'written before any of this' })), 'a draft the owner left is never filled in')
  ok(seedable(d({ restored: true })), 'but a kept draft holding nothing is still a fresh one')
  const seeded = seedInto(d({ text: 'go' }), ALL, SCOPE)
  eq(seeded.askMentis, ALL, 'filling in puts the saved selections in the draft')
  eq([seeded.seeded, seeded.seededIn], [true, SCOPE], 'marked as filled in, and for which Brain and owner')
  eq(seedInto(d({ askMentis: { coordinate: false, decided: byHand('coordinate') } }), ALL, SCOPE).askMentis,
    { consent: ALL.consent, coordinate: false, followUp: 1, decided: ['coordinate'] }, 'and never over a decision already made here')
  /* WHOSE: NOT ANOTHER BRAIN'S OR OWNER'S (B1) */
  const mine = filled()
  ok(forScope(mine, SCOPE) === mine, 'on the Brain and owner it was filled in for, the draft is untouched')
  const elsewhere = forScope(filled({ text: 'carried words' }), scopeOf(OTHER_BRAIN, ME))
  eq(elsewhere.askMentis, undefined, 'on another Brain, what was filled in is taken out')
  eq([elsewhere.seeded, elsewhere.seededIn], [undefined, undefined], 'and nothing is left marked as filled in')
  eq(elsewhere.text, 'carried words', 'while the words the owner wrote are untouched')
  eq(forScope(filled(), scopeOf(BRAIN, 'ent-someone-else')).askMentis, undefined, 'another owner is another scope')
  eq(forScope(filled(), null).askMentis, undefined, 'and a page with no scope at all carries none of it')
  eq(forScope(filled({ askMentis: { ...ALL, decided: ['consent'] } }), null).askMentis, { consent: ALL.consent, decided: ['consent'] },
    'what the owner decided by hand is theirs and is kept')
  const unmarked = d({ seeded: true, askMentis: { coordinate: false, decided: ['coordinate'] } })
  ok(forScope(unmarked, null) === unmarked, 'a draft chosen on a page that has no Brain to mark it with is left alone')
  /* and nothing of another scope's reaches the submission */
  ok(!('ask_mentis' in bodyOf(forScope(filled({ text: 'x' }), scopeOf(OTHER_BRAIN, ME)), ME, [])),
    'so the body of a draft sent on another Brain carries no permissions')
  /* WHAT: NEW WORK ONLY (B2) */
  const copied = seedAddressees(filled(), true)
  eq(copied.to, [], 'nobody to copy to is nothing to do')
  const withWorker = seedAddressees(filled({ to: [worker()] }), true)
  eq(withWorker.to[0].consent, ALL.consent, 'whoever is marked for work takes a copy')
  ok(withWorker.to[0].consent !== ALL.consent, 'as their own copy, never a shared list')
  ok(withWorker.to[0].seeded, 'marked as having taken it, so it is taken once')
  eq(seedAddressees(filled({ to: [worker()] }), false).to[0].consent, undefined,
    'and where the default does not apply -- a reply, or a composer without these controls -- nobody takes anything')
  eq(seedAddressees(filled({ to: [{ participant: 'ent-x', alias: '@Mo' }] }), true).to[0].consent, undefined,
    'somebody only addressed takes nothing: nothing runs for them')
  const left = leftFreshWork(withWorker)
  eq(left.askMentis, undefined, 'leaving new Work takes the default out of the draft')
  eq([left.to[0].consent, left.to[0].coordinate, left.to[0].followUp], [undefined, undefined, undefined],
    'and out of whoever had taken a copy of it')
  eq(left.to[0].seeded, undefined, 'who is no longer marked as having taken anything')
  const theirs = leftFreshWork(filled({ askMentis: { ...ALL, decided: ['coordinate'] } }))
  eq(theirs.askMentis, { coordinate: true, decided: ['coordinate'] }, 'while what the owner decided by hand survives the boundary')
  const nothingFilled = d({ text: 'a reply' })
  ok(leftFreshWork(nothingFilled) === nothingFilled, 'and a draft nothing was filled into is untouched')
}

/* -- WAS A DRAFT ALREADY HERE? -------------------------------------------- */
{
  const bag = store()
  ;(globalThis as { sessionStorage?: Storage }).sessionStorage = bag
  const where = 'conversation:ent-kept'
  ok(!keptDraft(where), 'nothing kept here: a composer opening here starts a fresh draft')
  saveDraft(where, { ...emptyDraft(), text: 'half a thought' })
  ok(keptDraft(where), 'a draft left here is kept, and a composer opening here restores it')
  dropDraft(where)
  ok(!keptDraft(where), 'and sending it leaves nothing: the next draft is a fresh one')
  delete (globalThis as { sessionStorage?: Storage }).sessionStorage
}

/* -- THE COMPOSER'S OWN GLUE, read from its source ------------------------
   WHAT THESE ARE AND ARE NOT. The lifecycle is no longer read from
   characters: it is mounted and driven in tests/permission_lifecycle_unit.mjs
   (review adm-232c2d36269e, N3 -- source checks passed while B1-B4
   reproduced). What is left here is the composer's wiring to that lifecycle
   -- which prop it hands it, which seam every change to the draft goes
   through, and where the entry is drawn -- each one line, and each one a line
   whose behaviour is checked above or there. */
{
  /* `assert.match` on a whole source file prints the file on a failure, which
     buries what failed; this says what was looked for. */
  const has = (text: string, re: RegExp, what: string) => { assert.ok(re.test(text), what); checks++ }
  const c = src('fluid/Composer.tsx')
  /* WHERE THESE CONTROLS ARE OFFERED: Quiet Chat's composer, and a
     workspace's ask -- which is new original Work drawn in the older
     composer (review adm-232c2d36269e, B5) */
  has(c, /const permissionsHere = !!operations \|\| !!asking/, 'the permission controls are offered in Quiet Chat and in a workspace ask')
  has(c, /const freshWork = !replyTo && !thread\b/, 'new original Work is anything that is not a reply and not in a thread')
  /* THE LIFECYCLE, in one place, given what it needs */
  has(c, /usePermissionDefault\(\{\s*\n\s*enabled: permissionsHere, fresh: freshWork, owner: me, draft, setDraft,/,
    'and one lifecycle is given them, with the draft and the owner')
  /* ONE SEAM for whoever is newly marked for work */
  has(c, /const seedWork = \(d: Draft\): Draft => seedAddressees\(d, permissionsHere && freshWork\)/,
    'a copy of the selections is handed on only where the default applies')
  has(c, /const setDraft = [\s\S]{0,200}?seedWork\(/, 'and every change to the draft goes through that one seam')
  has(c, /setDraftState\(restorable\(where\)\)/, 'a draft already kept here is restored as one')
  /* NOTHING OF ANOTHER SCOPE'S REACHES A SUBMISSION. Both bodies are built
     from a draft PLACED against the scope resolved at submission, and a
     submission the page cannot place is not built at all (focused re-review
     adm-871e7b570a26, B1 -- what the scope is, and what it does to the body,
     are driven in permission_lifecycle_unit and permission_send_unit). */
  eq(c.match(/bodyOf\(/g)?.length, 2, 'the body is built in exactly two places')
  eq(c.match(/await placed\(/g)?.length, 2, 'and each is placed against the scope this submission resolves to first')
  eq(c.match(/if \(!ready\.ok\) \{ setErr\(ready\.why\); return \}/g)?.length, 2,
    'and neither is sent where the page cannot say which Brain and owner it would be recorded for')
  has(c, /const ready = await placed[\s\S]{0,240}?const into = await ensure\(\)/,
    'the ordinary post is placed before anything is written for it')
  /* AND WHAT THE WRITE WILL NAME IS ASKED THERE TOO (re-review R1): a body
     carrying placed values with no Brain to name them is refused before the
     Conversation is made, not left to leave unnamed. Both submissions ask it. */
  eq(c.match(/if \(unnamed\(/g)?.length, 2, 'both submissions ask what their write would name')
  has(c, /if \(unnamed\(ready\.draft, ready\.brain\)\) \{ setErr\(UNNAMED_POST\); return \}\s*\n\s*const into = await ensure\(\)/,
    'and the ordinary post asks it before anything is written for it either')
  /* the generic entry, in both composers, and the same panel both ways */
  has(c, /const askShown = permissionsHere && !closed && words\.action === 'ask-mentis'/,
    'the generic entry is shown wherever Ask Mentis is what sending does, a reply included (owner, 2026-11-28)')
  has(c, /const built = bodyOf\(d, me, d\.topics, fallback, \{ continuing: !freshWork \}\)/,
    'and a reply or a post in a thread is built as continuing work')
  has(c, /\? 'Unchanged' : chosenWords\(draft\.askMentis \?\? \{\}\)/, 'on a reply, nothing chosen reads as unchanged')
  eq(c.match(/\{permEntry\}/g)?.length, 2, 'and is drawn on both composers that start new Work')
  has(c, /<Operations ask who=\{askWho\}/, 'it opens the same panel a named request uses')
  has(c, /preference=\{preferenceFor\(savedOf\(who\)\)\}/, 'the saved default can be set from a named request')
  has(c, /preference=\{preferenceFor\(draft\.askMentis \?\? \{\}\)\}/, 'and from ordinary Ask Mentis')
  /* choosing here settles the draft, marked with the scope it was settled in */
  has(c, /\{ \.\.\.d, seeded: true, seededIn: scope \?\? undefined, askMentis: askOf\(next\) \}/,
    'choosing by hand settles the draft for this Brain and owner, decisions and all')

  const o = src('fluid/composer/Operations.tsx')
  /* EVERY PERMISSION ROW RECORDS THE OWNER'S DECISION (B4): three rows in the
     named panel, three in the generic one, and the two that edit a consent */
  /* three authority options for Ask Mentis, two for a named request, the
     Permission Mode, the workspaces it is within, the categories it also
     counts as routine, and the side-work permission */
  eq(o.match(/decided\(\{ \.\.\.who/g)?.length, 9, 'every permission row records that the owner decided it')
  ok(!/pick: \(\) => choose\(\{ \.\.\.who, (consent|coordinate|followUp)/.test(o), 'and no permission row sets one without recording it')
  const s = src('fluid/composer/Settings.tsx')
  eq(s.match(/withDecision\(\{ \.\.\.who/g)?.length, 5, 'the older settings panel records them too')
  /* THE SAME PERMISSION ROWS, chosen from one piece of code */
  eq(o.match(/key: 'consent'/g)?.length, 1, 'Permission Mode is built once, for named work and for Ask Mentis alike')
  eq(o.match(/key: 'gravity'/g)?.length, 1, 'and so is the side-work permission')
  has(o, /if \(ask \|\| who\.dispatch\) \{\s*\n\s*const consentMode/, 'and both reach those rows')
  /* and nothing about a participant or a runtime in the generic panel */
  has(o, /if \(who\.dispatch && !ask\) \{/, 'runtime, model, effort, Persona and instance are for a named request only')
  has(o, /if \(who\.dispatch && !ask && modes\) \{/, 'and so is Execution Mode')
  has(o, /usePersonaChoices\(!ask\)/, 'the generic panel asks for no Personas')
  has(o, /useDesignations\(ask \? \[\] : \[who\.participant\]\)/, 'and reads nothing about a participant')
  has(o, /if \(!ask\) void rereadDesignation\(who\.participant\)/, 'nor re-reads a designation for a subject that is not one')
  /* three-valued authority there, two-valued for a named dispatch */
  has(o, /name: 'As Mentis organises it', note: 'nothing said'/, "Ask Mentis's authority offers what it has always done")
  has(o, /on: who\.coordinate === false,\s*\n\s*pick: \(\) => choose\(decided\(\{ \.\.\.who, coordinate: false \}, 'coordinate'\)\)/, 'and the owner narrowing it')
  /* the saved default is offered where permissions are chosen, and says what it is */
  has(o, /if \(preference && \(ask \|\| who\.dispatch\)\) \{/, 'the saved default is offered where permissions are chosen')
  has(o, /\{p\.why && <p className="fc-ops-risk" role="alert">\{p\.why\}<\/p>\}/, 'and a browser that would not keep it says so')

  /* the saved selections are permissions and nothing else: no runtime, model,
     effort, Persona, instance or Execution Mode is ever remembered */
  const p = src('fluid/composer/permissionDefault.ts')
  for (const never of ['runtime', 'model', 'effort', 'persona', 'newInstance', 'executionMode', 'executionAck']) {
    ok(!new RegExp(`\\b${never}\\??:`).test(p.replace(/\/\*[\s\S]*?\*\//g, '')), `a saved configuration never holds ${never}`)
  }
}

console.log(`permission default: ${checks} checks ok`)
