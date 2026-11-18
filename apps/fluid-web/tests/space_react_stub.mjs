/* ------------------------------------------------------------------------ *
 * A HOOK RUNTIME SMALL ENOUGH TO READ.
 *
 * Why this exists: the 3D Brain's camera lifetime is decided in a component's
 * render body and its effects, and the only checks the repository had of that
 * were regular expressions over BrainSpace.tsx's characters. An expression
 * matched the exact text of a gate that never opened, so a green suite
 * reported that the eye flew to what you chose while it did not
 * (review adm-425121b18a7f, findings A-1 and A-2).
 *
 * So: a test loads the REAL component, this stands in for `react` and
 * `react/jsx-runtime`, and the component is mounted, re-rendered, remounted
 * and unmounted while its real effects run. It is not React and does not try
 * to be: no concurrency, no batching of its own, no DOM. It renders function
 * components depth-first, keeps each one's hooks where they were, runs effects
 * child-before-parent after a pass, and runs their cleanups when deps change
 * or the component goes away. That is enough to see what a camera does.
 *
 * What a test may NOT conclude from it: anything about painted pixels, layout
 * or real browser scheduling. Those belong to browser evidence.
 * ------------------------------------------------------------------------ */

const EL = Symbol('element')
export const Fragment = Symbol('Fragment')

export const jsx = (type, props, key) => ({ [EL]: true, type, props: props ?? {}, key })
export const jsxs = jsx
export const createElement = (type, props, ...kids) =>
  jsx(type, { ...(props ?? {}), ...(kids.length ? { children: kids.length === 1 ? kids[0] : kids } : {}) })
export const isElement = (v) => Boolean(v && typeof v === 'object' && v[EL] === true)

/* ---- hooks -------------------------------------------------------------- */

let current = null
let dirty = false
let ids = 0

const slot = () => {
  const inst = current
  if (!inst) throw new Error('a hook was called outside a render')
  const i = inst.at++
  return inst.hooks[i] ?? (inst.hooks[i] = {})
}
const same = (a, b) =>
  Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => Object.is(v, b[i]))

export function useRef(init) {
  const s = slot()
  if (!s.ref) s.ref = { current: init }
  return s.ref
}

export function useState(init) {
  const s = slot()
  if (!s.held) {
    s.held = true
    s.v = typeof init === 'function' ? init() : init
    s.set = (next) => {
      const v = typeof next === 'function' ? next(s.v) : next
      if (Object.is(v, s.v)) return
      s.v = v
      dirty = true
    }
  }
  return [s.v, s.set]
}

export function useMemo(fn, deps) {
  const s = slot()
  if (!s.held || !same(s.deps, deps)) {
    s.held = true
    s.v = fn()
    s.deps = deps
  }
  return s.v
}

export const useCallback = (fn, deps) => useMemo(() => fn, deps)

export function useEffect(fn, deps) {
  const s = slot()
  s.effect = true
  s.pending = { fn, deps }
}
export const useLayoutEffect = useEffect

export function useId() {
  const s = slot()
  if (!s.v) s.v = `:s${(ids += 1)}:`
  return s.v
}

/* Subscribed once per mounted hook; a change asks for another pass, which is
   what useSyncExternalStore does for a store that is not React's. */
export function useSyncExternalStore(subscribe, getSnapshot) {
  const s = slot()
  if (!s.unsub) {
    s.store = true
    s.unsub = subscribe(() => {
      dirty = true
    })
  }
  return getSnapshot()
}

/* A BOUNDARY AND A LAZY CHILD, enough to mount a component that defers a
   large module (the graph). `Suspense` renders its children; `lazy` stands for
   the module while it is not loaded, which is where a test of the HOST's own
   chrome wants it: what the deferred module draws is its own test's business.
   `loaded()` names what was deferred, so a test can say it was mounted. */
export const Suspense = ({ children }) => children
export const lazy = (load) => {
  const Lazy = () => null
  Lazy.loads = load
  return Lazy
}

/* ---- the renderer ------------------------------------------------------- */

const root = { hooks: [], kids: new Map(), at: 0 }
let element = null
let rendered = []

const own = (parent, key, type) => {
  const got = parent.kids.get(key)
  if (got && got.type === type) return got
  if (got) drop(got)
  const made = { type, hooks: [], kids: new Map(), at: 0 }
  parent.kids.set(key, made)
  return made
}

function drop(inst) {
  for (const kid of inst.kids.values()) drop(kid)
  inst.kids.clear()
  for (const s of inst.hooks) {
    if (s.cleanup) {
      s.cleanup()
      s.cleanup = null
    }
    if (s.unsub) {
      s.unsub()
      s.unsub = null
    }
  }
  inst.hooks.length = 0
}

function walk(node, holder, key) {
  if (node === null || node === undefined || typeof node === 'boolean') return null
  if (typeof node === 'string' || typeof node === 'number') return node
  if (Array.isArray(node)) return node.map((n, i) => walk(n, holder, `${key}.${i}`))
  if (!isElement(node)) return null
  const { type, props } = node
  const named = typeof type === 'function' ? type.name || 'anon' : String(type)
  const here = `${key}/${node.key ?? ''}${named}`
  if (typeof type === 'function') {
    const inst = own(holder, here, type)
    inst.at = 0
    const was = current
    current = inst
    let out
    try {
      out = type(props)
    } finally {
      current = was
    }
    inst.props = props
    inst.out = walk(out, inst, here)
    rendered.push(inst) // after its children: effects run child before parent
    inst.seen = true
    return { type, props, inst, out: inst.out }
  }
  return { type, props, out: walk(props?.children, holder, here) }
}

function sweep(inst) {
  for (const [key, kid] of [...inst.kids]) {
    if (!kid.seen) {
      drop(kid)
      inst.kids.delete(key)
      continue
    }
    kid.seen = false
    sweep(kid)
  }
}

let tree = null

function pass() {
  rendered = []
  tree = walk(element, root, '')
  sweep(root)
  for (const inst of rendered) {
    for (const s of inst.hooks) {
      if (!s.effect || !s.pending) continue
      const { fn, deps } = s.pending
      s.pending = null
      if (s.ran && same(s.deps, deps)) continue
      if (s.cleanup) {
        s.cleanup()
        s.cleanup = null
      }
      s.ran = true
      s.deps = deps
      const back = fn()
      s.cleanup = typeof back === 'function' ? back : null
    }
  }
}

/** Render this element at the root and settle: keep passing while something
 *  a pass did asked for another, as a real renderer would. */
export function render(el) {
  element = el
  let rounds = 0
  do {
    dirty = false
    pass()
    rounds += 1
  } while (dirty && rounds < 50)
  if (dirty) throw new Error('renders did not settle')
  return tree
}

/** Do something from outside (a click, a key, a frame) and settle after it. */
export function act(fn) {
  const out = fn()
  let rounds = 0
  while (dirty && rounds < 50) {
    dirty = false
    pass()
    rounds += 1
  }
  if (dirty) throw new Error('renders did not settle')
  return out
}

export function unmount() {
  element = null
  for (const [key, kid] of [...root.kids]) {
    drop(kid)
    root.kids.delete(key)
  }
  tree = null
}

/** The rendered tree, walked: every element of this type, in render order. */
export function find(type, from = tree) {
  const got = []
  const seek = (node) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) return node.forEach(seek)
    if (node.type === type) got.push(node)
    seek(node.out)
  }
  seek(from)
  return got
}

/** The first host element whose props match, for sending it an event. */
export function one(type, from = tree) {
  const got = find(type, from)
  if (!got.length) throw new Error(`nothing of type ${String(type)} is rendered`)
  return got[0]
}

export const rendering = () => tree
