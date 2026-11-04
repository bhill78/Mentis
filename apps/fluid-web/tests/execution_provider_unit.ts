/* WHO SERVES A MODEL, SAID PLAINLY: `modelSays` puts the provider first when the
 * catalogue names one, never when it does not -- a hosted model under its own
 * runtime shows no provider at all, and an antigravity model shows which of its
 * several providers' families actually serves it. */

import assert from 'node:assert/strict'
import { modelSays, type ModelChoice } from '../src/composer/execution'

const model = (provider: string | null, locality = 'unknown'): ModelChoice =>
  ({ slug: 'x', name: 'x', efforts: [], default_effort: null, locality, provider })

// The ordinary hosted case: the runtime serves its own model, so no "via" at all.
assert.equal(modelSays(model(null), 'claude'), 'Claude')
assert.equal(modelSays(model(null), 'codex'), 'Codex')

// Antigravity is a gateway over several providers' models.
assert.equal(modelSays(model('claude'), 'antigravity'), 'Claude via Antigravity')
assert.equal(modelSays(model('gemini'), 'antigravity'), 'Gemini via Antigravity')
assert.equal(modelSays(model('gpt'), 'antigravity'), 'GPT via Antigravity')

// Locality travels alongside, when the catalogue reports it.
assert.equal(modelSays(model('ollama', 'local'), 'codex'), 'Ollama via Codex · local')

console.log('execution provider: 6 checks passed')
