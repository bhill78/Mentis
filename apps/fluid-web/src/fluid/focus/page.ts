/* EVERY PAGE IS A WORKING SPACE (page-level Fluid Focus).
 *
 * A page -- This post, or one of the place's own pages (workspace/place.ts
 * `PageArr`) -- has its own Fluid Focus: its tree, what its column place
 * shows, its primary, its floats and its Esc history. This post's are the
 * arrangement's own `tree` and `focus`; another page's are its `PageArr.tree`
 * and `PageArr.focus`.
 *
 * The Focus model (model.ts) reads and writes `tree` and `focus` of an `Arr`.
 * Rather than teach every function about pages, a page is handed to it as a
 * VIEW: the arrangement with that page's tree and focus in those two places
 * (`pageView`), and what the model made of it written back to that page
 * (`onPage`). Every Focus interaction acts on the page shown through these,
 * so it works the same on every page. Nothing else of the arrangement (its
 * pages, width, look, pins) is touched through a view.
 *
 * Page identity (`PageArr.id`) is kept apart from a section's (`Zone.id`) and
 * from a content's (a live address kept in a slot): a page holds sections,
 * a section holds contents by reference.
 *
 * TRAVELLING FLOATS (model.ts, place.ts `TRAVEL`): a float of one object is
 * the owner's, not a page's. It is over whichever page is shown, so it is
 * kept in the shown page's focus and moved onto the page arrived at
 * (`gatherTravel`); no page's saved layout ever keeps it. */

import { useMemo } from 'react'
import * as nav from '../nav'
import type { Arr } from '../workspace/place'
import { useArr } from '../workspace/place'
import { useNav } from '../workspace/hooks'

export const THIS_POST = 'this-post'

/** The page shown now. */
export const shownPage = (): string => nav.snapshot().page

/** The page `page` names in `a`: itself, or This post when `a` has no such
 *  page (a page closed meanwhile). */
export const pageIn = (a: Arr, page: string): string =>
  page !== THIS_POST && a.pages.some((p) => p.id === page) ? page : THIS_POST

const views = new WeakMap<Arr, Map<string, Arr>>()
/** Page `page` of `a`, as the Focus model reads it: its tree in `tree`, its
 *  focus in `focus`. This post is `a` itself. The same view is returned for
 *  the same arrangement and page, so it can be a hook's dependency. */
export function pageView(a: Arr, page: string = shownPage()): Arr {
  const at = pageIn(a, page)
  if (at === THIS_POST) return a
  let byPage = views.get(a)
  if (!byPage) views.set(a, (byPage = new Map()))
  const had = byPage.get(at)
  if (had) return had
  const p = a.pages.find((x) => x.id === at)!
  const { focus: _thisPost, setAside: _thisPostSetAside, ...rest } = a
  const v: Arr = { ...rest, tree: p.tree, ...(p.focus ? { focus: p.focus } : {}), ...(p.setAside?.length ? { setAside: p.setAside } : {}) }
  byPage.set(at, v)
  return v
}

/** `v` (a view of page `page`, as the model left it) written back into `a`. */
export function withPageView(a: Arr, page: string, v: Arr): Arr {
  const at = pageIn(a, page)
  if (at === THIS_POST) return v
  return {
    ...a,
    pages: a.pages.map((p) => {
      if (p.id !== at) return p
      const { focus: _old, setAside: _oldSetAside, ...rest } = p
      return { ...rest, tree: v.tree, ...(v.focus ? { focus: v.focus } : {}), ...(v.setAside?.length ? { setAside: v.setAside } : {}) }
    }),
  }
}

/** A Focus change made on page `page` (the page shown, unless named): for
 *  `workspace.edit(onPage((v) => makePrimary(v, id)))`. Unchanged, it
 *  returns `a` itself, so no step is made of nothing. */
export const onPage = (f: (v: Arr) => Arr, page: string = shownPage()) => (a: Arr): Arr => {
  const at = pageIn(a, page)
  if (at === THIS_POST) return f(a)
  const v = pageView(a, at)
  const next = f(v)
  return next === v ? a : withPageView(a, at, next)
}

/** Every page's view: This post first, then the place's own pages. */
export const allPageViews = (a: Arr): { page: string; view: Arr }[] =>
  [{ page: THIS_POST, view: a }, ...a.pages.map((p) => ({ page: p.id, view: pageView(a, p.id) }))]

/** The page shown, and its view of the workspace's arrangement. */
export function useShownView(): { page: string; view: Arr } {
  const a = useArr()
  const page = useNav().page
  return useMemo(() => ({ page: pageIn(a, page), view: pageView(a, page) }), [a, page])
}
