import { useState, useEffect, useRef } from 'react'
import { shortId } from '../../api'
import { bytes, count, type Choices, type LinkRow, type Preview, type RunView, type SweepResult } from './route'
import '../governance/ActDialogs.css'

/* ------------------------------------------------------------------------ *
 * THE PIECES EVERY SOURCE FLOW SHARES, written once.
 *
 * Preview is the PreviewSheet pattern: folder bytes are staged locally,
 * with nothing in the record or held store. Confirm is the ActDialog pattern: a "What happens"
 * sentence and one filled button that writes. Result is the ExecutionSheet
 * pattern: what the record now says, with absent, withheld, refused, not
 * examined and visible-not-selected KEPT APART -- never added together,
 * because each means something different about the source.
 * ------------------------------------------------------------------------ */

export function Tally({ cells }: { cells: [string | number, string][] }) {
  return (
    <div className="src-tally">
      {cells.map(([n, label]) => (
        <div key={label}>
          <b>{typeof n === 'number' ? count(n) : n}</b>
          <span>{label}</span>
        </div>
      ))}
    </div>
  )
}

/** A preview, read out. Nothing here was recorded and the banner says so. */
export function PreviewBody({
  p,
  revising,
  onDecisions,
  onDecisionEdit,
  onOffer,
}: {
  p: Preview
  revising?: boolean
  onDecisions?: (d: Record<string, 'include' | 'exclude'>, categories?: Choices) => void
  onDecisionEdit?: () => void
  onOffer?: (connector: string) => void
}) {
  const c = p.counts
  return (
    <div className="src-preview">
      <p className="src-banner">
        Preview only: source bytes are staged machine-locally. Nothing enters the record or held store until confirm.{' '}
        <span className="src-mono">{shortId(p.plan, 14)}</span> · exact
        {revising && p.revising && (
          <>
            {' '}
            · revising the scope from <code>{p.revising.from.include.join(' ')}</code> to{' '}
            <code>{p.revising.to.include.join(' ')}</code>
          </>
        )}
      </p>
      {p.capture_semantics && <p>{p.capture_semantics}. Confirm records this exact capture; later source changes belong to the next refresh.</p>}
      {(p.sensitive_columns?.length || p.partial_required) ? (
        <ColumnChoices key={'sqlite-' + p.plan} p={p} onPreview={onDecisions} onEdit={onDecisionEdit} />
      ) : null}
      {p.coverage && <details><summary>Table coverage</summary><ul>{Object.entries(p.coverage).map(([table, state]) => <li key={table}><code>{table}</code>: {state}</li>)}</ul></details>}
      {p.sensitive_files?.length ? (
        <SensitiveChoices key={p.plan} p={p} onPreview={onDecisions && ((d) => onDecisions(d, p.category_decisions))} onEdit={onDecisionEdit} />
      ) : null}
      {p.categories?.length ? (
        <CategoryChoices key={'c' + p.plan} p={p} onPreview={onDecisions && ((cs) => onDecisions(p.sensitive_decisions ?? {}, cs))} onEdit={onDecisionEdit} />
      ) : null}
      {p.repository?.detected && <RepositoryOffer r={p.repository} onOffer={onOffer} />}
      {p.at && (
        <p className="src-faint">
          Read at <code>{p.at.ref}</code> <span className="src-mono">{p.at.commit.slice(0, 12)}</span>
          {p.at.remote && (
            <>
              {' '}
              from <span className="src-mono">{p.at.remote}</span>
            </>
          )}
        </p>
      )}
      {p.binding_note && <p className="src-banner att">{p.binding_note}</p>}
      <Tally
        cells={[
          [c.new, 'new'],
          [c.changed + c.reappeared, 'changed · reappeared'],
          [c.absent, 'absent'],
          [bytes(p.bytes_new_to_store), 'new to the store'],
        ]}
      />
      <Tally
        cells={[
          [c.not_acquired, 'not acquired (withheld)'],
          [c.refused, 'refused (links / junctions / Git metadata)'],
          [c.not_examined + c.unexamined, 'not examined'],
          [c.visible_not_selected, 'visible, not selected'],
        ]}
      />
      {(p.links.links_to > 0 || p.links.embeds > 0) && (
        <p className="src-note">
          {count(p.links.links_to)} links and {count(p.links.embeds)} embeds in what would be acquired.
          They are kept as authored and as resolved; a target outside the scope is reported as not
          acquired and is never fetched.
        </p>
      )}
      {p.evidence && (
        <section aria-label="Git change evidence">
          <Tally cells={[[p.evidence.change_records, 'change records'],
            [p.evidence.blobs, 'blobs'], [p.evidence.trees, 'trees'],
            [bytes(p.evidence.new_bytes), 'unique new evidence bytes']]} />
          <p className="src-note">Per-object limit: {p.evidence.limit_disclosed_label} ({bytes(p.evidence.limit_disclosed)}).
            {' '}{p.evidence.coverage.complete} complete records; {p.evidence.coverage.partial} partial records.</p>
          <details>
            <summary>Coverage of each change record</summary>
            <ul className="src-list">{p.evidence.coverage.records?.map((r) => (
              <li key={r.key}><code>{r.key}</code>: {r.status}
                {r.reasons.map((x) => `; ${x.id}: ${x.reason}`).join('')}</li>
            ))}</ul>
          </details>
          <Kept rows={[["Evidence withheld", "not held, with the reason",
            p.evidence.withheld.map((x) => `${x.key}: ${x.reason}`)]]} visible={null} noVisible />
        </section>
      )}
      {p.largest.length > 0 && (
        <p className="src-note">
          Largest:{' '}
          {p.largest.slice(0, 3).map((x, i) => (
            <span key={x.path}>
              {i > 0 && ' · '}
              <code>{x.path}</code> {bytes(x.size)}
            </span>
          ))}
        </p>
      )}
      <Kept
        rows={[
          ['Absent', 'recorded as gone', p.absent],
          ['Not acquired', 'selected but not held, with the reason', p.not_acquired.map((x) => `${x.path} — ${x.reason}`)],
          ['Refused', 'links or junctions, not followed; Git metadata, never acquired here', p.refused.map((x) => `${x.path} — ${x.reason}`)],
          ['Not examined', 'no absence inferred', [...p.absence_withheld, ...p.unexamined.map((x) => `${x.path}/ — ${x.reason}`)]],
        ]}
        visible={p.visible_not_selected}
      />
      {p.not_selected && <LeftOut n={p.not_selected} />}
    </div>
  )
}

function ColumnChoices({ p, onPreview, onEdit }: { p: Preview; onPreview?: (d: Choices, categories?: Choices) => void; onEdit?: () => void }) {
  const [choices, setChoices] = useState<Choices>(p.sensitive_decisions ?? {})
  const [partial, setPartial] = useState(!!p.partial_confirmed)
  const columns = p.sensitive_columns ?? []
  return <section aria-label="SQLite acquisition consent">
    <p>Suspected secret columns are flagged by name. No sample values are shown. Answer every column before acquisition.</p>
    {columns.map(c => <label className="src-field" key={c.path}>
      <span>{c.table}.{c.column}</span>
      <select aria-label={`Decision for ${c.table}.${c.column}`} value={choices[c.path] ?? ''} onChange={e => {
        const next = { ...choices }; delete next[c.path]
        if (e.target.value) next[c.path] = e.target.value as 'include' | 'exclude'
        setChoices(next); onEdit?.()
      }}>
        <option value="">Choose include or exclude</option><option value="include">Include</option><option value="exclude">Exclude</option>
      </select>
    </label>)}
    {p.partial_required && <label><input type="checkbox" checked={partial} onChange={e => { setPartial(e.target.checked); onEdit?.() }} /> Acquire only examined tables. Unreadable tables and their reasons stay recorded as not examined; no absence is inferred for them.</label>}
    <p><button className="btn" disabled={columns.some(c => !choices[c.path]) || (!!p.partial_required && !partial)} onClick={() => onPreview?.(choices, partial ? { partial: 'include' } : undefined)}>Preview these decisions</button></p>
  </section>
}

/** K4: WHAT WAS LEFT OUT, BOUNDED. Excluded folders where the walk met them,
 *  their contents unknown -- never zero -- and unselected files counted by
 *  category and pattern. */
export function LeftOut({ n }: { n: NonNullable<Preview['not_selected']> }) {
  return (
    <details className="src-leftout">
      <summary>
        Left out: {count(n.excluded_folders_total)} excluded folders (contents unknown) ·{' '}
        {count(n.unselected_files_total)} files not selected
      </summary>
      <p className="src-faint">{n.excluded_folder_note}.</p>
      <ul className="src-list">
        {n.excluded_folders.map((b) => (
          <li key={b.path}>
            <code>{b.path}/</code> — <code>{b.pattern}</code>
            {b.category ? ` · ${b.category}` : ''} · contents unknown
          </li>
        ))}
        {n.excluded_folders_truncated && (
          <li>… and {count(n.excluded_folders_total - n.excluded_folders.length)} more excluded folders</li>
        )}
      </ul>
      <ul className="src-list">
        {n.unselected_files.map((g) => (
          <li key={`${g.category}|${g.pattern}`}>
            {count(g.files)} files · {g.pattern ? <code>{g.pattern}</code> : 'matched no include'}
            {g.category ? ` · ${g.category}` : ''}
          </li>
        ))}
        {n.unselected_files_truncated && <li>… more groups not shown</li>}
      </ul>
    </details>
  )
}

/** K6: an offer of the Git connector. Nothing is added or associated. */
export function RepositoryOffer({ r, onOffer }: { r: NonNullable<Preview['repository']>; onOffer?: (connector: string) => void }) {
  return (
    <p className="src-note">
      {r.note}.{' '}
      {r.at === 'enclosing' && `Its top is ${r.levels_up} folder${r.levels_up === 1 ? '' : 's'} above this one. `}
      {onOffer && (
        <button className="btn quiet" onClick={() => onOffer(r.offer)}>
          Add the repository as its own collection…
        </button>
      )}
    </p>
  )
}

/** K5: ONE DECISION PER CATEGORY, submitted to a new preview. Never a claim
 *  that what it admits holds no secrets. */
export function CategoryChoices({ p, onPreview, onEdit }: { p: Preview; onEdit?: () => void; onPreview?: (d: Choices) => void }) {
  const [choices, setChoices] = useState<Choices>(p.category_decisions ?? {})
  const cats = p.categories ?? []
  const pending = cats.filter((c) => c.new_files > 0)
  return (
    <div className="src-sensitive">
      <strong>Evidence categories</strong>
      <p>
        Logs and build output can hold what a file name does not reveal. Nothing new in a category is read until you
        include it here and preview again; flagged file names inside still need their own decision. Including a category
        is your choice to acquire it, {p.category_note ? <i>{p.category_note}</i> : 'not a check for secrets'}.
      </p>
      <ul>
        {cats.map((c) => (
          <li key={c.category}>
            <b>{c.label}</b>: {count(c.new_files)} new files · {bytes(c.new_bytes)}
            {c.previously_acquired > 0 && <> · {count(c.previously_acquired)} previously acquired (unchanged by this)</>}
            {c.new_files > 0 && (
              <>
                {' '}
                <select
                  aria-label={`Decision for ${c.label}`}
                  value={choices[c.category] ?? ''}
                  onChange={(e) => {
                    const next = { ...choices }
                    if (e.target.value) next[c.category] = e.target.value as 'include' | 'exclude'
                    else delete next[c.category]
                    setChoices(next)
                    onEdit?.()
                  }}
                >
                  <option value="">Choose include or exclude</option>
                  <option value="include">Include the category</option>
                  <option value="exclude">Exclude the category</option>
                </select>
                <details>
                  <summary>files</summary>
                  <ul className="src-list">
                    {c.files.map((f) => (
                      <li key={f}>
                        <code>{f}</code>
                      </li>
                    ))}
                    {c.files_truncated && <li>… and {count(c.new_files - c.files.length)} more</li>}
                  </ul>
                </details>
              </>
            )}
          </li>
        ))}
      </ul>
      {pending.length > 0 && onPreview && (
        <button className="btn" disabled={pending.some((c) => !choices[c.category])} onClick={() => onPreview(choices)}>
          Preview these category decisions
        </button>
      )}
      {p.can_confirm === false && pending.some((c) => !c.decision) && (
        <p>Confirmation is blocked until every category with new files has a decision in a new preview.</p>
      )}
    </div>
  )
}

/** The five things kept apart, each with what it means. `noVisible` leaves
 * out the "Visible, not selected" row where it does not apply (the change
 * evidence section); everywhere else an unknown count stays visible as "—". */
export function Kept({ rows, visible, noVisible = false }: { rows: [string, string, string[]][]; visible: number | null; noVisible?: boolean }) {
  return (
    <ul className="src-kept">
      {rows.map(([name, means, list]) => (
        <li key={name}>
          <b>{name}</b>: {means}. {count(list.length)}
          {list.length > 0 && (
            <details>
              <summary>show</summary>
              <ul className="src-list">
                {list.slice(0, 200).map((x) => (
                  <li key={x}>
                    <code>{x}</code>
                  </li>
                ))}
                {list.length > 200 && <li>… and {count(list.length - 200)} more</li>}
              </ul>
            </details>
          )}
        </li>
      ))}
      {!noVisible && (
        <li>
          <b>Visible, not selected</b>: never opened. {visible === null ? '—' : count(visible)}
        </li>
      )}
    </ul>
  )
}

/** A run in progress, with its one way to stop it. */
export function RunBar({ run, onCancel }: { run: RunView; onCancel?: () => void }) {
  const what = run.kind === 'sweep' ? 'Acquiring' : 'Reading the folder for a preview'
  return (
    <div className="src-run" role="status">
      <span className="src-spin" aria-hidden="true" />
      <span>
        {what}: {count(run.progress.files)} files · {bytes(run.progress.bytes)}
        {run.progress.current ? (
          <>
            {' '}
            · <code>{run.progress.current}</code>
          </>
        ) : null}
      </span>
      {onCancel && run.state === 'running' && (
        <button className="btn quiet" onClick={onCancel} disabled={run.cancel_requested}>
          {run.cancel_requested ? 'Stopping…' : 'Cancel'}
        </button>
      )}
      <span className="src-faint">
        Cancel works until the record is written; nothing is recorded by a run that stops first.
      </span>
    </div>
  )
}

/** Confirm: the ActDialog pattern. One sentence of what happens, one
 *  filled button that writes. Esc or a press outside cancels. */
export function Confirm({
  title,
  effect,
  verb,
  busy,
  refused,
  onConfirm,
  onCancel,
  children,
}: {
  title: string
  effect: React.ReactNode
  verb: string
  busy?: boolean
  refused?: string | null
  onConfirm: () => void
  onCancel: () => void
  children?: React.ReactNode
}) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCancel()
      }
    }
    window.addEventListener('keydown', key, true)
    box.current?.querySelector<HTMLElement>('textarea, input, button.act-confirm')?.focus()
    return () => window.removeEventListener('keydown', key, true)
  }, [onCancel])
  return (
    <div className="act-veil" onMouseDown={onCancel}>
      <div
        className="act-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={box}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 className="act-title">{title}</h2>
        <p className="act-effect">
          <strong>What happens:</strong> {effect}
        </p>
        {children}
        {refused && <p className="act-refused">{refused}</p>}
        <div className="act-buttons">
          <button className="act-cancel" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="act-confirm" onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : verb}
          </button>
        </div>
      </div>
    </div>
  )
}

/** The Result: what the sweep act recorded, kept apart. */
export function Result({ r, visible }: { r: SweepResult; visible: number | null }) {
  const by = r.admitted_by_action
  return (
    <div className="src-result">
      <p className="src-banner ok">
        Swept · <span className="src-mono">{shortId(r.act, 14)}</span> · batch{' '}
        <span className="src-mono">{r.batch}</span> · {count(by.new?.length)} new ·{' '}
        {count(by.changed?.length)} changed · {count(by.reappeared?.length)} reappeared ·{' '}
        {count(r.absent.length)} absent · {count(r.withheld.length)} withheld ·{' '}
        {count(r.not_examined.length)} not examined
      </p>
      <Kept
        rows={[
          ['Absent', 'recorded as gone', r.absent],
          ['Not acquired', 'selected but not held', r.withheld],
          ['Not examined', 'no absence inferred', r.not_examined],
        ]}
        visible={visible}
      />
    </div>
  )
}

/* ------------------------------------------------------------------------ *
 * A LINK'S TARGET, AS AN INERT LABELLED PLACEHOLDER (G3).
 *
 * Whatever is not acquired is drawn as words: its status from the record,
 * what was authored, the key it resolves to. Never an <img src>, never a
 * fetch, never a request to anything that reads the bound folder. An
 * acquired target is a way to its own object page -- in this app, from the
 * record -- and nothing more.
 * ------------------------------------------------------------------------ */

export function LinkStatus({ l, onOpen }: { l: LinkRow; onOpen?: (key: string) => void }) {
  const tone =
    l.target === 'acquired'
      ? 'ok'
      : l.target === 'recorded absent'
        ? 'att'
        : l.target.startsWith('not acquired · withheld')
          ? 'att'
          : ''
  return (
    <li className="src-link" data-target={l.target}>
      <span className={'src-chip ' + tone}>{l.rel === 'embeds' ? 'embed' : 'link'}</span>
      <code className="src-authored">{l.authored}</code>
      {l.resolved && l.resolved !== l.authored && (
        <span className="src-faint">
          {' '}
          → <code>{l.resolved}</code>
        </span>
      )}
      <span className={'src-status ' + tone}>
        {l.target}
        {l.reason ? ` (${l.reason})` : ''}
      </span>
      {l.target === 'acquired' && l.resolved && onOpen && (
        <button className="btn quiet" onClick={() => onOpen(l.resolved!)}>
          open
        </button>
      )}
    </li>
  )
}

/** Consent is submitted to a new preview; changing a choice never confirms. */
export function SensitiveChoices({ p, onPreview, onEdit }: { p: Preview; onEdit?: () => void; onPreview?: (d: Record<string, 'include' | 'exclude'>) => void }) {
  const [choices, setChoices] = useState<Record<string, 'include' | 'exclude'>>(p.sensitive_decisions ?? {})
  const flagged = p.sensitive_files ?? []
  const pending = flagged.filter((f) => !f.previously_acquired)
  return <div className="src-sensitive">
    <strong>Credential-like files</strong>
    <p>Names only; no suspected secret values are shown. Choose include or exclude for each new file, then preview again. Exclusions become explicit scope patterns.</p>
    <ul>{flagged.map((f) => <li key={f.path}>
      <code>{f.path}</code> · {f.size_from === 'record' ? 'last recorded size: ' : ''}{bytes(f.size)} · rule <code>{f.rule}</code>{' '}
      {f.previously_acquired ? <span>previously acquired, flagged</span> : <label>
        Decision for {f.path}{' '}
        <select aria-label={`Decision for ${f.path}`} value={choices[f.path] ?? ''} onChange={(e) => {
          const next = { ...choices }
          if (e.target.value) next[f.path] = e.target.value as 'include' | 'exclude'
          else delete next[f.path]
          setChoices(next)
          onEdit?.()
        }}>
          <option value="">Choose include or exclude</option>
          <option value="include">Include</option>
          <option value="exclude">Exclude</option>
        </select>
      </label>}
    </li>)}</ul>
    {pending.length > 0 && onPreview && <button className="btn" disabled={pending.some((f) => !choices[f.path])} onClick={() => onPreview(choices)}>Preview these decisions</button>}
    {p.can_confirm === false && <p>Confirmation is blocked until every flagged new file has a decision in a new preview.</p>}
  </div>
}
