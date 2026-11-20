# Architecture

Source of truth for how the platform fits together. Section numbers are referenced elsewhere.

## 1. Layers (top to bottom)

```
┌───────────────────────────────────────────────┐  BUILD TIME (AI allowed)
│ 1. IDE agent + skills                         │  Copilot / Claude Code, MCP servers,
│                                               │  ontology docs, .claude/skills/*
└──────────────────────┬────────────────────────┘
                       ▼
┌───────────────────────────────────────────────┐
│ 2. Dashboard spec (YAML in Git)               │  dashboards/*.yaml
│                                               │  validated by Pydantic in CI
└──────────────────────┬────────────────────────┘
═══════════════════════╪═════════════════════════  RUN TIME (no AI, deterministic)
                       ▼
┌───────────────────────────────────────────────┐
│ 3. RBC framework on Vizro                     │  compiler, theme, components,
│                                               │  modules (access, export, snapshot,
│                                               │  subscriptions, cache, usage, a11y)
└──────────────────────┬────────────────────────┘
                       ▼
┌───────────────────────────────────────────────┐
│ 4. Semantic layer                             │  semantic/datasets.yaml, semantic/org.yaml
│                                               │  dataset resolver, org-cutover resolver
└──────────────────────┬────────────────────────┘
                       ▼
┌───────────────────────────────────────────────┐
│ 5. Data platforms (via connectors)            │  prototype: DuckDB
│                                               │  later: Databricks, Snowflake, PG, SQL Server
└───────────────────────────────────────────────┘
```

**Flow at run time:** request → SSO identity → access check → compiled Vizro page → datasets
resolved via the semantic layer (with org cutover applied) → connector query → cache → render.

## 2. Dashboard spec (`dashboards/<id>.yaml`)

One file per dashboard. It has two parts: **metadata** (RBC governance) and **layout** (what to
show). The compiler maps layout to Vizro models. Keep the spec small and opinionated: fewer
options mean more consistent agent output.

```yaml
id: tech-spend-overview              # kebab-case, unique, matches filename
title: Tech spend overview
description: Monthly tech spend vs budget by org, for managers and senior managers.
owner: dev.team@rbc.com              # owning team distribution list
domain: tech_finance                 # tech_finance | talent | operations
access: public                       # public | {groups: [AD_GROUP_A, ...]}
org_cutover: month_start             # immediate | month_start | onboarded (see §5)
refresh: daily                       # informs cache TTL (see §7.3)
tags: [finance, monthly]

filters:                             # page-level controls, applied to every component
  - field: fiscal_month
    type: date_range
  - field: svp_name                  # an org field, so the cutover policy is applied
    type: multi_select

layout:                              # rows of components; the framework sizes and spaces them
  - row:
      - kpi: { dataset: spend_monthly, measure: actual_spend, agg: sum, format: currency, title: Actual spend }
      - kpi: { dataset: spend_monthly, measure: budget, agg: sum, format: currency, title: Budget }
      - kpi: { dataset: spend_monthly, measure: variance_pct, agg: weighted, format: percent, title: Variance }
  - row:
      - chart:
          type: line                 # line | bar | stacked_bar | area | scatter | donut (small approved set)
          dataset: spend_monthly
          x: fiscal_month
          y: [actual_spend, budget]
          title: Spend vs budget trend
      - chart:
          type: bar
          dataset: spend_monthly
          x: svp_name
          y: actual_spend
          sort: desc
          title: Spend by SVP
  - row:
      - table:
          dataset: spend_monthly
          columns: [fiscal_month, svp_name, vp_name, cost_centre, actual_spend, budget, variance_pct]
          exportable: true           # adds CSV/Excel export (see §7.2)
```

### Validation rules (Pydantic + cross-reference checks)

- Every `dataset` exists in `semantic/datasets.yaml`.
- Every field (`x`, `y`, `measure`, `columns`, filter `field`) exists in that dataset's schema.
- Every `measure` is numeric. `format` matches the field type.
- `access.groups` is non-empty when access isn't `public`.
- `id` is unique and matches the filename.
- **No style keys anywhere** (`color`, `font`, `css`, `style`, ...): reject with a clear message.
- **No physical table names or SQL in a dashboard spec.**
- Error messages name the file, the YAML path and a fix, e.g.
  `dashboards/tech-spend-overview.yaml: layout[1].row[0].chart.y[1] 'budgt' is not a field of dataset 'spend_monthly'. Did you mean 'budget'?`

Provide a CLI: `python -m rbc_bi.spec validate [paths...]` (used by `make validate` and CI).
Also export a JSON Schema (`framework/spec/dashboard.schema.json`) so IDE YAML plugins and agents
get autocomplete and inline errors.

## 3. Compiler (`framework/compiler/`)

- Loads every valid spec and builds **one Vizro `Dashboard`**: each RBC dashboard becomes a
  Vizro `Page`, grouped in navigation by `domain`.
- Maps spec components to approved wrappers in `framework/components/`:
  - `kpi` → Vizro KPI card figure
  - `chart` → Plotly Express chart via `vizro.plotly.express`, with the RBC template applied
  - `table` → Vizro AG Grid table
  - `filters` → Vizro `Filter` controls
- Layout rows become a Vizro `Grid`/`Layout` with consistent spacing from the theme.
- Unknown component types fail at validation, never at render.

## 4. Semantic layer (`semantic/`)

Dashboards talk to **datasets**. The semantic layer maps datasets to SQL against a connector.

```yaml
# semantic/datasets.yaml
datasets:
  spend_monthly:
    description: Monthly actual and budgeted tech spend by cost centre.
    connector: warehouse            # name in connectors config
    grain: [fiscal_month, cost_centre]
    org_join: cost_centre           # the key that links rows to the org dimension (§5)
    sql: |
      select fiscal_month, cost_centre, actual_spend, budget,
             (actual_spend - budget) / nullif(budget, 0) as variance_pct
      from finance.spend_fact
    fields:
      fiscal_month:  { type: date,     label: Fiscal month }
      cost_centre:   { type: string,   label: Cost centre }
      actual_spend:  { type: currency, label: Actual spend }
      budget:        { type: currency, label: Budget }
      variance_pct:  { type: percent,  label: Variance % }
    # org fields (evp_name, svp_name, vp_name) are added automatically when org_join is set
```

- **Connector interface** (`framework/semantic/connectors/`): `query(sql, params) -> pandas.DataFrame`.
  Prototype: `DuckDBConnector`. Stubs with the same interface: `DatabricksConnector`
  (databricks-sql-connector), `PostgresConnector`, `SqlServerConnector`, `SnowflakeConnector`.
  Connector config comes from env vars, never from specs.
- **Dataset resolver** registers each dataset with Vizro's `data_manager` as a loader function so
  data loads at request time and goes through the cache.
- **Migration story:** moving `spend_monthly` from Postgres to Databricks means changing its
  `connector` and `sql` only. Every dashboard using it is untouched. A **reconciliation check**
  (`make reconcile DATASET=x`) compares row counts and measure totals between old and new.
- Later, field descriptions are synced from Unity Catalog or the metadata catalog service, plus the
  Confluence ontology docs. In the prototype they're hand-written YAML.

## 5. Org dimension and cutover policy (the "SVP moved" problem)

**Requirement:** when leadership changes, different stakeholders want the change to show at
different times: immediately, from the 1st of the next month, or only once the new leader has
onboarded. Today this is hardcoded per dashboard.

**Design:** store the change once, with all three dates, and let each dashboard choose its policy.

```yaml
# semantic/org.yaml
org:
  connector: warehouse
  table: org.org_assignment          # effective-dated (SCD Type 2 style)
  key: cost_centre
  levels: [evp_name, svp_name, vp_name]
```

`org.org_assignment` columns:

| column | meaning |
|---|---|
| cost_centre | key joined to facts |
| evp_name, svp_name, vp_name | leaders for this cost centre |
| announced_date | when the change was announced |
| effective_date | official effective date |
| onboarded_date | when the new leader finished onboarding (nullable until known) |
| valid_to | when the next change for this cost centre starts (null = current) |

**Cutover policies** (the dashboard's `org_cutover`) choose which date counts as "this assignment
starts":

| policy | assignment applies from |
|---|---|
| `immediate` | `announced_date` |
| `month_start` | first day of the month after `effective_date` (or `effective_date` itself if it is the 1st) |
| `onboarded` | `onboarded_date`; if null, the previous assignment stays in force |

The **org-cutover resolver** builds the current org view for a policy as of "today" (and supports
an `as_of` date for testing) and joins it to any dataset with `org_join`. Implement it as SQL
generated per policy, cached per (policy, date). A dashboard never contains a leader's name.

**Demo requirement:** the synthetic data has one SVP change where the three dates differ, so three
copies of the same dashboard with different policies show different SVP names on the same day.

## 6. Access control (role-level, not row-level)

The current model works, so mirror it:

- **Public tier:** anyone in the public AD group can see every `access: public` dashboard.
- **Private dashboards:** `access: {groups: [...]}`. The user needs at least one listed group.
- No row-level security is needed now. Keep a hook in the dataset resolver for it later.

**Identity:** in production, SSO via OIDC (Entra ID / RBC IdP) at the OCP ingress or in the Flask
server, with AD group claims. **Prototype:** a mock identity provider: a dev-only user switcher
that sets the user and groups from `config/mock_users.yaml`.

**Enforcement:** server-side, before the page renders (Flask `before_request` on page routes) *and*
in navigation (hide pages the user can't open). Exports and snapshots go through the same check.
Return a friendly "request access to <group>" page on denial.

## 7. Framework modules (Tableau parity)

Every dashboard gets these with no spec changes, unless it opts out where noted.

### 7.1 Theme and components (`framework/theme/`, `framework/components/`)
- RBC design tokens (colours, type scale, spacing) in one file. The prototype uses an RBC-like
  blue/gold palette as **placeholders**, so don't copy RBC's logo or brand assets.
- Plotly template applied to every figure, plus a Vizro theme override (CSS).
- A small, approved set of chart types. Adding a type means adding a wrapper with a test.

### 7.2 Exports
- Tables with `exportable: true` get **CSV and Excel** download buttons (Vizro's export action, or
  a custom one) that export the **filtered** data.
- Dashboard-level **PDF** export uses the snapshot renderer (§7.4).
- Exports respect access (§6) and log to usage (§7.6). Configurable row cap (default 1M), with a
  clear message when it's hit.

### 7.3 Caching
- Cache dataset query results keyed by (dataset, cutover policy, filter params), with a TTL from
  the spec's `refresh` (`hourly` 1h, `daily` 24h, `realtime` none).
- Prototype: Flask-Caching `SimpleCache` or a filesystem cache. Production: Redis on OCP.
  Same interface for both.

### 7.4 Snapshot mode (for the deck team)
- `?snapshot=1` on any dashboard URL renders a clean, fixed 1920×1080 view: no navigation, no
  controls panel, active filters shown as text chips, a title bar with "Data as of <timestamp>".
- `make snapshot DASH=<id> [FILTERS=...]` renders PNG and PDF headlessly with Playwright.
- Per-component "copy as image" is a stretch goal.

### 7.5 Email subscriptions
- `subscriptions/*.yaml`: dashboard id, filters, format (pdf/png), schedule (cron), recipients
  (must have access).
- A runner (`python -m rbc_bi.modules.subscriptions run`) renders via §7.4 and sends email.
  Production: an OCP CronJob plus the RBC SMTP relay. **Prototype:** write the email as an `.eml`
  file to `outbox/` instead of sending.

### 7.6 Usage analytics
- Log page views, filter changes, exports and snapshots: timestamp, user, dashboard, event,
  details. Write to a `usage_events` table through the connector (prototype: DuckDB).
- Ship a built-in **"Platform usage"** dashboard written as a normal spec. We eat our own cooking.

### 7.7 Accessibility (WCAG 2.1 AA target)
- Palette contrast checked in a unit test (text and key chart marks ≥ 4.5:1 or 3:1 as applicable).
- Keyboard navigation for filters and tables. Every chart has a title and an accessible
  description. Never use colour alone to encode meaning.
- `make a11y` runs axe-core (via Playwright) on every page and fails on serious violations.

## 8. Agent skills (`.claude/skills/`)

Skills turn the agent into a reliable dashboard engineer. Each is a folder with a `SKILL.md`.

- **build-dashboard:** from a user ask, explore datasets (semantic layer first; add a dataset only
  if needed), draft the spec, run `make validate`, fix errors, run the app, take a snapshot and
  review it against the ask. Must include 2–3 full example specs.
- **debug-dashboard:** given "why does X show Y", trace component → dataset → SQL → org cutover,
  run read-only queries, explain with numbers, and propose a fix as a diff.
- **add-dataset:** add or modify a dataset in `semantic/datasets.yaml` with field types and
  descriptions, then validate.
- **port-superset** (prototype stretch) and **port-tableau** (later): map an exported Superset
  dashboard (YAML) or Tableau workbook (`.twb` XML) to a spec plus datasets. List anything that
  couldn't be mapped (for example LOD expressions) in a `PORTING_NOTES.md`.

Agent data access in production: read-only service principal, all queries audited. Never write
credentials into skills or specs.

## 9. Deployment (target, not prototype)

- Container image (Python 3.11, gunicorn running the Dash/Flask server) on **OpenShift (OCP)**.
- Config via env vars and OCP secrets. Redis for cache. CronJob for subscriptions.
- CI: lint, `make validate`, `make test`, `make a11y`, image build. CD to dev, UAT and prod via
  the existing RBC pipeline.

## 10. Explicit non-goals

- No drag-and-drop editor. No AI chat inside the app. No AI-generated narrative on dashboards.
- No row-level security (hook only).
- No custom per-dashboard CSS or Python callbacks in specs.
- Not replacing the enterprise semantic or catalog platform; we consume it later.
