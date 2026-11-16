/* MANAGE SOURCES, DESIGN ROUND 1 -- the mockup's frame. Builds Quiet Chat's
 * own layout (top line, left rail with the Brain icon and the NEW data-store
 * icon, the conversation's pane, an optional working column beside it and an
 * optional floating browser card) around what a page supplies in <template>
 * elements, so each page holds only what is specific to it:
 *
 *   <template id="center">  the centre column's content (a source, the Add
 *                           flow). Without it, the conversation is shown.
 *   <template id="card">    the floating Sources browser's inner content.
 *   <template id="beside">  a working column to the right of the centre pane.
 *
 * <body data-rail="sources|brain|none" data-beside-width="560"
 *       data-pane-width="..."> tune it. ?theme=light|dark picks the theme.
 * Nothing here talks to a server. */
(function () {
  const q = new URLSearchParams(location.search)
  const theme = q.get('theme') || 'dark'
  document.documentElement.dataset.theme = theme
  const body = document.body
  const tpl = (id) => { const t = document.getElementById(id); return t ? t.innerHTML : null }
  const center = tpl('center'), card = tpl('card'), beside = tpl('beside')
  const rail = body.dataset.rail || 'sources'
  const other = theme === 'dark' ? 'light' : 'dark'
  const here = location.pathname.split('/').pop()
  const embedded = q.get('frame') === '1'

  const brain = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M6 2.5a2 2 0 0 0-2 2v.3A2.2 2.2 0 0 0 2.5 7a2.2 2.2 0 0 0 .7 1.6A2.3 2.3 0 0 0 5 12.4 1.8 1.8 0 0 0 8 13V3.6A1.9 1.9 0 0 0 6 2.5Z"/><path d="M10 2.5a2 2 0 0 1 2 2v.3A2.2 2.2 0 0 1 13.5 7a2.2 2.2 0 0 1-.7 1.6 2.3 2.3 0 0 1-1.8 3.8A1.8 1.8 0 0 1 8 13"/></svg>'
  const store = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/><path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/></svg>'

  const conversation = `
    <div class="q2-col">
      <header class="q2-conv-head"><h1>Colony Island Three</h1><p class="q2-conv-meta">256 posts · brian, Caretaker, Builder</p></header>
      <article class="q2-post"><div class="q2-article">
        <div class="q2-byline"><span class="mk-avatar">b</span><span class="q2-byline-words"><span class="q2-name">brian</span><span class="q2-byline-meta">2:41 PM · #254</span></span></div>
        <div class="q2-prose">Before the next session, check the campaign notes for what the party agreed with the harbour master. I think it was in the session nine write-up.</div>
      </div></article>
      <article class="q2-post"><div class="q2-article">
        <div class="q2-byline"><span class="mk-avatar agent">C</span><span class="q2-byline-words"><span class="q2-name">Caretaker</span><span class="q2-byline-meta">2:43 PM · #255</span></span></div>
        <div class="q2-prose">Found it in the D&amp;D Knowledge source, <i>Sessions/Session 09.md</i>: safe berth for one season, in exchange for charting the eastern reef. The copy Mentis holds was taken on October 2, so anything written since is not in it.</div>
      </div></article>
      <article class="q2-post"><div class="q2-article">
        <div class="q2-byline"><span class="mk-avatar">b</span><span class="q2-byline-words"><span class="q2-name">brian</span><span class="q2-byline-meta">2:44 PM · #256</span></span></div>
        <div class="q2-prose">Good. I have added two sessions since then, so that copy is stale.</div>
      </div></article>
      <div class="mk-dock"><div>Message Colony Island Three…</div></div>
    </div>`

  const paneStyle = body.dataset.paneWidth ? `flex:none;width:${body.dataset.paneWidth}px` : 'flex:1;min-width:0'
  const bars = [22, 30, 14, 22, 8, 14, 22].map((w, i) => `<li${i === 2 ? ' class="current"' : ''}><span class="q2-bar" style="width:${w}px;height:${i < 3 ? 2 : 1}px"></span></li>`).join('')
  body.innerHTML = `
  <div class="q2 fx q2-arr-one q2-side-left mk">
    <header class="q2-top">
      <span class="mk-brand"><svg viewBox="0 0 14 14" fill="none" stroke="currentColor"><circle cx="7" cy="7" r="5.5"/><circle cx="7" cy="7" r="1.6"/></svg>Mentis : <b>Day-to-day</b></span>
      <span class="q2-top-conv">Colony Island Three</span>
      <span class="q2-top-gap"></span>
      ${embedded ? '' : `<span class="mk-tools"><a href="index.html?theme=${theme}">all mockups</a><a href="${here}?theme=${other}">${other} theme</a></span>`}
      <span class="mk-tag">mockup · sample data</span>
    </header>
    <nav class="mk-rail" aria-label="Rail">
      <button class="mk-icon${rail === 'brain' ? ' on' : ''}" title="Brain" aria-label="Brain">${brain}</button>
      <button class="mk-icon mk-new${rail === 'sources' ? ' on' : ''}" title="Sources" aria-label="Sources">${store}</button>
      <button class="mk-plus" aria-label="New conversation">+</button>
      <ul>${bars}</ul>
    </nav>
    <div class="q2-work"><div class="q2-panes">
      <section class="q2-pane q2-conv" style="${paneStyle}">${center
        ? `<div class="q2-col q2-col-brain"><div class="q2-stream q2-brain-main">${center}</div></div>` : conversation}</section>
      ${beside ? `<div class="q2-divider" role="separator" aria-orientation="vertical" title="Drag to resize"></div><section class="q2-pane mk-beside" style="flex:1;min-width:0">${beside}</section>` : ''}
    </div></div>
    ${card ? `<div class="q2-brain-veil" style="pointer-events:none"><div class="q2-brain-card" role="dialog" aria-label="Sources" style="pointer-events:auto"><div class="q2-cl">${card}</div></div></div>` : ''}
  </div>`

  /* the card takes the room beside the reading column, as BrainBrowser.tsx
     measures it in the app (the same sum) */
  const cardEl = document.querySelector('.q2-brain-card')
  const measure = () => {
    if (!cardEl) return
    const column = document.querySelector('.q2-pane.q2-conv > .q2-col:not(.q2-col-brain)')
    const left = cardEl.getBoundingClientRect().left
    const edge = column ? column.getBoundingClientRect().left - 24 : left
    cardEl.style.setProperty('--q2-brain-room', Math.max(0, Math.floor(edge - left - 12)) + 'px')
  }
  measure()
  new ResizeObserver(measure).observe(document.documentElement)

  /* folds open and close, so the detail pages can be tried */
  document.querySelectorAll('.rv-d > button').forEach((b) => b.addEventListener('click', () => {
    const d = b.parentElement, open = d.classList.toggle('open')
    b.setAttribute('aria-expanded', String(open))
    b.querySelector('.c').textContent = open ? '▾' : '▸'
    const bodyEl = d.querySelector('.rv-body'); if (bodyEl) bodyEl.hidden = !open
  }))
  document.querySelectorAll('.rv-d:not(.open) .rv-body').forEach((el) => { el.hidden = true })

  /* the divider drags, so the centre column can be resized by hand */
  const divider = document.querySelector('.q2-divider'), pane = document.querySelector('.q2-pane.q2-conv')
  if (divider && pane) {
    divider.addEventListener('pointerdown', (e) => {
      divider.setPointerCapture(e.pointerId); document.body.classList.add('q2-resizing')
      const move = (ev) => { pane.style.flex = 'none'; pane.style.width = Math.max(320, ev.clientX) + 'px' }
      const up = () => { divider.removeEventListener('pointermove', move); divider.removeEventListener('pointerup', up); document.body.classList.remove('q2-resizing') }
      divider.addEventListener('pointermove', move); divider.addEventListener('pointerup', up)
    })
  }
})()
