# CLAUDE.md: BI-as-Code prototype

Dashboards here are **declarative YAML specs in Git**, rendered by a thin framework (`rbc_bi`, in
`framework/`) on top of open-source **Vizro**. AI agents write the YAML at design time; the
framework enforces one look, approved components and validation. At run time there is **no AI**.

Background: `docs/vision.md`, `docs/architecture.md` (target design), `docs/decisions.md` (what
this prototype does differently and why).

## How to do common tasks (use the skills)

| Ask | Skill |
|---|---|
| "Make a dashboard showing ..." / change a dashboard | `.claude/skills/build-dashboard` |
| A dashboard needs data, a field or a metric that doesn't exist | `.claude/skills/add-dataset` |
| "Why does X show Y?" | `.claude/skills/debug-dashboard` |

## Commands

Activate the venv first (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` elsewhere).

```bash
rbc-bi validate [files...]   # validate config, semantic layer (incl. SQL) and dashboards
rbc-bi run                   # http://localhost:8050, reloads on any YAML/framework change
rbc-bi datasets [name]       # list datasets, fields, types, aggregations, descriptions
rbc-bi sql <dataset>         # SQL behind a dataset
rbc-bi query "<sql>"         # read-only query against the local warehouse
rbc-bi snapshot <id>         # PNG + PDF of a dashboard in snapshots/
rbc-bi schema                # regenerate framework/spec/dashboard.schema.json
python -m pytest             # tests
```

## Non-negotiable rules

- **Declarative over imperative.** A dashboard is a YAML spec. Never hand-write Dash/Vizro Python
  for one dashboard. If a spec can't express something, extend the framework (spec model +
  compiler + component + test) so every dashboard gets it.
- **Dashboards never reference physical tables or SQL.** Only `semantic/datasets.yaml` does.
- **One look.** Styling lives in `framework/theme/` (`tokens.yaml` + `assets/rbc.css`). Specs
  can't set colours, fonts or CSS; the validator rejects it.
- **Validation first.** `rbc-bi validate` must pass. Error messages are written for you: read them
  and apply the suggested fix.
- **No AI at run time.** No LLM calls in the app.
- **Swappable backend.** All queries go through `framework/semantic/connectors.py`.

## Where things live

```
dashboards/          one YAML file per dashboard (the thing agents write)
semantic/            datasets.yaml: datasets -> SQL + typed, described fields
config/              platform.yaml (title, domains), connectors.yaml (named connections, env vars)
framework/           the rbc_bi package
  spec/              Pydantic models, validator (agent-friendly errors), JSON Schema
  compiler/          spec -> Vizro Dashboard (one page per spec, nav grouped by domain)
  components/        approved KPI / chart / table wrappers + semantic-aware aggregation
  theme/             tokens.yaml (brand), Plotly template patch, CSS
  semantic/          connectors (DuckDB + stubs), dataset resolver (Vizro data_manager)
  modules/           cache, snapshot
  app.py, cli.py
data/                build_warehouse.py (Kaggle Superstore -> DuckDB), raw/
tests/
```

## Extending the framework (when a spec can't express something)

1. Add the option to the Pydantic model in `framework/spec/models.py` (with a `description`).
2. Add cross-reference checks to `framework/spec/validator.py` with a helpful message.
3. Implement it in `framework/components/` and wire it in `framework/compiler/compiler.py`.
4. Add a test in `tests/`, run `rbc-bi schema`, update the build-dashboard skill's reference.

Vizro moves fast: check the installed version's API (`.venv/Lib/site-packages/vizro`) before
using it. Prefer public APIs: `vizro.models`, `vizro.figures`, `vizro.tables`, `vizro.actions`,
`vizro.managers.data_manager`.
