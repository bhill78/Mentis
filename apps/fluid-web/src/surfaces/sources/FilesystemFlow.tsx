import { useEffect, useState } from 'react'
import { post, qs, useApi, type Id } from '../../api'
import PickSource from './pick/PickSource'
import { baseName } from './pick/recent'
import type { Picker } from './route'
import { Steps } from './AddSource'
import { Confirm, PreviewBody, Result, RunBar } from './parts'
import ScopeForm, { optionDefaults, presetValue, type ScopeValue } from './ScopeForm'
import {
  bytes,
  cancelRun,
  count,
  runToEnd,
  takesAddress,
  type Choices,
  type Descriptor,
  type Preview,
  type RunView,
  type SourcesRoute,
  type SweepResult,
} from './route'

/* ------------------------------------------------------------------------ *
 * A FOLDER, FROM NOTHING TO ACQUIRED (U5) -- and any connector whose binding
 * is a folder on this machine: a Git repository is chosen the same way, and
 * its own scope fields come from its descriptor through the same form. The
 * flow names the connector and never branches on which one it is.
 *
 * Name -> folder -> scope -> Preview -> Confirm -> Result, on one page, each
 * step below the last so what was chosen stays in view.
 *
 * THE PREVIEW DECLARES NOTHING. It is a draft: the server reads the folder
 * and says exactly what would be recorded, and nothing is declared, bound or
 * written. Acquire now declares the collection, binds it on this machine and
 * sweeps it as ONE act -- if the folder changed since the preview, nothing at
 * all is recorded and the preview is offered again.
 *
 * THE FOLDER IS CHOSEN HERE, ON THIS MACHINE. A browser cannot hand over a
 * path, so the server lists folders (never files) for the chooser; that is a
 * local read and is never recorded. The path goes to this machine's binding
 * file and nowhere else.
 * ------------------------------------------------------------------------ */

interface FolderList {
  path: string | null
  parent: string | null
  folders: { name: string; path: string | null; refused?: string }[]
  refused: string | null
}

export default function FilesystemFlow({
  descriptor,
  me,
  go,
  onChanged,
  picker,
  onLock,
}: {
  descriptor: Descriptor
  picker?: Picker
  onLock?: (locked: boolean) => void
  me: Id | null
  go: (r: SourcesRoute) => void
  onChanged: () => void
}) {
  const notes = descriptor.presets.find((p) => p.id === 'notes') ?? descriptor.presets[0]
  const [name, setName] = useState('')
  const [root, setRoot] = useState<string | null>(null)
  const [choosing, setChoosing] = useState(true)
  const [nameEdited, setNameEdited] = useState(false)
  const [via, setVia] = useState<string | undefined>()
  // OR AN ADDRESS, for a connector whose descriptor lists one among its
  // locations. Exactly one of the two is sent; nothing is fetched until the
  // preview, and nothing that could be a credential belongs in it.
  const byAddress = takesAddress(descriptor)
  const [address, setAddress] = useState('')
  const remote = byAddress && !root && address.trim() ? address.trim() : null
  const where = root ?? remote
  const [scope, setScope] = useState<ScopeValue>(presetValue(notes, optionDefaults(descriptor)))
  const hasOptions = descriptor.scope_fields.some((f) => f.option)
  const [run, setRun] = useState<RunView | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [decisionsDirty, setDecisionsDirty] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refused, setRefused] = useState<string | null>(null)
  const [result, setResult] = useState<SweepResult | null>(null)

  const step = result || confirming ? 4 : preview ? 3 : where ? 2 : 1
  useEffect(() => onLock?.(!!preview), [preview, onLock])

  const doPreview = async (decisions?: Record<string, 'include' | 'exclude'>, categories?: Choices) => {
    setRefused(null)
    setDecisionsDirty(false)
    setPreview(null)
    try {
      const end = await runToEnd(
        post<RunView>('/api/sources/plan', {
          draft: {
            connector: descriptor.id,
            name,
            ...(remote ? { remote } : { root }),
            include: scope.include,
            exclude: scope.exclude,
            sensitive_decisions: decisions,
            category_decisions: categories,
            ...(hasOptions ? { options: scope.options } : {}),
          },
        }),
        setRun,
      )
      setRun(null)
      if (end.state === 'done') setPreview(end.result as Preview)
      else setRefused(end.failure ?? end.state)
    } catch (e) {
      setRun(null)
      setRefused((e as Error).message)
    }
  }

  const acquire = async () => {
    if (!preview?.draft) return
    setBusy(true)
    setRefused(null)
    try {
      const end = await runToEnd(
        post<RunView>('/api/sources/sweep', { draft: preview.draft, plan: preview.plan, by: me }),
        setRun,
      )
      setRun(null)
      if (end.state === 'done') {
        setResult(end.result as SweepResult)
        setConfirming(false)
        onChanged()
      } else setRefused(end.failure ?? end.state)
    } catch (e) {
      setRun(null)
      setRefused((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="src-page">
      <Steps at={step} />
      <div className="src-cols">
        <div>
          <label className="src-field">
            <span className="src-label">Name</span>
            <input value={name} onChange={(e) => { setNameEdited(true); setName(e.target.value) }} placeholder={descriptor.binding === 'local-file' ? 'Filled in from the file you pick' : 'Filled in from the folder you pick'} disabled={!!result} />
          </label>
          <div className="src-field">
            <span className="src-label">Where, on this machine</span>
            {root && <div className="src-note"><b>{baseName(root)}</b><p className="src-mono">{root}</p>
              <button className="link" onClick={() => setChoosing(true)}>Change...</button>
              <p>Read-only. Mentis never changes anything here.</p>{via && <p>Using the folder that contains <b>{via}</b>.</p>}</div>}
            {choosing && <PickSource purpose="folder" picker={picker} onPath={(path, file) => {
              setRoot(path); setVia(file); setAddress(''); setChoosing(false); setPreview(null)
              if (!nameEdited) setName(baseName(path))
            }} />}

          </div>
          {byAddress && (
            <AddressField
              value={address}
              disabled={!!result}
              onChange={(v) => {
                setAddress(v)
                if (v.trim()) setRoot(null)
                setPreview(null)
              }}
            />
          )}
          {where && (
            <div className="src-field">
              <span className="src-label">What to take</span>
              <ScopeForm
                descriptor={descriptor}
                value={scope}
                onChange={(v) => {
                  setScope(v)
                  setPreview(null)
                }}
              />
            </div>
          )}
          {where && !result && (
            <p>
              <button className="btn primary" disabled={!name.trim() || !!run} onClick={() => void doPreview()}>
                Preview
              </button>{' '}
              <span className="src-faint">reads it; records nothing</span>
            </p>
          )}
        </div>
      </div>

      {run && <RunBar run={run} onCancel={() => void cancelRun(run.key)} />}
      {refused && !confirming && <p className="act-refused">{refused}</p>}

      {preview && !result && (
        <>
          <PreviewBody
            p={preview}
            onDecisions={(d, cs) => void doPreview(d, cs)}
            onDecisionEdit={() => setDecisionsDirty(true)}
            onOffer={(connector) => go({ at: 'flow', connector })}
          />
          <p className="src-right">
            <button className="btn quiet" onClick={() => setPreview(null)}>
              Back to scope
            </button>{' '}
            <button className="btn primary" onClick={() => setConfirming(true)} disabled={preview.admit.length === 0 || preview.can_confirm === false || decisionsDirty}>
              Acquire {count(preview.counts.new)} files…
            </button>
          </p>
        </>
      )}

      {confirming && preview && (
        <Confirm
          title={`Acquire into this Brain`}
          verb="Acquire now"
          busy={busy}
          refused={refused}
          onCancel={() => setConfirming(false)}
          onConfirm={acquire}
          effect={
            <>
              1 collection declared, <b>{name}</b> · {remote ? 'this address' : 'this folder'} bound on this
              machine ·{' '}
              {count(preview.counts.new)} Admissions recorded · {bytes(preview.bytes_new_to_store)} copied into
              the held store · 1 <code>source-swept</code> act citing{' '}
              <span className="src-mono">{preview.plan}</span>, recorded as yours. If the folder changed since
              this preview, nothing is recorded and you are shown the new preview. The folder itself is never
              modified.
            </>
          }
        >
          {run && <RunBar run={run} />}
        </Confirm>
      )}

      {result && (
        <>
          <Result r={result} visible={preview?.visible_not_selected ?? null} />
          <p>
            <button
              className="btn primary"
              onClick={() => result.collection && go({ at: 'collection', col: result.collection, tab: 'overview' })}
            >
              Open {name}
            </button>
          </p>
        </>
      )}
    </section>
  )
}

/** A LOCATION ELSEWHERE, TYPED: drawn for any connector whose descriptor
 *  lists `address` among its locations. The server checks it and refuses
 *  one that carries a credential; access comes from what this machine
 *  already has. */
export function AddressField({
  value,
  onChange,
  disabled,
  onSubmit,
}: {
  value: string
  onChange: (v: string) => void
  disabled?: boolean
  onSubmit?: () => void
}) {
  return (
    <form
      className="src-field"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit?.()
      }}
    >
      <label>
        <span className="src-label">Or the repository address</span>
        <input
          className="src-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="https://host/owner/repo.git or git@host:owner/repo.git"
          aria-label="Repository address"
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <p className="src-faint">
        https or ssh. Never put a password or token in it: it is refused. Access uses the credentials this machine
        already has (its credential manager, its ssh agent). It is fetched into this machine's own copy only when you
        preview, and the address, never a credential, is recorded.
      </p>
      {onSubmit && (
        <button className="btn" type="submit" disabled={disabled || !value.trim()}>
          Bind to this address
        </button>
      )}
    </form>
  )
}

/** The folder chooser: folders only, on this machine, never recorded. */
export function Chooser({ onChoose }: { onChoose: (path: string) => void }) {
  const [at, setAt] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const list = useApi<FolderList>('/api/sources/folders' + qs({ path: at }), { live: false })
  const d = list.data
  return (
    <div className="src-chooser">
      <form
        className="src-chooser-bar"
        onSubmit={(e) => {
          e.preventDefault()
          if (typed.trim()) setAt(typed.trim())
        }}
      >
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="or paste a folder path"
          aria-label="folder path"
        />
        <button className="btn quiet" type="submit">
          Go
        </button>
      </form>
      <div className="src-chooser-bar">
        <code>{d?.path ?? 'This machine'}</code>
        {d?.path && (
          <button className="btn quiet" onClick={() => setAt(d.parent)}>
            Up
          </button>
        )}
        {d?.path && !d.refused && (
          <button className="btn primary" onClick={() => onChoose(d.path!)}>
            Use this folder
          </button>
        )}
      </div>
      {d?.refused && <p className="act-refused">{d.refused}</p>}
      {list.error && <p className="act-refused">{list.error}</p>}
      <ul className="src-list">
        {(d?.folders ?? []).map((f) => (
          <li key={f.name}>
            {f.path ? (
              <button className="link" onClick={() => setAt(f.path)}>
                {f.name}
              </button>
            ) : (
              <span className="src-faint">
                {f.name} — {f.refused}
              </span>
            )}
          </li>
        ))}
        {d && d.folders.length === 0 && <li className="src-faint">no folders here</li>}
      </ul>
    </div>
  )
}
