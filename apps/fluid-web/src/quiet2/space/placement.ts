/* PARKING AND COMING BACK (addendum §3), as decisions apart from the page.
 *
 * PARK IS EXPLICIT. A parked graph keeps its viewer id and its session; it
 * holds no column, reserves no maximised `from`, and is not what `maximised`,
 * `inColumn`, eviction or column settlement see (viewer/viewers.ts). It is
 * never deleted by a generic path: everything that would otherwise close a
 * graph parks it instead, and only the one release path disposes it.
 *
 * WHAT A TRANSITION ACTUALLY DISPLACES is computed BEFORE anything moves, so
 * the existing leaving question (leaving.ts) is put for every place that
 * really loses something -- and for nothing else. Where any of them says
 * Stay, nothing at all has changed: not placement, not the receded
 * conversation, not visibility, not playback, not the history.
 *
 * Pure, so §3's placement priority and its guard set are checkable
 * (`tests/quiet_space_nav_unit.ts`). */

export type Col = 's1' | 's2'
export type SpacePlace = 'max' | Col
/** the centre reading column, as leaving.ts names it */
export const CENTRE = 'centre'
export type GuardPlace = typeof CENTRE | Col

/** Where a parked graph came from, kept with it while it is parked. */
export interface ParkedFrom { place: SpacePlace; from: Col | null }

/** What the page can say about its columns at this moment. */
export interface ColumnRoom {
  /** the working columns drawn now, in order */
  shown: Col[]
  /** nothing else is in it (no surface, viewer, dock panel) */
  free: (s: Col) => boolean
}

/** WHERE A PARKED GRAPH COMES BACK TO (§3, "Restoration placement priority"):
 *  its old column while that is still shown and free, else another shown free
 *  column, else maximised. A graph that was maximised asks for max again, and
 *  keeps its old `from` only while that column is still shown and free -- so
 *  Restore never drops it onto content that arrived in the meantime. */
export function restoreTo(was: ParkedFrom, room: ColumnRoom): { place: SpacePlace; from: Col | null } {
  const usable = (s: Col | null): s is Col => !!s && room.shown.includes(s) && room.free(s)
  if (was.place === 'max') return { place: 'max', from: usable(was.from) ? was.from : null }
  if (usable(was.place)) return { place: was.place, from: null }
  const other = room.shown.find((s) => s !== was.place && room.free(s))
  if (other) return { place: other, from: null }
  return { place: 'max', from: null }
}

/** What a viewer's current placement is, as it is parked. */
export const parkedFrom = (v: { place: SpacePlace; from: Col | null }): ParkedFrom =>
  ({ place: v.place, from: v.place === 'max' ? v.from : null })

export type SpaceTransition =
  /** the first explicit Open, or a parked graph coming back, into `into` */
  | { what: 'place'; into: SpacePlace }
  /** reading a node, or a link off its reader: a reader takes the centre */
  | { what: 'inspect' }
  /** the graph itself closed */
  | { what: 'close' }
  /** somewhere else in Quiet Chat is being gone to while the graph is up */
  | { what: 'elsewhere'; into: GuardPlace | null }

/** EVERY PLACE THIS TRANSITION ACTUALLY TAKES SOMETHING FROM. The guard is
 *  put for each, in order, and the transition commits only once they all
 *  permit leaving. A maximised graph displaces nothing by being drawn over
 *  the page: what it covers is still there, and comes back when it parks. */
export function affectedPlaces(t: SpaceTransition, room: ColumnRoom): GuardPlace[] {
  switch (t.what) {
    case 'place':
      /* a column is taken from whatever is in it; max covers, it does not take */
      return t.into === 'max' ? [] : room.free(t.into) ? [] : [t.into]
    case 'inspect':
      /* the reader takes the centre reading column */
      return [CENTRE]
    case 'close':
      /* the graph's own close discards the graph, which the guard does not
         speak for; anything else it would discard is named by the caller */
      return []
    case 'elsewhere':
      return t.into && t.into !== CENTRE ? (room.free(t.into) ? [] : [t.into]) : t.into ? [CENTRE] : []
  }
}

/** Whether a graph in `place` would obscure a reader taking the centre, and
 *  so must park for it to be seen (§3, "Node Open"). */
export const obscuresCentre = (place: SpacePlace) => place === 'max'

/** WHEN THE CANVAS IS ACTUALLY VISIBLE (addendum §1, "Visibility and
 *  attachment"): drawn in a host that is not inert, on a page the browser is
 *  showing. Parked is none of those, and so is false. Animation needs this
 *  AND the renderer attached; the session is told only this. */
export const graphVisible = (at: { drawn: boolean; inertHost: boolean; documentVisible: boolean }) =>
  at.drawn && !at.inertHost && at.documentVisible

/** WHAT A TEMPORARY PRESENTATION OVERRIDE REMEMBERS. Inspecting from the
 *  graph may need the conversation column back to show a reader in it. That
 *  is presentation, not a saved workspace choice: the value it had, and the
 *  layout revision it had it at, are remembered, and the return puts it back
 *  ONLY where the reader has not changed the layout since. */
export interface RecededOverride { was: boolean; atRevision: number }
export const restoresReceded = (o: RecededOverride, revisionNow: number) => o.atRevision === revisionNow
