---
description: Generate the research tree — a demo-ready HTML report (TLDR · timeline · decision spine · search tree)
argument-hint: "[project]"
---
Run the Trainlint research visualizer and show me the result. This is READ-ONLY — do not edit anything.

1. Run: `python3 "${CLAUDE_PLUGIN_ROOT}/research/viz.py" $ARGUMENTS`
   (the optional argument is the project name; default is the active project. Pass `index` —
   `python3 .../viz.py index` — to regenerate EVERY project and build a linked overview page.)
2. Show me the compact ASCII summary it prints — goal · main thread · the verified/decided/open scoreboard · the latest timeline beats · any wall→paper "ready to read" hints.
3. Send me the file it points to: a line `HTML: <path>` (one project) or `INDEX: <path>` (the overview). Both are self-contained and open in any browser — top-down TLDR, a dated timeline, the phase-ordered decision spine beside the search tree, with knowledge-readiness edges. (The index links to the per-project pages by relative path, so they're clickable when opened from `research/viz/`.)
