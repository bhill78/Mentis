/* THE OBJECT, FLOATING-WINDOW AND MAGNET HOSTS. Round 5 bootstrap by S;
 * W2 mounts it, package O owns the body.
 *
 * O composes the hosts that already exist -- the detail, preview and media
 * views, the Floats and NarrowFloats, the DockLayer and LensLayer, the Magnet
 * discs with their Orbit, Summary, Expand and Peek -- scoped to the measured
 * `areaElement`, so a float cannot cover the Quiet composer or toolbar. It
 * copies none of those renderers.
 *
 * THE BOOTSTRAP MOUNTS NOTHING. Until O lands, an action needing one of these
 * hosts is UNAVAILABLE and says so (W2's refusal); an invisible float or Peek
 * that reported success would be the worst of the possible placeholders.
 */
import type { ObjectHostsView } from '../contract'
import './object-hosts.css'

const ObjectHosts: ObjectHostsView = () => null

export default ObjectHosts
