---
description: Pull a Trainlint quiz question to test your understanding of a transferable training principle
argument-hint: "[id or topic]"
---
Read the quiz bank at `${CLAUDE_PLUGIN_ROOT}/quiz.jsonl` (JSONL; each line has fields
id/principle/level/context/q/naive/why/a).

Pick ONE question: if `$ARGUMENTS` is given, the one whose id or principle matches it;
otherwise a random L2 or L3 question.

Show me ONLY its `context` and `q`. Withhold `naive`, `why`, and `a`. Wait for my answer.
Then reveal the `why` and the `a`, and tell me whether my answer matched the underlying
`principle` (the transferable law) — not just the domain detail.
