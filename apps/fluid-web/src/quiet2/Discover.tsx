/* EVERY CONVERSATION, FOUND (topic hierarchy and discovery round).
 *
 * The left rail stays a quick visual index of the most recently active
 * conversations. Its chevron opens this: the whole collection the Brain
 * lets the reader see, in the Brain's own order (most recent activity
 * first), read a page at a time as the list is scrolled, and searched by
 * name with the server's own search. Nothing is copied or ranked here: it
 * is Fluid's conversation list (`store.conversationPage`), the same read the
 * switcher in Fluid makes.
 *
 * Choosing one opens it the way the rail does; ⇥ opens it in a working
 * surface where there is one. Esc, a press outside, or × closes it, and
 * focus goes back to the chevron.
 *
 * NEW, at its top, starts a conversation the way Fluid's + does: Mentis's
 * own creation, unnamed until it is named, opened where the rail opens one.
 * It is offered only where the page may write (never on a read-only Brain);
 * a press while one is being made does nothing, and a refusal is said here. */
import { useEffect, useRef, useState } from 'react'
import type { Conversation } from '../fluid/store'
import { store } from '../fluid/store'
import { ago } from './Markers'
import { repairText } from './text'
import './discover.css'

const minutesSince = (at: number | null | undefined) => at ? Math.max(1, Math.round((Date.now() / 1000 - at) / 60)) : null

export default function Discover({ current, onPick, onBeside, onNew, onClose }: {
  current: string | null
  onPick: (id: string) => void
  /** opens it in a working surface, where there is one */
  onBeside?: (id: string) => void
  /** starts a new conversation and opens it; absent where nothing may be written */
  onNew?: () => Promise<void>
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<Conversation[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [next, setNext] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const end = useRef<HTMLLIElement>(null)
  /* which question the rows answer: a late page of an older search is dropped */
  const asked = useRef('')
  const close = useRef(onClose)
  close.current = onClose
  /* one conversation made per press: a second press while it is made does nothing */
  const [making, setMaking] = useState(false)
  const makingRef = useRef(false)
  const makeNew = () => {
    if (!onNew || makingRef.current) return
    makingRef.current = true
    setMaking(true); setError(null)
    onNew().then(() => close.current(), (e: unknown) => setError(`Could not start a conversation: ${e instanceof Error ? e.message : String(e)}`))
      .finally(() => { makingRef.current = false; setMaking(false) })
  }

  /* the first page for the question asked, a moment after typing stops */
  useEffect(() => {
    const words = q.trim()
    setNext(null)
    const t = window.setTimeout(() => {
      asked.current = words
      setBusy(true); setError(null)
      store.conversationPage(null, words).then((got) => {
        if (asked.current !== words) return
        setRows(got.conversations); setTotal(got.total); setNext(got.next)
        list.current?.scrollTo({ top: 0 })
      }, (e: unknown) => { if (asked.current === words) setError(`Could not read the conversations: ${String(e)}`) })
        .finally(() => { if (asked.current === words) setBusy(false) })
    }, words ? 220 : 0)
    return () => clearTimeout(t)
  }, [q])

  /* the next page, once the end of the list comes into view */
  useEffect(() => {
    const el = end.current
    if (!el || !next || busy) return
    const io = new IntersectionObserver((seen) => {
      if (!seen.some((s) => s.isIntersecting)) return
      io.disconnect()
      const words = asked.current
      setBusy(true)
      store.conversationPage(next, words).then((got) => {
        if (asked.current !== words) return
        setRows((had) => {
          const known = new Set((had ?? []).map((c) => c.id))
          return [...(had ?? []), ...got.conversations.filter((c) => !known.has(c.id))]
        })
        setTotal(got.total); setNext(got.next)
      }, (e: unknown) => { if (asked.current === words) { setError(`Could not read more: ${String(e)}`); setNext(null) } })
        .finally(() => { if (asked.current === words) setBusy(false) })
    }, { root: list.current, rootMargin: '120px' })
    io.observe(el)
    return () => io.disconnect()
  }, [next, busy, rows])

  /* closing: Esc anywhere, or a press outside */
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    box.current?.querySelector<HTMLInputElement>('input')?.focus()
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      e.preventDefault()
      const input = box.current?.querySelector<HTMLInputElement>('input')
      if (input && document.activeElement === input && input.value) { setQ(''); return }
      close.current()
    }
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node) && !(e.target as Element).closest?.('.q2-rail-more')) close.current() }
    document.addEventListener('keydown', esc); document.addEventListener('pointerdown', away)
    return () => {
      document.removeEventListener('keydown', esc); document.removeEventListener('pointerdown', away)
      if (opener?.isConnected) opener.focus()
    }
  }, [])

  const shown = rows ?? []
  return (
    <div className="q2-discover" role="dialog" aria-label="All conversations" ref={box}>
      <header className="q2-discover-head">
        <h2>Conversations</h2>
        {total !== null && <span className="q2-discover-count">{q.trim() ? `${total} found` : `${total} in this Brain`}</span>}
        {total === null && <span className="q2-discover-count" />}
        {onNew && (
          <button className="q2-discover-new" onClick={makeNew} disabled={making} aria-busy={making || undefined}
            title="Start a new conversation, unnamed until it is named" aria-label="New conversation">
            <span aria-hidden="true">+</span>{making ? 'Starting…' : 'New'}
          </button>
        )}
        <button className="q2-discover-close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <input type="search" className="q2-discover-search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Search conversations by name" aria-label="Search conversations by name" />
      <ul className="q2-discover-list" ref={list} aria-busy={busy || undefined}>
        {shown.map((c) => {
          const idle = minutesSince(c.last_activity)
          return (
            <li key={c.id}>
              <button className="q2-discover-row" aria-current={c.id === current ? 'true' : undefined}
                onClick={() => { onPick(c.id); onClose() }}>
                <span className="q2-discover-name">{repairText(c.name) || 'Unnamed conversation'}</span>
                <span className="q2-discover-meta">{c.posts} {c.posts === 1 ? 'post' : 'posts'}{idle ? ` · ${ago(idle)}` : ''}</span>
              </button>
              {onBeside && c.id !== current && (
                <button className="q2-marker-beside" title={`Open ${repairText(c.name)} in a working surface`} aria-label={`Open ${repairText(c.name)} in a working surface`}
                  onClick={() => { onBeside(c.id); onClose() }}>⇥</button>
              )}
            </li>
          )
        })}
        {next && <li ref={end} className="q2-discover-note" aria-hidden="true">{busy ? 'Reading more…' : ''}</li>}
        {rows && !shown.length && !busy && <li className="q2-discover-note">No conversation is named like that.</li>}
        {!rows && !error && <li className="q2-discover-note">Reading the Brain's conversations…</li>}
        {error && <li className="q2-discover-note" role="alert">{error}</li>}
      </ul>
    </div>
  )
}
