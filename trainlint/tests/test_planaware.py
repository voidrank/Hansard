#!/usr/bin/env python3
"""Plan-aware doorman tests — the three behaviours the audit demanded.

Run against the worked-example plan.mimo.jsonl (active project = mimo). No
session_id in the events -> dedupe is off -> deterministic.
"""
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))
import planaware  # noqa: E402
import router     # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def _surfaced(out):
    """What the user actually sees (the escalate channel)."""
    return (out or {}).get("systemMessage", "")


def _ctx(out):
    return ((out or {}).get("hookSpecificOutput", {}) or {}).get("additionalContext", "")


# 1. Acting on an OPEN decision -> ESCALATE, with the decision + its principle.
# absolute paths OUTSIDE the plugin root, else prefilter treats them as self-edits and drops them
ev_open = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
           "tool_input": {"file_path": "/home/shiyil/mimo/deploy/stream.py",
                          "new_string": "use the bidirectional encoder for streaming"}}
items, located = planaware.assess(ev_open)
check(any(i.get("plan_decision") == "streaming-encoder" and i["level"] == "escalate"
          for i in items),
      "OPEN decision (streaming-encoder) -> escalate item with its id")
out = router.decide(ev_open)
check("streaming-encoder" in _surfaced(out) or "UNDECIDED" in _surfaced(out),
      "router surfaces the undecided-decision escalation to the user")

# 2. Acting on a VERIFIED decision via a throwaway probe -> the keyword 'forward-change'
#    escalation is DOWNGRADED (no false user interruption), and the right principle is
#    delivered as a coach note. This is the audit's central false-alarm case.
ev_tf = {"hook_event_name": "PreToolUse", "tool_name": "Write",
         "tool_input": {"file_path": "/home/shiyil/mimo/tf_top1.py",
                        "content": "teacher forcing top-1; uses a sampler and top_p over logits"}}
items, located = planaware.assess(ev_tf)
check(any(d.get("id") == "eval-protocol" and d.get("status") == "verified" for d in located),
      "probe script locates onto the VERIFIED eval-protocol decision")
out = router.decide(ev_tf)
check("forward / mask / sampling" not in _surfaced(out),
      "the keyword forward-change escalation is NOT pushed to the user (downgraded)")
check("free-running" in _ctx(out) or "eval-protocol" in _ctx(out),
      "the agent still gets the right principle (free-running) as a coach note")

# 3. Machine-certain (verifier-backed) items are NEVER downgraded, even on a verified
#    decision. A mel edit hits the real mel-power verifier AND the verified mel-power plan
#    decision; the verifier escalation must still reach the user.
ev_mel = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
          "tool_input": {"file_path": "/home/shiyil/mimo/encode.py",
                         "new_string": "mel = MelSpectrogram(sample_rate=24000, power=2.0)"}}
out = router.decide(ev_mel)
check("user" in _surfaced(out).lower() or "confirm" in _surfaced(out).lower()
      or "mel" in _surfaced(out).lower(),
      "machine-certain mel-power verifier still escalates to the user (not downgraded)")

# 4. ANTI-PRIOR WATCH — drifting toward an explicitly rejected option is caught on ANY action,
#    coach-level (agent-facing), and names the decision that rejected it.
ev_drift = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "torchrun train.py --resume dup_d3v21s/latest"}}
items, _ = planaware.assess(ev_drift)
check(any("REJECTED" in i["message"] and i.get("plan_decision") == "ckpt-init" for i in items),
      "anti-prior: resuming from a previous duplex ckpt is flagged (cites ckpt-init)")
out = router.decide(ev_drift)
check("REJECTED" in _ctx(out) and "Needs your check" not in _surfaced(out),
      "anti-prior reaches the agent as a coach (not a user-facing escalation)")
# a LEGITIMATE mention (borrowing the recipe / fresh-from-base) must NOT trip the watch
ev_ok = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
         "tool_input": {"command": "torchrun train.py --init_from base --fresh"}}
items_ok, _ = planaware.assess(ev_ok)
check(not any("REJECTED" in i["message"] for i in items_ok),
      "anti-prior does NOT fire on the legitimate fresh-from-base path (no false positive)")

# 5. HARD GATE — model/loss/training-stage work on an UN-DRILLED decision now BLOCKS the tool
#    action (reject -> permissionDecision deny) until the decision is quizzed + mastered. The
#    gate-clearing `progress.py mark` command is exempt (catch-22 guard); non-high-stakes never gate.
_sp = HOOKS.parent / "research" / ".state" / "mimo.plan-progress.json"    # ensure nothing mastered
_bak = _sp.read_text() if _sp.exists() else None
try:
    _sp.unlink()
except OSError:
    pass


def _pd(out):
    return ((out or {}).get("hookSpecificOutput", {}) or {}).get("permissionDecision")


def _reason(out):
    return ((out or {}).get("hookSpecificOutput", {}) or {}).get("permissionDecisionReason", "")


ev_hs = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
         "tool_input": {"file_path": "/home/shiyil/mimo/loss.py", "new_string": "empty_loss_weight = 0.5"}}
out_hs = router.decide(ev_hs)
check(_pd(out_hs) == "deny",
      "hard gate: high-stakes un-drilled tool action is BLOCKED (permissionDecision deny)")
check("BLOCKED" in _reason(out_hs) and "mark" in _reason(out_hs),
      "the deny reason instructs the agent to quiz, then run the mark command to clear it")
ev_clear = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": f"python3 {HOOKS.parent}/research/progress.py mark empty-loss-weight"}}
check(_pd(router.decide(ev_clear)) != "deny",
      "catch-22 guard: the `progress.py mark` command itself is never blocked by the gate")
ev_lo = {"hook_event_name": "PreToolUse", "tool_name": "Write",
         "tool_input": {"file_path": "/home/shiyil/mimo/eval_metric.py", "content": "aggregate accuracy top-1"}}
check(_pd(router.decide(ev_lo)) != "deny",
      "non-high-stakes (eval-stage) work does NOT block")
if _bak is not None:
    _sp.write_text(_bak)

# 6. FOREIGN-TREE EXEMPTION — a high-stakes-MATCHING edit whose target lives under a tree marked
#    `.trainlint-foreign` (a sibling tool repo / mined-repo checkout) must NOT block, even though
#    its content trips a high-stakes decision's keywords. Real project edits (no marker) still gate.
import tempfile  # noqa: E402

_foreign = Path(tempfile.mkdtemp(prefix="foreign-tree-"))
(_foreign / planaware.FOREIGN_MARKER).write_text("not the project under management\n")
try:
    _sp2 = HOOKS.parent / "research" / ".state" / "mimo.plan-progress.json"
    _bak2 = _sp2.read_text() if _sp2.exists() else None
    try:
        _sp2.unlink()
    except OSError:
        pass
    ev_foreign = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                  "tool_input": {"file_path": str(_foreign / "prospect.py"),
                                 "content": "SIGNAL = r'loss|lr|freeze|scheduler'  # mines fix-commits"}}
    items_f, located_f = planaware.assess(ev_foreign)
    check(items_f == [] and located_f == [],
          "foreign-tree edit locates NOTHING (gate + soft + drift all skipped)")
    check(_pd(router.decide(ev_foreign)) != "deny",
          "foreign-tree edit with high-stakes keywords is NOT blocked")
    # control: same content WITHOUT the marker (a real project path) still blocks
    ev_real = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
               "tool_input": {"file_path": "/home/shiyil/mimo/train.py", "new_string": "lr = 2e-5  # full-ft"}}
    check(_pd(router.decide(ev_real)) == "deny",
          "control: the SAME keywords in a real project path (no marker) still block")
    # 6b. BASH surface — a git commit run INSIDE the foreign tree, message full of guarded vocabulary
    #     AND a session URL (which must NOT be mistaken for a disqualifying path), is exempt too.
    ev_commit = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": f"cd {_foreign} && git commit -m "
                                           f"'fix loss lr freeze scheduler dedup split; "
                                           f"see https://claude.ai/code/session_x'"}}
    check(_pd(router.decide(ev_commit)) != "deny",
          "foreign-tree bash commit (vocabulary-heavy message + URL) is NOT blocked")
    # 6c. the HARNESS's OWN source tree (has .claude-plugin/plugin.json) is exempt on the bash surface
    #     too — committing the fix itself, with a vocabulary-heavy message, must not trip the gate.
    ev_self = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": f"cd {HOOKS.parent} && git commit -m 'fix loss lr freeze scheduler'"}}
    check(_pd(router.decide(ev_self)) != "deny",
          "bash command inside the harness's own plugin-source tree is NOT blocked")
    # ...but a command that ALSO touches a real, EXISTING, non-exempt path stays gated (fail-safe)
    _realfd, _realpath = tempfile.mkstemp(prefix="real-nonexempt-")  # in /tmp: no marker, no plugin.json
    ev_mixed = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": f"cd {_foreign} && git apply {_realpath}  # loss lr"}}
    check(planaware._action_is_foreign(ev_mixed) is False,
          "a bash command touching BOTH an exempt tree and a real non-exempt path stays gated")
    import os  # noqa: E402
    os.close(_realfd)
    os.unlink(_realpath)
    if _bak2 is not None:
        _sp2.write_text(_bak2)
finally:
    import shutil  # noqa: E402
    shutil.rmtree(_foreign, ignore_errors=True)

print(f"\n{21 - fails}/21 passed")
sys.exit(1 if fails else 0)
