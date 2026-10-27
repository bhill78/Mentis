import { useCallback, useEffect, useState, type DragEvent, type ChangeEvent } from 'react'
import { CLIENT_HEADERS } from '../../api'
import './ImportArchive.css'

interface ItemRef {
  id: string
  name?: string
  text?: string
  kind?: string
  table?: string
  state?: string
  reason?: string
  blocked_by?: string[]
}

interface ConflictRef {
  id: string
  type: string
  subject: string | null
  words: string
  blocks?: string[]
}

interface PreviewCounts {
  new?: number
  skipped?: number
  diverged?: number
  conversations?: number
  turns?: number
  identical?: number
  blocked?: number
  conflicts?: number
  evidence?: number
  stubs?: number
  blobs?: number
}

interface PreviewPlan {
  ok: boolean
  manifest_sha256: string
  origin?: Record<string, unknown>
  receiver?: Record<string, unknown>
  ledger_identical?: boolean
  counts: PreviewCounts
  new: ItemRef[]
  skipped: ItemRef[]
  diverged: ItemRef[]
  conversations: ItemRef[]
  turns: ItemRef[]
  conflicts: ConflictRef[]
  refused: string[]
  backup_dest: string
}

interface StagedStatus {
  staged: boolean
  staged_path?: string
  size?: number
  manifest_sha256?: string
  error?: string
}

export default function ImportArchiveTab() {
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [staging, setStaging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [plan, setPlan] = useState<PreviewPlan | null>(null)
  const [stagedStatus, setStagedStatus] = useState<StagedStatus | null>(null)

  const [openSection, setOpenSection] = useState<'convs' | 'turns' | 'skipped' | 'diverged' | null>('convs')

  const refreshStaged = useCallback(async () => {
    try {
      const res = await fetch('/api/exchange/import/stage', {
        headers: { ...CLIENT_HEADERS },
      })
      if (res.ok) {
        const data = (await res.json()) as StagedStatus
        setStagedStatus(data)
      }
    } catch {
      // Ignore network errors on background poll
    }
  }, [])

  useEffect(() => {
    void refreshStaged()
  }, [refreshStaged])

  const analyzeFile = async (f: File) => {
    setFile(f)
    setError(null)
    setSuccess(null)
    setPlan(null)
    setLoading(true)

    try {
      const arrayBuffer = await f.arrayBuffer()
      const res = await fetch('/api/exchange/import/preview', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/zip',
          ...CLIENT_HEADERS,
        },
        body: arrayBuffer,
      })

      const data = await res.json()
      if (!res.ok) {
        setError(data.error || 'Failed to preview archive.')
      } else {
        setPlan(data as PreviewPlan)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = () => {
    setDragging(false)
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const dropped = e.dataTransfer.files[0]
      if (dropped.name.endsWith('.zip') || dropped.type.includes('zip')) {
        void analyzeFile(dropped)
      } else {
        setError('Please drop a valid .zip Mentis archive file.')
      }
    }
  }

  const handleFileInput = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      void analyzeFile(e.target.files[0])
    }
  }

  const handleConfirmStage = async () => {
    if (!file) return
    setStaging(true)
    setError(null)

    try {
      const arrayBuffer = await file.arrayBuffer()
      const res = await fetch('/api/exchange/import/stage', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/zip',
          ...CLIENT_HEADERS,
        },
        body: arrayBuffer,
      })

      const data = await res.json()
      if (!res.ok) {
        setError(data.error || 'Failed to stage archive.')
      } else {
        setSuccess('Archive verified and successfully staged at .import-staged.zip for application on next restart!')
        void refreshStaged()
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setStaging(false)
    }
  }

  return (
    <div className="import-archive-wrap" role="region" aria-label="Import Archive">
      <div className="import-archive-header">
        <h3 className="import-archive-title">Import Mentis Archive</h3>
        <p className="import-archive-sub">
          Preview and stage an incoming Mentis archive (.zip). Reads and classifies incoming conversations, turns,
          and governed items under a shared read lock before staging changes to apply safely.
        </p>
      </div>

      {stagedStatus?.staged && (
        <div className="import-staged-banner" role="status">
          <div className="import-staged-info">
            <h4>Import Staged for Next Restart</h4>
            <p>
              Archive payload saved at <code>{stagedStatus.staged_path || '.import-staged.zip'}</code>
              {stagedStatus.size ? ` (${(stagedStatus.size / 1024).toFixed(1)} KB)` : ''}
              {stagedStatus.manifest_sha256 ? ` · ${stagedStatus.manifest_sha256.slice(0, 12)}` : ''}
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="import-error-banner" role="alert">
          <h4>Import Refused or Error</h4>
          <p>{error}</p>
        </div>
      )}

      {success && (
        <div className="import-success-banner" role="status">
          <p>{success}</p>
        </div>
      )}

      <div
        className={`import-dropzone ${dragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".zip,application/zip,application/x-zip-compressed"
          onChange={handleFileInput}
          aria-label="Select Mentis archive file (.zip)"
        />
        <span className="import-drop-icon" aria-hidden="true">📦</span>
        <div className="import-drop-text">
          {file ? file.name : 'Drop a Mentis archive (.zip) here, or browse files'}
        </div>
        <div className="import-drop-hint">
          {file ? `${(file.size / 1024).toFixed(1)} KB` : 'Only standard Mentis .zip archives with manifest'}
        </div>
        {file && (
          <div className="import-file-badge">
            <span>Selected: {file.name}</span>
          </div>
        )}
      </div>

      {loading && (
        <div className="fg-faint" style={{ textAlign: 'center', padding: '1rem' }}>
          Analyzing archive and classifying items against this Brain…
        </div>
      )}

      {plan && (
        <div className="import-preview-plan">
          <h4 style={{ margin: '0.5rem 0' }}>Itemized Preview Plan</h4>

          <div className="import-counts-grid">
            <div className="import-count-card">
              <div className="import-count-val">{plan.counts.conversations ?? plan.conversations.length}</div>
              <div className="import-count-label">Conversations</div>
            </div>
            <div className="import-count-card">
              <div className="import-count-val">{plan.counts.turns ?? plan.turns.length}</div>
              <div className="import-count-label">Turns</div>
            </div>
            <div className="import-count-card">
              <div className="import-count-val">{plan.counts.new ?? plan.new.length}</div>
              <div className="import-count-label">New Items</div>
            </div>
            <div className="import-count-card">
              <div className="import-count-val">{plan.counts.skipped ?? plan.skipped.length}</div>
              <div className="import-count-label">Skipped / Identical</div>
            </div>
            <div className="import-count-card">
              <div className="import-count-val">{plan.counts.diverged ?? plan.diverged.length}</div>
              <div className="import-count-label">Diverged</div>
            </div>
          </div>

          <div className="import-backup-banner">
            <span className="import-backup-title">Required Backup Destination:</span>
            <span className="import-backup-dest">{plan.backup_dest}</span>
            <span className="import-backup-note">
              A full verified backup will be recorded to this location before any changes are written.
            </span>
          </div>

          {plan.refused && plan.refused.length > 0 && (
            <div className="import-error-banner" role="alert">
              <h4>Archive Refused by Classification:</h4>
              <ul>
                {plan.refused.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="import-sections-accordion">
            <div className="import-acc-item">
              <button
                type="button"
                className="import-acc-trigger"
                onClick={() => setOpenSection(openSection === 'convs' ? null : 'convs')}
              >
                <span>Incoming Conversations ({plan.conversations.length})</span>
                <span>{openSection === 'convs' ? '▲' : '▼'}</span>
              </button>
              {openSection === 'convs' && (
                <div className="import-acc-content">
                  {plan.conversations.length === 0 ? (
                    <p className="fg-faint">No new conversations in archive.</p>
                  ) : (
                    plan.conversations.map((c) => (
                      <div key={c.id} className="import-item-row">
                        <span className="import-item-name">{c.name || c.id}</span>
                        <span className="import-item-id">{c.id}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            <div className="import-acc-item">
              <button
                type="button"
                className="import-acc-trigger"
                onClick={() => setOpenSection(openSection === 'turns' ? null : 'turns')}
              >
                <span>Incoming Turns ({plan.turns.length})</span>
                <span>{openSection === 'turns' ? '▲' : '▼'}</span>
              </button>
              {openSection === 'turns' && (
                <div className="import-acc-content">
                  {plan.turns.length === 0 ? (
                    <p className="fg-faint">No new turns in archive.</p>
                  ) : (
                    plan.turns.map((t) => (
                      <div key={t.id} className="import-item-row">
                        <span className="import-item-name">{t.text || 'Turn content'}</span>
                        <span className="import-item-id">{t.id}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            <div className="import-acc-item">
              <button
                type="button"
                className="import-acc-trigger"
                onClick={() => setOpenSection(openSection === 'diverged' ? null : 'diverged')}
              >
                <span>Diverged Items ({plan.diverged.length})</span>
                <span>{openSection === 'diverged' ? '▲' : '▼'}</span>
              </button>
              {openSection === 'diverged' && (
                <div className="import-acc-content">
                  {plan.diverged.length === 0 ? (
                    <p className="fg-faint">No diverged items.</p>
                  ) : (
                    plan.diverged.map((d) => (
                      <div key={d.id} className="import-item-row">
                        <div>
                          <span className="import-item-name">{d.kind || 'item'}</span>
                          <span className="import-item-reason"> · {d.reason}</span>
                        </div>
                        <span className="import-item-id">{d.id}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            <div className="import-acc-item">
              <button
                type="button"
                className="import-acc-trigger"
                onClick={() => setOpenSection(openSection === 'skipped' ? null : 'skipped')}
              >
                <span>Skipped / Identical Conflicts ({plan.skipped.length})</span>
                <span>{openSection === 'skipped' ? '▲' : '▼'}</span>
              </button>
              {openSection === 'skipped' && (
                <div className="import-acc-content">
                  {plan.skipped.length === 0 ? (
                    <p className="fg-faint">No skipped items.</p>
                  ) : (
                    plan.skipped.map((s) => (
                      <div key={s.id} className="import-item-row">
                        <div>
                          <span className="import-item-name">{s.kind || s.table || 'item'}</span>
                          <span className="import-item-reason"> · {s.reason || 'identical or blocked'}</span>
                        </div>
                        <span className="import-item-id">{s.id}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="import-actions">
            <button
              type="button"
              className="import-btn-primary"
              disabled={staging || (plan.refused && plan.refused.length > 0)}
              onClick={handleConfirmStage}
            >
              {staging ? 'Staging Import…' : 'Confirm and Stage Import'}
            </button>
            <button
              type="button"
              className="import-btn-secondary"
              disabled={staging}
              onClick={() => {
                setFile(null)
                setPlan(null)
                setError(null)
                setSuccess(null)
              }}
            >
              Choose Different Archive
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
