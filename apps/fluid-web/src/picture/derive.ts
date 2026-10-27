/* ------------------------------------------------------------------------ *
 * A THEME FROM ONE PICTURE — THE ARITHMETIC.
 *
 * PROTOTYPE. Browser-only: nothing here leaves the page and nothing is
 * fetched. It automates what was done by hand for Hail Mary
 * (experiments/theme_hailmary/README.md):
 *
 *   1. read the picture's colours           analyse()
 *   2. map them onto the atmosphere tokens  makeTheme()
 *   3. place the picture and its veils      placeWide() / tallCrop()
 *   4. hold every veil at the strength the  veilFor()
 *      words need, and no weaker
 *
 * It writes the same token block atmosphere.css already defines (see THE
 * CONTRACT there), so the canvas needs no new mechanism: a picture theme is
 * one more `:root[data-atmosphere=…]` rule, written at run time.
 *
 * Colour work is in OKLab/OKLCH so "lighter", "same hue" and "less vivid"
 * mean what they say; contrast is WCAG's, measured in sRGB, because that is
 * where the browser composites the veil over the picture.
 * ------------------------------------------------------------------------ */

export type RGB = [number, number, number] // 0..255
type Lab = [number, number, number]
type LCh = [number, number, number] // L 0..1, C, h degrees

// -- colour spaces --------------------------------------------------------

const toLin = (c: number) => {
  const v = c / 255
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}
const fromLin = (v: number) => {
  const c = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055
  return c * 255
}

function rgbToLab([r, g, b]: RGB): Lab {
  const lr = toLin(r), lg = toLin(g), lb = toLin(b)
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb)
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb)
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

function labToLinear([L, a, b]: Lab): [number, number, number] {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
}

const labToLch = ([L, a, b]: Lab): LCh => [L, Math.hypot(a, b), ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360]

/** OKLCH → sRGB, pulling chroma in until the colour exists on a screen. */
export function lch(L: number, C: number, h: number): RGB {
  let c = C
  for (let i = 0; i < 24; i++) {
    const rad = (h * Math.PI) / 180
    const lin = labToLinear([L, c * Math.cos(rad), c * Math.sin(rad)])
    if (lin.every((v) => v >= -0.0005 && v <= 1.0005) || c < 0.002) {
      return lin.map((v) => Math.round(Math.min(255, Math.max(0, fromLin(Math.min(1, Math.max(0, v))))))) as RGB
    }
    c *= 0.85
  }
  return [0, 0, 0]
}

export const hex = ([r, g, b]: RGB) => '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')
export const rgba = ([r, g, b]: RGB, a: number) => `rgba(${r}, ${g}, ${b}, ${+a.toFixed(3)})`

// -- contrast (WCAG 2) ----------------------------------------------------

export const luminance = ([r, g, b]: RGB) => 0.2126 * toLin(r) + 0.7152 * toLin(g) + 0.0722 * toLin(b)
export function contrast(x: RGB, y: RGB) {
  const a = luminance(x), b = luminance(y)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}
const over = (top: RGB, alpha: number, under: RGB): RGB =>
  [0, 1, 2].map((i) => top[i] * alpha + under[i] * (1 - alpha)) as RGB

/** THE READING GUARANTEE. The weakest veil of `veil` that still gives `ink`
 *  `target`:1 over the worst pixel in the region — the brightest one under
 *  light words, the darkest under dark ones. Found by halving, since
 *  contrast only improves as the veil thickens. */
export function veilFor(veil: RGB, ink: RGB, worst: RGB, target: number): number {
  if (contrast(ink, worst) >= target) return 0
  let lo = 0, hi = 1
  for (let i = 0; i < 20; i++) {
    const mid = (lo + hi) / 2
    if (contrast(ink, over(veil, mid, worst)) >= target) hi = mid
    else lo = mid
  }
  return hi
}

// -- reading the picture --------------------------------------------------

export interface Cluster {
  rgb: RGB
  lch: LCh
  share: number
}

export interface Analysis {
  width: number
  height: number
  /** a small copy of the picture, kept for the region measurements */
  small: ImageData
  clusters: Cluster[]
  /** mean OKLab lightness, 0..1 — decides dark or light */
  meanL: number
  /** where the picture's bright and busy part is, 0..1 each way */
  focus: { x: number; y: number }
  /** small, bright, vivid parts — lights, highlights — which a palette of
   *  big areas misses and a person picking an accent would not */
  lights: Cluster[]
}

const SMALL = 96

/** Everything the rest needs, from one pass over a 96px copy. */
export function analyse(img: HTMLImageElement | ImageBitmap): Analysis {
  const w0 = img.width, h0 = img.height
  const k = SMALL / Math.max(w0, h0)
  const w = Math.max(8, Math.round(w0 * k)), h = Math.max(8, Math.round(h0 * k))
  const cv = document.createElement('canvas')
  cv.width = w
  cv.height = h
  const cx = cv.getContext('2d', { willReadFrequently: true })!
  cx.drawImage(img, 0, 0, w, h)
  const data = cx.getImageData(0, 0, w, h)

  const labs: Lab[] = []
  for (let i = 0; i < data.data.length; i += 4) {
    labs.push(rgbToLab([data.data[i], data.data[i + 1], data.data[i + 2]]))
  }
  const meanL = labs.reduce((s, p) => s + p[0], 0) / labs.length

  // THE PALETTE: k-means in OKLab, seeded far apart so it is deterministic.
  const K = 12
  const seeds: Lab[] = [labs[Math.floor(labs.length / 2)]]
  while (seeds.length < K) {
    let best = 0, bestD = -1
    for (let i = 0; i < labs.length; i += 3) {
      const d = Math.min(...seeds.map((s) => dist(s, labs[i])))
      if (d > bestD) { bestD = d; best = i }
    }
    seeds.push(labs[best])
  }
  let centres = seeds.map((s) => [...s] as Lab)
  const owner = new Array<number>(labs.length).fill(0)
  for (let round = 0; round < 12; round++) {
    const sum = centres.map(() => [0, 0, 0, 0])
    labs.forEach((p, i) => {
      let bi = 0, bd = Infinity
      centres.forEach((c, j) => { const d = dist(c, p); if (d < bd) { bd = d; bi = j } })
      owner[i] = bi
      const s = sum[bi]; s[0] += p[0]; s[1] += p[1]; s[2] += p[2]; s[3]++
    })
    centres = centres.map((c, j) => (sum[j][3] ? [sum[j][0] / sum[j][3], sum[j][1] / sum[j][3], sum[j][2] / sum[j][3]] : c))
  }
  const counts = centres.map((_, j) => owner.filter((o) => o === j).length)
  const clusters = centres
    .map((c, j) => {
      const l = labToLch(c)
      return { rgb: lch(l[0], l[1], l[2]), lch: l, share: counts[j] / labs.length }
    })
    .filter((c) => c.share > 0.002)
    .sort((a, b) => b.share - a.share)

  // THE FOCUS: where the eye goes — edges, departures from the mean, and
  // colour — weighted towards its strongest fifth.
  const sal: number[] = []
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x
    const L = labs[i][0]
    const gx = x > 0 && x < w - 1 ? labs[i + 1][0] - labs[i - 1][0] : 0
    const gy = y > 0 && y < h - 1 ? labs[i + w][0] - labs[i - w][0] : 0
    const C = Math.hypot(labs[i][1], labs[i][2])
    sal.push(Math.hypot(gx, gy) * 2 + Math.abs(L - meanL) + C)
  }
  const cut = [...sal].sort((a, b) => b - a)[Math.floor(sal.length * 0.2)]
  let fx = 0, fy = 0, fw = 0
  sal.forEach((s, i) => {
    if (s < cut) return
    fx += (i % w) * s; fy += Math.floor(i / w) * s; fw += s
  })
  const focus = fw ? { x: fx / fw / (w - 1), y: fy / fw / (h - 1) } : { x: 0.5, y: 0.5 }

  // THE LIGHTS: vivid pixels, weighted by how bright they are, by hue.
  const bins = Array.from({ length: 24 }, () => ({ w: 0, L: 0, C: 0, a: 0, b: 0, n: 0 }))
  labs.forEach((p) => {
    const [L, C, h] = labToLch(p)
    if (C < 0.07 || L < 0.45) return
    const bin = bins[Math.floor(h / 15) % 24]
    const wgt = C * L
    bin.w += wgt; bin.L += L * wgt; bin.C += C * wgt; bin.a += p[1] * wgt; bin.b += p[2] * wgt; bin.n++
  })
  const lights = bins
    .filter((b) => b.n >= Math.max(3, labs.length * 0.0015))
    .map((b) => {
      const h = ((Math.atan2(b.b, b.a) * 180) / Math.PI + 360) % 360
      const l: LCh = [b.L / b.w, b.C / b.w, h]
      return { rgb: lch(l[0], l[1], l[2]), lch: l, share: b.n / labs.length }
    })

  return { width: w0, height: h0, small: data, clusters, meanL, focus, lights }
}

const dist = (a: Lab, b: Lab) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2

/** The worst pixel for `dark` or light words inside a rectangle of the
 *  picture (fractions of it). The 99.5th percentile rather than the single
 *  extreme, so one hot speck does not decide the whole veil. */
function worstIn(a: Analysis, r: { x0: number; x1: number; y0: number; y1: number }, lightInk: boolean): RGB {
  const { width: w, height: h, data } = a.small
  const px: { l: number; rgb: RGB }[] = []
  for (let y = Math.floor(r.y0 * h); y < Math.ceil(r.y1 * h); y++)
    for (let x = Math.floor(r.x0 * w); x < Math.ceil(r.x1 * w); x++) {
      const i = (y * w + x) * 4
      const rgb: RGB = [data[i], data[i + 1], data[i + 2]]
      px.push({ l: luminance(rgb), rgb })
    }
  if (!px.length) return lightInk ? [255, 255, 255] : [0, 0, 0]
  px.sort((p, q) => p.l - q.l)
  const at = lightInk ? Math.min(px.length - 1, Math.floor(px.length * 0.995)) : Math.floor(px.length * 0.005)
  return px[at].rgb
}

// -- placing it -----------------------------------------------------------

/** The reference screen the wide placement is worked out for. */
const VIEW = 1440 / 900

/** WIDE: move the busy part out from under the reading column, towards the
 *  right where the reading veil lets go. Returns the CSS position and the
 *  part of the picture that is then on screen. */
export function placeWide(a: Analysis) {
  const ia = a.width / a.height
  let px = 50, py = 50
  let win = { x0: 0, x1: 1, y0: 0, y1: 1 }
  if (ia > VIEW) {
    const W = ia / VIEW // picture width, in screen widths
    const p = clamp((0.78 - a.focus.x * W) / (1 - W), 0, 1)
    px = p * 100
    const off = (W - 1) * p
    win = { x0: off / W, x1: (off + 1) / W, y0: 0, y1: 1 }
  } else {
    const H = VIEW / ia
    const p = clamp((0.42 - a.focus.y * H) / (1 - H), 0, 1)
    py = p * 100
    const off = (H - 1) * p
    win = { x0: 0, x1: 1, y0: off / H, y1: (off + 1) / H }
  }
  const sub = (f0: number, f1: number) => ({
    x0: win.x0 + (win.x1 - win.x0) * f0, x1: win.x0 + (win.x1 - win.x0) * f1, y0: win.y0, y1: win.y1,
  })
  return {
    /** any span of the screen's width, as a region of the picture */
    span: sub,
    position: `${px.toFixed(1)}% ${py.toFixed(1)}%`,
    /** where the words are: after the rail, before the right-hand fade */
    reading: sub(0.12, 0.8),
    /** the rail, which sits on the canvas itself */
    rail: sub(0, 0.3),
  }
}

/** TALL: the phone crop, taken around the focus, as a region of the picture. */
export function tallCrop(a: Analysis, focus = a.focus) {
  const aspect = 9 / 19.5
  const ia = a.width / a.height
  if (ia <= aspect) return { x0: 0, x1: 1, y0: 0, y1: 1 }
  const wf = aspect / ia
  const x0 = clamp(focus.x - wf / 2, 0, 1 - wf)
  return { x0, x1: x0 + wf, y0: 0, y1: 1 }
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

// -- the theme ------------------------------------------------------------

export type Scheme = 'dark' | 'light'
/** How much of the picture shows. Never below what reading needs. */
export type Strength = 'picture' | 'balanced' | 'reading'

export interface Options {
  scheme: Scheme
  /** index into accents() */
  accent: number
  strength: Strength
  /** where the phone crop is centred; defaults to the found focus */
  focus?: { x: number; y: number }
  /** the picture behind everything, or a plain ground in its colours */
  backdrop?: Backdrop
}

/** THE OWNER'S TWO USES OF A PICTURE: as the background itself, or only as
 *  the source of the colours over a plain background. */
export type Backdrop = 'picture' | 'plain'

/** The picture's candidate accents, most useful first: vivid, big enough
 *  to matter, and different in hue from the ground. At most five, all
 *  distinct from one another. */
export function accents(a: Analysis): LCh[] {
  const ground = a.clusters[0].lch
  const scored = [...a.clusters, ...a.lights]
    .filter((c) => c.lch[1] > 0.035)
    .map((c) => {
      // A mark has to stand out from the ground it sits on: red on a red
      // picture is not a highlight (Hail Mary took the hull's amber for it).
      const apart = hueGap(c.lch[2], ground[2]) > 35 || ground[1] < 0.03 ? 2 : 0.5
      return { c, score: c.lch[1] * c.share ** 0.35 * apart }
    })
    .sort((p, q) => q.score - p.score)
  const out: LCh[] = []
  for (const { c } of scored) {
    if (out.every((o) => hueGap(o[2], c.lch[2]) > 28)) out.push(c.lch)
    if (out.length === 5) break
  }
  if (!out.length) out.push([0.6, 0.1, 172]) // Mentis teal, when the picture has no colour to give
  // A PICTURE OF ONE COLOUR STILL GETS A CHOICE. Hail Mary's wide frame is
  // red throughout; its hand-made accent is the neighbouring amber, which is
  // what a designer reaches for. So: the warm and cool neighbours, then the
  // opposite — offered after anything the picture itself contains.
  for (const d of [50, -50, 180]) {
    if (out.length >= 3) break
    const h = (out[0][2] + d + 360) % 360
    if (out.every((o) => hueGap(o[2], h) > 28)) out.push([out[0][0], Math.max(out[0][1], 0.1), h])
  }
  return out
}

const hueGap = (x: number, y: number) => {
  const d = Math.abs(x - y) % 360
  return d > 180 ? 360 - d : d
}
/** move hue `h` up to `max` degrees towards `toward` */
const nudge = (h: number, toward: number, max: number) => {
  let d = ((toward - h + 540) % 360) - 180
  d = clamp(d * 0.15, -max, max)
  return (h + d + 360) % 360
}

export interface PictureTheme {
  scheme: Scheme
  backdrop: Backdrop
  wide: Record<string, string>
  tall: Record<string, string>
  swatch: [string, string, string]
  /** the contrast the faint text actually gets over the worst pixel */
  measured: { wide: number; tall: number; rail: number }
  /** the weakest veil reading allows; the Strength setting sits above it */
  floor: number
  /** the reading veil's average strength, for drawing a small card of it */
  veil: number
}

export function makeTheme(a: Analysis, o: Options, images: { wide: string; tall: string }): PictureTheme {
  const dark = o.scheme === 'dark'
  const g = a.clusters[0].lch
  const acc = accents(a)[Math.min(o.accent, accents(a).length - 1)]
  const gh = g[2]
  const gc = Math.min(g[1], dark ? 0.035 : 0.018)

  const ground = lch(dark ? 0.18 : 0.965, gc, gh)
  const deeper = lch(dark ? 0.15 : 0.93, gc, gh)
  const deep = lch(dark ? 0.21 : 0.9, gc, gh)
  const raised = lch(dark ? 0.23 : 0.99, gc * 0.6, gh)
  const text = lch(dark ? 0.955 : 0.24, 0.012, gh)
  const dim = lch(dark ? 0.86 : 0.4, 0.016, gh)
  const faint = lch(dark ? 0.8 : 0.46, 0.02, gh)

  const aC = clamp(acc[1], 0.09, 0.16)
  const accent = lch(dark ? 0.8 : 0.47, aC, acc[2])
  const accentInk = lch(dark ? 0.86 : 0.41, aC, acc[2])

  // STATUS IS NEVER THE PICTURE'S. Green, red and amber stay what they are;
  // they only lean a few degrees towards the ground so they sit in it.
  const attH = hueGap(acc[2], 60) < 25 ? 28 : 55
  const live = lch(dark ? 0.8 : 0.46, 0.13, nudge(148, gh, 10))
  const fail = lch(dark ? 0.72 : 0.46, 0.15, nudge(25, gh, 6))
  const attention = lch(dark ? 0.76 : 0.48, 0.14, nudge(attH, gh, 8))
  const who = [0, 1, 2, 3, 4, 5].map((i) => hex(lch(dark ? 0.78 : 0.48, 0.11, (acc[2] + 30 + i * 60) % 360)))

  // THE VEILS, held to the words. 4.6 for the faintest text over the worst
  // pixel: a hair above AA's 4.5, so rounding never lands under it.
  const TARGET = 4.6
  const wide = placeWide(a)
  const readFloor = veilFor(ground, faint, worstIn(a, wide.reading, dark), TARGET)
  // THE READING VEIL FOLLOWS THE PICTURE. The column is cut into bands
  // across the screen (0.26–0.84 of its width: from the rail's edge to past
  // the last word at any pane layout), each measured on its own and each
  // given the veil ITS worst pixel needs. Each band takes the strongest of
  // itself and its neighbours, so the straight line the browser draws
  // between two band centres never dips under either band's need.
  const BANDS = 6, L0 = 0.26, L1 = 0.84
  const bw = (L1 - L0) / BANDS
  const need = Array.from({ length: BANDS }, (_, i) =>
    veilFor(ground, faint, worstIn(a, wide.span(L0 + (i - 0.5) * bw, L0 + (i + 1.5) * bw), dark), TARGET))
  const held = need.map((n, i) => Math.max(n, need[i - 1] ?? 0, need[i + 1] ?? 0))
  const railFloor = veilFor(ground, faint, worstIn(a, wide.rail, dark), TARGET)
  const crop = tallCrop(a, o.focus)
  const tallFloor = veilFor(ground, faint, worstIn(a, crop, dark), TARGET)
  const lift = { picture: 0, balanced: 0.35, reading: 0.65 }[o.strength]
  const up = (f: number) => Math.min(0.97, f + (0.95 - f) * lift)
  const railA = up(railFloor), tallA = up(tallFloor)
  const bandA = held.map(up)

  const common: Record<string, string> = {
    '--canvas': hex(ground),
    '--canvas-ink': hex(text),
    '--canvas-image-opacity': '1',
    '--canvas-drift': '0',
    '--reading-blur': 'none',
    '--surface': hex(ground),
    '--surface-sunken': rgba(deeper, 0.55),
    '--surface-deep': rgba(deep, 0.58),
    '--surface-raised': rgba(raised, 0.94),
    '--raised': rgba(raised, 0.92),
    '--on-canvas': rgba(ground, 0.84),
    '--on-canvas-blur': '12px',
    '--text': hex(text),
    '--text-dim': hex(dim),
    '--text-faint': hex(faint),
    '--line': rgba(text, 0.15),
    '--line-strong': rgba(text, 0.38),
    '--wash': rgba(text, dark ? 0.07 : 0.045),
    '--wash-strong': rgba(text, dark ? 0.13 : 0.08),
    '--selection': rgba(accent, 0.24),
    '--accent': hex(accent),
    '--accent-ink': hex(accentInk),
    '--accent-soft': rgba(accent, 0.2),
    '--accent-wash': rgba(accent, 0.14),
    '--attention': hex(attention),
    '--attention-soft': rgba(attention, 0.18),
    '--live': hex(live),
    '--live-soft': rgba(live, 0.18),
    '--ok': hex(live),
    '--fail': hex(fail),
    '--edge': rgba(accent, 0.3),
    '--who-tint': hex(deeper),
    ...Object.fromEntries(who.map((c, i) => [`--who-${i + 1}`, c])),
  }

  // PLAIN: THE COLOURS WITHOUT THE PICTURE. No image, no veils, and every
  // surface opaque again — translucency is there to let a picture through,
  // and over a plain ground it would only muddy it. The words are held to
  // the ground alone, which every scheme here clears by a wide margin.
  if (o.backdrop === 'plain') {
    const plain: Record<string, string> = {
      ...common,
      '--surface-sunken': hex(deeper),
      '--surface-deep': hex(deep),
      '--surface-raised': hex(raised),
      '--raised': hex(raised),
      '--on-canvas': hex(ground),
      '--on-canvas-blur': '0px',
      '--canvas-image': 'none',
      '--canvas-veil': 'none',
      '--reading-veil': 'none',
      '--reading-fade': 'none',
    }
    const onGround = contrast(faint, ground)
    return {
      scheme: o.scheme,
      backdrop: 'plain',
      floor: 0,
      veil: 0,
      measured: { wide: onGround, rail: onGround, tall: onGround },
      swatch: [hex(ground), hex(a.clusters[0].rgb), hex(accent)],
      wide: plain,
      tall: { '--canvas-image': 'none', '--canvas-veil': 'none', '--reading-veil': 'none', '--reading-fade': 'none' },
    }
  }

  return {
    scheme: o.scheme,
    backdrop: 'picture',
    floor: readFloor,
    veil: bandA.reduce((x, y) => x + y, 0) / bandA.length,
    measured: {
      wide: Math.min(...bandA.map((v, i) =>
        contrast(faint, over(ground, v, worstIn(a, wide.span(L0 + i * bw, L0 + (i + 1) * bw), dark))))),
      rail: contrast(faint, over(ground, railA, worstIn(a, wide.rail, dark))),
      tall: contrast(faint, over(ground, tallA, worstIn(a, crop, dark))),
    },
    swatch: [hex(ground), hex(a.clusters[0].rgb), hex(accent)],
    wide: {
      ...common,
      '--canvas-image': `url('${images.wide}')`,
      '--canvas-image-position': wide.position,
      '--canvas-veil':
        `linear-gradient(90deg, ${rgba(ground, railA)} 0, ${rgba(ground, railA)} 440px, ${rgba(ground, 0)} 580px), ` +
        `linear-gradient(180deg, ${rgba(ground, 0.08)} 0%, ${rgba(ground, 0.3)} 100%)`,
      // Stops are in the SCREEN's width (fixed attachment), because that is
      // what the bands were measured in; the column's own width varies with
      // which panes are open.
      '--reading-veil':
        `linear-gradient(90deg, ${bandA.map((v, i) => `${rgba(ground, v)} ${((L0 + (i + 0.5) * bw) * 100).toFixed(1)}vw`).join(', ')}) fixed`,
      '--reading-fade': 'none',
    },
    tall: {
      '--canvas-image': `url('${images.tall}')`,
      '--canvas-image-position': 'center center',
      '--canvas-veil': `linear-gradient(180deg, ${rgba(ground, 0.06)} 0%, ${rgba(ground, 0.26)} 100%)`,
      '--reading-veil': `linear-gradient(90deg, ${rgba(ground, tallA)} 0%, ${rgba(ground, tallA)} 100%)`,
      '--reading-fade': 'none',
    },
  }
}

// -- a name a person would say --------------------------------------------

function colourWord([L, C, h]: LCh): string {
  if (C < 0.03) return L < 0.3 ? 'charcoal' : L > 0.8 ? 'ivory' : 'grey'
  const dark = L < 0.45
  const bands: [number, string, string][] = [
    [20, 'rose', 'wine'], [45, 'red', 'maroon'], [70, 'amber', 'rust'], [105, 'gold', 'olive'],
    [160, 'green', 'forest'], [200, 'teal', 'deep teal'], [265, 'blue', 'navy'],
    [320, 'violet', 'plum'], [361, 'rose', 'wine'],
  ]
  const b = bands.find(([top]) => h < top)!
  return dark ? b[2] : b[1]
}

/** A name for the version actually chosen: its ground, its highlight, and
 *  whether it is only the picture's colours -- so two looks made from one
 *  picture do not both come out "Maroon and red". */
export function nameFor(a: Analysis, o?: Pick<Options, 'accent' | 'backdrop' | 'scheme'>): string {
  const ground = colourWord(a.clusters[0].lch)
  const list = accents(a)
  const acc = colourWord(list[Math.min(o?.accent ?? 0, list.length - 1)])
  const words = ground === acc ? [ground] : [ground, acc]
  let s = words.join(' and ')
  if (o?.scheme === 'light') s = 'pale ' + s
  if (o?.backdrop === 'plain') s += ', plain'
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// -- the files a theme keeps ----------------------------------------------

/** The two pictures a theme keeps: the wide one, no bigger than a large
 *  screen needs, and the phone crop. JPEG, so a theme is ~0.5MB not ~10. */
export async function renderImages(img: HTMLImageElement | ImageBitmap, a: Analysis, focus = a.focus) {
  const enc = (w: number, h: number, draw: (c: CanvasRenderingContext2D) => void) =>
    new Promise<Blob>((res) => {
      const cv = document.createElement('canvas')
      cv.width = w
      cv.height = h
      draw(cv.getContext('2d')!)
      cv.toBlob((b) => res(b!), 'image/jpeg', 0.84)
    })
  const k = Math.min(1, 2400 / img.width)
  const wide = await enc(Math.round(img.width * k), Math.round(img.height * k), (c) =>
    c.drawImage(img, 0, 0, Math.round(img.width * k), Math.round(img.height * k)))
  const r = tallCrop(a, focus)
  const sw = (r.x1 - r.x0) * img.width, sh = (r.y1 - r.y0) * img.height
  const tk = Math.min(1, 1600 / sh)
  const tall = await enc(Math.round(sw * tk), Math.round(sh * tk), (c) =>
    c.drawImage(img, r.x0 * img.width, r.y0 * img.height, sw, sh, 0, 0, Math.round(sw * tk), Math.round(sh * tk)))
  return { wide, tall }
}
