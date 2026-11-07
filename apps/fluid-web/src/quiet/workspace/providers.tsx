/* WHAT EVERYTHING INSIDE THE WORKING STAGE NEEDS. Round 5 bootstrap by S;
 * package W2 owns the body.
 *
 * W2 supplies the COMPLETE inventory the plan's F1 lists: the real
 * GovContext, Actions targeted at the effective conversation, Shell's
 * ToastView lifted onto the existing `frame/toasts.ts` store with its
 * actionable Undo, one frame Layer with its `fx-layer` portal target for
 * Sheets, menus and the Keep chooser, the ActionPalette, and the idempotent
 * `installProviders()` for the hosted registry actions. None of that is
 * copied: they are the mechanisms Fluid already has.
 *
 * THE BOOTSTRAP PROVIDES NOTHING AND PRETENDS NOTHING. It renders its
 * children so the tree has the right shape from the first commit; a
 * placeholder GovContext or Actions would answer a consumer with a fake
 * permission, a fake owner or a fake success, which is the one failure mode
 * none of these are allowed (no invisible successful action). A consumer that
 * needs a real host before W2 lands finds it absent, which is the truth.
 */
import type { WorkingProvidersView } from '../contract'

export const WorkingProviders: WorkingProvidersView = ({ children }) => children ?? null

export default WorkingProviders
