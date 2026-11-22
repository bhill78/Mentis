// Serializes the production request builder for the real HTTP/worker gate test.
import { registerHooks } from 'node:module'
import { readFileSync } from 'node:fs'
import ts from '../node_modules/typescript/lib/typescript.js'
registerHooks({
  load(url, context, next) {
    if (url.endsWith('.ts')) return { format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(new URL(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
      }).outputText }
    return next(url, context)
  },
})
const { agentsOf, groundedRequest } = await import('../src/quiet2/magnets/evidence.ts')
const input = JSON.parse(readFileSync(0, 'utf8'))
const agent = input.people ? agentsOf(input.people).find(a => a.id === input.agent.id) : input.agent
if (!agent) throw Error('The explicitly chosen recipient was not offered by Fluid.')
process.stdout.write(JSON.stringify(groundedRequest(input.magnet, input.author,
  input.question, input.replyTo ?? null, input.op, agent, input.collection)))
