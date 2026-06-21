---
description: Run the research-lint — reconstruct the search tree and surface directionality + readiness hints
argument-hint: "[project]"
---
Run: `python3 "${CLAUDE_PLUGIN_ROOT}/research/lint.py" $ARGUMENTS`
(optional argument = project name; default = active project).

Present its search-shape report. This is a LINT, not a planner: only describe the current
shape (stalled / deepening / abandoned branches, unexplored moves, walls that now match a
paper). Never tell me to abandon a branch — the judgment is mine.
