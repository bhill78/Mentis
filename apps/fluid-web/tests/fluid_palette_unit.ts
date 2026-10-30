/* SURFACE TENSION P3: THE FIND-AN-ACTION PALETTE (plan adm-b848fa881c8d §4 P3,
 * rev 3 §5.3).
 *
 *   * palette list = T2 list, for every target;
 *   * disabled entries carry their reason, in the palette and in T2;
 *   * Ctrl/⌘+K opens it and does not collide with "/" (the bar's search);
 *   * "Find an action…" is the last T2 row, and opens the palette on the
 *     same target;
 *   * narrowing by label and old words keeps the T2 order. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { isFindActionKey, paletteList, registry } from '../src/fluid/surface/actions/registry'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, hosted, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { aimFallback, aimed, closePalette, openPalette, paletteOpen, pointAt } from '../src/fluid/surface/actions/paletteStore'
import { hostCtx, hostSurface, postTarget, workspaceTarget } from '../src/fluid/surface/actions/targets'
import { ActionBar, ActionMenu } from '../src/fluid/surface/actions/ActionMenu'
import type { ActionCtx, ActionTarget } from '../src/fluid/surface/actions/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

const nothing = () => {}
const ops = {
  object: { open: nothing, peek: nothing, float: nothing, keep: nothing, primary: nothing, focus: nothing },
  openPlace: nothing, back: nothing, openAsPage: nothing, anchorOf: () => null, confirm: () => false, toast: nothing, copy: async () => {},
  post: (id: string) => ({ id, home: 'c1', number: 3, deleted: false, here: 'c1', included: false }),
  postActs: () => ({ reply: nothing, startSelect: nothing, goHome: nothing, busy: false }),
  postLink: () => 'l', openPostDetails: nothing, openPostFull: nothing, openReplies: nothing, openAddress: nothing, openAnnotate: nothing,
  exportTurn: async () => {}, conversationViews: nothing, following: () => false, setFollow: nothing, conversationFocused: () => false,
  setConversationFocused: nothing, putConversationAway: nothing, bringConversationBack: nothing, conversationPutAway: () => false,
  exportConversation: async () => {},
  holder: () => ({ kind: 'workspace', savedAt: null, save: async () => {}, restoreSaved: async () => {}, undo: nothing, canUndo: () => false, reset: nothing }),
  floatsHere: () => ({ count: 0, unfolded: 0 }), putAllAway: nothing, tidyFloats: nothing, newFollower: nothing,
  lensOn: () => false, exitFocus: nothing, keepLensLayout: nothing, tidyAround: nothing, hideOthers: nothing, stopRun: async () => {},
} satisfies Ops
bindOps(ops)
installProviders(registry)
const ctx: ActionCtx = hostCtx('wide')

const section = hosted({ surface: hostSurface('z1', 'section', 'dock') } as ActionTarget, {
  makePrimary: { run: nothing }, float: { run: nothing }, merge: { run: nothing, off: 'Nothing beside it to merge into' }, removeFromWorkspace: { run: nothing },
})
const window = hosted({ surface: hostSurface('w1', 'float', 'float') } as ActionTarget, { collapse: { run: nothing }, dock: { run: nothing }, removeFromWorkspace: { run: nothing } })
const targets: Record<string, ActionTarget> = {
  section, window, workspace: workspaceTarget('c1'), post: postTarget('p1'),
  form: { resource: { address: 'live:p1:form#0', kind: 'form' } }, run: { resource: { address: 'run:r1', kind: 'run' } },
  conversation: { resource: { address: 'conversation:c1', kind: 'conversation' } },
}

/* -- palette list = T2 list ------------------------------------------------- */
for (const [name, t] of Object.entries(targets)) {
  const t2 = registry.list(t, ctx)
  eq(paletteList(t2, '').map((x) => x.def.id), t2.map((x) => x.def.id), `${name}: the palette lists exactly T2`)
  eq(paletteList(t2, '   '), t2, `${name}: a blank query is T2 too`)
  for (const q of ['a', 're', 'layout', 'minimise']) {
    const got = paletteList(t2, q)
    ok(got.every((x) => t2.includes(x)), `${name}: "${q}" finds only T2 entries`)
    eq(got.map((x) => t2.indexOf(x)), [...got.map((x) => t2.indexOf(x))].sort((a, b) => a - b), `${name}: "${q}" keeps the T2 order`)
  }
  eq(t2[t2.length - 1].def.id, 'findAction', `${name}: "Find an action…" is the last T2 row`)
  for (const x of t2) if (x.availability.state === 'disabled') ok(x.availability.reason.message.length > 3, `${name}: ${x.def.id} is disabled with its reason`)
}

/* -- disabled entries carry their reason, and the menu says it ---------------- */
const ws = registry.list(targets.workspace, ctx)
const undo = ws.find((x) => x.def.id === 'undo')!
eq(undo.availability, { state: 'disabled', reason: { code: 'state', message: 'Nothing to undo', retryable: true } }, 'Undo with nothing to undo is disabled, saying so')
ok(paletteList(ws, 'undo').some((x) => x.def.id === 'undo' && x.availability.state === 'disabled'), 'the palette shows it disabled too')
await assert.rejects(registry.run('undo', targets.workspace, ctx), /Nothing to undo/); checks++
const html = renderToString(createElement(ActionMenu, { target: section, ctx, label: 'This section' }))
ok(html.includes('Nothing beside it to merge into'), 'T2 shows a disabled entry with its reason beside it')
ok(html.includes('aria-disabled="true"'), 'and marks it disabled')
const rows = [...html.matchAll(/data-action="([^"]+)"/g)].map((m) => m[1])
eq(rows[rows.length - 1], 'findAction', 'the menu drawn ends with Find an action…')
eq(rows, registry.list(section, ctx).map((x) => x.def.id), 'the menu draws the registry list, in its order')
ok(html.includes('>Arrange<') && html.indexOf('>Arrange<') < html.indexOf('Find an action'), 'the groups are headed, Find an action… after them')
const bar = renderToString(createElement(ActionBar, { target: section, ctx, budget: 2 }))
eq([...bar.matchAll(/data-action="([^"]+)"/g)].map((m) => m[1]), registry.primary(section, ctx, 2).map((d) => d.id), 'T1 draws registry.primary')

/* -- Ctrl/⌘+K, and "/" stays the search ---------------------------------------- */
ok(isFindActionKey({ key: 'k', ctrlKey: true }), 'Ctrl+K opens the palette')
ok(isFindActionKey({ key: 'k', metaKey: true }), '⌘+K opens the palette')
ok(isFindActionKey({ key: 'K', ctrlKey: true, shiftKey: true }), 'Ctrl+Shift+K too')
ok(!isFindActionKey({ key: 'k' }), 'a plain k is typing')
ok(!isFindActionKey({ key: '/' }), '"/" is not the palette')
ok(!isFindActionKey({ key: '/', ctrlKey: true }), 'Ctrl+/ is not the palette')
ok(!isFindActionKey({ key: 'k', ctrlKey: true, altKey: true }), 'Ctrl+Alt+K is left alone')
const barControls = read('fluid/frame/BarControls.tsx')
ok(barControls.includes("if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return"),"the bar's \"/\" ignores Ctrl/⌘, so Ctrl/⌘+K reaches only the palette")
const menu = read('fluid/surface/actions/ActionMenu.tsx')
ok(menu.includes('isFindActionKey(e)') && !/key === '\/'/.test(menu), 'the palette listens for Ctrl/⌘+K and never for "/"')
ok(read('fluid/Shell.tsx').includes('<ActionPalette />'), 'the shell mounts the palette once')

/* -- Find an action… opens the palette on the same target ---------------------- */
closePalette()
await registry.run('findAction', section, ctx)
eq(paletteOpen()?.target, section, 'Find an action… opens the palette on its own target')
closePalette()
eq(paletteOpen(), null, 'and it closes')
aimFallback(() => ({ target: targets.workspace, ctx, name: 'this place' }))
eq(aimed()?.target, targets.workspace, 'with nothing pointed at, Ctrl/⌘+K speaks for the workspace')
pointAt({ target: window, ctx, name: 'w1' })
eq(aimed()?.target, window, 'a surface pointed at comes first')
openPalette()
eq(paletteOpen()?.target, window, 'Ctrl/⌘+K opens on what is aimed at')
closePalette(); pointAt(null)

/* -- the old words, in the palette -------------------------------------------- */
const sectionAll = registry.list(hosted({ surface: hostSurface('z2', 'section', 'dock') } as ActionTarget, { collapse: { run: nothing }, putAway: { run: nothing }, makePrimary: { run: nothing } }), ctx)
eq(paletteList(sectionAll, 'minimise').map((x) => x.def.id), ['collapse', 'putAway'], '"minimise" finds Collapse and Put away')
const all = paletteList(ws, 'minimise all')
eq(all.map((x) => [x.def.id, x.availability.state]), [['putAllAway', 'disabled']], '"minimise all" finds Put all away, disabled while no window is open')
eq(all[0].availability.state === 'disabled' && all[0].availability.reason.message, 'No open floating windows here', '… saying why')

console.log(`fluid palette: ${checks} checks passed`)
