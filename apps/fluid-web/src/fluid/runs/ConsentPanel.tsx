/* THE CONSENT IN FORCE ON A RUN (docs/run-consent.md §2, §6).
 *
 * Which operations of this work proceed without asking: the mode in the
 * server's words, how many workspaces, the tools allowed for this run only,
 * and the operations answered so far, each with who answered it and its
 * exact command under its details. Read from the run row (`consent`) and
 * from `GET /api/runs/<run>/consent` -- on opening, when the run ends, and
 * after every change.
 *
 * CHANGING IT IS THE OWNER'S, FOR WHAT COMES NEXT. A mode or a revoked tool
 * applies to subsequent operations; nothing already answered is undone. The
 * server records the change, and the panel shows what it reads back, never
 * what it asked for.
 *
 * SAID ONLY WHEN THE SERVER SAYS IT: a row without `consent` is an older
 * server, and the panel draws nothing new. */

import { useEffect, useState } from 'react'
import { ago, post, read } from '../../api'
import type { RunConsent } from '../../composer/execution'
import { store } from '../store'
import { BY_WORDS, CONSENT_MODES, CONSENT_TIP, consentLine, type ConsentRead } from './consent'

export default function Consent({ run, consent, ended }: { run: string; consent: RunConsent | null | undefined; ended?: boolean }) {
  const [got, setGot] = useState<ConsentRead | null>(null)
  const [busy, setBusy] = useState(false)
  const [why, setWhy] = useState<string | null>(null)
  const path = `/api/runs/${encodeURIComponent(run)}/consent`
  const reread = () => read<ConsentRead>(path).then(setGot).catch(() => {})
  const said = consent !== undefined
  useEffect(() => {
    if (!said) return
    let live = true
    void read<ConsentRead>(path).then((r) => { if (live) setGot(r) }).catch(() => {})
    return () => { live = false }
  }, [path, said, ended])
  const c = got?.consent ?? consent
  if (!said || !c) return null
  const change = async (body: Record<string, unknown>) => {
    if (busy) return
    setBusy(true)
    setWhy(null)
    try {
      await post(path, body)
    } catch (e) {
      setWhy(e instanceof Error ? e.message : String(e))
    } finally {
      await Promise.all([reread(), store.loadRuns([run], true).catch(() => {})])
      setBusy(false)
    }
  }
  const applied = got?.applied ?? c.applied
  const ops = got?.operations ?? []
  return (
    <div className="fr-consent" aria-label="the consent in force on this run">
      <div className="fr-consent-line">
        <span title={CONSENT_TIP + (c.source ? ` (${c.source.replace(/-/g, ' ')})` : '')}>{consentLine(c)}</span>
        {!ended && (
          <span className="fr-consent-modes" role="group" aria-label="change it for subsequent operations">
            {CONSENT_MODES.map((m) => (
              <button key={m.mode} type="button" aria-pressed={c.mode === m.mode} className={c.mode === m.mode ? 'on' : ''}
                disabled={busy || c.mode === m.mode} title={`${m.words}, for operations from now on`}
                onClick={() => void change({ mode: m.mode })}>
                {m.mode === 'ask' ? 'ask' : m.mode === 'task' ? 'routine proceeds' : 'never wait'}
              </button>
            ))}
          </span>
        )}
      </div>
      {!!c.tools?.length && (
        <div className="fr-consent-line">
          <span>Allowed for this run:</span>
          {c.tools.map((t) => (
            <span key={t} className="fr-consent-tool">
              {t}
              {!ended && <button type="button" disabled={busy} aria-label={`Revoke ${t} for this run`} title="Revoke: its operations are asked again"
                onClick={() => void change({ revoke_tool: t })}>✕</button>}
            </span>
          ))}
        </div>
      )}
      {applied?.enforced_by === 'none' && <p className="fr-note fr-error">This runtime does not ask before acting; consent cannot be enforced here.</p>}
      {why && <p className="fr-note fr-error">Not changed: {why}</p>}
      {ops.length > 0 && (
        <details>
          <summary>Operations answered ({ops.length})</summary>
          <ul>
            {ops.map((o, i) => (
              <li key={i} className={'fr-op fr-op-' + o.answer}>
                <details>
                  <summary>
                    <span className="fr-op-what">{o.operation.summary ?? o.operation.tool ?? 'an operation'}</span>
                    <span className="fr-op-by">{[o.answer, BY_WORDS[o.by] ?? o.by, o.operation.within === false ? 'outside the task' : null, ago(o.at)].filter(Boolean).join(' · ')}</span>
                  </summary>
                  {o.operation.command && <pre>{o.operation.command}</pre>}
                </details>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
