---
description: Visualize the research search tree (directions x status) with knowledge-readiness edges
argument-hint: "[project]"
---
Run the Trainlint research visualizer and show me the result. This is READ-ONLY — do not edit anything.

1. Run: `python3 "${CLAUDE_PLUGIN_ROOT}/research/viz.py" $ARGUMENTS`
   (the optional argument is the project name; default is the active project).
2. Show me the ASCII tree it prints (status legend: `·` open, `▸` deepening, `⚠` stalled, `✗` abandoned, `★` won) and the knowledge-readiness section.
3. If it prints a line `PNG: <path>`, send that PNG file to me.
