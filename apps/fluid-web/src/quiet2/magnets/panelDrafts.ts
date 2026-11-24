/** H5's draft slots: the words the owner has typed in the panels but not saved.
 *
 *  Five slots live here, and nothing may clobber another (§5-H5-8): the
 *  new-question draft, one revision draft **per Perspective**, one rename draft
 *  per Perspective, and the staged settings. The fifth, H2's message draft, is
 *  not here on purpose -- it belongs to `conversation.ts`, and no helper in this
 *  file reads or writes it, so neither Cancel nor Escape in the panels can
 *  touch it.
 *
 *  Each slot survives tab switches, lens switches, overlay changes and a
 *  reload: the writes go to device storage under the Magnet's own key, keyed by
 *  Brain instance exactly as the composer's hold is, so another Brain or
 *  another Magnet never sees them.
 *
 *  Nothing durable lives here. Staged settings are a device-side copy of what
 *  the owner is editing; the saved configuration is the Brain's. */
import { page } from '../../brainBinding'
import type { MagnetSource } from '../../fluid/surface/magnet/types'
import type { MagnetResource } from './contract'

/** The settings overlay's staged copy: taken on open, committed by Save,
 *  discarded by Cancel, kept by Escape. */
export interface StagedSettings {
  sources: MagnetSource[]
  types: string[]
  after: string
  before: string
  manual: boolean
}
export interface PanelDrafts {
  /** The question-first creation draft. One per Magnet. */
  question: string
  /** The reason offered with a lifecycle action. One per Magnet. */
  reason: string
  /** One revision draft per Perspective, by its Topic reference. */
  revisions: Record<string, string>
  /** One rename draft per Perspective, by its Topic reference. */
  renames: Record<string, string>
  /** The staged settings, or null when nothing is staged. */
  settings: StagedSettings | null
  /** Raised by a committed save, consumed once by the overlay's return. */
  returned: number
}
/** A Magnet, named the way both panels can name it without the frame's help:
 *  `CollectionConfiguration` is given its Magnet and Brain, not its resource. */
export interface PanelAt { brainKey: string; magnet: string }

export const EMPTY: PanelDrafts = { question: '', reason: '', revisions: {}, renames: {}, settings: null, returned: 0 }
const LIMIT = 65536
const HELD_LIMIT = 300000

export const panelAt = (resource: MagnetResource): PanelAt => ({ brainKey: resource.brainKey, magnet: resource.saved.id })
export const panelKey = (at: PanelAt): string => `${at.brainKey}::${page.bound() ?? 'unbound'}::${at.magnet}`
const storageKey = (key: string) => `mentis-magnet-panels-v1:${key}`
const persistent = (key: string) => !key.includes('::unbound::')

const held = new Map<string, PanelDrafts>()
const listeners = new Map<string, Set<() => void>>()

const words = (v: unknown): string | null => typeof v === 'string' && v.length <= LIMIT ? v : null
const slots = (v: unknown): Record<string, string> => {
  const out: Record<string, string> = {}
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    for (const [topic, text] of Object.entries(v as Record<string, unknown>)) {
      if (/^ent-[a-zA-Z0-9]{6,40}$/.test(topic) && words(text) !== null) out[topic] = text as string
    }
  }
  return out
}
const sourceOf = (v: unknown): MagnetSource | null => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  const o = v as Record<string, unknown>
  if (o.kind === 'conversation' && typeof o.conversation === 'string') return { kind: 'conversation', conversation: o.conversation }
  if (o.kind === 'file' && typeof o.collection === 'string')
    return { kind: 'file', collection: o.collection, ...(typeof o.path === 'string' ? { path: o.path } : {}) } as MagnetSource
  return null
}
const stagedOf = (v: unknown): StagedSettings | null => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  const o = v as Record<string, unknown>
  if (!Array.isArray(o.sources) || !Array.isArray(o.types)) return null
  const sources = o.sources.map(sourceOf).filter((s): s is MagnetSource => !!s).slice(0, 20)
  if (sources.length !== o.sources.length) return null   // A half-read selection is never staged.
  return { sources, types: o.types.filter((t): t is string => typeof t === 'string').slice(0, 8),
    after: words(o.after) ?? '', before: words(o.before) ?? '', manual: o.manual === true }
}

/** The page's own copy, read from device storage the first time it is asked for. */
export function panelDrafts(at: PanelAt): PanelDrafts {
  const key = panelKey(at)
  const memory = held.get(key)
  if (memory) return memory
  let drafts = EMPTY
  try {
    const raw = persistent(key) ? globalThis.localStorage?.getItem(storageKey(key)) : null
    const v = raw && raw.length <= HELD_LIMIT ? JSON.parse(raw) as Record<string, unknown> : null
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      drafts = { question: words(v.question) ?? '', reason: words(v.reason) ?? '',
        revisions: slots(v.revisions), renames: slots(v.renames), settings: stagedOf(v.settings), returned: 0 }
    }
  } catch { /* Unreadable device storage leaves the panels working, with nothing staged. */ }
  held.set(key, drafts)
  return drafts
}

function put(at: PanelAt, change: Partial<PanelDrafts>) {
  const key = panelKey(at)
  const next: PanelDrafts = { ...panelDrafts(at), ...change }
  held.set(key, next)
  try {
    if (persistent(key)) {
      const empty = !next.question && !next.reason && !next.settings
        && !Object.keys(next.revisions).length && !Object.keys(next.renames).length
      if (empty) globalThis.localStorage?.removeItem(storageKey(key))
      else globalThis.localStorage?.setItem(storageKey(key), JSON.stringify({
        question: next.question, reason: next.reason, revisions: next.revisions, renames: next.renames, settings: next.settings }))
    }
  } catch { /* The in-page copy still holds the words until this page goes away. */ }
  listeners.get(key)?.forEach((fn) => fn())
}

export const subscribePanelDrafts = (at: PanelAt, changed: () => void): () => void => {
  const key = panelKey(at), set = listeners.get(key) ?? new Set<() => void>()
  listeners.set(key, set); set.add(changed)
  return () => { set.delete(changed); if (!set.size) listeners.delete(key) }
}

/** Drop the page's in-memory copy. The next read comes from device storage, as
 *  it does after a reload; nothing is discarded. */
export const forgetPanelDrafts = (at?: PanelAt) => { if (at) held.delete(panelKey(at)); else held.clear() }

export const setQuestionDraft = (at: PanelAt, question: string) => put(at, { question: question.slice(0, LIMIT) })
export const setReasonDraft = (at: PanelAt, reason: string) => put(at, { reason: reason.slice(0, LIMIT) })
export const clearQuestionDraft = (at: PanelAt) => put(at, { question: '' })

export const revisionDraft = (at: PanelAt, topic: string): string | undefined => panelDrafts(at).revisions[topic]
export const setRevisionDraft = (at: PanelAt, topic: string, text: string) =>
  put(at, { revisions: { ...panelDrafts(at).revisions, [topic]: text.slice(0, LIMIT) } })
export const clearRevisionDraft = (at: PanelAt, topic: string) => {
  const { [topic]: _gone, ...rest } = panelDrafts(at).revisions
  put(at, { revisions: rest })
}
export const renameDraft = (at: PanelAt, topic: string): string | undefined => panelDrafts(at).renames[topic]
export const setRenameDraft = (at: PanelAt, topic: string, text: string) =>
  put(at, { renames: { ...panelDrafts(at).renames, [topic]: text.slice(0, LIMIT) } })
export const clearRenameDraft = (at: PanelAt, topic: string) => {
  const { [topic]: _gone, ...rest } = panelDrafts(at).renames
  put(at, { renames: rest })
}

export const stagedSettings = (at: PanelAt): StagedSettings | null => panelDrafts(at).settings
export const stageSettings = (at: PanelAt, settings: StagedSettings) => put(at, { settings })
/** Cancel: the staged copy goes entirely, and nothing else is touched. */
export const discardStagedSettings = (at: PanelAt) => put(at, { settings: null })

/** A committed save asks the overlay to return by `settingsReturn`. The panel
 *  that saves is given its Magnet, not the frame, so it says so here and the
 *  overlay -- which has the resource -- does the returning. */
export const requestSettingsReturn = (at: PanelAt) => put(at, { settings: null, returned: panelDrafts(at).returned + 1 })
export function takeSettingsReturn(at: PanelAt): boolean {
  const drafts = panelDrafts(at)
  if (!drafts.returned) return false
  put(at, { returned: 0 })
  return true
}
