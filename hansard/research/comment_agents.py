#!/usr/bin/env python3
"""comment_agents — the report is the center: comment → agent → propose a report change → you review.

The operator leaves COMMENTS on a report. "Deal with comments" spawns ONE read-only Claude Code
agent per comment. Each agent investigates the real code + the report substrate (grounded in
file:line) and PROPOSES a concrete change to the REPORT that resolves the comment. The operator
reviews each proposal and either APPLIES it or SENDS IT BACK with feedback — in which case the
SAME agent session RESUMES (claude --resume) for another pass. Nothing lands until the operator
approves; the system NEVER edits code or touches git — it only writes the report's own substrate
(glossary / clarifications), exactly like today's digest.

This is the general form of feedback_agent (which was one-shot per feedback item): here each
comment gets a RESUMABLE session that can iterate under human review.

Per-comment session record in  agent_sessions.<name>.jsonl  (merged by comment key):
  {key, quote, note, sid, state, passes, proposal, run_dir, ts}
  state: running | proposed | applied | dismissed
Full multi-pass transcript (the accessible log) grows under  agent_runs/<name>/<key>/transcript.jsonl

CLI:  python3 comment_agents.py deal   <project>            spawn an agent for every NEW comment
      python3 comment_agents.py resume <project> <key> "<operator feedback>"   another pass
      python3 comment_agents.py apply  <project> <key>      land the proposal into the substrate
      python3 comment_agents.py list   <project>
"""
import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import paths          # noqa: E402
import feedback       # noqa: E402  — reuse collect_new (comments -> items)
import feedback_agent as fa  # noqa: E402  — reuse the read-only spawn/parse core

STATES = ("running", "proposed", "applied", "dismissed")


def _sessions_path(name):
    return paths.wfile(f"agent_sessions.{name}.jsonl")


def _run_dir(name, key):
    slug = "".join(c if (c.isalnum() or c in "._-") else "_" for c in str(key))[:80] or "item"
    d = paths.data_root() / "agent_runs" / name / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_sessions(name):
    """All per-comment session records, newest write wins per key (merge-by-key). [] if none."""
    p = _sessions_path(name)
    if not p.exists():
        return []
    by, order = {}, []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        k = o.get("key")
        if not k:
            continue
        if k not in by:
            order.append(k)
        by[k] = o
    return [by[k] for k in order]


def _merge_session(name, rec):
    """Atomic upsert of one session record by key (single writer under the backend lock)."""
    recs = load_sessions(name)
    seen = False
    for i, r in enumerate(recs):
        if r.get("key") == rec["key"]:
            recs[i] = rec
            seen = True
            break
    if not seen:
        recs.append(rec)
    p = _sessions_path(name)
    body = ("# hansard comment-agent sessions — one per comment, merged by key. See comment_agents.py.\n"
            + "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n")
    tmp = p.with_suffix(".jsonl.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(p)
    return rec


AGENT_SYS = (
    "You are a hansard report agent. The operator left a COMMENT on a research status report and you "
    "handle it like a developer picking up that one ticket. You are READ-ONLY (Read/Grep/Glob) — you "
    "investigate the REAL project code and the report substrate (grounded in file:line) and PROPOSE a "
    "concrete change to the REPORT that resolves the comment. You never edit code; a human reviews "
    "your proposal and a deterministic step applies the safe part. Be right and grounded, not verbose.")

_SCHEMA = """RETURN — your FINAL message must be ONLY this JSON (no prose, no fence), small and valid:
{
  "summary": "2-4 sentences: what you found and how you concluded, grounded in file:line",
  "report_change": {
    "kind": "glossary | note | none",
    "human_readable": "ONE line: exactly what will change on the report if approved",
    "glossary": [{"term": "...", "plain": "one jargon-free sentence", "why": "why it matters HERE (file:line)"}],
    "note": "a clarification/correction note to attach to the report (empty unless kind=note)"
  },
  "done": true,
  "evidence": ["file:line", "..."],
  "confidence": "high | medium | low"
}
kind=glossary -> fill glossary[] (the terms that would have prevented the confusion); kind=note ->
fill note; kind=none -> nothing to change (say why in summary). done=false ONLY if you are blocked
and need the operator to clarify before you can propose."""


def _prompt_new(item, name, sub_dirs):
    return f"""{AGENT_SYS}

THE COMMENT (left on the report for project '{name}'):
- on / context: {item.get('quote') or '(no anchor context)'}
- the operator wrote: "{item.get('note')}"

READ — the report substrate (under {paths.data_root()}/):
  goal.{name}.txt · purpose.{name}.txt · plan.{name}.jsonl · surprises.{name}.jsonl ·
  focus.{name}.jsonl · glossary.{name}.jsonl · log.{name}.jsonl
THE REAL PROJECT CODE you may read: {', '.join(sub_dirs) or '(none configured — substrate only)'}

Locate what the comment refers to, verify against the real code, then propose the report change.
{_SCHEMA}"""


def _prompt_resume(fb):
    return (f"The operator REVIEWED your proposal and SENT IT BACK with this feedback:\n\"{fb}\"\n\n"
            f"Revise: investigate further if needed (still READ-ONLY) and re-propose.\n{_SCHEMA}")


def _run_agent(name, key, prompt, sid, resume):
    """Spawn (or RESUME) one read-only agent session; append to transcript.jsonl; return the parsed
    proposal dict or None. Uses a fixed per-comment session id so a send-back can --resume it."""
    sub_dirs = fa._repo_dirs(name)
    rec_dir = _run_dir(name, key)
    cmd = [fa.CLAUDE, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--allowedTools", *fa.READ_ONLY_TOOLS, "--disallowedTools", *fa.DENY_TOOLS]
    cmd += ["--resume", sid] if resume else ["--session-id", sid]
    cmd += ["--add-dir", str(paths.data_root())]
    for d in sub_dirs:
        cmd += ["--add-dir", d]
    model = os.environ.get("HANSARD_AGENT_MODEL") or os.environ.get("TRAINLINT_AGENT_MODEL")
    if model:
        cmd += ["--model", model]
    tpath = rec_dir / "transcript.jsonl"
    cwd = sub_dirs[0] if sub_dirs else str(paths.data_root())
    try:
        # append across passes so the transcript is the FULL multi-pass session log
        with open(tpath, "ab") as tf, open(os.devnull, "rb") as devnull:
            subprocess.run(cmd, stdin=devnull, stdout=tf, stderr=subprocess.DEVNULL,
                           cwd=cwd, timeout=fa.PER_AGENT_TIMEOUT)
    except Exception as e:
        return {"_error": str(e)[:300]}
    return fa._parse_result(tpath)


def run_one(name, item):
    """First pass for one NEW comment: mint a session id, spawn a read-only agent, store the
    proposal. Returns the session record."""
    key = item.get("key")
    sid = str(uuid.uuid4())
    rec = {"key": key, "quote": item.get("quote", ""), "note": item.get("note", ""),
           "sid": sid, "state": "running", "passes": 0,
           "run_dir": f"agent_runs/{name}/{key}/", "ts": time.time()}
    _merge_session(name, rec)
    prop = _run_agent(name, key, _prompt_new(item, name, fa._repo_dirs(name)), sid, resume=False)
    return _finish(name, rec, prop)


def resume_one(name, key, fb):
    """Another pass: the operator sent the proposal back with feedback; RESUME the same session."""
    rec = next((r for r in load_sessions(name) if r.get("key") == key), None)
    if not rec:
        return None
    rec["state"] = "running"
    _merge_session(name, rec)
    prop = _run_agent(name, key, _prompt_resume(fb), rec["sid"], resume=True)
    return _finish(name, rec, prop)


def _finish(name, rec, prop):
    rec["passes"] = rec.get("passes", 0) + 1
    if not prop or prop.get("_error"):
        rec["state"] = "proposed"
        rec["proposal"] = {"kind": "none", "human_readable": "agent returned no parseable proposal",
                           "summary": (prop or {}).get("_error", "no result")}
    else:
        rec["proposal"] = prop
        rec["state"] = "proposed"
    (paths.data_root() / rec["run_dir"] / "proposal.json").write_text(
        json.dumps(rec.get("proposal", {}), ensure_ascii=False, indent=2), encoding="utf-8")
    return _merge_session(name, rec)


def apply_one(name, key):
    """Land the approved proposal into the report SUBSTRATE (no code, no git). Slice 1 applies the
    two safe kinds — glossary (dedup by term) and note (a clarification row) — then marks applied."""
    rec = next((r for r in load_sessions(name) if r.get("key") == key), None)
    if not rec or rec.get("state") != "proposed":
        return None
    rc = (rec.get("proposal") or {}).get("report_change") or {}
    kind = rc.get("kind")
    if kind == "glossary":
        gp = paths.resolve(f"glossary.{name}.jsonl")
        have = set()
        if gp.exists():
            for ln in gp.read_text(encoding="utf-8").splitlines():
                try:
                    have.add(json.loads(ln).get("term"))
                except Exception:
                    pass
        with gp.open("a", encoding="utf-8") as f:
            for t in (rc.get("glossary") or []):
                if t.get("term") and t["term"] not in have:
                    f.write(json.dumps({"term": t["term"], "plain": t.get("plain", ""),
                                        "why": t.get("why", ""), "dec": None}, ensure_ascii=False) + "\n")
    elif kind == "note" and rc.get("note"):
        cp = paths.resolve(f"clarify.{name}.jsonl")
        with cp.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"q": rec.get("note", ""), "a": rc.get("note"), "dec": None,
                                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                               ensure_ascii=False) + "\n")
    rec["state"] = "applied"
    _merge_session(name, rec)
    try:
        import viz
        viz.generate(name)  # re-render + re-upload so the applied change shows on the report
    except Exception:
        pass
    return rec


def dismiss_one(name, key):
    rec = next((r for r in load_sessions(name) if r.get("key") == key), None)
    if rec:
        rec["state"] = "dismissed"
        _merge_session(name, rec)
    return rec


def deal(name):
    """Spawn a read-only agent for every NEW comment (one without a session yet), bounded."""
    existing = {r.get("key") for r in load_sessions(name)}
    _items, recs = feedback.collect_new(name)
    fresh = [r for r in recs if r.get("src") == "comment" and r.get("key") not in existing]
    if not fresh:
        return {"project": name, "new": 0}
    cap = max(1, int(os.environ.get("HANSARD_DIGEST_AGENTS") or os.environ.get("TRAINLINT_DIGEST_AGENTS", "3")))
    with ThreadPoolExecutor(max_workers=cap) as ex:
        list(ex.map(lambda it: run_one(name, it), fresh))
    try:
        import viz
        viz.generate(name)  # bake the new proposals onto the report for review
    except Exception:
        pass
    return {"project": name, "new": len(fresh)}


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().split("CLI:")[-1].strip())
        return 2
    cmd, name = argv[0], argv[1]
    if cmd == "deal":
        print(json.dumps(deal(name)))
    elif cmd == "resume" and len(argv) >= 4:
        r = resume_one(name, argv[2], argv[3])
        print("resumed" if r else "no such session", argv[2])
    elif cmd == "apply" and len(argv) >= 3:
        r = apply_one(name, argv[2])
        print("applied" if r else "not applicable", argv[2])
    elif cmd == "list":
        for r in load_sessions(name):
            rc = (r.get("proposal") or {}).get("report_change") or {}
            print(f"{r.get('state', '?'):<9} pass{r.get('passes', 0)} {r.get('key', '')[:36]}"
                  f"  [{rc.get('kind', '-')}] {rc.get('human_readable', '')[:70]}")
    else:
        print("usage: comment_agents.py deal|resume|apply|list <project> ...")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
