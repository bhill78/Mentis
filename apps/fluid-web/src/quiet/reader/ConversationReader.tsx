/* THE READING ITSELF. Round 5 bootstrap by S; package R owns the body.
 *
 * R extracts the existing Flow, Thread and ConversationView out of the shell
 * into this module WITHOUT replacing their APIs, their history paging, the
 * draft builder or the composer: one `qc-stream`, one `qc-reading`, one
 * `qc-dock` and one composer, as there has always been.
 *
 * THE BOOTSTRAP DRAWS WHATEVER IT IS GIVEN AND NOTHING OF ITS OWN. A
 * placeholder reader that drew a reader would be a second reading of the
 * conversation; one that drew a message about itself would be a control the
 * owner never asked for. So it is the slot and no more, and it exists for one
 * reason: R can mount this name on day one and the manifest can hold it.
 */
import type { ReactNode } from 'react'

export default function ConversationReader(props: { children?: ReactNode }): ReactNode {
  return props.children ?? null
}
