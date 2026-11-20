---
name: add-dataset
description: Add or change a dataset in the semantic layer (semantic/datasets.yaml) so dashboards can use new data, fields or metrics. Use when a dashboard needs a field, grain or metric that no dataset provides.
---

# Add or change a dataset

The semantic layer (`semantic/datasets.yaml`) is the only place that knows about physical tables
and SQL. Dashboards reference datasets and fields by name. Changing a dataset's SQL or connector
never requires a dashboard change, as long as the field names stay the same.

## Workflow

1. **Check what exists:** `rbc-bi datasets`. Prefer extending an existing dataset (a new field)
   over creating a near-duplicate. Create a new dataset when the **grain** differs (e.g. one row
   per customer vs one row per order line, or monthly targets vs order lines).
2. **Explore the physical data** read-only:
   ```bash
   rbc-bi query "show all tables"
   rbc-bi query "describe retail.orders"
   rbc-bi query "select * from retail.orders limit 5"
   ```
3. **Write the SQL** for one row per grain. Compute row-level derived columns in SQL. For ratios,
   also return the numerator and denominator columns.
4. **Declare every column** under `fields` with `type`, `label` and a `description` that says what
   it means (agents and people read these). Types: `date | string | integer | number | currency |
   percent`.
   - Set `agg: mean` for measures that shouldn't be summed (rates, durations, scores).
   - Mark ratios with `ratio: [numerator, denominator]` so they re-aggregate as
     sum(numerator)/sum(denominator) at any grain. Example: `profit_margin: {type: percent,
     label: Profit margin, ratio: [profit, sales]}`.
   - Quote descriptions that contain commas or colons inside `{ ... }` flow mappings.
5. **Set** `grain` (fields that make a row unique), `connector` (from `config/connectors.yaml`,
   usually `warehouse`), `refresh` (`realtime | hourly | daily`, the cache TTL) and, if rows are
   dated, `time_field` (the date field the dashboard time bar acts on: date range, Month/Quarter/
   Year, MoM/QoQ/YoY).
6. **Validate:** `rbc-bi validate`. It runs your SQL with `LIMIT 0` and fails if the query errors
   or if returned columns and declared fields differ.
7. **Sanity-check values:** `rbc-bi query "select count(*), sum(<measure>) from (<your sql>)"`.

## Template

```yaml
  customer_summary:
    description: >
      One row per customer with lifetime orders, sales and profit. Use for customer
      segmentation and top-customer analysis.
    connector: warehouse
    refresh: daily
    grain: [customer_id]
    time_field: first_order_date
    sql: |
      select customer_id, any_value(customer_name) as customer_name, any_value(segment) as segment,
             any_value(region) as region, min(order_date) as first_order_date,
             count(distinct order_id) as orders, sum(sales) as sales, sum(profit) as profit,
             sum(profit) / nullif(sum(sales), 0) as profit_margin
      from retail.orders
      group by customer_id
    fields:
      customer_id:      { type: string,   label: Customer ID }
      customer_name:    { type: string,   label: Customer }
      segment:          { type: string,   label: Segment }
      region:           { type: string,   label: Region }
      first_order_date: { type: date,     label: First order date }
      orders:           { type: integer,  label: Orders, description: Distinct orders placed. }
      sales:            { type: currency, label: Sales }
      profit:           { type: currency, label: Profit }
      profit_margin:    { type: percent,  label: Profit margin, ratio: [profit, sales] }
```

## Moving a dataset to another platform (e.g. Databricks)
Change `connector` (add the connection to `config/connectors.yaml` with secrets as `${ENV_VARS}`)
and rewrite `sql` in that platform's dialect, keeping the **same output column names**. Run
`rbc-bi validate`. No dashboard changes.

## Rules
- Never put credentials in YAML. Use `${ENV_VAR}` in `config/connectors.yaml`.
- Read-only SQL only.
- Don't rename or remove a field that dashboards use without updating them: `rbc-bi validate`
  will list every broken reference.
