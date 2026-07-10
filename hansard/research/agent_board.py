#!/usr/bin/env python3
"""agent_board — a board of Claude Code CLI agents, one per TASK, managed from the report.

This is the general form of feedback_agent (which runs one read-only agent per feedback item):
here the unit of work is a TASK the operator (or, later, another agent) creates, tracked on a
board and rendered on the report. SLICE 0 ships ONLY the read-only `investigator` task — same
proven safety regime as the digest (agents have NO write path; Read/Grep/Glob allowed,
Bash/Write/Edit/NotebookEdit denied). The write-tier (agents editing in an isolated git worktree,
operator-approved onto an agent/<id> branch) and the bounded recursive orchestrator graft onto
THIS spine later without reopening it. See memory: multiagent-board-design.

Substrate (per operator, under the per-tenant data_root):
  tasks.<board>.jsonl              — one JSON line per task, merged by id (the board state)
  agent_runs/<board>/<id>/         — transcript.jsonl (full stream-json) + outcome.json (the log)
  .agent_status.<board>.json       — scheduler liveness + counts, for the report poll

The id is ALWAYS server-minted (paths derive from it); `board` is validated by the same strict
allowlist the worker/feedback path uses before it ever touches paths.* or subprocess.

CLI:  python3 agent_board.py create <board> "<title>" "<prompt>"   -> mints + queues a task
      python3 agent_board.py run    <board>                         -> run all queued tasks
      python3 agent_board.py list   <board>
"""
import json
import os
import re
import secrets
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import paths          # noqa: E402
import feedback_agent as fa  # noqa: E402  — reuse the proven spawn/parse core verbatim

# The two hardcoded tool constants in feedback_agent become a NAMED policy registry. Slice 0 has
# only read_only (byte-identical to the digest's policy). write_worktree lands with the write-tier.
POLICIES = {
    "read_only": {"allow": fa.READ_ONLY_TOOLS, "deny": fa.DENY_TOOLS, "writes": False},
}
SAFE_BOARD = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
SAFE_ID = re.compile(r"^t-[a-f0-9]{12}$")
TASK_STATES = ("queued", "running", "done", "error")


def _safe_board(v):
    v = str(v or "").strip()
    return v if SAFE_BOARD.match(v) else ""


def _tasks_path(board):
    return paths.data_root() / f"tasks.{board}.jsonl"


def _run_dir(board, tid):
    d = paths.data_root() / "agent_runs" / board / tid
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_tasks(board):
    """All task rows for a board, newest write wins on duplicate id (merge-by-id). [] if none."""
    board = _safe_board(board)
    p = _tasks_path(board) if board else None
    if not p or not p.exists():
        return []
    by = {}
    order = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        tid = o.get("id")
        if not tid:
            continue
        if tid not in by:
            order.append(tid)
        by[tid] = o
    return [by[t] for t in order]


def _write_tasks(board, tasks):
    """Atomic rewrite of the whole board file (single writer: the scheduler / a create call under
    the backend lock). Temp-in-same-dir + replace, so a crash never leaves a half file."""
    p = _tasks_path(board)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "# hansard agent board — one task per line, merged by id. See agent_board.py.\n" + \
           "\n".join(json.dumps(t, ensure_ascii=False) for t in tasks) + "\n"
    tmp = p.with_suffix(".jsonl.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(p)


def _merge_task(board, task):
    """Upsert one task row by id, preserving order, atomically. Returns the merged list."""
    tasks = load_tasks(board)
    seen = False
    for i, t in enumerate(tasks):
        if t.get("id") == task["id"]:
            tasks[i] = task
            seen = True
            break
    if not seen:
        tasks.append(task)
    _write_tasks(board, tasks)
    return tasks


def _status_path(board):
    return paths.data_root() / f".agent_status.{board}.json"


def _write_status(board, obj):
    try:
        p = _status_path(board)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass


def board_status(board):
    """{state, total, done, running, pid, counts{}} for the report poll. Task states are read from
    tasks.jsonl (the single source of truth); the scheduler-liveness pid comes from the status file
    and is validated with the SAME /proc-cmdline liveness check the digest uses (no blind kill)."""
    board = _safe_board(board)
    if not board:
        return {"state": "idle"}
    tasks = load_tasks(board)
    counts = {s: 0 for s in TASK_STATES}
    for t in tasks:
        counts[t.get("state", "queued")] = counts.get(t.get("state", "queued"), 0) + 1
    st = {}
    try:
        st = json.loads(_status_path(board).read_text(encoding="utf-8"))
    except Exception:
        pass
    running = st.get("state") == "running" and _sched_alive(st.get("pid"))
    return {"state": "running" if running else "idle", "board": board,
            "total": len(tasks), "done": counts.get("done", 0) + counts.get("error", 0),
            "counts": counts, "pid": st.get("pid") if running else None,
            "tasks": [{"id": t.get("id"), "title": t.get("title"), "state": t.get("state"),
                       "kind": (t.get("outcome") or {}).get("kind")} for t in tasks]}


def _sched_alive(pid):
    """True iff `pid` is a LIVE agent_board scheduler — cmdline check, not a blind kill(pid,0), so a
    recycled pid reads as dead and the board never wedges (same discipline as viz.digest_alive)."""
    try:
        pid = int(pid or 0)
        if pid <= 0:
            return False
        cl = Path(f"/proc/{pid}/cmdline").read_bytes()
        return b"agent_board" in cl and b"run" in cl
    except Exception:
        return False


# ---- task creation -------------------------------------------------------------------------------
def create_task(board, title, prompt, policy="read_only", created_by="operator", source=""):
    """Mint a server-side id and write a queued task row. Returns the task dict, or None on a bad
    board / unknown policy (never trust caller-supplied ids or policy VALUES — only a policy NAME).
    `source` carries the operator note a kimi-drafted task came from (the 📋 Tasks tab shows it)."""
    board = _safe_board(board)
    if not board or policy not in POLICIES:
        return None
    tid = "t-" + secrets.token_hex(6)
    task = {"id": tid, "board": board, "title": (str(title or "").strip()[:200] or "(untitled)"),
            "prompt": str(prompt or "").strip()[:8000], "type": "investigator", "policy": policy,
            "state": "queued", "created_by": created_by, "source": str(source or "").strip()[:300],
            "created_ts": time.time(),
            "run_dir": f"agent_runs/{board}/{tid}/", "outcome": None, "pid": None, "error": None}
    _merge_task(board, task)
    return task


# ---- the read-only investigator agent ------------------------------------------------------------
INVESTIGATOR_SYS = (
    "You are a hansard board agent handling ONE task on a research project, like a developer picking "
    "up a ticket. You investigate the REAL project code and the report substrate, grounded in "
    "file:line, and return a STRUCTURED result. You are READ-ONLY (Read/Grep/Glob only) — you "
    "investigate and PROPOSE; you do not edit anything. Be right and grounded, not verbose.")


def _task_prompt(task, board, sub_dirs):
    return f"""{INVESTIGATOR_SYS}

THE TASK: {task.get('title')}
{task.get('prompt')}

READ — the report substrate for board '{board}' (under {paths.data_root()}/):
  goal.{board}.txt · purpose.{board}.txt · plan.{board}.jsonl ·
  focus.{board}.jsonl · glossary.{board}.jsonl · log.{board}.jsonl
THE REAL PROJECT CODE you may read: {', '.join(sub_dirs) or '(none configured — substrate only)'}

RETURN — your FINAL message must be ONLY this JSON (no prose, no code fence), small and valid:
{{
  "summary": "2-5 sentences: what you found, grounded",
  "findings": ["one concrete finding with file:line", "..."],
  "proposal": "the concrete next step / change you WOULD make (someone else applies it)",
  "evidence": ["file:line", "..."],
  "confidence": "high|medium|low"
}}"""


PLAIN_SYS = (
    "You summarize ONE finished investigation for the project's operator. Input JSON: the task "
    "(title + instruction + the operator note it came from) and the agent's structured outcome. "
    "Write 2-4 SHORT sentences in the SAME LANGUAGE as the operator note / task title: what was "
    "checked, what was found, and what should happen next or be decided. Plain words a "
    "non-engineer reads in one pass — NO file:line, no code identifiers, no JSON, no headings. "
    "Output the sentences only.")


def _plain_summary(task, outcome):
    """The report ladder (default kimi) rewrites the claude agent's technical outcome into a few
    plain sentences in the operator's language — the 📋 Tasks tab surface (claude never writes
    reader-facing prose). '' on any failure or when the LLM is off (fail-open: the technical
    outcome still renders, folded)."""
    prov = (os.environ.get("HANSARD_REPORT_LLM")
            or os.environ.get("TRAINLINT_REPORT_LLM", "kimi")).strip().lower()
    if prov in ("", "none", "off", "0", "false", "template"):
        return ""
    try:
        import viz
        user = json.dumps({"task": {"title": task.get("title"), "prompt": task.get("prompt"),
                                    "operator_note": task.get("source") or ""},
                           "outcome": outcome}, ensure_ascii=False)
        return viz._llm(prov, PLAIN_SYS, user).strip()[:1200]
    except Exception:
        return ""


def run_task(task):
    """Spawn one read-only Claude Code agent for `task`; capture transcript + outcome; return the
    updated task dict. Reuses feedback_agent's spawn+parse core (read_only policy, byte-identical
    tool flags). NO write path: Read/Grep/Glob allowed, Bash/Write/Edit/NotebookEdit denied."""
    board = task["board"]
    tid = task["id"]
    pol = POLICIES.get(task.get("policy", "read_only"))
    if pol is None or pol["writes"]:
        task.update(state="error", error="unknown or write policy not supported in slice 0")
        _merge_task(board, task)
        return task
    sub_dirs = fa._repo_dirs(board)
    rec = _run_dir(board, tid)
    prompt = _task_prompt(task, board, sub_dirs)
    cmd = [fa.CLAUDE, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--allowedTools", *pol["allow"], "--disallowedTools", *pol["deny"],
           "--add-dir", str(paths.data_root())]
    for d in sub_dirs:
        cmd += ["--add-dir", d]
    model = os.environ.get("HANSARD_AGENT_MODEL") or os.environ.get("TRAINLINT_AGENT_MODEL")
    if model:
        cmd += ["--model", model]
    tpath = rec / "transcript.jsonl"
    cwd = sub_dirs[0] if sub_dirs else str(paths.data_root())
    task.update(state="running", pid=os.getpid())
    _merge_task(board, task)
    try:
        with open(tpath, "wb") as tf, open(os.devnull, "rb") as devnull:
            subprocess.run(cmd, stdin=devnull, stdout=tf, stderr=subprocess.DEVNULL,
                           cwd=cwd, timeout=fa.PER_AGENT_TIMEOUT)
    except Exception as e:
        task.update(state="error", error=str(e)[:300], pid=None)
        (rec / "outcome.json").write_text(json.dumps({"error": str(e)[:300]}), encoding="utf-8")
        _merge_task(board, task)
        return task
    outcome = fa._parse_result(tpath)
    if outcome is not None:
        (rec / "outcome.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
        task.update(state="done", outcome=outcome, pid=None, error=None,
                    plain=_plain_summary(task, outcome))
    else:
        task.update(state="error", error="agent returned no parseable structured result", pid=None)
    _merge_task(board, task)
    return task


def run_board(board):
    """Run every QUEUED task on the board with bounded concurrency; keep the status file fresh so
    the report poll shows done/total. Single-flight is enforced by the caller (backend lock) +
    the cmdline-liveness check; this just does the work."""
    board = _safe_board(board)
    if not board:
        return {"error": "bad board"}
    queued = [t for t in load_tasks(board) if t.get("state") == "queued"]
    total = len(queued)
    if not total:
        _write_status(board, {"state": "idle", "board": board, "note": "no queued tasks"})
        return {"board": board, "ran": 0}
    cap = max(1, int(os.environ.get("HANSARD_DIGEST_AGENTS") or os.environ.get("TRAINLINT_DIGEST_AGENTS", "3")))
    done = [0]
    _write_status(board, {"state": "running", "board": board, "total": total, "done": 0,
                          "pid": os.getpid(), "started": time.time()})

    def _task(t):
        r = run_task(t)
        done[0] += 1
        _write_status(board, {"state": "running", "board": board, "total": total, "done": done[0],
                              "pid": os.getpid(), "started": time.time()})
        return r

    with ThreadPoolExecutor(max_workers=cap) as ex:
        results = list(ex.map(_task, queued))
    ok = sum(1 for r in results if r.get("state") == "done")
    _write_status(board, {"state": "done", "board": board, "total": total, "done": len(results),
                          "ok": ok, "finished": time.time()})
    # re-render + re-upload so the board's new results are baked into the static report
    try:
        import viz
        viz.generate(board)
    except Exception:
        pass
    return {"board": board, "ran": total, "ok": ok}


def main(argv):
    if not argv:
        print(__doc__.strip().split("CLI:")[-1].strip())
        return 2
    cmd = argv[0]
    if cmd == "create" and len(argv) >= 4:
        t = create_task(argv[1], argv[2], argv[3])
        if not t:
            print("bad board or policy")
            return 1
        print(f"queued {t['id']}: {t['title']}")
        return 0
    if cmd == "run" and len(argv) >= 2:
        print(json.dumps(run_board(argv[1])))
        return 0
    if cmd == "list" and len(argv) >= 2:
        for t in load_tasks(argv[1]):
            oc = t.get("outcome") or {}
            print(f"{t['state']:<8} {t['id']}  {t.get('title','')[:60]}"
                  + (f"  -> {oc.get('summary','')[:80]}" if oc.get('summary') else ""))
        return 0
    print("usage: agent_board.py create|run|list <board> ...")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
