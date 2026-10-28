/* THE 3D BRAIN, AS ONE OF FLUID'S PLACES (`#/brain/space`, from the Brain
 * menu, as Mark IV had it).
 *
 * The drawing is Mark IV's own (surfaces/space/), carried across unchanged:
 * the field, its choosing, its strands and reach, its options and its chosen
 * card. What Fluid adds sits around it, never in it.
 *
 * Imported lazily by the Shell: nobody who never comes here loads it. */

import SpaceSurface from '../../surfaces/space/SpaceSurface'
import { goHome, type BrainDoors } from './address'
import './brain.css'

export default function BrainPlace({ doors }: { doors: BrainDoors }) {
  return (
    <SpaceSurface onOpen={(n) => goHome(n, doors)} />
  )
}
