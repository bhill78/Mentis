/* WHICH BRAIN THE SERVER IS SERVING THIS PAGE NOW -- INSTANCE INCLUDED, AND
 * READ WHEN IT IS ASKED (independent re-review adm-af5263a65134, F1 and F2).
 *
 * TWO BLOCKING FINDINGS, ONE CAUSE: the hand-off asked the HOST for the Brain's
 * identity, and the host gave the wrong one, from the wrong place.
 *
 *   F2 -- THE WRONG IDENTITY. `Quiet2.tsx`'s `brain.key` is the 3D Brain's
 *   GRAPH key (`space/registry.ts` `spaceBrainKey`): the origin, the pinned
 *   proxy choice and the corpus id. A copy of the same corpus restored in
 *   place, or one served by another process at the same origin, has exactly
 *   that same graph key -- so a result saved against the old serving instance
 *   resumed happily against the new one. `launch.ts` has always documented its
 *   `BrainKey` as `<corpus>@<instance>`, which is `brainBinding.ts`'s key and
 *   not the graph's; the graph key simply does not hold the instance, and that
 *   is not a defect in the graph contract -- it is the wrong key for this one.
 *
 *   F1 -- THE WRONG PLACE. `() => brain.key ?? null` is built inside the host
 *   component, so it closes over THAT RENDER's `brain`. A pending read and an
 *   open chooser belong to the render that began them, and that render's getter
 *   goes on answering with the Brain that render saw -- however often the page
 *   is rebound afterwards, unless the centre also moves, which is the only
 *   thing `mount.ts`'s generation counts. Asking the page at all was the
 *   mistake: which Brain the server serves is not one render's state.
 *
 * SO IT IS NOT A HOST MEMBER ANY MORE. `brainBinding.ts`'s `page` binding is
 * already this page's one authority on the question: it is what every write
 * names in `X-Mentis-Brain`, what `confirmBrain` checks each read against, and
 * what a 409 `BrainChanged` moves. It is a MODULE store, so an old render's
 * closure reads today's answer through it exactly as it already reads today's
 * viewer store. Nothing is added to it here and nothing here binds, confirms or
 * moves anything: this is one reading of what it already holds.
 *
 * A MOVED PAGE HAS NO CURRENT BRAIN. Once another Brain has answered, the
 * binding stays moved until the page is reloaded, and what it is still `bound`
 * to is the Brain the page was OPENED on -- not the one being served. Answering
 * with that key would let every pending resume act exactly as before, which is
 * the whole of F1. So a moved page answers `null`, as a page that has not bound
 * yet does, and `brainVerdict` reads both as `unknown`: nothing saved is
 * replayed and nothing late is placed. Fail-closed, in the same direction as
 * the fresh read (B4.1).
 *
 * AND "NO CURRENT BRAIN" IS A STATE, NOT A BLANK (independent review
 * adm-1cb30e65d05f, F3). `null` was true of both states above and was read as
 * "nothing to compare" by the gates that matter, so a launch MADE in either
 * state was exempt from them: it placed, navigated and reported `opened`. The
 * answer this module gives is a `Serving` now -- `serving`, `unconfirmed` or
 * `moved` -- and `launch.ts` `mayAct` acts on the first alone. The key form is
 * kept beside it for the two things that hold a key and have always refused a
 * missing one themselves: the saved history entry and the resume.
 *
 * NOTHING IS ADDED TO THE BINDING AND NOTHING HERE BINDS. `unconfirmed` is
 * `bound() === null`: before the page's first `confirmBrain` answers, and on a
 * page that never asks at all. Which pages ask is `brainBinding.ts`'s and
 * `live.ts`'s business, not this module's, and this module does not make a host
 * that never binds safe -- it makes it REFUSE, and `HOST-INTEGRATION.md` §5
 * says so in the wiring rather than leaving it to be discovered.
 *
 * Checked in `tests/quiet2_result_serving_unit.ts` against the real binding. */
import { page as pageBinding, type Binding } from '../../brainBinding'
import { servingKey, type BrainKey, type Serving } from './launch'

/** WHICH OF THE THREE A BINDING IS IN. A moved page is `moved` even though it
 *  is still `bound` to the Brain it was opened on: what it was opened on is not
 *  what is being served, and only a reload binds it again. */
export const servingOf = (binding: Binding): Serving => {
  if (binding.moved()) return { how: 'moved' }
  const key = binding.bound()
  return key ? { how: 'serving', key } : { how: 'unconfirmed' }
}

/** THIS PAGE'S OWN, for every result decision that names a Brain. A plain
 *  module read, so a closure made by an earlier render sees it too. */
export const servingNow = (): Serving => servingOf(pageBinding)

/** THE BRAIN A BINDING SAYS IS BEING SERVED NOW, or null where it has no
 *  current answer: it has not bound yet, or another Brain has answered since
 *  and only a reload binds it again. */
export const servingKeyOf = (binding: Binding): BrainKey | null => servingKey(servingOf(binding))

/** THIS PAGE'S OWN KEY, for the history entry and the resume. A launch still
 *  names it, and a launch that names none is refused by `mayAct` rather than
 *  exempted by it (F3). */
export const servingBrainKey = (): BrainKey | null => servingKey(servingNow())
