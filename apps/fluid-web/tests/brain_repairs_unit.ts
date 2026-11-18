/* THE MANAGE BRAIN FUNCTIONAL REPAIRS (Quiet UI audit, 2026-11-18, release
 * 20261118-638cf44), checked without a server or a browser. Each block names
 * the audit's defect and checks the decision that was wrong, in the module
 * that now makes it:
 *
 *   - Defect 4: a revision that has just been saved holds nothing, so going
 *     on to the new version is not asked about; one that has not been saved
 *     is asked about exactly as before (`creating.heldAfterSave`, with the
 *     page's own registry and question from `leaving.ts`);
 *   - Defect 2: a Kind that requires a basis is created WITH it, the later
 *     `derive-from` is not sent for it, and an empty basis is refused in the
 *     form; a Kind whose basis is optional is sent what it always was;
 *   - Defect 7: every Kind standing applies to starts proposed, through each
 *     of the three doors;
 *   - Defect 3: what the record's menu says while its acts are being read;
 *   - Defect 12: an adoption's "Applies to" lists each choice once.
 *
 * Where the repair is wiring inside a component (Defects 1, 5, 6 and the
 * hosted forms' Cancel), the wiring is checked in the source, as
 * `quiet_nav_unit.ts` does; that it behaves so on screen needs a browser. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { DISCARD, LOST_RECORD, STAY, forgetUnfinished, leaving, tell, unfinished, written } from '../src/quiet2/leaving'
import { ACT_WORDS, actUnsaved } from '../src/surfaces/governance/acting'
import {
  BASIS_NEEDED, basisIds, basisRefusal, citesAfterCreate, entryCreateBody, heldAfterSave, requiresBasis, startsProposed,
} from '../src/surfaces/governance/creating'
import type { KindAuthoring } from '../src/surfaces/governance/r2Model'
import { ACTS_FAILED, ACTS_LOADING, actsPending, scopeChoices } from '../src/quiet2/brain/logic'
import { establishInstructionBody } from '../src/fluid/conversation/instructionsModel'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = (p: string) => readFileSync(fileURLToPath(new URL('../src/' + p, import.meta.url)), 'utf8')

const kind = (name: string, door: 'entry' | 'persona' | 'instruction', more: Partial<KindAuthoring> = {}, standing: boolean | null = true): KindAuthoring => ({
  kind: name, fields: ['text'], meaning: '', standing_apt: standing, expects_falsifier: false,
  authoring: { section: 'x', door, placeable: door !== 'persona', basis: door === 'entry', placement_directs_work: true, standing_apt: standing, expects_falsifier: false },
  ...more,
})
const rule = kind('rule', 'entry')
const decision = kind('decision', 'entry')
const lesson = kind('lesson', 'entry', { requires_basis: true })
const persona = kind('persona', 'persona')
const instruction = kind('conversation-instruction', 'instruction')

/* -- Defect 4: a saved revision is not asked about -------------------------- */
{
  forgetUnfinished()
  // what BrainRecord tells the page: the hosted form's words from its last
  // draw, unless a save has answered since
  const page = { unsaved: null as string | null, settled: false }
  const off = tell(() => { const held = heldAfterSave(page.unsaved, page.settled); return written(held ?? '', !!held) })

  page.unsaved = actUnsaved({ open: 'edit', typed: true }, { act: null, typed: false })
  eq(page.unsaved, ACT_WORDS.edit, 'a revision with changed words is held')
  const before = leaving(unfinished())
  eq(before.ask?.title, 'Leave this revision unfinished?', 'an unsaved revision is asked about, as before')
  eq(before.ask?.lines, [LOST_RECORD], 'and the question says nothing of it is in the Brain')
  eq([before.ask?.stay, before.ask?.leave], [STAY, DISCARD], 'with the same two answers')

  // the save answers: `onSaved` is said BEFORE the form has drawn again, so
  // `unsaved` still names the revision -- and nothing is asked
  page.settled = true
  eq(page.unsaved, ACT_WORDS.edit, 'the form has not drawn again: its words are stale')
  eq(unfinished(), null, 'a saved revision holds nothing')
  eq(leaving(unfinished()).ask, null, 'so going on to the new version is not asked about')

  // the next draw: the flag is taken down, and a NEW unsaved revision asks again
  page.settled = false; page.unsaved = null
  eq(unfinished(), null, 'after the draw nothing is held')
  page.unsaved = ACT_WORDS.edit
  ok(leaving(unfinished()).ask, 'a later unsaved revision is protected exactly as before')
  off()

  eq(heldAfterSave('this establishment', true), null, 'an act dialog that was just recorded holds nothing either')
  eq(heldAfterSave(null, false), null, 'nothing held stays nothing')

  const record = src('surfaces/governance/R2Record.tsx')
  ok(/else \{ onSaved\?\.\(\); onInspect\(r\.version\) \}/.test(record), 'the saved revision says so before it moves to the new version')
  ok(/outcome\.entry !== id\) \{ onSaved\?\.\(\); onInspect\(outcome\.entry\) \}/.test(record), 'and so does an act dialog that leads to another record')
  const page_ = src('quiet2/brain/BrainRecord.tsx')
  ok(page_.includes('onSaved: () => { settled.current = true }') && page_.includes('heldAfterSave(r.unsaved, settled.current)'), 'the record page hears it')
}

/* -- Defect 2: a Kind that requires a basis is created with it -------------- */
{
  ok(requiresBasis(lesson), 'a lesson declares that it requires a basis')
  ok(!requiresBasis(rule) && !requiresBasis(decision), 'a rule and a decision do not')
  ok(!requiresBasis(kind('odd', 'persona', { requires_basis: true })), 'only the generic door takes a basis with the write')
  ok(!requiresBasis(undefined), 'no Kind, no requirement')

  eq(basisIds(' ent-aaaaaaaaaaaa, ent-bbbbbbbbbbbb\nent-aaaaaaaaaaaa '), ['ent-aaaaaaaaaaaa', 'ent-bbbbbbbbbbbb'], 'references are split and said once')
  eq(basisRefusal(lesson, ''), BASIS_NEEDED, 'an empty basis is refused in the form')
  eq(basisRefusal(lesson, '  ,\n '), BASIS_NEEDED, 'and so is one that is only separators')
  eq(basisRefusal(lesson, 'ent-aaaaaaaaaaaa'), null, 'a named reference is accepted')
  eq(basisRefusal(rule, ''), null, 'a Kind whose basis is optional is never refused for lacking one')
  ok(!/requires_basis|`basis`/.test(BASIS_NEEDED), 'the refusal is a plain sentence, not the server\'s field names')

  const sources = ['ent-aaaaaaaaaaaa', 'ent-bbbbbbbbbbbb']
  const made = entryCreateBody({ k: lesson, body: { text: 'It failed twice.' }, me: 'ent-owner', establishes: false, falsifier: '', context: '', sources })
  eq(made, { kind: 'lesson', body: { text: 'It failed twice.' }, attributed_to: 'ent-owner', establish: false, falsifier: '', links: [], basis: sources },
    'the create request for a lesson carries its basis')
  ok(!citesAfterCreate(lesson, sources), 'so derive-from is not sent after it: the basis would be linked twice')
  eq(entryCreateBody({ k: lesson, body: {}, me: 'ent-owner', establishes: true, falsifier: 'f', context: '', sources }).establish, false,
    'and it is established by its own act after the create, never in it')

  const plain = entryCreateBody({ k: rule, body: { text: 'Do it so.' }, me: 'ent-owner', establishes: false, falsifier: '', context: '', sources })
  ok(!('basis' in plain), 'a rule\'s create is what it always was: no basis in it')
  ok(citesAfterCreate(rule, sources), 'its basis is still cited by derive-from, with its reason')
  ok(!citesAfterCreate(rule, []), 'and nothing is cited where nothing was named')
  eq(entryCreateBody({ k: rule, body: {}, me: 'ent-owner', establishes: true, falsifier: '', context: '', sources: [] }).establish, true,
    'a rule with no basis is still established on creation when the owner chooses that')
  eq(entryCreateBody({ k: decision, body: {}, me: 'ent-owner', establishes: false, falsifier: '', context: ' ent-cccccccccccc ', sources: [] }).links,
    [{ relation: 'in-context', to: 'ent-cccccccccccc' }], 'a decision\'s question context is still linked')

  const form = src('surfaces/governance/R2Forms.tsx')
  ok(form.includes("'/api/entries', entryCreateBody({"), 'the form sends what is checked here')
  ok(form.includes('references ({basisNote})') && form.includes("needsBasis ? 'required' : 'optional'"), 'the field is labelled required where it is')
  ok(!form.includes('references (optional)'), 'and nowhere says optional regardless of the Kind')
  ok(form.includes('const unbased = created ? null : basisRefusal(k, basis)'), 'the empty basis is refused before the request')
  ok(form.includes('if (sourceIds.length && !cited)'), 'derive-from is skipped once the basis went with the record')
}

/* -- Defect 7: nothing is established by default ---------------------------- */
{
  for (const k of [rule, decision, lesson, persona, instruction]) ok(startsProposed(k), `a new ${k.kind} starts as Keep proposed`)
  ok(!startsProposed(kind('note', 'entry', {}, null)), 'a Kind standing does not apply to has no status to start in')
  ok(!startsProposed(undefined), 'no Kind, nothing proposed')
  const form = src('surfaces/governance/R2Forms.tsx')
  ok(form.includes('const establishes = a.standing_apt === true && !proposed'), 'establishing is only ever the explicit choice')
  ok(form.includes('attributed_to: me, propose: !establishes'), 'the persona door is sent the matching value')
  ok(form.includes('attributed_to: me, establish: establishes'), 'and so is the instruction door')
  ok(form.includes('<option value="force">I am establishing this as owner</option>'), 'establishing remains available')
  // the conversation header's older popover is a separate route and is NOT changed
  eq(establishInstructionBody('Keep it short.', 'ent-owner').establish, true, 'the header popover still establishes at once, as it says it does')
}

/* -- Defect 6 and the hosted forms: typed work is asked about ---------------- */
{
  const popover = leaving(written(ACT_WORDS.write, true))
  eq(popover.ask?.title, 'Leave this new instruction unfinished?', 'a typed instruction is asked about in the page\'s own question')
  eq(leaving(written(ACT_WORDS.write, false)).ask, null, 'an empty popover closes at once')
  const instructions = src('fluid/conversation/Instructions.tsx')
  ok(instructions.includes('telling.current?.(typed)') && instructions.includes("const typed = text.trim() !== ''"), 'the popover says when it holds typed words')
  ok(instructions.includes('establishInstructionBody(instruction, me)'), 'and what it writes is unchanged')
  const quiet = src('quiet2/Quiet2.tsx')
  ok(quiet.includes("useUnfinished(() => written(ACT_WORDS.write, open === 'instructions' && typing.current))"), 'Quiet Chat registers it with the page')
  ok(quiet.includes("if (open === 'instructions' && next !== 'instructions') guarded(() => setOpenNow(next))"), 'and every way of closing it goes through the one question')
  ok(/const away = [^\n]*closing\.current\(null\)/.test(quiet) && /const esc = [^\n]*closing\.current\(null\)/.test(quiet), 'Escape and an outside press included')

  const record = src('surfaces/governance/R2Record.tsx')
  ok(record.includes("const closeForm = () => { if (askDiscard && unsaved && open) setDiscarding('form'); else prepare(null) }"), 'a hosted form\'s Cancel asks only where something was typed and the host asks for it')
  ok(record.includes('<button disabled={busy} onClick={closeForm}>Cancel</button>'), 'and Cancel is that')
  ok(record.includes('askDiscard = false'), 'Fluid, which does not ask for it, is unchanged')
  ok(src('quiet2/brain/BrainRecord.tsx').includes('askDiscard: true'), 'Quiet Chat asks for it')
  ok(!src('fluid/governance/GovItem.tsx').includes('askDiscard'), 'Fluid does not')
}

/* -- Defect 3: the menu while the record's acts are being read --------------- */
{
  eq(actsPending({ canAct: true, read: false, error: null }), 'loading', 'until the read answers the menu says the acts are loading')
  eq(actsPending({ canAct: true, read: false, error: 'timed out' }), 'failed', 'a failed read is said, with Retry')
  eq(actsPending({ canAct: true, read: true, error: null }), null, 'once read, the acts themselves are listed')
  eq(actsPending({ canAct: true, read: true, error: 'a later reread failed' }), null, 'acts already read are kept through a failed reread')
  eq(actsPending({ canAct: false, read: false, error: null }), null, 'a reader who can do nothing is promised nothing')
  ok(/loading/.test(ACTS_LOADING) && /Retry/.test(ACTS_FAILED), 'the words say which')
  const page = src('quiet2/brain/BrainRecord.tsx')
  ok(page.includes("{ key: 'acts-loading', label: ACTS_LOADING, disabled: true, run: () => {} }"), 'the loading line is disabled')
  ok(page.includes('run: () => r.entry.reload()'), 'and Retry asks again')
}

/* -- Defect 12: each scope once ---------------------------------------------- */
{
  const convs = [{ id: 'ent-c1', name: 'Planning' }]
  const brainWide = scopeChoices('All conversations (Brain-wide)', convs)
  eq(brainWide.map((o) => o.label), ['All conversations (Brain-wide)', 'Only when named', 'Conversation: Planning'], 'Brain-wide is listed once')
  eq(brainWide[0].value, '', 'and the default is still what was asked for')
  const working = scopeChoices('Brain-wide working position', convs)
  eq(working.map((o) => o.value), ['', 'whole_brain', 'when_named', 'ent-c1'], 'a different default keeps every explicit choice')
  eq(scopeChoices('Conversation: Planning', convs).map((o) => o.value), ['', 'whole_brain', 'when_named'], 'a conversation asked for is not offered twice either')
}

/* -- Defects 1 and 5: the creation page names the current Kind; refusals go -- */
{
  const form = src('surfaces/governance/R2Forms.tsx')
  ok(form.includes('useEffect(() => { naming.current?.(kind) }, [kind])'), 'the form says which Kind it is writing now')
  ok(/useEffect\(\(\) => \{ setError\(null\) \}, \[step, kind, reach, where,/.test(form), 'a refusal is taken down when its cause or the step changes')
  const page = src('quiet2/brain/BrainPages.tsx')
  ok(page.includes('New · {kindWords(writing)}') && page.includes('authoring(`this new ${kindWords(writing).toLowerCase()}`)') && page.includes('onKind={setWriting}'),
    'the header and the leave question name that Kind')
}

console.log(`brain_repairs_unit: ${checks} checks passed`)
