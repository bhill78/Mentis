import { F3, type Example } from './model'

/* Real Problem records in the owner's Brain. At the time of writing the Brain
   held none; ent-c7bd20340989 was proposed (as a candidate, through the normal
   propose_material path) by @Caretaker in the Markdown Renderer Experiment
   Conversation, because it is a genuine problem this experiment found. */
const CONV = 'ent-7a71cef2d536' // Markdown Renderer Experiment

export const problemExamples: Example[] = [
  {
    id: 'problems-refs',
    category: 'problems',
    title: 'Live view: named Problems (explicit references)',
    note:
      'The block names Problems by id and says how to show them; it holds none of their state. Every value is read from Mentis and re-read when /api/pulse says the record moved. Pin it, then change the Problem in Mentis (Open in Mentis → delete/dispute/edit there) and watch the pinned copy follow. Add more ids to refs to watch them too.',
    source: `${F3}problems version=1 title="Problems I am watching" refs=ent-c7bd20340989 include=all
${F3}`,
  },
  {
    id: 'problems-conversation',
    category: 'problems',
    title: 'Live view: Problems raised in a Conversation (scoped query)',
    note:
      'Asks Mentis for Problems placed in, or raised in, one Conversation. Only those two associations exist in the record; Problems written without either are COUNTED as unplaceable, never guessed. When a new Problem is proposed in this Conversation it appears here without anybody editing the block.',
    demands: ['A Conversation id is an opaque ent-… string. Omitting conversation= binds the view to whichever Conversation it is first drawn in, which the surface records as its own state.'],
    source: `${F3}problems version=1 title="Problems raised in the Markdown Renderer Experiment" scope=conversation conversation=${CONV} order=newest
${F3}`,
  },
  {
    id: 'problems-brain',
    category: 'problems',
    title: 'Live view: every Problem in this Brain, replaced and deleted included',
    note: 'The widest honest scope. include=all keeps replaced and deleted Problems, labelled as what the record says happened to them.',
    source: `${F3}problems version=1 title="All Problems" scope=brain include=all show=text,author,recorded,record,place
${F3}`,
  },
  {
    id: 'problems-wrong-ref',
    category: 'problems',
    title: 'What a wrong reference shows',
    note: 'refs names a Conversation, not a Problem, and an id the record does not hold. Each is said as what it is rather than drawn as an empty row.',
    source: `${F3}problems version=1 title="Mixed references" refs=ent-c7bd20340989,${CONV},ent-000000000000
${F3}`,
  },
]
