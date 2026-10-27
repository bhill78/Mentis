import { cancelRun } from '../route'
// Said at the control that opened the native picker, not across the page: the page is only dimmed.
export default function WaitingForDialog({ runKey }: { runKey?: string }) {
  return <span className="src-dialog-wait" role="status"><span className="src-dialog-dot" aria-hidden="true" />
    <span title="Can't see it? It may be behind this browser window.">Waiting for the Windows picker…</span>
    <button className="link" disabled={!runKey} onClick={() => runKey && void cancelRun(runKey)}>Cancel</button></span>
}
