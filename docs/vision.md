# Vision: Agentic BI-as-Code at RBC

## One line

**AI agents build dashboards at design time; a framework enforces RBC standards; dashboards run
as plain, deterministic code.**

## The problem today

Our team is data engineers and AI engineers, not reporting analysts, yet a large share of our
time goes into Tableau and Power BI:

- **Tool friction.** Half the effort is working out *how* to do something in the BI tool, not
  *what* the dashboard should show.
- **Change amplification.** A small business change (an SVP moving roles, a renamed org) means
  hand-editing many dashboards, because org names and rules are hardcoded in each workbook.
- **Opaque debugging.** "Why does this dashboard show X?" means clicking through calculated
  fields, data sources and filters in a GUI. Nothing is diffable or reviewable.
- **Migration cost.** We're moving off Postgres and SQL Server, probably to Databricks. Every
  dashboard that points at a physical table has to be remapped by hand.
- **No vendor AI.** Vendor-integrated AI (Snowflake Cortex, Databricks Genie, Copilot in Power BI)
  is disabled at the enterprise level so our data isn't used to train vendor models. And no new
  BI vendor contracts will be approved.

## The idea

Treat dashboards like any other software:

1. A dashboard is a **YAML spec in Git**: reviewed in PRs, tested in CI, versioned and rolled back.
2. The engineer **prompts an IDE agent** (GitHub Copilot or Claude Code, already approved at RBC).
   The agent explores the data through approved MCP servers and ontology docs, then **writes the
   spec**.
3. A **framework** (the RBC layer on open-source Vizro) turns the spec into a dashboard. It
   enforces the RBC theme, approved components, access rules and exports, so every dashboard looks
   and behaves the same while still being tailored to its purpose.
4. **Debugging is a prompt.** "Why does the Q3 spend tile show $4.2M?" The agent reads the spec,
   follows the dataset to its SQL, runs read-only queries and explains the answer, or opens a PR
   with the fix.
5. **Migrations are agent tasks.** Skills port Tableau workbooks and Superset exports into specs.
   Platform migrations happen once, in the semantic layer, instead of once per dashboard.

### The analogy

Tableau is a hand-painted poster: every one is unique and every change is repainting.
This platform is a **printing press with RBC's typeface locked in**. The agent sets the type (the
YAML), the press guarantees the look, and reprinting after a change is free.

## Who uses it

| User | What they do | What they need |
|---|---|---|
| Managers and senior managers | Track tech finance (spend vs budget, forecasts, headcount) | Interactive filters, clear KPIs, emailed subscriptions |
| Analysts | Day-to-day analysis | Slicing, drill-downs, **Excel/CSV data dumps** |
| Deck team | Screenshots for SVP slide decks | **Snapshot mode**: clean, fixed-size, branded renders, PNG/PDF |
| Data and AI engineers (builders) | Build and maintain dashboards | Spec + agent + validator + fast local preview |

SVPs don't read AI-generated summaries. Narrative analysis is written by reporting stakeholders
in slide decks. **No AI-generated text is shown in dashboards.**

## Principles

1. **Declarative, not imperative.** Agents write config, not arbitrary code. That's what keeps
   output consistent and auditable.
2. **Semantic layer owns meaning.** Dashboards reference business datasets and metrics, never
   tables. Org rules, cutover timing and migrations are solved once there.
3. **AI at build time only.** Run time is deterministic. That's the core of the approval story.
4. **Thin layer on open source.** Don't build a renderer. Build RBC's standards on top of Vizro.
5. **Tableau parity is built in, not bolted on.** Subscriptions, exports, caching, usage analytics,
   accessibility and access control are framework modules every dashboard gets for free.
6. **Everything in Git.** Specs, semantic definitions, agent skills and theme.

## Why this can get enterprise architecture approval

- **No new vendor contract.** Vizro is Apache 2.0 open source, used like any Python library
  (pandas, Plotly). It goes through the standard open-source intake: licence scan, vulnerability
  scan, internal package mirror.
- **No vendor AI and no data leaving RBC.** The only AI is the IDE agent RBC already approved.
  The app makes zero LLM calls.
- **Hosted on RBC's OpenShift (OCP)** with SSO and the existing AD groups.
- **More auditable than today.** Every change is a reviewed PR with a diff.

## Phases

1. **Prototype (now):** prove the full loop on synthetic data, locally. See `prototype-plan.md`.
2. **Pilot:** 2–3 real dashboards on Databricks, deployed to OCP, with real AD groups.
3. **Framework v1:** all parity modules hardened, CI/CD, an onboarding guide.
4. **Agent skills at scale:** build, debug and port skills (Tableau `.twb`, Superset export).
5. **Migration:** remap the semantic layer from PG/SQL Server to Databricks; dashboards unchanged.

## Known risks

- **Support model:** no vendor support for open source. Mitigation: keep the RBC layer thin so the
  engine can be swapped.
- **Hidden Tableau features:** users will notice anything missing on day one. Mitigation: parity
  modules are in scope from the start.
- **Tableau porting:** calculated fields and LOD expressions don't map 1:1. Expect the agent to
  do about 70% and engineers to review the rest.
- **Ownership:** this is an internal product. Name an owner and an on-call rota before production.
