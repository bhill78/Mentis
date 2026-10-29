/* Unit tests for Workflows in the `/` palette:
 * 1. filtering by what follows `/` (substring of the name, any case)
 * 2. picking attaches to `draft.use.governed`, and `bodyOf` carries `governed`
 * 3. picking again never duplicates
 * 4. `/timer` and `/form` still come first and still match
 * 5. path text (`/usr/bin`, `//C:\`) and nothing-matches fall through as before
 * 6. the register's rows are read as name + id
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { attachWorkflow, dropToken, matchWorkflows, workflowsOf, type WorkflowRow } from '../src/fluid/composer/workflows'
import { slashItems, type SlashItem } from '../src/fluid/composer/SlashPalette'
import { triggerAt } from '../src/composer/trigger'
import { bodyOf, emptyDraft, type Draft } from '../src/composer/draft'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const WF: WorkflowRow[] = [
  { entry: 'ent-sw', name: 'Software change' },
  { entry: 'ent-rv', name: 'Release review' },
]
const names = (items: SlashItem[]) => items.map((i) => (i.kind === 'command' ? i.cmd.id : 'wf:' + i.workflow.name))
/** What the composer would show for this text with the caret at its end. */
const shown = (text: string, wf = WF) => {
  const t = triggerAt(text, text.length)
  return t && t.sigil === '/' ? names(slashItems(t.query, wf)) : null
}

// 1. filtering
eq(matchWorkflows(WF, 'soft').map((w) => w.name), ['Software change'], '/soft finds Software change')
eq(matchWorkflows(WF, 'SOFT').map((w) => w.name), ['Software change'], 'case-insensitive')
eq(matchWorkflows(WF, 'change').map((w) => w.name), ['Software change'], 'substring, not only prefix')
eq(matchWorkflows(WF, 'zzz'), [], 'no match, no rows')
eq(matchWorkflows(WF, '').length, 2, 'bare / lists every Workflow')
eq(shown('/soft'), ['wf:Software change'], 'typed /soft shows only Software change')
eq(shown('please do /rel'), ['wf:Release review'], 'mid-sentence /rel')
eq(shown('/zzz'), [], 'nothing matches: no rows')

// 4. commands still work, and come first
eq(shown('/timer'), ['timer'], '/timer still matches the timer')
eq(shown('/form'), ['form'], '/form still matches forms')
eq(shown('/poll'), ['form'], 'command keywords still match')
eq(shown('/'), ['timer', 'form', 'wf:Software change', 'wf:Release review'], 'commands first, then Workflows')
eq(names(slashItems('t', [])), ['timer'], 'with no Workflows held, the commands as before')

// 5. paths and fall-through
eq(shown('/usr/bin'), [], '/usr/bin opens nothing pickable, so Enter falls through and sends')
eq(shown('see /usr/bin/env'), [], 'mid-sentence path likewise')
eq(shown('//C:\\Work\\notes'), null, '//C:\\ opens no slash palette')
eq(shown('open //C:\\Work'), null, 'mid-sentence //C:\\ opens no slash palette')
eq(shown('https://example.org/soft'), null, 'a URL opens nothing')
eq(shown('a/soft'), null, '/ jammed against a word opens nothing')

// 2. picking attaches, and the request carries `governed`
const t = triggerAt('fix the build /soft', 19)!
const out = dropToken('fix the build /soft', t)
eq(out, { text: 'fix the build ', caret: 14 }, 'the /… token is removed')
eq(dropToken('a /soft b', triggerAt('a /soft b', 7)!), { text: 'a b', caret: 2 }, 'one space kept between words')
eq(dropToken('/soft', triggerAt('/soft', 5)!), { text: '', caret: 0 }, 'token alone')

const base: Draft = { ...emptyDraft(), text: out.text }
const picked = attachWorkflow(base, WF[0])
eq(picked.use, { governed: ['ent-sw'], said: { 'ent-sw': 'Software change' } }, 'attached as Use… attaches, with the chip label')
eq(bodyOf(picked, 'me', [], 'ask-mentis').governed, ['ent-sw'], 'Ask Mentis carries governed')
const working: Draft = { ...picked, to: [{ participant: 'p-1', alias: '@Quill', dispatch: true }] }
eq(bodyOf(working, 'me', []).dispatch[0].governed, ['ent-sw'], 'a dispatched request carries governed')
ok(!('governed' in bodyOf({ ...picked, action: 'record-only' }, 'me', [], 'ask-mentis')), 'record-only sends no governed, as today')
ok(!('governed' in bodyOf(picked, 'me', [], 'record-only')), 'a reply (record-only fallback) sends no governed, as today')

// alongside what Use… already attached
const viaUse: Draft = { ...base, use: { governed: ['ent-x'], said: { 'ent-x': 'Other' } } }
eq(attachWorkflow(viaUse, WF[0]).use, { governed: ['ent-x', 'ent-sw'], said: { 'ent-x': 'Other', 'ent-sw': 'Software change' } },
  'added after what Use… chose, keeping its labels')

// 3. no duplicates
const twice = attachWorkflow(picked, WF[0])
eq(twice.use!.governed, ['ent-sw'], 'picking again leaves it attached once')
eq(bodyOf(twice, 'me', [], 'ask-mentis').governed, ['ent-sw'], 'and the request names it once')

// 6. the register's rows
eq(workflowsOf({ groups: { standing: [
  { entry: 'ent-sw', kind: 'workflow', summary: ' Software change ', governs: true },
  { entry: 'ent-blank', kind: 'workflow', summary: '', governs: true },
] } }), [{ entry: 'ent-sw', name: 'Software change' }], 'name from summary; unnamed rows left out')
eq(workflowsOf(null), [], 'nothing read: nothing offered')
eq(workflowsOf({}), [], 'no groups: nothing offered')

// the composer wires it through the existing mechanisms
const src = fileURLToPath(new URL('../src/', import.meta.url))
const composer = readFileSync(src + 'fluid/Composer.tsx', 'utf8')
ok(composer.includes('onWorkflow={pickWorkflow}'), 'the composer gives the palette its Workflow pick')
ok(composer.includes("useWorkflows(trigger?.sigil === '/' && !activeHelper)"), 'Workflows read again as the palette opens')
const hook = readFileSync(src + 'fluid/composer/useWorkflows.ts', 'utf8')
ok(hook.includes('/fluid/api/governed?state=standing&kind=workflow'), 'read from the governed register, standing Workflows only')

console.log(`fluid slash workflows: ${checks} checks passed`)
