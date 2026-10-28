/* THE CONVERSATION IN A SECTION (types.ts): after a swap it can sit in a
 * leaf of the tree, with the section's caption and tools above it. The
 * conversation itself is the one drawn in the Shell, moved in here
 * (hosts.tsx), so its place in the posts and its draft come with it.
 * Every page is kept drawn on the track (Workspace.tsx), but only the page
 * shown takes the conversation in: a page not shown keeps its section, quiet,
 * so it never takes the conversation from the place that shows it. */

import type { Zone } from '../workspace/tree'
import { ZoneTools, type ZoneCtl } from '../workspace/TreeView'
import { useArr } from '../workspace/place'
import { useNav } from '../workspace/hooks'
import { closeSheetPane, useNarrow } from '../frame/narrow'
import { Mount } from './hosts'
import { PlacedZone } from './ColumnPlace'
import { standIn } from './narrowView'
import { CONVERSATION_ID } from './types'
import { minimizeConversation } from './Launcher'
import { pageIn, pageView } from './page'

export default function ConvLeaf({ z, ctl, page }: { z: Zone; ctl: ZoneCtl; page: string }) {
  const name = z.name ?? 'Conversation'
  /* NARROW (narrowView.ts): the conversation is in the main column; this
     section shows what the column holds on the desktop, else says where the
     conversation is. */
  const narrow = useNarrow()
  const a = useArr()
  const shown = pageIn(a, useNav().page) === page
  const stand = narrow ? standIn(pageView(a, page)) : null
  if (stand) return (
    <section className="wk-zone wk-panel fq-conv-leaf fq-stand" aria-label={`${stand.name ?? 'Primary'} section`} data-zone-name={stand.name ?? 'Primary'}>
      <PlacedZone z={stand} page={page} why="Split it on a wider screen" />
    </section>
  )
  return (
    <section className="wk-zone wk-panel fq-conv-leaf" aria-label={`${name} section`} data-zone="conversation" data-zone-name={name}>
      <div className="wk-zcap">
        <span className="wk-what">{name}</span>
        <span className="wk-grow" />
        {/* Put away to the launcher: the section's room goes to its neighbour. */}
        <span className="wt-tools fq-min-tools"><button data-act="minimize" aria-label={`Minimize ${name}`} title="Minimize to the launcher (Undo brings it back)"
          onClick={() => minimizeConversation(page)}>–</button></span>
        <ZoneTools ctl={ctl} name={name} />
      </div>
      <div className="wk-zbody fq-conv-body">
        {narrow ? <ConvStub /> : shown && <Mount id={CONVERSATION_ID} />}
      </div>
    </section>
  )
}

/** Where the conversation is, at a narrow width: the main column. It can be
 *  drawn in one place only (hosts.tsx), so its section or float says so. */
export function ConvStub() {
  return (
    <div className="fq-conv-stub" role="note">
      <span>The conversation is in the main column.</span>
      <button type="button" className="fq-conv-stub-go" onClick={() => closeSheetPane()}>Show the conversation</button>
    </div>
  )
}
