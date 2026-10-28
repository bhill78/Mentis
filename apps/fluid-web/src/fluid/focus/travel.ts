/* TRAVELLING FLOATS ACROSS PAGES (page-level Fluid Focus).
 *
 * A float of ONE object (isObjectZone) is the owner's, not a page's: it
 * stays over whichever page is shown. Switching pages moves every object
 * float onto the page arrived at (gatherTravel). They are never saved in
 * any page's layout (session-local mentis.fluid.travel, as between
 * conversations).
 *
 * Section floats, run floats and the conversation's float are page-owned
 * and stay with their page. */

import { useEffect } from 'react'
import type { Arr } from '../workspace/place'
import { useArr, workspace } from '../workspace/place'
import { useNav } from '../workspace/hooks'
import { allPageViews, pageIn, pageView, shownPage, withPageView } from './page'
import { carryObjectFloats, leaveObjectFloats, objectFloatsOf } from './model'

/** Move every object float from other pages onto page `page` (the page shown,
 *  unless named): at the same rectangle, front-most order kept, never twice
 *  the same address on a page, never past MAX_FLOATS. Their origin and
 *  zone.options.from are dropped. Page-owned floats (section, run,
 *  conversation) stay with their page. Returns `a` itself when nothing moves. */
export function gatherTravel(a: Arr, page: string = shownPage()): Arr {
  const target = pageIn(a, page)
  const views = allPageViews(a)
  const others = views.filter((v) => v.page !== target)
  if (!others.some((v) => objectFloatsOf(v.view).length > 0)) return a

  let curr = a
  for (const other of others) {
    const v = pageView(curr, other.page)
    if (objectFloatsOf(v).length > 0) {
      curr = withPageView(curr, other.page, leaveObjectFloats(v))
    }
  }

  let targetView = pageView(curr, target)
  for (const other of others) {
    if (objectFloatsOf(other.view).length > 0) {
      targetView = carryObjectFloats(targetView, other.view)
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
