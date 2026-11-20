# Prototype plan

**Goal:** a working local demo that convinces the team the full loop works:
*prompt an agent → spec → validated → consistent dashboard → debug by prompt → org change handled by config.*

Runs on a laptop with no RBC infrastructure: DuckDB plus synthetic data, mock identity.

## Synthetic data (`data/generate.py`)

A tech finance domain, deterministic (fixed seed), 24 months up to the current month.

| table | contents |
|---|---|
| `org.org_assignment` | ~40 cost centres, 3 EVPs, 6–8 SVPs, ~15 VPs, with announced, effective and onboarded dates (§5) |
| `finance.spend_fact` | monthly actual spend and budget per cost centre, with seasonality and a few overruns |
| `finance.forecast_fact` | monthly forecast per cost centre for the remaining fiscal year |
| `talent.headcount_fact` | monthly headcount (FTE and contractors) per cost centre |
| `usage_events` | empty; filled by the app |

**Planted scenario (required):** an SVP change on one org, with `announced_date` = 10 days ago,
`effective_date` = 5 days ago and `onboarded_date` = 20 days from now. So today:
- `immediate` shows the **new** SVP
- `month_start` shows the **old** SVP (switches on the 1st of next month)
- `onboarded` shows the **old** SVP

Use clearly fictional names (no real RBC people).

## Milestones

### M1: Skeleton and data
- Repo layout per `CLAUDE.md`, Makefile, pyproject, pinned deps (`vizro`, `pydantic`, `duckdb`,
  `pandas`, `pyyaml`, `flask-caching`, `playwright`, `openpyxl`, `pytest`).
- `make data` builds `data/warehouse.duckdb`.
- DuckDB connector, plus the connector interface and stubs.

### M2: Spec, validator and compiler
- Pydantic models for dashboard, dataset and org specs. JSON Schema export.
- `make validate` with the rules in architecture §2 and agent-friendly error messages.
- Compiler: specs → one Vizro app, pages grouped by domain. KPI, chart, table and filters work.
- RBC theme applied everywhere.

### M3: Semantic layer and org cutover
- Dataset resolver registered with `data_manager`, automatic org-field join.
- Org-cutover resolver with all three policies, plus `as_of` for tests.
- Unit tests covering the planted scenario for each policy.

### M4: Example dashboards (all written as specs)
1. `tech-spend-overview`: KPIs, trend, by-SVP bar, detail table (`org_cutover: month_start`, public)
2. `forecast-vs-budget`: forecast accuracy by VP (`org_cutover: immediate`, public)
3. `headcount-by-org`: FTE vs contractors (`org_cutover: onboarded`, private: `AG_TALENT_VIEW`)
4. `platform-usage`: built on `usage_events` (private: `AG_BI_ADMIN`)

### M5: Parity modules
- Access: mock users (`config/mock_users.yaml`: a manager, an analyst, a deck-team user, an
  admin), a user switcher in dev mode, enforcement plus friendly denial page.
- Exports: CSV/Excel on tables, PDF via snapshot.
- Snapshot mode (`?snapshot=1`) and `make snapshot`.
- Cache with TTL. Usage logging.
- Subscriptions runner writing `.eml` files to `outbox/`.
- `make a11y` with axe-core.

### M6: Agent skills
- `.claude/skills/build-dashboard`, `debug-dashboard`, `add-dataset`, each with examples.
- Stretch: `port-superset` with one sample Superset export in `examples/superset/`.

## Acceptance criteria

- [ ] `make setup data validate test run` works from a clean clone.
- [ ] All four example dashboards render with the same look and no spec-level styling.
- [ ] A spec with a typo in a field name fails validation with a message naming the file, the
      path and a suggestion.
- [ ] A spec containing `color:` or raw SQL is rejected.
- [ ] On the same day, the three dashboards with different `org_cutover` policies show the
      expected SVP for the planted change.
- [ ] Changing an SVP means adding one row to `org.org_assignment`: no dashboard file changes.
- [ ] Repointing `spend_monthly` to a different table or connector requires no dashboard changes.
- [ ] Analyst user can export filtered table data to Excel. Deck-team user can produce a clean
      PNG/PDF snapshot.
- [ ] A user without `AG_TALENT_VIEW` can't see or open `headcount-by-org` (nav hidden, URL denied).
- [ ] Page views and exports appear in `platform-usage`.
- [ ] `make a11y` reports no serious violations.
- [ ] Using only the `build-dashboard` skill, an agent can create a new dashboard from a one-line
      ask that passes validation on its first or second try.

## Demo script (about 10 minutes, for the team)

1. **The problem (1 min):** show a Tableau change request, e.g. an SVP move across dashboards.
2. **Build by prompt (3 min):** in Claude Code: "Create a dashboard showing contractor spend
   trend by SVP for the last 12 months, public, month_start cutover." Show the spec it writes,
   `make validate`, then the page. Point out that it matches the others automatically.
3. **Debug by prompt (2 min):** "Why does Actual spend for SVP X show $Y in March?" The agent
   traces the spec to the dataset and SQL, runs a query and explains.
4. **Org change (2 min):** show the three cutover policies side by side on the planted SVP change.
   Add one row to the org table to show a new change landing with no dashboard edits.
5. **Parity (1 min):** Excel export as the analyst, snapshot as the deck team, access denial as a
   user without the group, the usage dashboard.
6. **Approval story (1 min):** open source (Apache 2.0), no vendor AI, no run-time AI, OCP-ready,
   everything in Git.

## Out of scope for the prototype

Real SSO, real data sources, OCP deployment, Redis, real email sending, Tableau porting.
