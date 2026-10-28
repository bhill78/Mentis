/* TRAVELLING FLOATS ACROSS PAGES (page-level Fluid Focus).
 *
 * A PINNED float (model.ts carryPinnedFloats) is the owner's, not a page's:
 * it stays over whichever page is shown. Switching pages moves every pinned
 * float onto the page arrived at (gatherTravel). They are never saved in
 * any page's layout (session-local mentis.fluid.travel, as between
 * conversations).
 *
 * Unpinned floats -- of an object, a post or a section -- and run floats and
 * the conversation's float are page-owned and stay with their page. */

import { useEffect } from 'react'
import type { Arr } from '../workspace/place'
import { useArr, workspace } from '../workspace/place'
import { useNav } from '../workspace/hooks'
import { allPageViews, pageIn, pageView, shownPage, withPageView } from './page'
import { carryPinnedFloats, leavePinnedFloats, pinnedFloatsOf } from './model'

/** Move every pinned float from other pages onto page `page` (the page shown,
 *  unless named): at the same rectangle, front-most order kept, never twice
 *  the same thing on a page, never past MAX_FLOATS. Their origin and
 *  zone.options.from are dropped. Unpinned floats stay with their page.
 *  Returns `a` itself when nothing moves. */
export function gatherTravel(a: Arr, page: string = shownPage()): Arr {
  const target = pageIn(a, page)
  const views = allPageViews(a)
  const others = views.filter((v) => v.page !== target)
  if (!others.some((v) => pinnedFloatsOf(v.view).length > 0)) return a

  let curr = a
  for (const other of others) {
    const v = pageView(curr, other.page)
    if (pinnedFloatsOf(v).length > 0) {
      curr = withPageView(curr, other.page, leavePinnedFloats(v))
    }
  }

  let targetView = pageView(curr, target)
  for (const other of others) {
    if (pinnedFloatsOf(other.view).length > 0) {
      targetView = carryPinnedFloats(targetView, other.view)
    }
  }

  return withPageView(curr, target, targetView)
}

/** Keep travelling floats on whichever page is shown: when the arrangement or
 *  the shown page changes, gather them onto the shown page. Uses `carryOver` so
 *  no undo step is created and the place is not marked touched. */
export function useTravelOnPage(): void {
  const arr = useArr()
  const page = useNav().page
  useEffect(() => {
    workspace.carryOver((a) => gatherTravel(a, page))
  }, [arr, page])
}
