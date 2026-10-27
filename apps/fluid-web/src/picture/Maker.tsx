import { useEffect, useMemo, useRef, useState } from 'react'
import {
  accents, analyse, hex, lch, makeTheme, nameFor, renderImages,
  type Analysis, type Backdrop, type Options, type PictureTheme, type Scheme, type Strength,
} from './derive'
import { cssFor, UNREACHABLE, useStyle } from './store'
import './picture.css'

/* ------------------------------------------------------------------------ *
 * MAKE A LOOK FROM A PICTURE.
 *
 * Written for somebody who has never heard the word "token". Three steps and
 * no settings: choose a picture, tap the version you like, use it. The
 * workspace behind the panel IS the preview — whatever is tapped is what the
 * real screen turns into, so there is nothing to imagine.
 *
 * WHAT IT NEVER ASKS. Contrast, crops, veils, opacity, hex. Readability is
 * not a check the person can fail: every version is built so the faintest
 * words already clear 4.5:1 over the brightest part of the picture, and the
 * one strength control only goes up from there. The phone picture is cut
 * automatically. "Adjust" is behind one link, in plain words, for whoever
 * wants it.
 * ------------------------------------------------------------------------ */

export const PREVIEW_ID = 'look-preview'

export type Scope = 'conversation' | 'everywhere'

interface Made {
  name: string
  theme: PictureTheme
  images: { wide: Blob; tall: Blob }
  scope: Scope
}

export interface MakerProps {
  /** where "use this" applies by default — where the selector was opened */
  scope: Scope
  /** a conversation is open; if not, only "everywhere" makes sense */
  canScopeConversation: boolean
  scopeName: string
  /** the workspace shows `id` while the panel is open; null when it closes */
  onPreview: (id: string | null) => void
  /** keeps the look; rejects if it could not be kept, and the panel says so */
  onUse: (made: Made) => Promise<void>
  onClose: () => void
}

const STRENGTHS: { id: Strength; says: string }[] = [
  { id: 'picture', says: 'More picture' },
  { id: 'balanced', says: 'Balanced' },
  { id: 'reading', says: 'Easier reading' },
]

export default function Maker({ scope: scope0, canScopeConversation, scopeName, onPreview, onUse, onClose }: MakerProps) {
  const [img, setImg] = useState<ImageBitmap | null>(null)
  const [a, setA] = useState<Analysis | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [pick, setPick] = useState(0)
  const [opts, setOpts] = useState<Options | null>(null)
  const [adjust, setAdjust] = useState(false)
  const [backdrop, setBackdrop] = useState<Backdrop>('picture')
  const [name, setName] = useState('')
  /** the person typed a name: stop suggesting one */
  const [named, setNamed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const [scope, setScope] = useState<Scope>(canScopeConversation ? scope0 : 'everywhere')
  const [images, setImages] = useState<{ wide: Blob; tall: Blob } | null>(null)
  const [urls, setUrls] = useState<{ wide: string; tall: string } | null>(null)
  const [thumb, setThumb] = useState<string | null>(null)
  const file = useRef<HTMLInputElement | null>(null)
  const [over, setOver] = useState(false)

  const take = async (f: File | undefined) => {
    if (!f) return
    if (!f.type.startsWith('image/')) {
      setErr('That file is not a picture. Try a photo or an image file.')
      return
    }
    setErr(null)
    setBusy(true)
    try {
      const bm = await createImageBitmap(f)
      const an = analyse(bm)
      setImg(bm)
      setA(an)
      setNamed(false)
      setPick(0)
      setOpts(null)
      setThumb(URL.createObjectURL(f))
    } catch {
      setErr('That picture could not be opened. Try another one.')
    } finally {
      setBusy(false)
    }
  }

  // THE THREE READY-MADE VERSIONS. The picture decides the first; the second
  // is its opposite; the third keeps the first's ground and changes colour.
  const variants = useMemo(() => {
    if (!a) return []
    const natural: Scheme = a.meanL < 0.56 ? 'dark' : 'light'
    const other: Scheme = natural === 'dark' ? 'light' : 'dark'
    const n = accents(a).length
    const say = (s: Scheme) => (s === 'dark' ? 'Dark' : 'Light')
    const o = (scheme: Scheme, accent: number, strength: Strength = 'balanced'): Options =>
      ({ scheme, accent, strength, backdrop })
    return [
      { says: say(natural), o: o(natural, 0) },
      { says: say(other), o: o(other, 0) },
      n > 1 || backdrop === 'plain'
        ? { says: 'Different colour', o: o(natural, Math.min(1, n - 1)) }
        : { says: 'More picture', o: o(natural, 0, 'picture') },
    ]
  }, [a, backdrop])

  const current: Options | null = opts ? { ...opts, backdrop } : variants[pick]?.o ?? null
  const focus = current?.focus ?? a?.focus

  // The pictures a theme keeps. Re-cut only when the focus moves.
  useEffect(() => {
    if (!img || !a || !focus) return
    let live = true
    renderImages(img, a, focus).then((im) => {
      if (!live) return
      setImages(im)
      setUrls((old) => {
        if (old) { URL.revokeObjectURL(old.wide); URL.revokeObjectURL(old.tall) }
        return { wide: URL.createObjectURL(im.wide), tall: URL.createObjectURL(im.tall) }
      })
    })
    return () => { live = false }
  }, [img, a, focus?.x, focus?.y])

  // THE SUGGESTED NAME FOLLOWS THE VERSION, until the person names it.
  useEffect(() => {
    if (a && current && !named) setName(nameFor(a, current))
  }, [a, current?.accent, current?.backdrop, current?.scheme, named])

  const theme = useMemo(() => {
    if (!a || !current || !urls) return null
    return makeTheme({ ...a, focus: focus! }, current, urls)
  }, [a, current, urls, focus])

  const cards = useMemo(() => {
    if (!a || !urls) return []
    return variants.map((v) => makeTheme(a, v.o, urls))
  }, [a, urls, variants])

  useStyle('mentis-picture-preview', theme ? cssFor(PREVIEW_ID, theme) : '')
  useEffect(() => {
    onPreview(theme ? PREVIEW_ID : null)
  }, [theme != null])
  useEffect(() => () => onPreview(null), [])

  const change = (p: Partial<Options>) => setOpts({ ...(current as Options), ...p })

  const pickAccent = a ? accents(a) : []

  return (
    <aside className="pm" role="dialog" aria-label="Make a look from a picture">
      <header className="pm-head">
        <h2>Make a look from a picture</h2>
        <button className="pm-x" aria-label="Close" onClick={onClose}>×</button>
      </header>

      {!a && (
        <div
          className={'pm-drop' + (over ? ' over' : '')}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); void take(e.dataTransfer.files[0]) }}
        >
          <div className="pm-drop-art" aria-hidden="true">
            <span /><span /><span />
          </div>
          <button className="pm-primary" onClick={() => file.current?.click()} disabled={busy}>
            {busy ? 'Looking at your picture…' : 'Choose a picture'}
          </button>
          <p className="pm-hint">or drag one here</p>
          <p className="pm-small">
            A photo works best: a landscape, a place you like, a still from a film. Mentis picks the colours and
            keeps the words easy to read.
          </p>
          {err && <p className="pm-err">{err}</p>}
          <input
            ref={file}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => void take(e.target.files?.[0])}
          />
        </div>
      )}

      {a && (
        <div className="pm-body">
          {/* THE PICTURE BEHIND EVERYTHING, OR ONLY ITS COLOURS. Asked first,
              because it changes what every version below looks like. */}
          <div className="pm-row">
            <span className="pm-label">Background</span>
            <div className="pm-seg" role="radiogroup" aria-label="Background">
              <button role="radio" aria-checked={backdrop === 'picture'} className={backdrop === 'picture' ? 'on' : ''} onClick={() => setBackdrop('picture')}>
                Show the picture
              </button>
              <button role="radio" aria-checked={backdrop === 'plain'} className={backdrop === 'plain' ? 'on' : ''} onClick={() => setBackdrop('plain')}>
                Plain, in its colours
              </button>
            </div>
          </div>
          <p className="pm-step">Tap the one you like. The screen behind shows it.</p>
          <div className="pm-cards">
            {variants.map((v, i) => {
              const t = cards[i]
              const on = !opts && pick === i
              return (
                <button
                  key={i}
                  className={'pm-card' + (on ? ' on' : '')}
                  aria-pressed={on}
                  onClick={() => { setPick(i); setOpts(null) }}
                >
                  {t && urls ? <Mini t={t} img={urls.wide} /> : <span className="pm-mini" />}
                  <span className="pm-card-says">{v.says}</span>
                </button>
              )
            })}
          </div>

          <label className="pm-name">
            <span>Name</span>
            <input value={name} onChange={(e) => { setName(e.target.value); setNamed(true) }} />
          </label>

          {canScopeConversation && (
            <div className="pm-scope" role="radiogroup" aria-label="Where to use it">
              <span className="pm-label">Use it for</span>
              <div className="pm-seg">
                <button role="radio" aria-checked={scope === 'conversation'} className={scope === 'conversation' ? 'on' : ''} onClick={() => setScope('conversation')}>
                  {scopeName}
                </button>
                <button role="radio" aria-checked={scope === 'everywhere'} className={scope === 'everywhere' ? 'on' : ''} onClick={() => setScope('everywhere')}>
                  Everywhere
                </button>
              </div>
            </div>
          )}

          {!adjust ? (
            <button className="pm-link" onClick={() => setAdjust(true)}>Adjust…</button>
          ) : (
            current && (
              <div className="pm-adjust">
                <div className="pm-row">
                  <span className="pm-label">Light or dark</span>
                  <div className="pm-seg">
                    {(['dark', 'light'] as Scheme[]).map((s) => (
                      <button key={s} className={current.scheme === s ? 'on' : ''} onClick={() => change({ scheme: s })}>
                        {s === 'dark' ? 'Dark' : 'Light'}
                      </button>
                    ))}
                  </div>
                </div>
                {backdrop === 'picture' && <div className="pm-row">
                  <span className="pm-label">How much picture</span>
                  <div className="pm-seg">
                    {STRENGTHS.map((s) => (
                      <button key={s.id} className={current.strength === s.id ? 'on' : ''} onClick={() => change({ strength: s.id })}>
                        {s.says}
                      </button>
                    ))}
                  </div>
                </div>}
                <div className="pm-row">
                  <span className="pm-label">Highlight colour</span>
                  <div className="pm-dots">
                    {pickAccent.map((c, i) => (
                      <button
                        key={i}
                        className={'pm-dot' + (current.accent === i ? ' on' : '')}
                        style={{ background: hex(lch(0.74, Math.max(0.09, Math.min(0.16, c[1])), c[2])) }}
                        aria-label={`highlight colour ${i + 1}`}
                        onClick={() => change({ accent: i })}
                      />
                    ))}
                  </div>
                </div>
                {backdrop === 'picture' && thumb && focus && (
                  <div className="pm-row pm-row-col">
                    <span className="pm-label">Move the picture <em>drag the circle onto what matters</em></span>
                    <Focus src={thumb} at={focus} onMove={(f) => change({ focus: f })} />
                  </div>
                )}
              </div>
            )
          )}

          <footer className="pm-foot">
            <button className="pm-quiet" onClick={() => { setA(null); setImg(null); setOpts(null); setAdjust(false) }}>
              Another picture
            </button>
            <button
              className="pm-primary"
              disabled={!theme || !images || saving}
              onClick={() => {
                if (!theme || !images || !current) return
                setSaving(true)
                setFailed(null)
                onUse({ name: name.trim() || nameFor(a, current), theme, images, scope })
                  .catch(() => setFailed(UNREACHABLE))
                  .finally(() => setSaving(false))
              }}
            >
              {saving ? 'Saving…' : 'Use this look'}
            </button>
          </footer>
          {failed && <p className="pm-err pm-center" role="alert">{failed}</p>}
          <p className="pm-small pm-center">Saved in this brain, so it is on every device you use.</p>
        </div>
      )}
    </aside>
  )
}

/** A card: the picture, veiled the way the theme veils it, with a few lines
 *  of its own ink and one mark of its highlight — a room, not a swatch. */
export function Mini({ t, img }: { t: PictureTheme; img: string }) {
  const w = t.wide
  if (t.backdrop === 'plain') {
    return (
      <span className="pm-mini" style={{ backgroundColor: w['--canvas'] }}>
        <i style={{ background: w['--text'], width: '58%' }} />
        <i style={{ background: w['--text-dim'], width: '70%' }} />
        <i style={{ background: w['--text-dim'], width: '44%' }} />
        <b style={{ background: w['--accent'] }} />
      </span>
    )
  }
  return (
    <span
      className="pm-mini"
      style={{
        backgroundColor: w['--canvas'],
        backgroundImage:
          `linear-gradient(90deg, color-mix(in srgb, ${w['--canvas']} ${Math.round(t.veil * 100)}%, transparent) 70%, ` +
          `color-mix(in srgb, ${w['--canvas']} ${Math.round(t.veil * 40)}%, transparent)), url('${img}')`,
        backgroundSize: 'cover, cover',
        backgroundPosition: `0 0, ${w['--canvas-image-position']}`,
      }}
    >
      <i style={{ background: w['--text'], width: '58%' }} />
      <i style={{ background: w['--text-dim'], width: '70%' }} />
      <i style={{ background: w['--text-dim'], width: '44%' }} />
      <b style={{ background: w['--accent'] }} />
    </span>
  )
}

function Focus({ src, at, onMove }: { src: string; at: { x: number; y: number }; onMove: (f: { x: number; y: number }) => void }) {
  const box = useRef<HTMLDivElement | null>(null)
  const [p, setP] = useState(at)
  const drag = useRef(false)
  useEffect(() => setP(at), [at.x, at.y])
  const where = (e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect()
    return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) }
  }
  return (
    <div
      ref={box}
      className="pm-focus"
      onPointerDown={(e) => { drag.current = true; (e.target as Element).setPointerCapture(e.pointerId); setP(where(e)) }}
      onPointerMove={(e) => drag.current && setP(where(e))}
      onPointerUp={(e) => { drag.current = false; onMove(where(e)) }}
    >
      <img src={src} alt="" draggable={false} />
      <span className="pm-focus-ring" style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }} />
    </div>
  )
}
