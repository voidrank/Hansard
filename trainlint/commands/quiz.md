---
description: Test your grasp of a transferable training principle — soft, but if you miss it, it drills you with more
argument-hint: "[id or topic]"
---
Read the quiz bank at `${CLAUDE_PLUGIN_ROOT}/quiz.jsonl` (JSONL; fields
id/principle/level/context/q/naive/why/a).

This is **SOFT** — never block the user; they can say "skip" at any point to end it.

1. Pick ONE question: the one whose id or `principle` matches `$ARGUMENTS` if given, else a
   random L2 or L3 question. Show me ONLY its `context` and `q`. Withhold `naive`/`why`/`a`.
   Wait for my answer.

2. When I answer, reveal the `why` and the `a`, and judge whether I grasped the underlying
   `principle` (the transferable law) — not just the domain detail.

3. If I got the principle → done.

4. **If I got it wrong or couldn't answer → don't let it go: GENERATE more questions that
   drill the SAME principle.** Produce 3 new questions — reuse other bank items that share
   that `principle`, and/or invent fresh ones in the same `context → q → ... → why → a`
   shape (same principle, a different concrete scar). Present them as a numbered menu and let
   me CHOOSE which to answer. Grade each against the principle, and keep offering more on
   that principle until I clearly demonstrate I've got it. Still soft — "skip" always ends it,
   and you never block my actual work.
