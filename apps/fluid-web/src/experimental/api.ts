/* EXPERIMENTAL: what one marked-block TYPE supplies to the core.

   A type is a meaning ("chart", "form"), never an implementation. The core
   owns everything generic: reading the fence line, version, unknown and
   required attributes, enumerations, state storage (tab lifetime), pinning,
   the degraded/source views and "Send back to agent". A type supplies only
   its own attributes, how to read its body, how to draw it, its readable
   (degraded) text and any extra handoff fields.                              */
import type React from 'react'
import type { Size, TypeSpec } from './spec/api'

export type { AttrSpec, Ctx, Shared, Size, TypeSpec } from './spec/api'

/** Helpers the core lends a type for things only the core can do. */
export interface Help {
  /** The state key of this block (for nested blocks' keys). */
  key: string
  /** Where the block sits, e.g. "Turn ent-…" or "gallery/form-1". */
  where: string
  /** Draw Markdown (which may itself contain marked blocks) under a scope. */
  Nested: (p: { src: string; scope: string }) => React.ReactNode
  /** Readable text of every marked block in `src` (for a container's degraded form). */
  nestedReadable(src: string, scope: string): string
  /** All of `src` as plain text: its own words as written, each marked block
      replaced in place by its readable form (a container's degraded form
      that keeps its prose). */
  nestedText(src: string, scope: string): string
  /** Handoff of every marked block in `src` (for a container's send-back). */
  nestedHandoff(src: string, scope: string): unknown[]
}

/** An entry a surface adds to its block's ⋯ menu. `checked` makes it a radio. */
export interface MenuItem { label: string; checked?: boolean; disabled?: boolean; onSelect(): void }
export interface MenuGroup { label: string; items: MenuItem[] }

export interface RichProps<D, S> {
  data: D
  attrs: Record<string, string>
  state: S | undefined
  /** Replace this block's state; `undefined` returns it to what the source says. */
  set(s: S | undefined): void
  help: Help
  /** 'inline' in a Turn/gallery, 'pin' in the dock (narrower). */
  mode: 'inline' | 'pin'
  /** Offer secondary actions in the block's own ⋯ menu instead of on the page.
      Call during render with everything currently offered (an empty list for none). */
  menu?(groups: MenuGroup[]): void
  /** The block's ⋯, handed over when `placesTools` says the surface places it. */
  tools?: React.ReactNode
  /** The host draws the block's leading heading (TypeDef.heading) as its
      label, so the drawing must not draw it again. Absent in the conversation. */
  labelled?: boolean
  /** The size a workspace draws this copy at (compact, medium, large).
      Absent in the conversation, and then a type draws exactly as it always
      has. table, chart and diagram read it; the rest draw one way. */
  size?: Size
}

/** A type's reading half (./spec) plus how it is drawn. */
export interface TypeDef<D = any, S = any> extends TypeSpec<D> {
  Rich: (p: RichProps<D, S>) => React.ReactNode
  /** Degraded form: plain text that keeps every declared value and the
      current state. Deterministic. */
  readable(data: D, attrs: Record<string, string>, state: S | undefined, help: Help): string
  /** True when the requested presentation is meant to sit inside running text
      (a chat Turn): the core then draws a lighter frame. Presentation, not layout. */
  slim?(attrs: Record<string, string>): boolean
  /** True when the drawing places the block's ⋯ itself (passed as `tools`),
      so one ⋯ sits with the content it acts on. Presentation only. */
  placesTools?(data: D, attrs: Record<string, string>): boolean
  /** Extra fields for the send-back payload (the core adds source, state, problems). */
  handoff?(data: D, attrs: Record<string, string>, state: S | undefined, help: Help): Record<string, unknown>
}
