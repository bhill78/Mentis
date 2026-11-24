/** R2 of the inspection re-review (adm-6a1f95f203bf): the saved reading
 *  position must be rendered when the view is returned to, and must survive
 *  content that arrives after the view does.
 *
 *  The defect had two halves and both are checked here against the real
 *  `places` spine: a position written into a container whose content has not
 *  arrived is clamped and never re-applied, and the clamped offset is reported
 *  back through the view's scroll handler, which saved it over the number the
 *  reader left. The decisions the frame makes from `position.ts` are driven
 *  through a container that clamps exactly as a scroll container does; the
 *  rendered behaviour itself is covered by the mounted Edge regression
 *  `quiet_magnet_reading_position_browser.py`. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { closeInspect, inspect, place, placeKeyOf, goTab, setOpen } from '../src/quiet2/magnets/places'
import { magnetScroll } from '../src/quiet2/magnets/Magnet'
import { pendingScroll, reachedScroll, savesReportedScroll } from '../src/quiet2/magnets/position'
import { page as binding } from '../src/brainBinding'

const SOURCE = 'ent-source333333'
const brainKey = 'origin|fixture|brain-position'
const memory = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-position@instance-one')
  return mem
}
const config = (id: `mag-${string}`) => ({ id, sources: [{ kind: 'conversation' as const, conversation: SOURCE }], selection: {}, conversation: 'ent-own333333',
  collection: { mode: 'one-time' as const }, synthesis: { mode: 'manual' as const },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' as const } })
const resourceFor = (id: `mag-${string}`) => createMagnetResource({ id: `qm-${id}`, brainKey,
  saved: { id, name: 'Reading position', config: config(id) },
  get: async () => ({ status: 200, body: {} }) })

/** A scroll container, with the one behaviour that matters: it cannot hold an
 *  offset its content is too short for, and it reports what it took. */
class Container {
  height = 0
  top = 0
  reports: number[] = []
  set scrollTop(v: number) { this.top = Math.max(0, Math.min(Math.round(v), this.height)); this.reports.push(this.top) }
  get scrollTop() { return this.top }
}

/** The frame's three decisions, in one place, over the real spine: apply the
 *  saved position, keep what the container could not take, and save only what a
 *  report is allowed to save. */
function frame(resource: ReturnType<typeof resourceFor>, el: Container) {
  let waiting: number | null = null
  const applySaved = () => {
    el.scrollTop = magnetScroll(resource.snapshot())
    waiting = pendingScroll(el.scrollTop, magnetScroll(resource.snapshot()))
  }
  const grew = (height: number) => {
    el.height = height
    if (waiting === null) return
    el.scrollTop = waiting
    if (reachedScroll(el.scrollTop, waiting)) waiting = null
  }
  /** Exactly the frame's onScroll: it saves into the place, or it does not. */
  const reported = (top: number) => {
    if (!savesReportedScroll(waiting, top)) return false
    const s = resource.snapshot(), p = place(s)
    resource.update({ places: { ...s.places, [placeKeyOf(s)]: p.inspected ? { ...p, inspectScroll: top } : { ...p, scroll: top } } })
    return true
  }
  const readerMoved = () => { waiting = null }
  return { applySaved, grew, reported, readerMoved, kept: () => waiting }
}

test('a position the container can take is reached and nothing is kept', () => {
  memory()
  const r = resourceFor('mag-position-reached')
  setOpen(r, true)
  goTab(r, 'Conversation')
  const el = new Container()
  el.height = 1200
  r.update({ places: { ...r.snapshot().places, Conversation: { ...place(r.snapshot()), scroll: 400 } } })
  const f = frame(r, el)
  f.applySaved()
  assert.equal(el.scrollTop, 400)
  assert.equal(f.kept(), null)
})

test('a position the content is too short for is kept, applied when it grows, and never overwritten', () => {
  memory()
  const r = resourceFor('mag-position-late')
  setOpen(r, true)
  goTab(r, 'Conversation')
  r.update({ places: { ...r.snapshot().places, Conversation: { ...place(r.snapshot()), scroll: 400 } } })
  const el = new Container()
  el.height = 93                                   // the posts have not arrived
  const f = frame(r, el)
  f.applySaved()
  assert.equal(el.scrollTop, 93, 'the container clamps what it was given')
  assert.equal(f.kept(), 400, 'and the position it could not take is kept')
  assert.equal(f.reported(93), false, 'the clamp is not saved as a reading position')
  assert.equal(place(r.snapshot()).scroll, 400, 'so the number the reader left is still there')
  f.grew(1200)                                     // the posts arrive
  assert.equal(el.scrollTop, 400, 'the kept position is applied to the content that arrived')
  assert.equal(f.kept(), null)
  assert.equal(f.reported(400), true, 'and the restore itself is an ordinary report again')
  assert.equal(place(r.snapshot()).scroll, 400)
})

test('leaving an inspection renders and keeps the list position it returns to', () => {
  memory()
  const r = resourceFor('mag-position-inspect')
  setOpen(r, true)
  goTab(r, 'Conversation')
  const el = new Container()
  el.height = 1200
  const f = frame(r, el)
  f.reported(400)
  assert.equal(place(r.snapshot()).scroll, 400)
  inspect(r, 'ent-citedpost1111')
  el.height = 300                                  // the inspection is its own length
  f.applySaved()
  assert.equal(el.scrollTop, 0, 'an inspection starts at its own top')
  assert.equal(f.kept(), null, 'and nothing is waited for')
  closeInspect(r)
  el.height = 93                                   // the view remounts, short again
  f.applySaved()
  assert.equal(f.kept(), 400)
  assert.equal(f.reported(93), false)
  assert.equal(place(r.snapshot()).scroll, 400, 'Back does not destroy the saved list position')
  f.grew(1200)
  assert.equal(el.scrollTop, 400, 'and the reader is returned to where they were reading')
})

test('a reader who moves in the view gives up the kept position', () => {
  memory()
  const r = resourceFor('mag-position-gesture')
  setOpen(r, true)
  goTab(r, 'Conversation')
  r.update({ places: { ...r.snapshot().places, Conversation: { ...place(r.snapshot()), scroll: 400 } } })
  const el = new Container()
  el.height = 93
  const f = frame(r, el)
  f.applySaved()
  assert.equal(f.kept(), 400)
  f.readerMoved()
  assert.equal(f.kept(), null)
  el.scrollTop = 40                                // the reader's own gesture moves it
  assert.equal(f.reported(el.scrollTop), true, 'their own position is saved')
  assert.equal(place(r.snapshot()).scroll, 40)
  f.grew(1200)
  assert.equal(el.scrollTop, 40, 'and growing content does not pull them back')
})

test('pendingScroll keeps only a position that was wanted and not reached', () => {
  assert.equal(pendingScroll(0, 0), null, 'the top is never waited for')
  assert.equal(pendingScroll(0, 400), 400)
  assert.equal(pendingScroll(400, 400), null)
  assert.equal(pendingScroll(399.6, 400), null, 'a fractional report that reached it')
  assert.equal(pendingScroll(0, -10), null, 'a nonsense position is not waited for')
  assert.equal(pendingScroll(0, Number.NaN), null)
  assert.equal(pendingScroll(0, 400.4), 400, 'and the kept position is rounded as the place is')
})

test('savesReportedScroll refuses only a report short of a position still waited for', () => {
  assert.equal(savesReportedScroll(null, 0), true)
  assert.equal(savesReportedScroll(null, 93), true)
  assert.equal(savesReportedScroll(400, 93), false)
  assert.equal(savesReportedScroll(400, 400), true)
  assert.equal(savesReportedScroll(400, 900), true, 'a reader who has gone further keeps their own')
})
