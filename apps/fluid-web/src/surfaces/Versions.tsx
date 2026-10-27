import Bounded from './governance/Bounded'
import { useEffect, useRef, useState } from 'react'
import {
  ago,
  announceAdvance,
  post,
  when,
  type Deletion,
  type Id,
  type Offers,
  type Part,
  type Revision,
  type Turn,
  type VersionsRead,
} from '../api'
import { Floating } from '../bits'
import './versions.css'

/* ------------------------------------------------------------------------ *
 * EDIT AND DELETE, AS THE RECORD DOES THEM.
 *
 * An entry is never rewritten. EDIT writes the next version -- a new entry
 * that supersedes the last -- and DELETE writes a deletion record that
 * supersedes the current version. Everything that was there stays there, and
 * Details shows every version and what a deleted item said.
 *
 * SO THE WORDS ON THE BUTTONS ARE THE OPERATION. There is no "Save" distinct
 * from committing a new version, so nothing here says Save: it says "Save as
 * new version", or "Propose new version" where the Kind adjudicates its
 * material and the current version keeps standing until the owner approves.
 * Which of those it is comes from the server (`may.edit_mode`), never from a
 * Kind name here.
 *
 * Nothing here decides who may do what. The route refuses what it refuses,
 * and the refusal is shown in its own words.
 * ------------------------------------------------------------------------ */

export const editEntry = (
  entry: Id,
  by: Id | null,
  opts: { text?: string; body?: Record<string, unknown>; because?: string },
) =>
  post<{ version: Id; mode: string; says: string }>(`/api/entries/${entry}/edit`, {
    attributed_to: by,
    ...opts,
  })

export const deleteEntry = (entry: Id, by: Id | null, because?: string) =>
  post<{ deletion: Id }>(`/api/entries/${entry}/delete`, {
    attributed_to: by,
    because: because ?? '',
  })

/** What the author typed: text and the characters of inline references, in
 *  order. The server rebuilds parts from this and keeps every attachment. */
export const flowText = (parts: Part[] | undefined) =>
  (parts ?? [])
    .filter((p) => p.type === 'text' || ['topic', 'turn', 'conversation'].includes(p.type))
    .map((p) => p.text ?? '')
    .join('')

const attachmentsOf = (parts: Part[] | undefined) =>
  (parts ?? []).filter(
    (p) => p.type !== 'text' && !['topic', 'turn', 'conversation'].includes(p.type),
  ).length

/** Run an act, say what landed or why it did not, and tell every reader. */
function useAct(onDone: (said: string) => void) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const run = async (act: () => Promise<unknown>, said: string) => {
    setBusy(true)
    setErr(null)
    try {
      await act()
      announceAdvance()
      onDone(said)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return { busy, err, run }
}

/* ------------------------------------------------------------ Turns --- */

export function TurnEditor({
  turn,
  me,
  onDone,
  onCancel,
}: {
  turn: Turn
  me: Id | null
  onDone: (said: string) => void
  onCancel: () => void
}) {
  const initial = flowText(turn.parts)
  const [text, setText] = useState(initial)
  const { busy, err, run } = useAct(onDone)
  const box = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    box.current?.focus()
  }, [])
  const kept = attachmentsOf(turn.parts)
  const unchanged = text.trim() === initial.trim()
  const save = () =>
    !busy &&
    !unchanged &&
    text.trim() &&
    void run(() => editEntry(turn.id, me, { text }), `Turn #${turn.number} edited · the earlier words are in its history`)
  return (
    <div
      className="ver-panel"
      role="group"
      aria-label={`edit turn ${turn.number}`}
      onClick={(e) => e.stopPropagation()}
    >
      <textarea
        ref={box}
        className="ver-text"
        aria-label={`the words of turn ${turn.number}`}
        value={text}
        rows={Math.min(12, Math.max(3, text.split('\n').length + 1))}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel()
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save()
        }}
      />
      <p className="ver-note">
        Saves a new version of Turn #{turn.number}. The earlier words stay in its history
        {kept > 0 ? `; its ${kept === 1 ? 'attachment is' : `${kept} attachments are`} kept` : ''}.
      </p>
      {err && <p className="ver-err">not saved: {err}</p>}
      <div className="ver-go">
        <button className="btn" disabled={busy || unchanged || !text.trim()} onClick={save}>
          Save as new version
        </button>
        <button className="ver-quiet" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

export function TurnDelete({
  turn,
  me,
  onDone,
  onCancel,
}: {
  turn: Turn
  me: Id | null
  onDone: (said: string) => void
  onCancel: () => void
}) {
  const [why, setWhy] = useState('')
  const { busy, err, run } = useAct(onDone)
  return (
    <div
      className="ver-panel ver-danger"
      role="group"
      aria-label={`delete turn ${turn.number}`}
      onClick={(e) => e.stopPropagation()}
    >
      <p className="ver-lede">Delete Turn #{turn.number}?</p>
      <p className="ver-note">
        It keeps its place, marked deleted. Nothing new can reply to it, reference it or build on
        it, and there is no undelete. Its words, versions and everything that happened stay in the
        record and in its Details.
      </p>
      <input
        className="ver-why"
        aria-label="why (optional)"
        placeholder="why? (optional)"
        value={why}
        autoFocus
        onChange={(e) => setWhy(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel()
        }}
      />
      {err && <p className="ver-err">not deleted: {err}</p>}
      <div className="ver-go">
        <button
          className="btn ver-delete"
          disabled={busy}
          onClick={() =>
            void run(() => deleteEntry(turn.id, me, why.trim()), `Turn #${turn.number} deleted`)
          }
        >
          Delete Turn #{turn.number}
        </button>
        <button className="ver-quiet" onClick={onCancel}>
          Keep it
        </button>
      </div>
    </div>
  )
}

/** A quiet mark beside the time: this Turn has been edited, and when. */
export function EditedMark({ revision }: { revision: Revision }) {
  return (
    <span
      className="ver-edited"
      title={`edited ${when(revision.edited_at)} · ${revision.versions} versions — see Details`}
    >
      edited
    </span>
  )
}

/** What stands where a deleted Turn's words were. */
export function DeletedNotice({ deleted }: { deleted: Deletion }) {
  return (
    <p className="ver-deleted" role="note">
      <span className="ver-deleted-word">Deleted</span>
      {deleted.by_alias ? ` by ${deleted.by_alias}` : ''} · {ago(deleted.at)}
      {deleted.because && deleted.because !== 'deleted' ? ` — ${deleted.because}` : ''}
      <span className="ver-deleted-where"> · what it said is kept in its Details</span>
    </p>
  )
}

/* ---------------------------------------------------------- history --- */

/** Every version, oldest first, and the deletion that ended the line.
 *  `principal` names the field to show for an entry; a Turn shows its words. */
export function VersionList({
  read,
  principal,
  onOpenEntry,
}: {
  read: VersionsRead
  principal?: string
  onOpenEntry?: (id: Id) => void
}) {
  if (read.versions.length <= 1 && !read.deleted) return null
  return (
    <div aria-label="versions">
      <Bounded items={read.versions} label="Versions" listClass="ver-list">{(v) => {
        const said = v.parts
          ? flowText(v.parts)
          : principal && v.body
            ? String(v.body[principal] ?? '')
            : ''
        return (
          <li key={v.entry} className={'ver-row' + (v.current ? ' current' : '')}>
            <div className="ver-row-head">
              {onOpenEntry ? (
                <button className="ver-quiet" onClick={() => onOpenEntry(v.entry)}>
                  version {v.version}
                </button>
              ) : (
                <b>version {v.version}</b>
              )}
              <span>
                {' '}
                · {v.by_alias} · {when(v.at)}
                {v.current ? ' · current' : ''}
              </span>
            </div>
            {v.because && v.because !== 'edited' && <div className="ver-row-why">because {v.because}</div>}
            <blockquote className="ver-row-said">{said || <i>nothing written</i>}</blockquote>
            {v.parts && attachmentsOf(v.parts) > 0 && (
              <div className="ver-row-why">
                with {attachmentsOf(v.parts)} attachment{attachmentsOf(v.parts) > 1 ? 's' : ''}
              </div>
            )}
          </li>
        )
      }}</Bounded>
      {read.deleted && (
        <div className="ver-row ver-row-deleted">
          <div className="ver-row-head">
            <b>deleted</b> · {read.deleted.by_alias} · {when(read.deleted.at)}
          </div>
          {read.deleted.because && read.deleted.because !== 'deleted' && (
            <div className="ver-row-why">because {read.deleted.because}</div>
          )}
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------- entries --- */

interface EntryFacts {
  id: Id
  fields: string[]
  body: Record<string, unknown>
  may?: Offers
}

export const EDIT_WORDS: Record<string, { go: string; note: string }> = {
  proposed: {
    go: 'Propose new version',
    note: 'The current version keeps standing. The new one is a proposal until the owner establishes it; no earlier approval carries over.',
  },
  candidate: {
    go: 'Save as new candidate',
    note: 'Replaces this candidate with a new one. Neither has been approved, and the new one is not approved by being written.',
  },
  edited: {
    go: 'Save as new version',
    note: 'The new version becomes current at once. The earlier one stays in its history.',
  },
}

/** Edit and delete for an entry of any Kind, offered only where the server
 *  says the act would be accepted, and worded as what it will really do. */
export function EntryVersionActs({
  d,
  me,
  onDone,
}: {
  d: EntryFacts
  me: Id | null
  onDone: (said: string) => void
}) {
  const [open, setOpen] = useState<'edit' | 'delete' | null>(null)
  const editable = (d.fields.length ? d.fields : Object.keys(d.body)).filter(
    (f) => typeof (d.body[f] ?? '') === 'string',
  )
  const [values, setValues] = useState<Record<string, string>>({})
  const [why, setWhy] = useState('')
  const { busy, err, run } = useAct((said) => {
    setOpen(null)
    onDone(said)
  })
  if (!me || !d.may || (!d.may.edit && !d.may.delete)) return null
  const words = EDIT_WORDS[d.may.edit_mode ?? 'edited']
  const current = (f: string) => values[f] ?? String(d.body[f] ?? '')
  const changed = editable.filter((f) => current(f) !== String(d.body[f] ?? ''))
  return (
    <div className="ver-entry">
      <p className="ei-acts">
        {d.may.edit && (
          <button
            className={'ei-link' + (open === 'edit' ? ' on' : '')}
            aria-expanded={open === 'edit'}
            onClick={() => setOpen(open === 'edit' ? null : 'edit')}
          >
            edit
          </button>
        )}
        {d.may.edit && d.may.delete && ' · '}
        {d.may.delete && (
          <button
            className={'ei-link' + (open === 'delete' ? ' on' : '')}
            aria-expanded={open === 'delete'}
            onClick={() => setOpen(open === 'delete' ? null : 'delete')}
          >
            delete
          </button>
        )}
      </p>
      {open === 'edit' && (
        <div className="ver-panel" role="group" aria-label="edit this entry">
          {editable.map((f) => (
            <label key={f} className="ver-field">
              <span>{f}</span>
              <textarea
                className="ver-text"
                value={current(f)}
                rows={Math.min(10, Math.max(2, current(f).split('\n').length + 1))}
                onChange={(e) => setValues({ ...values, [f]: e.target.value })}
              />
            </label>
          ))}
          <input
            className="ver-why"
            aria-label="why (optional)"
            placeholder="why? (optional)"
            value={why}
            onChange={(e) => setWhy(e.target.value)}
          />
          <p className="ver-note">{words.note}</p>
          {err && <p className="ver-err">not saved: {err}</p>}
          <div className="ver-go">
            <button
              className="btn"
              disabled={busy || changed.length === 0}
              onClick={() =>
                void run(
                  () =>
                    editEntry(d.id, me, {
                      body: Object.fromEntries(changed.map((f) => [f, current(f)])),
                      because: why.trim(),
                    }),
                  d.may?.edit_mode === 'proposed'
                    ? 'New version proposed · the current one still stands'
                    : 'New version saved · the earlier one is in its history',
                )
              }
            >
              {words.go}
            </button>
            <button className="ver-quiet" onClick={() => setOpen(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {open === 'delete' && (
        <div className="ver-panel ver-danger" role="group" aria-label="delete this entry">
          <p className="ver-note">
            Deleting ends any standing it has now and makes it inert: nothing can be established
            from it, replaced with it or built on it again, and there is no undelete. Its contents,
            versions and history stay in the record.
          </p>
          <input
            className="ver-why"
            aria-label="why (optional)"
            placeholder="why? (optional)"
            value={why}
            onChange={(e) => setWhy(e.target.value)}
          />
          {err && <p className="ver-err">not deleted: {err}</p>}
          <div className="ver-go">
            <button
              className="btn ver-delete"
              disabled={busy}
              onClick={() => void run(() => deleteEntry(d.id, me, why.trim()), 'Deleted · its history is kept')}
            >
              Delete
            </button>
            <button className="ver-quiet" onClick={() => setOpen(null)}>
              Keep it
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ----------------------------------------------------------- topics --- */

/** Rename a Topic in place. Its identity is kept: every filing still points
 *  at it, and the old name stays in its history. */
export function TopicRename({
  topic,
  me,
  onDone,
}: {
  topic: { id: Id; name: string }
  me: Id | null
  onDone?: (said: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(topic.name)
  const [at, setAt] = useState<React.CSSProperties>({ visibility: 'hidden' })
  const opener = useRef<HTMLButtonElement | null>(null)
  const { busy, err, run } = useAct((said) => {
    setOpen(false)
    onDone?.(said)
  })
  useEffect(() => setName(topic.name), [topic.name])
  /* WHERE THE FORM STANDS: BESIDE THE NAME IT RENAMES. The rail's foot is a
     few characters wide, and the form squeezed into it wrapped its own name
     field and explanation into a column (owner, after #52). So it floats
     over the page, level with the Topic's row and outside the rail, where it
     has room -- and on a phone, the width of the screen near the control. */
  useEffect(() => {
    if (!open) return
    const place = () => {
      const btn = opener.current
      /* the row this pencil sits on, whether or not its Topic is in force */
      const row = btn?.closest('.topic-line')?.querySelector<HTMLElement>('.topic-row') ?? null
      const W = Math.min(400, window.innerWidth - 16)
      const H = 230
      if (row && window.innerWidth >= 640) {
        const r = row.getBoundingClientRect()
        const left = r.left - W - 10 >= 8 ? r.left - W - 10 : Math.max(8, r.right + 10)
        const top = Math.max(8, Math.min(r.top - 10, window.innerHeight - H - 8))
        setAt({ position: 'fixed', top, left, width: W })
      } else if (btn) {
        const r = btn.getBoundingClientRect()
        const above = r.top > H + 16
        setAt(above
          ? { position: 'fixed', bottom: window.innerHeight - r.top + 8, left: 8, right: 8 }
          : { position: 'fixed', top: r.bottom + 8, left: 8, right: 8 })
      }
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [open])
  if (!me) return null
  const opening = (
    <button
      ref={opener}
      className="topic-rename"
      aria-label={`rename topic ${topic.name}`}
      aria-expanded={open}
      title={`Rename ${topic.name}. Everything filed under it stays filed.`}
      onClick={() => setOpen(!open)}
    >
      {/* A pencil beside the Topic's own row, shown on hover or focus
          (ent-2b306f840389 item 3); it used to be a worded button in the
          rail's foot, reachable only for the Topic in force. */}
      <svg width="12" height="12" viewBox="0 0 14 14" aria-hidden="true">
        <path
          d="M9.3 2.2l2.5 2.5-7 7H2.3V9.2l7-7zM8 3.5l2.5 2.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  )
  if (!open) return opening
  const go = () =>
    name.trim() &&
    name.trim() !== topic.name &&
    void run(() => editEntry(topic.id, me, { body: { name: name.trim() } }), `Renamed to ${name.trim()}`)
  return (
    <>
    {opening}
    <Floating>
    <div className="scrim" onClick={() => setOpen(false)} />
    <div
      className="ver-panel topic-rename-panel"
      role="dialog"
      aria-label={`rename topic ${topic.name}`}
      style={at}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
      }}
    >
      <p className="topic-rename-was">
        Renaming <b>{topic.name}</b>
      </p>
      <input
        className="ver-why"
        aria-label="new topic name"
        value={name}
        autoFocus
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') go()
          if (e.key === 'Escape') setOpen(false)
        }}
      />
      <p className="ver-note">Same Topic, new name. Its Turns stay filed under it; the old name stays in its history.</p>
      {err && <p className="ver-err">not renamed: {err}</p>}
      <div className="ver-go">
        <button className="btn" disabled={busy || !name.trim() || name.trim() === topic.name} onClick={go}>
          Rename
        </button>
        <button className="ver-quiet" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
    </Floating>
    </>
  )
}
