# Copilot instructions

This repo is a BI-as-Code platform. Read `CLAUDE.md` at the repo root for the rules and commands;
they apply to every agent. Task playbooks live in `.claude/skills/*/SKILL.md`:

- New or changed dashboard: `.claude/skills/build-dashboard/SKILL.md`
- New data / field / metric: `.claude/skills/add-dataset/SKILL.md`
- "Why does X show Y?": `.claude/skills/debug-dashboard/SKILL.md`

Always finish with `rbc-bi validate` passing.
