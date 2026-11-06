/* PACKAGE G owns this module. At P0 it renders the ground exactly as Quiet
   rendered it before the split: the `.qc` element and the fixed image layer
   behind it, whose paint is in surface.css. G replaces the body of this file
   with the atmospheres and the solid/glass treatments; the element it mounts,
   and the class the rest of the shell is laid out by, do not change. */
import type { ReactNode } from 'react'
import './surface.css'

export default function Surface({ children }: { children: ReactNode }) {
  return <div className="qc">{children}</div>
}
