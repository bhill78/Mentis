import assert from 'node:assert/strict'
import { dropPart, padsFor } from '../src/fluid/focus/drag'
import { fitFloat } from '../src/fluid/focus/fitFloat'
import { clearOf, dockFloat, floatRun, RUN_SHOW } from '../src/fluid/focus/model'
import { Holder, type Arr } from '../src/fluid/workspace/place'
import { moveOf, pageLanding } from '../src/fluid/workspace/keep'
import { followSlot, keepSlot, zones, type Node, type Slot, type Zone } from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const rect = { x: 100, y: 80, w: 600, h: 400 }
eq(dropPart(rect, 620, 420), 'body', 'the whole section body places')
eq(dropPart(rect, 20, 20), 'outside', 'outside every section floats')
const left = padsFor(rect).find((p) => p.where === 'left')!
eq(dropPart(rect, left.x, left.y), 'left', 'an edge pad still splits')

const placed = { address: 'live:p:k', kept: true, page: 'p1', zone: 'shelf' }
eq(moveOf(placed, false), { page: 'p1', zone: 'shelf' }, 'an existing placement moves by default')
eq(moveOf(placed, true), undefined, 'Ctrl leaves the source placement as a copy')
eq(moveOf({ address: 'live:p:k' }, false), undefined, 'a followed object has no placement to remove')

const z = (id: string, slot: Slot): Zone => ({ type: 'zone', id, name: id, show: 'objects', slot })
const feed = { ...keepSlot(), feed: { source: 'actions' } } as Slot
const pages: Node = { type: 'split', dir: 'row', sizes: [.3, .3, .4], kids: [z('read', followSlot()), z('feed', feed), z('shelf', keepSlot())] }
eq(pageLanding(pages)?.id, 'shelf', 'a tab lands in the first section with no feed')
eq(pageLanding({ type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('read', followSlot()), z('feed', feed)] }), null,
  'a tab asks for a new section when every section has a feed')

const room = { w: 1000, h: 700 }
const compact = fitFloat({ kind: 'compact', w: 180, h: 90 }, room)
const visual = fitFloat({ kind: 'visual', w: 620, h: 400 }, room)
const text = fitFloat({ kind: 'text', w: 1400, h: 1800 }, room)
ok(compact.w < visual.w && compact.h < visual.h, 'small forms open compact while diagrams open readably')
ok(text.w >= 560 && text.w <= 680, 'long text gets a comfortable reading width')
ok(text.x >= 0 && text.y >= 0 && text.x + text.w <= room.w && text.y + text.h <= room.h, 'initial rectangles stay in the viewport')
const image = fitFloat({ kind: 'image', w: 800, h: 400, aspect: 2 }, room)
ok(Math.abs((image.h - 42) / image.w - .5) < .02, 'images retain their own aspect ratio')

/* A new float asked for where one already sits steps clear of it, title line and all. */
const first = { x: 900, y: 140, w: 620, h: 420 }
const second = clearOf({ ...first }, [first])
ok(Math.abs(second.x - first.x) >= 16 || Math.abs(second.y - first.y) >= 16, 'a second float does not land on the first')
eq([second.w, second.h], [620, 420], 'stepping clear keeps its size')
const third = clearOf({ ...first }, [first, second])
ok(![first, second].some((o) => Math.abs(o.x - third.x) < 16 && Math.abs(o.y - third.y) < 16), 'nor a third on either')
eq(clearOf({ x: 40, y: 40, w: 300, h: 200 }, [first]), { x: 40, y: 40, w: 300, h: 200 }, 'a float with room of its own stays where asked')

/* A run docks as the same live-run zone, rather than becoming a generic feed
   slot. The pointer drag records its pre-drag arrangement as one Undo step. */
const runStart: Arr = { tree: z('contents', keepSlot()), pages: [] }
const runFloat = floatRun(runStart, 'run-17', '@Caretaker', { x: 44, y: 55, w: 460, h: 520 })
const beforeRunDock = structuredClone(runFloat)
const runFloatId = runFloat.focus!.floats![0].id
const runHolder = new Holder(() => runFloat)
runHolder.edit((a) => dockFloat(a, runFloatId, 'contents', 'bottom'))
const dockedRun = zones(runHolder.arr.tree).find((zone) => zone.show === RUN_SHOW)
eq(dockedRun?.options, { run: 'run-17', who: '@Caretaker' }, 'docking preserves the run identity for the live panel')
eq(runHolder.arr.focus?.floats ?? [], [], 'the docked run no longer has a floating copy')
eq(runFloat, beforeRunDock, 'docking does not mutate the prior arrangement')
runHolder.undo()
eq(runHolder.arr, beforeRunDock, 'Undo restores the exact run float and prior tree')

console.log(`fluid drop: ${checks} checks passed`)
