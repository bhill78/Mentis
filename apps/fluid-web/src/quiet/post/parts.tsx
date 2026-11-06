/* PACKAGE E owns this module: what one part of a post's body becomes. Text
   goes through Prose, untrusted, as it always has. Anything that is a file or
   an image is F's, through MediaPart -- so E never decides how media looks and
   F never touches the post's own markup. */
import { Prose } from '../../prose'
import type { Part } from '../../api'
import MediaPart from '../media/MediaPart'

export default function PostPart({ part, scope }: { part: Part; scope: string }) {
  if (part.type === 'text') return <Prose src={part.text ?? ''} scope={scope} untrusted />
  if (part.type === 'topic_ref' && part.text) return <span>{part.text}</span>
  if (part.artifact?.state === 'held' && part.artifact.url) return <MediaPart part={part} scope={scope} />
  // Retain authored non-text references without importing Fluid's object surfaces.
  return <p className="qc-context">{part.text || part.alt || part.ref || part.type}</p>
}
