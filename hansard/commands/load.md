---
description: Inhale an EXISTING project once — read its skills, CLAUDE.md/AGENTS.md guidance, and auto-memory, classify every item into skill / lint / knowledge, and write them into the project's stores so every new session starts from them (and keeps them growing)
argument-hint: "[project] [--home DIR]"
---
`/hansard:load` is the **one-time inhale**: a project that lived before Hansard already carries
context — `.claude/skills/`, `CLAUDE.md` / `AGENTS.md`, Claude Code's auto-memory
(`~/.claude/projects/<slug>/memory/*.md`), cursor/copilot rules. Load reads all of it ONCE,
sorts every item into the store that can actually act on it, and stamps a manifest so it never
re-ingests what's already in. From then on the SessionStart briefing injects the digest, a
prompt that matches a loaded skill gets a just-in-time pointer, and every agent keeps the
stores growing as it works. Load is deliberate (a command, invoked once); the re-surfacing is
ambient (hooks) — same split as the rest of Hansard.

## 0. Resolve the project (register if needed)

Active project = the session lock (`/hansard:use`) or cwd-home inference. If `$ARGUMENTS` names a
project, bind it first (`python3 "${CLAUDE_PLUGIN_ROOT}/research/use.py" <name> [--home DIR]`).
If the project isn't registered at all, run the thin registrar from the project's directory —
`python3 "${CLAUDE_PLUGIN_ROOT}/research/new_project.py" <name>` — then continue here. (Load does
NOT replace `/hansard:plan`: load inhales what's already written down; plan establishes context
and decisions. Do load first on an existing project — the inhaled material makes the plan cheaper.)

## 1. Load-once check

Run `python3 "${CLAUDE_PLUGIN_ROOT}/research/load.py" status <name>`.
- **Never loaded** → full inhale (step 2, all sources).
- **Loaded, nothing changed** → say so ("inhaled on <ts>, all sources unchanged") and STOP.
  Do not re-read, do not rewrite — load once means once.
- **Loaded, N sources new/changed** → refresh ONLY those N files (status lists them); everything
  below applies to just that subset. Never re-ingest an unchanged source.

## 2. Discover and READ the sources

`python3 "${CLAUDE_PLUGIN_ROOT}/research/load.py" discover <name>` prints every candidate as one
JSON line: `{path, kind, bytes, state}`. READ each file with state `new`/`changed` (a big one —
stream/grep it or hand it to a subagent; never skip it silently — if you drop a source, SAY which
and why).

## 3. Classify every item — route it to the store that can ACT on it

One source file usually yields entries in SEVERAL buckets (a memory file mixes procedure, fact,
and warning in one page). Split it; don't force a whole file into one bucket. The test for each
item is **who can act on it**:

- **skill** — a PROCEDURE you'd follow again (a launch recipe, env setup, a pipeline invocation,
  "how to re-encode audio"). → append to `skills.<name>.jsonl`:
  `{"id","title","when","how","match":[task keywords],"source"}`. `how` is the distilled
  runnable steps (concrete commands), not prose about them. `match` is what a future prompt
  asking for this would contain (include Chinese keywords if the operator works in Chinese —
  the hint matcher is a plain substring check).
- **lint** — a GUARDABLE mistake: "never X", "always Y before Z", a feedback scar ("bs=1 is
  5-10x slower — enable batching BEFORE launching"). The doorman can act on it at the moment of
  the action. → per DESIGN.md §6/§8 discipline: the project-specific STRING (path, regex, value)
  goes into `project.<name>.json` as a fact the existing general rules reference
  (`bad_storage_re`, `preproc_trap_re`, `codec_contract`, `not_re`, …); ONLY if no existing
  general principle covers it, propose a new `{{fact}}`-parameterized rule and add a
  `tests/cases.jsonl` case + run `python3 tests/run.py`. Never hard-code a project noun into a
  rule body.
- **knowledge** — a FACT or FINDING (an architecture note, a post-mortem's root cause, a
  baseline number, a paper/ref). Useful when a future wall matches it. → append to
  `knowledge.<name>.jsonl`: `{"id","title","problem","concepts":[],"prereqs":[],
  "match":[wall keywords],"read":false,"source"}` — index it by the PROBLEM it solves, and give
  `match` the words the wall would contain, not the words the title contains.
- **glossary** — a term definition → `glossary.<name>.jsonl` `{term, plain, why}`.
- **plan material** — a memory that records project STATUS or a standing DECISION ("pivoted to
  single-turn Q→A", "fresh training only, never resume") is not a skill/fact: note it and, at the
  end, tell the operator these belong in the plan — `/hansard:plan` (a rejected option becomes a
  decision's `not_this`/`not_re`). Don't silently drop them into knowledge where nothing acts
  on them.

Rules that hold for every entry: **distill, don't paste** (the store entry is the usable core;
`source` keeps the pointer back to the full text); **write incrementally** as you classify — one
source file classified, its entries written, then the next — never accumulate everything for one
big write at the end; keep ids kebab-case; skip an item that is pure conversation-local trivia
(say you skipped it).

**Human-facing prose is drafted by kimi, not you.** The operator's standing rule: everything a
human will READ (skill `title`/`when`/`how` wording, knowledge `title`/`problem`, glossary
`plain`/`why`) is written by the kimi CLI; you (claude/codex) do the WORK — reading sources,
judging buckets, picking `match` keywords and ids, verifying the draft against the source.
Batch it: one kimi call per source file with the classified raw material —
`kimi --print -y --output-format stream-json -p "<drafting instructions>\n\n<material>"`
(the same recipe `viz._llm('kimi', …)` uses) — then fix anything kimi got structurally wrong
before writing the entries. If kimi is unavailable, draft inline and SAY the fallback happened.

## 4. Stamp the manifest, report

When the (sub)set is ingested, run `python3 "${CLAUDE_PLUGIN_ROOT}/research/load.py" mark <name>`
— this is what makes the load once-only. Then report like a person: how many sources read, how
many entries per bucket (skill / lint-fact / knowledge / glossary), which items you routed to the
plan and which you skipped, and one line on what happens next: "every new session now starts
with this digest; a prompt matching a skill gets pointed at it; keep appending as you learn."

## Afterwards — the stores keep growing (every agent, every session)

The SessionStart briefing carries the keep-producing contract, so agents that never saw this
command still follow it: learned a new reusable procedure → append to `skills.<name>.jsonl`;
established a new fact/finding → `knowledge.<name>.jsonl`; hit a new guardable mistake → a fact
in `project.<name>.json` (+ a rule per DESIGN.md §8 if no principle covers it). Load is the
inhale; the session loop is the breathing.
