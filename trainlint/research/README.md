# research-lint — a research-process lint (sibling of Trainlint's action doorman)

Trainlint's hooks are an **action-time** doorman (don't make a single wrong move).
This is the **research-process** layer: it makes the *shape of your search* visible so
you don't over-commit to one direction or read a paper before you can understand it.
**It only hints — it never restricts the agent's exploration.** Coach-only, read-only.

## Two lints (both periodic, both pure hints)

- **governor (inward)** — reconstructs the *frontier tree* of directions you've explored
  and shows each branch's shape: status / spend / recent marginal gains / walls hit /
  unexplored candidate moves / missing trunk-checks. It **never says "abandon"** —
  research is non-monotonic (a plateau can precede a breakthrough). It corrects the
  biases of unsupervised search (sunk-cost over-DFS, novelty over-BFS) with *information*,
  not control.
- **surfacer (outward)** — takes the **walls** in the tree (problems you actually hit) and
  surfaces knowledge-library entries that address them: "this may be readable now."
  Trigger = a wall, **not recency** (reading earlier = cargo-cult).

A **wall is a dual signal**: the governor's stop-shape AND the surfacer's unlock key.

## Why it survives compaction/deletion (the durability model)

The tree is a **derived view, rebuilt every run** — never a maintained file:

- **skeleton** ← re-derived each run from durable repo traces (run dir names + metrics).
  `derive_structured()` globs `runs_glob`, parses directions via `direction_regex`.
- **annotations** ← `log.<name>.jsonl`, a durable **append-only** log of the JUDGMENTS
  traces can't prove (why-abandoned / hypothesis / verdict / wall). It lives in git.

The session transcript is **ephemeral** (Claude compacts/rotates it), so `harvest.py`
pulls those judgments OUT of a session INTO the durable log **before** they're lost —
wire it to Claude Code's `PreCompact` and `SessionEnd` hooks, and/or run it periodically.
Append-only → never rots (rot comes from needing to *sync*; appends never sync).
If the harvest never ran and the log is lost → degrade to **skeleton only**, LLM
re-infers judgments (lossy, not broken). Fail-soft, like the rest of Trainlint.

## Run

```bash
python3 lint.py [project]                 # rebuild tree, print the two lints' hints
python3 harvest.py <transcript.jsonl> [project]   # PreCompact/SessionEnd/periodic
python3 test_research.py                  # 9/9
```
Schedule `lint.py` (cron / a Claude Code routine) for the periodic hint; wire
`harvest.py` to `PreCompact`/`SessionEnd` so judgments are captured before loss.

## Files (general mechanism vs per-project facts)

```
tree.py governor.py surfacer.py harvest.py lint.py   ← mechanism (general, fixed)
facts.<name>.json       thresholds / runs_glob / direction_regex / trunk_checks / candidate_moves
knowledge.<name>.jsonl  papers/refs indexed by the PROBLEM they solve (+ match keywords)
log.<name>.jsonl        durable append-only annotations (git-committed)
```

**To port to another project:** write `facts.<name>.json` + `knowledge.<name>.jsonl`
+ start an empty `log.<name>.jsonl`; the mechanism is unchanged. (Same general/facts
split as the Trainlint rules.) Active project = `HARNESS_PROJECT` env / `.active-project`
/ default `mimo`.
