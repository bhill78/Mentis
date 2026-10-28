/* FOCUS SEARCH: THE BAR (search-in/, the approved assignment's 3).
 *
 * The reader's way of asking "where in what I am looking at does it say …":
 * a quiet bar a section's tools open, searching that section's current
 * content as it is typed (match.ts, highlight.ts). It changes nothing it
 * searches: closing it -- or emptying the input -- calls clear() and the
 * section looks exactly as it did.
 *
 * Enter is the next match, Shift+Enter the previous; Esc closes the bar and
 * stops, so it does not also step anything else back. `.*` takes the input
 * as a pattern (a bad one is said, never thrown), `Aa` makes it exact about
 * case. Ctrl/Cmd+F opens the bar of the section the keyboard is in -- and
 * only then keeps the browser's own find from opening.
 *
 * THE SEARCH IS THE CONTENT'S (kept.ts): given its content id, the bar keeps
 * its query, options and match there, so the content drawn in another place
 * -- a float, Primary, a leaf -- opens its bar again where it was. */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { compile, MAX_MATCHES, type Matcher } from './match'
import { searchIn, type SearchState } from './highlight'
import { forgetSearch, keepSearch, keptSearch } from './kept'
import './search-in.css'

export interface ElsewhereMatch { label: string; pick: () => void }
export interface ElsewhereResult { label: string; matches?: ElsewhereMatch[] }
type Elsewhere = string | ElsewhereResult | null

export function FocusSearch({ target, onClose, contentId, elsewhere }: {
  /** where the section's searchable content is, asked each time (a ref's
   *  current): the bar never holds a stale element */
  target: () => HTMLElement | null
  onClose: () => void
  /** the content searched (a zone's id), whose search this bar keeps */
  contentId?: string
  /** what the section holds but does not draw now (a slide not shown) that
   *  also matches, said after the count; null where there is none */
  elsewhere?: (m: Matcher) => Elsewhere
}) {
  const was = keptSearch(contentId)
  const [q, setQ] = useState(was?.q ?? '')
  const [re, setRe] = useState(was?.re ?? false)
  const [cs, setCs] = useState(was?.cs ?? false)
  const [error, setError] = useState<string | null>(null)
  const [count, setCount] = useState(0)
  const [index, setIndex] = useState(-1)
  const [also, setAlso] = useState<Elsewhere>(null)
  const state = useRef<SearchState | null>(null)
  /* asked of the caller on every render; held in a ref so a new closure does
     not re-run the search */
  const targetRef = useRef(target)
  targetRef.current = target
  const elsewhereRef = useRef(elsewhere)
  elsewhereRef.current = elsewhere
  /* the match a search coming back with its content resumes at; a new query
     or option starts at its first */
  const resume = useRef(was?.index ?? -1)
  const typed = (fn: () => void) => { resume.current = -1; fn() }
  /* The section's element can be replaced under the bar (a zone's body is
     drawn anew for each post it follows): searched again, the same query. */
  const searched = useRef<HTMLElement | null>(null)
  const [gen, setGen] = useState(0)
  useLayoutEffect(() => {
    const el = targetRef.current()
    if (!searched.current || !el || el === searched.current) return
    /* what the replaced element was at, the new one resumes at */
    searched.current = el
    resume.current = state.current?.index ?? -1
    setGen((g) => g + 1)
  })
  useEffect(() => { keepSearch(contentId, { q, re, cs }) }, [contentId, q, re, cs])
  const said = (s: SearchState, m: Matcher) => {
    setCount(s.count)
    setIndex(s.index)
    keepSearch(contentId, { index: s.index })
    setAlso(elsewhereRef.current?.(m) ?? null)
  }

  /* Search as typed. A new query or option is a new search over the section;
     the old one is cleared first, and closing (unmount) clears the last. */
  useEffect(() => {
    setError(null)
    setAlso(null)
    if (!q) { setCount(0); setIndex(-1); return }
    const m = compile(q, { regex: re, caseSensitive: cs })
    if ('error' in m) { setError(m.error); setCount(0); setIndex(-1); return }
    const el = targetRef.current()
    searched.current = el
    if (!el) { setCount(0); setIndex(-1); return }
    /* searchIn reports its first result before it returns: read it through
       a holder that is filled once it has. */
    const box: { s: SearchState | null } = { s: null }
    const s = searchIn(el, m, () => { if (box.s) said(box.s, m) }, resume.current)
    box.s = s
    state.current = s
    said(s, m)
    return () => { s.clear(); if (state.current === s) state.current = null }
  }, [q, re, cs, gen])

  const step = (d: 1 | -1) => {
    const s = state.current
    if (!s) return
    if (d > 0) s.next()
    else s.prev()
    setCount(s.count)
    setIndex(s.index)
    keepSearch(contentId, { index: s.index })
  }
  const close = () => { forgetSearch(contentId); onClose() }

  return (
    <div className="fs-bar" role="search" aria-label="Search in this section" data-search-skip
      onKeyDown={(e) => {
        /* Esc is this bar's first: nothing behind it may see it */
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close() }
      }}>
      <input
        className="fs-q"
        type="text"
        value={q}
        autoFocus
        placeholder="Find in this section"
        aria-label="Find in this section"
        spellCheck={false}
        onChange={(e) => { const v = e.target.value; typed(() => setQ(v)) }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); step(e.shiftKey ? -1 : 1) }
        }}
      />
      <span className={'fs-count' + (error ? ' fs-err' : '')} role="status">
        {error ? error : q ? (count > 0 ? `${index + 1} of ${count}${count >= MAX_MATCHES ? '+' : ''}${also ? ' here' : ''}` : also ? 'None here' : 'No matches') : ''}
        {!error && q && also ? ` · ${typeof also === 'string' ? also : also.label}` : ''}
      </span>
      {!error && q && typeof also === 'object' && also?.matches?.map((hit) => (
        <button key={hit.label} type="button" className="fs-elsewhere" onClick={hit.pick} title={`Peek at ${hit.label}`}>{hit.label}</button>
      ))}
      <button type="button" className="fs-btn" aria-label="Previous match (Shift+Enter)" title="Previous match (Shift+Enter)"
        disabled={!count} onClick={() => step(-1)}>↑</button>
      <button type="button" className="fs-btn" aria-label="Next match (Enter)" title="Next match (Enter)"
        disabled={!count} onClick={() => step(1)}>↓</button>
      <button type="button" className={'fs-btn fs-tog' + (re ? ' on' : '')} aria-pressed={re}
        aria-label="Use a regular expression" title="Use a regular expression"
        onClick={() => typed(() => setRe((v) => !v))}>.*</button>
      <button type="button" className={'fs-btn fs-tog' + (cs ? ' on' : '')} aria-pressed={cs}
        aria-label="Match case" title="Match case"
        onClick={() => typed(() => setCs((v) => !v))}>Aa</button>
      <button type="button" className="fs-btn fs-x" aria-label="Close search (Esc)" title="Close search (Esc)"
        onClick={close}>×</button>
    </div>
  )
}

/** The quiet tool that opens a section's search, in Fluid's tool-button
 *  manner; the caller's className puts it in its row (`fx-ctl` in the
 *  conversation's tools, the zone caption's own). */
export function SearchButton({ onOpen, className, label }: { onOpen: () => void; className?: string; label?: string }) {
  const says = label ?? 'Search in this section'
  return (
    <button type="button" className={'fs-open' + (className ? ' ' + className : '')}
      aria-label={`${says} (Ctrl+F)`} title={`${says} (Ctrl+F)`}
      onClick={(e) => { e.stopPropagation(); onOpen() }}>
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M10.4 10.4 14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  )
}

/** A section's search in two lines: `<SearchButton onOpen={() => s.setOpen(true)} />`
 *  among its tools, `{s.bar}` under its header. Ctrl/Cmd+F while the keyboard
 *  is inside the section (its target, or `hotkeyWithin` where that is wider)
 *  opens the bar, and only then is the browser's find kept away. Given the
 *  content's id, a search left open comes back wherever that content is
 *  drawn next (kept.ts). */
export function useFocusSearch(target: () => HTMLElement | null, hotkeyWithin?: () => HTMLElement | null,
  contentId?: string, elsewhere?: (m: Matcher) => Elsewhere) {
  const [open, setOpenState] = useState(() => !!keptSearch(contentId))
  const setOpen = useCallback((on: boolean) => {
    if (on) keepSearch(contentId, {})
    setOpenState(on)
  }, [contentId])
  const targetRef = useRef(target)
  targetRef.current = target
  const hotRef = useRef(hotkeyWithin)
  hotRef.current = hotkeyWithin
  /* Asked again after every render: the section may re-shape (a boundary
     dragged, a body remounted) and its element answer with it. */
  useEffect(() => {
    const el = hotRef.current?.() ?? targetRef.current()
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.key !== 'f' && e.key !== 'F') || !(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return
      e.preventDefault()
      e.stopPropagation()
      setOpen(true)
    }
    el.addEventListener('keydown', onKey)
    return () => el.removeEventListener('keydown', onKey)
  })
  const close = useCallback(() => setOpen(false), [])
  const ask = useCallback(() => targetRef.current(), [])
  const bar = open ? <FocusSearch key={contentId} target={ask} onClose={close} contentId={contentId} elsewhere={elsewhere} /> : null
  return { open, setOpen, bar }
}
