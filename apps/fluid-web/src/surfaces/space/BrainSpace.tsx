import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  firstSeen,
  isDark,
  look,
  orderHue,
  presence,
  tint,
  under,
  worldRadius,
  type Eye,
  type Placed,
  type Seen,
  type Strand,
} from './layout'

/* ------------------------------------------------------------------------ *
 * THE BRAIN, IN SPACE: the canvas.
 *
 * Mark III's 3D Brain, carried across as BEHAVIOUR (see layout.ts for what
 * is and is not inherited). What made it the best version, kept here:
 *
 *   QUIET AT REST. No strand is drawn and no frame is scheduled until an
 *   edge explains something -- a selection, or "every connection" asked for.
 *   A white haze of lit lines is what the earlier Brains became.
 *
 *   STARS, NOT DISCS. A small core and an additive glow on a dark ground, so
 *   a dense Conversation becomes visibly dense without anything claiming
 *   density means something. On a light ground light does not add, so the
 *   glow is painted normally and the stars are ink.
 *
 *   EVERY STRAND IS A LINK THE RECORD HOLDS, coloured by which relation it
 *   is, and while it is explaining a selection a light runs along it in the
 *   link's own direction. That claims nothing traversed it.
 *
 *   SELECTION REACHES TWO HOPS, because one hop is always a star around the
 *   query. Hop one is coloured by direction (what it points to, what points
 *   to it); hop two is neutral and fainter, since the record says nothing
 *   about it and the selection; everything else recedes but stays put.
 *
 *   SEMANTIC ZOOM. A thing earns its words by being drawn large enough for
 *   them to be read, a dozen at most; the selection and its reach are named
 *   on leaders held clear of their own glow.
 *
 * THE THEME IS READ, NOT ASSUMED. Every colour comes from the tokens the
 * canvas element computes (`--text`, `--accent`, ...), and whether the ground
 * is dark is measured from `--surface`, so atmospheres and light/dark reach
 * the drawing without it knowing either exists.
 * ------------------------------------------------------------------------ */

export type Palette = 'none' | 'layer' | 'conversation'
type Tie = 'chosen' | 'out' | 'in' | 'near'

export interface BrainSpaceProps {
  placed: Placed[]
  links: Strand[]
  selected: string | null
  onSelect: (id: string | null) => void
  palette: Palette
  allStrands: boolean
  /** layers not drawn now; the layout still covers them so nothing moves */
  hidden: ReadonlySet<string>
  /** draw the Brain as of this moment (seconds); null is now */
  asOf: number | null
  playing: boolean
  /** a Conversation's name, for callouts */
  nameOf: (conversation: string | null) => string | null
  label: string
  /** go where the chosen thing lives (Enter) */
  onOpen?: (id: string) => void
}

/** The words a thing is shown by. A deleted thing's words are not given. */
export function wordsOf(n: { summary: string | null; deleted: boolean; entry: string }): string {
  return n.summary || (n.deleted ? 'deleted' : n.entry)
}

/** Drawn hollow: here, and no longer carrying anything. */
const hollow = (n: { deleted: boolean; replaced: boolean }) => n.deleted || n.replaced

/** How the eye starts: outside and a little above, so the shape reads first. */
const OPENING = { turn: 0.6, rise: 0.42 }
/** A thing earns its name at this projected size (px). */
const READABLE = 4
/** How many plain names may be on screen at once. */
const NAMED_AT_MOST = 12
/** Below this a thing is not drawn, and so not there to be clicked. ONE number. */
const FAINTEST = 0.02
/** The largest a star may draw, in px. A star does not become a moon. */
const BIGGEST = 7

/** How much light a layer has. The ladder, not a score. */
const LIT: Record<string, number> = { how: 1, that: 0.9, other: 0.85, place: 0.82, who: 0.78, said: 0.5, material: 0.4 }
/** How big a layer draws, in world units. Small and star-like. */
const SIZE: Record<string, number> = { how: 1.9, that: 1.6, other: 1.5, place: 1.45, who: 1.35, said: 0.85, material: 0.75 }

export const LAYER_TOKEN: Record<string, string> = {
  how: '--attention',
  that: '--accent',
  place: '--live',
  who: '--who-1',
  other: '--who-5',
  said: '--text-dim',
  material: '--who-6',
}

const reduced = () =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

export default function BrainSpace({
  placed,
  links,
  selected,
  onSelect,
  palette,
  allStrands,
  hidden,
  asOf,
  playing,
  nameOf,
  label,
  onOpen,
}: BrainSpaceProps) {
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const holder = useRef<HTMLDivElement | null>(null)
  const [hover, setHover] = useState<Placed | null>(null)
  const drawn = useRef<(Placed & Seen)[]>([])
  const frame = useRef(0)
  const sprites = useRef(new Map<string, HTMLCanvasElement>())

  const radius = useMemo(() => worldRadius(placed.length), [placed.length])
  const regionAt = useMemo(() => firstSeen(placed.map((p) => p.node.conversation)), [placed])
  const relationAt = useMemo(() => firstSeen(links.map((l) => l.relation)), [links])
  const byId = useMemo(() => new Map(placed.map((p) => [p.id, p])), [placed])
  /** How much each Conversation holds, so the busiest regions are named first. */
  const held = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of placed) if (p.node.conversation) m.set(p.node.conversation, (m.get(p.node.conversation) ?? 0) + 1)
    return m
  }, [placed])

  const eye = useRef<Eye>({ ...OPENING, out: radius * 1.85, at: { x: 0, y: 0, z: 0 } })
  useEffect(() => {
    eye.current.out = radius * 1.85
  }, [radius])

  /* What is drawable right now: not a hidden layer, and arrived by `asOf`.
     The layout covers everything whatever is shown, so arriving and showing
     a layer never shove anything else around. */
  const visible = useCallback(
    (p: Placed) => !hidden.has(p.node.layer) && (asOf === null || (p.node.at ?? 0) <= asOf),
    [hidden, asOf],
  )

  /** Who is joined to whom, both directions, read once. */
  const adjacent = useMemo(() => {
    const m = new Map<string, { other: string; dir: 'out' | 'in'; relation: string }[]>()
    const add = (k: string, v: { other: string; dir: 'out' | 'in'; relation: string }) => {
      const got = m.get(k)
      if (got) got.push(v)
      else m.set(k, [v])
    }
    for (const l of links) {
      add(l.from.id, { other: l.to.id, dir: 'out', relation: l.relation })
      add(l.to.id, { other: l.from.id, dir: 'in', relation: l.relation })
    }
    return m
  }, [links])

  /** The selection's neighbourhood, two hops, from the record and nothing else. */
  const near = useMemo(() => {
    const found = new Map<string, { tie: Tie; hop: number; relation: string | null }>()
    if (!selected || !byId.has(selected)) return found
    found.set(selected, { tie: 'chosen', hop: 0, relation: null })
    let ring = [selected]
    for (let hop = 1; hop <= 2; hop += 1) {
      const next: string[] = []
      for (const at of ring) {
        for (const a of adjacent.get(at) ?? []) {
          if (found.has(a.other)) continue
          const p = byId.get(a.other)
          if (!p || !visible(p)) continue
          found.set(a.other, { tie: hop === 1 ? a.dir : 'near', hop, relation: hop === 1 ? a.relation : null })
          next.push(a.other)
        }
      }
      ring = next
    }
    return found
  }, [selected, adjacent, byId, visible])

  /** Strands worth drawing: inside the neighbourhood, every one if asked, or none. */
  const showing = useMemo(() => {
    const here = links.filter((l) => visible(l.from) && visible(l.to))
    if (selected && near.size > 0) return here.filter((l) => near.has(l.from.id) && near.has(l.to.id))
    return allStrands ? here : []
  }, [links, visible, selected, near, allStrands])

  const travelled = useRef(0)

  const sprite = useCallback((colour: string) => {
    let s = sprites.current.get(colour)
    if (s) return s
    s = document.createElement('canvas')
    s.width = s.height = 64
    const g = s.getContext('2d')
    if (g) {
      const glow = g.createRadialGradient(32, 32, 0, 32, 32, 32)
      glow.addColorStop(0, tint(colour, 1))
      glow.addColorStop(0.35, tint(colour, 0.35))
      glow.addColorStop(1, tint(colour, 0))
      g.fillStyle = glow
      g.fillRect(0, 0, 64, 64)
    }
    sprites.current.set(colour, s)
    return s
  }, [])

  const span = useMemo(() => {
    let lo = Infinity
    let hi = -Infinity
    for (const p of placed) {
      const t = p.node.at
      if (t === null) continue
      lo = Math.min(lo, t)
      hi = Math.max(hi, t)
    }
    return hi > lo ? hi - lo : 1
  }, [placed])

  const paint = useCallback(() => {
    const el = canvas.current
    const box = holder.current
    if (!el || !box) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = box.clientWidth
    const h = box.clientHeight
    if (!w || !h) return
    if (el.width !== Math.round(w * dpr) || el.height !== Math.round(h * dpr)) {
      el.width = Math.round(w * dpr)
      el.height = Math.round(h * dpr)
      el.style.width = `${w}px`
      el.style.height = `${h}px`
    }
    const g = el.getContext('2d')
    if (!g) return
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, w, h)

    const style = getComputedStyle(el)
    const token = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback
    const ink = token('--text', '#eceae5')
    const accent = token('--accent', '#79ccb6')
    const COLOUR: Record<Tie, string> = {
      chosen: accent,
      out: token('--attention', '#e59a63'),
      in: token('--live', '#78b6ea'),
      near: ink,
    }
    const dark = isDark(token('--surface', '#17181b'))
    const font = style.fontFamily || 'system-ui, sans-serif'
    const layerColour: Record<string, string> = {}
    for (const [layer, name] of Object.entries(LAYER_TOKEN)) layerColour[layer] = token(name, ink)
    const tinted = palette !== 'none'
    const own = (p: Placed) =>
      palette === 'layer'
        ? layerColour[p.node.layer] ?? ink
        : palette === 'conversation'
          ? p.node.conversation
            ? orderHue(regionAt.get(p.node.conversation) ?? 0, dark)
            : ink
          : ink

    const E = eye.current
    /* FRAMED FOR THE SCREEN IT IS ON until somebody travels. The Brain is
       wider than it is tall, so a portrait phone needs the eye further out
       to see all of it at once. */
    if (!zoomed.current) E.out = radius * 1.85 * (h > w ? 1.4 : 1)
    const seen: (Placed & Seen)[] = []
    for (const p of placed) {
      if (!visible(p)) continue
      const s = look(p, E, w, h)
      if (s.ahead) seen.push({ ...p, ...s })
    }
    seen.sort((a, b) => b.depth - a.depth)
    drawn.current = seen.filter((p) => presence(p.depth, radius, E.out) > FAINTEST)
    const at = new Map(seen.map((s) => [s.id, s]))
    const carrying = Boolean(selected) && near.size > 0

    // ── strands, under everything, coloured by which relation they are ──────
    g.lineCap = 'round'
    for (const l of showing) {
      const a = at.get(l.from.id)
      const b = at.get(l.to.id)
      if (!a || !b) continue
      const lit = Math.max(presence(a.depth, radius, E.out), presence(b.depth, radius, E.out))
      if (lit <= FAINTEST) continue
      const out = Math.max(near.get(a.id)?.hop ?? 0, near.get(b.id)?.hop ?? 0)
      const reach = out >= 2 ? 0.34 : 1
      const hue = orderHue(relationAt.get(l.relation) ?? 0, dark)
      g.strokeStyle = carrying ? tint(hue, lit * 0.9 * reach) : tint(hue, lit * (dark ? 0.34 : 0.42))
      g.lineWidth = carrying ? (out >= 2 ? 0.85 : 1.3) : 0.8
      g.setLineDash(hollow(a.node) || hollow(b.node) ? [3, 3] : [])
      g.beginPath()
      g.moveTo(a.sx, a.sy)
      g.lineTo(b.sx, b.sy)
      g.stroke()
      g.setLineDash([])
      if (carrying && out < 2 && !reduced()) {
        const t = travelled.current % 1
        const px = a.sx + (b.sx - a.sx) * t
        const py = a.sy + (b.sy - a.sy) * t
        g.globalAlpha = Math.min(1, lit * 0.95)
        g.drawImage(sprite(hue), px - 4.5, py - 4.5, 9, 9)
        g.globalAlpha = 1
      }
    }

    // ── the stars ──────────────────────────────────────────────────────────
    const fresh = span / 40
    const labelled: (Placed & Seen)[] = []
    for (const p of seen) {
      const lit = presence(p.depth, radius, E.out)
      if (lit <= FAINTEST) continue
      const kin = near.get(p.id)
      const layer = p.node.layer
      const hub = p.node.kind === 'conversation'
      const carry = tinted ? 0.72 + (LIT[layer] ?? 0.5) * 0.28 : LIT[layer] ?? 0.5
      let alpha = lit * carry * 0.9
      if (carrying && !kin) alpha *= 0.28
      if (kin) alpha = Math.max(alpha, kin.hop >= 2 ? 0.5 : 0.95)
      if (hollow(p.node)) alpha *= 0.55
      const justCame = asOf !== null && asOf - (p.node.at ?? 0) < fresh
      if (justCame) alpha = 1

      const base = (SIZE[layer] ?? 1) * (hub ? 1.6 : 1)
      const grown = tinted ? 1.55 : 1
      const plain = Math.min(BIGGEST, Math.max(0.85, base * p.scale))
      const r = Math.min(BIGGEST, Math.max(tinted ? 1.35 : 0.85, base * p.scale * grown))
      const colour = kin ? COLOUR[kin.tie] : tinted ? own(p) : ink

      if (dark) g.globalCompositeOperation = 'lighter'
      const spread = (tinted ? 2.4 : 3.4) * r
      g.globalAlpha = Math.min(1, alpha * (tinted ? 1 : dark ? 0.85 : 0.5))
      g.drawImage(sprite(colour), p.sx - spread, p.sy - spread, spread * 2, spread * 2)
      g.globalAlpha = 1
      g.globalCompositeOperation = 'source-over'

      /* ENDED IS DRAWN HOLLOW, AND IT IS STILL DRAWN: here, and no longer
         standing -- not absent, which would say it never existed. */
      if (hollow(p.node)) {
        g.beginPath()
        g.arc(p.sx, p.sy, Math.max(r, 2), 0, Math.PI * 2)
        g.setLineDash([2, 2])
        g.strokeStyle = tint(colour, Math.min(1, alpha * 0.95))
        g.lineWidth = 1
        g.stroke()
        g.setLineDash([])
      } else {
        g.beginPath()
        g.arc(p.sx, p.sy, r, 0, Math.PI * 2)
        g.fillStyle = tint(colour, Math.min(1, alpha * 1.15))
        g.fill()
      }
      if (hub && !kin && lit > 0.2) {
        /* A Conversation is the centre of its region: a thin ring says so. */
        g.beginPath()
        g.arc(p.sx, p.sy, r + 2.5, 0, Math.PI * 2)
        g.strokeStyle = tint(colour, alpha * 0.55)
        g.lineWidth = 0.75
        g.stroke()
      }
      if (justCame && p.id !== selected) {
        const age = (asOf! - (p.node.at ?? 0)) / fresh
        g.beginPath()
        g.arc(p.sx, p.sy, r + 4 + (1 - age) * 12, 0, Math.PI * 2)
        g.strokeStyle = tint(accent, 0.75 * (1 - age))
        g.lineWidth = 1.25
        g.stroke()
      }
      if (p.id === selected) {
        g.globalAlpha = dark ? 0.5 : 0.35
        g.drawImage(sprite(accent), p.sx - r * 7, p.sy - r * 7, r * 14, r * 14)
        g.globalAlpha = 1
        g.beginPath()
        g.arc(p.sx, p.sy, r + 7, 0, Math.PI * 2)
        g.strokeStyle = tint(accent, 1)
        g.lineWidth = 1.75
        g.stroke()
      }
      if ((hub ? plain * 0.7 : plain) >= READABLE * (hub ? 0.5 : 1) && alpha > 0.35) labelled.push(p)
    }

    // ── callouts: the selection and its reach, on leaders ────────────────────
    type Called = { p: Placed & Seen; hop: number; tie: Tie; relation: string | null }
    const calling: Called[] = []
    const chosen = selected ? at.get(selected) : null
    if (chosen && presence(chosen.depth, radius, E.out) > FAINTEST) {
      calling.push({ p: chosen, hop: 0, tie: 'chosen', relation: null })
    }
    if (carrying) {
      const round = seen
        .map((p) => ({ p, kin: near.get(p.id) }))
        .filter(
          (n): n is { p: Placed & Seen; kin: { tie: Tie; hop: number; relation: string | null } } =>
            Boolean(n.kin) &&
            n.kin!.hop > 0 &&
            presence(n.p.depth, radius, E.out) > 0.06 &&
            n.p.sx > -40 &&
            n.p.sx < w + 40 &&
            n.p.sy > -40 &&
            n.p.sy < h + 40,
        )
        .sort((a, b) => a.kin.hop - b.kin.hop || a.p.depth - b.p.depth)
      for (const n of round.slice(0, NAMED_AT_MOST)) {
        calling.push({ p: n.p, hop: n.kin.hop, tie: n.kin.tie, relation: n.kin.relation })
      }
    }

    const taken: { x: number; y: number; r: number; b: number }[] = []
    const clear = (x: number, y: number, r: number, b: number) =>
      x >= -4 && r <= w + 4 && !taken.some((t) => x < t.r + 8 && r > t.x - 8 && y < t.b + 6 && b > t.y - 6)
    const called = new Set<string>()
    const onScreen = new Set(drawn.current.map((p) => p.id))
    const narrow = w < 520
    /* WHAT FLOATS OVER THE FIELD IS NOT WRITTEN UNDER: the title and its
       caption (and the colour key beneath them while something is chosen),
       and the Options control. Words there would be read through them. */
    taken.push({ x: -8, y: -8, r: narrow ? w - 110 : 300, b: narrow ? (carrying ? 225 : 140) : carrying ? 200 : 150 })
    taken.push({ x: w - 130, y: -8, r: w + 8, b: 56 })

    for (const { p: c, hop, tie, relation } of calling) {
      const strength = hop === 0 ? 1 : hop === 1 ? 0.62 : 0.34
      const kind = c.node.kind === 'contribution' ? 'turn' : c.node.kind
      const words = wordsOf(c.node)
      const dot = Math.min(BIGGEST, Math.max(1.4, (SIZE[c.node.layer] ?? 1) * c.scale))
      const WIDE = Math.min(hop === 0 ? 232 : 190, narrow ? w * 0.52 : 999)
      const REACH = hop === 0 ? (narrow ? 34 : 66) : narrow ? 24 : 42
      const RISE = hop === 0 ? 52 : 30
      const pointsTo = hop > 0 ? 0 : links.filter((l) => l.from.id === c.id && onScreen.has(l.to.id)).length
      const pointedAt = hop > 0 ? 0 : links.filter((l) => l.to.id === c.id && onScreen.has(l.from.id)).length
      const counts =
        hop > 0
          ? ''
          : [pointsTo > 0 ? `points to ${pointsTo} here` : null, pointedAt > 0 ? `${pointedAt} point to it here` : null]
              .filter(Boolean)
              .join('  ·  ')
      const bodyFont = `${hop === 0 ? 12.5 : 11.5}px ${font}`
      g.font = bodyFont
      const runs: string[] = []
      let run = ''
      const lines = hop === 0 ? 2 : 1
      for (const word of words.split(/\s+/)) {
        const next = run ? `${run} ${word}` : word
        if (g.measureText(next).width > WIDE && run) {
          runs.push(run)
          run = word
        } else run = next
        if (runs.length === lines) break
      }
      if (runs.length < lines && run) runs.push(run)
      const step = hop === 0 ? 15 : 14
      const high = 22 + runs.length * step + (counts ? 13 : 0)

      let dir: 1 | -1 = c.sx + dot + REACH + 20 + WIDE > w ? -1 : 1
      const box = () => {
        const x3 = c.sx + dir * (dot + REACH) + dir * 20
        const tx = x3 + dir * 7
        const l = dir > 0 ? tx : tx - WIDE
        return { x: l, y: c.sy - RISE - 26, r: l + WIDE, b: c.sy - RISE - 26 + high }
      }
      let spot = box()
      if (!clear(spot.x, spot.y, spot.r, spot.b)) {
        dir = dir === 1 ? -1 : 1
        spot = box()
        if (!clear(spot.x, spot.y, spot.r, spot.b) && hop > 0) continue
      }
      /* THE WORDS STAY ON SCREEN. On a narrow screen neither side may have
         room; the box is slid back inside and the leader follows it. */
      const slide = spot.r > w - 6 ? w - 6 - spot.r : spot.x < 6 ? 6 - spot.x : 0
      spot = { ...spot, x: spot.x + slide, r: spot.r + slide }
      /* SLID OVER ITS OWN STAR, the words are lifted clear of it and the
         leader rises straight up to them: never a line that doubles back. */
      const over = slide !== 0 && spot.x - 4 < c.sx && c.sx < spot.r + 4
      const lift = over ? Math.max(0, spot.b - (c.sy - dot - 14)) : 0
      spot = { ...spot, y: spot.y - lift, b: spot.b - lift }
      if ((slide || lift) && hop > 0 && !clear(spot.x, spot.y, spot.r, spot.b)) continue
      taken.push(spot)
      called.add(c.id)
      const x3 = c.sx + dir * (dot + REACH) + slide + dir * 20
      const x2 = x3 - dir * 20
      const y2 = c.sy - RISE - lift
      g.strokeStyle = tint(hop === 0 ? accent : COLOUR[tie], 0.75 * strength)
      g.lineWidth = hop === 0 ? 1 : 0.75
      g.beginPath()
      if (over) {
        g.moveTo(c.sx, c.sy - dot - 6)
        g.lineTo(c.sx, spot.b + 2)
      } else {
        g.moveTo(c.sx + dir * (dot + 7), c.sy - 5)
        g.lineTo(x2, y2)
        g.lineTo(x3, y2)
      }
      g.stroke()

      g.textAlign = dir > 0 ? 'left' : 'right'
      const tx = x3 + dir * 7
      g.font = `600 ${hop === 0 ? 9.5 : 9}px ${font}`
      g.fillStyle = tint(hop === 0 ? (tinted ? own(c) : accent) : COLOUR[tie], 0.95 * strength)
      const where = hop === 0 && c.node.kind !== 'conversation' ? nameOf(c.node.conversation) : null
      let head = [kind, relation, where].filter(Boolean).join(' · ').toUpperCase()
      while (head.length > 4 && g.measureText(head).width > WIDE) head = `${head.slice(0, -2)}…`
      g.fillText(head, tx, y2 - 21)
      g.font = bodyFont
      g.fillStyle = tint(ink, 0.97 * strength)
      runs.forEach((line, i) => {
        const more = i === runs.length - 1 && runs.join(' ').length < words.length
        g.fillText(more ? `${line}…` : line, tx, y2 - 7 + i * step)
      })
      if (counts) {
        g.font = `10px ${font}`
        g.fillStyle = tint(ink, 0.55)
        g.fillText(counts, tx, y2 - 7 + runs.length * step + 3)
      }
      g.textAlign = 'left'
    }

    /* ── THE REGIONS, NAMED, while nothing is chosen. A Conversation is where
       a region is, and a field of unnamed clusters gives nobody a bearing.
       The busiest few are named at their own centre, quietly, and give way
       to anything a callout already says. ─────────────────────────────── */
    if (!carrying) {
      const hubs = seen
        .filter((p) => p.node.kind === 'conversation' && presence(p.depth, radius, E.out) > 0.3)
        .filter((p) => p.sx > 20 && p.sx < w - 20 && p.sy > 60 && p.sy < h - 20)
        .sort((a, b) => (held.get(b.id) ?? 0) - (held.get(a.id) ?? 0))
        .slice(0, w < 520 ? 4 : 9)
      g.font = `600 10px ${font}`
      g.textAlign = 'center'
      for (const p of hubs) {
        const words = p.node.summary || 'a Conversation'
        const said = words.length > 30 ? `${words.slice(0, 28)}…` : words
        const wide = g.measureText(said).width
        const spot = { x: p.sx - wide / 2, y: p.sy - 22, r: p.sx + wide / 2, b: p.sy - 10 }
        if (!clear(spot.x, spot.y, spot.r, spot.b)) continue
        taken.push(spot)
        called.add(p.id)
        g.fillStyle = tint(ink, 0.62 * presence(p.depth, radius, E.out))
        g.fillText(said, p.sx, p.sy - 12)
      }
      g.textAlign = 'left'
    }

    // ── plain names for what is near enough to have earned one ──────────────
    g.font = `11px ${font}`
    for (const p of labelled.slice(-NAMED_AT_MOST)) {
      if (called.has(p.id)) continue
      const words = wordsOf(p.node)
      const said = words.length > 46 ? `${words.slice(0, 44)}…` : words
      /* THE SAME ON-SCREEN RULE AS A CALLOUT: a name that would run off an
         edge, or over words already placed, is not drawn at all. */
      const wide = g.measureText(said).width
      const spot = { x: p.sx + 9, y: p.sy - 8, r: p.sx + 9 + wide, b: p.sy + 5 }
      if (spot.x < 4 || spot.r > w - 4 || !clear(spot.x, spot.y, spot.r, spot.b)) continue
      taken.push(spot)
      g.fillStyle = tint(ink, p.node.kind === 'conversation' ? 0.8 : 0.68)
      g.fillText(said, p.sx + 9, p.sy + 3)
    }

    const over = hover ? at.get(hover.id) : null
    if (over && !called.has(over.id)) {
      const words = wordsOf(over.node)
      g.font = `12px ${font}`
      const said = words.length > 64 ? `${words.slice(0, 62)}…` : words
      const wide = g.measureText(said).width
      const side = over.sx + 10 + wide > w ? over.sx - 10 - wide : over.sx + 10
      const left = Math.max(4, Math.min(side, w - 4 - wide))
      g.fillStyle = tint(ink, 0.95)
      g.fillText(said, left, over.sy - 9)
    }
  }, [placed, visible, radius, selected, near, showing, palette, asOf, span, hover, links, nameOf, sprite, held, regionAt, relationAt])

  /* BRINGING A SELECTION INTO VIEW: the eye TRAVELS to it -- what it orbits
     moves -- so the wheel then goes toward the selection rather than toward
     the middle of the Brain. The angle is left alone: which way you had the
     Brain turned is your bearing on it. Letting go returns to the middle. */
  const facing = useRef(0)
  const [travelling, setTravelling] = useState(false)
  useEffect(() => {
    const found = selected ? byId.get(selected) : null
    const want = found ? { x: found.x, y: found.y, z: found.z } : { x: 0, y: 0, z: 0 }
    const from = { ...eye.current.at }
    if (Math.abs(from.x - want.x) < 0.01 && Math.abs(from.y - want.y) < 0.01 && Math.abs(from.z - want.z) < 0.01)
      return
    if (reduced()) {
      eye.current.at = want
      paint()
      return
    }
    const began = performance.now()
    const MS = 420
    cancelAnimationFrame(facing.current)
    const step = () => {
      const t = Math.min(1, (performance.now() - began) / MS)
      const e = 1 - Math.pow(1 - t, 3)
      eye.current.at = {
        x: from.x + (want.x - from.x) * e,
        y: from.y + (want.y - from.y) * e,
        z: from.z + (want.z - from.z) * e,
      }
      paint()
      if (t < 1) facing.current = requestAnimationFrame(step)
      else setTravelling(false)
    }
    setTravelling(true)
    facing.current = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(facing.current)
      setTravelling(false)
    }
    // `paint` deliberately omitted: this runs when the SELECTION changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, byId])

  /* THE ONLY LOOP, AND IT DOES NOT RUN AT REST: it exists while a selection's
     strands are being explained, and never for somebody who asked for no
     motion. */
  const sparking = Boolean(selected) && showing.length > 0 && !reduced()
  const moving = sparking || travelling || playing
  useEffect(() => {
    if (!sparking) return
    let live = true
    let last = performance.now()
    const tick = (now: number) => {
      if (!live) return
      travelled.current = (travelled.current + (now - last) / 2600) % 1
      last = now
      paint()
      requestAnimationFrame(tick)
    }
    const id = requestAnimationFrame(tick)
    return () => {
      live = false
      cancelAnimationFrame(id)
    }
  }, [sparking, paint])

  useEffect(() => {
    paint()
  }, [paint])
  useEffect(() => {
    const box = holder.current
    if (!box || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => paint())
    ro.observe(box)
    return () => ro.disconnect()
  }, [paint])
  /* A THEME OR ATMOSPHERE CHANGE IS A REPAINT. The tokens are read on every
     paint; what was missing was being told they changed. */
  useEffect(() => {
    const mo = new MutationObserver(() => {
      sprites.current.clear()
      paint()
    })
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class', 'style'] })
    const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null
    const again = () => {
      sprites.current.clear()
      paint()
    }
    mq?.addEventListener?.('change', again)
    return () => {
      mo.disconnect()
      mq?.removeEventListener?.('change', again)
    }
  }, [paint])

  const nudge = useCallback(() => {
    if (frame.current) return
    frame.current = requestAnimationFrame(() => {
      frame.current = 0
      paint()
    })
  }, [paint])
  useEffect(
    () => () => {
      if (frame.current) cancelAnimationFrame(frame.current)
      frame.current = 0
    },
    [],
  )

  const zoomed = useRef(false)
  const zoom = useCallback(
    (by: number) => {
      zoomed.current = true
      eye.current.out = Math.max(radius * 0.035, Math.min(radius * 7, eye.current.out * by))
      nudge()
    },
    [radius, nudge],
  )

  /* A CLICK IS NOT A DRAG OF ZERO PIXELS: a real click jitters a pixel or
     two, and turning the camera by that moved the star out from under it
     before `click` fired. Past SLOP it is a turn; under it, a choice. Two
     fingers are a pinch. */
  const SLOP = 4
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const dragging = useRef<{ x: number; y: number; from: { x: number; y: number }; moved: boolean } | null>(null)
  const pinch = useRef<number | null>(null)
  const turned = useRef(false)

  const onDown = useCallback((e: React.PointerEvent) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      pinch.current = Math.hypot(a.x - b.x, a.y - b.y)
      dragging.current = null
      turned.current = true
      return
    }
    dragging.current = { x: e.clientX, y: e.clientY, from: { x: e.clientX, y: e.clientY }, moved: false }
  }, [])

  const onMove = useCallback(
    (e: React.PointerEvent) => {
      const box = holder.current
      if (!box) return
      if (pointers.current.has(e.pointerId)) pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
      if (pinch.current !== null && pointers.current.size >= 2) {
        const [a, b] = [...pointers.current.values()]
        const d = Math.hypot(a.x - b.x, a.y - b.y)
        if (d > 0 && pinch.current > 0) zoom(pinch.current / d)
        pinch.current = d
        return
      }
      if (dragging.current) {
        const held = dragging.current
        const far = Math.hypot(e.clientX - held.from.x, e.clientY - held.from.y)
        if (!held.moved && far < SLOP) return
        const dx = e.clientX - held.x
        const dy = e.clientY - held.y
        dragging.current = { ...held, x: e.clientX, y: e.clientY, moved: true }
        eye.current.turn += dx * 0.005
        eye.current.rise = Math.max(-1.35, Math.min(1.35, eye.current.rise + dy * 0.005))
        nudge()
        return
      }
      if (e.pointerType !== 'mouse') return
      const r = box.getBoundingClientRect()
      const found = under({ x: e.clientX - r.left, y: e.clientY - r.top }, drawn.current)
      if ((found?.id ?? null) !== (hover?.id ?? null)) setHover(found)
    },
    [hover, nudge, zoom],
  )

  const onUp = useCallback((e?: React.PointerEvent) => {
    if (e) pointers.current.delete(e.pointerId)
    if (pointers.current.size < 2) pinch.current = null
    if (!turned.current) turned.current = dragging.current?.moved ?? false
    dragging.current = null
  }, [])

  /* Wheel is travel, bounded so you can get in among the stars without
     ending up inside one. React attaches wheel passively, so it is bound by
     hand to be allowed to stop the page scrolling. */
  useEffect(() => {
    const box = holder.current
    if (!box) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      zoom(1 + e.deltaY * 0.0014)
    }
    box.addEventListener('wheel', wheel, { passive: false })
    return () => box.removeEventListener('wheel', wheel)
  }, [zoom])

  const onClick = useCallback(
    (e: React.MouseEvent) => {
      const box = holder.current
      if (!box) return
      if (turned.current) {
        turned.current = false
        return
      }
      const r = box.getBoundingClientRect()
      const coarse = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches
      const found = under({ x: e.clientX - r.left, y: e.clientY - r.top }, drawn.current, coarse ? 18 : 9)
      onSelect(found ? found.id : null)
    },
    [onSelect],
  )

  /* THE KEYBOARD CHOOSES, NOT ONLY TURNS (review N3). Tab walks from the
     chosen thing to the next thing it is connected to that the walk has not
     yet visited -- or, with nothing chosen, to the busiest Conversation not
     yet visited -- and the camera travels with it; Shift+Tab steps back
     along the walk. When there is nowhere left to go, Tab leaves the canvas
     as it would anywhere else, so focus is never trapped. Enter opens what
     is chosen; Esc lets go; arrows turn and + and - travel. */
  const trail = useRef<string[]>([])
  const visited = useRef(new Set<string>())
  useEffect(() => {
    if (!selected) {
      trail.current = []
      visited.current = new Set()
    } else visited.current.add(selected)
  }, [selected])
  const nextStop = useCallback((): string | null => {
    const fresh = (id: string) => !visited.current.has(id) && byId.has(id) && visible(byId.get(id)!)
    if (selected) {
      const hop = [...near.entries()]
        .filter(([, k]) => k.hop === 1)
        .map(([id]) => id)
        .sort()
      const go = hop.find(fresh)
      if (go) return go
    }
    const hubs = placed
      .filter((p) => p.node.kind === 'conversation')
      .sort((a, b) => (held.get(b.id) ?? 0) - (held.get(a.id) ?? 0) || (a.id < b.id ? -1 : 1))
      .map((p) => p.id)
    return hubs.find(fresh) ?? null
  }, [selected, near, byId, visible, placed, held])

  const onKey = useCallback(
    (e: React.KeyboardEvent) => {
      const E = eye.current
      if (e.key === 'Tab') {
        if (e.shiftKey) {
          const back = trail.current.pop()
          if (back === undefined) return
          e.preventDefault()
          onSelect(back)
          return
        }
        const to = nextStop()
        if (!to) return
        e.preventDefault()
        if (selected) trail.current.push(selected)
        onSelect(to)
        return
      }
      if (e.key === 'Enter' && selected && onOpen) {
        e.preventDefault()
        onOpen(selected)
        return
      }
      if (e.key === 'ArrowLeft') E.turn -= 0.12
      else if (e.key === 'ArrowRight') E.turn += 0.12
      else if (e.key === 'ArrowUp') E.rise = Math.max(-1.35, E.rise - 0.1)
      else if (e.key === 'ArrowDown') E.rise = Math.min(1.35, E.rise + 0.1)
      else if (e.key === '+' || e.key === '=') return zoom(0.85)
      else if (e.key === '-' || e.key === '_') return zoom(1.18)
      else if (e.key === 'Escape' && selected) {
        e.stopPropagation()
        onSelect(null)
        return
      } else return
      e.preventDefault()
      nudge()
    },
    [zoom, nudge, onSelect, selected, nextStop, onOpen],
  )

  const drawing = useMemo(() => placed.filter(visible).length, [placed, visible])

  return (
    <div
      className="space-field"
      ref={holder}
      data-strands={showing.length}
      data-moving={String(moving)}
      data-drawn={drawing}
      data-selected={selected ?? ''}
      tabIndex={0}
      role="application"
      aria-label={label}
      aria-roledescription="3D view of this Brain"
      aria-description="Tab moves to the next connected thing, Shift+Tab steps back, Enter opens it, Escape lets go; arrow keys turn, plus and minus travel"
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      onPointerLeave={(e) => {
        onUp(e)
        setHover(null)
      }}
      onClick={onClick}
      onKeyDown={onKey}
    >
      <canvas ref={canvas} className="space-canvas" />
    </div>
  )
}
