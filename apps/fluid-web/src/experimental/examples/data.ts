import { F3, type Example } from './model'

export const dataExamples: Example[] = [
  {
    id: 'form-1',
    category: 'form',
    title: 'Simple form: a meeting request',
    note: 'Fill it in; the Markdown keeps only the defaults. Press “Ask for a slot” with Topic empty to see the required check. Every value you type is state keyed by the field id, so reordering lines in the source keeps it.',
    demands: ['The label must be in "double quotes"; without them the id is used as the label (a warning, not an error).'],
    source: `${F3}form version=1 title="Book a review" submit="Ask for a slot"
topic: text "Topic" required hint="One line: what should we look at?"
length: select "Length" choices=15,30,60 default=30 hint="minutes"
remote: checkbox "Join remotely"
${F3}`,
  },
  {
    id: 'form-2',
    category: 'form',
    title: 'Rich form: every kind, sections, conditions and ranges',
    note:
      'Try: pick “Other” under Reason (a new field appears); tick “Travelling” (a section’s fields appear, and “Country” only when Destination is abroad); type 45 or “ten” into Days; type a date before 2026-10-01. Hidden fields are left out of the values and of validation. Switch to Degraded: each field comes back as a declaration line plus its value now.',
    demands: [
      'when= must name a field ABOVE it (conditions read top to bottom); naming a later field is an error.',
      'when=field=value is two “=” in one word. A value with spaces must be quoted after the second “=”: when=reason="other reason". A weak model may write when="reason=other" (also accepted) or when=reason==other (not accepted).',
      'min/max mean different things per kind: a number’s value, a date’s bounds, text length in characters, how many of a multi are ticked. The renderer says which in its errors, but the author has to know.',
      'Checkbox defaults and conditions use yes/no, not true/false.',
      'choices with a comma inside a choice need quotes: choices=a,"b, c". Quote rules for one line are the main thing to get right.',
    ],
    source: `${F3}form version=1 title="Leave request" submit="Request leave"
## Who and when
name: text "Your name" required min=2 max=60
start: date "First day" required min=2026-10-01 max=2027-09-30
days: number "Working days" required min=0.5 max=30 unit=days default=1 hint="Half days are fine (0.5)."
reason: radio "Reason" required choices=holiday,sick,parental,other
reason_other: textarea "Tell us more" required when=reason=other hint="A sentence is enough."
## Travel
travelling: checkbox "Travelling during the leave"
destination: select "Destination" required choices=domestic,abroad when=travelling
country: text "Country" required when=destination=abroad
reachable: multi "Reachable by" choices=email,phone,"not at all" default=email min=1 when=travelling
## Handover
cover: text "Who covers for you" hint="Leave empty if nobody is needed."
agree: checkbox "I have told my team" required
${F3}`,
  },
  {
    id: 'form-3',
    category: 'form',
    title: 'Form with declaration mistakes (shows the checks)',
    note: 'Nothing is drawn: every problem names its line and says what to write instead. Fix them one at a time in the source on the left.',
    source: `${F3}form version=1 title="Broken on purpose"
size: select "Size" choices=S,M,L default=XL
size: text "Size again"
qty: number "Quantity" min=10 max=2
colour: radio "Colour"
notes: memo "Notes"
gift: text "Gift message" when=wrap
wrap: checkbox "Gift wrap"
${F3}`,
  },
  {
    id: 'table-1',
    category: 'table',
    title: 'Simple table: sort and filter',
    note: 'Click a column heading to sort (ascending, descending, back to source order); the numeric column sorts as numbers because every cell in it is one. Type in the filter. Sort and filter are kept as state, so they survive pinning and show up in Degraded and in Send back.',
    source: `${F3}table version=1 title="Largest Nordic cities"
city,country,population
Stockholm,Sweden,984748
Oslo,Norway,709037
Copenhagen,Denmark,660842
Helsinki,Finland,674500
Gothenburg,Sweden,604616
Bergen,Norway,291940
${F3}`,
  },
  {
    id: 'table-2',
    category: 'table',
    title: 'Rich table: choose rows and correct cells',
    note:
      'Tick rows to choose them (the header box chooses every shown row); correct quantity, price or note (✎ columns). Edited cells are marked and hover shows the source value; typing “ten” into a numeric column is kept but flagged. Selection and edits are keyed by sku, so they follow the row when you sort, filter, or reorder lines in the source. Degraded shows the source rows with edits applied and marked, then the selection and an edit list.',
    demands: [
      'Cells with commas must be quoted CSV ("Bolt, M6"); an unquoted comma shifts the row and is reported as a cell-count problem.',
      'key= must be a column whose values are unique and never empty. A weak model may pick a name column with duplicates; that is an error naming both lines.',
    ],
    source: `${F3}table version=1 title="Reorder list" key=sku select=many editable=qty,price,note
sku,item,supplier,qty,price,note
A-100,"Bolt, M6",Fastco,500,0.12,
A-101,"Bolt, M8",Fastco,250,0.18,
A-102,"Nut, M6",Fastco,500,0.05,
A-103,"Nut, M8",Fastco,250,0.07,
A-110,Washer M6,Fastco,1000,0.02,
B-200,Cable tie 200mm,Wireline,300,0.04,
B-201,Cable tie 300mm,Wireline,200,0.06,
B-210,Heat shrink kit,Wireline,10,8.50,check colours
C-300,Drill bit 6mm,ToolHouse,20,2.40,
C-301,Drill bit 8mm,ToolHouse,20,2.90,
C-302,Drill bit 10mm,ToolHouse,10,3.60,
C-310,Hole saw set,ToolHouse,2,34.00,only if budget allows
D-400,Safety glasses,SafeWork,12,4.75,
D-401,Ear defenders,SafeWork,6,12.90,
D-402,Work gloves L,SafeWork,24,3.20,
D-403,Work gloves XL,SafeWork,12,3.20,
E-500,Masking tape,StickIt,40,1.10,
E-501,Duct tape,StickIt,15,4.30,
E-502,Double-sided tape,StickIt,,5.80,qty unknown
${F3}`,
  },
  {
    id: 'table-3',
    category: 'table',
    title: 'Table without a key (a warning, and one choice)',
    note: 'select=one gives radio buttons (click the chosen one again to clear it). There is no key=, so rows are known by position (#1, #2 …): the note under the card says what that risks. Choose a row, then swap two lines in the source and watch the choice move.',
    demands: ['Nothing forces a key; without one the table still works but state is positional. The warning is the only nudge.'],
    source: `${F3}table version=1 title="Pick a venue" select=one
venue,seats,distance_km,price
Harbour Hall,120,2.5,high
Old Library,60,0.8,medium
Rooftop Loft,40,4.1,high
Community Room,80,1.2,low
${F3}`,
  },
]
