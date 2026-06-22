#!/usr/bin/env python3
"""trainlint router — the orchestrator.

Pipeline:  stage1 prefilter (drop?) -> stage3 deterministic checks
                                     -> stage2 classifier (model or regex)
           -> merge by severity -> render to a channel.

Channels (all delivered via JSON; the process ALWAYS exits 0):
  reject   -> permissionDecision="deny"  (blocks the tool, bounces it back)   [tool events only]
  escalate -> systemMessage (user sees "please check this") + additionalContext (agent)
  coach    -> additionalContext only (silent steer; user undisturbed)
  none     -> no output

SAFETY: this whole module is fail-OPEN. Any internal error -> exit 0, emit
nothing. Blocking is done with permissionDecision, NEVER with a non-zero exit —
so a bug here can never lock the session (the lesson from the path-move lockout).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prefilter      # noqa: E402
import checks         # noqa: E402
import classifier     # noqa: E402
import planaware      # noqa: E402
import quiz           # noqa: E402

_RANK = {"reject": 3, "escalate": 2, "coach": 1}


def _level(item):
    return item.get("level") or item.get("class") or "coach"


def decide(data):
    """Pure function: hook event dict -> output dict (or None for silent)."""
    if prefilter.classify_action(data) == "drop":
        return None

    items = checks.run(data) + classifier.classify(data)

    # plan-aware routing: locate this action on the project PLAN and route by the
    # touched decision's status + principle (open->escalate, decided/verified->coach),
    # surfaced once per session per decision. Then DOWNGRADE: if the action's decision
    # is settled (verified), a keyword-only (non-certain, non-plan) escalation is most
    # likely a false alarm — turn it into a coach so the human isn't interrupted. A
    # machine-certain (verifier-backed) item is never downgraded.
    plan_items, located = planaware.assess(data)
    items = items + plan_items
    if any(d.get("status") == "verified" for d in located):
        for it in items:
            if (_level(it) == "escalate" and not it.get("certain")
                    and not it.get("plan_decision")):
                it["level"] = "coach"
                it["message"] = "(plan: this decision is settled) " + it.get("message", "")

    # quiz-gate (opt-in, non-blocking): surface ONE relevant question to make the
    # operator prove they understand before acting. Escalate-class, never blocks.
    qz = quiz.ask(data, classifier.haystack(data))
    if qz:
        q = qz[0]
        ctx = ("[context: " + q["context"] + "] ") if q.get("context") else ""
        items = items + [{"level": "escalate",
                          "message": "🧠 Knowledge gate (answer before you continue) " + ctx + q["q"]
                          + " (don't answer: " + q.get("naive", "") + ")"}]

    if not items:
        return None

    event = data.get("hook_event_name", "UserPromptSubmit")
    is_tool = event in ("PreToolUse", "PostToolUse")

    rejects = [i for i in items if _level(i) == "reject"]
    escalates = [i for i in items if _level(i) == "escalate"]
    coaches = [i for i in items if _level(i) == "coach"]

    out = {"hookSpecificOutput": {"hookEventName": event}}

    # reject only blocks a TOOL action; a "reject" on a user prompt can't block the
    # user — downgrade it to an escalation so the user still hears the warning.
    if rejects and is_tool:
        out["hookSpecificOutput"]["permissionDecision"] = "deny"
        out["hookSpecificOutput"]["permissionDecisionReason"] = "\n".join(
            i["message"] for i in rejects)
        rest = [i["message"] for i in escalates + coaches]
        if rest:
            out["hookSpecificOutput"]["additionalContext"] = "\n\n".join(rest)
        return out

    surfaced = escalates + (rejects if not is_tool else [])
    if surfaced:
        out["systemMessage"] = "⚠️ Needs your check:\n" + "\n".join(
            "• " + i["message"] for i in surfaced)
        out["hookSpecificOutput"]["additionalContext"] = "\n\n".join(
            i["message"] for i in surfaced + coaches)
        return out

    if coaches:
        out["hookSpecificOutput"]["additionalContext"] = "\n\n".join(
            i["message"] for i in coaches)
        return out

    return None


def main():
    try:
        data = json.load(sys.stdin)
        out = decide(data)
    except Exception:
        sys.exit(0)  # FAIL OPEN — never block because of a harness bug
    if out:
        print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)      # ALWAYS 0; blocking is via permissionDecision, not exit code


if __name__ == "__main__":
    main()
