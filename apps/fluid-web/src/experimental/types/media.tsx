/* EXPERIMENTAL: image and gallery -- pictures WITHOUT pictures.

   Nothing here generates, retrieves or loads an image. Every picture is a
   MOCK drawing made deterministically from the item's words (the same words
   always draw the same shapes), labelled on its face and beneath it so that
   nobody mistakes it for the real thing. A declared source or ref is shown
   exactly as declared; a URL an author writes is shown as text, never fetched.

   Image and gallery share one ITEM: a picture with a title, a caption, alt
   text and an optional ref, drawn by <Figure/> and enlarged by <Zoom/>. They
   stay two types because they mean different things: an image states an
   INTENT (show this existing item / ask for a new one) about one picture; a
   gallery is a set a person looks through, selects from and annotates. */
import './media.css'
import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import type { TypeDef } from '../api'
import { PALETTE, hash, q } from '../util'
import { URL_RE, gallerySpec, imageSpec, type Item } from '../spec/media'

export type { Item } from '../spec/media'

/* ------------------------------------------------------- shared: the item */

export const MOCK_LABEL = 'MOCK — nothing was generated or retrieved'
export const MOCK_PLACEHOLDER_DETAIL = 'No source image was retrieved or generated; this drawing is a placeholder made from the words in the block.'

/** A small deterministic generator, so the same words always draw the same picture. */
function rng(seed: number) {
  let s = seed || 1
  return () => {
    s ^= s << 13; s ^= s >>> 17; s ^= s << 5
    return (s >>> 0) / 4294967296
  }
}

/** The mock picture: a sky, a sun or moon, layered hills and a few marks, all
    chosen by hash(seed). The renderer picks every colour; nobody writes one. */
export function MockPicture({ seed, alt, big }: { seed: string; alt: string; big?: boolean }) {
  const W = 320, H = 200
  const r = rng(hash(seed))
  const pick = () => PALETTE[Math.floor(r() * PALETTE.length)]
  const sky = pick()
  const hills = [0, 1, 2].map((k) => {
    const base = H * (0.55 + k * 0.13)
    const pts: string[] = [`0,${H}`]
    for (let x = 0; x <= W; x += 40) pts.push(`${x},${Math.round(base - r() * 40)}`)
    pts.push(`${W},${H}`)
    return { pts: pts.join(' '), fill: pick(), op: 0.45 + k * 0.2 }
  })
  const sun = { x: 40 + r() * 240, y: 30 + r() * 40, rad: 14 + r() * 16 }
  const marks = Array.from({ length: 3 + Math.floor(r() * 4) }, () => ({
    x: r() * W, y: 20 + r() * 80, w: 6 + r() * 30, h: 3 + r() * 8, fill: pick(),
  }))
  return (
    <svg className={'rb-img-svg' + (big ? ' rb-img-big' : '')} viewBox={`0 0 ${W} ${H}`} role="img" preserveAspectRatio="xMidYMid slice">
      <title>{`${alt} (${MOCK_LABEL})`}</title>
      <rect width={W} height={H} fill="var(--surface-sunken)" />
      <rect width={W} height={H} fill={sky} opacity={0.22} />
      <circle cx={sun.x} cy={sun.y} r={sun.rad} fill={pick()} opacity={0.8} />
      {marks.map((m, i) => <rect key={i} x={m.x} y={m.y} width={m.w} height={m.h} rx={2} fill={m.fill} opacity={0.5} />)}
      {hills.map((h, i) => <polygon key={i} points={h.pts} fill={h.fill} opacity={h.op} />)}
      {/* The label is part of the drawing, so a cropped or zoomed view still says it. */}
      <g transform={`rotate(-12 ${W / 2} ${H / 2})`}>
        <rect x={-20} y={H / 2 - 22} width={W + 40} height={44} fill="#000" opacity={0.55} />
        <text x={W / 2} y={H / 2 + 2} fill="#fff" fontSize={26} fontWeight="bold" textAnchor="middle" letterSpacing={6}>MOCK</text>
        <text x={W / 2} y={H / 2 + 16} fill="#fff" fontSize={9} textAnchor="middle">nothing was generated or retrieved</text>
      </g>
    </svg>
  )
}

/** Enlarged view with plain zoom steps; the author never says how big. */
function Zoom({ item, seed, onClose }: { item: Item; seed: string; onClose: () => void }) {
  const [z, setZ] = useState(1)
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="rb-modal" role="dialog" aria-modal="true" aria-label={`Enlarged mock picture: ${item.title || item.alt}`} onClick={onClose}>
      <div className="rb-modal-box rb-img-zoombox" onClick={(e) => e.stopPropagation()}>
        <div className="rb-row">
          <b>{item.title || 'Picture'}</b>
          <span className="rb-img-mock">{MOCK_LABEL}</span>
          <span className="rb-grow" />
          {[1, 2, 3].map((n) => (
            <button key={n} className="btn quiet" aria-pressed={z === n} onClick={() => setZ(n)}>{n}×</button>
          ))}
          <button className="btn" onClick={onClose}>Close</button>
        </div>
        <div className="rb-img-zoomwrap">
          <div style={{ width: `${z * 100}%` }}>
            <MockPicture seed={seed} alt={item.alt} big />
          </div>
        </div>
        {item.caption && <p>{item.caption}</p>}
        <p className="rb-muted">alt: {item.alt}</p>
      </div>
    </div>
  )
}

/** One item, drawn the same way by image and by the gallery's detail pane. */
export function Figure({ item, seed, lead }: { item: Item; seed: string; lead?: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <figure className="rb-img-fig">
      <button className="rb-img-hit" onClick={() => setOpen(true)} title="Enlarge (mock picture)">
        <MockPicture seed={seed} alt={item.alt} />
      </button>
      <figcaption>
        <details className="rb-disclosure rb-img-mock">
          <summary><b>{MOCK_LABEL}</b></summary>
          <div className="rb-disclosure-body">{MOCK_PLACEHOLDER_DETAIL}</div>
        </details>
        {lead}
        {item.title && <b className="rb-img-title">{item.title}</b>}
        {item.caption && <div className="rb-img-cap">{item.caption}</div>}
        <div className="rb-muted">alt: {item.alt}</div>
        {item.ref && <div className="rb-muted">ref (declared, not retrieved): {item.ref}</div>}
        {URL_RE.test(item.caption + ' ' + item.ref) && (
          <div className="rb-muted">A URL above is shown as text only. Nothing was loaded from it.</div>
        )}
      </figcaption>
      {open && <Zoom item={item} seed={seed} onClose={() => setOpen(false)} />}
    </figure>
  )
}

const scopeLine = (a: Record<string, string>) =>
  a.source ? `source (declared, not resolved): ${a.source}${a.refs ? ' ' + a.refs : ''}` : 'source: (not declared)'

/* -------------------------------------------------------------------- image */

type ImageState = { note: string }

export const image: TypeDef<string, ImageState> = {
  ...imageSpec,
  Rich({ data, attrs: a, state, set }) {
    const item: Item = { id: 'image', title: a.title ?? '', caption: data, alt: a.alt, ref: a.source === 'refs' ? a.refs ?? '' : '' }
    const lead = a.intent === 'show'
      ? <div className="rb-img-intent">Would show {a.source === 'refs' ? <b>{a.refs}</b> : 'an item from the current conversation'}. It was <b>not retrieved</b>; this is a stand-in drawing.</div>
      : <div className="rb-img-intent">A request for a <b>new</b> picture, described below. <b>Nothing was generated</b>; this is a stand-in drawing.</div>
    return (
      <div className="rb-img">
        <Figure item={item} seed={`${a.alt}\n${data}\n${a.refs ?? ''}`} lead={lead} />
        <div className="rb-lbl">Your note on this picture</div>
        <textarea
          className="rb-img-note"
          placeholder="e.g. wrong angle; want it wider"
          value={state?.note ?? ''}
          onChange={(e) => set(e.target.value ? { note: e.target.value } : undefined)}
        />
      </div>
    )
  },
  readable(data, a, s) {
    const out = a.title ? [`title: ${q(a.title)}`] : []
    out.push(`intent: ${a.intent} (${a.intent === 'show' ? 'show an existing item' : 'request a new picture'})`)
    out.push(`alt: ${q(a.alt)}`)
    out.push(scopeLine(a))
    out.push(`${a.intent === 'show' ? 'caption' : 'description of the picture wanted'}: ${data ? q(data) : '(none)'}`)
    out.push(`picture: ${MOCK_LABEL}. ${MOCK_PLACEHOLDER_DETAIL}`)
    out.push(`note: ${s?.note ? q(s.note) : '(none)'}`)
    return out.join('\n')
  },
  handoff(data, a, s) {
    return a.intent === 'show'
      ? { image_would_show: a.source === 'refs' ? a.refs : 'an item from the conversation (unspecified)', retrieved: false, note: s?.note ?? null }
      : { image_requested: data, generated: false, note: s?.note ?? null }
  },
}

/* ------------------------------------------------------------------ gallery */

type GalState = { sel?: string[]; notes?: Record<string, string> }

export const gallery: TypeDef<Item[], GalState> = {
  ...gallerySpec,
  Rich({ data, attrs: a, state, set, mode }) {
    const [focus, setFocus] = useState(0)
    const grid = useRef<HTMLDivElement>(null)
    const i = Math.min(focus, data.length - 1)
    const it = data[i]
    const sel = state?.sel ?? []
    const how = a.select ?? 'none'
    const put = (s: GalState) => {
      const clean: GalState = {}
      if (s.sel?.length) clean.sel = s.sel
      if (s.notes && Object.keys(s.notes).length) clean.notes = s.notes
      set(Object.keys(clean).length ? clean : undefined)
    }
    const toggle = (id: string) => {
      const on = sel.includes(id)
      put({ ...state, sel: how === 'one' ? (on ? [] : [id]) : on ? sel.filter((x) => x !== id) : [...sel, id] })
    }
    const note = (id: string, v: string) => {
      const notes = { ...(state?.notes ?? {}) }
      if (v) notes[id] = v
      else delete notes[id]
      put({ ...state, notes })
    }
    /* Arrow keys move through the grid; the column count is whatever the grid currently shows. */
    const onKey = (e: React.KeyboardEvent) => {
      const cols = grid.current ? getComputedStyle(grid.current).gridTemplateColumns.split(' ').length : 1
      const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols }[e.key]
      if (step !== undefined) {
        e.preventDefault()
        const n = Math.max(0, Math.min(data.length - 1, i + step))
        setFocus(n)
        ;(grid.current?.children[n] as HTMLElement | undefined)?.querySelector('button')?.focus()
      } else if ((e.key === ' ' || e.key === 'Enter') && how !== 'none' && e.target instanceof HTMLButtonElement && e.target.classList.contains('rb-gal-thumb')) {
        e.preventDefault()
        toggle(data[i].id)
      }
    }
    if (!it) return <p className="rb-muted">No pictures.</p>
    return (
      <div className={'rb-gal' + (mode === 'pin' ? ' rb-gal-pin' : '')}>
        <p className="rb-muted">
          {data.length} mock pictures · {how === 'none' ? 'viewing only' : how === 'one' ? 'pick one' : 'pick any number'}
          {how !== 'none' && ` · ${sel.length} selected`} · arrows move{how !== 'none' ? ', Space selects' : ''} · click the large picture to enlarge
        </p>
        <div className="rb-gal-main">
          <div className="rb-gal-grid" ref={grid} onKeyDown={onKey} role="listbox" aria-multiselectable={how === 'many'} aria-label="Pictures">
            {data.map((x, n) => (
              <div key={x.id + n} className={'rb-gal-cell' + (n === i ? ' rb-gal-on' : '') + (sel.includes(x.id) ? ' rb-gal-sel' : '')}>
                <button className="rb-gal-thumb" role="option" aria-selected={sel.includes(x.id)} tabIndex={n === i ? 0 : -1} onClick={() => setFocus(n)} title={x.title}>
                  <MockPicture seed={`${x.alt}\n${x.caption}\n${x.ref}\n${x.id}`} alt={x.alt} />
                  <span className="rb-gal-name">{x.title}</span>
                </button>
                {how !== 'none' && (
                  <input
                    className="rb-gal-pick"
                    type={how === 'one' ? 'radio' : 'checkbox'}
                    checked={sel.includes(x.id)}
                    onChange={() => toggle(x.id)}
                    aria-label={`Select ${x.title}`}
                  />
                )}
                {state?.notes?.[x.id] && <span className="rb-gal-hasnote" title="has a note">✎</span>}
              </div>
            ))}
          </div>
          <div className="rb-gal-detail">
            <Figure key={it.id} item={it} seed={`${it.alt}\n${it.caption}\n${it.ref}\n${it.id}`} lead={<div className="rb-muted">{i + 1} of {data.length} · id {it.id}</div>} />
            <div className="rb-row">
              <button className="btn quiet" disabled={i === 0} onClick={() => setFocus(i - 1)}>◂ Previous</button>
              <button className="btn quiet" disabled={i === data.length - 1} onClick={() => setFocus(i + 1)}>Next ▸</button>
              <span className="rb-grow" />
              {how !== 'none' && (
                <button className="btn" aria-pressed={sel.includes(it.id)} onClick={() => toggle(it.id)}>
                  {sel.includes(it.id) ? 'Selected ✓' : how === 'one' ? 'Pick this one' : 'Select'}
                </button>
              )}
            </div>
            <div className="rb-lbl">Your note on {it.title || it.id}</div>
            <textarea className="rb-img-note" value={state?.notes?.[it.id] ?? ''} onChange={(e) => note(it.id, e.target.value)} />
          </div>
        </div>
      </div>
    )
  },
  readable(data, a, s) {
    const out = a.title ? [`title: ${q(a.title)}`] : []
    out.push(`select: ${a.select ?? 'none'}${a.select ? '' : ' (default)'}`)
    out.push(scopeLine(a))
    out.push(`pictures (${data.length}; each is a ${MOCK_LABEL}). ${MOCK_PLACEHOLDER_DETAIL}`)
    const sel = s?.sel ?? []
    data.forEach((it) => {
      const mark = a.select && a.select !== 'none' ? (sel.includes(it.id) ? '[x] ' : '[ ] ') : ''
      out.push(`- ${mark}${it.id}: ${q(it.title)}${it.caption ? ' — ' + q(it.caption) : ''}; alt ${q(it.alt)}${it.ref ? `; ref ${it.ref}` : ''}`)
      if (s?.notes?.[it.id]) out.push(`    note: ${q(s.notes[it.id])}`)
    })
    if (a.select && a.select !== 'none') out.push(`selected: ${sel.length ? sel.join(', ') : '(none)'}`)
    return out.join('\n')
  },
  handoff(data, _a, s) {
    const title = (id: string) => data.find((x) => x.id === id)?.title ?? id
    return {
      selected: (s?.sel ?? []).map((id) => ({ id, title: title(id), ref: data.find((x) => x.id === id)?.ref || null })),
      notes: Object.entries(s?.notes ?? {}).map(([id, note]) => ({ id, title: title(id), note })),
      pictures_are_mock: true,
    }
  },
}
