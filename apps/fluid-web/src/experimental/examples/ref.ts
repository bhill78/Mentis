import { F3, type Example } from './model'

/* Every reference below is a REAL record in the owner's Brain, except
   ent-af299ce272f2, a disposable candidate note proposed for the deleted-
   reference test (delete it yourself through Open in Mentis). */
const PROBLEM = 'ent-c7bd20340989' // problem: no act means resolved (candidate)
const FINDING = 'ent-d34f8fa1eb3e' // finding: standing declared not meaningful
const INSTRUCTION = 'ent-24d91e6a4eb9' // conversation-instruction: established, governs
const PERSONA = 'ent-a811146c070a' // persona: established, name + behaviour
const TOPIC = 'ent-defaeb7f18e5' // topic
const CONVERSATION = 'ent-a221db3552de' // a Conversation
const PARTICIPANT = 'ent-5936369158a8' // @brian
const DEFINITION = 'def-e8e65105b7d6' // the Kind definition of "observation"
const TURN = 'ent-d4b387627317' // a Turn in this Conversation
const LINK = 'ent-c14604bb021a' // a `supersedes` link
const DISPOSABLE = 'ent-af299ce272f2' // disposable note, for deletion

export const refExamples: Example[] = [
  {
    id: 'ref-compact',
    category: 'reference',
    title: '1 · One existing item, inline (the smallest declaration)',
    note: 'The author emits an id. That is all: Mentis resolves it, discovers it is a Problem, and draws it. Expand is on the item; Pin and Open in Mentis are in its ⋯.',
    source: `The problem we found:

${F3}ref version=1 id=${PROBLEM}
${F3}

(ordinary prose continues around it)`,
  },
  {
    id: 'ref-expanded',
    category: 'reference',
    title: '2 · The same reference, expanded',
    note: 'Identical reference, one more word: presentation=expanded. Nothing about the material is in the declaration.',
    source: `${F3}ref version=1 id=${PROBLEM} presentation=expanded
${F3}`,
  },
  {
    id: 'ref-generic',
    category: 'reference',
    title: '3 · Arbitrary Kinds with NO specialised presentation (generic fallback)',
    note: 'A finding (standing not meaningful), an established Conversation instruction, an established Persona with two fields, a Topic, a Conversation and a Participant. None has a presentation of its own; each is drawn only from what its record says. Expand each.',
    source: `${F3}ref version=1 title="Different Kinds, one renderer"
${FINDING}
${INSTRUCTION}
${PERSONA}
${TOPIC}
${CONVERSATION}
${PARTICIPANT}
${F3}`,
  },
  {
    id: 'ref-special',
    category: 'reference',
    title: '4 · Specialised presentations, switchable back to generic',
    note: 'A Kind definition (shown as the schema it declares) and a Turn (shown as the Turn reads, through the ordinary prose reader). Expand, then switch Presentation to Generic: the same record, drawn without the specialisation, loses nothing.',
    source: `${F3}ref version=1 presentation=expanded
${DEFINITION}
${TURN}
${F3}`,
  },
  {
    id: 'ref-mixed',
    category: 'reference',
    title: '5 · Mixed working material (pin the whole surface, or one item)',
    note: 'Several Kinds side by side as references, not copies. Pin the block from its header, or pin one item with its own Pin. Pinned items are live: change one in Mentis and the dock follows.',
    source: `${F3}ref version=1 title="Working material"
- ${INSTRUCTION}
- ${PERSONA}
- ${PROBLEM}
- ${FINDING}
- ${DEFINITION}
${F3}`,
  },
  {
    id: 'ref-broken',
    category: 'reference',
    title: '6 · Unknown, malformed, other-provider, link and deleted references',
    note: `Each degrades on its own line; the block and the Turn around it stay. ${DISPOSABLE} is a disposable note: expand it, Pin it, then delete it via Open in Mentis → delete, and watch the pinned copy.`,
    demands: ['A link entry resolves, but /api/entries does not return what it links, so its endpoints cannot be shown generically.'],
    source: `${F3}ref version=1 title="Things that go wrong"
ent-000000000000
ent-XYZ!
jira:MR-12
opr-8685f338bc1f
${LINK}
${DISPOSABLE}
${F3}`,
  },
]
