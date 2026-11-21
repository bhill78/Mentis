/* WHAT A RECORDED RESULT POINTS AT, checked without a browser
 * (src/quiet2/results/targets.ts): exact identity, the server's own
 * availability and `opens` words, whether a thing can be opened AT ALL, the
 * commit identity the record states, the external-URL policy of this opener,
 * and where the bytes came from as against where they were opened from.
 *
 * The rows are the navigation review's own falsifiers: B2/P1-P5 (provenance,
 * reach, URL policy), B4/V4 (typed handling), and the focused review's M2.1
 * and M2.2 (commit `sha`/`repository`; `state === 'ok'` is not openability). */
import assert from 'node:assert/strict'
import {
  REFERENCED_ONLY, actionOf, actionable, availabilityOf, commitOpens, commitTarget, externalHref, goneWords,
  destinationOfRef, isCommitSha, isProseAdmission, isRefId, openable, opensOf, sourceOf, targetKey, targetOfStated,
  type Availability, type Basis, type ResultDestination, type ResultTarget, type StatedReference,
} from '../src/quiet2/results/targets'
import type { ViewerSource } from '../src/quiet2/viewer/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const no = (a: unknown, what: string) => { assert.ok(!a, what); checks++ }

const SHA = 'a'.repeat(40)
const HERE = 'https://mentis.example'

const dest = (over: Partial<ResultDestination> & { target: ResultTarget }): ResultDestination => ({
  label: 'a result', source: null, basis: ['returned-by-run'], verified: true,
  availability: 'ok', available: true, opens: 'file', ...over,
})
const file = (over: Partial<ResultDestination> = {}) => dest({ target: { kind: 'artifact', ref: 'adm-667a23eb07a8' }, ...over })

/* -- exact identity, never a label ------------------------------------------ */
{
  ok(isRefId('adm-667a23eb07a8') && isRefId('ent-6c39bfc11d0d') && isRefId('opr-a71d4f7a25fc'), 'the record states these three')
  no(isRefId('adm-') || isRefId('post #88') || isRefId('x-667a23eb07a8'), 'nothing else is an identity')
  ok(isProseAdmission('adm-667a23eb07a8'), 'in prose, exactly twelve lowercase hex (review NB1)')
  no(isProseAdmission('adm-667A23EB07A8') || isProseAdmission('adm-667a23eb07a') || isProseAdmission('adm-667a23eb07a8b'), 'and nothing else, in prose')
  ok(isCommitSha(SHA), 'a whole revision')
  no(isCommitSha('a'.repeat(12)) || isCommitSha(SHA + 'a'), 'an abbreviation names no exact object')
  eq(targetKey({ kind: 'artifact', ref: 'adm-1' }), 'artifact:adm-1', 'identity, not label, tells two destinations apart')
  eq(targetKey({ kind: 'commit', sha: SHA, repository: 'bhill78/Mentis' }), `commit:bhill78/Mentis:${SHA}`, 'a commit is its repository and revision')
}

/* -- the server's own words -------------------------------------------------- */
{
  eq(availabilityOf('held'), 'ok', "an artifact descriptor's `held` is inspection's `ok`, not a new state")
  for (const w of ['ok', 'missing', 'deleted', 'erased', 'unreadable', 'purged', 'not-held', 'held-but-missing', 'held-but-corrupt'] as Availability[])
    eq(availabilityOf(w), w, `inspection's own word kept: ${w}`)
  eq(availabilityOf('quarantined'), 'unreadable', 'a word from a later server degrades, never a competing enum')
  eq(availabilityOf(null), 'unreadable', 'no word is not availability')
  eq(opensOf('file'), 'file', "inspection's own route")
  eq(opensOf('anything-else'), null, 'and nothing else is a route')
  for (const a of ['missing', 'deleted', 'erased', 'purged', 'not-held', 'held-but-missing', 'held-but-corrupt', 'unreadable'] as Availability[])
    ok(goneWords(a).length > 10 && goneWords(a) !== goneWords('ok'), `what is wrong is said as what it is: ${a}`)
}

/* -- openability: `ok` IS NOT THE CHECK (focused review M2.2) ---------------- */
{
  ok(openable(file()).can, 'held, and there is a route to it')
  const orphan = file({ opens: null })
  no(openable(orphan).can, 'ok with no route is not openable (an orphan post, a postless expectation, a run act)')
  eq(openable(orphan).why, 'The record holds it, and there is nothing here that opens it.', 'and it says so instead of offering a broken press')
  eq(actionOf(orphan), 'unavailable', 'so pressing it is not a file open')
  const gone = file({ available: false, availability: 'purged', reason: 'its contents were purged' })
  no(openable(gone).can, 'not available: not openable')
  eq(openable(gone).why, 'its contents were purged', "the server's own reason, where it gave one")
  eq(openable(file({ available: false, availability: 'held-but-corrupt', reason: null })).why, goneWords('held-but-corrupt'), 'and our own exact words where it did not')
  no(openable(file({ availability: 'unreadable', available: true })).can, 'available with a bad state is still not openable')
  no(openable(file({ opens: 'post' })).can, 'held bytes are not opened through a post route')
}

/* -- what pressing it does, by the target's own discriminant ----------------- */
{
  eq(actionOf(file()), 'file', 'an artifact opens held bytes')
  eq(actionOf(dest({ target: { kind: 'post', conversation: 'ent-c', post: 'ent-p' }, opens: 'post' })), 'post', 'a post opens its post')
  eq(actionOf(dest({ target: { kind: 'record', ref: 'ent-r' }, opens: 'record' })), 'record', 'a record opens its record')
  eq(actionOf(dest({ target: { kind: 'record', ref: 'ent-c' }, opens: 'conversation' })), 'conversation', 'a real conversation record opens the conversation')
  eq(actionOf(dest({ target: { kind: 'url', href: 'https://example.org/x' }, opens: null, available: false, availability: 'missing' })), 'external',
    'a URL is external handling whatever availability says: it is not a Mentis route')
  eq(actionOf(dest({ target: { kind: 'commit', sha: SHA }, opens: null, available: false, availability: 'missing' })), 'commit',
    'and a commit is identity handling; `opens: null` is expected for both, not a fabricated file route')
}

/* -- provenance: a claim alone is not a deliverable (review B2, P1/P2) ------- */
{
  ok(actionable(['returned-by-run']), 'a run returned it: actionable')
  ok(actionable(['authored-result-ref', 'attached-to-turn']), 'attached to a post as well: actionable')
  no(actionable(['authored-result-ref'] as Basis[]), 'a claim that merely names a ref establishes neither production nor reach')
  ok(/does not say this work produced it/.test(REFERENCED_ONLY), 'and it is labelled honestly')
}

/* -- source is not launch (review B3) --------------------------------------- */
{
  const post: ViewerSource = { kind: 'post', conversation: 'ent-c', post: 'ent-88' }
  eq(sourceOf(file({ source: post }), 'corpus@one'), post, 'the post the content came from is kept')
  eq(sourceOf(file({ source: null }), 'corpus@one'), { kind: 'brain', brainKey: 'corpus@one' }, 'the Brain itself where the record names no post')
  eq(sourceOf(file({ source: null }), null), null, 'and no source is invented where the Brain is unknown')
  eq(sourceOf(dest({ target: { kind: 'url', href: 'https://example.org/' }, source: null }), null), null, 'never a source post for a URL')
}

/* -- the commit the record states (focused review M2.1) --------------------- */
{
  eq(commitTarget({ sha: SHA, repository: 'bhill78/Mentis' }), { kind: 'commit', sha: SHA, repository: 'bhill78/Mentis', record: null },
    "the canonical fields are `sha` and `repository` (decision_presentation.py's `commit`)")
  eq(commitTarget({ sha: SHA.toUpperCase(), repository: '  ' }), { kind: 'commit', sha: SHA, repository: null, record: null }, 'one case, and a blank repository is none')
  eq(commitTarget({ sha: 'a'.repeat(12), repository: 'r' }), null, 'a shortened revision is refused')
  eq(commitTarget({ repository: 'r' }), null, 'and so is a commit with no revision at all')
  eq(commitTarget({ sha: SHA, record: 'ent-aaaaaa' })?.record, 'ent-aaaaaa', 'the record that states it, where one does')
  eq(commitTarget({ sha: SHA, record: 'nonsense' })?.record, null, 'and nothing that is not an identity')
  eq(commitOpens({ kind: 'commit', sha: SHA, record: 'ent-aaaaaa' }), { how: 'record', ref: 'ent-aaaaaa' }, 'through the record that states it')
  const bare = commitOpens({ kind: 'commit', sha: SHA, repository: 'bhill78/Mentis' })
  eq(bare.how, 'identity', 'otherwise its exact identity, said')
  ok(bare.how === 'identity' && /no commit viewer/i.test(bare.words), 'and no commit UI is claimed to exist')
}

/* -- the external-URL policy of THIS opener (review B2, P5) ----------------- */
{
  eq(externalHref('https://example.org/a?b=1#c', HERE), 'https://example.org/a?b=1#c', 'an absolute https URL, external to Mentis')
  eq(externalHref('http://example.org/', HERE), 'http://example.org/', 'and http')
  for (const bad of [
    'file:///C:/Work/Mentis/secret.md', 'javascript:alert(1)', 'data:text/html,<b>x', 'mailto:someone@example.org',
    '/api/artifacts/adm-667a23eb07a8', '../x', 'C:/Work/Mentis/x.html', '\\\\server\\share\\x',
    'https://user:pw@example.org/', 'https:// example.org', '', '   ',
  ]) eq(externalHref(bad, HERE), null, `refused by the result opener: ${bad || '(blank)'}`)
  eq(externalHref(HERE + '/api/work', HERE), null, 'a same-origin address is not an external result')
  eq(externalHref('https://example.org/', null), null, 'and with no origin to compare, nothing is opened')
  eq(externalHref('https://xn--n3h.example/', HERE), 'https://xn--n3h.example/', 'a punycode host is a host')
}

/* -- adapting the record's own typed references ------------------------------ */
{
  eq(targetOfStated({ kind: 'record', id: 'adm-667a23eb07a8' }, HERE), { kind: 'artifact', ref: 'adm-667a23eb07a8' }, 'an Admission identity is held bytes')
  eq(targetOfStated({ kind: 'record', id: 'opr-a71d4f7a25fc' }, HERE), { kind: 'record', ref: 'opr-a71d4f7a25fc' }, 'a request identity is a record')
  eq(targetOfStated({ kind: 'commit', repository: 'bhill78/Mentis', sha: SHA }, HERE), { kind: 'commit', sha: SHA, repository: 'bhill78/Mentis', record: null }, 'a commit')
  eq(targetOfStated({ kind: 'url', url: 'https://example.org/x' }, HERE), { kind: 'url', href: 'https://example.org/x' }, 'a URL, under the policy above')
  eq(targetOfStated({ kind: 'url', url: 'file:///x' }, HERE), null, 'and not one the policy refuses')
  eq(targetOfStated({ kind: 'record', id: 'not an id' } as StatedReference, HERE), null, 'nothing is taken from a label')
  eq(targetOfStated(null, HERE), null, 'and nothing from nothing')
  eq(targetOfStated({ kind: 'runtime' } as unknown as StatedReference, HERE), null, 'a kind this build does not know opens nothing')
}

/* -- a reference the server already resolved (B4: one opinion, not three) --- */
{
  const held = destinationOfRef({ id: 'adm-667a23eb07a8', type: 'file', label: 'review.png', available: true, state: 'ok', opens: 'file', file: { state: 'held', name: 'review.png', size: 2048 } })
  eq(held.target, { kind: 'artifact', ref: 'adm-667a23eb07a8' }, 'a file route on an Admission is held bytes')
  ok(openable(held).can && actionOf(held) === 'file', 'and it opens as a file')
  eq(held.file?.ref, 'adm-667a23eb07a8', 'with what the server said of the bytes, so no second read is needed to open them')
  const post = destinationOfRef({ id: 'ent-88', type: 'post', label: 'post #88', available: true, state: 'ok', opens: 'post', conversation: 'ent-c', post: 'ent-88' })
  eq(post.target, { kind: 'post', conversation: 'ent-c', post: 'ent-88' }, 'a post route needs the conversation the server named')
  eq(post.source, { kind: 'post', conversation: 'ent-c', post: 'ent-88' }, 'and that post is also where the content is from')
  const vague = destinationOfRef({ id: 'ent-88', type: 'post', available: true, state: 'ok', opens: 'post' })
  eq(vague.opens, null, 'a post route with no conversation opens nothing: it is said, never guessed from whatever is shown')
  eq(actionOf(vague), 'unavailable', 'so it is not offered as a press')
  const conv = destinationOfRef({ id: 'ent-c', type: 'conversation', label: 'Quiet', available: true, state: 'ok', opens: 'conversation', conversation: 'ent-c' })
  eq(actionOf(conv), 'conversation', 'a conversation reference opens the conversation')
  const gone = destinationOfRef({ id: 'ent-9', type: 'post', label: null, available: false, state: 'deleted', why: 'a deleted post', opens: null })
  no(openable(gone).can, 'what cannot be read is not openable')
  eq(openable(gone).why, 'a deleted post', "with the server's own words")
  eq(destinationOfRef({ id: 'ent-9', type: 'entry', available: true, state: 'quarantined', opens: 'record' }).availability, 'unreadable',
    'a state this build does not know degrades, and stays unopenable')
  eq(destinationOfRef({ id: 'ent-9', type: 'entry', available: true, state: 'ok', opens: 'record' }).label, 'ent-9', 'with no label, the id is shown rather than nothing')
  eq(destinationOfRef({ id: 'adm-1', type: 'file', available: true, state: 'ok', opens: 'file' }, { basis: ['authored-result-ref'] }).basis, ['authored-result-ref'],
    'the caller states the basis: this adapter claims none of its own')
}

console.log(`quiet2 result targets: ${checks} checks ok`)
