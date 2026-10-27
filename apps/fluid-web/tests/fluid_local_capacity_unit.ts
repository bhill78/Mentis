/* LOCAL MODEL CAPACITY: a local runtime's model servers are resources, not a
 * subscription quota. Fluid says what they report -- models, what is loaded,
 * the memory and VRAM it holds, context in use -- and leaves out, rather than
 * zeroes, any figure a server did not give. */

import assert from 'node:assert/strict'
import { bytesSaid, capacityMeters, localModelSays, localServerSays, type RuntimeCapacity } from '../src/composer/execution'

const ollama = {
  name: 'ollama', url: 'http://127.0.0.1:11434', reachable: true, version: '0.40.11',
  loadedMemoryBytes: 1_200_000_000, loadedVramBytes: 900_000_000,
  models: [
    { id: 'qwen2.5:0.5b', loaded: true, memoryBytes: 1_200_000_000, vramBytes: 900_000_000, contextLoaded: 4096, contextLength: 32768 },
    { id: 'qwen3.5:9b', loaded: false, memoryBytes: null, contextLength: 262144 },
  ],
}
assert.equal(localServerSays(ollama), 'Ollama 0.40.11: 1 of 2 models loaded, 1.2 GB (900 MB VRAM)')
assert.equal(localModelSays(ollama.models[0]), 'qwen2.5:0.5b: 1.2 GB, 900 MB VRAM · context 4,096 of 32,768')
assert.equal(localModelSays(ollama.models[1]), 'qwen3.5:9b: context up to 262,144')

// Nothing loaded: no memory figure at all, not "0 MB".
assert.equal(localServerSays({ ...ollama, loadedMemoryBytes: 0, loadedVramBytes: 0,
  models: ollama.models.map(m => ({ ...m, loaded: false })) }), 'Ollama 0.40.11: 0 of 2 models loaded')
// LM Studio reports no memory: the line carries none.
assert.equal(localServerSays({ name: 'lmstudio', url: '', reachable: true, loadedMemoryBytes: null,
  models: [{ id: 'q', loaded: true }] }), 'LM Studio: 1 of 1 model loaded')
assert.equal(localServerSays({ name: 'lmstudio', url: '', reachable: false, why: 'x' }), 'LM Studio: not running')
assert.equal(bytesSaid(397_821_319), '398 MB')

// Local resources never become quota meters.
const local: RuntimeCapacity = { established: false, plan: null, why_not: null, windows: [],
  local: { servers: [ollama], runningTurns: 0, unavailable: { throughput: 'not reported' } } }
assert.deepEqual(capacityMeters(local), [])

console.log('local capacity: 8 checks passed')
