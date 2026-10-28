/* KEEP AS SECTION: one of this conversation's views (Brief, Actions, Follow
 * ups, Media, Guidance -- sections/conversationViews.tsx), kept as a section
 * of the workspace rather than read in the About slide-out.
 *
 * The section brings the view in as its FEED (`slot.feed`, the shared source
 * registry's word) and places nothing yet: it follows no post, and what is
 * put in it later is its Placed lane above the feed. It goes beside the
 * conversation's primary on the page shown -- split off the primary's leaf
 * when the primary is docked in the tree, or at the tree's edge nearest the
 * column when the primary is the column (or a float, which has no side to
 * be beside). One step, undone like any other (`workspace.edit`).
 *
 * The same view kept twice is one section: when the page already has a
 * section bringing in that feed, it is lit (as Keep lights the zone a choice
 * names) and nothing is added.
 *
 * Placement only: nothing here writes to the record. */

import * as nav from '../nav'
import { locate, primaryOf } from '../focus/model'
import { onPage, pageIn, pageView, shownPage } from '../focus/page'
import { hintZone } from './keep'
import type { Arr } from './place'
import { workspace } from './place'
import { splitOuter, splitZone, zone, zones, type Feed, type Slot, type Zone } from './tree'

type FeedSlot = Slot

/** What the conversation's primary keeps of its leaf when a section is split
 *  off beside it (and the tree, of the page, when it goes at the edge). */
const KEEP = 2 / 3

/** The slot of a section bringing in `source` and placing nothing. */
export const feedSlot = (source: string): FeedSlot =>
  ({ follow: false, show: 'objects', items: [], present: 'list', feed: { source } })

/** Options as a feed keeps them, in one order, so two can be compared. */
const canon = (o: Record<string, unknown> | undefined) =>
  JSON.stringify(Object.keys(o ?? {}).sort().map((k) => [k, o![k]]))
const sameFeed = (a: Feed | undefined, b: Feed) => !!a && a.source === b.source && canon(a.options) === canon(b.options)

/** Every section on page view `v`: its tree's leaves, the column's content
 *  and its floats'. */
const placed = (v: Arr): Zone[] => [
  ...zones(v.tree),
  ...(v.focus?.column ? [v.focus.column] : []),
  ...(v.focus?.floats ?? []).map((f) => f.zone),
]

/** The section on `page` of `a` that already brings in `feed`, if one does. */
export function feedSectionOn(a: Arr, page: string, feed: Feed): string | undefined {
  return placed(pageView(a, page)).find((z) => sameFeed((z.slot as FeedSlot | undefined)?.feed, feed))?.id
}

/** `made` added beside the primary of page view `v`. */
function besidePrimary(v: Arr, made: Zone): Arr {
  const at = locate(v, primaryOf(v))
  if (at?.place === 'leaf') return { ...v, tree: splitZone(v.tree, at.zone.id, 'row', made, false, KEEP).tree }
  return { ...v, tree: splitOuter(v.tree, 'left', made, KEEP) }
}

/** `a` with a section bringing in `source` beside the conversation's primary
 *  on `page`, named `name` (the view's own name; a fresh one otherwise); or
 *  `a` itself, and the section that already does, when one is there. Pure:
 *  the caller makes it a step. */
export function withFeedSection(a: Arr, source: string, page: string, name?: string): { arr: Arr; zone: string; added: boolean } {
  const at = pageIn(a, page)
  const had = feedSectionOn(a, at, { source })
  if (had) return { arr: a, zone: had, added: false }
  const fresh = zone(pageView(a, at).tree, feedSlot(source))
  const made = name ? { ...fresh, name } : fresh
  return { arr: onPage((v) => besidePrimary(v, made), at)(a), zone: made.id, added: true }
}

/** Keep the view `source` (named `name`) as a section on the page shown;
 *  Undo is on the toast. When the page already has it, light that one. */
export function keepFeedSection(source: string, name: string): void {
  const page = shownPage()
  const got = withFeedSection(workspace.arr, source, page, name)
  if (got.added) workspace.edit(() => got.arr, `Kept ${name} as a section.`)
  else nav.toast({ text: `${name} is already a section on this page.` })
  /* Show where it is: lit for a moment, as Keep lights the zone it names. */
  hintZone(got.zone)
  setTimeout(() => hintZone(null), 1800)
}
