/* Fluid F1: ONE SOURCE OF OBJECT IDENTITY, held in Node against the UI source.

   For every post the Python test hands over (FLUID_OBJECTS_CASES, a JSON file):
     * the server's keys -- read by the bundle in the embedded engine -- are
       the keys `objectsOfPost` gives in the client, from the same input;
     * they are the Workspace Lab's keys (`objectsOfTurn`, which the Lab
       keeps for now), read from the Turn exactly as production serves it;
     * where the server could not extract (no engine), the `input` it handed
       back keys to the same objects the engine read.
   Run by tests/test_fluid_objects.py. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import type { Turn } from '../src/api'
import { objectsOfPost, type PostInput } from '../src/experimental/postobjects'

interface Row { key: string; kind: string; parent: string | null; part?: number | null }
interface Case { name: string; turn: Turn; input: PostInput; server: Row[]; fallback?: PostInput }

const path = process.env.FLUID_OBJECTS_CASES
if (!path) throw new Error('FLUID_OBJECTS_CASES names the cases file')
const cases = JSON.parse(readFileSync(path, 'utf8')).cases as Case[]
let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const rows = (xs: Row[]) => xs.map((o) => ({ key: o.key, kind: o.kind, parent: o.parent }))

let objects = 0
for (const c of cases) {
  const server = rows(c.server)
  const client = objectsOfPost(c.input)
  eq(rows(client), server, `${c.name}: the client's keys are the server's`)
  eq(client.map((o) => o.part), c.server.map((o) => o.part), `${c.name}: the parts agree`)
  /* The production Turn, given to the shared function as it is, keys alike. */
  eq(rows(objectsOfPost(c.turn as unknown as PostInput)), server, `${c.name}: the production Turn keys alike`)
  if (c.fallback) eq(rows(objectsOfPost(c.fallback)), server, `${c.name}: without the engine the client keys alike`)
  objects += server.length
}
if (!cases.length || !objects) throw new Error('no cases were checked')
console.log(`${cases.length} posts, ${objects} objects: ${checks} checks passed`)
