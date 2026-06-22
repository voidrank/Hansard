---
description: Build the project PLAN via a deterministic workflow (gathers full context, decomposes into decisions, GUARANTEES the plan is written), then reviews it with you and quizzes you
argument-hint: "[review | status | <free-text context>]"
---
The PLAN is the project's floor plan: an ordered list of DECISIONS (one JSONL line each in
`${CLAUDE_PLUGIN_ROOT}/research/plan.<active-project>.jsonl`), every one tagged with the
transferable PRINCIPLE that governs it. Active project = `${CLAUDE_PLUGIN_ROOT}/.active-project`.

**Why a workflow, not a to-do list here:** drafting a real plan spans many turns of code-reading,
and a long markdown to-do list gets dropped the moment the conversation diverges — that's how a
plan got "started" but never written, so the quiz never came. A workflow is a little program that
runs each step itself, so **writing the plan is guaranteed**, not left to the model to remember.

## `review` / `status`
Just read the existing plan and show it grouped by phase with status icons (✓ verified · decided
○ open), calling out `open` and `decided`-but-unverified ones. Change nothing. (`python3
research/plan.py` prints this.) Do NOT run the workflow for these.

## Otherwise — draft/update the plan

1. Get the active project name: read `${CLAUDE_PLUGIN_ROOT}/.active-project`.
2. **Launch the deterministic workflow** (one reliable tool call): call the **Workflow** tool with
   `scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/plan.workflow.js"` and
   `args: { "project": "<active-name>", "pluginRoot": "${CLAUDE_PLUGIN_ROOT}" }`. If `$ARGUMENTS`
   is free text (e.g. "focus on the turn-based audio discussion"), add it as `args.hint`.
   The Workflow tool is **non-blocking** — it returns a task id immediately, NOT the result; the
   workflow runs in the background (Gather → Decompose → **Write plan.<name>.jsonl**) and its result
   `{ exposition, decisionList, planFile }` arrives later via a `<task-notification>`.
3. **BLOCK — make it feel synchronous.** After launching, reply with ONE short line ("Building the
   plan — reading the code, decomposing, writing it. Hold on, I'll walk you through it the moment
   it's ready.") and then **do nothing else**: do not start unrelated work, do not ask unrelated
   questions, do not yield to other tasks. Just wait for the completion notification. If I message
   you before it finishes, briefly remind me the plan is still building and keep waiting.
   - **Fallback only if the Workflow tool is unavailable:** do it inline instead — read goal/facts/
     code, write the COMPLETE start-to-finish context (plain language, every term defined, file:line
     grounded, UNKNOWNs marked), decompose, and WRITE `plan.<name>.jsonl` BEFORE anything else.
4. **When the workflow completes** (its `<task-notification>` arrives), immediately continue —
   retrieve its result, present the `exposition` + decision list for my corrections (apply edits to
   the plan file), then **quiz me**: walk each decision as `/trainlint:quiz` does — pose its
   governing principle as a question, grade against the principle, **answer SHARP** (concrete fact
   first, principle second, zero hedging), drill misses with fresh scars, `progress.mark` the ones
   I get. Soft — "skip" exits.

The workflow guarantees the plan is written (step 2–3); the review + quiz (step 4) run right when it
finishes, so it feels like one continuous flow. And the SessionStart understanding-gate backstops the
quiz if anything still diverges — so the plan→quiz chain no longer depends on the model's memory.
