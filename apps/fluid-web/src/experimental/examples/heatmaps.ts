import { F3, type Example } from './model'

export const heatmapExamples: Example[] = [
  {
    id: 'calendar-heatmap-1', category: 'calendar-heatmap', title: 'Declared daily activity',
    note: 'Synthetic example data, not retrieved activity. Weeks are columns, Sunday first. Zero is declared on October 1; omitted dates are unknown. Scroll for more weeks, focus or tap a cell for its date and value.',
    source: `${F3}calendar-heatmap version=1 title="Activity (example data)" start=2026-09-01 end=2026-12-31
date,value
2026-09-01,1
2026-09-02,3
2026-09-03,6
2026-09-05,9
2026-09-06,7
2026-09-07,1
2026-09-08,8
2026-09-09,4
2026-09-10,0
2026-09-12,3
2026-09-14,6
2026-09-15,2
2026-09-16,9
2026-09-17,5
2026-09-19,8
2026-09-20,4
2026-09-21,0
2026-09-22,7
2026-09-23,3
2026-09-24,10
2026-09-26,2
2026-09-28,5
2026-09-29,1
2026-09-30,8
2026-10-01,0
2026-10-02,2
2026-10-03,8
2026-10-05,10
2026-10-06,6
2026-10-07,2
2026-10-08,9
2026-10-10,1
2026-10-12,4
2026-10-13,0
2026-10-14,7
2026-10-15,3
2026-10-17,6
2026-10-19,9
2026-10-20,5
2026-10-21,1
2026-10-22,8
2026-10-24,0
2026-10-26,3
2026-10-27,10
2026-10-28,6
2026-10-29,2
2026-10-31,5
2026-11-01,5
2026-11-02,8
2026-11-03,4
2026-11-04,0
2026-11-05,7
2026-11-07,10
2026-11-09,2
2026-11-10,9
2026-11-11,5
2026-11-12,1
2026-11-14,4
2026-11-16,7
2026-11-17,3
2026-11-18,10
2026-11-19,6
2026-11-21,9
2026-11-23,1
2026-11-24,8
2026-11-25,4
2026-11-26,0
2026-11-28,3
2026-11-30,6
2026-12-01,1
2026-12-02,9
2026-12-03,5
2026-12-05,8
2026-12-07,0
2026-12-08,7
2026-12-09,3
2026-12-10,10
2026-12-12,2
2026-12-14,5
2026-12-15,1
2026-12-16,8
2026-12-17,4
2026-12-19,7
2026-12-21,10
2026-12-22,6
2026-12-23,2
2026-12-24,9
2026-12-26,1
2026-12-28,4
2026-12-29,0
2026-12-30,7
2026-12-31,3
${F3}`,
  },
  {
    id: 'matrix-heatmap-1', category: 'matrix-heatmap', title: 'Hour × weekday activity',
    note: 'Synthetic counts. Sequential scale; blanks are missing, while 0 is measured zero. Wide matrices scroll horizontally on mobile.',
    source: `${F3}matrix-heatmap version=1 title="Hourly activity (example data)"
row,08:00,09:00,10:00,11:00,12:00,13:00
Mon,0,2,8,4,,3
Tue,1,4,6,8,2,5
Wed,2,3,7,4,1,2
Thu,0,4,8,6,2,1
Fri,1,2,4,3,0,
${F3}`,
  },
  {
    id: 'matrix-heatmap-2', category: 'matrix-heatmap', title: 'Declared diverging matrix',
    note: 'Synthetic correlations, not inferred from observations. The explicitly declared midpoint is 0. labels=no hides numeric text only; every cell still has an accessible value, native tooltip and focus/tap caption.',
    source: `${F3}matrix-heatmap version=1 title="Correlations (example data)" scale=diverging midpoint=0 labels=no
row,Alpha,Beta,Gamma
Alpha,1,-0.8,0
Beta,-0.8,1,0.4
Gamma,0,0.4,1
${F3}`,
  },
  {
    id: 'status-grid-1', category: 'status-grid', title: 'Declared test matrix',
    note: 'Synthetic statuses. Each cell supplies a label and a category from the explicit key. This grid is static; use the existing table for sorting, filtering or editable values.',
    source: `${F3}status-grid version=1 title="Platform checks (example data)"
{
  "rows": ["Desktop", "Mobile"],
  "columns": ["Light theme", "Dark theme", "Keyboard", "Offline"],
  "states": [{"label":"Pass", "tone":"good"}, {"label":"Pending", "tone":"warn"}, {"label":"Blocked", "tone":"bad"}],
  "cells": [
    [{"label":"Layout", "state":"Pass"}, {"label":"Contrast", "state":"Pass"}, {"label":"Focus", "state":"Pending"}, {"label":"Cache", "state":"Blocked"}],
    [{"label":"Scroll", "state":"Pass"}, {"label":"Labels", "state":"Pending"}, {"label":"Focus", "state":"Pending"}, {"label":"Cache", "state":"Blocked"}]
  ]
}
${F3}`,
  },
  {
    id: 'heatmap-errors', category: 'matrix-heatmap', title: 'Malformed matrix shows inline errors',
    note: 'Bad numeric data, duplicate row and an invalid midpoint are diagnosed by the existing block frame.',
    source: `${F3}matrix-heatmap version=1 scale=diverging midpoint=NaN
row,A,B
same,1,nope
same,2,3
${F3}`,
  },
]
