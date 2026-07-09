#!/usr/bin/env python3
"""agent_board core tests — the deterministic spine (no agent spawn).

Covers the task substrate (mint/create/merge-by-id/load), board_status counts, the /proc-cmdline
liveness discipline, and the two safety gates: board-name allowlist and policy-NAME-only (a
client can never inject a raw tool flag or a write policy in slice 0). The agent spawn itself is
verified end-to-end by CLI (create -> run -> done + transcript.jsonl + outcome.json), not here.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
os.environ["TRAINLINT_DATA_DIR"] = tempfile.mkdtemp()  # isolate: board files land in a throwaway root
import agent_board as ab  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("ok    " if cond else "FAIL  ") + msg)
    if not cond:
        fails += 1


# ---- create + mint + persist -----------------------------------------------------------------
t = ab.create_task("myboard", "  a title  ", "investigate X")
check(t and ab.SAFE_ID.match(t["id"]), "create: id is server-minted t-<12hex>")
check(t["state"] == "queued" and t["board"] == "myboard", "create: queued row on the named board")
check(t["title"] == "a title" and t["policy"] == "read_only", "create: title trimmed, default policy read_only")
check(t["run_dir"] == f"agent_runs/myboard/{t['id']}/", "create: run_dir derived from the minted id")

# ---- safety gates ----------------------------------------------------------------------------
check(ab.create_task("../etc/passwd", "x", "y") is None, "gate: board name outside allowlist rejected")
check(ab.create_task("bad/slash", "x", "y") is None, "gate: board with a slash rejected")
check(ab.create_task("myboard", "x", "y", policy="write_worktree") is None,
      "gate: an unknown/write policy NAME is rejected (slice 0 is read-only only)")
check("write_worktree" not in ab.POLICIES and not ab.POLICIES["read_only"]["writes"],
      "gate: only read_only exists, and it is declared non-writing")
check(ab.POLICIES["read_only"]["deny"] == ["Bash", "Write", "Edit", "NotebookEdit"],
      "gate: read_only denies every write tool (Bash included) — no write path")

# ---- load + merge-by-id ----------------------------------------------------------------------
t2 = ab.create_task("myboard", "second", "y")
ids = [x["id"] for x in ab.load_tasks("myboard")]
check(ids == [t["id"], t2["id"]], "load: both tasks present, insertion order preserved")
t["state"] = "done"
t["outcome"] = {"summary": "did it", "kind": None}
ab._merge_task("myboard", t)
reload = ab.load_tasks("myboard")
check(len(reload) == 2, "merge: updating a task by id does not duplicate the row")
check(next(x for x in reload if x["id"] == t["id"])["state"] == "done", "merge: the update took")

# ---- board_status ----------------------------------------------------------------------------
st = ab.board_status("myboard")
check(st["total"] == 2 and st["counts"]["done"] == 1 and st["counts"]["queued"] == 1,
      "status: counts reflect task states")
check(st["state"] == "idle", "status: no live scheduler -> idle")
check([x["id"] for x in st["tasks"]] == [t["id"], t2["id"]], "status: task summaries in order")
check(ab.board_status("../etc") == {"state": "idle"}, "status: bad board -> idle, no crash")

# ---- liveness: a bogus pid reads as dead (cmdline check, not blind kill) ----------------------
check(ab._sched_alive(0) is False and ab._sched_alive(2_000_000_000) is False,
      "liveness: nonexistent/zero pid reads as dead")

print("\n" + ("ALL PASS" if not fails else f"{fails} FAILURES"))
sys.exit(1 if fails else 0)
