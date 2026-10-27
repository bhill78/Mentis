import { F3, F4, type Example } from './model'

export const basicExamples: Example[] = [
  {
    id: 'scratch',
    category: 'playground',
    title: 'Scratch: paste anything',
    note: 'Paste or write any Markdown. Every marked block in it is drawn; everything else is ordinary Markdown, exactly as a Turn shows it.',
    source: `Write anything here. Ordinary **Markdown** stays ordinary.

${F3}checklist version=1 title="Try me"
- [ ] Edit this declaration on the left
- [ ] Tick an item here
${F3}
`,
  },
  {
    id: 'checklist-1',
    category: 'checklist',
    title: 'Release checklist',
    note: 'Tick items; ticks are state, the Markdown keeps what the author wrote. Pin it and keep ticking in the dock: both copies share state.',
    source: `${F3}checklist version=1 title="Before the release"
- [x] Tag the commit
- [ ] Write the notes
- [ ] Tell the owner
${F3}`,
  },
  {
    id: 'chart-1',
    category: 'chart',
    title: 'Bar chart with units',
    note: 'The readable text is under 4 · Degraded below, and in the chart’s ⋯ menu. Try form=line or form=scatter, or rename a column to see a validation problem.',
    source: `${F3}chart version=1 form=bar x=month y=oslo,bergen x_label="Month" y_label="Rainfall" y_unit=mm title="Rainfall, Jan-Apr"
month,oslo,bergen
Jan,49,190
Feb,36,152
Mar,47,170
Apr,41,114
${F3}`,
  },
  {
    id: 'chart-2',
    category: 'chart',
    title: 'Line chart with a gap',
    note: 'An empty cell is a missing value; the line breaks there rather than inventing a point.',
    source: `${F3}chart version=1 form=line x=week y=p50,p99 x_label="Week" x_unit=wk y_label="Request latency" y_unit=ms
week,p50,p99
1,120,410
2,118,
3,131,395
4,125,388
5,119,402
${F3}`,
  },
  {
    id: 'chart-stack-1',
    category: 'chart',
    title: 'Stacked horizontal bars out of 100%',
    note: 'stack=true draws the series end to end in one bar per row and labels their sum; max=100 fixes the axis and leaves the rest of each bar empty. A row above max is an error, never clipped. Try orient=vertical, or drop stack=true for grouped bars.',
    source: `${F3}chart version=1 form=bar stack=true orient=horizontal max=100 x=candidate y=first_count,second_count x_label="Candidate" y_label="Share of vote" y_unit=% title="First and second count share"
candidate,first_count,second_count
Disanayaka,42.31,13.58
Premadasa,32.76,11.35
${F3}`,
  },
  {
    id: 'chart-stack-2',
    category: 'chart',
    title: 'Stacked vertical bars',
    note: 'Without max the value axis rounds up past the tallest stack, as it does for every bar chart. Negative values cannot be stacked.',
    source: `${F3}chart version=1 form=bar stack=true x=quarter y=new,returning x_label="Quarter" y_label="Customers" title="Customers by quarter — illustrative example data"
quarter,new,returning
Q1,120,340
Q2,95,380
Q3,140,365
Q4,110,410
${F3}`,
  },
  {
    id: 'chart-pie-1',
    category: 'chart',
    title: 'Pie chart: commit distribution by author',
    note: 'Draws proportional slices with percentages, swatches and keyboard accessibility. Slices map from categories and values.',
    source: `${F3}chart version=1 form=pie x=author y=commits x_label="Author" y_label="Commits" y_unit=commits title="Commits by author — illustrative example data"
author,commits
jarvis,5
agent-memory builder,4
Mentis Dev,3
bhill78,3
Brian (GitHub),8
ernie,1
${F3}`,
  },
  {
    id: 'chart-venn-1',
    category: 'chart',
    title: 'Venn diagram: code overlap between PR branches',
    note: 'Draws overlapping sets with region labels and item counts. Supports 2-set and 3-set overlap structures.',
    source: `${F3}chart version=1 form=venn sets="feat/gap-harvest-slice-a,experiment/memory-vs-file" counts=exclusive x=branch_set y=files x_label="Branch set" y_label="Files modified" y_unit=files title="Branch file overlaps — illustrative example data"
branch_set,files
feat/gap-harvest-slice-a,14
experiment/memory-vs-file,18
feat/gap-harvest-slice-a&experiment/memory-vs-file,6
${F3}`,
  },
  {
    id: 'pad-1',
    category: 'pad',
    title: 'Notes pad with a declared scope',
    note: 'Type in it; the Markdown does not change. The declared scope is shown and labelled unresolved.',
    source: `${F3}pad version=1 title="Meeting notes" source=conversation
Decisions:
-

Open questions:
-
${F3}`,
  },
  {
    id: 'timer-1',
    category: 'timer',
    title: 'Time box: 25 minutes, then a 5 minute break',
    note: 'Start it, and the ring counts the box down, then the break. In a posted Turn with name= each person\'s runs are kept by Mentis; here, unposted, it is a stopwatch in this tab.',
    source: `${F3}timer version=1 name=focus title="Deep work" box=25m break=5m
${F3}`,
  },
  {
    id: 'timer-2',
    category: 'timer',
    title: 'A plain stopwatch',
    note: 'No box=: it counts up until it is stopped. After two hours of a kept run it asks "Still going?".',
    source: `${F3}timer version=1 name=support title="Support call"
${F3}`,
  },
  {
    id: 'panel-1',
    category: 'composition',
    title: 'Composite: weekly ops review (chart + checklist + pad, one send-back)',
    note:
      'A panel is only a container: the author writes the blocks they already know inside one longer ```` fence. Each part keeps its own state; Send back on the panel gathers all of them. Try arrange=side-by-side.',
    demands: [
      'The outer fence must be longer (````) than the inner ones (```). That is standard Markdown, but a weak model may not know it; a same-length outer fence closes early and the panel is reported unclosed.',
    ],
    source: `${F4}panel version=1 title="Weekly ops review" arrange=stack
Latency this week, then what we agreed to do about it.

${F3}chart version=1 form=line x=day y=p99 x_label="Day" y_label="p99 latency" y_unit=ms
day,p99
Mon,410
Tue,395
Wed,520
Thu,640
Fri,430
${F3}

${F3}checklist version=1 title="Actions"
- [ ] Find what changed on Wednesday
- [ ] Add an alert at 500 ms
- [ ] Re-run the load test
${F3}

${F3}pad version=1 title="Notes"
${F3}
${F4}`,
  },
]
