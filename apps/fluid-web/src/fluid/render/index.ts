/* WHAT CONTENT IS DRAWN AS, apart from where it is placed.
 *
 * A place -- the conversation column, the thread beside it, Home's column,
 * full screen, a zone, a preview, and later a floating or docked surface --
 * draws a post with `PostView` (or its pieces) and enlarges an object with
 * `inspect`. Neither knows the place: the place gives the element, the
 * reading, the scrolling and the selection, and says which `context` it is.
 * An object's own body is ObjectBody (workspace/), drawn at the size its
 * box allows by the present seam (present/). */

export {
  Actions, LATER, MoreChips, PinTag, PostBody, PostChips, PostHead, PostView, When, Where, Whole, Words, WorkOn,
  WorkStatusPill, WorkStatusProvider, filesOf, moreSheet, useActions,
  type Check, type PostActions, type PostContext,
} from './post'
export { inspectKey, inspectScope, stepIn, type InspectAction, type InspectAt, type InspectKey, type Listed } from './inspect'
export { closeInspect, inspect, useMediaOpen as useInspecting } from '../present/viewer'
export { default as ObjectBody } from '../workspace/ObjectBody'
