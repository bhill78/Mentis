/* THE TIDY CONTROL. Round 5 bootstrap by S; W2 mounts it at its one controls
 * point, package T owns the body.
 *
 * THE BOOTSTRAP DRAWS NOTHING, because there is nothing to tidy until W2 and
 * O have put floating surfaces in the area: a Tidy button over an empty stage
 * is a control that cannot do what it says. T draws it, keeps it reachable by
 * keyboard, and disables it with an explanation where no eligible floating
 * surface is drawn.
 */
import type { TidyView } from '../contract'

const Tidy: TidyView = () => null

export default Tidy
