/* ------------------------------------------------------------------------ *
 * ONE OPEN 3D BRAIN'S LIFETIME, HELD OUTSIDE REACT.
 *
 * The drawing (BrainSpace.tsx) and its frame (SpaceSurface.tsx) are unchanged
 * in what they draw and how they behave. What they lacked was a place to keep
 * the view while the renderer is remounted -- which is what moving a viewer
 * between columns, or maximising it, does. So this holds:
 *
 *   WHAT IS BEING LOOKED AT   the selection, the filters, the palette, the
 *                             moment on the record's clock
 *   WHERE THE EYE IS          angle, distance, what it orbits, whether
 *                             somebody has taken hold of it, and the walk
 *   WHAT WAS READ             the settled `/api/space` answer, per material
 *                             key, so a move is never a re-read
 *
 * IT IS BROWSER MEMORY AND NOTHING ELSE. No durable write, no persistence
 * across a reload, no second model of the graph: the nodes, edges and layout
 * stay exactly what `/api/space` said and what layout.ts makes of it.
 *
 * NOBODY HAS TO USE IT. Fluid's `#/brain/space` passes no session and keeps
 * its own local state and its own reader, with the defaults declared here --
 * which are the defaults it always had.
 *
 * WHO CALLS WHAT. The host (Quiet) creates one per open graph, says whether
 * it is visible, and disposes it; the renderer attaches to it and saves its
 * camera; SpaceSessionReader publishes what it read. Camera frames are saved
 * without telling anybody, so turning the Brain never renders the page.
 * ------------------------------------------------------------------------ */

import type { Eye, SpaceRead } from './layout'
import type { Palette } from './BrainSpace'

export type { Palette }

export type SpaceSessionId = string
export type SpaceBrainKey = string
export type SpaceMaterialKey = 'records' | 'material'

export interface SpaceView {
  selected: string | null
  material: boolean
  palette: Palette
  allStrands: boolean
  turns: boolean
  options: boolean
  asOf: number | null
  playing: boolean
}

export interface SpaceCamera {
  initialized: boolean
  framing: 'auto' | 'held'
  zoomed: boolean
  eye: Eye
  walk: readonly string[]
  selectionRevision: number
}

export interface SpaceReadState {
  key: SpaceMaterialKey
  data: SpaceRead | null
  loading: boolean
  error: string | null
}

export interface SpaceSnapshot {
  view: Readonly<SpaceView>
  read: Readonly<SpaceReadState>
  visible: boolean
  disposed: boolean
}

export interface SpaceSession {
  readonly id: SpaceSessionId
  readonly brainKey: SpaceBrainKey
  getSnapshot(): SpaceSnapshot
  subscribe(listener: () => void): () => void
  getCamera(): SpaceCamera
  saveCamera(camera: SpaceCamera): void
  setView(patch: Partial<Omit<SpaceView, 'selected'>>): void
  select(entry: string | null, intent: 'user' | 'reconcile'): void
  setVisible(visible: boolean): void
  attachRenderer(): () => void
  dispose(): void
}

/* ---- the defaults, which are Fluid's own ------------------------------- */

/** How the eye starts: outside and a little above, so the shape reads first.
 *  The same two numbers the canvas has always opened on. */
export const SPACE_OPENING = { turn: 0.6, rise: 0.42 } as const

/** What an unbound Fluid surface shows, declared once so a session and a
 *  session-less surface cannot drift apart. */
export const SPACE_VIEW_DEFAULTS: Readonly<SpaceView> = Object.freeze({
  selected: null,
  material: false,
  palette: 'none' as Palette,
  allStrands: false,
  turns: true,
  options: false,
  asOf: null,
  playing: false,
})

/** A camera nobody has touched. `out` is 0 until a measured layout gives the
 *  world a radius; `initialized` says that has not happened yet, so nothing
 *  mistakes this for a view somebody settled on. */
export function defaultCamera(): SpaceCamera {
  return {
    initialized: false,
    framing: 'auto',
    zoomed: false,
    eye: { turn: SPACE_OPENING.turn, rise: SPACE_OPENING.rise, out: 0, at: { x: 0, y: 0, z: 0 } },
    walk: [],
    selectionRevision: 0,
  }
}

export const materialKey = (material: boolean): SpaceMaterialKey => (material ? 'material' : 'records')

/** The read's own address. The two the surface always read, and no other. */
export const spacePath = (key: SpaceMaterialKey): string =>
  key === 'material' ? '/api/space?material=1' : '/api/space'

/** HOW FAR OUT AN UNTOUCHED EYE SITS: far enough to hold the whole Brain, and
 *  further on a portrait screen, which is the canvas's own rule. Width and
 *  height are left out where the container has not been measured. */
export function autoDistance(radius: number, w?: number, h?: number): number {
  const portrait = w !== undefined && h !== undefined && h > w
  return radius * 1.85 * (portrait ? 1.4 : 1)
}

/** WHETHER THE CONTAINER MAY STILL FRAME THE VIEW. An untouched auto camera
 *  follows the data and the container as it always did; once somebody has
 *  taken hold of the eye, nothing re-fits it -- not a radius change, not a
 *  remount, not a repaint. */
export const framesItself = (camera: Pick<SpaceCamera, 'framing' | 'zoomed'>): boolean =>
  camera.framing === 'auto' && !camera.zoomed

/** WHETHER A SELECTION IS STILL POINTING AT SOMETHING DRAWN.
 *
 *  `settled` is the whole guard: a selection is never reconciled against a
 *  read that has not landed, failed, or belongs to the other material key,
 *  because an absent answer is not evidence that the thing is gone. */
export function letsGoOfSelection(input: {
  selected: string | null
  settled: boolean
  drawn: boolean
  hiddenLayer: boolean
}): boolean {
  if (!input.selected || !input.settled) return false
  return !input.drawn || input.hiddenLayer
}

/* ---- the private seam between a reader and its session ------------------ *
 * Owned by surfaces/space. NOT a host API: a host never supplies a SpaceRead,
 * and nothing outside this directory publishes one. SpaceSessionReader and
 * the focused state tests are its only callers.
 * ---------------------------------------------------------------------- */

export interface SpaceSessionInside {
  /** which material key the view asks for now */
  activeKey(): SpaceMaterialKey
  /** what a read of `key` settled on, loading, or failed with */
  publish(key: SpaceMaterialKey, patch: { loading?: boolean; data?: SpaceRead | null; error?: string | null }): void
  /** what is retained for either key, whichever is active */
  retained(key: SpaceMaterialKey): Readonly<SpaceReadState>
  /** whether a renderer holds this session now */
  attached(): boolean
  /** how many times subscribers have been told, for proving what is quiet */
  told(): number
}

const inside = new WeakMap<SpaceSession, SpaceSessionInside>()

/** The reader's door into a session. Private to surfaces/space. */
export function spaceSessionInside(session: SpaceSession): SpaceSessionInside {
  const got = inside.get(session)
  if (!got) throw new Error('not a space session made here')
  return got
}

/* ---- the session itself ------------------------------------------------- */

const copyEye = (e: Eye): Eye => ({ turn: e.turn, rise: e.rise, out: e.out, at: { ...e.at } })

const copyCamera = (c: SpaceCamera): SpaceCamera => ({
  initialized: c.initialized,
  framing: c.framing,
  zoomed: c.zoomed,
  eye: copyEye(c.eye),
  walk: [...c.walk],
  selectionRevision: c.selectionRevision,
})

const emptyRead = (key: SpaceMaterialKey): SpaceReadState => ({ key, data: null, loading: false, error: null })

export function createSpaceSession(input: { id: SpaceSessionId; brainKey: SpaceBrainKey }): SpaceSession {
  /* NOTHING HAPPENS HERE. No fetch, no DOM, no timer: a host may make one
     before anything is placed, and does. */
  const { id, brainKey } = input
  let view: SpaceView = { ...SPACE_VIEW_DEFAULTS }
  const reads: Record<SpaceMaterialKey, SpaceReadState> = {
    records: emptyRead('records'),
    material: emptyRead('material'),
  }
  let camera = defaultCamera()
  let visible = false
  let disposed = false
  let attached = false
  let told = 0
  let snapshot: SpaceSnapshot | null = null
  const listeners = new Set<() => void>()

  const key = () => materialKey(view.material)

  /* A SNAPSHOT IS THE SAME OBJECT UNTIL SOMETHING CHANGES, so a subscriber
     that compares snapshots is told the truth and renders no more often. */
  const changed = () => {
    snapshot = null
    told += 1
    for (const l of [...listeners]) l()
  }

  const session: SpaceSession = {
    id,
    brainKey,

    getSnapshot() {
      if (!snapshot) {
        snapshot = Object.freeze({
          view: Object.freeze({ ...view }),
          read: Object.freeze({ ...reads[key()] }),
          visible,
          disposed,
        })
      }
      return snapshot
    },

    subscribe(listener) {
      if (disposed) return () => {}
      listeners.add(listener)
      return () => listeners.delete(listener)
    },

    /* THE CAMERA IS NOT IN THE SNAPSHOT, and saving it tells nobody: a
       pointer frame must not render the page it is drawn in. Both ways are
       value copies, so neither side can reach into the other's. */
    getCamera() {
      return copyCamera(camera)
    },

    saveCamera(next) {
      if (disposed) return
      camera = copyCamera(next)
    },

    setView(patch) {
      if (disposed) return
      const next: SpaceView = { ...view }
      let moved = false
      for (const [k, v] of Object.entries(patch) as [keyof SpaceView, never][]) {
        if (k === 'selected') continue
        if (v === undefined || next[k] === v) continue
        next[k] = v
        moved = true
      }
      if (!moved) return
      view = next
      changed()
    },

    /* A USER'S CHOICE IS THE ONLY THING THAT MAY MOVE THE EYE. Reconciling
       -- letting go of something no longer drawn -- changes the selection and
       nothing else, so a remount or a re-read never replays a flight. */
    select(entry, intent) {
      if (disposed || view.selected === entry) return
      view = { ...view, selected: entry }
      if (intent === 'user') camera = { ...camera, selectionRevision: camera.selectionRevision + 1 }
      changed()
    },

    /* PARKED, HIDDEN OR UNDRAWN IS NOT PLAYING. The moment on the clock is
       kept; the clock itself stops, and coming back does not start it. */
    setVisible(next) {
      if (disposed || visible === next) return
      visible = next
      if (!next && view.playing) view = { ...view, playing: false }
      changed()
    },

    attachRenderer() {
      if (disposed || attached) return () => {}
      attached = true
      let mine = true
      return () => {
        if (!mine) return
        mine = false
        attached = false
        /* DETACHED IS NOT DISPOSED. The session, its read and its camera
           stay; only the canvas's own clock stops. */
        if (view.playing) {
          view = { ...view, playing: false }
          changed()
        }
      }
    },

    dispose() {
      if (disposed) return
      disposed = true
      attached = false
      visible = false
      view = { ...view, playing: false }
      reads.records = emptyRead('records')
      reads.material = emptyRead('material')
      changed()
      listeners.clear()
    },
  }

  inside.set(session, {
    activeKey: key,
    publish(k, patch) {
      /* LATE IS IGNORED, NOT APPLIED. A completion after disposal, or for a
         key the view no longer asks for, changes nothing -- and a result is
         never filed under a key it did not come from. */
      if (disposed) return
      const was = reads[k]
      const next: SpaceReadState = {
        key: k,
        data: patch.data !== undefined ? patch.data : was.data,
        loading: patch.loading !== undefined ? patch.loading : was.loading,
        error: patch.error !== undefined ? patch.error : was.error,
      }
      /* A FAILED READ KEEPS THE LAST GOOD ANSWER FOR ITS OWN KEY, and says
         so: the Brain stays drawn with the failure beside it. */
      if (
        next.data === was.data &&
        next.loading === was.loading &&
        next.error === was.error
      )
        return
      reads[k] = next
      if (k === key()) changed()
    },
    retained(k) {
      return { ...reads[k] }
    },
    attached: () => attached,
    told: () => told,
  })

  return session
}
