import type { PostObjectEntry } from '../store'

export type FloatContent = 'visual' | 'image' | 'compact' | 'text' | 'wide' | 'other'
export interface FloatMeasure { kind: FloatContent; w?: number; h?: number; aspect?: number }
export interface FloatRoom { w: number; h: number }

const clamp = (n: number, low: number, high: number) => Math.max(low, Math.min(n, high))

/** The broad shape a new surface needs. The renderer still decides its
 *  compact/medium/large presentation once it has this room. */
export function floatContentOf(o?: PostObjectEntry | null): FloatContent {
  if (!o) return 'other'
  const word = `${o.kind} ${o.type} ${o.is?.word ?? ''}`.toLowerCase()
  if (/chart|diagram|timeline|graph|map/.test(word)) return 'visual'
  if (/image|photo|figure/.test(word)) return 'image'
  if (/table|code|spreadsheet|grid/.test(word)) return 'wide'
  if (/timer|form|poll|status/.test(word)) return 'compact'
  if (o.kind === 'post-text' || /document|text|markdown|note/.test(word)) return 'text'
  return 'other'
}

/** An initial float rectangle from measured content and the room it may use.
 *  It is intentionally a one-shot calculation: later resizes are the
 *  owner's and travel/docking code carries the stored rectangle unchanged. */
export function fitFloat(measured: FloatMeasure, room: FloatRoom, at = { x: 40, y: 40 }) {
  const margin = 12
  const maxW = Math.max(220, room.w - margin * 2)
  const maxH = Math.max(120, room.h - margin * 2)
  const naturalW = measured.w && measured.w > 0 ? measured.w + 32 : 0
  const naturalH = measured.h && measured.h > 0 ? measured.h + 54 : 0
  let w: number, h: number
  if (measured.kind === 'image') {
    const aspect = measured.aspect && measured.aspect > 0 ? measured.aspect
      : naturalW && naturalH ? naturalW / naturalH : 4 / 3
    w = clamp(naturalW || 560, 300, 720)
    h = w / aspect + 42
    if (h > maxH) { h = maxH; w = Math.max(220, (h - 42) * aspect) }
  } else if (measured.kind === 'visual') {
    w = Math.max(620, naturalW); h = Math.max(420, naturalH)
  } else if (measured.kind === 'wide') {
    w = Math.max(680, naturalW); h = Math.max(360, naturalH)
  } else if (measured.kind === 'compact') {
    w = Math.max(280, Math.min(380, naturalW || 320)); h = Math.max(170, Math.min(300, naturalH || 220))
  } else if (measured.kind === 'text') {
    w = Math.max(560, Math.min(680, naturalW || 640)); h = Math.max(320, Math.min(560, naturalH || 480))
  } else {
    w = Math.max(380, Math.min(560, naturalW || 440)); h = Math.max(260, Math.min(480, naturalH || 340))
  }
  w = Math.min(w, maxW); h = Math.min(h, maxH)
  return { x: clamp(at.x, margin, Math.max(margin, room.w - w - margin)), y: clamp(at.y, margin, Math.max(margin, room.h - h - margin)), w, h }
}

/** Read the same rendered content the zone's Fit action reads, including an
 *  image's intrinsic aspect ratio when it is available. */
export function measureFloat(el: HTMLElement | null, kind: FloatContent): FloatMeasure {
  const body = el?.querySelector<HTMLElement>('[data-fit-body], .zb-in, .wk-zbody') ?? el
  const image = body?.querySelector<HTMLImageElement>('img')
  return {
    kind,
    ...(body ? { w: Math.max(body.scrollWidth, body.offsetWidth), h: Math.max(body.scrollHeight, body.offsetHeight) } : {}),
    ...(image?.naturalWidth && image.naturalHeight ? { aspect: image.naturalWidth / image.naturalHeight } : {}),
  }
}
