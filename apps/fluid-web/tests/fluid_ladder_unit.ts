/* FOCUSED UNIT TESTS FOR EPISTEMIC LADDER FLUID UI (Contract §4, §5, §6).
 *
 * Verifies:
 * - govTabsOf produces the exact Contract §6 tab order (`Start`, `Learning`,
 *   `For adoption`, `Adopted`, `Instructions`, `Personas`, `Rules & decisions`,
 *   `Disciplines`, `Workflows`).
 * - normalizeGovSection maps `for-adoption` and `adoption` consistently.
 * - buildLadderItemsUrl encodes all 7 filter row parameters (`kind`,
 *   `conversation`, `agent`, `runtime`, `since`, `status`, `challenged=1`, `q`).
 * - filterLadderItems filters by search query, kind, conversation, agent,
 *   runtime, recency, status (including `without_basis`), and challenged.
 * - computeWordDiff isolates replaced vs inserted wording for `For adoption`
 *   revision cards.
 * - buildLadderContextPath includes `work=` for `/api/context`.
 * - hintOfLadderItem extracts the originating conversation and Turn for Stage
 *   opening beside the conversation.
 * - Typed fixtures in `tests/fixtures/ladder_fixtures.ts` satisfy all §4 and §5
 *   API response shapes. */

import assert from 'node:assert/strict'
import {
  agentOptionsOf,
  artifactIdOf,
  artifactUrl,
  askedByOf,
  attemptedLabel,
  basisVerb,
  buildAdoptPayload,
  buildLadderContextPath,
  buildLadderItemsUrl,
  challengeActsFor,
  challengeResolvedLine,
  citeView,
  computeWordDiff,
  DEFAULT_LEARNING_FILTERS,
  evidenceText,
  filterLadderItems,
  formatScopeLabel,
  formatStatusLabel,
  govTabsOf,
  hintOfLadderItem,
  isArtifactRef,
  isLadderMaterial,
  normalizeGovSection,
  recencyToEpoch,
  resolutionOf,
  splitChallenges,
  stageAfterOpenGov,
  summarizeBasis,
  whoOf,
} from '../src/fluid/governance/ladderTypes'
import { waitingChallenges } from '../src/surfaces/governance/r2Model'
import {
  FIXTURE_NOW_SEC,
  LADDER_ADOPTED_FIXTURE,
  LADDER_ADOPTION_FIXTURE,
  LADDER_CONTEXT_FIXTURE,
  LADDER_ITEM_DETAIL_FIXTURE,
  LADDER_ITEMS_FIXTURE,
} from './fixtures/ladder_fixtures'

// 1. Contract §6 tab order
{
  const tabs = govTabsOf([
    { kind: 'instruction', meaning: '', fields: [], required: [], authoring: { section: 'instructions', door: 'placement' } },
    { kind: 'persona', meaning: '', fields: [], required: [], authoring: { section: 'personas', door: 'persona' } },
    { kind: 'rule', meaning: '', fields: [], required: [], authoring: { section: 'rules', door: 'placement' } },
    { kind: 'discipline', meaning: '', fields: [], required: [], authoring: { section: 'disciplines', door: 'placement' } },
    { kind: 'workflow', meaning: '', fields: [], required: [], authoring: { section: 'workflows', door: 'placement' } },
  ])
  assert.deepEqual(
    tabs.map(([s]) => s),
    ['start', 'learning', 'adoption', 'adopted', 'instructions', 'personas', 'rules', 'import', 'disciplines', 'workflows'],
  )
  assert.deepEqual(
    tabs.map(([, label]) => label),
    ['Start', 'Learning', 'For adoption', 'Adopted', 'Instructions', 'Personas', 'Rules & decisions', 'Import Archive', 'Disciplines', 'Workflows'],
  )
}

// 2. Section normalization
{
  assert.equal(normalizeGovSection('for-adoption'), 'adoption')
  assert.equal(normalizeGovSection('adoption'), 'adoption')
  assert.equal(normalizeGovSection('learning'), 'learning')
  assert.equal(normalizeGovSection('adopted'), 'adopted')
  assert.equal(normalizeGovSection(''), 'start')
}

// 3. buildLadderItemsUrl query parameters
{
  const url = buildLadderItemsUrl({
    q: 'build_commit',
    kind: 'lesson',
    conversation: 'ent-conv-restart',
    agent: 'Caretaker',
    runtime: 'claude',
    since: '1776000000',
    status: 'adoption_requested',
    challenged: true,
  }, 50, 10)
  assert.equal(
    url,
    '/api/ladder/items?kind=lesson&conversation=ent-conv-restart&agent=Caretaker&runtime=claude&since=1776000000&status=adoption_requested&challenged=1&q=build_commit&limit=50&offset=10',
  )
}

// 4. recencyToEpoch & filterLadderItems
{
  assert.equal(recencyToEpoch('24h', 100000), 100000 - 86400)
  assert.equal(recencyToEpoch('7d', 1000000), 1000000 - 7 * 86400)

  const all = LADDER_ITEMS_FIXTURE.items
  assert.equal(filterLadderItems(all, DEFAULT_LEARNING_FILTERS, FIXTURE_NOW_SEC).length, 6)

  const lessons = filterLadderItems(all, { ...DEFAULT_LEARNING_FILTERS, kind: 'lesson' }, FIXTURE_NOW_SEC)
  assert.equal(lessons.length, 2)

  const challenged = filterLadderItems(all, { ...DEFAULT_LEARNING_FILTERS, challenged: true }, FIXTURE_NOW_SEC)
  assert.equal(challenged.length, 2)
  assert.ok(challenged.every((i) => i.challenged > 0))

  const noBasis = filterLadderItems(all, { ...DEFAULT_LEARNING_FILTERS, status: 'without_basis' }, FIXTURE_NOW_SEC)
  assert.equal(noBasis.length, 1)
  assert.equal(noBasis[0].id, 'ent-1180bc77e401')

  const byQuery = filterLadderItems(all, { ...DEFAULT_LEARNING_FILTERS, q: 'build_commit' }, FIXTURE_NOW_SEC)
  assert.equal(byQuery.length, 2)

  // the agent filter matches the alias, and (as the server's does) the persona
  // worn: @Builder, and @Quill wearing Builder
  const byAgent = filterLadderItems(all, { ...DEFAULT_LEARNING_FILTERS, agent: 'Builder' }, FIXTURE_NOW_SEC)
  assert.deepEqual(byAgent.map((i) => i.id), ['ent-a941bc08e120', 'ent-1180bc77e401'])
  const byAlias = filterLadderItems(all, { ...DEFAULT_LEARNING_FILTERS, agent: '@Quill' }, FIXTURE_NOW_SEC)
  assert.deepEqual(byAlias.map((i) => i.id), ['ent-1180bc77e401'])
}

// 5. computeWordDiff for For adoption cards
{
  const req = LADDER_ADOPTION_FIXTURE.requests[1]
  const diff = computeWordDiff(req.wording.current, req.wording.proposed)
  assert.equal(diff.hasDiff, true)
  assert.ok(diff.added.includes('formal verification and independent review'))
  assert.ok(diff.prefix.startsWith('Verify at the end, within scope.'))

  const noCurrent = computeWordDiff(null, LADDER_ADOPTION_FIXTURE.requests[0].wording.proposed)
  assert.equal(noCurrent.hasDiff, false)
}

// 6. buildLadderContextPath with `work` parameter
{
  const p = buildLadderContextPath(
    { conversation: 'ent-conv-restart', participant: 'ent-caretaker', persona: null },
    ['ent-5608ed0ee75f'],
    'restart the server',
  )
  assert.equal(
    p,
    '/api/context?conversation=ent-conv-restart&participant=ent-caretaker&entries=ent-5608ed0ee75f&work=restart%20the%20server',
  )

  const workOnly = buildLadderContextPath(
    { conversation: null, participant: null, persona: null },
    [],
    'diagnose :8760',
  )
  assert.equal(workOnly, '/api/context?work=diagnose%20%3A8760')
}

// 7. hintOfLadderItem opens beside originating conversation & Turn
{
  const hint = hintOfLadderItem(LADDER_ITEM_DETAIL_FIXTURE)
  assert.ok(hint.title.startsWith('Lesson · Do not read an executable’s path'))
  assert.deepEqual(hint.source, {
    conversation: 'ent-conv-restart',
    conversationName: 'Mark IV restart roll call',
    turn: 'ent-9bf03a19e2c1',
    why: 'proposed',
  })
}

// 8. Fixture contract shapes
{
  assert.equal(LADDER_ITEMS_FIXTURE.counts.recorded, 263)
  assert.equal(LADDER_ADOPTION_FIXTURE.requests.length, 2)
  assert.equal(LADDER_ADOPTED_FIXTURE.items.length, 2)
  assert.equal(LADDER_ITEM_DETAIL_FIXTURE.lineage.up.length, 2)
  assert.equal(LADDER_ITEM_DETAIL_FIXTURE.lineage.down.length, 2)
  assert.equal(LADDER_CONTEXT_FIXTURE.components.length, 5)
  assert.equal(LADDER_CONTEXT_FIXTURE.withheld.length, 2)
  assert.equal(formatStatusLabel('adoption_requested').label, 'Adoption requested')
  assert.equal(formatScopeLabel({ whole_brain: true }, true), 'All conversations (Brain-wide)')
}

// 9. Challenges carry their resolution (addendum 1, D7) and names show one '@'
{
  const ch = LADDER_ITEM_DETAIL_FIXTURE.challenges[0]
  assert.equal(resolutionOf(ch), 'set_aside')
  assert.equal(whoOf(ch), '@Quill')
  assert.equal(resolutionOf({ ...ch, resolution: undefined, set_aside: null }), 'open')
  assert.equal(resolutionOf({ ...ch, resolution: 'withdrawn', set_aside: null }), 'withdrawn')
  // Delivery quotes open challenges only, and the context answer is the server's shape.
  const exp = LADDER_CONTEXT_FIXTURE.components.filter((c) => c.tier === 'experience')
  assert.equal(exp.length, 2)
  for (const c of exp) {
    for (const x of c.trailer?.challenges ?? []) assert.equal(resolutionOf(x), 'open')
    assert.ok(c.source_id && c.text && c.why)
  }
  assert.equal(LADDER_CONTEXT_FIXTURE.components[0].tier, null)
  // Outcome rows are ladder.outcomes_of's: attempted is a boolean.
  for (const o of LADDER_ITEM_DETAIL_FIXTURE.outcomes as { attempted: unknown }[]) {
    assert.equal(typeof o.attempted, 'boolean')
  }
}

// 10. U1: edited wording is the proposed body with only `text` replaced; never `summary`
{
  const req = LADDER_ADOPTION_FIXTURE.requests[0]
  const p = buildAdoptPayload(req, { me: 'ent-brian', because: 'b', editedText: '  New words.  ' })
  assert.deepEqual(p.body, { ...req.wording.proposed_body, text: 'New words.' })
  assert.ok(!('summary' in (p.body as object)))
  assert.deepEqual(Object.keys(p.body as object).sort(), Object.keys(req.wording.proposed_body!).sort())
  // unedited wording sends no body at all, and the request's scope as asked
  const same = buildAdoptPayload(req, { me: 'ent-brian', because: 'b', editedText: req.wording.proposed })
  assert.ok(!('body' in same))
  assert.deepEqual(same.scope, req.scope)
  assert.equal(same.attributed_to, 'ent-brian')
  // a body whose principal field is not `text` has that field replaced
  const other = { ...req, wording: { ...req.wording, proposed: 'Be kind.', proposed_body: { behaviour: 'Be kind.', name: 'Kind' } } }
  assert.deepEqual(buildAdoptPayload(other, { me: 'm', because: 'b', editedText: 'Be kinder.' }).body,
    { behaviour: 'Be kinder.', name: 'Kind' })
  // revisions carry what they replace; a chosen scope overrides
  const rev = buildAdoptPayload(LADDER_ADOPTION_FIXTURE.requests[1], { me: 'm', because: 'b', scope: 'when_named' })
  assert.deepEqual(rev.replaces, ['ent-5608ed0ee75f'])
  assert.deepEqual(rev.scope, { whole_brain: false })
}

// 11. U2: a falsifier rides as payload.falsifier, and only when given
{
  const hyp = { ...LADDER_ADOPTION_FIXTURE.requests[0], kind: 'hypothesis', expects_falsifier: true }
  const p = buildAdoptPayload(hyp, { me: 'm', because: 'b', falsifier: '  A run that followed it and failed.  ' })
  assert.equal(p.falsifier, 'A run that followed it and failed.')
  const edited = buildAdoptPayload(hyp, { me: 'm', because: 'b', editedText: 'Edited.', falsifier: 'F' })
  assert.equal(edited.falsifier, 'F')
  assert.equal((edited.body as { text: string }).text, 'Edited.')
  assert.ok(!('falsifier' in buildAdoptPayload(hyp, { me: 'm', because: 'b', falsifier: '   ' })))
}

// 12. U3: naming a section closes the item on Stage; no section leaves it
{
  assert.deepEqual(stageAfterOpenGov({ focus: 'ent-x', card: null }, 'adoption', 'ent-x'), { focus: null, card: 'ent-x' })
  assert.deepEqual(stageAfterOpenGov({ focus: 'ent-x', card: 'ent-y' }, 'learning'), { focus: null, card: null })
  assert.deepEqual(stageAfterOpenGov({ focus: 'ent-x', card: 'ent-y' }), { focus: 'ent-x', card: 'ent-y' })
}

// 13. attempted is said only where recorded; basis relations as words
{
  assert.equal(attemptedLabel(true), ' · attempted')
  assert.equal(attemptedLabel(false), ' · not attempted')
  assert.equal(attemptedLabel(null), '')
  assert.equal(attemptedLabel(undefined), '')
  assert.equal(basisVerb('extracted-from'), 'extracted from')
  assert.equal(basisVerb('derived-from'), 'derived from')
  assert.equal(basisVerb('outcome-of'), 'outcome of')
  assert.equal(basisVerb('in-context'), 'in context')
  assert.equal(summarizeBasis([]), 'no basis recorded')
  assert.equal(summarizeBasis(LADDER_ITEMS_FIXTURE.items[1].basis), 'extracted from Turn #64')
  // an outcome's own grounds: no "no basis recorded", each relation said
  const grounds = summarizeBasis([
    { ref: 'ent-7af8d6a38909', relation: 'outcome-of', kind: 'lesson', label: 'ent-7af8d6 lesson', cite: null },
    { ref: 'ent-turn-31', relation: 'in-context', kind: 'contribution', label: 'Turn #31', cite: null },
  ])
  assert.equal(grounds, 'outcome of ent-7af8d6 lesson · in context Turn #31')
  assert.equal(summarizeBasis([
    { ref: 'ent-a', relation: 'derived-from', kind: 'finding', label: 'a', cite: null },
    { ref: 'ent-b', relation: 'derived-from', kind: 'finding', label: 'b', cite: null },
  ]), 'derived from 2 findings')
}

// 14. adm cites: excerpt quoted, else the byte range of the named artifact; never the raw token
{
  const token = 'adm-5f164374a792@d12ab[10:42]'
  const withExcerpt = citeView({ ref: 'adm-5f164374a792', label: token, cite: token,
    artifact: { name: 'restart.log', size: 900, media_type: 'text/plain' }, range: [10, 42], excerpt: 'WinError 32' })
  assert.deepEqual(withExcerpt, { link: 'restart.log', quote: 'WinError 32', note: null, artifact: true })
  const noExcerpt = citeView({ ref: 'adm-5f164374a792', label: token, cite: token,
    artifact: { name: 'shot.png', size: 9000, media_type: 'image/png' }, range: [10, 42], excerpt: null })
  assert.deepEqual(noExcerpt, { link: 'bytes 10–42 of shot.png', quote: null, note: null, artifact: true })
  assert.equal(citeView({ ref: 'adm-5f164374a792', label: 'adm-5f164374a792', artifact: { name: 'a.md' } }).link, 'a.md')
  // an older server with no artifact fields: the range is read off the token, still not quoted
  const bare = citeView({ ref: 'adm-5f164374a792', label: token, cite: token })
  assert.equal(bare.quote, null)
  assert.equal(bare.link, 'bytes 10–42 of adm-5f164374a792')
  // an entry whose cite is a token says it, not quotes it; ordinary cites are quoted
  const entryCite = citeView({ ref: 'ent-31c902a4e812', label: 'finding', cite: token })
  assert.equal(entryCite.quote, null)
  assert.equal(entryCite.note, 'cites bytes 10–42 of adm-5f164374a792')
  assert.equal(citeView(LADDER_ITEMS_FIXTURE.items[0].basis[0]).quote, LADDER_ITEMS_FIXTURE.items[0].basis[0].cite)
  assert.equal(artifactIdOf(token), 'adm-5f164374a792')
  assert.equal(artifactUrl(token), '/api/artifacts/adm-5f164374a792')
  assert.ok(isArtifactRef('adm-5f164374a792') && !isArtifactRef('ent-5f164374a792'))
  // evidence text is shown once
  assert.equal(evidenceText({ text: 'Turn #64', label: 'Turn #64' }), null)
  assert.equal(evidenceText({ text: 'Short', label: 'Short words, longer label' }), null)
  assert.equal(evidenceText({ text: 'Words that say more.', label: 'ent-1 finding' }), 'Words that say more.')
}

// 15. agent options from the unfiltered set: aliases, runtimes, persona names that occur
{
  const items = LADDER_ITEMS_FIXTURE.items.map((it, i) => i === 0
    ? { ...it, recorded_by: { ...it.recorded_by, persona_name: 'Caretaker persona' } } : it)
  const opts = agentOptionsOf(items)
  for (const want of ['@Caretaker', 'claude', '@Builder', 'agy', '@Quill', 'Caretaker persona']) assert.ok(opts.includes(want), want)
  // runtime `codex` and alias `@Quill` are two choices: a name is not a runtime
  assert.ok(opts.includes('codex'))
  // a record from before such names were refused can still show an alias and
  // a runtime that read the same word: one choice, as the filter matches either
  const legacy = agentOptionsOf([{ ...items[0], recorded_by: { ...items[0].recorded_by, alias: '@Codex', runtime: 'codex' } }])
  assert.deepEqual(legacy.filter((o) => o.toLowerCase().replace(/^@/, '') === 'codex'), ['@Codex'])
  assert.ok(!opts.includes('Reviewer'))
  assert.equal(new Set(opts.map((o) => o.toLowerCase().replace(/^@/, ''))).size, opts.length)
  // narrowing to one agent does not narrow the choices made from the unfiltered set
  const narrowed = filterLadderItems(items, { ...DEFAULT_LEARNING_FILTERS, agent: 'Builder' }, FIXTURE_NOW_SEC)
  assert.ok(agentOptionsOf(items, 'Builder').length > agentOptionsOf(narrowed, 'Builder').length)
  // the client fallback matches persona names as the server does
  assert.equal(filterLadderItems(items, { ...DEFAULT_LEARNING_FILTERS, agent: 'Caretaker persona' }, FIXTURE_NOW_SEC).length, 1)
  assert.equal(LADDER_ITEMS_FIXTURE.counts.all, 263)
}

// 16. challenges: only open ones warn; answered ones carry their resolution line
{
  const chs = LADDER_ADOPTION_FIXTURE.requests[1].challenges
  const { open, resolved } = splitChallenges(chs)
  assert.deepEqual(open.map((c) => c.link), ['ent-disp-771'])
  assert.deepEqual(resolved.map((c) => c.link), ['ent-disp-772'])
  assert.equal(challengeResolvedLine(resolved[0]),
    'withdrawn by @Quill: Covered by “separating any failures that also fail on base”.')
  assert.equal(challengeResolvedLine(LADDER_ITEM_DETAIL_FIXTURE.challenges[0]),
    'set aside by @Caretaker: The lesson explicitly says "/api/runtime’s build_commit OR the checkout HEAD".')
  assert.equal(challengeResolvedLine(open[0]), null)
  // Set aside only for the owner, on somebody else's open challenge; Withdraw only on your own
  assert.deepEqual(challengeActsFor(open[0], 'ent-brian', 'ent-brian'), { withdraw: false, setAside: true })
  assert.deepEqual(challengeActsFor(open[0], 'ent-other', 'ent-brian'), { withdraw: false, setAside: false })
  assert.deepEqual(challengeActsFor(open[0], 'ent-verifier', 'ent-brian'), { withdraw: true, setAside: false })
  assert.deepEqual(challengeActsFor(open[0], 'ent-brian', null), { withdraw: false, setAside: false })
  assert.deepEqual(challengeActsFor(resolved[0], 'ent-codex', 'ent-brian'), { withdraw: false, setAside: false })
}

// 17. one vocabulary: Ladder material is all but adopted governing material; who asked
{
  assert.equal(isLadderMaterial({ governs: true, status: 'adopted' }), false)
  assert.equal(isLadderMaterial({ governs: true, status: 'adoption_requested' }), true)
  assert.equal(isLadderMaterial({ governs: false, status: 'adopted' }), true)
  assert.equal(isLadderMaterial(null), false)
  assert.deepEqual(askedByOf(LADDER_ADOPTION_FIXTURE.requests[0].asked_by), { who: '@Caretaker', migratedBy: '@brian' })
  assert.deepEqual(askedByOf(LADDER_ADOPTION_FIXTURE.requests[1].asked_by), { who: '@Caretaker', migratedBy: null })
  assert.deepEqual(askedByOf({ by: 'ent-x', by_alias: 'Quill', migrated_by: 'ent-o' }), { who: '@Quill', migratedBy: '@ent-o' })
}

// 18. "Waiting on you" counts only OPEN challenges to standing material
{
  type R = { entry: string; state: 'stands' | 'candidate'; disputed_by: string[]; open_disputes?: string[] }
  const rows: R[] = [
    { entry: 'ent-open', state: 'stands', disputed_by: ['o1'], open_disputes: ['o1'] },
    { entry: 'ent-withdrawn', state: 'stands', disputed_by: ['o2'], open_disputes: [] },
    { entry: 'ent-aside', state: 'stands', disputed_by: ['o3', 'o4'], open_disputes: [] },
    { entry: 'ent-mixed', state: 'stands', disputed_by: ['o5', 'o6'], open_disputes: ['o6'] },
    { entry: 'ent-candidate', state: 'candidate', disputed_by: ['o7'], open_disputes: ['o7'] },
    { entry: 'ent-unread', state: 'stands', disputed_by: ['o8'] },
  ]
  const ids = (got: R[]) => got.map((r) => r.entry)
  assert.deepEqual(ids(waitingChallenges(rows)), ['ent-open', 'ent-mixed'])
  assert.deepEqual(ids(waitingChallenges(rows, (e) => e === 'ent-open')), ['ent-mixed'])
}

console.log('fluid_ladder_unit: all 18 test groups passed.')
