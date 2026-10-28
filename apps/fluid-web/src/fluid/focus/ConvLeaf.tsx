/* THE CONVERSATION IN A SECTION (types.ts): after a swap it can sit in a
 * leaf of the tree, with the section's caption and tools above it. The
 * conversation itself is the one drawn in the Shell, moved in here
 * (hosts.tsx), so its place in the posts and its draft come with it. */

import type { Zone } from '../workspace/tree'
import { ZoneTools, type ZoneCtl } from '../workspace/TreeView'
import { Mount } from './hosts'
import { CONVERSATION_ID } from './types'

export default function ConvLeaf({ z, ctl }: { z: Zone; ctl: ZoneCtl }) {
  const name = z.name ?? 'Conversation'
  return (
    <section className="wk-zone wk-panel fq-conv-leaf" aria-label={`${name} section`} data-zone="conversation" data-zone-name={name}>
      <div className="wk-zcap">
        <span className="wk-what">{name}</span>
        <span className="wk-grow" />
        <ZoneTools ctl={ctl} name={name} />
      </div>
      <div className="wk-zbody fq-conv-body">
        <Mount id={CONVERSATION_ID} />
      </div>
    </section>
  )
}
