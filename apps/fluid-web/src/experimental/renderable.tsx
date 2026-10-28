import { Component, createContext, useContext, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { Prose, blocksAt, blocksOf } from '../prose'
import { Glyph } from '../bits'
import Pop from '../pop'
import type { Help, MenuGroup, TypeDef } from './api'
import { TYPES } from './types'
import { Gallery } from './gallery'
import { readBlock, sourceOf, type RBlock, type Reading } from './spec/core'
import { keyOf, namesFor, type Names } from './objects'
import { ExpandContext, posted, type Expander, type ExpandTarget } from '../expandHook'
import { ExpandItems } from '../ExpandMenu'
import type { Size } from './spec/api'
import { durableState, isDurable } from './answers'

/* ------------------------------------------------------------------------ *
 * EXPERIMENTAL: MARKED MARKDOWN BLOCKS.
 *
 * The owner's experiment, in the conversation so it can be tried in ordinary
 * use. Neither the syntax nor the architecture is decided; this is here to be
 * judged. Started as a port of experiments/renderable_viewer/index.html
 * (itself from experiments/renderable_blocks/contract.py); the RICHNESS
 * experiment added the TypeDef registry (./api.ts, ./types/*) and the
 * gallery (./gallery.tsx), reachable only by opening Mentis at ?renderers (the owner asked for no button).
 *
 * Everything experimental lives in ui/src/experimental/. The hooks elsewhere
 * are: the code-fence case in prose.tsx, the `scope` passed by RichTurn and
 * the composer preview, <PinDock/> in App.tsx, and the handoff listener in
 * Composer.tsx. Remove those and this directory and it is gone.
 *
 * Real: parsing, validation, drawing from declared attributes only, the
 * degraded text forms, every interaction, state kept apart from the Markdown.
 * A FORM, CHECKLIST, EDITABLE TABLE OR PAD IN A POST WITH A UNIQUE name= is
 * kept by Mentis (./answers.ts, forms build P5a-P5c): its answers last, carry
 * who gave them, take the person's own words, and Done and Send back hand
 * them over through the server. For everything else:
 * Not real: state lasts only as long as the browser tab; block identity is
 * positional inside its scope (the scope of a posted block is its originating
 * Turn and text part: turnPartScope); a declared source scope is displayed and never
 * resolved or enforced; images are mock drawings, never generated or
 * retrieved; "Send back to agent" only puts a draft in the composer, which the
 * owner posts or not.
 * ------------------------------------------------------------------------ */

export { RENDERABLE } from './spec'
export { sourceOf, type Diag, type RBlock } from './spec/core'

export { NAME, parseInfo, SHARED, SIZES } from './spec/core'
export type { Shared, Size } from './spec/api'

export interface Analysis extends Omit<Reading, 'spec'> {
  def: TypeDef
}

/** Validation in plain language (./spec/core.ts), with the type's drawing
 *  beside it. The shared attributes (name, open, sizes, prefer, page) are
 *  read there too, so the conversation, the Workspace Lab and the server's
 *  render check read them the same way. */
export function analyse(b: RBlock): Analysis {
  const { spec: _spec, ...r } = readBlock(b)
  return { def: TYPES[b.type], ...r }
}

/* ---- state, held apart from the Markdown, for the life of this tab. ---- */

/** A block's state as its readable text and handoff read it: what Mentis
 *  keeps for a saved form, else what this tab holds. */
export const heldFor = (key: string): unknown => {
  const kept = durableState(key)
  const tab = store.held[key]
  /* A kept table still holds its view (sort, filter, selection) in the tab. */
  return kept ? (tab && typeof tab === 'object' ? { ...tab, ...kept } : kept) : tab
}

/** `names`: the Turn part's name table, so a pinned panel keys its children
 *  as the post does. */
export interface Pin { key: string; block: RBlock; where: string; names?: Names }
export const store = {
  held: {} as Record<string, unknown>,
  view: {} as Record<string, 'rendered' | 'degraded' | 'source'>,
  pins: [] as Pin[],
  open: true,
  /* The handoff dialog lives with the dock, not the block: placing the text
     closes the composer preview, which would take a block-owned dialog with it. */
  sending: null as string | null,
  gallery: typeof window !== 'undefined' && /(^|[?&])renderers\b/.test(window.location.search),
  v: 0,
}
const listeners = new Set<() => void>()
export const changed = () => { store.v++; listeners.forEach((f) => f()) }
const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f) } }
export const useStore = () => useSyncExternalStore(subscribe, () => store.v)

/* ---- where a posted block comes from (I1). ----
   A block in a posted Turn is keyed by the Turn it was WRITTEN in and the
   index of its text part in that Turn's `parts`, never by where it happens to
   be shown. One rule, so the same Turn's block is one block wherever it is
   drawn -- at home, linked into another Conversation, in a thread rail or
   focus, pinned -- and two different Turns, or two text parts of one Turn,
   never share a key however alike their words are. The first part keeps the
   bare form ("Turn ent-…") that home Turns have always used. Within that
   scope a block is still identified by its position (type#n); that, and what
   an edit does to it, is the identity question I2 specifies, not this. */
export { turnPartScope } from './objects'

/* ---- nesting (composition) and the helpers lent to types. ---- */

/** Every marked block in `src`, keyed exactly as <Prose scope=… names=…> keys
 *  them: by name where the name is unambiguous in the Turn part, by position
 *  otherwise. Without `names`, `src` is the top of its own Turn part. */
export function markedIn(src: string, scope: string, names: Names = namesFor(src, scope)): { block: RBlock; key: string }[] {
  const seen: Record<string, number> = {}
  const out: { block: RBlock; key: string }[] = []
  for (const b of blocksOf(src)) {
    if (b.kind !== 'code' || b.info === undefined || !b.lang) continue
    const n = (seen[b.lang] = (seen[b.lang] ?? -1) + 1)
    const block = { type: b.lang, info: b.info, body: b.text, closed: b.closed ?? true }
    out.push({ block, key: keyOf(scope, b.lang, n, nameOf(block, names), names) })
  }
  return out
}

/** The name a block declares, read only when there is a table to use it. */
export const nameOf = (block: RBlock, names?: Names) => (names && names.table.counts.size ? analyse(block).shared.name : null)

/* ONE COMPONENT PER NAME TABLE, so a container's children are the same
   children every time it is drawn. Made afresh on each draw, `Nested` was a
   new component type each time, and React remounted everything inside the
   container whenever it was redrawn -- closing a ⋯ open on a nested block
   and dropping any state its drawing held. Same table, same component. */
const nestedKept = new Map<string, { table: Names['table'] | undefined; C: Help['Nested'] }>()
function nestedFor(down?: Names): Help['Nested'] {
  const k = down?.root ?? ''
  const hit = nestedKept.get(k)
  if (hit && hit.table === down?.table) return hit.C
  const C: Help['Nested'] = ({ src, scope }) => <Prose src={src} scope={scope} names={down} />
  if (nestedKept.size > 400) nestedKept.delete(nestedKept.keys().next().value as string)
  nestedKept.set(k, { table: down?.table, C })
  return C
}

/** The helpers lent to block `b`. Its Turn part's `names` are handed down
 *  only by a panel: names are counted through panels, so only a panel's
 *  children are in that table. Anything else that draws Markdown starts a
 *  table of its own under its own key. */
export function helpFor(b: RBlock, key: string, where: string, names?: Names): Help {
  const down = b.type === 'panel' ? names : undefined
  const nested = (src: string, scope: string) => {
    const n = down ?? namesFor(src, scope)
    return markedIn(src, scope, n).map((x) => ({ ...x, names: n }))
  }
  return {
    key,
    where,
    Nested: nestedFor(down),
    nestedReadable: (src, scope) => nested(src, scope).map((x) => readableOf(x.block, x.key, where, 'part of a composite', x.names)).join('\n\n'),
    nestedText: (src, scope) => {
      const lines = src.replace(/\r\n?/g, '\n').split('\n')
      const parts = nested(src, scope)
      let i = 0
      return blocksAt(src).map((x) => {
        if (x.kind !== 'code' || x.info === undefined || !x.lang) return lines.slice(x.line, x.end).join('\n').trim()
        const p = parts[i++]
        return readableOf(p.block, p.key, where, 'part of a composite', p.names)
      }).filter(Boolean).join('\n\n')
    },
    nestedHandoff: (src, scope) => nested(src, scope).map((x) => payloadOf(x.block, x.key, where, x.names)),
  }
}

/** The full degraded form: a status line, then the type's readable text. */
export function readableOf(b: RBlock, key: string, where: string, reason: string, names?: Names) {
  const a = analyse(b)
  if (!a.ok)
    return [`[${b.type} -- not shown: the block does not meet its contract]`, 'problems:',
      ...a.d.map((x) => `- ${x.sev} (${x.where}): ${x.msg}`), 'source, exactly as written:', sourceOf(b)].join('\n')
  let body: string
  try {
    body = a.def.readable(a.data, a.attrs, heldFor(key), helpFor(b, key, where, names))
  } catch (e) {
    body = `(the ${b.type} readable form failed: ${(e as Error).message})\nsource, exactly as written:\n${sourceOf(b)}`
  }
  const extra = Object.keys(a.extra).length
    ? '\nother attributes (not in the contract, kept, not used): ' + Object.entries(a.extra).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' ')
    : ''
  return `[${b.type} v1 -- ${reason}]\n${body}${extra}`
}

/** What "Send back to agent" would hand over. */
export function payloadOf(b: RBlock, key: string, where: string, names?: Names): Record<string, unknown> {
  const a = analyse(b)
  const p: Record<string, unknown> = {
    experimental: 'marked-markdown handoff (draft only; posting is your choice)',
    block_key: key,
    type: b.type,
    where,
    source_markdown: sourceOf(b),
    contract_problems: a.d.map((x) => `${x.sev}: (${x.where}) ${x.msg}`),
    current_state: heldFor(key) ?? null,
    rendered: a.ok,
  }
  if (a.attrs.source)
    p.declared_scope = { source: a.attrs.source, refs: a.attrs.refs ?? null, resolved: false, enforced: false }
  if (a.ok && a.def.handoff) {
    try { Object.assign(p, a.def.handoff(a.data, a.attrs, heldFor(key), helpFor(b, key, where, names))) }
    catch (e) { p.handoff_error = (e as Error).message }
  }
  return p
}

export function handoffText(b: RBlock, key: string, where: string, names?: Names) {
  const a = analyse(b)
  const title = a.attrs.title ? ` “${a.attrs.title}”` : ''
  return `Handing back the ${b.type}${title} as it stands now:\n\n\`\`\`json\n${JSON.stringify(payloadOf(b, key, where, names), null, 2)}\n\`\`\`\n`
}

/* ---- "Send back to agent": a draft in the composer, never a post. ---- */

export const HANDOFF_EVENT = 'mentis:experimental-handoff'
/** Every open composer offers itself; the one most recently focused takes it. */
export interface HandoffDetail {
  text: string
  offers: { focusedAt: number; take: (text: string) => void }[]
}

export function placeInComposer(text: string): boolean {
  const detail: HandoffDetail = { text, offers: [] }
  window.dispatchEvent(new CustomEvent(HANDOFF_EVENT, { detail }))
  const best = detail.offers.sort((x, y) => y.focusedAt - x.focusedAt)[0]
  best?.take(text)
  return !!best
}

function SendDialog({ text, onClose }: { text: string; onClose: () => void }) {
  const [result, setResult] = useState<'none' | 'placed' | 'no-composer'>('none')
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="rb-modal" role="dialog" aria-modal="true" aria-label="Send back to agent" onClick={onClose}>
      <div className="rb-modal-box" onClick={(e) => e.stopPropagation()}>
        <p>
          <b>Nothing has been sent.</b> This is what would be handed back. <b>Put it in the composer</b> adds it to
          your draft. You choose whether to post it and to whom. Nothing is written to durable knowledge unless you post.
        </p>
        <pre className="rb-pre">{text}</pre>
        {result === 'placed' && <p className="rb-ok">Added to the composer draft. It has not been posted.</p>}
        {result === 'no-composer' && (
          <p className="rb-bad">There's no composer open on this screen, so nothing was placed. Open a conversation, then try again.</p>
        )}
        <div className="rb-row">
          <button
            className="btn primary"
            disabled={result === 'placed'}
            onClick={() => {
              const ok = placeInComposer(text)
              if (ok) store.gallery = false
              setResult(ok ? 'placed' : 'no-composer')
              changed()
            }}
          >
            Put it in the composer
          </button>
          <button className="btn" onClick={() => navigator.clipboard?.writeText(text)}>Copy</button>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

/* ---- the contextual ⋯ menu: every secondary action, none of them on the page ---- */

const VIEW_NAME = { rendered: 'Rendered', degraded: 'Readable text', source: 'Markdown source' } as const

/* Material that is referenced from elsewhere, or that takes your input, keeps
   a quiet rule beside it at rest so it is not mistaken for the post's own
   prose. Everything else reads as part of the post until hovered or focused.
   Presentation only: one shared treatment, never a frame per kind. */
const MARKED_AT_REST: ReadonlySet<string> = new Set(['checklist', 'ref', 'problems', 'helper', 'image', 'gallery', 'review', 'compare', 'form', 'pad', 'table', 'whiteboard'])

/** What the drawing on screen offers in its block's ⋯. A drawing says so on
 *  every render; an offer lasts only as long as the drawing that made it. When
 *  the surface draws something else (another kind, another view, an invalid
 *  block) or the drawing fails, what it offered is withdrawn, so no entry can
 *  act for content that is no longer there. */
class Offer {
  groups: MenuGroup[] = []
  /** The drawing this surface's current pass draws (null: none), and whether it has said anything yet. */
  from: unknown = null
  said = false
  v = 0
  private seen = new Set<() => void>()
  private due = false
  say = (g: MenuGroup[]) => { this.groups = g; this.said = true; this.tell() }
  withdraw = () => { if (this.groups.length) { this.groups = []; this.tell() } }
  /** The entry offered NOW under that group and label, if any: a click acts on this, never on what was shown earlier. */
  now(group: string, label: string) { return this.groups.find((g) => g.label === group)?.items.find((it) => it.label === label) }
  watch = (f: () => void) => { this.seen.add(f); return () => { this.seen.delete(f) } }
  /* Said during render, so an open ⋯ redraws once that render is over, never during it. */
  private tell() {
    if (this.due) return
    this.due = true
    queueMicrotask(() => { this.due = false; this.v++; this.seen.forEach((f) => f()) })
  }
}

function ToolsMenu({
  block: b,
  blockKey: key,
  where,
  mode,
  view,
  pinned,
  hasState,
  onTogglePin,
  onResetState,
  label,
  offer,
  names,
  expand,
}: {
  label: string
  names?: Names
  /** Where the surface around the block lets it be expanded; then the
   *  Expand group takes the place of "Pin beside the conversation". */
  expand?: { ex: Expander; target: ExpandTarget }
  /** What the surface itself offers here, read when the menu draws. */
  offer: Offer
  block: RBlock
  blockKey: string
  where: string
  mode: 'inline' | 'pin'
  view: 'rendered' | 'degraded' | 'source'
  pinned: boolean
  hasState: boolean
  onTogglePin: () => void
  onResetState: () => void
}) {
  const [open, setOpen] = useState(false)
  useSyncExternalStore(offer.watch, () => offer.v)
  const btnRef = useRef<HTMLButtonElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const entry = useRef<'first' | 'last'>('first')
  const dismiss = () => { setOpen(false); btnRef.current?.focus() }
  useEffect(() => {
    if (!open) return
    const items = wrapRef.current?.querySelectorAll<HTMLButtonElement>('[role^="menuitem"]')
    items?.[entry.current === 'last' ? items.length - 1 : 0]?.focus()
  }, [open])

  return (
    <div ref={wrapRef} className="popwrap rb-tools-wrap">
      <button
        ref={btnRef}
        className="btn quiet glyph rb-tools-btn"
        aria-label={`More for ${label}`}
        title="More"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={(e) => {
          e.stopPropagation()
          entry.current = 'first'
          if (open) dismiss(); else setOpen(true)
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault()
            entry.current = e.key === 'ArrowUp' ? 'last' : 'first'
            setOpen(true)
          }
          if (e.key === 'Escape' && open) {
            e.stopPropagation()
            dismiss()
          }
        }}
      >
        <Glyph name="more" />
      </button>
      {open && (
        <>
          <div
            className="scrim"
            onClick={(e) => {
              e.stopPropagation()
              dismiss()
            }}
          />
          <Pop
            role="menu"
            aria-label={`More for ${label}`}
            className="rb-tools-menu"
            onKeyDown={(e) => {
              if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
                e.preventDefault()
                e.stopPropagation()
                const items = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('[role^="menuitem"]'))
                const i = items.indexOf(document.activeElement as HTMLButtonElement)
                const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1
                  : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
                items[next]?.focus()
              }
              if (e.key === 'Tab') {
                dismiss()
              }
              if (e.key === 'Escape') {
                e.preventDefault()
                e.stopPropagation()
                dismiss()
                btnRef.current?.focus()
              }
            }}
          >
            <div className="rb-tools-group" role="group" aria-label="View">
              <div className="rb-tools-lbl" aria-hidden="true">View</div>
              {(['rendered', 'degraded', 'source'] as const).map((m) => (
                <button
                  key={m}
                  tabIndex={-1}
                  role="menuitemradio"
                  aria-checked={view === m}
                  className={`btn quiet rb-tools-item${view === m ? ' active' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    store.view[key] = m
                    dismiss()
                    changed()
                  }}
                >
                  <span>{VIEW_NAME[m]}</span>
                  {view === m && <span aria-hidden="true"> ✓</span>}
                </button>
              ))}
            </div>
            {offer.groups.filter((g) => g.items.length).map((g) => (
              <div key={g.label} className="rb-tools-group" role="group" aria-label={g.label}>
                <div className="rb-tools-lbl" aria-hidden="true">{g.label}</div>
                {g.items.map((it) => (
                  <button
                    key={it.label}
                    tabIndex={-1}
                    role={it.checked === undefined ? 'menuitem' : 'menuitemradio'}
                    aria-checked={it.checked}
                    aria-disabled={it.disabled || undefined}
                    className={`btn quiet rb-tools-item${it.checked ? ' active' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      const now = offer.now(g.label, it.label)
                      if (!now || now.disabled) return
                      dismiss()
                      now.onSelect()
                    }}
                  >
                    <span>{it.label}</span>
                    {it.checked && <span aria-hidden="true"> ✓</span>}
                  </button>
                ))}
              </div>
            ))}
            {expand && <ExpandItems ex={expand.ex} target={expand.target} dismiss={dismiss} />}
            <div className="rb-tools-group" role="group" aria-label="Actions">
              <div className="rb-tools-lbl" aria-hidden="true">Actions</div>
              {/* With the workspace open, Expand takes Pin's place; a block
                  already pinned can still be unpinned. */}
              {(!expand || mode === 'pin' || pinned) && <button
                tabIndex={-1}
                role="menuitem"
                className="btn quiet rb-tools-item"
                onClick={(e) => {
                  e.stopPropagation()
                  onTogglePin()
                  dismiss()
                }}
              >
                <span>{mode === 'pin' || pinned ? 'Unpin' : 'Pin beside the conversation'}</span>
              </button>}
              {/* A form Mentis keeps hands its answers over itself, beside Done. */}
              {!isDurable(key) && <button
                tabIndex={-1}
                role="menuitem"
                className="btn quiet rb-tools-item"
                onClick={(e) => {
                  e.stopPropagation()
                  store.sending = handoffText(b, key, where, names)
                  dismiss()
                  changed()
                }}
              >
                <span>Send back to agent…</span>
              </button>}
              {hasState && (
                <button
                  tabIndex={-1}
                role="menuitem"
                  className="btn quiet rb-tools-item"
                  onClick={(e) => {
                    e.stopPropagation()
                    onResetState()
                    dismiss()
                  }}
                >
                  <span>Reset to source</span>
                </button>
              )}
            </div>
          </Pop>
        </>
      )}
    </div>
  )
}

/* ---- the rendering context: how the surface around a block shows it. ----
   The same Markdown, the same contract, drawn according to where it is
   shown. The conversation gives no host, so every block draws exactly as it
   always has: `open` is ignored and a panel's heading stays in its body. The
   Workspace Lab gives a host, and then a LABELLED block (a title, or a
   panel's leading heading) folds to its label with ▸/▾, starting as its
   `open` says, and a heading used as the label is drawn once, as the label.
   Whether a block is open is the HOST's -- the post is one host, each copy
   in a zone another -- so it is never `store` state, which every copy
   shares, and never `store.open`, which belongs to the pin dock. */
export interface RenderHost {
  /** whether the block under `key` is open in this host; `initial` is what it declares */
  isOpen(key: string, initial: boolean): boolean
  setOpen(key: string, open: boolean): void
}
export const RenderHostContext = createContext<RenderHost | null>(null)

/* ---- one surface, drawn the same way inline and pinned. ---- */

/* FOCUS SEARCH (fluid/search-in/): a block whose drawing IS its meaning -- a
   chart, a diagram, a mock picture -- has no text a reader can find in it,
   but its source does. The source's descriptive fields are written on the
   card as `data-search-text`, which search-in's walker reads only where the
   card shows no text of its own, so nothing visible is ever found twice.
   Presentation only: the block, its rendering and the registry are
   unchanged. */
const SEARCH_FIELDS = ['title', 'name', 'caption', 'alt', 'description', 'label', 'summary']
function searchTextOf(b: RBlock, a: Analysis): string | undefined {
  const parts = [b.type]
  for (const k of SEARCH_FIELDS) {
    const v = (a.attrs[k] ?? a.extra[k])?.trim()
    if (v && !parts.includes(v)) parts.push(v)
  }
  return parts.join(' — ') || undefined
}

export function RenderableBlock({ block, blockKey, where, names, size }: {
  block: RBlock; blockKey: string; where: string; names?: Names
  /** the size a workspace draws it at; the conversation gives none */
  size?: Size
}) {
  useStore()
  const pinnedIdx = store.pins.findIndex((p) => p.key === blockKey)
  /* A pin keeps a copy of the block so it survives leaving the conversation;
     while the block is on screen, the copy follows it (a draft can change). */
  useEffect(() => {
    const p = store.pins.find((x) => x.key === blockKey)
    if (p && sourceOf(p.block) !== sourceOf(block)) { p.block = block; p.names = names; changed() }
  }, [block, blockKey, names])
  return <Surface block={block} blockKey={blockKey} mode="inline" where={where} pinned={pinnedIdx >= 0} names={names} size={size} />
}

export function Surface({ block: b, blockKey: key, mode, where, pinned, bare, names, size }: {
  block: RBlock; blockKey: string; mode: 'inline' | 'pin'; where: string; pinned: boolean
  /** The gallery shows source/degraded/state beside the surface itself, so no tabs. */
  bare?: boolean
  /** its Turn part's names, so a panel keys its children as the post does */
  names?: Names
  /** handed to the drawing as RichProps.size */
  size?: Size
}) {
  const a = analyse(b)
  const help = helpFor(b, key, where, names)
  /* Folding is the host's to offer (see RenderHost); without one, never. */
  const host = useContext(RenderHostContext)
  /* Expanding likewise (expandHook): only a posted block, drawn in its post. */
  const ex = useContext(ExpandContext)
  const expand = ex && !bare && mode === 'inline' && posted(where) ? { ex, target: { kind: 'block', key, where } as ExpandTarget } : undefined
  const foldable = !!host && !bare && mode === 'inline' && !!a.shared.label
  const open = !foldable || host!.isOpen(key, a.shared.open)
  const asLabel = foldable && a.shared.labelFrom === 'heading'
  const view = bare ? 'rendered' : store.view[key] || 'rendered'
  const held = store.held[key]
  const togglePin = () => {
    store.pins = pinned ? store.pins.filter((p) => p.key !== key) : [...store.pins, { key, block: b, where, names }]
    if (!pinned) store.open = true
    changed()
  }
  const set = (s: unknown) => {
    if (s === undefined) delete store.held[key]
    else store.held[key] = s
    changed()
  }
  /* Inside a container, `where` is the container's key: positional
     (`…/panel#0`) or named (`…/@tests:panel`). */
  const isNested = where.includes('#') || where.includes('/@')
  const Rich = a.def.Rich
  /* What the drawing offers in this block's ⋯; it says so on every render.
     Another drawing (or none) inherits nothing; a pass whose drawing said
     nothing withdraws what an earlier one said. */
  const [offer] = useState(() => new Offer())
  const drawing = view === 'rendered' && a.ok ? Rich : null
  if (offer.from !== drawing) offer.withdraw()
  offer.from = drawing
  offer.said = false
  useLayoutEffect(() => { if (!offer.said) offer.withdraw() })
  const scope = a.attrs.source
  const title = a.attrs.title
  const label = title ? `“${title}”` : `this ${b.type}`
  /* Folded, the drawing that would place the ⋯ is not drawn: it stays in the head. */
  const placed = !bare && open && a.ok && view === 'rendered' && !!a.def.placesTools?.(a.data, a.attrs)
  const tools = bare ? null : (
    <ToolsMenu
      label={label}
      block={b}
      blockKey={key}
      where={where}
      mode={mode}
      view={view}
      pinned={pinned}
      hasState={held !== undefined}
      onTogglePin={togglePin}
      onResetState={() => set(undefined)}
      offer={offer}
      names={names}
      expand={expand}
    />
  )
  let rendered: React.ReactNode
  if (view === 'source') {
    rendered = <pre className="rb-pre">{sourceOf(b)}</pre>
  } else if (!a.ok) {
    rendered = (
      <div className="rb-fallback">
        <p className="rb-notice">This {b.type} can't be shown as written, so it is shown as readable text. The Markdown source is intact.</p>
        <pre className="rb-pre">{readableOf(b, key, where, 'contract validation failure', names)}</pre>
      </div>
    )
  } else if (view === 'degraded') {
    rendered = <pre className="rb-pre">{readableOf(b, key, where, 'degraded view selected by you (a real fallback looks the same)', names)}</pre>
  } else {
    rendered = (
      <Guard type={b.type} block={b} blockKey={key} where={where} names={names} tools={placed ? tools : null} onFail={offer.withdraw}>
        <Rich data={a.data} attrs={a.attrs} state={held} set={set} help={help} mode={mode} menu={offer.say} tools={placed ? tools : undefined}
          {...(asLabel ? { labelled: true } : {})} {...(size ? { size } : {})} />
      </Guard>
    )
  }
  const H = isNested ? 'h4' : 'h3'
  const errors = a.d.filter((x) => x.sev === 'error').length
  const marked = !isNested && MARKED_AT_REST.has(b.type)
  return (
    /* Clicks stay inside: the composer's preview closes on any click. */
    <section
      aria-label={title ?? b.type}
      className={'rb-card' + (isNested ? ' rb-card-nested' : '') + (a.ok ? '' : ' rb-bad-card') + (mode === 'pin' ? ' rb-card-pin' : '')
        + (marked ? ' rb-marked' : '') + (title || foldable ? '' : ' rb-untitled') + (placed ? ' rb-tools-placed' : '')
        + (a.ok && mode === 'inline' && !bare && a.def.slim?.(a.attrs) ? ' rb-card-slim' : '') + (open ? '' : ' rb-folded')}
      data-block-key={key}
      data-search-text={searchTextOf(b, a)}
      onClick={(e) => e.stopPropagation()}
    >
      {mode === 'pin' && <p className="rb-from">Pinned from {where}</p>}
      <div className="rb-head">
        {foldable ? (
          <H className="rb-title rb-fold-title">
            <button className="rb-fold" aria-expanded={open} title={open ? 'Collapse' : 'Expand'} onClick={() => host!.setOpen(key, !open)}>
              <span className="rb-fold-mark" aria-hidden="true">{open ? '▾' : '▸'}</span>
              {a.shared.label}
            </button>
            {!open && <span className="rb-fold-what">{b.type}</span>}
          </H>
        ) : title && <H className="rb-title">{title}</H>}
        {expand && (
          <button className="rb-up" aria-label={`Expand ${label} into the workspace`}
            title="Expand into the workspace: its page if it names one, else this page (drag onto a zone to choose where)"
            onPointerDown={(e) => { if (e.button === 0) expand.ex.drag(expand.target, e.nativeEvent) }}
            onClick={(e) => { e.stopPropagation(); expand.ex.quick(expand.target) }}>↗</button>
        )}
        {!placed && tools}
      </div>
      {open && <>
      {view !== 'rendered' && (
        <p className="rb-viewing">
          Showing {view === 'degraded' ? 'the readable text' : 'the Markdown source'}.{' '}
          <button className="rb-link" onClick={() => { store.view[key] = 'rendered'; changed() }}>Show rendered</button>
        </p>
      )}
      <div className="rb-body">{rendered}</div>
      {a.d.length > 0 && (
        <details className="rb-disclosure rb-diag-box">
          <summary>
            {errors
              ? `${errors === 1 ? 'One problem' : `${errors} problems`} in this block's Markdown`
              : `${a.d.length === 1 ? 'A note' : `${a.d.length} notes`} on this block's Markdown`}
          </summary>
          <ul className="rb-diag">
            {a.d.map((x, i) => (
              <li key={i} className={x.sev}>
                {x.sev === 'error' ? 'Problem' : 'Note'} ({x.where}): {x.msg}
              </li>
            ))}
          </ul>
        </details>
      )}
      {a.ok && scope !== undefined && (
        <details className="rb-disclosure rb-scope">
          <summary>
            Source scope {scope}: unresolved and not enforced.
          </summary>
          <div className="rb-disclosure-body">
            Declared as{' '}
            {scope === 'none'
              ? 'none (may use no other material).'
              : scope === 'conversation'
                ? 'the current conversation.'
                : `only ${a.attrs.refs ?? '(no refs given)'}.`}{' '}
            This is shown as declared. Nothing is resolved, retrieved or checked in Mentis.
          </div>
        </details>
      )}
      {/* A form says itself where its answers are kept (types/form.tsx), and a
          block Mentis keeps holds only its view here (types/kept.tsx). */}
      {!bare && a.ok && held !== undefined && b.type !== 'form' && !isDurable(key) && (
        <details className="rb-disclosure rb-state">
          <summary>Modified in this tab</summary>
          <div className="rb-disclosure-body">
            <p>
              Your changes are held in this browser tab only; a reload clears them, and the Markdown is unchanged. They follow the
              block's position, so editing or reordering the source can move them onto another block or item. ⋯ › Reset to source
              discards them.
            </p>
            <p className="rb-tech">Position key {key} · <code>{JSON.stringify(held)}</code></p>
          </div>
        </details>
      )}
      </>}
    </section>
  )
}

/** A renderer that throws must not take the Turn (or the page) with it.
 *  Automatically falls back to local readable text without breaking surrounding content. */
class Guard extends Component<{ type: string; block: RBlock; blockKey: string; where: string; names?: Names; tools?: ReactNode; onFail?: () => void; children: ReactNode }, { e: Error | null }> {
  state = { e: null as Error | null }
  static getDerivedStateFromError(e: Error) { return { e } }
  componentDidCatch(error: Error, info: unknown) {
    console.warn(`[experimental] ${this.props.type} renderer threw:`, error, info)
  }
  componentDidUpdate(prevProps: { block: RBlock }) {
    if (this.state.e && (['type', 'info', 'body', 'closed'] as const).some((field) => this.props.block[field] !== prevProps.block[field])) {
      this.setState({ e: null })
    }
  }
  render() {
    const { e } = this.state
    if (!e) return this.props.children
    const { block, blockKey, where, names, type, tools, onFail } = this.props
    /* The failed drawing offers nothing, whatever it said before or while failing. */
    onFail?.()
    const fallbackText = readableOf(block, blockKey, where, `render exception in ${type}: ${e.message}`, names)
    return (
      <div className="rb-err-fallback">
        {/* The drawing that would have placed the ⋯ is gone; it stays reachable here. */}
        {tools && <div className="rb-row"><span className="rb-grow" />{tools}</div>}
        <div className="rb-bad" role="alert" style={{ marginBottom: '6px' }}>
          <b>The {type} renderer failed:</b> {e.message}
          <div className="rb-muted" style={{ fontSize: '11px', marginTop: '2px' }}>
            Showing readable fallback below. The Markdown source is intact and inspectable.
          </div>
        </div>
        <pre className="rb-pre">{fallbackText}</pre>
      </div>
    )
  }
}

/** Pinned surfaces, kept beside whatever you are doing, across conversations. */
export function PinDock() {
  useStore()
  /* A surface that sends you elsewhere in Mentis (e.g. "Open in Mentis") asks
     the gallery to get out of the way; the pin dock stays. */
  useEffect(() => {
    const close = () => { if (store.gallery) { store.gallery = false; changed() } }
    /* A surface may pin ONE PART of itself (e.g. one reference out of several):
       it hands over a block that names the material, never a copy of it. */
    const pin = (e: Event) => {
      const p = (e as CustomEvent<Pin>).detail
      if (!store.pins.some((x) => x.key === p.key)) store.pins = [...store.pins, p]
      store.open = true
      changed()
    }
    window.addEventListener('mentis:experimental-close-gallery', close)
    window.addEventListener('mentis:experimental-pin', pin)
    return () => {
      window.removeEventListener('mentis:experimental-close-gallery', close)
      window.removeEventListener('mentis:experimental-pin', pin)
    }
  }, [])
  return (
    <>
      {store.gallery && <Gallery onClose={() => { store.gallery = false; changed() }} />}
      {store.sending !== null && (
        <SendDialog key={store.sending} text={store.sending} onClose={() => { store.sending = null; changed() }} />
      )}
      <Dock />
    </>
  )
}

/** The door to the dock, in the app bar with the other top-right marks: a
 *  pin and how many are pinned (ent-2b306f840389 item 2). It used to be a
 *  worded tab floating over the page's top right corner. Nothing pinned,
 *  nothing drawn. */
export function PinsButton() {
  useStore()
  const n = store.pins.length
  if (!n) return null
  const says = store.open ? `Hide pinned (${n})` : `Show pinned (${n})`
  return (
    <button
      className="btn quiet glyph rb-pins"
      aria-pressed={store.open}
      title={says}
      aria-label={says}
      onClick={() => { store.open = !store.open; changed() }}
    >
      <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
        <path
          d="M6 2h4l-.6 4 2.6 2.4V10H4V8.4L6.6 6 6 2zM8 10v4.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      <span className="rb-pins-n">{n}</span>
    </button>
  )
}

/* ---- reconciling pins with the post they came from. ----
   A pin keeps a copy of its block, so it outlives the conversation. A
   surface that knows the current posts may say what each pin is NOW: the
   same block (perhaps revised), or gone -- its name removed, or shared with
   another block -- and then the dock shows a plate rather than the stale
   copy. Nobody says (null), and every pin draws its copy, as always. */
export type PinNow = { state: 'current'; block?: RBlock } | { state: 'removed' | 'ambiguous'; why: string }
export const pinCheck: { now: ((p: Pin) => PinNow | null) | null } = { now: null }

function Dock() {
  if (!store.pins.length || !store.open) return null
  return (
    <aside className="rb-dock" aria-label="Pinned surfaces">
      <div className="rb-row rb-dock-head">
        <b>Pinned</b>
        <span className="rb-grow" />
        <button className="btn quiet" onClick={() => { store.open = false; changed() }}>Hide ▸</button>
      </div>
      {store.pins.map((p) => {
        const now = pinCheck.now?.(p) ?? null
        if (now && now.state !== 'current')
          return (
            <section key={p.key} className="rb-card rb-card-pin rb-pin-plate" data-pin-state={now.state}>
              <p className="rb-from">Pinned from {p.where}</p>
              <p className="rb-muted">{now.why}</p>
              <div className="rb-row">
                <button className="btn quiet" onClick={() => { store.pins = store.pins.filter((x) => x.key !== p.key); changed() }}>Unpin</button>
              </div>
            </section>
          )
        const block = now?.block ?? p.block
        return <Surface key={p.key} block={block} blockKey={p.key} mode="pin" where={p.where} names={p.names} pinned />
      })}
    </aside>
  )
}
