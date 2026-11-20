# BI-as-Code prototype

**AI agents build dashboards at design time by writing YAML. A thin framework on open-source
[Vizro](https://github.com/mckinsey/vizro) makes every dashboard look and behave the same. At run
time there is no AI, just deterministic code.**

```
 "Make me a dashboard showing X"                     ┌──────────────────────────────┐
            │                                        │ dashboards/sales-overview.yaml│  ← the agent writes this
            ▼                                        └──────────────┬───────────────┘
   IDE agent + skills ──► rbc-bi validate (Pydantic, agent-friendly errors)
                                                                    ▼
   semantic/datasets.yaml (datasets → SQL, typed fields)  ──►  framework (rbc_bi on Vizro)
                                                                    ▼
                                    one themed app: catalog, filters, KPIs, charts, tables, exports
```

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip setuptools
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\activate
rbc-bi data        # builds data/warehouse.duckdb from data/raw/Sample - Superstore.csv
rbc-bi validate
rbc-bi run         # http://localhost:8050
```

macOS/Linux: same with `.venv/bin/...`, or `make setup data validate run`.
Snapshots (PNG/PDF) need Playwright: `pip install playwright` then `python -m playwright install chromium`.

The raw CSV is committed so the repo works offline. To re-download it from Kaggle:
`curl -L -o data/raw/superstore.zip https://www.kaggle.com/api/v1/datasets/download/vivek468/superstore-dataset-final`

## What's in the box

| | |
|---|---|
| **5 example dashboards** | `dashboards/*.yaml`: sales overview, regional sales vs target, product profitability, shipping operations, customer insights |
| **Semantic layer** | `semantic/datasets.yaml`: `orders` (order lines) and `sales_vs_target` (month x region). Ratio metrics re-aggregate correctly. |
| **Validator** | Pydantic + cross-reference checks. Typos get "Did you mean ...?", style keys and SQL are rejected. |
| **Top filter bar** | Every page: date range, **View by Month / Quarter / Year**, **Compare to previous period (MoM/QoQ) or last year (YoY)**, plus dropdown filters. Spec: one `time:` block. |
| **Components** | KPI (with optional reference/target), line, bar, stacked bar, area, scatter, donut, table (grouped, top-N, CSV/Excel export) |
| **Theme** | Light and dark modes from `framework/theme/tokens.yaml` (one file re-skins everything). KPI cards with change pills and sparklines. |
| **Agent skills** | `.claude/skills/`: `build-dashboard`, `add-dataset`, `debug-dashboard` (also referenced from `.github/copilot-instructions.md`) |
| **CLI** | `rbc-bi validate / run / datasets / sql / query / snapshot / schema / data` |
| **Live reload** | `rbc-bi run` restarts when any YAML or framework file changes; refresh the browser |
| **Snapshot mode** | `?snapshot=1` on any page, or `rbc-bi snapshot <id>` for PNG + PDF |
| **Connectors** | DuckDB (working) + Databricks/Snowflake/Postgres/SQL Server stubs behind one interface |

## Demo script (~10 min)

1. **The catalog (1 min).** Open http://localhost:8050. Every card is a YAML file. Click through
   two dashboards: same look, same behaviour, zero styling in the specs.
2. **Show a spec (1 min).** Open `dashboards/sales-overview.yaml` next to the page. ~60 lines,
   no Python, no SQL, no colours.
3. **Build by prompt (3 min).** With `rbc-bi run` running, ask Claude Code / Copilot:
   > *Build a dashboard for the West region sales manager: sales vs target by month, top 10 states
   > by profit, and ship mode mix. Filter by date and category. Domain: sales.*

   The agent uses the build-dashboard skill: reads `rbc-bi datasets`, writes
   `dashboards/<id>.yaml`, runs `rbc-bi validate`, fixes errors. Refresh the browser and the new page
   is in the nav under *Sales*. (`customer-insights.yaml` was built the same way from a one-line ask.)
4. **Guardrails (1 min).** Add `color: red` to a chart, or misspell a field (`proft`), and run
   `rbc-bi validate`:
   `dashboards/x.yaml: layout[1].row[0].chart.y 'proft' is not a field of dataset 'orders'. Did you mean 'profit'?`
   The app keeps running and lists broken specs on a *Spec errors* page.
5. **Debug by prompt (2 min).** "Why does Profit margin show 12.5% on Sales overview?" The
   debug-dashboard skill traces spec → dataset → SQL and reproduces the number with a query.
6. **One file re-themes everything (1 min).** Change `brand.primary` in
   `framework/theme/tokens.yaml`. Every dashboard updates.
7. **Extend the semantic layer (1 min).** "Add a customer-level dataset with lifetime sales" uses the
   add-dataset skill; the validator runs the new SQL and checks every declared field.

## Tests

```bash
python -m pytest -q
```
38 tests: one per validation rule, aggregation maths, connector behaviour, and an end-to-end
test that compiles every dashboard and renders every component against the real data.

See `docs/decisions.md` for what this prototype simplifies relative to `docs/architecture.md`.
