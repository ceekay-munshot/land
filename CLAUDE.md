# CLAUDE.md

## Dashboard tasks — mandatory skill

This repo uses the **dashboard-builder** skill (`.claude/skills/dashboard-builder/SKILL.md`) for ALL dashboard work.

Whenever a task involves creating, building, generating, modifying, or reviewing a dashboard — in any phrasing (dashboard, widgets, screener, heatmap, sector monitor, tracker, portfolio/watchlist view, document intelligence view, company comparison, etc.):

1. **Before writing any code**, read `.claude/skills/dashboard-builder/SKILL.md` in full and follow it for the task.
2. Apply its UI Standards (3-zone iframe shell, `WidgetCard`, design tokens, loading/empty/error states), Auth Standards (Munshot Dashboard SDK — never custom auth or custom postMessage), Dashboard Patterns (widget order: filters/context → KPIs → primary analysis → insights → detail → sources), and type-specific examples.
3. Use only datasources registered in the skill's Datasource Registry, via the documented `base_urls` and contracts.
4. Complete the skill's "Pre-Submission UI Checklist" before declaring the dashboard done.

`dashboard_skill.md` in the repo root is the distribution copy of this skill. If it is updated, sync its content into `.claude/skills/dashboard-builder/SKILL.md`, keeping the YAML frontmatter block at the top of the skill file intact.
