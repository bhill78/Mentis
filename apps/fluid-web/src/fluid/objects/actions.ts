/* ONE SET OF OBJECT ACTIONS, THE SAME FROM EVERY ORIGIN (fluid-arrange review,
 * owner's final consolidation brief §2, §5). A chart in a post, a line in a
 * card's "In this thread", a Contents row, a section card, a float header, a
 * search hit, a Brain entry, agent output: each offers exactly these, through
 * `ObjectActions.tsx`, and each calls the functions here -- never its own.
 *
 *   Open     the full view, with its own navigation (the owner's correction,
 *            W7): an object's detail (workspace/Detail.tsx), a post read with
 *            This post showing its context, a Brain entry's inspector
 *            (objects/route.ts says which). A click on the object or the
 *            post itself is Open too.
 *   Peek     inspect without disruption: a light surface over the workspace,
 *            Previous/Next through `siblings`; never changes Primary, Focus or
 *            the arrangement; closing returns to the same Page and scroll.
 *   Float    the object in its own floating surface beside where it was.
 *   Keep     the Keep chooser: a section or a Page.
 *   Primary  today's position swap (focus/model.ts makePrimary); an embedded
 *            object is floated first, then swapped, in one step.
 *   Focus    the temporary attention state (focus/lens.ts): the object takes
 *            the Page's stable Focus area in the remembered presentation.
 *
 * SHARED INTERFACE. Workstreams fill in their part by `provide(...)` from their
 * own module (lens.ts provides focus/primary, the Peek host provides peek);
 * every caller only imports `act`. The defaults below are today's behaviour,
 * so nothing breaks before a provider is merged. */

import * as nav from '../nav'
import { store } from '../store'
import { inspect } from '../present/viewer'
import { askKeep, floatIt } from '../workspace/keep'
import { openObject } from '../workspace/open'
import { openRoute, type ObjectAction } from './route'

export { ACTION_ORDER, openRoute, type ObjectAction, type OpenRoute } from './route'

/** What an action is asked about: the object and where it was asked from. */
export interface ObjectTarget {
  /** a live or exact object address (`live:<root>:<key>`), `brain:<entry>`,
   *  or `post:<id>` for a whole post */
  address: string
  title?: string
  /** the object's kind ('chart', 'diagram', 'file', 'form', 'table', 'image', 'post', 'brain'...) */
  kind?: string
  /** provenance in words: "#4 · reply to #3 · Dungeons and Dragons" */
  from?: string
  /** the element it was asked from: Peek grows out of it and returns into it */
  anchor?: HTMLElement | null
  /** what Previous/Next step through in Peek, in order (includes `address`) */
  siblings?: string[]
  /** the zone and Page it is shown in, when it is shown in one */
  zone?: string
  page?: string
}

export interface ObjectActionImpl {
  open(t: ObjectTarget): void
  peek(t: ObjectTarget): void
  float(t: ObjectTarget): void
  keep(t: ObjectTarget): void
  primary(t: ObjectTarget): void
  focus(t: ObjectTarget): void
}

/** A whole post opened: read where it lives, as a click on its card reads
 *  it, so This post shows its context (and its thread, with Follow on). */
function openPost(id: string) {
  const go = () => {
    const p = store.posts.get(id)
    const conversation = p?.home ?? nav.snapshot().conversation
    if (conversation) nav.read(conversation, id, p?.number ?? null)
  }
  if (store.posts.has(id)) go()
  else void store.loadPosts([id]).then(go, go)
}

/** OPEN: the full view of what `t` is (objects/route.ts). */
export function openTarget(t: ObjectTarget) {
  const r = openRoute(t.address)
  if (r.to === 'post') openPost(r.id)
  /* a Brain entry has no detail of its own outside the Brain: the record's
     inspector, which Peek draws (a Brain surface opens its own instead) */
  else if (r.to === 'brain') impl.peek(t)
  else openObject(r.address, t.anchor ?? null)
}

const impl: ObjectActionImpl = {
  open: (t) => openTarget(t),
  peek: (t) => inspect(t.address, t.anchor ?? null),
  float: (t) => floatIt(t.address, t.anchor ?? null, t.from),
  keep: (t) => askKeep({ address: t.address, zone: t.zone, page: t.page }, t.anchor ?? null),
  /* Until focus/lens.ts provides them: floating is the only way an embedded
     object becomes a surface, so both fall back to Float. */
  primary: (t) => floatIt(t.address, t.anchor ?? null, t.from),
  focus: (t) => floatIt(t.address, t.anchor ?? null, t.from),
}

/** A workstream replaces its actions here, once, at module load. */
export function provide(part: Partial<ObjectActionImpl>) { Object.assign(impl, part) }

/** Every caller goes through this. */
export const act: ObjectActionImpl = {
  open: (t) => impl.open(t),
  peek: (t) => impl.peek(t),
  float: (t) => impl.float(t),
  keep: (t) => impl.keep(t),
  primary: (t) => impl.primary(t),
  focus: (t) => impl.focus(t),
}

/** The icons and words every ObjectActions row uses (tooltips carry the words). */
export const ACTION_LOOK: Record<ObjectAction, { icon: string; label: string; says: string; key?: string }> = {
  open: { icon: '◨', label: 'Open', says: 'Open details: the full view, with its own navigation' },
  peek: { icon: '◱', label: 'Peek', says: 'Peek: look closer without changing anything (Esc returns)' },
  float: { icon: '⧉', label: 'Float', says: 'Float: open it in its own window beside you' },
  keep: { icon: '◆', label: 'Keep', says: 'Keep in a section or on a Page' },
  primary: { icon: '◎', label: 'Primary', says: 'Make primary: swap it into the primary place', key: 'F' },
  focus: { icon: '⛶', label: 'Focus', says: 'Focus: give it the large working area for now (Esc steps back)', key: 'Shift+F' },
}
