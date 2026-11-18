/* ------------------------------------------------------------------------ *
 * A WORKSPACE SHAPED LIKE THE JOB, for the four Kinds people actually write.
 *
 * The generic builder (`R2Forms`) asks a Kind how each field is entered and
 * stacks the answers. That is right for a Kind defined later, and wrong for
 * the four that carry most of this Brain's governance: writing a Decision,
 * building a Workflow, describing a Discipline and guiding one Conversation
 * are four different jobs, and a single column of fields makes all four look
 * like form-filling.
 *
 * So each of these four gets a layout organised around its own work, and all
 * four share one shell: the record as it will read stays beside the writing,
 * updating as it is typed, and creation is in that preview rather than behind
 * a review step. There is no review step: the review is the preview.
 *
 *   Decision                guidance and a worked example beside the writing.
 *   Conversation Instruction  the Conversation chosen first and visibly,
 *                           then the behaviour, with guidance beside it.
 *   Discipline              identity, then principles beside tools, then the
 *                           operating contract; tools as rows.
 *   Workflow                overview / activities / finish, with the ordered
 *                           sequence beside the activity being edited.
 *
 * IT HOLDS NO STATE OF THE RECORD. Every value is the composer's own
 * `fields`, in the same string-per-field shape the generic builder uses and
 * `r2Model.fieldValue` writes from, so what is typed here is written by the
 * same code, guarded by the same draft protection, and nothing here can
 * record anything.
 * ------------------------------------------------------------------------ */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { FieldForm, KindAuthoring } from './r2Model'
import R2Sequence from './R2Sequence'

/** The four Kinds this surface lays out for itself. Any other Kind keeps the
 *  generic builder, which is what lets a Kind defined later still work. */
export const SHAPED = new Set(['decision', 'workflow', 'discipline', 'conversation-instruction'])

/** What each of the four is for, in the words the entry point uses. */
export const SHAPED_WORDS: Record<string, { name: string; icon: string; task: string; prompt?: string; help?: string }> = {
  decision: {
    name: 'Decision', icon: '✓', task: 'Capture a settled choice',
    prompt: 'What question was settled, and what was decided?',
    help: 'Write the question and its settled answer in the same passage.',
  },
  workflow: { name: 'Workflow', icon: '⇢', task: 'Shape how work proceeds' },
  discipline: { name: 'Discipline', icon: '◇', task: 'Describe a way of practising' },
  'conversation-instruction': {
    name: 'Conversation Instruction', icon: '↳', task: 'Guide this conversation',
    prompt: 'How should people work in this conversation?',
    help: 'Write the behaviour you want everyone here to follow.',
  },
}

/* -- the widgets these layouts are built from ------------------------------ */

function Field({ field, label, help, rows, value, onChange }: {
  field: string; label: string; help?: string; rows?: number
  value: string; onChange: (v: string) => void
}) {
  return <label className="r2c-field">{label}
    {rows ? <textarea aria-label={field} rows={rows} value={value} onChange={(e) => onChange(e.target.value)} />
      : <input aria-label={field} value={value} onChange={(e) => onChange(e.target.value)} />}
    {help && <small>{help}</small>}</label>
}

/** A LIST FIELD AS EDITABLE ROWS, one value per row, which is how the
 *  material actually reads -- a Discipline's tools are five things, not a
 *  paragraph with newlines in it.
 *
 *  The rows are held here and written down as the field's text, because a
 *  single empty row and no rows at all are the same text. An empty row the
 *  author just added is a change to the draft (`onStructural`), so closing on
 *  one still warns, and it stays on screen until they fill or remove it.
 *
 *  Pasting several lines into a row makes separate rows, so material can be
 *  brought across from an existing record without turning the list into
 *  prose. */
function ListRows({ field, label, help, value, onChange, onStructural, addWord }: {
  field: string; label: string; help?: string; value: string
  onChange: (v: string) => void; onStructural: () => void; addWord: string
}) {
  const split = (v: string) => (v ? v.split(/\r?\n/) : [])
  const [rows, setRows] = useState<string[]>(() => split(value))
  const [seen, setSeen] = useState(value)
  /* The value changed somewhere else (a discarded draft, a changed Kind):
     read the rows from it again rather than showing stale ones. */
  if (seen !== value && value !== rows.join('\n')) { setSeen(value); setRows(split(value)) }
  const put = (next: string[]) => { setRows(next); setSeen(next.join('\n')); onChange(next.join('\n')) }
  const paste = (i: number, e: React.ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData('text/plain')
    if (!/\r?\n/.test(text)) return
    e.preventDefault()
    const parts = text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    put([...rows.slice(0, i), ...parts, ...rows.slice(i + 1)])
    onStructural()
  }
  return <div className="r2c-field r2c-list" data-list-field={field}>
    <span className="r2c-list-label">{label}</span>
    {help && <small>{help}</small>}
    <div>{rows.map((v, i) => <div key={i} className="r2c-list-row">
      <input aria-label={`${label} ${i + 1}`} value={v} onPaste={(e) => paste(i, e)}
        onChange={(e) => put(rows.map((r, j) => (j === i ? e.target.value : r)))} />
      <button type="button" aria-label={`Remove ${label} ${i + 1}`}
        onClick={() => { put(rows.filter((_, j) => j !== i)); onStructural() }}>×</button>
    </div>)}</div>
    <button type="button" className="r2c-addrow"
      onClick={() => { put([...rows, '']); onStructural() }}>+ Add {addWord}</button>
  </div>
}

function Caps({ label, help, value, onChange, choices, loading }: {
  label: string; help?: string; value: string; onChange: (v: string) => void
  choices: string[]; loading: boolean
}) {
  const picked = new Set(value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean))
  const flip = (c: string) => {
    const next = new Set(picked)
    if (next.has(c)) next.delete(c); else next.add(c)
    onChange([...next].join('\n'))
  }
  return <fieldset className="r2-capabilities" aria-label="requires"><legend>{label}</legend>
    {help && <small>{help}</small>}
    {choices.map((c) => <label key={c} className="r2-check">
      <input type="checkbox" checked={picked.has(c)} onChange={() => flip(c)} />{c}</label>)}
    {loading && !choices.length && <small>Reading the capability vocabulary…</small>}</fieldset>
}

/* -- the four layouts ------------------------------------------------------ */

interface Parts {
  kind: string
  k: KindAuthoring
  form: Record<string, FieldForm>
  fields: Record<string, string>
  set: (f: string, v: string) => void
  onStructural: () => void
  capabilities: string[]
  capabilitiesLoading: boolean
  selected: number
  onSelect: (i: number) => void
  section: string
  onSection: (s: string) => void
}

const labelOf = (p: Parts, f: string, fallback: string) => p.form[f]?.label ?? fallback
const helpOf = (p: Parts, f: string, fallback?: string) => p.form[f]?.help ?? fallback
const rowsOf = (p: Parts, f: string, fallback: number) => p.form[f]?.rows ?? fallback

function About({ p, help }: { p: Parts; help: string }) {
  return <Field field="about" label={`${labelOf(p, 'about', 'Subject')} (optional)`} help={helpOf(p, 'about', help)}
    value={p.fields.about ?? ''} onChange={(v) => p.set('about', v)} />
}

/** DECISION: two fields, and the hard part is knowing what belongs in them.
 *  So the width goes to guidance and a worked example beside the writing,
 *  rather than to two very wide boxes. */
function DecisionLayout({ p }: { p: Parts }) {
  const w = SHAPED_WORDS[p.kind]
  return <div className="r2c-short-layout">
    <aside className="r2c-guide">
      <p className="r2c-eyebrow">Write a useful decision</p>
      <h3>Keep the choice findable</h3>
      <ol>
        <li>Name the question that was settled.</li>
        <li>State the answer plainly.</li>
        <li>Add the boundary: what does this answer cover?</li>
      </ol>
      <blockquote>“Which defects belong to this work? Repair what this work made wrong; record everything else as discovered work.”</blockquote>
      <p className="r2c-faint">A worked example, from a decision already recorded here. It is here to read, not to copy in.</p>
    </aside>
    <section className="r2c-section">
      <p className="r2c-eyebrow">The settled choice</p>
      <Field field="text" label={labelOf(p, 'text', w.prompt!)} help={helpOf(p, 'text', w.help)} rows={rowsOf(p, 'text', 10)}
        value={p.fields.text ?? ''} onChange={(v) => p.set('text', v)} />
      <About p={p} help="Use a recognisable subject so related guidance can be found together." />
      <div className="r2c-notice">This records a choice already made. Creating a Decision does not answer or close an open request.</div>
    </section>
  </div>
}

/** CONVERSATION INSTRUCTION: which Conversation it belongs to is the first
 *  thing about it and the thing most easily got wrong, so it is chosen first
 *  and stays visible while the behaviour is written. */
function InstructionLayout({ p, destination }: { p: Parts; destination: ReactNode }) {
  const w = SHAPED_WORDS[p.kind]
  return <>
    <div className="r2c-instruction-context">
      <div>
        <p className="r2c-eyebrow">One conversation · everyone here</p>
        <h3>Where this guidance belongs</h3>
        <p className="r2c-faint">It applies in the Conversation chosen here, across participants and Personas.</p>
      </div>
      <div className="r2c-destination">{destination}</div>
    </div>
    <div className="r2c-instruction-writing">
      <section className="r2c-section">
        <Field field="text" label={labelOf(p, 'text', w.prompt!)} help={helpOf(p, 'text', w.help)} rows={rowsOf(p, 'text', 9)}
          value={p.fields.text ?? ''} onChange={(v) => p.set('text', v)} />
        <About p={p} help="A short subject, such as “welcome tour”." />
      </section>
      <aside className="r2c-guide">
        <p className="r2c-eyebrow">Make it useful here</p>
        <h3>Describe the behaviour</h3>
        <p>Say what people should do in this conversation, and when it matters.</p>
        <blockquote>“When someone asks a question here, explain what the feature is for, where it is on screen, and what to try next.”</blockquote>
        <p>This guidance travels with the Conversation. A Persona change does not change who it is for.</p>
      </aside>
    </div>
  </>
}

/** DISCIPLINE: grouped as the practice reads -- who it is and when it
 *  applies, then the method beside the tools it draws on, then what it takes,
 *  produces and is checked by. */
function DisciplineLayout({ p }: { p: Parts }) {
  return <>
    <section className="r2c-section">
      <p className="r2c-eyebrow">The practice</p>
      <div className="r2c-twofields">
        <Field field="name" label={labelOf(p, 'name', 'Name')} value={p.fields.name ?? ''} onChange={(v) => p.set('name', v)} />
        <Field field="about" label={labelOf(p, 'about', 'When it applies')} help={helpOf(p, 'about', 'The kind of work this Discipline is for.')}
          value={p.fields.about ?? ''} onChange={(v) => p.set('about', v)} />
      </div>
    </section>
    <div className="r2c-practice-grid">
      <section className="r2c-section">
        <p className="r2c-eyebrow">Principles &amp; procedure</p>
        <h3>How to do the work well</h3>
        <p className="r2c-sectionintro">Keep the practical method together, with room for real procedure.</p>
        <Field field="text" label={labelOf(p, 'text', 'Principles and procedure')} help={helpOf(p, 'text')}
          rows={rowsOf(p, 'text', 12)} value={p.fields.text ?? ''} onChange={(v) => p.set('text', v)} />
      </section>
      <section className="r2c-section">
        <p className="r2c-eyebrow">Tools &amp; their use</p>
        <h3>What the practice draws on</h3>
        <ListRows field="tools" label={labelOf(p, 'tools', 'Tools it uses')} addWord="tool"
          help={helpOf(p, 'tools', 'Named, not granted. One tool or interface per row.')}
          value={p.fields.tools ?? ''} onChange={(v) => p.set('tools', v)} onStructural={p.onStructural} />
        <Field field="tool_use" label={labelOf(p, 'tool_use', 'Tool use')} help={helpOf(p, 'tool_use', 'How these tools are used. Tool use is not verified by Mentis.')}
          rows={rowsOf(p, 'tool_use', 6)} value={p.fields.tool_use ?? ''} onChange={(v) => p.set('tool_use', v)} />
        <Caps label={labelOf(p, 'requires', 'Requires')} help={helpOf(p, 'requires', 'Capabilities a runtime must have. Naming tools does not grant them.')}
          value={p.fields.requires ?? ''} onChange={(v) => p.set('requires', v)}
          choices={p.capabilities} loading={p.capabilitiesLoading} />
      </section>
    </div>
    <section className="r2c-section">
      <p className="r2c-eyebrow">Inputs &amp; outcome</p>
      <div className="r2c-twofields">
        <Field field="inputs" label={labelOf(p, 'inputs', 'What it takes')} help={helpOf(p, 'inputs', 'What the work starts from.')}
          rows={rowsOf(p, 'inputs', 3)} value={p.fields.inputs ?? ''} onChange={(v) => p.set('inputs', v)} />
        <Field field="outputs" label={labelOf(p, 'outputs', 'What it produces')} help={helpOf(p, 'outputs', 'What someone hands back.')}
          rows={rowsOf(p, 'outputs', 3)} value={p.fields.outputs ?? ''} onChange={(v) => p.set('outputs', v)} />
      </div>
    </section>
    <div className="r2c-twofields">
      <section className="r2c-section">
        <p className="r2c-eyebrow">Checks</p>
        <Field field="verification" label={labelOf(p, 'verification', 'Verification')} help={helpOf(p, 'verification', 'How to tell work was done to this practice.')}
          rows={rowsOf(p, 'verification', 6)} value={p.fields.verification ?? ''} onChange={(v) => p.set('verification', v)} />
      </section>
      <section className="r2c-section">
        <p className="r2c-eyebrow">Boundaries</p>
        <Field field="limits" label={labelOf(p, 'limits', 'Known limitations and dependencies')} help={helpOf(p, 'limits', 'Where it stops working, and what it depends on.')}
          rows={rowsOf(p, 'limits', 4)} value={p.fields.limits ?? ''} onChange={(v) => p.set('limits', v)} />
      </section>
    </div>
  </>
}

/** WORKFLOW: three parts of one job, because the activities need the whole
 *  width and the rest does not. */
function WorkflowLayout({ p, participant, persona }: { p: Parts; participant: ReactNode; persona: ReactNode }) {
  const count = (() => { try { const v = JSON.parse(p.fields.activities || '[]'); return Array.isArray(v) ? v.length : 0 } catch { return 0 } })()
  const tabs: [string, string][] = [['overview', 'Overview'], ['activities', `Activities · ${count}`], ['finish', 'Finish & handoff']]
  return <>
    <div className="r2c-tabs" role="group" aria-label="Workflow sections">
      {tabs.map(([k, t]) => <button key={k} type="button" aria-pressed={p.section === k}
        onClick={() => p.onSection(k)}>{t}</button>)}
    </div>
    {p.section === 'activities' ? <R2Sequence value={p.fields.activities ?? ''} onChange={(v) => p.set('activities', v)}
      onStructural={p.onStructural} selected={p.selected} onSelect={p.onSelect} />
      : p.section === 'overview' ? <section className="r2c-section">
        <p className="r2c-eyebrow">Purpose &amp; scope</p>
        <Field field="name" label={labelOf(p, 'name', 'Name')} value={p.fields.name ?? ''} onChange={(v) => p.set('name', v)} />
        <Field field="about" label={labelOf(p, 'about', 'When it applies')} help={helpOf(p, 'about', 'The kind of work this Workflow is for.')}
          value={p.fields.about ?? ''} onChange={(v) => p.set('about', v)} />
        <ListRows field="projects" label={labelOf(p, 'projects', 'Projects it applies to')} addWord="project"
          help={helpOf(p, 'projects', 'Repository names or paths. No projects means any.')}
          value={p.fields.projects ?? ''} onChange={(v) => p.set('projects', v)} onStructural={p.onStructural} />
        <Field field="text" label={labelOf(p, 'text', 'How the work proceeds')} help={helpOf(p, 'text', 'Describe the shape of the work. The ordered activities hold the hand-offs.')}
          rows={rowsOf(p, 'text', 8)} value={p.fields.text ?? ''} onChange={(v) => p.set('text', v)} />
      </section> : <>
        <section className="r2c-section">
          <p className="r2c-eyebrow">Owner decisions</p>
          <ListRows field="decisions" label={labelOf(p, 'decisions', 'Decisions reserved to the owner')} addWord="reserved decision"
            help={helpOf(p, 'decisions', 'One reserved decision per row. The carrier asks these; it does not make them.')}
            value={p.fields.decisions ?? ''} onChange={(v) => p.set('decisions', v)} onStructural={p.onStructural} />
        </section>
        <section className="r2c-section">
          <p className="r2c-eyebrow">Completion</p>
          <Field field="done_when" label={labelOf(p, 'done_when', 'Done when')} help={helpOf(p, 'done_when', 'What makes the whole piece of work complete.')}
            rows={rowsOf(p, 'done_when', 3)} value={p.fields.done_when ?? ''} onChange={(v) => p.set('done_when', v)} />
          <Field field="evidence" label={labelOf(p, 'evidence', 'What supports completion')} help={helpOf(p, 'evidence', 'What supports saying it is complete.')}
            rows={rowsOf(p, 'evidence', 3)} value={p.fields.evidence ?? ''} onChange={(v) => p.set('evidence', v)} />
          <Field field="interrupted" label={labelOf(p, 'interrupted', 'If interrupted')} help={helpOf(p, 'interrupted', 'What is left in the record and how a later session picks it up.')}
            rows={rowsOf(p, 'interrupted', 4)} value={p.fields.interrupted ?? ''} onChange={(v) => p.set('interrupted', v)} />
        </section>
        <section className="r2c-section">
          <p className="r2c-eyebrow">The carrier</p>
          <div className="r2c-twofields">{participant}{persona}</div>
          <p className="r2c-hint">Defaults the Composer pre-fills. A Workflow grants no authority and schedules nothing.</p>
          <Caps label={labelOf(p, 'requires', 'Requires')} help={helpOf(p, 'requires', 'Capabilities the carrier needs. Naming tools does not grant them.')}
            value={p.fields.requires ?? ''} onChange={(v) => p.set('requires', v)}
            choices={p.capabilities} loading={p.capabilitiesLoading} />
        </section>
      </>}
  </>
}

/* -- the shell the four share ---------------------------------------------- */

export default function R2Shaped({ parts, header, destination, participant, persona, settings, preview, commit }: {
  parts: Parts
  /** the Kind switcher and what this Kind is, above the workspace */
  header: ReactNode
  /** the Conversation chooser, for the Kind whose record belongs to one */
  destination: ReactNode
  participant: ReactNode
  persona: ReactNode
  /** reach, standing and supporting material: the composer's own controls */
  settings: ReactNode
  /** the record as it will read */
  preview: ReactNode
  /** creating it, beside that preview */
  commit: ReactNode
}) {
  const p = parts
  const w = SHAPED_WORDS[p.kind]
  const writing = useRef<HTMLElement>(null)
  const showing = useRef<HTMLDivElement>(null)
  /* THE SELECTED ACTIVITY, BROUGHT INTO THE PREVIEW, so changing where it
     belongs can be read where the record reads. Only when the selection
     itself changes: it never pulls the reader off what they were reading. */
  useEffect(() => {
    if (p.kind !== 'workflow' || p.section !== 'activities') return
    showing.current?.querySelector(`#r2c-preview-activity-${p.selected}`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [p.kind, p.section, p.selected])
  return <div className="r2-create-shaped">
    {header}
    <div className={`r2c-compose r2c-kind-${p.kind}`}>
      <section className="r2c-editor" id="r2c-editor" ref={writing} aria-label={`Compose ${w.name}`}>
        {p.kind === 'workflow' ? <WorkflowLayout p={p} participant={participant} persona={persona} />
          : p.kind === 'discipline' ? <DisciplineLayout p={p} />
            : p.kind === 'decision' ? <DecisionLayout p={p} />
              : <InstructionLayout p={p} destination={destination} />}
        {settings}
      </section>
      <aside className="r2c-previewcol" id="r2c-preview" aria-label="Live preview and create">
        <div className="r2c-previewhead"><h3>Your record, as it will read</h3><span className="r2c-live">Live preview</span></div>
        <div className="r2c-record-window" ref={showing} tabIndex={0} aria-label="Scrollable record preview">{preview}</div>
        <p className="r2c-previewnote">It changes as you type. Scroll this record to read the whole thing.</p>
        <div className="r2c-commitbox">{commit}</div>
      </aside>
    </div>
    <nav className="r2c-mobilebar" aria-label="Composer shortcuts">
      <button type="button" onClick={() => writing.current?.scrollIntoView({ block: 'start' })}>Write ↑</button>
      <button type="button" onClick={() => showing.current?.scrollIntoView({ block: 'start' })}>Live preview ↓</button>
    </nav>
  </div>
}
