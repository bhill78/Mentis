import { F3, F4, type Example } from './model'

export const mediaExamples: Example[] = [
  {
    id: 'image-generate',
    category: 'image',
    title: 'Ask for a new picture (nothing is generated)',
    note:
      'intent=generate with source=none: the body is the description of the picture wanted. Click the picture to enlarge and zoom; write a note. Change a word in the body and the mock drawing changes, deterministically.',
    source: `${F3}image version=1 intent=generate source=none alt="A lighthouse on a rocky point at dusk" title="Cover picture for the field notes"
A lighthouse on a low rocky point at dusk, light just switched on, calm sea, no people. Wide, quiet, a little cold.
${F3}`,
  },
  {
    id: 'image-show',
    category: 'image',
    title: 'Show an existing item by ref (nothing is retrieved)',
    note:
      'intent=show needs somewhere to show from: here source=refs refs=… The card says which item would be shown and that it was not retrieved. Try deleting source=refs to see the refs rule, or source= entirely to see the intent=show rule.',
    demands: ['intent=show needs source (and refs when source=refs): two attributes that must agree, the same rule as pad.'],
    source: `${F3}image version=1 intent=show source=refs refs=photo:site-visit-2026-09-12/07 alt="North wall of the pump house, crack running from the window corner"
The crack we discussed: it starts at the lower-left corner of the window and runs about a metre down.
${F3}`,
  },
  {
    id: 'gallery-1',
    category: 'gallery',
    title: 'Pick one cover from ten candidates',
    note:
      'Select one (radio on each thumbnail, or Space), move with the arrow keys, read the caption in the detail pane, add a note to any picture. Each row’s ref sits under the declared refs (album:…/07 is under album:…). Pin it: in the narrow dock the detail moves below the grid. Image and gallery share one item renderer (the detail pane IS the image figure).',
    demands: [
      'CSV: a caption containing a comma must be wrapped in double quotes ("like, this"). A weak model often forgets, which shifts the columns; the problem is reported per line.',
      'ids must be unique and are what the selection and notes are keyed on.',
    ],
    source: `${F3}gallery version=1 select=one title="Cover candidates" source=refs refs=album:field-notes-2026
id,title,caption,ref,alt
c1,Lighthouse at dusk,"Wide, quiet; the light just on",album:field-notes-2026/01,Lighthouse on a rocky point at dusk
c2,Harbour wall,Waves breaking over the old wall,album:field-notes-2026/02,Waves over a stone harbour wall
c3,Net sheds,Tarred sheds in a row,album:field-notes-2026/03,Black wooden sheds along a quay
c4,Tide pool,"Close-up: anemones, one crab",album:field-notes-2026/04,Anemones and a crab in a tide pool
c5,Pump house,The north wall before repair,album:field-notes-2026/05,Brick pump house with a cracked wall
c6,Fog bank,Fog rolling in over the point,album:field-notes-2026/06,A fog bank covering a headland
c7,Boat ramp,Low tide; the ramp fully exposed,album:field-notes-2026/07,Concrete boat ramp at low tide
c8,Gulls,Three gulls on the rail,album:field-notes-2026/08,Three gulls on a metal railing
c9,Path,The cliff path looking south,album:field-notes-2026/09,Narrow path along a cliff edge
c10,Night,The beam over the water,album:field-notes-2026/10,Lighthouse beam across dark water
${F3}`,
  },
  {
    id: 'gallery-2',
    category: 'gallery',
    title: 'A gallery of one (is it just an image?)',
    note:
      'The same item drawn by the gallery. Compare with the image examples: the picture, caption, alt, ref and zoom are one shared renderer. What the gallery adds (selection, per-item notes, navigation) and what image adds (intent: show vs generate) are why they stay two types.',
    source: `${F3}gallery version=1 select=none source=conversation
id,title,caption,alt
only,Pump house,The north wall before repair,Brick pump house with a cracked wall
${F3}`,
  },
  {
    id: 'compare-1',
    category: 'compare',
    title: 'Three ways to host the relay (with a chart inside one option)',
    note:
      'Mark each option against each criterion (click a cell: + − ? ·), write a note per option, pick one. Nothing is totalled or ranked. "Show differences" works on the plain-text options; the one holding a chart is shown as-is. In the dock the columns stack.',
    demands: [
      'The compare fence must be ```` because an option contains a ``` chart block.',
      'Each option starts with a "## Name" line; an option cannot use ## headings inside itself (use ###).',
      'criteria is a comma list in quotes when it has spaces.',
    ],
    source: `${F4}compare version=1 title="Where the relay runs" choose=one criteria="monthly cost,effort to set up,who can fix it,data leaves the house"
Three options we talked about on Tuesday. None is assumed.

## Home server
Runs on the box under the stairs.
Cost is electricity only.
Needs the router port opened.
Only the owner can fix it.

## Small VPS
A 2-core VPS at the usual host.
Cost is about 6 per month.
No router changes.
Anyone with the key can fix it.

## Managed service
Their hosted relay, nothing to run.
Cost depends on traffic:

${F3}chart version=1 form=bar x=tier y=monthly x_label="Traffic tier" y_label="Monthly cost" y_unit=EUR
tier,monthly
low,0
medium,9
high,24
${F3}

No router changes.
Only their support can fix it.
${F4}`,
  },
  {
    id: 'review-1',
    category: 'review',
    title: 'Approve a proposed change (material holds a chart and prose)',
    note:
      'Tick checks (add a note to any), write a comment, choose a decision. Choosing reject or request-changes asks for a reason; the summary line says what is missing. Send back shows exactly what would be handed over; nothing changes in Mentis.',
    demands: [
      'The review fence must be ```` because the material contains a ``` block.',
      'The two section lines must be exactly "## Material" and "## Checks"; other ## lines inside the material are kept as part of it.',
      'reason_required must name decisions that exist (spelled the same, e.g. request-changes).',
    ],
    source: `${F4}review version=1 title="Proposal: raise the latency alert to 500 ms" reason_required=reject,request-changes
## Material
**Proposal.** Raise the p99 alert threshold from 400 ms to 500 ms. Last week it paged six times; four were the Wednesday deploy, two were normal Friday load.

${F3}chart version=1 form=line x=day y=p99 x_label="Day" y_label="p99 latency" y_unit=ms title="Last week"
day,p99
Mon,410
Tue,395
Wed,520
Thu,640
Fri,430
${F3}

The Thursday peak (640 ms) would still page under the new threshold. Rollback: set it back to 400.

## Checks
- [ ] The chart covers a full normal week
- [ ] A real incident would still page at 500 ms
- [ ] The rollback is written down
- [ ] Whoever is on call has been told
- [ ] Nothing else reads this threshold
${F4}`,
  },
]
