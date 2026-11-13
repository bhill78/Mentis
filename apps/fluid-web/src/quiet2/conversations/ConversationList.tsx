/* THE CONVERSATION LIST (owner-approved design, 2026-11-12): what the left
 * rail's card shows. Opened by hovering the rail, focusing a bar (Enter goes
 * into it), the chevron, or a tap on touch; it is placed where the rail's
 * card always was (Markers `placeCard`).
 *
 *   Conversations                         ×
 *   [ Filter                             ]   titles only, this tab only
 *   Active  Archived  Trash                  text tabs; the chosen one by
 *                                            weight and a thin underline
 *   Title ······························ 2 h   one line, a faint time
 *
 * Each row's go-to-latest arrow and ⋯ show on hover, keyboard focus or while
 * its menu is open (the current row keeps ⋯ on touch and narrow screens).
 * The menu opens from ⋯, right-click, Shift+F10, the menu key, or a
 * touch-and-hold of about 0.45 s; Esc closes it and returns to the row.
 *
 * Every change is the server's (`store.changeConversationState`, the rename
 * route) and shows at once: the tab is read again, and the rail with it.
 * The filter never searches posts and never opens the global Search. */
import './conversations.css'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { newOp, store, type Conversation, type ConversationChange, type ConversationState, type DeletionCapability, type Id } from '../../fluid/store'
import { repairText } from '../text'
import { TABS, changedWords, emptyLine, inFlight, menuFor, rowLabel, rowTime, stateOf, titleMatches, type MenuAct, type MenuEntry } from './manage'

/** the tab the list last showed, for the next time it opens */
let lastTab: ConversationState = 'active'
/** the server's answer about permanent deletion, read once per page */
let deletion: Promise<DeletionCapability> | null = null
const readDeletion = () => (deletion ??= store.conversationDeletion())

const HOLD_MS = 450

const ICON: Record<string, React.ReactNode> = {
  rename: <path d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4" />,
  archive: <><rect x="3" y="4.5" width="18" height="4.5" rx=".9" /><path d="M4.5 9v10.5h15V9M9.75 12.75h4.5" /></>,
  unarchive: <path d="M3.75 5.25h16.5v10.5h-9l-4.5 3.75v-3.75h-3z" />,
  trash: <path d="M3.75 6.75h16.5M9 6.75V4.5h6v2.25M6 6.75l1.05 13.5h9.9L18 6.75M10.2 10.5v6.75M13.8 10.5v6.75" />,
  restore: <path d="M4.5 12a7.5 7.5 0 1 0 2.25-5.4M4.5 3.75v3.75h3.75" />,
  delete: <path d="M3.75 6.75h16.5M9 6.75V4.5h6v2.25M6 6.75l1.05 13.5h9.9L18 6.75M9 10.5l6 6M15 10.5l-6 6" />,
}
const Icon = ({ name }: { name: string }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON[name]}</svg>
)
const More = () => <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><circle cx="3.5" cy="8" r="1.3" /><circle cx="8" cy="8" r="1.3" /><circle cx="12.5" cy="8" r="1.3" /></svg>
const Latest = () => <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
const Warn = () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 2 15 14H1z" /><path d="M8 6.5v3.5M8 12v.1" /></svg>

export default function ConversationList({ current, onPick, onLatest, onClose, onHold, onSay, onDanger, focusTab }: {
  current: Id | null
  onPick: (id: Id) => void
  onLatest?: (id: Id) => void
  /** close the card (Esc, ×, a pick) */
  onClose: (refocus: boolean) => void
  /** a menu or a rename is open: the card stays while it is */
  onHold: (held: boolean) => void
  /** what the page says (the notice) */
  onSay: (words: string) => void
  /** permanent deletion asked for: the page draws the Danger Zone */
  onDanger?: (c: Conversation) => void
  /** bumped to move focus to the chosen tab (Enter on a bar, the chevron) */
  focusTab: number
}) {
  const [tab, setTabState] = useState<ConversationState>(lastTab)
  /* a tab shows at once what the rail already holds of it; its own read follows */
  const setTab = (t: ConversationState) => {
    if (t === tab) return
    lastTab = t; setTabState(t)
    setRows(store.list ? store.list.filter((c) => stateOf(c) === t) : null); setNext(null)
  }
  const [filter, setFilter] = useState('')
  /* what the rail already holds shows at once; the tab's own read replaces it */
  const [rows, setRows] = useState<Conversation[] | null>(() => store.list ? store.list.filter((c) => stateOf(c) === lastTab) : null)
  const [next, setNext] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [menu, setMenu] = useState<{ id: Id; at: { left: number; top: number } | null; keyboard: boolean } | null>(null)
  const [renaming, setRenaming] = useState<Id | null>(null)
  const [cap, setCap] = useState<DeletionCapability | null>(null)
  const [reread, setReread] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const end = useRef<HTMLLIElement>(null)
  const menuBox = useRef<HTMLDivElement>(null)
  /* which question the rows answer: a late page of an older one is dropped */
  const asked = useRef('')
  const sent = useRef(0)
  const applied = useRef(0)

  useEffect(() => { void readDeletion().then(setCap) }, [])
  useEffect(() => { onHold(!!menu || !!renaming) }, [menu, renaming, onHold])
  useEffect(() => () => onHold(false), [onHold])

  /* THE TAB'S FIRST PAGE: at once for a tab, a moment after typing stops */
  useEffect(() => {
    const words = filter.trim()
    /* THE QUESTION is the tab and the words; a reread of the same question
       does not drop an answer already on its way -- the newest answered wins */
    const key = `${tab}\u0000${words}`
    const t = window.setTimeout(() => {
      if (asked.current !== key) setNext(null)
      asked.current = key
      const n = ++sent.current
      setBusy(true); setError(null)
      store.conversationPage(null, words, tab).then((got) => {
        if (asked.current !== key || n < applied.current) return
        applied.current = n
        setRows(got.conversations); setNext(got.next)
      }, (e: unknown) => { if (asked.current === key && n === sent.current) setError(`Could not read the conversations: ${e instanceof Error ? e.message : String(e)}`) })
        .finally(() => { if (n === sent.current) setBusy(false) })
    }, words ? 180 : 0)
    return () => clearTimeout(t)
  }, [tab, filter, reread])

  /* the record moved (the change feed rereads the rail's list): read again */
  useEffect(() => store.subscribe('coll:conversations', () => setReread((n) => n + 1)), [])

  /* the next page, once the end of the list comes into view */
  useEffect(() => {
    const el = end.current
    if (!el || !next || busy) return
    const io = new IntersectionObserver((seen) => {
      if (!seen.some((s) => s.isIntersecting)) return
      io.disconnect()
      const key = asked.current
      setBusy(true)
      store.conversationPage(next, filter.trim(), tab).then((got) => {
        if (asked.current !== key) return
        setRows((had) => {
          const known = new Set((had ?? []).map((c) => c.id))
          return [...(had ?? []), ...got.conversations.filter((c) => !known.has(c.id))]
        })
        setNext(got.next)
      }, (e: unknown) => { if (asked.current === key) { setError(`Could not read more: ${String(e)}`); setNext(null) } })
        .finally(() => { if (asked.current === key) setBusy(false) })
    }, { root: list.current, rootMargin: '120px' })
    io.observe(el)
    return () => io.disconnect()
  }, [next, busy, rows, tab, filter])

  /* Enter on a bar, or the chevron: into the list, at the chosen tab */
  useEffect(() => {
    if (!focusTab) return
    requestAnimationFrame(() => box.current?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus())
  }, [focusTab])

  /* the menu takes focus at its first item it can do, when opened by key or hold */
  useLayoutEffect(() => {
    if (!menu || !menuBox.current) return
    const m = menuBox.current
    const row = box.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(menu.id)}"]`)
    if (row && !menu.at) {
      const r = row.getBoundingClientRect(), w = m.offsetWidth, h = m.offsetHeight
      const left = Math.min(Math.max(8, r.right - w), window.innerWidth - w - 8)
      let top = r.bottom + 2
      if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 2)
      setMenu({ ...menu, at: { left, top } })
      return
    }
    if (menu.at && menu.keyboard) m.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])')?.focus()
  }, [menu])

  /* an open menu follows its row: a change of it on its way, or arriving */
  const [, setTick] = useState(0)
  useEffect(() => (menu ? store.subscribe('conv:' + menu.id, () => setTick((n) => n + 1)) : undefined), [menu?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  /* a press outside the menu closes it */
  useEffect(() => {
    if (!menu) return
    const away = (e: PointerEvent) => {
      const t = e.target as Node
      if (menuBox.current?.contains(t)) return
      if ((t as Element).closest?.(`[data-id="${CSS.escape(menu.id)}"] .q2-cl-more`)) return
      setMenu(null)
    }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [menu])

  const rowButton = (id: Id) => box.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"] .q2-cl-open`)
  const closeMenu = (refocus: boolean) => {
    const id = menu?.id
    setMenu(null)
    if (refocus && id) requestAnimationFrame(() => rowButton(id)?.focus())
  }
  const openMenu = (id: Id, keyboard: boolean) => setMenu({ id, at: null, keyboard })

  const act = async (c: Conversation, what: MenuAct) => {
    setMenu(null)
    if (what === 'rename') { setRenaming(c.id); return }
    if (what === 'delete') { onDanger?.(c); return }
    const change = what as ConversationChange
    try {
      const author = store.me ?? await store.loadMe()
      await store.changeConversationState(c.id, author, change, newOp())
      /* it leaves this tab at once; the tab's own read follows */
      setRows((had) => had && had.filter((r) => r.id !== c.id))
      onSay(changedWords(change, repairText(c.name) || 'Unnamed conversation', inFlight(c).running))
    } catch (e: unknown) {
      onSay(e instanceof Error ? e.message : String(e))
    }
    setReread((n) => n + 1)
  }

  const shown = (rows ?? []).filter((c) => stateOf(c) === tab && titleMatches(repairText(c.name), filter))
  const menuRow = menu ? shown.find((c) => c.id === menu.id) ?? null : null
  const entries: MenuEntry[] = menuRow ? menuFor(menuRow, cap, store.changingState(menuRow.id)) : []

  const onKeys = (e: React.KeyboardEvent) => {
    if (e.key !== 'Escape') return
    /* Esc closes an open menu first, focus back on its row; then the card */
    e.preventDefault(); e.stopPropagation()
    if (menu) { closeMenu(true); return }
    onClose(true)
  }

  return (
    <div className="q2-cl" ref={box} onKeyDown={onKeys}>
      <header className="q2-cl-head">
        <h2>Conversations</h2>
        <button type="button" className="q2-cl-close" aria-label="Close" title="Close" onClick={() => onClose(true)}>×</button>
      </header>
      <input type="search" className="q2-cl-filter" value={filter} placeholder="Filter" autoComplete="off" spellCheck={false}
        aria-label="Filter these conversations by title"
        onChange={(e) => setFilter(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Escape' && filter) { e.preventDefault(); e.stopPropagation(); setFilter('') } }} />
      <div className="q2-cl-tabs" role="tablist" aria-label="Which conversations"
        onKeyDown={(e) => {
          if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
          e.preventDefault()
          const i = TABS.findIndex((x) => x.id === tab)
          const n = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length].id
          setTab(n); setMenu(null)
          const el = e.currentTarget
          requestAnimationFrame(() => el.querySelector<HTMLElement>(`[data-tab="${n}"]`)?.focus())
        }}>
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" data-tab={t.id} aria-selected={tab === t.id} tabIndex={tab === t.id ? 0 : -1}
            onClick={() => { setTab(t.id); setMenu(null) }}>{t.label}</button>
        ))}
      </div>
      <ul className="q2-cl-list" ref={list} role="list" aria-busy={busy || undefined}>
        {shown.map((c) => (
          <Row key={c.id} c={c} current={c.id === current} open={menu?.id === c.id} renaming={renaming === c.id}
            onPick={() => { onPick(c.id); onClose(false) }}
            onLatest={onLatest && stateOf(c) !== 'trashed' ? () => { onLatest(c.id); onClose(false) } : undefined}
            onMenu={(keyboard) => (menu?.id === c.id ? closeMenu(false) : openMenu(c.id, keyboard))}
            onRenamed={(name) => { setRenaming(null); if (name) { setRows((had) => had && had.map((r) => (r.id === c.id ? { ...r, name, provisional: false } : r))); onSay(`Renamed “${name}”.`); setReread((n) => n + 1) } requestAnimationFrame(() => rowButton(c.id)?.focus()) }}
            onSay={onSay} />
        ))}
        {next && <li ref={end} className="q2-cl-note" aria-hidden="true">{busy ? 'Reading more…' : ''}</li>}
        {rows && !shown.length && !busy && !error && <li className="q2-cl-note">{emptyLine(tab, filter)}</li>}
        {rows && !shown.length && busy && !error && <li className="q2-cl-note">Reading…</li>}
        {!rows && !error && <li className="q2-cl-note">Reading the conversations…</li>}
        {error && <li className="q2-cl-note" role="alert">{error}</li>}
      </ul>
      {menu && menuRow && (
        <div ref={menuBox} className="q2-menu q2-cl-menu" role="menu" aria-label={repairText(menuRow.name) || 'Conversation'}
          style={menu.at ? { left: menu.at.left, top: menu.at.top } : { visibility: 'hidden', left: 0, top: 0 }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeMenu(true); return }
            if (e.key === 'Tab') { e.preventDefault(); closeMenu(true); return }
            if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') return
            e.preventDefault()
            const items = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]')]
            const i = items.indexOf(document.activeElement as HTMLElement)
            const n = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length
            items[n]?.focus()
          }}>
          {entries.map((it, i) => it.kind === 'danger-head'
            ? <div key={'h' + i} className="q2-cl-danger-head" role="presentation"><hr /><p className="q2-menu-head"><Warn />Danger Zone</p></div>
            : (
              <button key={it.act} type="button" role="menuitem" data-act={it.act} aria-disabled={it.disabled || undefined}
                className={'q2-cl-item' + (it.danger ? ' q2-cl-danger' : '')}
                aria-description={it.sub}
                onClick={() => { if (!it.disabled) void act(menuRow, it.act) }}>
                <Icon name={it.act} />
                <span className="q2-cl-item-words"><span className="q2-cl-label">{it.label}</span>
                  {it.sub && <span className={'q2-cl-sub' + (it.note ? ' q2-cl-note-sub' : '')}>{it.sub}</span>}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  )
}

function Row({ c, current, open, renaming, onPick, onLatest, onMenu, onRenamed, onSay }: {
  c: Conversation; current: boolean; open: boolean; renaming: boolean
  onPick: () => void; onLatest?: () => void
  onMenu: (keyboard: boolean) => void
  onRenamed: (name: string | null) => void
  onSay: (w: string) => void
}) {
  const st = stateOf(c)
  const name = repairText(c.name) || 'Unnamed conversation'
  const time = rowTime(c)
  const hold = useRef<number | null>(null)
  const held = useRef(false)
  const [pressing, setPressing] = useState(false)
  const stop = () => { if (hold.current) { clearTimeout(hold.current); hold.current = null } setPressing(false) }
  return (
    <li className={`q2-cl-row ${st}` + (current ? ' is-current' : '') + (open ? ' is-open' : '') + (pressing ? ' is-pressing' : '')} data-id={c.id}>
      {renaming
        ? <RenameInPlace c={c} done={onRenamed} onSay={onSay} />
        : (
          <button type="button" className="q2-cl-open" aria-current={current ? 'true' : undefined} aria-label={rowLabel(c)} aria-keyshortcuts="Shift+F10"
            onClick={(e) => { if (held.current) { e.preventDefault(); held.current = false; return } onPick() }}
            onKeyDown={(e) => { if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); e.stopPropagation(); onMenu(true) } }}
            onContextMenu={(e) => { e.preventDefault(); if (!open) onMenu(true) }}
            onPointerDown={(e) => {
              if (e.pointerType !== 'touch') return
              held.current = false; setPressing(true)
              hold.current = window.setTimeout(() => { hold.current = null; held.current = true; setPressing(false); if (!open) onMenu(true) }, HOLD_MS)
            }}
            onPointerUp={stop} onPointerCancel={stop} onPointerLeave={stop}>
            <span className="q2-cl-name">{name}</span>
            <span className={'q2-cl-time' + (time.busy ? ' busy' : '')}>{time.busy && <span className="q2-cl-dot" aria-hidden="true" />}{time.words}</span>
          </button>
        )}
      {!renaming && (
        <span className="q2-cl-acts">
          {onLatest && (
            <button type="button" className="q2-latest-of" title={`Go to the newest post in ${name}`} aria-label={`Go to the newest post in ${name}`}
              onClick={onLatest}><Latest /></button>
          )}
          <button type="button" className="q2-cl-more" aria-haspopup="menu" aria-expanded={open} title="Actions" aria-label={`Actions for ${name}`}
            onClick={(e) => { e.stopPropagation(); onMenu(e.detail === 0) }}><More /></button>
        </span>
      )}
    </li>
  )
}

/* RENAME, IN PLACE: the existing rename route (`store.renameConversation`).
   Enter saves, Esc lets it go, leaving it saves what was typed. */
function RenameInPlace({ c, done, onSay }: { c: Conversation; done: (name: string | null) => void; onSay: (w: string) => void }) {
  const named = c.provisional ? '' : repairText(c.name)
  const [text, setText] = useState(named)
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const finished = useRef(false)
  useEffect(() => { input.current?.focus(); input.current?.select() }, [])
  const save = async () => {
    if (finished.current || busy) return
    const want = text.trim()
    if (!want || want === named.trim()) { finished.current = true; done(null); return }
    setBusy(true)
    try {
      const author = store.me ?? await store.loadMe()
      const got = await store.renameConversation(c.id, author, want, newOp())
      finished.current = true
      done(got.name ?? want)
    } catch (e: unknown) {
      onSay(e instanceof Error ? e.message : String(e))
      setBusy(false)
      input.current?.focus()
    }
  }
  return (
    <input ref={input} className="q2-cl-rename" value={text} maxLength={200} disabled={busy} aria-label="New name"
      placeholder="A name for this conversation"
      onChange={(e) => setText(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); void save() }
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finished.current = true; done(null) }
      }}
      onBlur={() => { void save() }} />
  )
}
