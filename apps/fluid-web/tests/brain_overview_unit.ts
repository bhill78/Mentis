/* ABOUT THIS BRAIN, checked without a server or a browser: how a count and a
 * size are said, that a size nobody measured is never said as zero, that the
 * overview's lines carry the server's numbers and nothing else, and that the
 * portability sentence says exactly what is included and what is left out,
 * each clause only where it is true. */
import assert from 'node:assert/strict'
import {
  brainName, diskLine, diskRows, fetchBrainOverview, folderWords, holdsLines, kindRows, leftOutRows, measuredWords, num, originRows, portableWords, size, standingRows, things,
  type BrainOverviewData,
} from '../src/quiet2/brain/overview'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/* -- numbers --------------------------------------------------------------- */
eq(num(0), '0', 'zero')
eq(num(11218), '11,218', 'thousands')
eq(num(1234567), '1,234,567', 'millions')
eq(things(1, 'post'), '1 post', 'one')
eq(things(0, 'post'), '0 posts', 'none is plural')
eq(things(2, 'reply', 'replies'), '2 replies', 'its own plural')
eq(size(null), 'not measured', 'unknown is said, never 0')
eq(size(undefined), 'not measured', 'absent is said')
eq(size(0), '0 bytes', 'a real zero is a real zero')
eq(size(1), '1 byte', 'one byte')
eq(size(1023), '1,023 bytes', 'under a KB')
eq(size(1024), '1 KB', 'a KB is 1,024 bytes')
eq(size(1536), '1.5 KB', 'no trailing zero')
eq(size(396431360), '378 MB', 'three figures')
eq(size(3496610854), '3.26 GB', 'gigabytes')
eq(size(15 * 1024 * 1024), '15 MB', 'whole')

/* -- a Brain, as the server answers ---------------------------------------- */
const o: BrainOverviewData = {
  brain: { id: 'c-1', corpus_name: 'TEST', corpus_role: 'development' },
  read_at: 1795200000,
  counts: {
    conversations: { total: 111, archived: 4, trash: 1 }, posts: 11218,
    knowledge: { total: 285, kinds: [{ kind: 'finding', count: 70 }, { kind: 'note', count: 215 }], standing: [{ status: 'adopted', count: 3 }, { status: 'adoption_requested', count: 0 }, { status: 'recorded', count: 282 }, { status: 'declined', count: 0 }], past: 0 },
    governing: { total: 73, kinds: [{ kind: 'conversation-instruction', count: 12 }, { kind: 'rule', count: 61 }], standing: [{ status: 'adopted', count: 31 }, { status: 'adoption_requested', count: 2 }, { status: 'recorded', count: 38 }, { status: 'declined', count: 2 }], past: 45 },
    files: { unique: 7908, references: 8001, purged_references: 0, purged_files: 0, recorded_bytes: 3496000000, unsized: 0, origins: [
      { group: 'returned', origin: 'execution', references: 4990, unique: 4900, bytes: 2900000000 },
      { group: 'source', origin: 'git', references: 1573, unique: 1570, bytes: 500000000 },
      { group: 'attached', origin: 'submission', references: 210, unique: 200, bytes: 90000000 },
      { group: 'other', origin: 'avatar', references: 17, unique: 17, bytes: 6000000 }] },
    sources: { total: 2, bound: 1, collections: [
      { collection: 'col-1', name: 'Mentis repository', connector: 'git', connector_label: 'Git repository', bound: true },
      { collection: 'col-2', name: 'D&D Knowledge', connector: 'filesystem', connector_label: 'Folder', bound: false }] },
  },
  storage: {
    measured_at: 1795199400, kept_for_s: 600, folder_why_not: null,
    database: { bytes: 417925240, why_not: null, files: [{ name: 'corpus.db', bytes: 396431360 }, { name: 'corpus.db-wal', bytes: 21461112 }, { name: 'corpus.db-shm', bytes: 32768 }], copy_bytes: 396595200 },
    files: { why_not: null, on_disk: 7928, bytes: 3496610854, missing: 0, missing_bytes: 0, unnamed: 20, unnamed_bytes: 610854, purged_present: 0, purged_present_bytes: 0, stray: 0, stray_bytes: 0 },
    kept: [{ what: 'runtime-notes', files: 3, bytes: 31000000, why_not: null, portable: true }, { what: 'presentation', files: 40, bytes: 7100000, why_not: null, portable: true }],
    other: [{ what: 'derived', files: 8, bytes: 2100000, why_not: null, portable: false }],
  },
  portable: {
    bytes: 3931306054, why_not: null, as: 'python -m mentis.brain backup --portable', not_counted: ['BACKUP.json'],
    parts: [{ part: 'database', bytes: 396595200 }, { part: 'files', bytes: 3496610854, count: 7928 }, { part: 'kept', bytes: 38100000, count: 2 }],
    left_out: { sources: 2, purged_files: 0, purged_bytes: 0, missing_files: 0, stray_files: 0, stray_bytes: 0, other: [{ what: 'derived', files: 8, bytes: 2100000, why_not: null, portable: false }], other_bytes: 2100000, sidecar_bytes: 21493880 },
  },
}

eq(brainName(o), 'TEST · development', 'name and what it is for')
eq(brainName({ ...o, brain: { id: 'x', corpus_name: null, corpus_role: null } }), 'This Brain has no name recorded', 'no name is said, not invented')

/* -- the few lines: every number is the server's ---------------------------- */
eq(holdsLines(o), [
  '111 conversations (4 archived, 1 in Trash) · 11,218 posts',
  '285 knowledge records · 73 governing records, 31 in effect',
  '7,908 files, referred to 8,001 times · 2 connected sources',
], 'what it holds')
const bare: BrainOverviewData = { ...o, counts: { ...o.counts, conversations: { total: 1, archived: 0, trash: 0 }, posts: 1,
  knowledge: { ...o.counts.knowledge, total: 0, kinds: [] }, governing: { total: 0, kinds: [], standing: [], past: 0 },
  files: { ...o.counts.files, unique: 1, references: 1, origins: [] }, sources: { total: 0, bound: 0, collections: [] } } }
eq(holdsLines(bare), ['1 conversation · 1 post', '0 knowledge records · 0 governing records', '1 file · 0 connected sources'], 'singular, and no clause for what is not there')
eq(diskLine(o), 'Database 399 MB · Files 3.26 GB', 'sizes on disk: the database with its working files, the files as measured')
ok(!holdsLines(o).join(' ').match(/MB|GB|bytes/), 'counts carry no size')
ok(!diskLine(o).match(/conversation|post|record/), 'sizes carry no count of content')

/* -- portability: what it includes and leaves out, exactly ------------------ */
const p = portableWords(o)
eq(p.total, 'About 3.66 GB as a portable backup.', 'the estimate')
eq(p.includes, 'Includes the database, all 7,928 stored files, each once and the pictures, layouts and settings kept in the Brain’s folder.', 'what it includes')
eq(p.excludes, 'Leaves out the 2 connected sources themselves (their folders, repositories and databases stay where they are; only the copies already taken are included) and 2 MB that is rebuilt or belongs to this computer.', 'what it leaves out')
const whole = portableWords({ ...o, portable: { ...o.portable, left_out: { ...o.portable.left_out, sources: 0, other: [], other_bytes: 0 } } })
eq(whole.excludes, 'Leaves nothing of this Brain out.', 'nothing left out is said as that')
const lossy = portableWords({ ...o, portable: { ...o.portable, left_out: { ...o.portable.left_out, sources: 1, purged_files: 3, purged_bytes: 2048, missing_files: 1, stray_files: 2, stray_bytes: 10, other: [], other_bytes: 0 } } })
ok(lossy.excludes.includes('the connected source itself') && lossy.excludes.includes('3 files you removed (2 KB)')
  && lossy.excludes.includes('1 file the Brain refers to but no longer has on disk') && lossy.excludes.includes('2 unfinished or misplaced files (10 bytes)'), 'each thing left out is named with its count')
const unmeasured = portableWords({ ...o, portable: { ...o.portable, bytes: null, why_not: 'the database’s size could not be read' } })
eq(unmeasured.total, 'Not measured: the database’s size could not be read.', 'an estimate that could not be made is not a number')
const none = portableWords({ ...o, portable: { ...o.portable, parts: [{ part: 'database', bytes: 4096 }, { part: 'files', bytes: 0, count: 0 }, { part: 'kept', bytes: 0, count: 0 }] } })
eq(none.includes, 'Includes the database and no stored files (there are none).', 'a Brain with no files')

/* -- detail ----------------------------------------------------------------- */
eq(kindRows(o.counts.knowledge), [{ label: 'Finding', value: '70' }, { label: 'Note', value: '215' }], 'knowledge by kind')
eq(kindRows(o.counts.governing)[0], { label: 'Conversation instruction', value: '12' }, 'a kind in words')
eq(standingRows(o.counts.governing), [
  { label: 'Adopted', value: '31', note: 'in effect' },
  { label: 'Adoption requested', value: '2', note: 'waiting for a decision' },
  { label: 'Recorded', value: '38', note: 'not in effect' },
  { label: 'Adoption declined', value: '2', note: 'not in effect' },
  { label: 'Replaced or ended', value: '45', note: 'kept, not counted above' },
], 'governing records by standing, in the words the browser uses')
eq(standingRows(o.counts.knowledge).map((r) => r.label), ['Adopted', 'Recorded'], 'a standing nobody has is not listed (Adopted always is)')
eq(originRows(o).map((r) => r.label), ['Returned by agents', 'Taken from a source (Git repository)', 'Attached by people', 'Other (avatar)'], 'where files came from')
eq(originRows(o)[0], { label: 'Returned by agents', value: '2.7 GB', note: '4,900 files' }, 'unique files and their size')
const disk = diskRows(o)
eq(disk[0], { label: 'Database', value: '378 MB', note: 'corpus.db' }, 'the database file')
eq(disk[1].label, 'Database, changes not yet folded in', 'the -wal is said and counted')
eq(disk[3], { label: 'Stored files', value: '3.26 GB', note: '7,928 files, each kept once' }, 'stored files')
ok(disk.some((r) => r.label === 'Search and status indexes (rebuilt)' && r.note === '8 files · not in a portable backup'), 'what is not carried says so')
const out = leftOutRows(o)
eq(out[0], { label: 'Mentis repository', value: 'Git repository', note: 'stays where it is; where that is, is not part of the Brain' }, 'a connected source')
eq(out[1].note, 'not connected on this computer', 'an unbound source')
ok(out.some((r) => r.label === 'Search and status indexes (rebuilt)' && r.value === '2 MB'), 'the rest of the folder')
ok(out.some((r) => r.label === 'Database working files'), 'the working files')
ok(!JSON.stringify([holdsLines(o), diskLine(o), p, out, disk, originRows(o)]).match(/\b(ent|adm|opr|col)-[0-9a-f]/), 'no internal id is shown')
ok(measuredWords(o).includes('20 stored files (597 KB) are referred to by nothing; a portable backup carries them too.'), 'unnamed files are said')
ok(/Counts read at \d\d:\d\d\. The Brain’s folder was measured at \d\d:\d\d, by size only/.test(measuredWords(o)), 'when it was read and measured')

/* -- what could not be read is "not measured" with the reason, never zero ---- */
const unread: BrainOverviewData = { ...o,
  storage: { ...o.storage,
    files: { why_not: 'Access is denied', on_disk: null, bytes: null, missing: null, missing_bytes: null, unnamed: null, unnamed_bytes: null, purged_present: null, purged_present_bytes: null, stray: null, stray_bytes: null },
    kept: [{ what: 'presentation', files: null, bytes: null, why_not: 'Access is denied', portable: true }] },
  portable: { ...o.portable, bytes: null, why_not: 'the stored files could not all be read (Access is denied)',
    parts: [{ part: 'database', bytes: 396595200 }, { part: 'files', bytes: null, count: null }, { part: 'kept', bytes: null, count: 1 }],
    left_out: { ...o.portable.left_out, purged_files: null, purged_bytes: null, missing_files: null, stray_files: null, stray_bytes: null } } }
eq(diskLine(unread), 'Database 399 MB · Files not measured (Access is denied)', 'a size that could not be read says so and why')
eq(portableWords(unread).total, 'Not measured: the stored files could not all be read (Access is denied).', 'and so does the estimate')
ok(!/\b0 (bytes|files)/.test(JSON.stringify([diskLine(unread), portableWords(unread), diskRows(unread), leftOutRows(unread), measuredWords(unread)])), 'nothing unread is said as zero')
eq(diskRows(unread).find((r) => r.label === 'Stored files'), { label: 'Stored files', value: 'not measured', note: 'could not all be read: Access is denied' }, 'the stored files row')
eq(diskRows(unread).find((r) => r.label === 'Pictures, layouts and summaries'), { label: 'Pictures, layouts and summaries', value: 'not measured', note: 'could not all be read: Access is denied' }, 'an item that could not all be read gives no count and no size')
ok(measuredWords(unread).includes('The stored files could not all be read (Access is denied), so no size is given for them.'), 'said at the foot too')
eq(diskLine({ ...o, storage: { ...o.storage, database: { ...o.storage.database, bytes: null, why_not: 'Access is denied' } } }), 'Database not measured (Access is denied) · Files 3.26 GB', 'the database likewise')

/* -- the folder is said by what things are; the rest is one line, unnamed ---- */
const extra: BrainOverviewData = { ...o, storage: { ...o.storage, other: [...o.storage.other, { what: 'other', files: 2, bytes: 750, why_not: null, portable: false }] } }
eq(diskRows(extra)[diskRows(extra).length - 1], { label: 'Other files in the Brain’s folder', value: '750 bytes', note: '2 files · not in a portable backup' }, 'what Mentis did not put there, together')
eq(folderWords('something-new'), 'Other files in the Brain’s folder', 'an item this page does not know is not named either')

/* -- the read --------------------------------------------------------------- */
const asked: string[] = []
globalThis.fetch = (async (url: string) => { asked.push(String(url)); return { ok: true, statusText: 'OK', json: async () => o } }) as unknown as typeof fetch
eq((await fetchBrainOverview()).counts.posts, 11218, 'the answer, as it is')
await fetchBrainOverview(true)
eq(asked, ['/api/brain/overview', '/api/brain/overview?measure=1'], 'measuring again is asked for, never assumed')

console.log(`brain_overview_unit: ${checks} checks passed`)
