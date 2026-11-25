/* Render the five approved Perspectives states as static HTML with the real
   stylesheets, so the rebuilt surface can be put beside the round-3 mockups.
   The frame's own chrome (head, tabs, footer) is Part A's and is approximated
   here only so the body reads at the right proportions. */
import { registerHooks } from 'node:module'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.css$/.test(url)) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText }
    return next(url, context)
  },
})
const { createElement } = await import('react')
const { renderToStaticMarkup } = await import('react-dom/server')
const { page } = await import('../src/brainBinding.ts')
const Panel = await import('../src/quiet2/magnets/InquiryPanel.tsx')
const { perspectivesOf } = await import('../src/quiet2/magnets/perspectives.ts')
const { setQuestionDraft, panelAt, forgetPanelDrafts } = await import('../src/quiet2/magnets/panelDrafts.ts')
const { createMagnetResource } = await import('../src/quiet2/magnets/state.ts')

const mem = new Map()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v), removeItem: (k) => mem.delete(k), clear: () => mem.clear() } })
page.saw('shots@instance')
forgetPanelDrafts()

const SOURCE = 'ent-source111111', digest = 'a'.repeat(64)
const config = (id) => ({ id, sources: [{ kind: 'conversation', conversation: SOURCE }],
  selection: { informationTypes: ['post'], dates: {} }, conversation: 'ent-own111111',
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } })
const post = (n, text, at) => ({ kind: 'post', id: `ent-post${n}11111`, number: 10 + n, version: `ent-version${n}1111`,
  conversation: SOURCE, via: 'home', at, value: { parts: [{ type: 'text', text }] } })
const POSTS = [
  post(1, 'We had to wait for the release tool again before we could complete the deployment.', 1764000100),
  post(2, 'Let us record the steps that held up the last release and check them next time.', 1763900200),
]
const ACTIVATION = { post: 'ent-activation111', artifact: { ref: 'adm-batch111111', digest, size: 2048, media_type: 'application/json' }, at: 1764000500, state: 'recorded' }
const resource = (id) => createMagnetResource({ id: `qm-${id}`, brainKey: 'origin|shots|brain', saved: { id, name: 'Deployment learning', config: config(id) },
  get: async () => ({ status: 200, body: { magnet: id, config: config(id), activation: ACTIVATION,
    page: { sources: [{ source: config(id).sources[0], key: `conversation:${SOURCE}`, status: 'ok', results: POSTS }] } } }) })

const ROWS = [
  { perspective: 'ent-topicA11111', name: 'What is slowing our releases?', retired: false, question: null,
    current_question: { text: 'What is slowing our releases?', revision: 'adm-a' }, events: 3 },
  { perspective: 'ent-topicB11111', name: 'Are handoffs clearly owned?', retired: false, question: null,
    current_question: { text: 'Are handoffs clearly owned?', revision: 'adm-b' }, events: 3 },
  { perspective: 'ent-topicC11111', name: 'What changed in the last release?', retired: false, question: null,
    current_question: { text: 'What changed in the last release?', revision: 'adm-c' }, events: 2 },
]

const css = ['design.css', 'magnet.css', 'configuration.css', 'summary.css', 'perspectives.css']
  .map((f) => readFileSync(new URL(`../src/quiet2/magnets/${f}`, import.meta.url), 'utf8')).join('\n')

const FRAME = `
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:#171413;color:#eee8e5;font-size:15px}
.stage{height:900px;background:radial-gradient(ellipse at 12% 0%,#443a35,#221d1c 56%,#181616);padding:32px;display:flex;justify-content:flex-end}
.q2 .q2-magnet{position:static!important;width:auto!important;height:auto!important}
.q2 .q2-magnet-card{position:relative!important;--magnet-brown:#292322}
.shot-head{display:flex;align-items:center;gap:12px;padding:20px 24px 15px 76px;border-bottom:1px solid var(--magnet-rule)}
.shot-head .t{font-size:17px;font-weight:700;flex:1}
.shot-head .i{color:#c9bab3;font-size:20px}
.shot-tabs{display:flex;gap:22px;padding:0 24px;border-bottom:1px solid var(--magnet-rule);color:#c1b2ab;white-space:nowrap}
.shot-tabs div{padding:13px 0 11px}
.shot-tabs .on{border-bottom:3px solid #e6bc50;color:#f6cb62;font-weight:700}
.shot-foot{border-top:1px solid var(--magnet-rule);padding:13px 24px;color:#a89991;font-size:12px}
.wide .stage{justify-content:center;align-items:center}
`

/* Both places are rendered inside the panel's own section in the app. */
const panel = (markup) => `<section class="q2-magnet-perspectives" aria-label="Perspectives">${markup}</section>`

function shot(name, markup, width) {
  const room = Math.min(1, Math.max(0, (width - 320) / (900 - 320))).toFixed(3)
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>${css}\n${FRAME}</style></head>
<body class="${width > 900 ? 'wide' : ''}"><div class="stage"><div class="q2"><div class="q2-magnet">
<section class="q2-magnet-card" style="width:${width}px;${width > 900 ? 'height:820px;' : 'height:836px;'}--magnet-room:${room};--magnet-room-h:${room}">
<div class="shot-head"><span class="t">Deployment learning</span><span class="i">⤢</span><span class="i">×</span></div>
<div class="shot-tabs"><div>Summary</div><div>Collection</div><div class="on">Perspectives</div><div>Conversation</div></div>
<div class="mgd-body" style="overflow:auto;flex:1">${markup}</div>
<div class="shot-foot">Drag the panel edge to resize</div>
</section></div></div></div></body></html>`
  writeFileSync(new URL(`../partc-shot-${name}.html`, import.meta.url), html)
  console.log('wrote', name, width)
}

/* 02 -- nothing asked yet */
{
  const r = resource('mag-shot02')
  perspectivesOf(r).update({ rows: ROWS })
  shot('02-asking', renderToStaticMarkup(createElement(Panel.default, { resource: r, canWrite: true, onEvidence: () => {} })), 510)
}
/* 09 -- the one help panel: rendered by opening it in a second pass */
{
  const r = resource('mag-shot09')
  perspectivesOf(r).update({ rows: ROWS })
  const markup = renderToStaticMarkup(createElement(Panel.default, { resource: r, canWrite: true, onEvidence: () => {} }))
  // The help block is state; render its own markup beside the compose box.
  const help = `<div class="mgd-help"><div class="mgd-row mgd-spread"><b>${Panel.HELP_TITLE}</b><button type="button" class="mgd-link">×</button></div><p class="mgd-small">${Panel.HELP_WORDS}</p><div class="mgd-row"><button type="button" class="mgd-button mgd-secondary">Browse collection →</button><button type="button" class="mgd-link mgd-small">Continue here</button></div></div>`
  const from = markup.indexOf('<div class="mgd-subtle">TRY ASKING')
  const to = markup.indexOf('</p>', markup.indexOf('What can I do?')) + 4
  if (from < 0 || to < 4) throw new Error('the try-asking block was not found in the rendered markup')
  shot('09-help', markup.slice(0, from) + help + markup.slice(to), 510)
}
/* 05 / 10 -- a question and what is understood of it */
{
  const r = resource('mag-shot10')
  perspectivesOf(r).update({ rows: ROWS, selected: ROWS[0].perspective, viewed: ROWS[0].perspective,
    viewedDetail: ROWS[0], selectedDetail: ROWS[0] })
  shot('10-question', renderToStaticMarkup(createElement(Panel.default, { resource: r, canWrite: true, onEvidence: () => {} })), 510)
}
/* 06 -- supporting items */
{
  const r = resource('mag-shot06')
  await r.read()
  shot('06-support', panel(renderToStaticMarkup(createElement(Panel.SupportingItems, {
    resource: r, question: 'What is slowing our releases?', onOpen: () => {}, onBack: () => {} }))), 510)
}
/* 08 -- past questions */
{
  const r = resource('mag-shot08')
  perspectivesOf(r).update({ rows: ROWS, selected: ROWS[0].perspective, viewed: ROWS[0].perspective,
    viewedDetail: ROWS[0], selectedDetail: ROWS[0] })
  shot('08-past', panel(renderToStaticMarkup(createElement(Panel.PastQuestions, {
    resource: r, canWrite: true, onEvidence: () => {}, onNew: () => {}, onOpened: () => {} }))), 510)
}
/* 07 -- the same content with room */
{
  const r = resource('mag-shot07')
  perspectivesOf(r).update({ rows: ROWS, selected: ROWS[0].perspective, viewed: ROWS[0].perspective,
    viewedDetail: ROWS[0], selectedDetail: ROWS[0] })
  shot('07-room', renderToStaticMarkup(createElement(Panel.default, { resource: r, canWrite: true, onEvidence: () => {} })), 1100)
}
