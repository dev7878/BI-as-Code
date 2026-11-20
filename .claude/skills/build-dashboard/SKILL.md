---
name: build-dashboard
description: Create or change a dashboard from a plain-English ask by writing a YAML spec in dashboards/. Use whenever someone asks for a new dashboard, page, chart, KPI or table, or to change an existing one.
---

# Build a dashboard

You are a dashboard engineer on a BI-as-Code platform. A dashboard is **one YAML file** in
`dashboards/<id>.yaml`. The framework turns it into a page with the house theme, filters, exports
and navigation. You never write Python, CSS or SQL for a dashboard.

## Workflow (follow in order)

1. **Understand the ask.** Who is it for, what question does it answer, what time range, which
   breakdowns. If the ask is one line, make sensible choices and state them; don't stall.
2. **Explore the semantic layer first.**
   ```bash
   rbc-bi datasets            # every dataset, field, type, default aggregation, description
   rbc-bi datasets orders     # one dataset
   ```
   Pick fields by their descriptions. Measures are numeric (currency, percent, integer, number);
   dimensions are string or date. If what you need isn't there, use the `add-dataset` skill
   first, then come back. Never reference physical tables.
3. **Optionally sanity-check the numbers** with a read-only query:
   `rbc-bi query "select region, sum(sales) from retail.orders group by 1"`.
4. **Write the spec** in `dashboards/<id>.yaml` (id = filename, kebab-case). Copy the shape of the
   closest example below. Start the file with the schema comment for IDE autocomplete.
5. **Validate and fix until clean:**
   ```bash
   rbc-bi validate dashboards/<id>.yaml
   ```
   Every error names the YAML path and usually the fix ("Did you mean 'profit'?"). Apply it and
   re-run. Don't work around a rule (e.g. by adding style keys); the rules are the point.
6. **See it.** If `rbc-bi run` is already running, it reloads automatically: open
   `http://localhost:8050/<id>`. Otherwise start it. For a review image:
   `rbc-bi snapshot <id> --no-pdf` writes `snapshots/<id>.png`; look at it.
7. **Review against the ask** (checklist below) and report: the file you wrote, the choices you
   made, and the URL.

## Spec reference (everything a spec can say)

```yaml
# yaml-language-server: $schema=../framework/spec/dashboard.schema.json
id: my-dashboard                 # kebab-case, must equal the filename
title: My dashboard
description: Who it is for and the question it answers.
owner: team@example.com
domain: sales                    # one of config/platform.yaml domains: sales | products | operations | customers
tags: [optional, list]

filters:                         # page-level; applies to every component whose dataset has the field
  - { field: order_date, type: date_range }     # date fields
  - { field: region,     type: multi_select }   # string fields: multi_select | single_select | checklist
  - { field: discount,   type: range }          # numeric fields

layout:                          # rows top to bottom; 1-4 components per row, equal width
  - row:
      - kpi: { dataset: orders, measure: sales, title: Sales }
      - kpi: { dataset: orders, measure: order_id, agg: count_distinct, title: Orders }
      - kpi: { dataset: sales_vs_target, measure: sales, reference: sales_target, title: Sales vs target }
  - row:
      - chart:
          type: line             # line | bar | stacked_bar | area | scatter | donut
          dataset: orders
          x: order_date          # dimension (scatter: a measure; donut: the slice names)
          time_grain: month      # date x only: day | week | month | quarter | year (default month)
          y: sales               # measure, or a list of measures (without split_by)
          split_by: category     # optional dimension -> one series per value, with legend
          title: Monthly sales by category        # required
          description: One sentence on how to read it.   # optional, shown as a tooltip
  - row:
      - table:
          dataset: orders
          columns: [category, sub_category, sales, profit, profit_margin]
          group_by: [category, sub_category]     # optional: aggregate to this grain
          sort_by: sales
          sort: desc
          top_n: 25
          exportable: true       # adds Download CSV / Excel of the filtered data
          page_size: 10
```

Other chart keys: `agg` (override aggregation: sum | mean | median | min | max | count |
count_distinct | ratio), `sort: asc|desc` and `top_n` (bar, stacked_bar, donut),
`horizontal: true` (bars; good for long category names), `detail` (scatter: one point per value).
KPI keys: `agg`, `format` (currency | percent | number | integer; normally omit, it follows the
field type), `reference` (measure to compare against), `lower_is_better`.

### Rules the validator enforces
- Datasets and fields must exist in `semantic/datasets.yaml`.
- `y`, `measure` and `reference` must be measures, unless `agg` is `count` / `count_distinct`.
- `split_by`, `group_by`, `detail` must be dimensions. Don't combine `split_by` with several `y`.
- `stacked_bar` needs `split_by` (or 2+ `y`). `sort`/`top_n` aren't for line/area.
- Filter type must fit the field type. A filter field must belong to a dataset used on the page.
- **No styling** (`color`, `font`, `style`, `css`, `width`, ...). Use `split_by` to colour by a field.
- **No SQL, connectors or table names** anywhere in a dashboard.

### Design guidance (the framework handles the look; you handle the story)
- Lead with 3-4 KPIs that answer the headline question. Then trend, then breakdowns, then detail.
- Trend over time -> `line` (or `area` for part-to-whole over time). Compare categories -> `bar`
  (sorted, `horizontal` if labels are long). Composition -> `stacked_bar`; `donut` only for 2-5
  slices. Relationship between two measures -> `scatter` with `detail`.
- Ratios (margin, attainment) are `ratio` fields: they aggregate correctly at any grain. Never
  average a percentage yourself.
- Keep `split_by` to fields with few values (<= 8). Use `top_n` for long tails.
- Use `exportable: true` on tables analysts will want in Excel.
- Titles say what the chart shows ("Profit by region"), not how ("Bar chart").

## Examples (real, valid specs in this repo; read them before writing a new one)

| Example | Shows |
|---|---|
| `dashboards/sales-overview.yaml` | KPI row with ratio + count_distinct, line with split_by, sorted bar, donut, grouped exportable table |
| `dashboards/regional-targets.yaml` | KPI with `reference` (actual vs target), multi-measure line, quarterly stacked bar |
| `dashboards/product-profitability.yaml` | horizontal sorted bar, scatter with `detail`, top-N product table |
| `dashboards/shipping-operations.yaml` | mean-aggregated measure, count_distinct stacked bar, area over time |

## Review checklist before you report done
- [ ] `rbc-bi validate` passes with no errors.
- [ ] Every number the ask mentions is on the page, at the right grain and time range.
- [ ] Filters cover the obvious slices (date + the main dimensions).
- [ ] Titles are plain English; each chart answers one question.
- [ ] You looked at the rendered page or snapshot, not just the YAML.
