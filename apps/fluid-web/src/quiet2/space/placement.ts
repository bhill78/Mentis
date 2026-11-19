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

/** WHERE THE 3D BRAIN IS SHOWN -- ALWAYS THE SAME PLACE (owner, revision of
 *  2026-11-18, ent-46aecf919fe8: "The brain should always open consistently as
 *  well. Not sometimes in a different column workspace and then sometimes full
 *  screen. It should work with the full screen").
 *
 *  It used to open wherever there happened to be room -- a free working column
 *  when there was one, maximised when there was not -- so the SAME door gave a
 *  different thing depending on what the columns held at that moment. It is
 *  full screen, every time: the first Open, a parked graph coming back, and a
 *  graph reached again through the browser's history alike. The columns are not
 *  consulted at all, and `room` is deliberately not a parameter: there is no
 *  state this answer can depend on.
 *
 *  Other viewer content (a PDF, pictures, a rendered block) keeps the generic
 *  column-or-maximise placement the page has for it: this is the graph's rule,
 *  and only the graph's. */
export const spacePlace = (): { place: SpacePlace; from: Col | null } => ({ place: 'max', from: null })

/** WHICH PRESENTATION A MAXIMISED VIEWER GETS (owner ent-46aecf919fe8: "not
 *  the document vewer like overlay"). The 3D Brain is a place, drawn on the
 *  canvas the reader is already on in its own stage (space/SpaceStage.tsx);
 *  every other kind of content is a document, drawn in the viewer frame over
 *  a frosted page (viewer/Viewer.tsx). One rule, read at the one place the
 *  page decides what to draw. */
export const presentationOf = (kind: string): 'space-stage' | 'viewer-frame' =>
  kind === 'brain-space' ? 'space-stage' : 'viewer-frame'

/** What a viewer's current placement is, as it is parked. */
export const parkedFrom = (v: { place: SpacePlace; from: Col | null }): ParkedFrom =>
  ({ place: v.place, from: v.place === 'max' ? v.from : null })

export type SpaceTransition =
  /** the first explicit Open, or a parked graph coming back, into `into`.
   *  `centreHeld` is true where the centre reading column holds a reader now
   *  -- a record, a source, the detail the graph sent them to -- because a
   *  graph entry shows none and so takes the centre back from it. */
  | { what: 'place'; into: SpacePlace; centreHeld?: boolean }
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
    case 'place': {
      /* THE GRAPH SHOWN AGAIN ALSO TAKES THE CENTRE (independent review R1).
         A graph entry has no reader, so whatever the centre holds is
         displaced by it -- including a half-written challenge on the record
         the graph itself sent the reader to. The Brain menu's own Open is
         that return path, and it was committing it without a word. The
         conversation underneath is NOT displaced: with the centre on it,
         nothing is lost and nothing is asked. */
      const taken: GuardPlace[] = t.centreHeld ? [CENTRE] : []
      /* a column is taken from whatever is in it; max covers, it does not take */
      if (t.into !== 'max' && !room.free(t.into)) taken.push(t.into)
      return taken
    }
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
