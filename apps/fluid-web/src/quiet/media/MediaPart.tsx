/* PACKAGE F owns this module: a part that is a file or an image. At P0 it is
   the bare link Quiet showed before the split -- which is the defect §6
   reports: an image arrives as `image.png ↗` instead of as a picture.

   WHAT F CHANGES. An image part renders as an image; the images in a post
   form a gallery with previous / next / Escape, focus trapped while open and
   returned to the opener on close, opened through MediaLayer; a non-image
   attachment states its name, type and size and names its originating post,
   and still reaches part.artifact.url. Built on `fluid/render/inspect.ts`,
   which is pure -- Fluid's viewer.tsx is bound to its store and cannot be
   mounted here. */
import type { Part } from '../../api'
import './media.css'

export default function MediaPart({ part }: { part: Part; scope: string }) {
  return <p><a href={part.artifact?.url}>{part.alt || part.artifact?.name || part.ref} ↗</a></p>
}
