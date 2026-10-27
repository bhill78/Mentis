import { createContext } from 'react'

/** Something in a posted Turn the surface around it may expand: a marked
 *  block by its key and Turn part, an attachment by its media key, or the
 *  post's own words (its text outside its sections). */
export type ExpandTarget =
  | { kind: 'block'; key: string; where: string }
  | { kind: 'media'; key: string; turn: string; ref?: string | null }
  | { kind: 'text'; turn: string }

/** One place an object can be expanded to: a zone. */
export interface ExpandPlace { id: string; label: string }
/** One page an object can be sent to, with its zones. */
export interface ExpandPage { id: string; label: string; current: boolean; zones: ExpandPlace[] }

/** What the surface around a Turn offers for expanding what it holds. The
 *  conversation offers nothing (null), so its blocks keep "Pin beside the
 *  conversation" and draw no ↗; the Workspace Lab offers it while its
 *  workspace is open. Only what was POSTED can be expanded: a draft in the
 *  composer preview has a different key once posted (`posted`). */
export interface Expander {
  /** ↗: the object's page if it declares one, else the working page */
  quick(t: ExpandTarget): void
  /** Expand › On this page: the page showing, or -- while Replies & details
   *  shows -- the page you were last on */
  toPage(t: ExpandTarget): void
  /** what "On this page" is called now */
  here(): string
  /** Expand › To page ▸: every page, and its zones */
  pages(): ExpandPage[]
  /** to one page: into `zone`, or (null) the zone it would go to there */
  toZone(t: ExpandTarget, zone: string | null, page: string): void
  /** Expand › On a new page */
  toNewPage(t: ExpandTarget): void
  /** a ↗ dragged onto a zone: its centre appends, its edge splits */
  drag(t: ExpandTarget, e: PointerEvent): void
}

export const ExpandContext = createContext<Expander | null>(null)

/** Is this a posted Turn part's scope (`turnPartScope`), so its blocks keep
 *  their keys? A draft's is `draft in …`, a search preview's `search-preview/…`. */
export const posted = (where: string) => where.startsWith('Turn ')
