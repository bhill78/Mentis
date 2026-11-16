/* MANAGE SOURCES IN QUIET CHAT -- ONE INTERACTIVE PROTOTYPE.
 *
 * A design-review prototype: Quiet Chat's layout and stylesheets, sample
 * data, and SIMULATED operations. It talks to no server and nothing here is
 * imported by the app.
 *
 * Every action offered is one the existing source system has
 * (mentis/web/sources.py): declare, locate on this machine (bind), preview
 * (plan), refresh (sweep), cancel a run, change what is included
 * (revise-scope), stop refreshing here (unbind), browse and read what is
 * held. Nothing is offered that it does not have: no rename, remove, turn
 * off, schedule, credential entry, or per-source access.
 *
 *   ?theme=light|dark   ?phone=1 (a 390x844 frame of this same page)   ?frame=1 (inside that frame)
 */
(() => {
  const Q = new URLSearchParams(location.search)
  const FRAME = Q.get('frame') === '1'
  let theme = Q.get('theme') === 'light' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
  const num = (n) => Math.round(n).toLocaleString('en-US')
  const bytes = (b) => b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b >= 1e6 ? (b / 1e6).toFixed(1) + ' MB' : b >= 1e3 ? Math.round(b / 1e3) + ' KB' : b + ' B'
  const now = () => new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  const ICON = {
    brain: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M6 2.5a2 2 0 0 0-2 2v.3A2.2 2.2 0 0 0 2.5 7a2.2 2.2 0 0 0 .7 1.6A2.3 2.3 0 0 0 5 12.4 1.8 1.8 0 0 0 8 13V3.6A1.9 1.9 0 0 0 6 2.5Z"/><path d="M10 2.5a2 2 0 0 1 2 2v.3A2.2 2.2 0 0 1 13.5 7a2.2 2.2 0 0 1-.7 1.6 2.3 2.3 0 0 1-1.8 3.8A1.8 1.8 0 0 1 8 13"/></svg>',
    store: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/><path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/></svg>',
  }

  /* ---- phone width: this same page, in a phone-sized frame ---------------- */
  if (Q.get('phone') === '1') {
    document.body.innerHTML = `<div class="mk-phonepage">
      <span class="pt-tools"><button data-go="index.html?theme=${theme}">‹ Back to the full workspace</button><button data-go="index.html?phone=1&theme=${theme === 'dark' ? 'light' : 'dark'}">${theme === 'dark' ? 'Light' : 'Dark'} theme</button></span>
      <iframe title="Manage Sources at phone width" src="index.html?frame=1&theme=${theme}"></iframe>
      <span style="font:var(--type-meta);color:var(--text-faint)">390 × 844. The same prototype, at a phone's width: use it as you would on a phone.</span></div>`
    document.body.addEventListener('click', (e) => { const b = e.target.closest('[data-go]'); if (b) location.href = b.dataset.go })
    return
  }

  /* ---- sample data --------------------------------------------------------- */
  const F = (folder, n, files) => ({ folder, n, files })
  const sources = [
    { id: 'mentis', name: 'Mentis repository', kind: 'git', what: 'A Git repository on this machine.', bound: true, since: 'Oct 8',
      held: { n: 866, bytes: 21.1e6, links: 264, unselected: 12, absent: 0 }, last: 'Nov 14, 3:12 PM', declared: 'Oct 8',
      scope: { include: '*', exclude: 'node_modules/**\ntarget/**\n*.png', branch: 'main', history: 'The latest commit only', revisions: 3, changed: 'Nov 2 by brian' },
      tree: [F('mentis/', 412, ['web/sources.py', 'sources/registry.py', 'sources/lifecycle.py', 'sources/git.py', 'worker.py']), F('apps/fluid-web/', 238, ['src/quiet2/Quiet2.tsx', 'src/quiet2/brain/BrainBrowser.tsx', 'src/theme.css']), F('tests/', 131, ['test_sources.py', 'test_worker.py']), F('docs/', 46, ['execution-visibility.md', 'sources.md']), F('crates/', 39, ['front/src/main.rs'])],
      sweeps: [['Nov 14, 3:12 PM', '3 new, 12 changed, 1 gone'], ['Nov 9, 10:40 AM', '0 new, 27 changed'], ['Nov 2, 6:05 PM', 'what is included changed · 64 no longer included'], ['Oct 8, 9:21 AM', 'first taken · 902 new']],
      withheld: ['.env', 'deploy/id_ed25519'], plan: { neu: 4, changed: 9, gone: 0, bytes: 0.4e6 } },
    { id: 'agent', name: 'Agent Memory', kind: 'git', what: 'A Git repository on this machine.', bound: true, since: 'Oct 12',
      held: { n: 677, bytes: 18.2e6, links: 91, unselected: 0, absent: 3 }, last: 'Nov 3, 8:20 AM', declared: 'Oct 12',
      scope: { include: '*', exclude: '', branch: 'main', history: 'The last 50 commits', revisions: 1, changed: 'Oct 12 by brian' },
      tree: [F('memory/episodes/', 498, ['2026-10/episode-0412.md', '2026-10/episode-0413.md', '2026-11/episode-0431.md']), F('memory/lessons/', 122, ['background-tests.md', 'model-capacity.md']), F('tools/', 57, ['agent_memory.py', 'migrate.py'])],
      sweeps: [['Nov 3, 8:20 AM', '14 new, 6 changed'], ['Oct 12, 2:02 PM', 'first taken · 663 new']],
      withheld: [], plan: { neu: 22, changed: 5, gone: 0, bytes: 0.9e6 } },
    { id: 'handbook', name: 'Client handbook', kind: 'git', remote: 'https://git.example.com/acme/handbook.git', what: 'A Git repository at an https address.', bound: true, since: 'Oct 21',
      held: { n: 214, bytes: 6.3e6, links: 58, unselected: 28, absent: 0 }, last: 'Oct 30, 4:18 PM', declared: 'Oct 21',
      scope: { include: '*', exclude: 'drafts/**\n*.psd', branch: 'main', history: 'The latest commit only', revisions: 1, changed: 'Oct 21 by brian' },
      tree: [F('policies/', 81, ['security.md', 'travel.md', 'leave.md']), F('onboarding/', 52, ['first-week.md', 'accounts.md']), F('engineering/', 60, ['release-process.md', 'on-call.md']), F('templates/', 21, ['proposal.md'])],
      sweeps: [['Oct 30, 4:18 PM', '6 new, 19 changed'], ['Oct 21, 11:02 AM', 'first taken · 208 new']],
      withheld: ['.env', 'secrets/prod.key', 'ops/id_rsa'], plan: { neu: 9, changed: 14, gone: 2, bytes: 0.3e6 },
      failure: { when: 'Nov 16, 9:02 AM', title: 'sign-in was refused', kind: 'authentication required' }, signedIn: false },
    { id: 'ledger', name: 'Campaign ledger', kind: 'sqlite', what: 'A SQLite database file on this machine, opened read-only.', bound: true, since: 'Nov 1',
      held: { n: 3120, bytes: 1.4e6, links: 0, unselected: 2, absent: 0, tables: 14 }, last: 'Nov 15, 6:44 PM', declared: 'Nov 1',
      scope: { include: '*', exclude: 'sqlite_*\naudit_log', revisions: 2, changed: 'Nov 4 by brian', columns: 'players.email is left out' },
      tree: [F('characters', 6, null), F('sessions', 11, null), F('loot', 284, null), F('npcs', 97, null), F('locations', 63, null)],
      sweeps: [['Nov 15, 6:44 PM', '41 new rows, 12 changed'], ['Nov 4, 9:15 AM', 'what is included changed · 1 column left out'], ['Nov 1, 7:30 PM', 'first taken · 3,067 rows']],
      withheld: [], plan: { neu: 18, changed: 4, gone: 0, bytes: 9e3 } },
    { id: 'dnd', name: 'D&D Knowledge', kind: 'folder', what: 'A folder of files.', bound: false,
      held: { n: 1078, bytes: 523e6, links: 2140, unselected: 31, absent: 0 }, last: 'Oct 2, 5:51 PM', declared: 'Oct 2',
      scope: { include: '*', exclude: '*.tmp\n.obsidian/**', revisions: 1, changed: 'Oct 2 by brian' },
      tree: [F('Sessions/', 9, ['Session 07.md', 'Session 08.md', 'Session 09.md']), F('Rules/', 412, ['Combat.md', 'Spellcasting.md']), F('World/', 388, ['Saltmere.md', 'Eastern Reef.md']), F('Maps/', 269, ['saltmere-harbour.pdf'])],
      sweeps: [['Oct 2, 5:51 PM', 'first taken · 1,078 new']], withheld: [], plan: { neu: 6, changed: 3, gone: 0, bytes: 1.2e6 },
      pick: ['C:\\Users\\brian\\Documents\\D&D Knowledge', 'D:\\Archive\\D&D Knowledge'] },
    { id: 'directives', name: 'Old Mentis Directives', kind: 'folder', what: 'A folder of files.', bound: false,
      held: { n: 86, bytes: 2.9e6, links: 12, unselected: 0, absent: 0 }, last: 'Oct 3, 11:07 AM', declared: 'Oct 3',
      scope: { include: '*.md\n*.txt', exclude: '', revisions: 1, changed: 'Oct 3 by brian' },
      tree: [F('directives/', 61, ['001-identity.md', '014-verification.md']), F('notes/', 25, ['retired.txt'])],
      sweeps: [['Oct 3, 11:07 AM', 'first taken · 86 new']], withheld: [], plan: { neu: 0, changed: 2, gone: 0, bytes: 4e3 },
      pick: ['C:\\Projects\\mentis-directives', 'D:\\Archive\\mentis-directives'] },
    { id: 'pdfs', name: 'Research PDFs', kind: 'folder', what: 'A folder of files.', bound: false,
      held: { n: 0, bytes: 0, links: 0, unselected: 0, absent: 0 }, last: null, declared: 'Nov 12',
      scope: { include: '*.pdf', exclude: '', revisions: 1, changed: 'Nov 12 by brian' },
      tree: [], sweeps: [], withheld: [], plan: { neu: 38, changed: 0, gone: 0, bytes: 212e6 }, pdf: true,
      pick: ['C:\\Users\\brian\\Documents\\Research', 'D:\\Papers'],
      futureTree: [F('agents/', 21, ['tool-use-survey.pdf', 'memory-architectures.pdf']), F('retrieval/', 17, ['dense-retrieval.pdf'])] },
  ]
  const KIND = { git: 'Git repository', folder: 'Folder', sqlite: 'SQLite database' }
  const KSHORT = { git: 'Git', folder: 'Folder', sqlite: 'SQLite' }
  const unit = (s) => s.kind === 'sqlite' ? 'rows' : 'files'
  const byId = (id) => sources.find((s) => s.id === id)

  const LINES = [
    ['b', 'Picking this back up. Where did we leave the harbour master?'],
    ['C', 'She offered safe berth for one season in exchange for a chart of the eastern reef. That is in the session nine write-up.'],
    ['b', 'And the pilot’s ledger?'],
    ['C', 'Still missing. The last mention is in session eight: it was seen in the customs house before the fire.'],
    ['b', 'Draft a short recap I can read out at the table.'],
    ['B', 'Draft is ready: three paragraphs, the bargain, the debt, and the three open threads.'],
    ['b', 'Shorter. Two paragraphs.'],
    ['B', 'Cut to two. The open threads are now one closing sentence.'],
    ['b', 'Good. What do we know about the lights beyond the reef?'],
    ['C', 'Two sightings, both at slack tide. Nothing in the notes says what they are.'],
    ['b', 'Before the next session, check the campaign notes for what the party agreed with the harbour master.'],
    ['C', 'Found it in the D&D Knowledge source, Sessions/Session 09.md: safe berth for one season, in exchange for charting the eastern reef. The copy Mentis holds was taken on October 2, so anything written since is not in it.'],
    ['b', 'Good. I have added two sessions since then, so that copy is stale.'],
  ]
  const convs = [
    { id: 'c1', title: 'Colony Island Three', who: 'brian, Caretaker, Builder', posts: LINES.slice(), base: 244 },
    { id: 'c2', title: 'Quiet Chat usability, round 4', who: 'brian, Builder, Reviewer', base: 12,
      posts: [['b', 'The background browser checks keep dying again. Did we not learn something about this last week?'], ['B', 'Yes. There is an adopted lesson for exactly this. I waited for the test this time and it returned its result.'], ['b', 'Good. Next: the composer loses focus after sending.'], ['B', 'Reproduced. The focus moves to the new post. Fix is ready on the branch.'], ['R', 'Reviewed. One note on the keyboard path; otherwise fine.'], ['b', 'Ship it to TEST.']] },
    { id: 'c3', title: 'Client handbook questions', who: 'brian, Caretaker', base: 3,
      posts: [['b', 'What does the handbook say about on-call handover?'], ['C', 'From the Client handbook source, engineering/on-call.md: handover is at 10:00 on Mondays, with a written summary. That copy was taken on October 30.'], ['b', 'It has changed since. I need to refresh that source.']] },
  ]
  const WHO = { b: ['brian', ''], C: ['Caretaker', ' agent'], B: ['Builder', ' agent'], R: ['Reviewer', ' agent'] }

  /* ---- state ---------------------------------------------------------------- */
  const st = {
    conv: 'c1', view: 'conv', source: null, last: null, cols: 1, split: 0.56,
    card: { open: false, q: '', tab: 'all', kind: '', order: 'recent', scroll: 0 },
    open: { contents: true }, tree: {}, find: '', panel: null, menu: null, beside: null, scroll: {}, draft: null,
  }
  const timers = {}

  /* ---- skeleton -------------------------------------------------------------- */
  document.body.innerHTML = `
  <div class="q2 fx q2-arr-one q2-side-left mk" id="root">
    <header class="q2-top">
      <span class="mk-brand"><svg viewBox="0 0 14 14" fill="none" stroke="currentColor"><circle cx="7" cy="7" r="5.5"/><circle cx="7" cy="7" r="1.6"/></svg>Mentis : <b>Prototype</b></span>
      <span class="q2-top-conv" id="topconv"></span>
      <span class="q2-top-gap"></span>
      ${FRAME ? '' : '<span class="pt-tools" id="tools"></span><span class="mk-tag">prototype · sample data · simulated</span>'}
    </header>
    <nav class="mk-rail" aria-label="Rail" id="rail"></nav>
    <div class="q2-work"><div class="q2-panes" id="panes">
      <section class="q2-pane q2-conv" id="pane">
        <div class="pt-conv" id="convwrap"></div>
        <div class="q2-col q2-col-brain pt-hidden" id="srccol"><div class="q2-stream q2-brain-main" id="src"></div></div>
      </section>
      <div class="q2-divider pt-hidden" id="divider" role="separator" aria-orientation="vertical" tabindex="0" aria-label="Resize the centre column" title="Drag to resize"></div>
      <section class="q2-pane mk-beside pt-hidden" id="beside"></section>
    </div></div>
    <div class="q2-brain-veil pt-hidden" id="veil"><div class="q2-brain-card" role="dialog" aria-label="Sources" id="card"><div class="q2-cl" id="cardin"></div></div></div>
    <div class="pt-toast pt-hidden" id="toast" role="status"></div>
  </div>`
  const $ = (id) => document.getElementById(id)
  const pane = $('pane'), root = $('root')

  let toastT
  const toast = (words) => { const t = $('toast'); t.textContent = words; t.classList.remove('pt-hidden'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.add('pt-hidden'), 3800) }

  /* ---- top line and rail ------------------------------------------------------ */
  function paintTop() {
    const c = convs.find((x) => x.id === st.conv)
    $('topconv').textContent = c.title
    document.title = (st.view === 'source' && st.source ? byId(st.source).name + ' · Sources' : st.view === 'add' ? 'New source · Sources' : c.title) + ' · Quiet (prototype)'
    if (FRAME) return
    $('tools').innerHTML = `
      <button data-act="theme" title="Switch theme">${theme === 'dark' ? 'Light theme' : 'Dark theme'}</button>
      <button data-act="cols" class="pt-wide${st.cols === 2 ? ' on' : ''}" title="Quiet Chat's Columns setting">${st.cols === 2 ? 'One column' : 'Two columns'}</button>
      <button data-act="phone" class="pt-wide" title="Open this prototype at a phone's width">Phone width</button>
      <button data-act="reset" class="pt-wide" title="Start the prototype over">Reset</button>`
  }
  function paintRail() {
    const w = [22, 30, 14]
    $('rail').innerHTML = `
      <button class="mk-icon" data-act="brain" title="Brain" aria-label="Brain">${ICON.brain}</button>
      <button class="mk-icon${st.card.open || st.view !== 'conv' ? ' on' : ''}" data-act="sources" title="Sources" aria-label="Sources">${ICON.store}</button>
      <button class="mk-plus" data-act="newconv" aria-label="New conversation" title="New conversation">+</button>
      <ul>${convs.map((c, i) => `<li class="${c.id === st.conv ? 'current' : ''}"><button data-act="conv" data-id="${c.id}" title="${esc(c.title)}" aria-label="${esc(c.title)}"><span class="q2-bar" style="width:${w[i % 3]}px;height:2px"></span></button></li>`).join('')}</ul>`
  }

  /* ---- the conversation -------------------------------------------------------- */
  function paintConv() {
    const c = convs.find((x) => x.id === st.conv)
    $('convwrap').innerHTML = `<div class="q2-col">
      <header class="q2-conv-head"><h1>${esc(c.title)}</h1><p class="q2-conv-meta">${c.base + c.posts.length} posts · ${esc(c.who)}</p></header>
      ${c.posts.map(([w, text], i) => `<article class="q2-post"><div class="q2-article">
        <div class="q2-byline"><span class="mk-avatar${WHO[w][1]}">${w}</span><span class="q2-byline-words"><span class="q2-name">${WHO[w][0]}</span><span class="q2-byline-meta">#${c.base + i + 1}</span></span></div>
        <div class="q2-prose">${esc(text)}</div></div></article>`).join('')}
      <div class="pt-dock"><input id="composer" placeholder="Message ${esc(c.title)}…" aria-label="Message" autocomplete="off"></div>
    </div>`
  }

  /* ---- views: which is shown, and where each was left ---------------------------- */
  const key = () => st.view === 'conv' ? 'conv:' + st.conv : st.view === 'source' ? 'src:' + st.source : 'add'
  const keep = () => { st.scroll[key()] = pane.scrollTop }
  function show(view, id) {
    keep()
    st.view = view; st.panel = null; st.menu = null
    if (view === 'source') { st.source = id; st.last = id; st.find = '' }
    $('convwrap').classList.toggle('pt-hidden', view !== 'conv')
    $('srccol').classList.toggle('pt-hidden', view === 'conv')
    if (view === 'conv') paintConv(); else paintSrc()
    const k = key()
    pane.scrollTop = st.scroll[k] ?? (view === 'conv' ? pane.scrollHeight : 0)
    paintTop(); paintRail(); measure()
  }
  function paintSrc() {
    const top = pane.scrollTop
    $('src').innerHTML = st.view === 'add' ? addHtml() : st.view === 'source' ? sourceHtml(byId(st.source)) : ''
    pane.scrollTop = top
  }

  /* ---- the Sources browser ------------------------------------------------------- */
  function stateWords(s) {
    if (s.run) return ['run', `Refreshing now · ${num(s.run.files)} ${unit(s)}, ${bytes(s.run.bytes)} so far`]
    if (s.failure) return ['bad', `Last refresh failed · ${s.failure.kind}`]
    if (!s.bound && !s.held.n) return ['none', 'Declared · nothing taken yet']
    const held = s.kind === 'sqlite' ? `${s.held.tables} tables, ${num(s.held.n)} rows` : `${num(s.held.n)} files`
    if (!s.bound) return ['off', `Not connected on this machine · ${held} held · taken ${s.last.split(',')[0]}`]
    if (!s.held.n) return ['', 'Connected here · nothing taken yet']
    return ['', `Connected here · ${held} · refreshed ${s.last.split(',')[0]}`]
  }
  function listed() {
    const c = st.card, q = c.q.trim().toLowerCase()
    let rows = sources.filter((s) => (!q || (s.name + ' ' + KIND[s.kind]).toLowerCase().includes(q)) && (!c.kind || s.kind === c.kind) &&
      (c.tab === 'all' || (c.tab === 'here' && s.bound) || (c.tab === 'away' && !s.bound) || (c.tab === 'attention' && s.failure)))
    if (c.order === 'name') rows = rows.slice().sort((a, b) => a.name.localeCompare(b.name))
    if (c.order === 'size') rows = rows.slice().sort((a, b) => b.held.bytes - a.held.bytes)
    return rows
  }
  function paintCard() {
    $('veil').classList.toggle('pt-hidden', !st.card.open)
    if (!st.card.open) return
    const c = st.card, attention = sources.filter((s) => s.failure).length
    const tab = (id, label, n) => `<button role="tab" data-act="tab" data-id="${id}" aria-selected="${c.tab === id}">${label}${n ? `<span class="q2-brain-tabcount">${n}</span>` : ''}</button>`
    const count = (k) => sources.filter((s) => s.kind === k).length
    $('cardin').innerHTML = `
      <header class="q2-cl-head"><h2>Sources</h2><span class="q2-brain-tools">
        <button type="button" class="q2-brain-more" data-act="add" aria-label="Add a source" title="Add a source">+</button>
        <button type="button" class="q2-cl-close" data-act="closecard" aria-label="Close" title="Close">×</button></span></header>
      <input type="search" class="q2-cl-filter" id="cardq" placeholder="Find a source" aria-label="Find a source" autocomplete="off" value="${esc(c.q)}">
      <div class="q2-cl-tabs" role="tablist" aria-label="Which sources">${tab('all', 'All')}${tab('here', 'Connected here')}${tab('away', 'Not connected')}${tab('attention', 'Needs attention', attention)}</div>
      <div class="q2-brain-narrow">
        <select id="cardkind" aria-label="Kind of source"><option value="">Any kind</option>${['folder', 'git', 'sqlite'].map((k) => `<option value="${k}"${c.kind === k ? ' selected' : ''}>${KIND[k]} · ${count(k)}</option>`).join('')}</select>
        <select id="cardorder" aria-label="Order">${[['recent', 'As listed'], ['name', 'Name'], ['size', 'Largest']].map(([v, l]) => `<option value="${v}"${c.order === v ? ' selected' : ''}>${l}</option>`).join('')}</select>
      </div>
      <ul class="q2-brain-rows" role="list" id="rows"></ul>
      <button class="sv-add pt-add" data-act="add">＋ Add a source…</button>
      <p class="q2-brain-foot"><span id="cardfoot"></span></p>`
    paintRows()
    $('rows').scrollTop = c.scroll
    $('rows').addEventListener('scroll', (e) => { st.card.scroll = e.currentTarget.scrollTop })
    measure()
  }
  function paintRows() {
    if (!st.card.open || !$('rows')) return
    const rows = listed(), ul = $('rows'), top = ul.scrollTop
    ul.innerHTML = rows.map((s) => { const [dot, words] = stateWords(s); return `<li><button type="button" class="q2-brain-row" data-act="open" data-id="${s.id}"${s.id === st.last ? ' aria-current="true"' : ''}><span class="q2-brain-text">
        <span class="sv-row-top"><span class="q2-brain-name">${esc(s.name)}</span><span class="sv-kind">${KSHORT[s.kind]}</span></span>
        <span class="q2-brain-meta sv-state${dot === 'bad' ? ' sv-bad' : dot === 'run' ? ' sv-run' : dot === 'off' || dot === 'none' ? ' q2-brain-off' : ''}"><span class="sv-dot ${dot}"></span>${esc(words)}</span></span></button></li>` }).join('') ||
      `<li class="q2-cl-note">${st.card.q || st.card.kind || st.card.tab !== 'all' ? 'Nothing matches.' : 'No sources yet.'}</li>`
    ul.scrollTop = top
    const here = sources.filter((s) => s.bound).length
    $('cardfoot').textContent = `${rows.length === sources.length ? sources.length + ' sources' : rows.length + ' of ' + sources.length + ' sources'} · ${here} connected on this machine · ${bytes(sources.reduce((a, s) => a + s.held.bytes, 0))} held`
  }
  /* the card takes the room beside the reading column, as BrainBrowser.tsx measures it */
  function measure() {
    const card = $('card'); if (!st.card.open) return
    const column = st.view === 'conv' ? pane.querySelector('.pt-conv > .q2-col') : null
    const left = card.getBoundingClientRect().left
    const edge = column ? column.getBoundingClientRect().left - 24 : left
    card.style.setProperty('--q2-brain-room', Math.max(0, Math.floor(edge - left - 12)) + 'px')
  }
  new ResizeObserver(measure).observe(pane)

  /* ---- a source ------------------------------------------------------------------ */
  const fold = (id, title, sub, body) => { const o = !!st.open[id]; return `<div class="rv-d${o ? ' open' : ''}"><button data-act="fold" data-id="${id}" aria-expanded="${o}"><span class="c">${o ? '▾' : '▸'}</span>${title}<span class="s">${sub}</span></button>${o ? `<div class="rv-body">${body}</div>` : ''}</div>` }
  function failHtml(s) {
    const f = s.failure
    return `<div class="sv-alert" role="alert">
      <h3>The last refresh failed: ${f.title}</h3>
      <p>Mentis asked this machine’s Git to fetch <span class="sv-code">${esc(s.remote)}</span> and was told:</p>
      <p><code>${f.kind}: ${esc(s.remote)}</code></p>
      <p>Mentis holds no password for it. Sign in to that server with Git on this machine (its credential helper, or an SSH key), then try again.</p>
      <p class="pt-simline"><label><input type="checkbox" data-change="signedin"${s.signedIn ? ' checked' : ''}> Pretend I have now signed in with Git on this machine</label><span class="pt-sim">prototype control</span></p>
    </div>`
  }
  function progressHtml(s) {
    return `<div class="sv-progress" role="status"><p><b>Refreshing now</b> · <span data-live="count">${num(s.run.files)} ${unit(s)}, ${bytes(s.run.bytes)}</span> taken so far · started ${s.run.started} by brian</p>
      <p class="cur" data-live="cur">${esc(s.run.current)}</p><div class="pt-bar"><i></i></div></div>`
  }
  function panelHtml(s) {
    const p = st.panel; if (!p || p.id !== s.id) return ''
    if (p.type === 'asking') return `<div class="sv-preview pt-panel"><h3>Looking at the source…</h3><p class="sv-note" style="margin:0">${s.remote ? 'Asking this machine’s Git to fetch it.' : 'Comparing it with what Mentis holds.'} Nothing is being taken.</p><div class="pt-bar"><i></i></div></div>`
    if (p.type === 'preview') {
      const pl = s.plan, nothing = !pl.neu && !pl.changed && !pl.gone && !p.dropped
      const u = unit(s)
      return `<div class="sv-preview pt-panel" role="region" aria-label="Preview"><h3>Preview · nothing has been taken</h3>${nothing
        ? `<p class="sv-note" style="margin:0">Nothing has changed since the last refresh.</p><div class="sv-acts"><button class="sv-btn" data-act="closepanel">Close</button></div>`
        : `<ul class="sv-list">
          <li>New<span class="n">${num(pl.neu)} ${u}</span></li><li>Changed<span class="n">${num(pl.changed)}</span></li><li>No longer in the source<span class="n">${num(pl.gone)}</span></li>
          ${p.dropped ? `<li>No longer included, by your change<span class="n">${num(p.dropped)}</span></li>` : ''}
          <li>Withheld: names that look like secrets<span class="n">${s.withheld.length}</span></li><li>To be taken<span class="n">about ${bytes(pl.bytes)}</span></li></ul>
          <div class="sv-acts"><button class="sv-btn go" data-act="take">${s.held.n ? 'Take these changes' : `Take these ${num(pl.neu)} ${u}`}</button><button class="sv-btn" data-act="preview">Preview again</button><button class="sv-btn quiet" data-act="closepanel">Not now</button></div>
          <p class="sv-note">The preview is good until the source changes; if it has, taking asks you to preview again.</p>`}</div>`
    }
    if (p.type === 'scope') return `<div class="sv-preview pt-panel"><h3>Change what is included</h3>
      <label for="sc-in">Include, one pattern per line</label><textarea id="sc-in" rows="2">${esc(s.scope.include)}</textarea>
      <label for="sc-ex">Leave out, one pattern per line</label><textarea id="sc-ex" rows="3">${esc(s.scope.exclude)}</textarea>
      <div class="sv-acts"><button class="sv-btn go" data-act="savescope">Save and preview</button><button class="sv-btn quiet" data-act="closepanel">Cancel</button></div>
      <p class="sv-note">This decides what enters the Brain. It is recorded as a new version; the preview then shows what it changes before anything is taken.</p></div>`
    if (p.type === 'stop') return `<div class="sv-preview pt-panel"><h3>Stop refreshing ${esc(s.name)} from this machine?</h3>
      <p class="sv-note" style="margin:0">Mentis forgets where it is on this machine, so it can no longer be refreshed from here. Everything Mentis holds from it stays, and agents can still read it. You can locate it again later.</p>
      <div class="sv-acts"><button class="sv-btn go" data-act="stopyes">Stop refreshing here</button><button class="sv-btn quiet" data-act="closepanel">Keep it connected</button></div></div>`
    if (p.type === 'locate') return `<div class="sv-preview pt-panel"><h3>Where is ${esc(s.name)} on this machine?</h3>
      ${s.remote ? `<label for="loc-addr">Its https or ssh address</label><input type="text" id="loc-addr" value="${esc(s.remote)}"><div class="sv-acts"><button class="sv-btn go" data-act="locateaddr">Use this address</button><button class="sv-btn quiet" data-act="closepanel">Cancel</button></div>`
        : `<p class="sv-note" style="margin:0">Quiet Chat would open this machine’s own ${s.kind === 'sqlite' ? 'file' : 'folder'} chooser here.<span class="pt-sim">simulated chooser</span></p>
      <ul class="pt-pick">${(s.pick || ['C:\\Users\\brian\\Documents\\' + s.name]).map((x) => `<li><button data-act="locatepick" data-id="${esc(x)}">${esc(x)}</button></li>`).join('')}</ul>
      <div class="sv-acts"><button class="sv-btn quiet" data-act="closepanel">Cancel</button></div>`}</div>`
    return ''
  }
  function contentsHtml(s) {
    if (!s.tree.length) return '<p>Nothing has been taken from this source yet.</p>'
    const q = st.find.trim().toLowerCase(), sql = s.kind === 'sqlite'
    const rows = s.tree.map((f) => {
      const files = sql ? null : (f.files || []).filter((x) => !q || (f.folder + x).toLowerCase().includes(q))
      if (q && (sql ? !f.folder.toLowerCase().includes(q) : !files.length)) return ''
      const k = s.id + ':' + f.folder, o = !!st.tree[k] || (!!q && !sql)
      if (sql) return `<li><button data-act="file" data-id="${esc(f.folder)}"${st.beside && st.beside.key === s.id + '/' + f.folder ? ' class="on"' : ''}>${esc(f.folder)}<span class="n">${num(f.n)} rows</span></button></li>`
      return `<li><button data-act="folder" data-id="${esc(f.folder)}" aria-expanded="${o}">${o ? '▾' : '▸'} ${esc(f.folder)}<span class="n">${num(f.n)}</span></button>${o ? `<ul>${files.map((x) => `<li><button data-act="file" data-id="${esc(f.folder + x)}"${st.beside && st.beside.key === s.id + '/' + f.folder + x ? ' class="on"' : ''}>${esc(x)}</button></li>`).join('')}${!q && f.n > files.length ? `<li><button data-act="morefiles">… ${num(f.n - files.length)} more</button></li>` : ''}</ul>` : ''}</li>`
    }).join('')
    return `<input class="pt-find" id="find" placeholder="Find in what Mentis holds from ${esc(s.name)}" aria-label="Find in contents" autocomplete="off" value="${esc(st.find)}">
      <ul class="pt-tree" id="tree">${rows || '<li style="padding:8px 4px;color:var(--text-faint)">Nothing matches.</li>'}</ul>
      <p class="sv-note">${sql ? 'Choose a table to read its rows beside this.' : 'Choose a file to read it beside this.'} These are the copies Mentis holds, not the source itself.</p>`
  }
  function sourceHtml(s) {
    const u = unit(s), h = s.held, sc = s.scope
    const kindLine = KIND[s.kind] + (s.remote ? ' · remote' : '')
    const what = !h.n ? `${s.what} It has been declared, and nothing has been taken from it yet.`
      : `${s.what} Mentis holds a copy of ${s.kind === 'sqlite' ? `${num(h.n)} rows from ${h.tables} tables` : `${num(h.n)} files`}${sc.branch ? ` from its <span class="sv-code">${esc(sc.branch)}</span> branch` : ''}, taken on ${s.last.split(',')[0]}. Agents read that copy, never the source itself.`
    let state, acts
    if (s.run) { state = progressHtml(s); acts = `<button class="sv-btn" data-act="cancelrun">Cancel this refresh</button><span class="sv-note" style="margin:0;align-self:center">It reports ${u} and bytes as it goes; it does not know how many remain.</span>` }
    else if (s.failure) {
      state = failHtml(s) + `<p class="rv-state"><span class="dot ask"></span><span><span class="q2e-status">Held · not refreshed</span>What Mentis took on ${s.last.split(',')[0]} is still here and still readable.</span></p><p class="rv-sub">Failed ${s.failure.when}, asked by brian · last refreshed ${s.last} by brian</p>`
      acts = `<button class="sv-btn go" data-act="preview">Try again</button><button class="sv-btn" data-act="locate">Locate it somewhere else…</button><button class="sv-btn quiet" data-act="stop">Stop refreshing here</button>`
    } else if (!s.bound) {
      state = `<p class="rv-state"><span class="dot" style="background:transparent;border:1.5px solid var(--text-faint)"></span><span><span class="q2e-status">${h.n ? 'Not connected on this machine' : 'Declared · nothing taken yet'}</span>${h.n ? 'Mentis holds what was taken, and agents can read it. It cannot be refreshed until you say where it is on this machine.' : 'Say where it is on this machine, then preview what would be taken.'}</span></p>
        <p class="rv-sub">${h.n ? `Last refreshed ${s.last} by brian · ` : ''}declared ${s.declared} by brian</p>`
      acts = `<button class="sv-btn go" data-act="locate">Locate it on this machine…</button>`
    } else {
      state = `<p class="rv-state"><span class="dot"></span><span><span class="q2e-status">Connected here</span>It can be refreshed from this machine. It is refreshed only when you ask.</span></p>
        <p class="rv-sub">${h.n ? `Last refreshed ${s.last} by brian · ` : ''}declared ${s.declared} by brian</p>`
      acts = `<button class="sv-btn go" data-act="preview" title="Looks at the source and shows what would change, before anything is taken">${h.n ? 'Refresh…' : 'Preview what would be taken…'}</button><button class="sv-btn" data-act="scope">Change what is included…</button><button class="sv-btn quiet" data-act="stop">Stop refreshing here</button>`
    }
    const facts = h.n ? `<div class="sv-facts" aria-label="What Mentis holds">
        <div><b>${num(h.n)}</b><span>${u} held</span></div>${h.tables ? `<div><b>${h.tables}</b><span>tables</span></div>` : ''}<div><b>${bytes(h.bytes)}</b><span>held in the Brain</span></div>
        ${s.kind !== 'sqlite' ? `<div><b>${num(h.links)}</b><span>links between them</span></div>` : ''}<div><b>${num(h.unselected)}</b><span>seen, not included</span></div><div><b>${num(h.absent)}</b><span>gone from the source</span></div></div>` : ''
    const lines = (t) => t.split('\n').filter(Boolean).map((x) => `<span class="sv-code">${esc(x)}</span>`).join(' ') || '<span style="color:var(--text-faint)">nothing</span>'
    const nEx = sc.exclude.split('\n').filter(Boolean).length
    const menu = st.menu === 'source' ? `<div class="pt-menu" role="menu">
        <button role="menuitem" data-act="copyref">Copy a reference to this source<small>To paste into a message, so an agent knows which source you mean</small></button>
        <button role="menuitem" data-act="fluid">Open in Fluid’s Sources<small>The existing page, with every detail</small></button></div>` : ''
    return `<div class="q2-back-bar rv-backbar">
        <button class="q2-back-btn" data-act="backlist">‹ Sources</button>
        <span class="q2-back-where">Source</span>
        <button class="q2-link-quiet" data-act="backconv">Back to the conversation</button></div>
      <div class="rv rv-full"><div class="rv-grid">
        <div class="rv-main">
          <div class="rv-top"><p class="rv-kind">${kindLine}</p><span class="pt-menuwrap"><button class="rv-head-menu" data-act="menu" aria-label="More on this source" aria-expanded="${st.menu === 'source'}">⋯</button>${menu}</span></div>
          <h1 class="sv-name">${esc(s.name)}</h1>
          <p class="sv-what">${what}</p>
          ${s.note ? `<p class="sv-note" style="margin:0 0 14px">${esc(s.note)}</p>` : ''}
          ${state}
          <div class="sv-acts">${acts}</div>
          ${panelHtml(s)}
          ${facts}
          ${s.sweeps.length ? `<p class="sv-note">Last refresh: ${esc(s.sweeps[0][1])}${s.withheld.length ? `, ${s.withheld.length} withheld because their names look like secrets` : ''}.</p>` : ''}
        </div>
        <div class="rv-more">
          ${fold('contents', 'Contents', h.n ? `${s.kind === 'sqlite' ? h.tables + ' tables' : num(h.n) + ' files in ' + s.tree.length + ' folders'}` : 'nothing yet', contentsHtml(s))}
          ${fold('scope', 'What is included', nEx ? `everything matching, except ${nEx} pattern${nEx > 1 ? 's' : ''}` : 'everything matching', `<dl class="sv-kv">
            <dt>Includes</dt><dd>${lines(sc.include)}</dd><dt>Leaves out</dt><dd>${lines(sc.exclude)}</dd>
            ${sc.branch ? `<dt>Branch</dt><dd><span class="sv-code">${esc(sc.branch)}</span></dd><dt>History</dt><dd>${sc.history}</dd>` : ''}${sc.columns ? `<dt>Columns</dt><dd>${sc.columns}</dd>` : ''}
            <dt>Last changed</dt><dd>${sc.changed} · version ${sc.revisions}</dd></dl>${s.bound && !s.run ? '<p class="sv-note"><button class="rv-link" data-act="scope">Change what is included…</button></p>' : ''}`)}
          ${fold('history', 'Refresh history', `${s.sweeps.length} refresh${s.sweeps.length === 1 ? '' : 'es'}`, s.sweeps.length ? `<ul class="sv-list">${s.sweeps.map(([w, t]) => `<li><span class="w">${w}</span> brian · ${esc(t)}</li>`).join('')}</ul><p class="sv-note">Only refreshes that completed are kept. Failed and cancelled ones are not recorded.</p>` : '<p>It has not been refreshed yet.</p>')}
          ${s.pdf && h.n ? fold('text', 'Text read from the PDFs', '31 of 38 read', '<ul class="sv-list"><li>Read<span class="n">31</span></li><li>Still being read<span class="n">5</span></li><li>No text could be read<span class="n">2</span></li></ul><p class="sv-note">A scanned PDF has no text to read; Mentis does not recognise text in images.</p>') : ''}
          ${fold('where', 'Where it is on this machine', s.bound ? `connected since ${s.since}` : 'not connected', `<p>Mentis remembers where a source is on this machine only, apart from the Brain. Another machine with the same Brain sees it as not connected until it is located there.</p>${s.remote ? `<p>Address: <span class="sv-code">${esc(s.remote)}</span></p>` : s.bound ? '<p class="sv-note">The folder itself is not shown: the source system does not hand the path back.</p>' : ''}${s.run ? '' : `<p class="sv-note"><button class="rv-link" data-act="locate">${s.bound ? 'Locate it somewhere else…' : 'Locate it on this machine…'}</button></p>`}`)}
          ${fold('who', 'Who can read it', 'every agent', '<p>What Mentis holds from a source can be read and searched by every agent, in every conversation. There is no per-source restriction today.</p>')}
          ${s.withheld.length ? fold('withheld', 'Withheld', `${s.withheld.length} files`, `<ul class="sv-list sv-tree">${s.withheld.map((x) => `<li>${esc(x)}<span class="n">name looks like a secret</span></li>`).join('')}</ul><p class="sv-note">Names are checked, not contents. A file you include on purpose is taken as it is.</p>`) : ''}
        </div>
      </div></div>`
  }

  /* ---- simulated operations ----------------------------------------------------------- */
  const samplePath = (s) => { const t = s.tree.length ? s.tree : (s.futureTree || [F('', 0, ['…'])]); const f = t[Math.floor(Math.random() * t.length)]; return f.files ? f.folder + f.files[Math.floor(Math.random() * f.files.length)] : f.folder }
  function startRun(s, done, pace) {
    const total = Math.max(40, s.held.n + s.plan.neu), totalBytes = Math.max(2e5, s.held.bytes + s.plan.bytes)
    s.run = { files: done || 0, bytes: (done || 0) / total * totalBytes, current: samplePath(s), started: now().split(', ')[1] }
    s.failure = null; s.note = null
    const step = Math.max(1, Math.ceil(total / 48))
    clearInterval(timers[s.id])
    timers[s.id] = setInterval(() => {
      s.run.files = Math.min(total, s.run.files + step + Math.floor(Math.random() * step))
      s.run.bytes = s.run.files / total * totalBytes
      s.run.current = samplePath(s)
      if (s.run.files >= total) return finishRun(s)
      live(s)
    }, pace || 280)
  }
  function finishRun(s) {
    clearInterval(timers[s.id])
    const pl = s.plan, first = !s.held.n
    if (first && s.futureTree) s.tree = s.futureTree
    s.held.n += pl.neu - pl.gone; s.held.bytes += pl.bytes; s.held.absent += pl.gone
    if (s.kind !== 'sqlite') s.held.links += Math.round(pl.neu * 0.4)
    s.last = now()
    s.sweeps.unshift([s.last, first ? `first taken · ${num(pl.neu)} new` : `${pl.neu} new${s.kind === 'sqlite' ? ' rows' : ''}, ${pl.changed} changed${pl.gone ? ', ' + pl.gone + ' gone' : ''}`])
    s.plan = { neu: 0, changed: 0, gone: 0, bytes: 0 }; s.run = null
    toast(`${s.name} was refreshed. ${first ? num(s.held.n) + ' ' + unit(s) + ' taken.' : 'What Mentis holds is now as of ' + s.last + '.'}`)
    repaint(s)
  }
  function live(s) {
    if (st.view === 'source' && st.source === s.id) {
      const c = $('src').querySelector('[data-live=count]'), cur = $('src').querySelector('[data-live=cur]')
      if (c) c.textContent = `${num(s.run.files)} ${unit(s)}, ${bytes(s.run.bytes)}`
      if (cur) cur.textContent = s.run.current
    }
    paintRows()
  }
  const repaint = (s) => { if (st.view === 'source' && st.source === s.id) paintSrc(); paintRows() }
  function preview(s, extra) {
    st.panel = { id: s.id, type: 'asking' }; paintSrc()
    clearTimeout(timers.ask)
    timers.ask = setTimeout(() => {
      if (!st.panel || st.panel.id !== s.id || st.panel.type !== 'asking') return
      if (s.remote && s.signedIn === false) {
        s.failure = { when: now(), title: 'sign-in was refused', kind: 'authentication required' }
        st.panel = null; toast('Git refused the sign-in again. Nothing was taken.')
      } else { s.failure = null; st.panel = { id: s.id, type: 'preview', ...(extra || {}) } }
      repaint(s)
    }, 1400)
  }

  /* ---- the working column ---------------------------------------------------------------- */
  function fileBody(s, path) {
    if (s.kind === 'sqlite') {
      const rows = { characters: [['1', 'Kessa', 'Ranger', '6'], ['2', 'Dorn', 'Cleric', '6'], ['3', 'Ilse Varn', 'NPC', '—']], sessions: [['9', 'The Harbour Master’s Bargain', '2026-09-28'], ['8', 'Fire at the Customs House', '2026-09-14']] }[path] || [['1', 'sample', 'row'], ['2', 'sample', 'row']]
      return `<table><tr>${rows[0].map((_, i) => `<th>${['id', 'name', 'value', 'level'][i] || 'col' + i}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</table><p class="sv-note">The first rows of ${esc(path)}, as held.</p>`
    }
    if (/Session 09/.test(path)) return `<div class="prose"><h2>Session 09: The Harbour Master’s Bargain</h2><p>The party reached Saltmere at dusk. Harbour Master Ilse Varn offered safe berth for one season in exchange for a chart of the eastern reef, to be delivered before the autumn tides.</p><p>Kessa signed for the party. Dorn objected and was overruled. The chart is owed; nothing was said about what happens if the reef cannot be charted.</p><p>Open threads: the missing pilot’s ledger, the lights seen beyond the reef, and who paid for the party’s berth before they arrived.</p></div>`
    if (/\.pdf$/.test(path)) return `<div class="prose"><h2>${esc(path.split('/').pop())}</h2><p>The text Mentis read from this PDF would be shown here, page by page.</p></div>`
    if (/\.(md|txt)$/.test(path)) return `<div class="prose"><h2>${esc(path.split('/').pop().replace(/\.\w+$/, ''))}</h2><p>Sample text standing in for this file. In Quiet Chat this would be the file as Mentis holds it, rendered, with its links to other files in the same source.</p><p>It is the copy taken at the last refresh, not the file as it is now.</p></div>`
    return `<pre>${esc(`# ${path}\n# Sample text standing in for this file, as Mentis holds it.\n\ndef example():\n    """The held copy, exactly as taken at the last refresh."""\n    return "sample"\n`)}</pre>`
  }
  function paintBeside() {
    const two = st.cols === 2 && !FRAME
    root.classList.toggle('q2-arr-two', two); root.classList.toggle('q2-arr-one', !two)
    $('beside').classList.toggle('pt-hidden', !two); $('divider').classList.toggle('pt-hidden', !two)
    pane.style.flex = two ? `${st.split} 1 0` : '1 1 0'
    $('beside').style.flex = `${1 - st.split} 1 0`
    if (!two) return
    const b = st.beside
    $('beside').innerHTML = b ? `<header><b>${esc(b.title)}</b><span>${esc(b.meta)}</span><button data-act="closefile" title="Close this file">×</button></header><div class="pt-file">${b.html}</div>`
      : `<header><b>Working column</b><span>Quiet Chat’s second column</span><button data-act="cols" title="Back to one column">×</button></header><div class="pt-empty">A file from a source opens here: choose one under a source’s Contents. Drag the divider to resize the centre column.</div>`
  }
  function openFile(s, path) {
    st.beside = { key: s.id + '/' + path, title: path.split('/').pop() || path, meta: `${s.name} · as taken ${s.last.split(',')[0]}`, html: fileBody(s, path) }
    if (FRAME || innerWidth < 900) { toast(`${path}: on a phone the file would open in place of this page, with Back returning here.`); return }
    st.cols = 2; paintBeside(); paintTop(); paintSrc()
  }

  /* ---- adding a source ---------------------------------------------------------------------- */
  const blank = (kind) => ({ kind, name: '', where: '', mode: 'local', address: '', branch: 'main', history: 'latest', preset: 'Everything', exclude: '', tables: '*', picking: false, preview: null, stale: false, error: '' })
  const SAMPLE = { folder: ['C:\\Users\\brian\\Documents\\Campaign notes', 'C:\\Users\\brian\\Documents\\Research', 'D:\\Archive\\Handbooks'], git: ['C:\\Work\\Mentis', 'C:\\Work\\MARS', 'C:\\Projects\\oatmeal'], sqlite: ['C:\\Users\\brian\\Documents\\campaign.db', 'D:\\Data\\inventory.sqlite'] }
  function addPlan(d) {
    const base = { folder: { Everything: 412, Documents: 268, 'Source code': 97 }, git: { Everything: 530, Documents: 141, 'Source code': 344 }, sqlite: {} }[d.kind]
    const ex = d.exclude.split('\n').filter((x) => x.trim()).length
    if (d.kind === 'sqlite') return { n: 2840, tables: 9, left: ex, withheld: 0, bytes: 1.1e6, tree: [F('customers', 412, null), F('orders', 1980, null), F('products', 448, null)] }
    const n = Math.max(12, (base[d.preset] || base.Everything) - ex * 14)
    return { n, left: ex * 14, withheld: d.kind === 'git' ? 2 : 1, bytes: n * 23800, tree: [F('notes/', Math.round(n * 0.5), ['overview.md', 'decisions.md']), F('reference/', Math.round(n * 0.3), ['glossary.md']), F('archive/', n - Math.round(n * 0.5) - Math.round(n * 0.3), ['2025.md'])] }
  }
  function addPreviewHtml() {
    const d = st.draft
    if (!d || !d.kind) return `<div class="sv-preview pt-wait">Choose a kind of source to begin.</div>`
    if (d.preview === 'asking') return `<div class="sv-preview"><h3>Looking at the source…</h3><p class="sv-note" style="margin:0">Nothing is being taken.</p><div class="pt-bar"><i></i></div></div>`
    if (!d.preview) return `<div class="sv-preview pt-wait"><h3 style="color:var(--text)">Preview</h3>Say where it is and what to include, then preview. A preview looks at the source and shows what would be taken. It takes nothing.</div>`
    const p = d.preview, u = d.kind === 'sqlite' ? 'rows' : 'files'
    return `<div class="sv-preview${d.stale ? ' pt-stale' : ''}" role="region" aria-label="Preview"><h3>Preview · nothing has been taken${d.stale ? ' · out of date' : ''}</h3>
      <ul class="sv-list"><li>Would be taken<span class="n">${num(p.n)} ${u}${p.tables ? ' in ' + p.tables + ' tables' : ''} · ${bytes(p.bytes)}</span></li>
      <li>Left out by your patterns<span class="n">${num(p.left)}</span></li><li>Withheld: names that look like secrets<span class="n">${p.withheld}</span></li><li>Could not be examined<span class="n">0</span></li></ul>
      <ul class="sv-list sv-tree" style="margin-top:12px">${p.tree.map((f) => `<li>${esc(f.folder)}<span class="n">${num(f.n)}</span></li>`).join('')}</ul>
      <div class="sv-acts" style="margin-top:18px">${d.stale ? '<button class="sv-btn go" data-act="addpreview">Preview again</button>' : `<button class="sv-btn go" data-act="addtake">Take these ${num(p.n)} ${u}</button><button class="sv-btn" data-act="addpreview">Preview again</button>`}<button class="sv-btn quiet" data-act="addcancel">Cancel</button></div>
      <p class="sv-note">${d.stale ? 'You changed something after this preview. Preview again before taking.' : 'A large source reports files and bytes as it is taken, and can be cancelled.'}</p></div>`
  }
  function addHtml() {
    const d = st.draft, k = d.kind
    const kc = (id, title, sub) => `<button class="sv-kindcard${k === id ? ' on' : ''}" data-act="addkind" data-id="${id}" aria-pressed="${k === id}"><b>${title}</b><span>${sub}</span></button>`
    const step = !k ? 0 : d.preview && d.preview !== 'asking' && !d.stale ? 3 : 1
    const steps = ['Kind', 'Where and what', 'Preview', 'Take it'].map((t, i) => `<li class="${i < step || (i === 1 && step === 3) ? 'done' : ''}${(step === 0 && i === 0) || (step === 1 && i === 1) || (step === 3 && i === 3) ? ' on' : ''}">${t}</li>`).join('')
    const chooser = d.picking ? `<p class="sv-note" style="margin:8px 0 0">Quiet Chat would open this machine’s own chooser here.<span class="pt-sim">simulated chooser</span></p><ul class="pt-pick">${SAMPLE[k].map((x) => `<li><button data-act="addpick" data-id="${esc(x)}">${esc(x)}</button></li>`).join('')}</ul>` : ''
    const whereLocal = `<div class="sv-inline"><input type="text" data-f="where" value="${esc(d.where)}" placeholder="${k === 'sqlite' ? 'A .db or .sqlite file' : 'A folder on this machine'}"><button class="sv-btn" data-act="addchoose">Choose…</button></div>${chooser}`
    let fields = ''
    if (k) fields = `<p class="sv-h">Where and what</p>
      <label class="sv-field"><span>Name</span><input type="text" data-f="name" value="${esc(d.name)}" placeholder="What you will call it"></label>
      <div class="sv-field"><span>Where it is</span>${k === 'git' ? `<div class="sv-radio" style="margin-bottom:8px">
          <label><input type="radio" name="mode" data-change="mode" value="local"${d.mode === 'local' ? ' checked' : ''}> A repository on this machine</label>
          <label><input type="radio" name="mode" data-change="mode" value="remote"${d.mode === 'remote' ? ' checked' : ''}> An https or ssh address</label></div>
          ${d.mode === 'local' ? whereLocal : `<div class="sv-inline"><input type="text" data-f="address" value="${esc(d.address)}" placeholder="https://git.example.com/team/project.git"></div>
          <p class="hint">Mentis stores no passwords or tokens. A private repository is reached with this machine’s own Git sign-in (its credential helper, or SSH keys). An address that contains a password or token is refused.</p>`}` : whereLocal}
        ${d.error ? `<p class="bad" role="alert">${esc(d.error)}</p>` : ''}</div>
      ${k === 'git' ? `<label class="sv-field"><span>Branch or tag</span><input type="text" data-f="branch" value="${esc(d.branch)}"></label>
        <div class="sv-field"><span>History</span><div class="sv-radio"><label><input type="radio" name="hist" data-change="history" value="latest"${d.history === 'latest' ? ' checked' : ''}> The latest commit only</label><label><input type="radio" name="hist" data-change="history" value="50"${d.history === '50' ? ' checked' : ''}> The last 50 commits</label></div></div>` : ''}
      ${k === 'sqlite' ? `<label class="sv-field"><span>Tables to include</span><input type="text" data-f="tables" value="${esc(d.tables)}"><p class="hint">Patterns, separated by spaces. The file is opened read-only.</p></label>`
        : `<div class="sv-field"><span>What to include</span><div class="sv-presets">${['Everything', 'Documents', 'Source code'].map((p) => `<button class="sv-chip${d.preset === p ? ' on' : ''}" data-act="addpreset" data-id="${p}">${p}</button>`).join('')}</div></div>`}
      <label class="sv-field"><span>Leave out</span><textarea rows="2" data-f="exclude" placeholder="${k === 'sqlite' ? 'audit_log' : 'drafts/**'}">${esc(d.exclude)}</textarea><p class="hint">One pattern per line. This decides what enters the Brain; it can be changed later.</p></label>
      <div class="sv-acts" style="margin:0 0 30px"><button class="sv-btn go" data-act="addpreview">Preview</button><button class="sv-btn quiet" data-act="addcancel">Cancel</button></div>`
    return `<div class="q2-back-bar rv-backbar">
        <button class="q2-back-btn" data-act="backlist">‹ Sources</button><span class="q2-back-where">New source</span>
        <button class="q2-link-quiet" data-act="backconv">Back to the conversation</button></div>
      <div class="rv rv-full"><div class="rv-grid">
        <div class="rv-main">
          <div class="rv-top"><p class="rv-kind">New source</p></div>
          <h1 class="sv-name">Add a source</h1>
          <ol class="sv-steps">${steps}</ol>
          <p class="sv-h">Kind</p>
          <div class="sv-kinds">${kc('folder', 'Folder on this machine', 'Files under a folder you choose')}${kc('git', 'Git repository', 'On this machine, or at an https or ssh address')}${kc('sqlite', 'SQLite database file', 'Tables from a .db or .sqlite file, opened read-only')}</div>
          <p class="sv-later">Not available yet:</p><div class="pt-later">${['Slack', 'Jira', 'Confluence', 'Gmail', 'HTTP API', 'Web', 'RSS / Atom'].map((x) => `<span>${x}</span>`).join('')}</div>
          ${fields}
        </div>
        <div class="rv-more" style="border-top:0" id="addpreview">${addPreviewHtml()}</div>
      </div></div>`
  }
  function addPreview() {
    const d = st.draft
    const where = d.kind === 'git' && d.mode === 'remote' ? d.address.trim() : d.where.trim()
    d.error = !d.name.trim() ? 'Give it a name first.' : !where ? 'Say where it is first.' : ''
    if (!d.error && d.kind === 'git' && d.mode === 'remote') {
      if (/^https?:\/\/[^/]*@/i.test(where) || /[?#]/.test(where)) d.error = 'This address carries sign-in details or extra parts. Mentis refuses it: give the plain address and sign in with Git on this machine.'
      else if (!/^(https:\/\/|ssh:\/\/|[\w.-]+@[\w.-]+:)/i.test(where)) d.error = 'That is not an https or ssh address.'
    }
    if (sources.some((s) => s.name.toLowerCase() === d.name.trim().toLowerCase())) d.error = 'There is already a source with that name.'
    if (d.error) { d.preview = null; paintSrc(); return }
    d.preview = 'asking'; d.stale = false; d.picking = false; paintSrc()
    clearTimeout(timers.addask)
    timers.addask = setTimeout(() => { if (st.view !== 'add' || st.draft !== d) return; d.preview = addPlan(d); paintSrc() }, 1300)
  }
  function addTake() {
    const d = st.draft, p = d.preview, remote = d.kind === 'git' && d.mode === 'remote'
    const s = { id: 'new' + Date.now(), name: d.name.trim(), kind: d.kind, remote: remote ? d.address.trim() : undefined, bound: true, since: 'today', signedIn: true,
      what: d.kind === 'folder' ? 'A folder of files.' : d.kind === 'sqlite' ? 'A SQLite database file on this machine, opened read-only.' : remote ? 'A Git repository at an https or ssh address.' : 'A Git repository on this machine.',
      held: { n: 0, bytes: 0, links: 0, unselected: p.left, absent: 0, tables: p.tables }, last: null, declared: 'today',
      scope: { include: d.kind === 'sqlite' ? d.tables : d.preset === 'Everything' ? '*' : d.preset === 'Documents' ? '*.md\n*.txt\n*.pdf\n*.docx' : '*.py\n*.ts\n*.rs\n*.go', exclude: d.exclude.trim(), branch: d.kind === 'git' ? d.branch : undefined, history: d.history === '50' ? 'The last 50 commits' : 'The latest commit only', revisions: 1, changed: 'today by brian' },
      tree: [], futureTree: p.tree, sweeps: [], withheld: ['.env', 'id_rsa'].slice(0, p.withheld), plan: { neu: p.n, changed: 0, gone: 0, bytes: p.bytes } }
    sources.unshift(s); st.draft = null
    startRun(s); show('source', s.id); paintRows()
    toast(`${s.name} was declared and is being taken.`)
  }

  /* ---- actions ------------------------------------------------------------------------------- */
  const cur = () => byId(st.source)
  const ACT = {
    theme() { theme = theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; paintTop() },
    cols() { st.cols = st.cols === 2 ? 1 : 2; if (st.cols === 1) st.beside = null; paintBeside(); paintTop(); if (st.view !== 'conv') paintSrc(); measure() },
    phone() { location.href = 'index.html?phone=1&theme=' + theme },
    reset() { location.href = 'index.html?theme=' + theme },
    brain() { toast('The Brain browser is already in Quiet Chat and is not part of this prototype.') },
    newconv() { toast('New conversation is already in Quiet Chat and is not part of this prototype.') },
    sources() { st.card.open = !st.card.open; paintCard(); paintRail(); if (st.card.open) $('cardq').focus() },
    closecard() { st.card.open = false; paintCard(); paintRail() },
    conv(id) { if (st.view === 'conv') keep(); st.conv = id; if (st.view === 'conv') { paintConv(); pane.scrollTop = st.scroll['conv:' + id] ?? pane.scrollHeight; paintTop(); paintRail(); measure() } else show('conv') },
    tab(id) { st.card.tab = id; st.card.scroll = 0; paintCard() },
    open(id) { st.card.open = false; paintCard(); show('source', id) },
    add() { st.card.open = false; paintCard(); st.draft = st.draft || blank(''); show('add') },
    backlist() { show('conv'); st.card.open = true; paintCard(); paintRail() },
    backconv() { show('conv') },
    fold(id) { st.open[id] = !st.open[id]; paintSrc() },
    menu() { st.menu = st.menu === 'source' ? null : 'source'; paintSrc() },
    copyref() { st.menu = null; paintSrc(); toast(`Copied: a reference to ${cur().name}. (Simulated: nothing was put on the clipboard.)`) },
    fluid() { st.menu = null; paintSrc(); toast('This would open the existing Sources page in Fluid. It is not part of this prototype.') },
    preview() { preview(cur()) },
    closepanel() { st.panel = null; paintSrc() },
    take() { const s = cur(); st.panel = null; startRun(s); repaint(s) },
    cancelrun() { const s = cur(); clearInterval(timers[s.id]); s.run = null; s.note = `A refresh was cancelled at ${now().split(', ')[1]}. Nothing was taken, and what Mentis held before is unchanged.`; repaint(s); toast('Refresh cancelled. Nothing was taken.') },
    scope() { st.panel = { id: st.source, type: 'scope' }; st.open.scope = true; paintSrc(); $('sc-ex')?.focus() },
    savescope() { const s = cur(), inc = $('sc-in').value.trim() || '*', ex = $('sc-ex').value.trim(), was = s.scope.exclude.split('\n').filter(Boolean).length, is = ex.split('\n').filter(Boolean).length
      if (inc === s.scope.include && ex === s.scope.exclude) { st.panel = null; paintSrc(); toast('Nothing was changed.'); return }
      s.scope.include = inc; s.scope.exclude = ex; s.scope.revisions += 1; s.scope.changed = 'today by brian'
      preview(s, { dropped: Math.max(0, is - was) * 14 }) },
    stop() { st.panel = { id: st.source, type: 'stop' }; paintSrc() },
    stopyes() { const s = cur(); s.bound = false; s.failure = null; st.panel = null; repaint(s); toast(`${s.name} is no longer refreshed from this machine. What Mentis holds is unchanged.`) },
    locate() { st.panel = { id: st.source, type: 'locate' }; st.open.where = true; paintSrc() },
    locatepick() { const s = cur(); s.bound = true; s.since = 'today'; st.panel = null; repaint(s); toast(`${s.name} is connected on this machine. Preview a refresh to see what has changed.`) },
    locateaddr() { const s = cur(), a = $('loc-addr').value.trim(); if (/^https?:\/\/[^/]*@/i.test(a)) { toast('That address carries sign-in details. Mentis refuses it.'); return } s.remote = a || s.remote; s.bound = true; st.panel = null; repaint(s); toast('Address saved. Try again to see whether Git can reach it.') },
    folder(id) { const k = st.source + ':' + id; st.tree[k] = !st.tree[k]; paintSrc() },
    file(id) { openFile(cur(), id) },
    morefiles() { toast('The rest of the folder would be listed here, a page at a time.') },
    closefile() { st.beside = null; paintBeside(); if (st.view === 'source') paintSrc() },
    addkind(id) { const d = st.draft; st.draft = { ...blank(id), name: d.name }; paintSrc() },
    addchoose() { st.draft.picking = !st.draft.picking; paintSrc() },
    addpick(id) { const d = st.draft; d.where = id; d.picking = false; if (!d.name) d.name = id.split('\\').pop().replace(/\.\w+$/, ''); d.stale = !!d.preview; d.error = ''; paintSrc() },
    addpreset(id) { st.draft.preset = id; st.draft.stale = !!st.draft.preview; paintSrc() },
    addpreview() { addPreview() },
    addtake() { addTake() },
    addcancel() { st.draft = null; ACT.backlist() },
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]')
    if (st.menu && !e.target.closest('.pt-menuwrap')) { st.menu = null; if (st.view === 'source') paintSrc() }
    if (!b) {
      if (st.card.open && !e.target.closest('#card') && !e.target.closest('#rail') && !e.target.closest('#tools')) ACT.closecard()
      return
    }
    e.preventDefault()
    ACT[b.dataset.act]?.(b.dataset.id)
  })
  document.addEventListener('input', (e) => {
    const t = e.target
    if (t.id === 'cardq') { st.card.q = t.value; st.card.scroll = 0; paintRows() }
    else if (t.id === 'find') { st.find = t.value; const s = cur(); const tmp = document.createElement('div'); tmp.innerHTML = contentsHtml(s); $('tree').replaceWith(tmp.querySelector('#tree')) }
    else if (t.dataset.f && st.draft) { const d = st.draft; d[t.dataset.f] = t.value; d.error = ''; if (d.preview && d.preview !== 'asking' && !d.stale) { d.stale = true; $('addpreview').innerHTML = addPreviewHtml() } }
  })
  document.addEventListener('change', (e) => {
    const t = e.target
    if (t.id === 'cardkind') { st.card.kind = t.value; paintRows() }
    else if (t.id === 'cardorder') { st.card.order = t.value; paintRows() }
    else if (t.dataset.change === 'signedin') { cur().signedIn = t.checked }
    else if (t.dataset.change === 'mode') { st.draft.mode = t.value; st.draft.error = ''; st.draft.stale = !!st.draft.preview; paintSrc() }
    else if (t.dataset.change === 'history') { st.draft.history = t.value; st.draft.stale = !!st.draft.preview; paintSrc() }
  })
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.id === 'composer' && e.target.value.trim()) {
      const c = convs.find((x) => x.id === st.conv); c.posts.push(['b', e.target.value.trim()]); paintConv(); pane.scrollTop = pane.scrollHeight; $('composer').focus()
    } else if (e.key === 'Escape') {
      if (st.menu) { st.menu = null; paintSrc() } else if (st.panel) ACT.closepanel(); else if (st.card.open) { if (st.card.q) { st.card.q = ''; paintCard() } else ACT.closecard() }
    } else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && e.target.id === 'divider') {
      e.preventDefault(); st.split = Math.min(0.85, Math.max(0.18, st.split + (e.key === 'ArrowLeft' ? -0.02 : 0.02))); paintBeside()
    }
  })

  /* the divider drags: the centre column takes what it is given */
  $('divider').addEventListener('pointerdown', (e) => {
    const d = e.currentTarget, box = $('panes').getBoundingClientRect()
    d.setPointerCapture(e.pointerId); document.body.classList.add('q2-resizing')
    const move = (ev) => { st.split = Math.min(0.85, Math.max(0.18, (ev.clientX - box.left) / box.width)); pane.style.flex = `${st.split} 1 0`; $('beside').style.flex = `${1 - st.split} 1 0` }
    const up = () => { d.removeEventListener('pointermove', move); d.removeEventListener('pointerup', up); d.removeEventListener('pointercancel', up); document.body.classList.remove('q2-resizing') }
    d.addEventListener('pointermove', move); d.addEventListener('pointerup', up); d.addEventListener('pointercancel', up)
  })

  /* ---- begin: one source is already refreshing, as it might be found ------------------------------ */
  paintTop(); paintRail(); paintConv(); paintBeside(); paintCard()
  pane.scrollTop = pane.scrollHeight
  startRun(byId("agent"), 312, 3500)
  window.__proto = { st, sources }
})()
