// Run every Fluid client unit test: node tests/run.mjs
import { readdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
const here = fileURLToPath(new URL('.', import.meta.url))
let failed = 0
for (const f of readdirSync(here).filter((n) => n.endsWith('_unit.mjs')).sort()) {
  // fluid_objects_unit needs the server's cases (FLUID_OBJECTS_CASES); run it when given.
  if (f === 'fluid_objects_unit.mjs' && !process.env.FLUID_OBJECTS_CASES) { console.log('skip ' + f + ' (no FLUID_OBJECTS_CASES)'); continue }
  const r = spawnSync(process.execPath, [here + f], { encoding: 'utf8' })
  console.log((r.status === 0 ? 'ok   ' : 'FAIL ') + f)
  if (r.status !== 0) { failed++; console.log(r.stdout + r.stderr) }
}
process.exit(failed ? 1 : 0)
