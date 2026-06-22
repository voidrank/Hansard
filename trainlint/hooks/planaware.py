#!/usr/bin/env python3
"""Stage 2.4 — PLAN-AWARE routing.

Locate a live action on the project PLAN (research/plan.<name>.jsonl) and route by
the touched DECISION's status + governing principle — instead of matching keywords
in whatever file happens to be open.

This is the fix for why the plugin underperformed in real use (audit of session
8cc76f15): it keyword-escalated throwaway probe scripts and delivered the right
principle ~285 lines too late. With the plan, an action is mapped to the decision
it actually touches:

  open      -> ESCALATE: you're acting on an UNDECIDED fork; here's its principle — decide it
  decided   -> COACH:    decided but unverified; make the code match the choice, then verify
  verified  -> COACH:    settled; deliver the known-right answer + principle, just-in-time

Each (session, decision) is surfaced AT MOST ONCE — no more identical repeated
escalations (the audit's "3 byte-identical, ignored" failure). A verified decision
also lets the router DOWNGRADE a keyword-only escalation (the region is settled) —
see router.decide. Fail-OPEN: any error -> no items, never raises.
"""
import sys
from pathlib import Path

RESEARCH = Path(__file__).resolve().parent.parent / "research"
STATE = RESEARCH / ".state"
sys.path.insert(0, str(RESEARCH))
try:
    import plan as planlib  # noqa: E402
except Exception:  # pragma: no cover
    planlib = None


def _haystack(data):
    """Fuller than classifier's: include the DIFF content too, so content-level
    decisions (e.g. a MelSpectrogram edit) are located, not just path/command."""
    if data.get("hook_event_name", "") == "UserPromptSubmit":
        return data.get("prompt", "") or ""
    ti = data.get("tool_input", {}) or {}
    parts = [str(data.get("tool_name", ""))]
    for k in ("command", "file_path", "path"):
        if ti.get(k):
            parts.append(str(ti[k]))
    if isinstance(ti.get("files"), list):
        parts.extend(str(x) for x in ti["files"])
    for k in ("new_string", "content"):
        if ti.get(k):
            parts.append(str(ti[k]))
    if isinstance(ti.get("edits"), list):
        for e in ti["edits"]:
            if isinstance(e, dict) and e.get("new_string"):
                parts.append(str(e["new_string"]))
    return " ".join(parts)


def _seen_then_mark(session, did):
    """True if this (session, decision) was already surfaced. Marks it on first
    sight. No session id (e.g. in tests) -> never deduped. Best-effort, fail-open."""
    if not session:
        return False
    m = STATE / f"plan-seen.{session}.{did}"
    try:
        if m.exists():
            return True
        STATE.mkdir(exist_ok=True)
        m.write_text("1", encoding="utf-8")
    except Exception:
        pass
    return False


def assess(data):
    """Return (items, located). items are severity-tagged + carry plan_decision;
    located is every plan decision this action touches (used for the downgrade)."""
    if planlib is None:
        return [], []
    try:
        located = planlib.locate(_haystack(data))
    except Exception:
        return [], []
    if not located:
        return [], []
    session = data.get("session_id", "")
    items = []
    for d in located:
        did = d.get("id", "?")
        if _seen_then_mark(session, did):
            continue  # surfaced once already this session — never repeat
        status = d.get("status", "open")
        princ = d.get("principle", "")
        decision = d.get("decision", "")
        why = (" " + d["why"]) if d.get("why") else ""
        choice = d.get("choice", "")
        if status == "open":
            items.append({"level": "escalate", "plan_decision": did,
                          "message": (f"⟦plan:{did}⟧ this acts on an UNDECIDED decision — "
                                      f"«{decision}» (principle: {princ}).{why} "
                                      f"Decide/confirm it before proceeding.")})
        elif status == "decided":
            items.append({"level": "coach", "plan_decision": did,
                          "message": (f"⟦plan:{did}⟧ decided but UNVERIFIED — «{decision}» → "
                                      f"{choice} (principle: {princ}).{why} "
                                      f"Make the code match the choice, then verify it holds.")})
        else:  # verified
            items.append({"level": "coach", "plan_decision": did,
                          "message": (f"⟦plan:{did}⟧ settled decision — «{decision}» → {choice} "
                                      f"(principle: {princ}).{why} Don't drift from it.")})
    return items, located
