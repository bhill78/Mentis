Chart options contract
======================

Pie accepts exactly one series of present, finite, non-negative values and
requires a positive total. Zero categories remain in its legend. This renderer
supports pie, not donut; no `hole=` or `form=donut` option is advertised.

Venn is schematic, not to scale. Declare exactly two or three distinct set names
with `sets="A,B,C"`. Names cannot contain commas or `&`. The x column is an
explicit region membership key: `A`, `B`, `C`, `A&B`, `A&C`, `B&C`, `A&B&C`.
Membership order is immaterial; duplicate membership rows are errors.
An undeclared region is blank. Names are shown in an outside, wrapping legend;
each declared count is shown in its region and repeated in an accessible list.
Counts default to exclusive per-region values. `counts=total` declares inclusive
counts and requires member totals for each intersection, which cannot exceed
any of those totals. Negative and missing counts are errors in both modes.
The readable form and Send back include sets, regions and counts mode.

Bar charts take three optional attributes, all ignored with a warning on other
forms. A bar chart that declares none of them is drawn exactly as before.

    chart version=1 form=bar stack=true orient=horizontal max=100 x=candidate y=first_count,second_count x_label="Candidate" y_label="Share of vote" y_unit=%

- `stack=true|false` (default false): the `y` series are drawn end to end in
  one bar per row, in declared order, coloured and listed in the legend per
  series. The sum of a row's present segments is labelled at the end of the
  fill, written to the most decimals any of its cells uses. Summing is the only
  arithmetic; shares and percentages are never computed. Empty cells add
  nothing. A negative value in a stacked bar is a contract error.
- `orient=vertical|horizontal` (default vertical): horizontal puts the `x`
  categories down the side and the values along the bottom. It works with and
  without `stack`.
- `max=N` (a positive number): fixes the value axis at 0..N and draws the rest
  of each bar, up to N, as an empty track. A stacked total above N, or without
  `stack` any value above N or below 0, is a contract error shown with the
  other validation problems. Bars are never clipped.

Mirrored or back-to-back layouts are not supported. Two charts in a `panel`
with `arrange=side-by-side` come closest. The readable form states the layout
and, for stacked bars, every row's total.

Timeline dependencies exist only when `parents=<column>` is declared. Also
declare `id=<column>` as the one unique key for matching prerequisites. Parent
cells hold these ids, separated by semicolons or CSV-quoted commas. Dates and
labels are never alternative keys. Empty/duplicate ids, unresolved ids and
self-parenting are contract errors. Links point from prerequisite to dependent
event. Readable text and Send back retain dependency ids. Without `parents=`,
a parent/parents column remains an ordinary extra column.

Git uses declaration order, declared groups and parent-to-child edges. Ungrouped
commits remain neutral; no missing history is invented. Cycles are errors.
Gallery datasets for these four options are illustrative example data.

Verification safety
-------------------

`tests/chart_options_guard.py` provides a module-scoped, reversible monkeypatch
fixture. The chart tests import it; regression runs explicitly load it as a
pytest plugin. It suppresses sweeps/reconcile, stubs passive and observed
capacity for all three runtime adapters, blocks subprocesses other than the
Playwright driver, and writes its spawn/denial log to `CHART_EVIDENCE` when set.
No root conftest side effects or tracked screenshot writes are needed.
