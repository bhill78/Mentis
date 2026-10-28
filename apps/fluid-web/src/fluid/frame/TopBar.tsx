/* THE TOP BAR (spec section 3; #190's header): one bar, 48px, never grows.
 *
 *   Mentis:brain ◎ +  ← Back to #216   Local LLM Prelim ▾ 2 elsewhere
 *   This post · #222   +                  Latest  Arrange ▾   ⌕  🔔  ◐
 *
 * The mark is production's Brain menu, on hover. ◎ is Home and + a new
 * conversation, both always here (#190); the name's ▾ opens the switcher,
 * and "2 elsewhere" counts the other conversations working or waiting on
 * you. The post read is named once, by the This post tab (barWords.ts); who
 * is in the conversation and who is working are the column's, not the bar's.
 * Back names where it goes. Page tabs are the pages Open as page made.
 * Search, Activity and Look are quiet marks at the right end
 * (BarControls.tsx), after a slot kept for the conversation's chat mark (A7).
 * Arrange opens Track B's sheet, mounted here. What gives way as the window
 * narrows, and in what order, is bar.css ("THE LADDER").
 *
 * LATEST (conversation/latest.ts) sits before Arrange: the newest posts
 * across every conversation, replies included, each opened exactly -- its
 * thread, with it the post read. `L` opens it, never while typing. */

import { useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import * as nav from '../nav'
import { useList, useNav, usePost } from '../conversation/hooks'
import type { Id } from '../store'
import { ArrangeMark, BarEnd, Brand, HomeAndNew } from './BarControls'
import { elsewhereWords, thisPostTitle } from './barWords'
import { closeMedia, useMediaOpen } from '../present'
import { Who } from '../identity/Who'
import { SectionSpin } from '../../loading'
import { SWITCHER } from '../conversation/Switcher'
import ArrangeSlot from './ArrangeSlot'
import { openSuggested, useSuggested } from '../workspace/suggested'
import { closeSheet, openSheet, Sheet, sheetOpen, useOpenSheet } from './Sheet'
import { useChanged } from '../workspace/place'
import { carries, dropOnTab } from '../workspace/keep'
import { showWorkspace } from './narrow'
import { showWorkspaceContent } from '../conversation/threads'
import { isGovObject } from '../governance/model'
import { GovContext } from '../governance/context'
import { ago } from '../../api'
import { isNew, keyIsNotOurs, LATEST, latestAnchor, markSeen, openLatest, setOpener, setShowsLatestWork, useLatest, useLatestWork, useSeenAt, type LatestItem, type LatestPage } from '../conversation/latest'

export const ARRANGE = 'arrange'

/* THE POST READ IS NAMED ONCE (barWords.ts): by the This post tab, its
   number in a slot of its own so nothing moves when another post is read
   (D3), its author on hover. */
function Tabs({ shown }: { shown: boolean }) {
  const s = useNav()
  const post = usePost(s.reading ?? '')
  const suggested = useSuggested()
  const gov = useContext(GovContext)
  const seen = useRef(new Set<string>(s.pages.map((p) => p.id)))
  const [born, setBorn] = useState<string | null>(null)
  const hoverTimer = useRef<{ id: string; timer: ReturnType<typeof setTimeout> } | null>(null)
  const clearHover = () => {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current.timer)
      hoverTimer.current = null
    }
  }
  useEffect(() => {
    const onEnd = () => clearHover()
    window.addEventListener('dragend', onEnd)
    return () => {
      clearHover()
      window.removeEventListener('dragend', onEnd)
    }
  }, [])

  const onTabDragOver = (e: React.DragEvent, id: string) => {
    if (!carries(e)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = e.ctrlKey ? 'copy' : 'move'
    if (id !== nav.snapshot().page) {
      if (!hoverTimer.current || hoverTimer.current.id !== id) {
        clearHover()
        hoverTimer.current = {
          id,
          timer: setTimeout(() => {
            if (id !== nav.snapshot().page) {
              nav.showPage(id)
              showWorkspaceContent()
              showWorkspace()
            }
            hoverTimer.current = null
          }, 600),
        }
      }
    } else {
      clearHover()
    }
  }

  const onTabDragLeave = (e: React.DragEvent, id: string) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      if (hoverTimer.current?.id === id) clearHover()
    }
  }

  const onTabDrop = (e: React.DragEvent, id: string) => {
    clearHover()
    if (!carries(e)) return
    e.preventDefault()
    dropOnTab(e, id)
  }

  useEffect(() => {
    for (const p of s.pages) {
      if (!seen.current.has(p.id)) {
        seen.current.add(p.id)
        setBorn(p.id)
        const t = setTimeout(() => setBorn(null), 650)
        return () => clearTimeout(t)
      }
    }
  }, [s.pages])
  /* THE TABS SCROLL, "+" STAYS (opr-9b739de2f062): with more pages than the
     bar has room for, the tabs scroll sideways inside their own strip and the
     page shown is kept in view; "+" and the suggested pages sit after the
     strip, so they are never clipped off the bar. */
  const strip = useRef<HTMLSpanElement>(null)
  /* The page shown, brought into the strip's view. Measured against the
     strip itself (opr-d4e9c42677b1): a tab's offsetLeft is from the bar, not
     the strip, which scrolled "This post" behind the title at 900 px. Done
     again whenever the strip's width changes, so the width it settles at
     after loading is the one that counts. */
  const reveal = () => {
    const box = strip.current
    const el = box?.querySelector<HTMLElement>('.fx-tab.on')
    if (!el || !box) return
    const left = el.getBoundingClientRect().left - box.getBoundingClientRect().left + box.scrollLeft
    if (left < box.scrollLeft) box.scrollLeft = left
    else if (left + el.offsetWidth > box.scrollLeft + box.clientWidth) box.scrollLeft = left + el.offsetWidth - box.clientWidth
  }
  useEffect(reveal, [s.page, s.pages])
  /* Which ends of the strip have tabs scrolled out of view: those ends fade. */
  useEffect(() => {
    const box = strip.current
    if (!box) return
    const mark = () => {
      box.toggleAttribute('data-before', box.scrollLeft > 1)
      box.toggleAttribute('data-after', box.scrollLeft + box.clientWidth < box.scrollWidth - 1)
    }
    mark()
    const ro = new ResizeObserver(() => { reveal(); mark() })
    ro.observe(box)
    box.addEventListener('scroll', mark, { passive: true })
    return () => { ro.disconnect(); box.removeEventListener('scroll', mark) }
  }, [s.pages.length])
  return (
    <nav className="fx-pages" id="pages" aria-label="pages" style={{ visibility: shown ? undefined : 'hidden' }}>
      <span className="fx-pagetabs" ref={strip}
        onWheel={(e) => { if (e.deltaY && !e.deltaX) e.currentTarget.scrollLeft += e.deltaY }}>
        {/* A tab shows its page -- the one already selected too: in Focus it
            leaves Focus, so the page is seen (opr-386bc88f49c9). */}
        {s.pages.map((p) => {
          const tab = (
            <button key={p.id} className={'fx-tab' + (p.id === s.page ? ' on' : '') + (born === p.id ? ' born' : '')} data-tab={p.id}
              aria-current={p.id === s.page ? 'page' : undefined}
              onClick={() => { if (p.id !== nav.snapshot().page) nav.showPage(p.id); showWorkspaceContent(); showWorkspace() }}
              onDragOver={(e) => onTabDragOver(e, p.id)}
              onDragLeave={(e) => onTabDragLeave(e, p.id)}
              onDrop={(e) => onTabDrop(e, p.id)}
              title={'title' in p ? p.title : thisPostTitle(s.reading ? s.readingNumber : null, post?.author_name)}>
              {'title' in p ? p.title : <>This post{s.readingNumber != null && <> · <span className="fx-tabnum">#{s.readingNumber}</span></>}</>}
            </button>
          )
          /* A governed item's tab closes, as the mockup's does, and as the
             item's own Close does: back to where it was opened from. */
          return 'object' in p && !!p.object && isGovObject(p.object) ? (
            <span key={p.id} className={'fx-tab-gov' + (p.id === s.page ? ' on' : '')}>
              {tab}
              <button className="fx-tab-x" aria-label={`close ${p.title}`} title="Close" onClick={() => (gov ? gov.closeItem(p.id) : nav.closePage(p.id))}>×</button>
            </span>
          ) : tab
        })}
      </span>
      <button className="fx-tab" data-act="newpage" title="A new page of your own" aria-label="New page"
        onClick={() => { nav.newPage(); showWorkspace() }}>+</button>
      {suggested.filter((g) => !s.pages.some((p) => 'title' in p && p.title === g && !p.object)).map((g) => (
        <button key={g} className="fx-tab fx-ghost" data-ghost={g} title={`The post's "${g}" page: everything it marks for it`}
          onClick={() => { openSuggested(g); showWorkspace() }}>+ {g}</button>
      ))}
    </nav>
  )
}

/* -- Latest ------------------------------------------------------------------ */

/** "Latest": the newest posts everywhere; a dot while one is newer than what
 *  this browser was last shown. `L` opens it, as `/` opens search. */
function LatestControl({ here, onOpenPost }: { here: Id | null; onOpenPost: (c: Id, p: Id) => void }) {
  const open = useOpenSheet()
  const shown = open?.id === LATEST
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => setOpener(onOpenPost), [onOpenPost])
  /* Read at rest too, so the dot can say something is new; read again
     whenever the sheet opens. */
  const page = useLatest(true, null, shown)
  const items = page?.items ?? null
  /* the dot speaks of what Latest would show: agent work left out unless
     the reader shows it (the server's read already says which) */
  const seen = useSeenAt()
  const fresh = !!items?.[0] && isNew(items[0], seen)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'l' && e.key !== 'L') return
      if (keyIsNotOurs(e, sheetOpen())) return
      const at = latestAnchor()
      if (!at) return
      e.preventDefault()
      openSheet(LATEST, at, at === ref.current ? 'end' : 'start')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  return (
    <>
      <button ref={ref} className="fx-ctl fx-latest-ctl" id="latest" data-ctl="latest" aria-expanded={shown} aria-haspopup="dialog"
        aria-label={fresh ? 'Latest activity (new since you looked)' : 'Latest activity'}
        title="The newest posts in every conversation, replies included (L)"
        onClick={(e) => (shown ? closeSheet() : openSheet(LATEST, e.currentTarget, 'end'))}>
        {/* Wide, the word; narrower than 760 px, its mark alone (latest.css),
            named by its label and title. */}
        <svg className="fx-latest-mark" width="15" height="15" viewBox="0 0 16 16" aria-hidden="true" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 3.5h12M2 8h8M2 12.5h5" /><circle cx="13" cy="11" r="2" fill="currentColor" stroke="none" />
        </svg>
        <span className="fx-latest-word">Latest</span>{fresh && <span className="fx-latest-dot" aria-hidden="true" />}
      </button>
      <Sheet id={LATEST} label="latest" className="fb-sheet fx-latest-sheet">
        <LatestBody here={here} page={page} />
      </Sheet>
    </>
  )
}

function LatestBody({ here, page }: { here: Id | null; page: LatestPage | null }) {
  const items = page?.items ?? null
  /* AGENT WORK IS LEFT OUT BY DEFAULT (latest.ts), as the conversation folds
     it away, behind the same control: how many, and show them. */
  const showWork = useLatestWork()
  const n = page ? (page.showing ? page.agentWork : page.hidden) : 0
  /* What was new when the sheet opened stays marked while it is open; the
     reader has now been shown everything in it. */
  const now = useSeenAt()
  const [since] = useState(now)
  useEffect(() => { if (items?.[0]) markSeen(items[0].at) }, [items])
  const go = (it: LatestItem) => { closeSheet(); openLatest(it, here) }
  /* FOCUS GOES INTO THE SHEET (once its items are there): the first post,
     so Enter opens it, Tab and Up/Down move through them, Esc closes. */
  const list = useRef<HTMLUListElement>(null)
  const focused = useRef(false)
  useEffect(() => {
    if (focused.current || !items?.length) return
    const t = setTimeout(() => {
      const first = list.current?.querySelector<HTMLElement>('[data-latest-item]')
      if (first) { first.focus(); focused.current = true }
    }, 30)
    return () => clearTimeout(t)
  }, [items])
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const all = [...(list.current?.querySelectorAll<HTMLElement>('[data-latest-item]') ?? [])]
    const i = all.indexOf(document.activeElement as HTMLElement)
    const next = all[Math.max(0, Math.min(all.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]
    if (next) { e.preventDefault(); next.focus() }
  }
  return (
    <>
      <div className="fx-sec">Latest activity</div>
      {page && (showWork || n > 0) && (
        <div className="fx-latest-work">
          <button className="fx-agent-work-toggle fx-latest-work-toggle" aria-pressed={showWork}
            title={showWork ? 'Leave out the posts agents wrote to each other' : 'Show the briefs, findings, results and follow-ups agents wrote to each other'}
            onClick={() => setShowsLatestWork(!showWork)}>
            {showWork ? `Hide agent work (${n})` : `Show ${n} agent work ${n === 1 ? 'post' : 'posts'}`}
          </button>
        </div>
      )}
      {!items && <p className="fx-none fx-faint" aria-busy="true">Reading…</p>}
      {items && items.length === 0 && (
        <p className="fx-none fx-faint">{!showWork && n > 0
          ? `Only agent work among the newest posts (${n} left out).`
          : 'Nothing has been posted yet.'}</p>)}
      <ul className="fx-rows" ref={list} onKeyDown={onKey}>
        {(items ?? []).map((it) => {
          const fresh = isNew(it, since)
          const reply = it.reply_to ? (it.reply_to_number != null ? `reply to #${it.reply_to_number}` : 'a reply') : null
          return (
            <li key={it.id}>
              <button className={'fx-row fx-latest-row' + (fresh ? ' new' : '') + (it.agent_work ? ' fx-latest-agent' : '')} data-latest-item={it.id} data-root={it.root}
                data-agent-work={it.agent_work?.kind}
                title={`Open ${it.conversation_name}${it.number != null ? ` #${it.number}` : ''}${reply ? `, the ${reply}` : ''}, in its thread`}
                onClick={() => go(it)}>
                <span className="fx-latest-head">
                  {fresh && <span className="fx-latest-new" aria-label="new" />}
                  <Who id={it.author} name={it.author_alias} show="avatar" size={16} />
                  <span className="fx-latest-where"><b>{it.author_alias.replace(/^@/, '')}</b> in {it.conversation_name}{it.number != null ? ` · #${it.number}` : ''}</span>
                  {reply && <span className="fx-latest-reply">{reply}</span>}
                  <small>{ago(it.at)}</small>
                </span>
                {it.agent_work && <span className="fx-latest-why">Agent work · {it.agent_work.why}</span>}
                <span className="fx-latest-text">{it.deleted ? <i className="fx-faint">deleted</i> : it.excerpt || <i className="fx-faint">no words</i>}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </>
  )
}

/** Other conversations working or waiting on you (#190 decision 4: only
 *  those, not unread posts): the mark on the switcher's ▾. */
function Elsewhere({ here }: { here: Id | null }) {
  const list = useList()
  const n = (list ?? []).filter((c) => c.id !== here && c.id !== 'home' && (c.working > 0 || (c.needs_you ?? 0) > 0)).length
  if (!n) return null
  const w = elsewhereWords(n)
  return <span className="fb-elsewhere" title={w.title} aria-label={w.title}>{w.short}<span className="fb-elsewhere-word"> {w.word}</span></span>
}

export default function TopBar({ brain, brainInfo, view, title, first, back, extra, error, here, busy, onHome, onNew, onOpenPost, onPick, onManage, onSources, onSpace }: {
  brain: string
  /** the Brain's manifest, for the mark's menu */
  brainInfo?: { name: string | null; whyNot?: string | null; path?: string | null }
  view: 'conversation' | 'home' | 'stream' | 'gov' | 'sources' | 'space'
  title: string
  first: boolean
  /** Back as the view needs it: history in a conversation, return from Home */
  back: { label: string; disabled: boolean; run: () => void; returns: boolean }
  /** what sits beside the title: Save... for a conversation not yet named */
  extra?: ReactNode
  error?: ReactNode
  /** the conversation shown, if one is */
  here: Id | null
  busy: boolean
  onHome: () => void
  onNew: () => void
  onOpenPost: (conversation: Id, post: Id) => void
  onPick: (conversation: Id) => void
  /** the Brain menu's Manage Brain: Fluid's own Governance */
  onManage?: () => void
  /** the Brain menu's Manage Sources: Fluid's own Sources surface */
  onSources?: () => void
  /** the Brain menu's 3D Brain (`#/brain/space`) */
  onSpace?: () => void
}) {
  const open = useOpenSheet()
  const viewing = useMediaOpen()
  const titleRef = useRef<HTMLButtonElement>(null)
  /* Manage Sources and the 3D Brain are places of the whole Brain, as Home is. */
  const brainWide = view === 'sources' || view === 'space'
  const reading = view !== 'home' && view !== 'gov' && !brainWide && !first
  const pages = useNav().pages.length
  const changed = useChanged()
  return (
    <header className={'fx-bar fw-bar' + (view === 'home' ? ' fw-bar-home' : view === 'stream' ? ' fw-bar-stream' : view === 'gov' ? ' fw-bar-gov' : '')
      + (view !== 'home' && view !== 'gov' && !brainWide && pages > 1 ? ' fx-has-pages' : '')}>
      <Brand brain={brainInfo ?? { name: brain }} atHome={view === 'home' || brainWide} atSources={view === 'sources'} atSpace={view === 'space'} onHome={onHome} onManage={onManage} onSources={onSources} onSpace={onSpace} conversation={view === 'conversation' ? here : null} />
      <HomeAndNew atHome={view === 'home'} onHome={onHome} onNew={onNew} busy={busy} />
      <button id="back" className={'fx-ctl fx-back fw-back' + (back.returns ? ' fw-return-link' : '')} disabled={back.disabled && !viewing}
        title={back.label && back.label !== 'Back' ? `${back.label} (Alt+Left)` : 'Back (Alt+Left)'} aria-label={back.returns ? 'return to conversation' : undefined} onClick={() => { if (!closeMedia()) back.run() }}>
        ← <span id="backLabel">{back.label}</span>
      </button>
      <button ref={titleRef} id="title"
        className={'fx-title fw-title' + (view === 'home' ? ' fw-home-title' : view === 'stream' ? ' fw-stream-title' : '')}
        aria-expanded={open?.id === SWITCHER} aria-haspopup="dialog" title={title}
        style={{ ['--tlen' as string]: title.length }}
        onClick={(e) => openSheet(SWITCHER, e.currentTarget)}>
        {/* The name gives way (ellipsis) before anything else on the bar; its ▾ and mark stay. */}
        <span className="fx-tname">{title}</span> <SectionSpin id={here ? 'fluid:conversation:' + here : null} label={title} /> <span className="fx-caret" aria-hidden="true">▾</span><Elsewhere here={here} />
      </button>
      {extra}
      {view !== 'home' && view !== 'gov' && !brainWide && <Tabs shown={reading} />}
      <span className="fx-grow" />
      {error}
      <LatestControl here={view === 'conversation' ? here : null} onOpenPost={onOpenPost} />
      {view !== 'home' && view !== 'gov' && !brainWide && (
        <button className="fx-ctl" id="arrange" aria-expanded={open?.id === ARRANGE} data-changed={changed ? '' : undefined}
          title={changed ? 'This arrangement is changed in this tab: Save keeps it in the Brain' : undefined}
          aria-label={changed ? 'Arrange (changed, not saved)' : 'Arrange'}
          onClick={(e) => openSheet(ARRANGE, e.currentTarget)}>
          <span className="fx-arrange-mark" aria-hidden="true"><ArrangeMark /></span>
          <span className="fx-arrange-word">Arrange</span>{changed && <span className="fw-changed" aria-hidden="true"> ●</span>}<span className="fx-arrange-word"> ▾</span>
        </button>
      )}
      <BarEnd conversation={view === 'conversation' ? here : null} onOpenPost={onOpenPost} onPick={onPick} />
      <Sheet id={ARRANGE} label="arrange" className="fx-arrange"><ArrangeSlot onClose={closeSheet} /></Sheet>
    </header>
  )
}

/** The title button, for the first visit's picker to open under. */
export const titleButton = () => document.getElementById('title')
