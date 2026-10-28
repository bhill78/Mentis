/* THE ONE SHARED SOURCE REGISTRY: every collection a Home zone can show,
 * and every feed a conversation section can bring in, by the word kept for
 * it (`show`), registered here rather than named in either (Fluid
 * completion; Home's COLLECTIONS list and if-chain, made a registry, then
 * made shared with the workspace's sections).
 *
 * Home asks the registry for everything it used to hardcode: the picker's
 * list (`sources('home')`, in the order registered), a zone's section
 * (`sectionOf(z.show)`), each section's body and the flags Home draws by
 * (`conversation` docks as the rail; `kept` holds kept items). A workspace
 * section asks `sources('conversation')` for the feeds it may bring in:
 * this conversation's Brief, Actions, Follow ups, Media and Guidance (the
 * About slide-out's views, scope 'conversation') and Home's collections. A
 * new section is added with `registerSection()` and no edit to either.
 *
 * The stored word is the section's identity: it is what a saved arrangement
 * keeps (arrangements.py `_SHOW`), so it never changes. */

import type { ComponentType, ReactNode } from 'react'
import type { Id } from '../store'
import type { Slot, Zone } from '../workspace/tree'

/** The chrome every section is drawn in: its name and count on the left of
 *  the caption, fold, the zone's tools and ⋯ on the right. Home draws it;
 *  a section fills it. */
export interface ChromeParts { count?: number; filters?: ReactNode; tools?: ReactNode; children: ReactNode }
export type Chrome = (p: ChromeParts) => ReactNode

/** What Home, or a workspace section drawing the body as its feed, hands a
 *  section's body. */
export interface SectionBodyProps {
  z: Zone
  /** the zone's options read through the section's `readOptions` (Work's tab
   *  as its state, the Briefing's period), defaults applied */
  options: Record<string, unknown>
  /** keep one of the zone's options, flat beside the rest */
  setOption: (key: string, value: unknown) => void
  /** change what the zone's slot keeps or how it presents it (a kept zone) */
  setSlot: (f: (s: Slot) => Slot, words?: string) => void
  onOpenPost: (c: Id, p: Id) => void
  /** the Governance page, reached from Needs you */
  onOpenGovernance?: () => void
  chrome: Chrome
  /** the conversation a conversation-scoped source reads; null on Home */
  conversation?: Id | null
  /** drawn as a feed inside a workspace section (which draws its own
   *  caption): `chrome` then just renders its children */
  inSection?: boolean
}

export interface SectionDef {
  /** the word a zone showing this section keeps, stored unchanged */
  show: string
  /** its name in the picker and on the zone's caption */
  name: string
  /** what fills the chrome; absent for the conversation, which Home draws
   *  itself (the frame's conversation column) */
  body?: ComponentType<SectionBodyProps>
  /** the options a zone of this section starts from when nothing was chosen
   *  (Work's tab `all`; the Briefing's period null -- the period it is now) */
  defaults?: Record<string, unknown>
  /** the body's view of the zone's stored options, defaults applied */
  readOptions?: (o: Record<string, unknown>) => Record<string, unknown>
  /** docks at its row's nearer edge as the rail when narrowed, and Home
   *  draws the conversation column in it rather than a section body */
  conversation?: boolean
  /** holds kept items: its slot is what it keeps, drawn through ../present */
  kept?: boolean
  /** where it may be chosen: on Home ('home', the default), or as a
   *  conversation section's feed ('conversation' -- it needs a conversation:
   *  the About slide-out's five views), or either ('anywhere') */
  scope?: 'home' | 'conversation' | 'anywhere'
}

const all: SectionDef[] = []
const byShow = new Map<string, SectionDef>()

/** Add a section to Home (or replace one registered under the same word,
 *  keeping its place). A section added here is offered by the picker and
 *  found by Home's body lookup without any edit to Home. */
export function registerSection(def: SectionDef): void {
  const had = byShow.get(def.show)
  if (had) all[all.indexOf(had)] = def
  else all.push(def)
  byShow.set(def.show, def)
}

/** Every registered section, in the order the picker offers them. */
export const sections = (): readonly SectionDef[] => all

/** The sources a place may bring in, in the order registered. Home's picker
 *  (scope 'home') offers Home's own and the anywhere sections -- never a
 *  conversation-only view; a conversation section's feed (scope
 *  'conversation') may be any registered source. */
export const sources = (scope: 'home' | 'conversation'): readonly SectionDef[] =>
  scope === 'conversation' ? all : all.filter((s) => s.scope !== 'conversation')

/** Home's body lookup: the section a zone's `show` names, if one is
 *  registered (a zone whose word none names asks what to show). */
export const sectionOf = (show: string): SectionDef | undefined => byShow.get(show)

/** A section's view of a zone's stored options: read through its own reader
 *  when it has one, its defaults under what was chosen otherwise. */
export const sectionOptions = (def: SectionDef, o: Record<string, unknown>): Record<string, unknown> =>
  def.readOptions ? def.readOptions(o) : def.defaults ? { ...def.defaults, ...o } : o
