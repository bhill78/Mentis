import { useState } from 'react'
import { post } from '../api'
import { useWorkflows } from '../fluid/composer/useWorkflows'
import type { WorkflowView } from './contract'
import { activityWords, changeBody, changePath, eventWords, evidenceWords, originWords } from './workflow'

/** THE WORKFLOW OF ONE PIECE OF WORK, in the Work drawer: what governs it now
 *  and how it came to, the activity progress the server computes, every
 *  change with its reason and evidence, and -- for the owner -- a way to
 *  change it. Nothing here moves the work on; a change is recorded, and the
 *  work's next run is composed with the new Workflow. */
export function WorkflowSection({ view, expectation, owner, onChanged }: {
  view: WorkflowView | undefined
  expectation: string
  /** The owner is looking: the change control is offered. */
  owner: boolean
  onChanged: () => void
}) {
  const [open, setOpen] = useState(false)
  if (!view) return null
  const changes = view.history.filter((e) => e.kind === 'changed').length
  return (
    <section className="work-workflow" aria-label="Workflow">
      <h3 className="work-section-title">Workflow</h3>
      <dl className="work-kv">
        <dt>Current</dt>
        <dd>{view.current.length ? view.current.map((w) => w.name ?? w.entry).join(', ') : 'None'}
          <span className="work-muted"> · {originWords(view)}</span></dd>
        {changes > 0 && <><dt>Changed</dt><dd>{changes === 1 ? 'once' : `${changes} times`}</dd></>}
      </dl>
      {view.why_unknown && <p className="work-muted">Unknown — {view.why_unknown}</p>}

      {view.progress.map((wf) => <div className="work-wf-progress" key={wf.entry}>
        <div className="work-muted">{wf.name || wf.entry} · activities</div>
        <ol>
          {wf.activities.map((a) => <li key={a.key}>
            <span>{a.what || a.key}</span>
            <span className="work-muted"> — {activityWords(a.children, a.said)}</span>
          </li>)}
        </ol>
        {wf.elsewhere > 0 && <p className="work-muted">{wf.elsewhere} delegated part{wf.elsewhere === 1 ? '' : 's'} name no activity of it</p>}
      </div>)}
      {view.progress_why && <p className="work-muted">Progress unknown — {view.progress_why}</p>}

      <details className="work-wf-history" open={changes > 0}>
        <summary>History ({view.history.length})</summary>
        <ol>
          {view.history.map((e, i) => <li key={e.kind === 'changed' ? e.act : `asked-${i}`}>
            <div>{eventWords(e)}{e.at && <span className="work-muted"> · {stamp(e.at)}</span>}</div>
            {e.kind === 'changed' && <>
              {e.because && <div className="work-wf-because">“{e.because}”</div>}
              {e.evidence.length > 0 && <div className="work-muted">Evidence: {e.evidence.map(evidenceWords).join(', ')}</div>}
            </>}
          </li>)}
        </ol>
      </details>

      {owner && (open
        ? <ChangeForm expectation={expectation} current={view.current.map((w) => w.entry)}
            onDone={() => { setOpen(false); onChanged() }} onCancel={() => setOpen(false)} />
        : <button className="work-link" onClick={() => setOpen(true)}>Change Workflow…</button>)}
    </section>
  )
}

function ChangeForm({ expectation, current, onDone, onCancel }: {
  expectation: string; current: string[]; onDone: () => void; onCancel: () => void
}) {
  const workflows = useWorkflows(true).filter((w) => !current.includes(w.entry))
  const [workflow, setWorkflow] = useState('')
  const [because, setBecause] = useState('')
  const [evidence, setEvidence] = useState('')
  const [said, setSaid] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [op] = useState(() => `wf-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`)
  const send = async () => {
    const got = changeBody(workflow, because, evidence, op)
    if ('why' in got) { setSaid(got.why); return }
    setSending(true)
    try {
      await post(changePath(expectation), got.body)
      onDone()
    } catch (e) {
      setSaid(e instanceof Error ? e.message : String(e))
    } finally { setSending(false) }
  }
  return (
    <form className="work-wf-change" onSubmit={(e) => { e.preventDefault(); void send() }}>
      <label>Change to
        <select value={workflow} onChange={(e) => setWorkflow(e.target.value)}>
          <option value="">Choose a Workflow…</option>
          {workflows.map((w) => <option key={w.entry} value={w.entry}>{w.name}</option>)}
        </select>
      </label>
      <label>Why
        <textarea rows={2} value={because} onChange={(e) => setBecause(e.target.value)}
          placeholder="what the work turned out to be" />
      </label>
      <label>Evidence
        <input value={evidence} onChange={(e) => setEvidence(e.target.value)}
          placeholder="ent-… or opr-… references, space separated" />
      </label>
      <p className="work-muted">Changes the Workflow only. What this work may do, its consent and its follow-up permission stay as they are; nothing is started.</p>
      {said && <p role="alert">{said}</p>}
      <div className="work-decision-actions">
        <button type="submit" disabled={sending}>{sending ? 'Changing…' : 'Change Workflow'}</button>
        <button type="button" className="work-link" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

function stamp(at: number) {
  return new Date(at * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
