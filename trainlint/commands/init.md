---
description: Register a new project — a thin scaffolder that creates the empty substrate and sets it active (no TODO ceremony; /trainlint:plan fills the facts)
argument-hint: "<project-name>"
---
Run: `python3 "${CLAUDE_PLUGIN_ROOT}/research/new_project.py" $ARGUMENTS`

This is a THIN registrar: it creates the empty per-project files (`project.<name>.json`,
`research/facts.<name>.json`, `knowledge`/`log`/`plan` jsonl, `goal.<name>.txt`) and sets the
project active. It deliberately does NOT make you fill a pile of TODO fields.

The facts (the doorman's danger patterns; the research layer's `runs_glob`/`direction_regex`)
are filled by **`/trainlint:plan`**, while it establishes the project's full context — because
that step reads the actual code anyway, which is the only honest way to know them. Until then
the stubs are empty and the doorman simply stays silent on this project (no crash).

After running this, tell me to run **`/trainlint:plan`** next — that's where the project gets
understood, the facts get filled, the decisions get drafted, and the quiz begins.
