---
name: debug-dashboard
description: Explain why a dashboard shows a number ("why does X show Y?") by tracing component -> dataset -> SQL -> data, and propose a fix as a diff. Use for questions about wrong, surprising or changed numbers.
---

# Debug a dashboard number

Everything is text in Git, so you can trace any number end to end. Explain with numbers, not
guesses. Only run read-only queries.

## Trace

1. **Find the component.** Open `dashboards/<id>.yaml` and find the KPI/chart/table by its title.
   Note `dataset`, `measure`/`y`, `agg`, `x`, `split_by`, `time_grain`, `top_n`, and the page
   `filters` (the user may have filters applied; ask which, or assume defaults = everything).
2. **Find the dataset.** `rbc-bi datasets <dataset>` shows field types, default aggregation and
   ratio definitions. `rbc-bi sql <dataset>` prints the SQL.
3. **Reproduce the number** by wrapping the dataset SQL:
   ```bash
   rbc-bi query "with d as (<dataset sql>) select region, sum(sales) from d where order_date >= '2025-01-01' group by 1"
   ```
   Apply the same aggregation the framework uses:
   - default agg: `sum` for numbers/currency, `mean` for percent, or the field's `agg`
   - ratio fields: `sum(numerator) / sum(denominator)` (never the mean of row ratios)
   - `count_distinct` = `count(distinct ...)`
   - date axes are bucketed to `time_grain` (default month) using the period start
4. **Drill into the raw table** if the dataset looks right but the value is surprising
   (duplicates, nulls, late data, negative values, a join fan-out).
5. **Explain** in 3-6 sentences with the actual numbers: what the component computes, from which
   rows, and why it comes out as Y.
6. **Propose a fix as a diff** if something is wrong: a spec change (wrong field/agg/filter) or a
   semantic-layer change (SQL bug, wrong type, missing `ratio`). Run `rbc-bi validate` on it.

## Common causes
- A percent averaged instead of re-computed: the field needs `ratio: [num, den]`.
- Summing a non-additive measure (durations, rates): set `agg: mean` on the field.
- Count of rows vs count of orders: use `agg: count_distinct` on the id.
- A filter on a field that only some datasets have: it only affects components whose dataset
  has that field.
- `top_n` hiding categories, or `time_grain` merging periods.
