/* THE ORDINARY CONVERSATION WRITE, AND WHAT IT NAMES.
 *
 * `POST /fluid/api/posts` is the write every conversation composer makes, and
 * it was the one submission path that named no Brain (focused independent
 * re-review ent-427a0f9ea610, residual B1-F2 / R1). The other two were closed:
 * a workspace's ask names the Brain its values were placed against
 * (`workspaces/client.ts`, `sendRequest`), and Quiet Chat's own writes are
 * named by the write guard it installs (`brainBinding.ts`, `guardWrites`).
 * A conversation composer on a page that installs NO guard -- legacy Fluid,
 * still served at `/fluid` -- wrote unnamed, and the draft is kept for the tab
 * by WHERE it is written, so a Quiet draft restored into that page keeps the
 * concrete Allow All, "may coordinate" and side-work depth it was filled in
 * with on the Brain it was written on (`seedable`: a restored draft is what
 * the owner left, values and all). A server that came to serve another Brain
 * between the asking and the writing therefore recorded one Brain's
 * permissions in another Brain's Work.
 *
 * So this write NAMES WHAT THE SUBMISSION WAS PLACED AGAINST
 * (`useDefault.ts`, `Sending.brain`), through the same header and the same
 * server check as the other two paths (`mentis/web/__init__.py`,
 * `_other_brain`: 409 `BrainChanged`, before anything is read of the body or
 * written). Nothing here is a new authorisation mechanism: it is the existing
 * check, asked on the path that was not asking it.
 *
 * A BODY CARRYING NOTHING SCOPED NAMES NO BRAIN and goes exactly as it always
 * did -- no default filled in, or what was filled in left out again.
 *
 * AND IT FAILS CLOSED RATHER THAN WIDENING QUIETLY (`unnamed`): a body that
 * still carries values placed for a Brain, with no Brain to name them, is NOT
 * SENT. A binding that went stale or an ask that failed resolves to no Brain
 * (`brainNow`), and the submission such an answer places carries nothing of
 * that Brain's -- but where the two ever disagree, the write is refused rather
 * than left to leave unnamed, which is the shape the defect had. */

import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, page, refusedAsOtherBrain } from '../../brainBinding'
import type { Draft } from '../../composer/draft'
import { fluidFetch } from '../http'
import { filledIn } from './permissionDefault'

export const POSTS_PATH = '/fluid/api/posts'

/** What a write carrying placed values with no Brain to name comes to: NOT
 *  SENT. The words, the people, the attachments and the owner's own choices
 *  are untouched -- the draft is only dropped once the post is in. */
export const UNNAMED_POST = 'Nothing was sent: this page cannot say which Brain the permission settings in this draft belong to, '
  + 'so nothing was recorded anywhere. Your words and your own choices are kept — check the permissions and send again.'

/** The server having come to serve another Brain, where it said so without words of its own. */
export const MOVED_POST = 'Nothing was recorded: this server now serves another Brain than this post was prepared for. '
  + 'Reload for the Brain it serves; your words are still here.'

/** A SUBMISSION THAT CARRIES PLACED VALUES AND NAMES NO BRAIN -- asked of the
 *  draft the body is built from, which is where the values are (the draft's
 *  own Ask Mentis selections, and every addressee that took a copy of them:
 *  `filledIn`). True is a write that must not leave. */
export const unnamed = (built: Draft, brain: string | null): boolean => filledIn(built) && brain === null

/** THE ORDINARY POST, NAMING THE BRAIN IT WAS PLACED AGAINST where its body
 *  carries anything scoped to one. The answer, or an Error with what the owner
 *  is to be told; a refusal as another Brain's also moves the page, so nothing
 *  scoped goes again until it is reloaded -- the same thing a guarded page's
 *  own writes and a workspace's ask come to. */
export async function sendPost(body: Record<string, unknown>, built: Draft, brain: string | null): Promise<Record<string, unknown>> {
  if (unnamed(built, brain)) throw new Error(UNNAMED_POST)
  const res = await fluidFetch(POSTS_PATH, {
    method: 'POST',
    headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json', ...(brain ? { [BRAIN_HEADER]: brain } : {}) },
    body: JSON.stringify(body),
  })
  const got = await res.json().catch(() => null) as Record<string, unknown> | null
  if (refusedAsOtherBrain(res.status, got)) {
    page.move()
    throw new Error(typeof got?.error === 'string' ? got.error : MOVED_POST)
  }
  if (!res.ok || !got || got.error) throw new Error((typeof got?.error === 'string' ? got.error : null) ?? res.statusText)
  return got
}
