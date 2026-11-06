/* PACKAGE D owns this module: what is running here, and what each run is on.
   At P0 it is the summary Quiet showed before the split, mounted in B's
   margin.

   THE NO-OP QUERY IS GONE. `?runs=true` was never read by /api/activity --
   runs are always computed -- so this read asks for the path plainly
   (ent-dffb798c7e65). `api.ts` now declares the run shape the server really
   sends, so D reads `activity`, `stopping`, `permission(s)`, `live` and each
   run's own `conversation` without widening a frozen file.

   WHAT D CHANGES. §5 asks for two runs side by side, each with its activity,
   runtime, model, permission mode and the feed's usage keys; detailed
   operations and permission history openable in place; this conversation's
   work told apart from Mentis's at large (`workingIn(all, here)`, which keeps
   the `working_on.conversation` fallback the filter below drops); and a stop
   control where the run is shown. */
import { useApi, type Activity, type Id } from '../../api'
import { href } from '../model'
import { ReadState } from '../read'
import './activity.css'

export default function ActivityPanel({ conversation, topic }: { conversation: Id; topic: Id | null }) {
  const read = useApi<Activity>('/api/activity')
  const rows = read.data?.activity.filter((a) => a.has_live_execution && a.conversation === conversation) ?? []
  return <><ReadState loading={read.loading} error={read.error} reload={read.reload} />
    {read.data && !rows.length && <p className="qc-muted">No active agents reported here.</p>}
    {rows.map((a) => <div className="qc-activity" key={a.participant}><strong>{a.alias}</strong>
      {a.runs?.map((run) => <p key={run.run}>{run.words}</p>)}
      {a.working_on?.turn ? <a href={href(conversation, topic, a.working_on.turn)}>Working on #{a.working_on.number ?? 'post'} →</a>
        : <p>{a.working_on_gap || 'The record does not name a post.'}</p>}</div>)}
  </>
}
