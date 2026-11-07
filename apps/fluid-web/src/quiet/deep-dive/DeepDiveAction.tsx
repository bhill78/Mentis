/* DEEP DIVE, FROM A POST OR A PASSAGE. Round 5 bootstrap by S; R mounts it in
 * its post action slot, package D owns the body.
 *
 * THE OWNER'S DECISION (ent-721348be82db): a Deep dive opened from a post
 * appears as a PAGE IN THAT CONVERSATION'S PAGE SEQUENCE. So D calls the
 * EXISTING `actions.deepDive`, which creates a real separate conversation,
 * and then registers the returned conversation as a Page of the origin
 * through `nav.addPage(name, { kind: 'deep-dive' })` -- whose label and toast
 * `fluid/nav.ts` owns (F14). It does not invent a backend command and it does
 * not ask for the dive twice.
 *
 * WHERE THE SELECTION COMES FROM (F5). `body` is a live accessor for the
 * rendered post's body, and the Source is `quiet/annotations/words.ts`'s
 * `usePostSource(post.id)` -- the Source ACTUALLY DRAWN. D reconciles the
 * part, start and end against the loaded Fluid Post's version before making
 * the Place, keeping every text-part index and the UTF-16 alignment; it never
 * derives the drawn source from `sourceOf(FluidPost)`.
 *
 * THE BOOTSTRAP DRAWS NOTHING. An action that opened a reason form and then
 * created nothing would be a promise to the record that nothing kept.
 */
import type { DeepDiveActionView } from '../contract'

const DeepDiveAction: DeepDiveActionView = () => null

export default DeepDiveAction
