import { useState } from 'react'
import { useApi, qs, type Id } from '../../api'
import type { GovFilters } from '../../address'
import Register from '../Register'
import {
  allRows,
  indexBy,
  isGovernedMaterial,
  nameOf,
  pathOf,
  reachLabel,
  type AppliesAnswer,
  type ContextAnswer,
  type ContextComponent,
  type ContextWithheld,
  type GovernedAnswer,
  type GovernedRow,
} from './InUseContext'
import './in-use.css'

/* ---------------------------------------------------------------------- *
 * IN USE -- how the same material acts on work now.
 *
 * The Standing lens reads what the record SAYS about the material. This
 * lens reads what the material DOES, computed from what stands, and the
 * two are lenses on one corpus rather than two corpora.
 *
 * IT IS NOT A RECORD, and the lede says so before anything else on the
 * page. Everything here is computed from where the material sits now; not
 * one line of it is evidence that any execution received anything. That
 * question has its own door and the lede names it.
 *
 * AND THE CORPUS IS READ THROUGH THE REGISTER, not through a second list of
 * the same rows. At Brain scope this lens mounts `Register` with `lens="use"`,
 * which is where the Applies facet -- Any way / Placed / By Persona / When
 * named / Truth-apt when named -- has always been implemented, along with the
 * search, the Kind facet, the paging and the `new` marker. Nothing here could
 * mount it before, so the facet was built and unreachable; a second register
 * of its own would have been two lists over one corpus, which is exactly what
 * "one corpus at two lenses" rules out. The row is one implementation,
 * arranged two ways, and this arranges it the second way.
 *
 * At Conversation scope there is no register, here or in the Standing lens:
 * the question there is which material reaches whom, answered in the three
 * groups below, and the facets belong to the corpus-wide read.
 * ---------------------------------------------------------------------- */

export interface InUseLensProps {
  /** the Conversation this lens looks through, or null for the whole
   *  governed corpus. A Conversation is a LENS and not an application:
   *  the same material is in both answers, seen from different places. */
  conversation: string | null
  /** what to call it. Absent falls back to the id, never to a placeholder. */
  conversationName?: string | null
  /** whose composition is being asked about, where the caller knows. It
   *  changes orientation only; no governed material is selected or
   *  withheld because of it. */
  participant?: string | null
  /** open Where meets Who -- "Why does something apply?" */
  onWhy?: () => void
  /** open the Preview sheet -- "Preview what an agent would receive". */
  onPreview?: () => void
  /** open the shared item inspector on one piece of governed material. */
  onInspect?: (entry: string) => void
  /** THE FACETS, HELD BY WHOEVER OWNS THE ADDRESS, so a link carries them and
   *  so switching lens does not silently drop the query. Read by the register
   *  at Brain scope; the Applies facet is the one that belongs to this lens. */
  filters: GovFilters
  onFilters: (next: GovFilters) => void
  /** who is looking, for the register's `new` marker. Without one there is no
   *  last look and so no marker -- absent, not "nothing is new". */
  me?: Id | null
  /** put two items side by side without choosing between them. */
  onCompare?: (left: Id, right: Id) => void
}

export default function InUseLens({
  conversation,
  conversationName,
  participant,
  onWhy,
  onPreview,
  onInspect,
  filters,
  onFilters,
  me,
  onCompare,
}: InUseLensProps) {
  const ctx = useApi<ContextAnswer>(
    '/api/context' + qs({ conversation, participant }),
  )
  /* WHAT COULD REACH AN EXECUTION AT ALL, which is a different question
     from what this Conversation's composition would include: a Persona
     applies to nobody here until an execution is started as it, and a
     when-named item applies to nobody until somebody names it. Neither is
     in `components`, and neither may be inferred from their absence. */
  const applies = useApi<AppliesAnswer>('/api/governance/applies')
  const governed = useApi<GovernedAnswer>('/api/governed' + qs({ limit: 200 }))
  const convs = useApi<{ conversations: { id: string; name: string }[] }>(
    '/api/conversations',
  )

  const names: Record<string, string> = {}
  for (const c of convs.data?.conversations ?? []) names[c.id] = c.name
  const index = indexBy(allRows(governed.data))
  const here = conversationName ?? (conversation ? names[conversation] ?? conversation : null)

  const error = ctx.error ?? applies.error
  if (error) {
    return (
      <section className="in-use">
        <p className="iu-error">{error}</p>
      </section>
    )
  }
  if (!ctx.data || !applies.data) {
    return (
      <section className="in-use">
        <p className="iu-faint">Reading what stands…</p>
      </section>
    )
  }

  return (
    <section className="in-use">
      {/* I-72. The limit is the first thing said, not a footnote. */}
      <p className="iu-lede">
        How that same material acts on work{here ? ' here' : ''} now, computed from what
        stands. This is not a record: it does not say what any execution received. For
        that, ask History.
      </p>
      {conversation ? (
        <Here
          ctx={ctx.data}
          applies={applies.data}
          index={index}
          onWhy={onWhy}
          onPreview={onPreview}
          onInspect={onInspect}
        />
      ) : (
        <Corpus
          ctx={ctx.data}
          applies={applies.data}
          index={index}
          names={names}
          filters={filters}
          onFilters={onFilters}
          me={me}
          onWhy={onWhy}
          onInspect={onInspect}
          onCompare={onCompare}
        />
      )}
    </section>
  )
}

/* ----------------------------- conversation ----------------------------- */

function Here({
  ctx,
  applies,
  index,
  onWhy,
  onPreview,
  onInspect,
}: {
  ctx: ContextAnswer
  applies: AppliesAnswer
  index: Record<string, GovernedRow>
  onWhy?: () => void
  onPreview?: () => void
  onInspect?: (entry: string) => void
}) {
  const material = ctx.components.filter(isGovernedMaterial)
  const placed = material.filter((c) => pathOf(c.scope) === 'placed')
  const personas = applies.rows.filter((r) => r.applies === 'by_persona')
  const nameable = applies.rows.filter((r) => r.applies === 'when_named')
  /* The machine reason, counted by the machine's own word. A withholding
     for any other reason is still shown below with ITS reason; it is this
     summary count that is specifically about what was placed and never
     established. */
  const notEstablished = ctx.withheld.filter((w) => w.why === 'not established')
  const withheldMaterial = ctx.withheld.filter((w) => w.source_id !== null)

  return (
    <>
      <p className="iu-summary">
        <span>{placed.length} apply to everyone here</span>
        <span>{ctx.conflicts.length} overlap</span>
        <span>{personas.length} Personas, if selected</span>
        <span>{nameable.length} only if named</span>
        <span>{notEstablished.length} withheld · not established</span>
      </p>

      <Overlaps conflicts={ctx.conflicts} index={index} />

      <section className="iu-block">
        <div className="iu-head">
          <h3>Applies to everyone who works here</h3>
          {onWhy && (
            <button type="button" className="btn quiet" onClick={onWhy}>
              Why does something apply?
            </button>
          )}
        </div>
        <p className="iu-sub">
          {placed.length} · whoever acts, whatever Persona they wear, whichever runtime
          carries them
        </p>
        {placed.length === 0 ? (
          <p className="iu-empty">
            Nothing is placed here, so nothing applies to everyone who works here. That
            is an empty answer, read from the placements.
          </p>
        ) : (
          <table className="iu-table">
            <thead>
              <tr>
                <th>Governed material</th>
                <th>Why it applies here</th>
                <th>Current composition</th>
              </tr>
            </thead>
            <tbody>
              {placed.map((c) => (
                <tr key={c.source_id ?? c.scope}>
                  <td>
                    <Material c={c} index={index} onInspect={onInspect} />
                  </td>
                  {/* the composer's own sentence, not a re-wording of it */}
                  <td className="iu-why">{c.why}</td>
                  <td className="iu-effect">includes it</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="iu-block">
        <div className="iu-head">
          <h3>Depends on the execution</h3>
          {onPreview && (
            <button type="button" className="btn quiet" onClick={onPreview}>
              Preview what an agent would receive
            </button>
          )}
        </div>
        <p className="iu-sub">
          nothing here is attached to this Conversation or to a Participant
        </p>

        <div className="iu-depends">
          <h4>If it is started as a Persona</h4>
          {personas.length === 0 ? (
            <p className="iu-empty">
              No Persona stands to be started as. An empty answer, read from what
              stands.
            </p>
          ) : (
            <>
              <ul className="iu-chips">
                {personas.map((r) => (
                  <li key={r.entry}>
                    <button
                      type="button"
                      className="iu-chip"
                      onClick={onInspect && (() => onInspect(r.entry))}
                    >
                      {nameOf(r.entry, index)}
                    </button>
                  </li>
                ))}
              </ul>
              <p className="iu-note">That Persona applies to that execution only.</p>
            </>
          )}
        </div>

        <Fold
          title={`${nameable.length} standing items can be named`}
          sub="none applies unless named"
        >
          {nameable.length === 0 ? (
            <p className="iu-empty">
              Nothing stands that could be named for an execution. An empty answer.
            </p>
          ) : (
            <ul className="iu-list">
              {nameable.map((r) => (
                <li key={r.entry}>
                  <button
                    type="button"
                    className="iu-link"
                    onClick={onInspect && (() => onInspect(r.entry))}
                  >
                    {nameOf(r.entry, index)}
                  </button>
                  <span className="iu-faint"> · {reachLabel(r, {})}</span>
                </li>
              ))}
            </ul>
          )}
        </Fold>
      </section>

      <Fold
        title="Withheld here"
        sub={`${withheldMaterial.length} · placed here but not established · composition withholds it`}
      >
        {withheldMaterial.length === 0 ? (
          <p className="iu-empty">
            Composition withheld no governed material here. An empty answer, read from
            the composition.
          </p>
        ) : (
          <table className="iu-table">
            <thead>
              <tr>
                <th>Governed material</th>
                <th>Kind</th>
                <th>Current composition</th>
              </tr>
            </thead>
            <tbody>
              {withheldMaterial.map((w) => (
                <tr key={w.source_id ?? w.source_kind}>
                  <td>
                    <Withheld w={w} index={index} onInspect={onInspect} />
                  </td>
                  <td className="iu-kind">{w.source_kind}</td>
                  {/* THE MACHINE REASON, VERBATIM. `not established` and
                      `superseded` are the engine's words and are shown as
                      the engine wrote them. */}
                  <td className="iu-machine">withheld: {w.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Fold>
    </>
  )
}

/* -------------------------------- brain --------------------------------- */

function Corpus({
  ctx,
  applies,
  index,
  names,
  filters,
  onFilters,
  me,
  onWhy,
  onInspect,
  onCompare,
}: {
  ctx: ContextAnswer
  applies: AppliesAnswer
  index: Record<string, GovernedRow>
  names: Record<string, string>
  filters: GovFilters
  onFilters: (next: GovFilters) => void
  me?: Id | null
  onWhy?: () => void
  onInspect?: (entry: string) => void
  onCompare?: (left: Id, right: Id) => void
}) {
  const f = applies.facets

  return (
    <>
      <p className="iu-summary">
        <span>{f.placed} placed in Conversations</span>
        <span>{f.by_persona} Personas, by selection</span>
        <span>{f.when_named} only when named</span>
        <span>
          {ctx.conflicts.length} overlap{ctx.conflicts.length === 1 ? '' : 's'}
        </span>
      </p>

      <Overlaps conflicts={ctx.conflicts} index={index} />

      <section className="iu-block">
        <div className="iu-head">
          <h3>How each standing item reaches work</h3>
          {onWhy && (
            <button type="button" className="btn quiet" onClick={onWhy}>
              Why does something apply?
            </button>
          )}
        </div>
        {/* THE FACET SLOT, AND THE ONE ROW IMPLEMENTATION IN IT. `Register`
            already knows how to search this corpus, offer the Applies facet
            and the Kind facet, page it 40 at a time and say "n of m"; it
            renders the same `RegisterRow` the Standing lens does, with the
            Applies column instead of the Standing and Authority ones. A list
            written again here would be a second reading of one corpus that
            could disagree with the first. Whoever owns the address holds the
            facets, so a link carries them and a lens switch keeps them. */}
        <Register
          lens="use"
          conversation={null}
          filters={filters}
          onFilters={onFilters}
          onOpenEntry={(entry) => onInspect?.(entry)}
          onCompare={onCompare}
          me={me}
          names={names}
        />
      </section>
    </>
  )
}

/* ------------------------------- overlaps -------------------------------- */

/** SURFACED, NEVER RESOLVED -- and honestly empty where there is nothing to
 *  group on.
 *
 *  Composition groups two standing items when both name the same subject.
 *  No authoring path writes that subject yet, so in real data this renders
 *  empty. What is said here is what is true: nothing carries a subject, so
 *  nothing can be grouped. It is NOT the claim that no two items overlap --
 *  that claim would require a look nobody has done. */
function Overlaps({
  conflicts,
  index,
}: {
  conflicts: ContextAnswer['conflicts']
  index: Record<string, GovernedRow>
}) {
  return (
    <section className="iu-block">
      <h3>Overlaps</h3>
      <p className="iu-sub">
        standing items on one subject; composition includes both and does not choose
      </p>
      {conflicts.length === 0 ? (
        <p className="iu-empty">
          Nothing here is grouped by subject. Composition groups on the subject an item
          declares, and nothing here declares one — so this answer is empty. It is not a
          finding that nothing overlaps.
        </p>
      ) : (
        <ul className="iu-list">
          {conflicts.map((k) => (
            <li key={k.about}>
              <p className="iu-conflict">
                {k.components.length} items here speak to “{k.about}”. Both are
                delivered; Mentis does not choose.
              </p>
              <ul className="iu-sublist">
                {k.components.map((c) => (
                  <li key={c}>{nameOf(c, index)}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/* -------------------------------- parts ---------------------------------- */

function Material({
  c,
  index,
  onInspect,
}: {
  c: ContextComponent
  index: Record<string, GovernedRow>
  onInspect?: (entry: string) => void
}) {
  const id = c.source_id
  /* A component with no durable identity has nothing to open. Said, not
     silently rendered as an inert word. */
  if (!id) return <span className="iu-said">{c.text}</span>
  return (
    <button type="button" className="iu-link" onClick={onInspect && (() => onInspect(id))}>
      {index[id]?.summary || c.text || id}
    </button>
  )
}

function Withheld({
  w,
  index,
  onInspect,
}: {
  w: ContextWithheld
  index: Record<string, GovernedRow>
  onInspect?: (entry: string) => void
}) {
  const id = w.source_id
  if (!id) return <span className="iu-said">{w.source_kind}</span>
  return (
    <button type="button" className="iu-link" onClick={onInspect && (() => onInspect(id))}>
      {nameOf(id, index)}
    </button>
  )
}

/** A disclosure. Closed by default where the approved lens closes it: what
 *  is folded away is not hidden, and its count is on the handle. */
function Fold({
  title,
  sub,
  children,
}: {
  title: string
  sub: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <section className="iu-block">
      <button
        type="button"
        className="iu-fold"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="caret">{open ? '▾' : '▸'}</span>
        <span className="iu-fold-title">{title}</span>
      </button>
      <p className="iu-sub">{sub}</p>
      {open && <div className="iu-fold-body">{children}</div>}
    </section>
  )
}
