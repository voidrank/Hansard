---
description: Scaffold Trainlint for a new project (template facts/knowledge/log/goal + set it active)
argument-hint: "<project-name>"
---
Run: `python3 "${CLAUDE_PLUGIN_ROOT}/research/new_project.py" $ARGUMENTS`

Then show me the files it created and walk me through the `TODO` fields I need to fill:
- `project.<name>.json` — action-rule facts (bad-storage regex, locked configs, preprocessing
  traps, reference impl, examples).
- `research/facts.<name>.json` — research facts (`runs_glob`, `direction_regex`, trunk-checks,
  candidate moves).
- `research/knowledge.<name>.jsonl` — papers indexed by the problem they solve.
- `research/goal.<name>.txt` — one line: what this project is building.

Use `project.mimo.json` and `research/facts.mimo.json` as worked examples. After I fill them,
the flow (context / hint / viz-on-change / quiz kickoff) runs against this project.
