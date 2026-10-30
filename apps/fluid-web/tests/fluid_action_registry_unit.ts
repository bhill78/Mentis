/* SURFACE TENSION P3: THE ONE ACTION REGISTRY (plan adm-b848fa881c8d §4 P3).
 *
 *   * completeness: for every target in rev 3's preservation table (§7, rows
 *     1–62 and 68–75, less the rows the plan defers), list() holds the row's
 *     action;
 *   * primary() ⊆ list();
 *   * one glyph per id and one id per glyph;
 *   * the old words find their new actions;
 *   * writes:'record' actions call the functions the controls call today;
 *   * Follow and Hold are absent on floats;
 *   * Close (this device) and Remove from workspace (shared) are distinct;
 *   * zoneMenu's section and window items are the registry's; no Magnet
 *     provider is registered before P7. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { HOST_ORDER, hostOf as hostKind, matches, registry } from '../src/fluid/surface/actions/registry'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, hosted, type Ops, type PostFacts, type SurfaceHost } from '../src/fluid/surface/actions/providers/ops'
import { WORDS } from '../src/fluid/surface/actions/words'
import type { ActionCtx, ActionId, ActionTarget, SurfaceRef } from '../src/fluid/surface/actions/types'
import type { Change, Level, PlacementKind, PresentationClass, SurfaceCapabilities, SurfaceKind, SurfaceState } from '../src/fluid/surface/types'
import { placeItems, windowItems, arrangeGroup } from '../src/fluid/workspace/zoneMenu'
import { aimed } from '../src/fluid/surface/actions/paletteStore'
import type { ZoneCtl } from '../src/fluid/workspace/TreeView'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

/* -- spies for every operation ------------------------------------------------ */

const calls: string[] = []
const spy = (name: string, ret?: unknown) => (...args: unknown[]) => { calls.push(`${name}(${args.filter((a) => typeof a === 'string' || typeof a === 'boolean').join(',')})`); return ret }
const posts: Record<string, PostFacts> = {
  p1: { id: 'p1', home: 'c1', number: 4, deleted: false, here: 'c1', included: false },
  p2: { id: 'p2', home: 'c2', number: 7, deleted: false, here: 'c1', included: false },
  p3: { id: 'p3', home: 'c2', number: 9, deleted: false, here: 'c1', included: true },
}
let following = false
let convFocused = false
let putAway = false
let lensOn = true
let undoable = true
const ops: Ops = {
  object: { open: spy('act.open'), peek: spy('act.peek'), float: spy('act.float'), keep: spy('act.keep'), primary: spy('act.primary'), focus: spy('act.focus') },
  openPlace: spy('openPlace'), back: spy('back'),
  openAsPage: spy('openAsPage'), closePage: spy('closePage'), anchorOf: () => null, confirm: (q) => { calls.push('confirm'); return !!q }, toast: spy('toast'),
  copy: async (t) => { calls.push(`copy(${t})`) },
  post: (id, via) => posts[id] ? { ...posts[id], via } : null,
  postActs: () => ({ reply: spy('acts.reply'), startSelect: spy('acts.startSelect'), goHome: spy('acts.goHome'), include: spy('acts.include'), remove: spy('acts.remove'), busy: false }),
  selectionActs: () => ({ keepConversation: spy('selection.keepConversation'), include: spy('selection.include'), remove: spy('selection.remove'), busy: false }),
  postLink: (p) => `link:${p.id}`,
  openPostDetails: spy('openPostDetails'), openPostFull: spy('openPostFull'), openReplies: spy('openReplies'),
  openAddress: spy('openAddress'), openAnnotate: spy('openAnnotate'), exportTurn: async (id) => { calls.push(`exportTurn(${id})`) },
  conversationViews: spy('conversationViews'), following: () => following, setFollow: (on) => { calls.push(`setFollow(${on})`) },
  conversationFocused: () => convFocused, setConversationFocused: (on) => { calls.push(`setConversationFocused(${on})`) },
  putConversationAway: spy('minimizeConversation'), bringConversationBack: spy('restoreConversation'), conversationPutAway: () => putAway,
  exportConversation: async (id) => { calls.push(`exportConversation(${id})`) },
  holder: () => ({ kind: 'workspace', savedAt: 1, save: async () => { calls.push('h.save') }, restoreSaved: async () => { calls.push('h.restoreSaved') }, undo: spy('h.undo'), canUndo: () => undoable, reset: spy('h.reset') }),
  floatsHere: () => ({ count: 2, unfolded: 1 }), putAllAway: spy('putAllAway'), tidyFloats: spy('tidyFloats'), newFollower: spy('newFollower'),
  lensOn: () => lensOn, exitFocus: spy('lens.restore'), keepLensLayout: spy('lens.keepLayout'), tidyAround: spy('toggleTidy'), hideOthers: spy('toggleHide'),
  stopRun: async (run) => { calls.push(`stopRun(${run})`) },
}
bindOps(ops)
installProviders(registry)

const applied: Array<{ id: string; c: Change }> = []
const ctxOf = (cls: PresentationClass = 'wide'): ActionCtx => ({
  cls, input: 'fine',
  apply: (id, c) => { applied.push({ id, c }); return { ok: true, arr: { tree: { type: 'zone', id } } as never, label: 'ok', layer: 'shared' } },
  nav: { open: spy('nav.open'), openPlace: spy('nav.openPlace'), back: spy('nav.back') },
})
const ctx = ctxOf()

/* -- surfaces with declared capabilities (what P1's capabilitiesOf declares) -- */

const S = <T extends string>(xs: T[]): ReadonlySet<T> => new Set(xs)
function caps(kind: SurfaceKind, over: Partial<SurfaceCapabilities> = {}): SurfaceCapabilities {
  return {
    kind, placementsBy: { wide: S(['dock', 'float', 'launcher']), medium: S(['dock', 'stack', 'sheet', 'launcher']), compact: S(['stack', 'sheet', 'launcher']) },
    levels: S(['icon', 'compact', 'standard', 'expanded']), size: { min: {} }, resize: 'free', movement: 'free', yield: 'slide', snap: true,
    focusable: true, fullscreen: true, closable: true, putAway: true, primaryable: true, canFollow: kind === 'section', ownsLayout: false,
    primaryBudget: { dock: 4, float: 3 }, ...over,
  }
}
function surface(id: string, kind: SurfaceKind, at: PlacementKind, o: { level?: Level; following?: boolean; current?: boolean; emphasis?: SurfaceState['emphasis']; open?: boolean; caps?: Partial<SurfaceCapabilities> } = {}): ActionTarget {
  const placement: SurfaceState['placement'] = at === 'float' ? { kind: 'float', floatId: 'f-' + id, rect: { x: 0, y: 0, w: 300, h: 200 } }
    : at === 'dock' ? { kind: 'dock', in: 'tree', page: null } : at === 'launcher' ? { kind: 'launcher' }
    : at === 'nested' ? { kind: 'nested', parent: 'z0' } : at === 'stack' ? { kind: 'stack', index: 1 } : at === 'sheet' ? { kind: 'sheet' } : { kind: 'page-root', page: id }
  const state: SurfaceState = {
    id, kind, cls: 'wide', placement, level: { auto: o.level ?? 'standard' }, emphasis: o.emphasis ?? 'none', open: o.open ?? true,
    binding: o.following ? { mode: 'following', source: 'reading', ...(o.current ? { current: { address: 'post:p1', kind: 'post' } } : {}) } : { mode: 'held', resource: { address: 'zone:' + id, kind } },
  }
  const ref: SurfaceRef = { id, state, caps: caps(kind, o.caps) }
  return { surface: ref }
}
const resource = (address: string, kind: string, extra: Partial<ActionTarget> = {}): ActionTarget => ({ resource: { address, kind }, ...extra })
const withHost = (t: ActionTarget, h: SurfaceHost) => hosted(t, h)
const op = (name: string, over: Partial<SurfaceHost[ActionId]> = {}) => ({ run: spy(name), ...over })

const T = {
  post: resource('post:p1', 'post'),
  postAway: resource('post:p2', 'post'),
  postIncluded: resource('post:p3', 'post'),
  postLinked: resource('post:p2', 'post', { resource: { address: 'post:p2', kind: 'post', via: 'linked' } }),
  selection: { selection: [{ address: 'post:p1', kind: 'post' }, { address: 'post:p2', kind: 'post' }] },
  object: resource('live:p1:chart#0', 'chart'),
  image: resource('live:p1:image#0', 'image'),
  file: resource('live:p1:file#0', 'file'),
  link: resource('live:p1:link#0', 'link'),
  form: resource('live:p1:form#0', 'form'),
  run: resource('run:r1', 'run'),
  conversation: { ...resource('conversation:c1', 'conversation'), ...surface('conv', 'conversation', 'dock', { caps: { canFollow: false } }) },
  homeConversation: withHost({ ...resource('conversation:c1', 'conversation') }, { 'conversation.own': op('home.open'), 'conversation.newHere': op('homeConversation.set') }),
  launcher: surface('conv', 'launcher-tile', 'launcher', { level: 'icon' }),
  section: withHost(surface('z1', 'section', 'dock'), {
    makePrimary: op('ctl.focus'), back: op('swapBack'), focus: op('focusSurface'), search: op('search.setOpen'), float: op('ctl.float'),
    split: op('ctl.split'), fit: op('ctl.toggleFit'), merge: op('ctl.merge'), removeFromWorkspace: op('ctl.close'),
    filter: op('setSlot.show'), present: op('setSlot.present'), settings: op('lookGroup'),
  }),
  sectionHeld: surface('z2', 'section', 'dock'),
  sectionFollowing: surface('z3', 'section', 'dock', { following: true, current: true }),
  card: surface('c1', 'nested-card', 'nested'),
  float: surface('w1', 'float', 'float'),
  floatFolded: surface('w2', 'float', 'float', { level: 'icon' }),
  window: withHost(surface('w3', 'float', 'float'), {
    makePrimary: op('editPrimary'), focus: op('focusIt'), dock: op('dockBack'), collapse: op('toggleMin'), tidy: op('tidyFloats'), removeFromWorkspace: op('closeFloat'),
  }),
  windowFolded: withHost(surface('w4', 'float', 'float'), { expand: op('toggleMin') }),
  brain: surface('brain', 'brain', 'float', { caps: { canFollow: false } }),
  lens: surface('lens', 'lens', 'page-root', { emphasis: 'lens' }),
  workspace: resource('place:c1', 'workspace'),
  page: surface('pg1', 'page-panel', 'page-root'),
  setAside: surface('z9', 'section', 'launcher'),
}

const listed = (t: ActionTarget, c = ctx) => registry.list(t, c).map((x) => x.def.id)

/* -- the completeness invariant: rev 3 §7, rows 1–62 and 68–75 ---------------
   Left out, as the plan says (§7 there, and the rows' own T2 column):
     14 and 66   Compare and selection Export as one archive (deferred parts)
     29–31       the bar's Switcher, Home/New/Back/Save and global search:
                 bar globals, no T2 group in rev 3 ("— (bar)")
     41–42       Home's zone ⋯ and Arrange ▾ as aliases (deferred; left as they are)
     69–71       float binding: the Details sheet and thread window following,
                 bar Preview as a follower (deferred) */
const ROWS: Array<[number, keyof typeof T, ActionId[]]> = [
  [1, 'post', ['open']], [2, 'post', ['open']], [3, 'post', ['post.reply']], [4, 'post', ['peek']], [5, 'post', ['focus']],
  [6, 'post', ['post.address']], [7, 'post', ['post.annotate']], [8, 'postAway', ['post.include']], [8, 'postIncluded', ['post.removeInclusion']],
  [9, 'post', ['details']], [10, 'post', ['expand']], [11, 'post', ['post.select']], [12, 'post', ['copyLink']], [13, 'post', ['export']],
  [14, 'selection', ['selection.keepConversation', 'selection.include', 'selection.remove']],
  [15, 'post', ['thread.replies']], [16, 'post', ['post.carries']], [17, 'object', ['keep']], [18, 'postAway', ['post.include']],
  [19, 'conversation', ['conversation.views']], [20, 'conversation', ['follow']], [21, 'conversation', ['focus']], [22, 'conversation', ['putAway']],
  [23, 'launcher', ['bringBack']], [24, 'conversation', ['export']], [25, 'homeConversation', ['conversation.own', 'conversation.newHere']],
  [26, 'conversation', ['filter']], [27, 'conversation', ['conversation.topics']], [28, 'conversation', ['filter']],
  [32, 'section', ['makePrimary', 'focus', 'search', 'fit', 'float', 'split', 'merge', 'removeFromWorkspace']],
  [33, 'section', ['fit', 'merge']], [34, 'section', ['makePrimary', 'back']], [35, 'section', ['filter', 'search', 'removeFromWorkspace']],
  [36, 'section', ['present']], [37, 'section', ['settings']],
  [38, 'section', ['makePrimary', 'back', 'focus', 'float', 'split', 'fit', 'merge', 'removeFromWorkspace']],
  [39, 'card', ['removeFromWorkspace', 'collapse']], [40, 'object', ['keep']],
  [43, 'window', ['collapse', 'removeFromWorkspace']], [43, 'windowFolded', ['expand']], [43, 'float', ['collapse', 'close', 'removeFromWorkspace']],
  [44, 'window', ['makePrimary', 'focus', 'dock', 'collapse', 'tidy', 'removeFromWorkspace']],
  [45, 'floatFolded', ['expand']], [46, 'float', ['dock']], [47, 'float', ['bringToFront']],
  [48, 'lens', ['exitFocus', 'tidyAround', 'filter', 'keepArrangement']],
  [49, 'image', ['openAsWorkspace', 'expand']], [50, 'object', ['keep', 'peek', 'openAsWorkspace']],
  [51, 'object', ['open', 'peek', 'float', 'keep', 'makePrimary', 'focus']],
  [52, 'workspace', ['saveLayout', 'restoreLayout', 'undo', 'resetPlace', 'putAllAway', 'tidy', 'sketch']],
  [53, 'workspace', ['layouts']], [53, 'setAside', ['bringBack']], [54, 'lens', ['present']], [55, 'workspace', ['settings']],
  [56, 'workspace', ['sketch']], [57, 'page', ['removeFromWorkspace']], [58, 'section', ['search']],
  [59, 'run', ['run.stop', 'run.consent']], [60, 'brain', ['collapse', 'close']],
  [61, 'file', ['open', 'file.download']], [61, 'link', ['link.openExternal']],
  [62, 'form', ['form.edit', 'form.validate', 'form.markReady', 'form.history']],
  [68, 'sectionHeld', ['follow']], [68, 'sectionFollowing', ['hold']], [72, 'sectionFollowing', ['hold']], [73, 'sectionFollowing', ['hold']],
  [74, 'sectionFollowing', ['keepAsWindow']], [75, 'workspace', ['newFollower']],
]
const covered = new Set(ROWS.map(([n]) => n))
for (let n = 1; n <= 75; n++) {
  if ([29, 30, 31, 41, 42, 63, 64, 65, 66, 67, 69, 70, 71].includes(n)) continue
  ok(covered.has(n), `row ${n} is checked`)
}
for (const [n, t, ids] of ROWS) {
  const got = listed(T[t])
  for (const id of ids) ok(got.includes(id), `row ${n}: ${t} lists ${id} (has ${got.join(' ')})`)
}
ok(listed(T.postLinked).includes('post.removeInclusion') && !listed(T.postLinked).includes('post.include'), 'a linked placement offers Remove from here, as MoreChips does')

/* -- every list: no absent entry, disabled ones with a reason, Find an action… last -- */
for (const [name, t] of Object.entries(T)) {
  const rows = registry.list(t, ctx)
  ok(rows.every((x) => x.availability.state !== 'absent'), `${name}: nothing absent is listed`)
  ok(rows.every((x) => x.availability.state !== 'disabled' || !!x.availability.reason.message), `${name}: every disabled entry says why`)
  eq(rows[rows.length - 1].def.id, 'findAction', `${name}: "Find an action…" is the last row`)
  eq(new Set(rows.map((x) => x.def.id)).size, rows.length, `${name}: one entry per action`)
  const groups = rows.filter((x) => x.def.id !== 'findAction').map((x) => ['resource', 'view', 'arrange', 'look', 'share', 'details'].indexOf(x.def.group))
  ok(groups.every((g, i) => i === 0 || groups[i - 1] <= g), `${name}: groups in the fixed order`)
  const leads = rows.filter((x) => x.def.lead)
  ok(leads.length <= 1, `${name}: at most one lead action`)
}

/* -- primary ⊆ list, within budget, lead first ----------------------------- */
for (const [name, t] of Object.entries(T)) {
  const all = new Set(listed(t))
  for (const budget of [0, 1, 2, 3, 4, 5, 9]) {
    const p = registry.primary(t, ctx, budget).map((d) => d.id)
    ok(p.every((id) => all.has(id)), `${name}: primary(${budget}) ⊆ list`)
    ok(p.length <= budget, `${name}: primary(${budget}) within budget`)
    ok(!p.includes('findAction') && !p.includes('close'), `${name}: T1 never holds ⋯ or ×`)
  }
}
eq(registry.primary(T.post, ctx, 3).map((d) => d.id)[0], 'post.reply', "a post's lead (Reply) comes first in T1")
eq(registry.primary(T.run, ctx, 2).map((d) => d.id)[0], 'run.stop', "a run's lead (Stop) comes first in T1")
eq(hostKind(T.section), 'dock', 'a docked section is drawn in the dock host')
eq(registry.primary(T.section, ctx, 4).map((d) => d.id), HOST_ORDER.dock.filter((id) => listed(T.section).includes(id)).slice(0, 4), "a section's T1 is the dock order, cut at 4")
eq(registry.primary(T.launcher, ctx, 0), [], 'an icon has no T1')

/* -- one glyph per id, one id per glyph ------------------------------------ */
const defs = registry.everyDef(Object.values(T))
const glyphOf = new Map<string, string>()
const idOf = new Map<string, string>()
for (const d of defs) {
  ok(!!d.glyph, `${d.id} has a glyph`)
  if (glyphOf.has(d.id)) eq(glyphOf.get(d.id), d.glyph, `${d.id} is drawn with one glyph`)
  glyphOf.set(d.id, d.glyph!)
  if (idOf.has(d.glyph!)) eq(idOf.get(d.glyph!), d.id, `${d.glyph} means one action`)
  idOf.set(d.glyph!, d.id)
}
const wordGlyphs = Object.values(WORDS).map((w) => w.glyph)
eq(new Set(wordGlyphs).size, wordGlyphs.length, 'the words table gives every action its own glyph')
eq(WORDS.float.glyph, '⇱', '⇱ is Float only')
eq(WORDS.keep.glyph, '◆', '◆ is Keep')
ok(!wordGlyphs.includes('⧉') && !wordGlyphs.includes('◫'), '⧉ is retired and ◫ is Preview only')
ok(WORDS.close.glyph !== WORDS.removeFromWorkspace.glyph && WORDS.close.label !== WORDS.removeFromWorkspace.label, 'Close and Remove from workspace differ in word and glyph')

/* -- the old words find the new actions ------------------------------------ */
const all = defs
const finds = (word: string) => new Set(all.filter((d) => matches(d, word)).map((d) => d.id))
const expect: Array<[string, ActionId[]]> = [
  ['minimise', ['collapse', 'putAway']],
  ['restore', ['bringBack', 'exitFocus', 'expand', 'restoreLayout']],
  ['pin as tab', ['keep']],
  ['open another', ['keepAsWindow']],
  ['full screen', ['fullscreen', 'expand']],
  ['stop keeping', ['removeFromWorkspace']],
]
for (const [word, ids] of expect) for (const id of ids) ok(finds(word).has(id), `"${word}" finds ${id}`)
ok(!finds('stop keeping').has('close'), '"stop keeping" is Remove from workspace, not Close')

/* -- writes:'record' actions call today's functions -------------------------- */
const recordRuns: Array<[keyof typeof T, ActionId, string[]]> = [
  ['post', 'post.address', ['openAddress(p1)']],
  ['post', 'post.annotate', ['openAnnotate(p1)']],
  ['postAway', 'post.include', ['confirm', 'acts.include(p2)']],
  ['postIncluded', 'post.removeInclusion', ['confirm', 'acts.remove(p3)']],
  ['selection', 'selection.keepConversation', ['selection.keepConversation()']],
  ['selection', 'selection.include', ['selection.include()']],
  ['selection', 'selection.remove', ['selection.remove()']],
  ['run', 'run.stop', ['stopRun(r1)']],
]
for (const [t, id, want] of recordRuns) {
  const d = registry.defsFor(T[t]).find((x) => x.id === id)!
  eq(d.writes, 'record', `${id} writes the record`)
  calls.length = 0
  await registry.run(id, T[t], ctx)
  eq(calls, want, `${id} calls ${want.join(', ')}`)
}
/* every record-writing action seen anywhere is one of those, or a body's own (form, consent) */
const recordIds = new Set(defs.filter((d) => d.writes === 'record').map((d) => d.id))
eq([...recordIds].sort(), ['form.edit', 'form.markReady', 'post.address', 'post.annotate', 'post.include', 'post.removeInclusion', 'run.consent', 'run.stop', 'selection.include', 'selection.keepConversation', 'selection.remove'], 'the record-writing actions')
/* a body's own record action runs the body's function when lent, and is disabled (never invented) when not */
const formHosted = hosted(resource('live:p1:form#1', 'form'), { 'form.markReady': op('A.markReady'), 'form.edit': op('A.draft') })
calls.length = 0
await registry.run('form.markReady', formHosted, ctx)
eq(calls, ['A.markReady()'], "Mark ready runs the form's own markReady")
ok(registry.list(T.form, ctx).find((x) => x.def.id === 'form.markReady')?.availability.state === 'disabled', 'without the form, Mark ready is disabled with where to find it')
await assert.rejects(registry.run('form.markReady', T.form, ctx), /form itself/); checks++
/* the bindings are today's calls (appOps.ts), by reading them */
const app = read('fluid/surface/actions/appOps.ts')
for (const [what, line] of [
  ['Address', 'openAddress: (id, el) => openSheet(addressSheet(id)'],
  ['Annotate', "querySelector<HTMLButtonElement>('[data-act=\"annotate\"]')"],
  ['Stop', 'stopRun: (run) => stopRun(run)'],
  ['Export turn', 'exportTurn: (id) => exportTurn(id)'],
  ['Export conversation', 'exportConversation: (id) => exportConversation(id)'],
  ['Put away', 'putConversationAway: () => minimizeConversation()'],
  ['Bring back', 'bringConversationBack: () => restoreConversation()'],
  ['Open', 'open: (a, el) => act.open(objectTarget(a, el))'],
  ['Save layout', 'holder: () => workspace'],
] as const) ok(app.includes(line), `${what} is bound to today's call: ${line}`)
const shell = read('fluid/Shell.tsx')
ok(shell.includes('providePostActs(actions)'), "the post actions are Shell's own (reply, select, include, remove)")
ok(read('fluid/render/post.tsx').includes("onClick={() => { closeSheet(); void exportTurn(post.id) }}"), "the More menu's Export turn is still api.exportTurn")

/* -- Follow and Hold: sections only; absent on floats ------------------------- */
for (const t of [T.float, T.floatFolded, T.window, T.brain]) {
  ok(!listed(t).includes('follow') && !listed(t).includes('hold'), 'Follow and Hold are absent on floats')
}
ok(listed(T.sectionHeld).includes('follow') && !listed(T.sectionHeld).includes('hold'), 'a held section offers Follow')
ok(listed(T.sectionFollowing).includes('hold') && !listed(T.sectionFollowing).includes('follow'), 'a following section offers Hold')

/* -- Close is this device's; Remove from workspace is shared -------------------- */
applied.length = 0
await registry.run('close', T.float, ctx)
await registry.run('removeFromWorkspace', T.float, ctx)
eq(applied, [{ id: 'w1', c: { prop: 'open', to: false } }, { id: 'w1', c: { prop: 'exists', to: false } }], 'Close writes open:false; Remove writes exists:false')
ok(listed(surface('w5', 'float', 'float', { open: false })).includes('reopen'), 'a closed surface offers Reopen')
ok(!listed(T.conversation).includes('removeFromWorkspace'), 'the conversation cannot be removed from its workspace')
calls.length = 0
await registry.run('removeFromWorkspace', T.page, ctx)
eq(calls, ['closePage(pg1)'], 'page Remove from workspace runs nav.closePage')
/* the other surface verbs go through ctx.apply as their one change */
applied.length = 0
for (const id of ['collapse', 'dock', 'bringToFront', 'fullscreen'] as ActionId[]) await registry.run(id, T.float, ctx)
eq(applied.map((x) => x.c), [{ prop: 'level', step: -1 }, { prop: 'placement', to: { kind: 'dock' } }, { prop: 'front' }, { prop: 'emphasis', to: 'fullscreen' }], 'surface verbs are one Change each through ctx.apply')
const fs = surface('w6', 'float', 'float', { emphasis: 'fullscreen' })
ok(listed(fs).includes('exitFullscreen') && !listed(fs).includes('fullscreen'), 'in full screen, Exit full screen is offered')
ok(!listed(T.float, ctxOf('compact')).includes('float') && listed(surface('s1', 'section', 'stack'), ctxOf('compact')).includes('moveDown'), 'compact has no float; a stack card moves down')

/* -- zoneMenu: the section's and window's items are the registry's ------------- */
const zm = read('fluid/workspace/zoneMenu.tsx')
ok(zm.includes('registry.list(target, ctx)') && zm.includes('registry.run(id, target, ctx)'), "zoneMenu's items are the registry's list and run")
ok(!zm.includes("label: 'Close'") && !zm.includes("label: w.minimise.on ? 'Restore' : 'Minimise'"), 'zoneMenu draws no Close or Minimise of its own')
const did: string[] = []
const ctl: ZoneCtl = {
  id: 'z1', focus: () => did.push('focus'), float: () => did.push('float'), stacked: false, across: false,
  canSplitRow: true, canSplitCol: false, whyNoSplitRow: null, whyNoSplitCol: 'Too short to split', canMerge: false, canClose: true,
  split: (d) => did.push('split-' + d), merge: () => did.push('merge'), close: () => did.push('close'), closing: false,
  widen: () => true, docked: false, fit: false, canFit: true, toggleFit: () => did.push('fit'),
}
const items = placeItems(ctl, { back: () => did.push('back'), focus: () => did.push('lens') })
eq(aimed()?.target.surface?.state.id, 'z1', 'opening a section menu points the palette at that section')
eq(items.map((x) => x.id), ['makePrimary', 'back', 'focus', 'float', 'split-row', 'split-col', 'fit', 'merge', 'removeFromWorkspace', 'findAction'], "a docked section's Arrange items, in their old order, Find an action… last")
eq(items.find((x) => x.id === 'split-col')?.why, 'Too short to split', 'a split it cannot make says why')
eq(items.find((x) => x.id === 'merge')?.why, 'Nothing beside it to merge into', 'Merge says why not')
eq(items.find((x) => x.id === 'removeFromWorkspace')?.label, 'Remove', "the section's × is Remove (from workspace)")
for (const it of items) if (!it.off && it.id !== 'findAction') it.onPick?.()
await new Promise((r) => setTimeout(r, 0))
eq(did, ['focus', 'back', 'lens', 'float', 'split-row', 'fit', 'close'], "each item runs the section's own function")
eq(placeItems(ctl, { floating: true }), [], 'a floating place offers its window items instead')
const wdid: string[] = []
const win = windowItems({ primary: () => wdid.push('primary'), focus: () => wdid.push('focus'), pin: { on: false, run: () => wdid.push('pin') }, dockBack: () => wdid.push('dock'),
  minimise: { on: false, run: () => wdid.push('min') }, tidy: () => wdid.push('tidy'), close: () => wdid.push('close') })
eq(aimed()?.target.surface?.state.id, 'window', 'opening a window menu points the palette at that window')
eq(win.map((x) => x.id), ['makePrimary', 'focus', 'pin', 'dock', 'collapse', 'tidy', 'removeFromWorkspace', 'findAction'], "a window's ⚙ items: Minimise is Collapse, × is Remove, Pin kept")
ok(win.find((x) => x.id === 'tidy')!.says.includes('Tidy floating windows'), 'Tidy keeps its words')
for (const it of win) if (it.id !== 'findAction') it.onPick?.()
await new Promise((r) => setTimeout(r, 0))
eq(wdid, ['primary', 'focus', 'pin', 'dock', 'min', 'tidy', 'close'], "each item runs the window's own function")
eq(windowItems({ minimise: { on: true, run: () => {} } }).map((x) => x.id), ['expand', 'findAction'], "a folded window's Restore is Expand")
const merged = arrangeGroup([...items, ...windowItems({ tidy: () => {} })])!
eq(merged.items!.filter((x) => x.id === 'findAction').length, 1, 'one Find an action… in a merged Arrange column')
eq(merged.items![merged.items!.length - 1].id, 'findAction', '… and it is last')

/* -- no Magnet provider before P7 -------------------------------------------- */
ok(!defs.some((d) => d.id.startsWith('magnet.') || d.id === 'conversation.makeMagnet'), 'no magnet.* or Make magnet action is registered (P7 owns them)')
ok(!read('fluid/surface/actions/providers/index.ts').includes("provide('magnet'"), 'no Magnet provider is installed')
assert.throws(() => registry.register({ ...defs[0], id: 'push' as ActionId }), /reserved|not a shared verb/); checks++

console.log(`fluid action registry: ${checks} checks passed`)
