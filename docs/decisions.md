# Decisions and assumptions (prototype)

`architecture.md` is the target design. This prototype deliberately narrows it to prove one idea:
**an agent can build consistent, correct dashboards by writing YAML against a good framework.**

| # | Decision | Why |
|---|---|---|
| 1 | **Data: Kaggle "Superstore"** (`vivek468/superstore-dataset-final`) loaded into local DuckDB instead of synthetic tech-finance data. Dates shifted +8 years (2022-2025). A synthetic `retail.sales_targets` table (prior-year sales x 1.10 per region/month) gives an "actual vs target" story like spend vs budget. | Real, familiar data; demo doesn't depend on internal data. |
| 2 | **Deferred: access control, org-cutover, subscriptions, usage analytics, a11y CI.** `access:` is accepted in specs (for governance) but not enforced. | Out of scope for this demo by request. Designs in architecture §5-7 still apply. |
| 3 | **`refresh` lives on the dataset**, not the dashboard. | Caching is per dataset query; two dashboards sharing a dataset shouldn't disagree on freshness. |
| 4 | **Ratio measures** (`ratio: [num, den]`) in the semantic layer replace the spec's `agg: weighted`. | The definition belongs with the data; it re-aggregates correctly at any grain. |
| 5 | **`split_by` instead of `color`** for series. | `color` is a banned style key; the name also says what it does. |
| 6 | **Chart heights are fixed per component kind** (KPI row, chart row, table sized by page size) on a 12-column grid; 1-4 components per row, equal width. | Consistency over flexibility; nothing for an agent to get wrong. |
| 7 | **`rbc-bi` CLI** instead of relying on `make`. A Makefile wraps it. | Windows laptops often have no `make`. |
| 8 | **Dev server supervisor** in `rbc-bi run` restarts the app on any spec/framework change. | Werkzeug's reloader doesn't start under Vizro 1.0; agents need write-YAML-then-refresh. |
| 9 | **Invalid specs don't crash the app.** They're skipped and listed on a "Spec errors" page. `rbc-bi validate` is the strict gate (CI). | A typo in one dashboard shouldn't take down the others. |
| 10 | **`dash-mantine-components` pinned to 2.x.** | DMC 3 requires React 19; Dash 4.5 defaults to React 18, which gives a blank page. |
| 11 | **Theme = Vizro light + token patch.** Tokens in `framework/theme/tokens.yaml` generate CSS variables and patch the Plotly templates. Brand values are placeholders. | Swap one file to re-brand. No logos committed. |
| 12 | **Chart colours**: a categorical order pre-validated for colour-vision-deficiency separation; brand blue for single-series charts. | Accessibility by default; re-validate if the brand palette replaces it. |
| 13 | **Exports** use Vizro's `export_data` action: they download the *filtered rows behind the table* (for a grouped table, the detail rows), CSV or Excel. | Analysts usually want the underlying data; reuses Vizro. |
| 14 | **Time bar via Vizro Parameters, not Filters.** Datasets declare `time_field`; specs add `time:`. Components receive `date_range`, `time_grain`, `compare` and slice time themselves. | A date Filter removes the rows a KPI needs for "vs previous period / last year". Parameters keep the full history available to each component. |
| 15 | **Filters live in a top bar** (a body Container's controls), not Vizro's left panel. | What business users expect; the left rail stays navigation only. |
| 16 | **Light and dark are both first-class.** Tokens define both; CSS keys off Vizro's `data-bs-theme`; charts are transparent and get grid/ring colours from per-mode Plotly templates. | The original theme hard-coded light surfaces, which broke the dark toggle. |
| 17 | **Date picker spans whole months**, and default ranges are relative to the latest data, not today. | Month-aligned windows make "previous period" a clean MoM/QoQ/YoY; demo data that ends in the past still opens on real numbers. |
