#!/usr/bin/env python3
"""Load — inhale an EXISTING project's accumulated context ONCE, then keep it in front
of every new session. The deterministic half of `/hansard:load` (the classification —
skill vs lint vs knowledge — is judgment, so the AGENT does it; this module only
discovers sources, keeps the load-once manifest, and surfaces what was inhaled).

What it discovers (per project, home-scoped — never machine-wide):
  - agent guidance:   CLAUDE.md / .claude/CLAUDE.md / CLAUDE.local.md / AGENTS.md
  - project skills:   .claude/skills/**/*.md   .claude/commands/**/*.md
  - other rules:      .cursorrules  .cursor/rules/**  .github/copilot-instructions.md
  - auto-memory:      ~/.claude/projects/<slug(home)>/memory/*.md  (Claude Code's
                      per-project memory dir; slug = home with [^A-Za-z0-9] -> '-')

Where the classified entries land (the agent writes these, incrementally):
  skill      -> skills.<name>.jsonl     (reusable procedures; NEW store, this feature)
  knowledge  -> knowledge.<name>.jsonl  (facts/findings indexed by the problem they solve)
  lint       -> project.<name>.json     (doorman facts; a general rule only via DESIGN.md §8)
  glossary   -> glossary.<name>.jsonl   (term definitions)

Load-once: `mark` stamps load.<name>.json = {ts, sources: {path: sha16}}. A later
`discover`/`status` diffs content hashes, so re-running /hansard:load ingests ONLY
new/changed sources — never re-inhales what's already in.

CLI (all fail-open, always exit 0 — flow.py imports brief()/skill_hits() directly):
  python3 load.py discover [project]   # candidate sources, one JSON per line (+state)
  python3 load.py status   [project]   # loaded? when? what changed since?
  python3 load.py mark     [project]   # stamp the manifest from the current source set
  python3 load.py digest   [project]   # the one-line SessionStart digest
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paths  # noqa: E402  — per-project data lives outside the versioned plugin dir


def _load_jsonl(path):
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return rows
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _sha(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception:
        return ""


def memory_dir(home: str) -> Path:
    """Claude Code's auto-memory dir for a project home — ~/.claude/projects/<slug>/memory,
    slug = the home path with every non-alphanumeric char replaced by '-'
    (/home/u/.claude/x -> -home-u--claude-x)."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(home))
    return Path.home() / ".claude" / "projects" / slug / "memory"


def _candidates(home: str):
    """(path, kind) for every source file worth inhaling. Existence-checked, read nothing."""
    h = Path(home)
    singles = [
        (h / "CLAUDE.md", "guidance"),
        (h / "CLAUDE.local.md", "guidance"),
        (h / ".claude" / "CLAUDE.md", "guidance"),
        (h / "AGENTS.md", "guidance"),
        (h / ".cursorrules", "rules"),
        (h / ".github" / "copilot-instructions.md", "rules"),
    ]
    out = [(p, k) for p, k in singles if p.is_file()]
    for pat, kind in ((".claude/skills/**/*.md", "skill"),
                      (".claude/commands/**/*.md", "command"),
                      (".cursor/rules/**/*", "rules")):
        try:
            out += [(p, kind) for p in sorted(h.glob(pat)) if p.is_file()]
        except Exception:
            pass
    md = memory_dir(home)
    try:
        out += [(p, "memory-index" if p.name == "MEMORY.md" else "memory")
                for p in sorted(md.glob("*.md")) if p.is_file()]
    except Exception:
        pass
    return out


def manifest(name):
    """The load-once record {ts, sources: {path: sha16}}, or {} if never loaded."""
    try:
        p = paths.resolve(f"load.{name}.json")
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def diff_sources(sources, man):
    """Split a discover set against the manifest: state = new | changed | ingested.
    Pure — takes [(path_str, sha)] + manifest dict, so it's directly testable."""
    seen = (man or {}).get("sources", {}) or {}
    out = []
    for path, sha in sources:
        if path not in seen:
            out.append((path, "new"))
        elif seen[path] != sha:
            out.append((path, "changed"))
        else:
            out.append((path, "ingested"))
    return out


def discover(name, home=None):
    """Every candidate source for this project, each with its load state.
    Returns [{path, kind, bytes, sha, state}]. Fail-open: no home -> []."""
    home = home or paths.project_home(name)
    if not home or not Path(home).is_dir():
        return []
    cands = _candidates(home)
    states = dict(diff_sources([(str(p), _sha(p)) for p, _ in cands], manifest(name)))
    out = []
    for p, kind in cands:
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        out.append({"path": str(p), "kind": kind, "bytes": size,
                    "sha": _sha(p), "state": states.get(str(p), "new")})
    return out


def mark(name, home=None):
    """Stamp the manifest from the CURRENT source set (call after ingesting). Returns path or None."""
    from datetime import datetime, timezone
    srcs = discover(name, home)
    man = manifest(name)
    merged = dict((man or {}).get("sources", {}) or {})
    merged.update({s["path"]: s["sha"] for s in srcs})
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "first_ts": (man or {}).get("first_ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "sources": merged}
    p = paths.wfile(f"load.{name}.json")
    try:
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
    except Exception:
        return None


def skill_hits(name, prompt, skills=None):
    """Loaded skills whose `match` keywords appear in the prompt — the just-in-time
    'you already have a procedure for this' signal (same coupling as the surfacer:
    trigger = the task at hand, not recency)."""
    text = (prompt or "").lower()
    if not text:
        return []
    if skills is None:
        skills = _load_jsonl(paths.resolve(f"skills.{name}.jsonl"))
    hits = []
    for s in skills:
        kws = s.get("match", []) or []
        if any(str(k).lower() in text for k in kws if str(k).strip()):
            hits.append(s)
    return hits


def brief(name):
    """The one-line SessionStart digest. Three states:
    never loaded + sources exist -> nudge /hansard:load once (the inhale);
    loaded -> counts + where the stores live + the KEEP-PRODUCING contract;
    nothing to say -> ''. Fail-open."""
    try:
        man = manifest(name)
        sk = _load_jsonl(paths.resolve(f"skills.{name}.jsonl"))
        kn = _load_jsonl(paths.resolve(f"knowledge.{name}.jsonl"))
        if not man:
            srcs = discover(name)
            if srcs:
                return (f"🧳 {len(srcs)} un-ingested skill/memory file(s) exist for this project "
                        f"(CLAUDE.md / .claude/skills / auto-memory) — run `/hansard:load` ONCE to "
                        f"inhale them into skill / lint / knowledge stores")
            return ""
        pending = [s for s in discover(name) if s["state"] != "ingested"]
        bits = [f"🧰 inhaled memory: {len(sk)} skill(s) · {len(kn)} knowledge entr(ies) "
                f"(loaded {str(man.get('first_ts', ''))[:10]})"]
        if sk:
            titles = " · ".join(s.get("title", s.get("id", "?")) for s in sk[:6])
            bits.append(f"skills on file: {titles}{' …' if len(sk) > 6 else ''} — read "
                        f"{paths.resolve(f'skills.{name}.jsonl')} before reinventing a procedure")
        bits.append("keep the stores growing as you work: new reusable procedure → skills, "
                    "new fact/finding → knowledge, new guardable mistake → project facts (lint)")
        if pending:
            bits.append(f"⟳ {len(pending)} source file(s) new/changed since load — "
                        f"`/hansard:load` refreshes just those")
        return "  ·  ".join(bits)
    except Exception:
        return ""


def status_text(name):
    man = manifest(name)
    srcs = discover(name)
    if not man:
        return (f"never loaded. {len(srcs)} candidate source(s) found — run /hansard:load to inhale."
                if srcs else "never loaded, and no candidate sources found (no home / nothing to inhale).")
    fresh = [s for s in srcs if s["state"] != "ingested"]
    sk = len(_load_jsonl(paths.resolve(f"skills.{name}.jsonl")))
    kn = len(_load_jsonl(paths.resolve(f"knowledge.{name}.jsonl")))
    lines = [f"loaded {man.get('first_ts', '?')} (last refresh {man.get('ts', '?')}) — "
             f"{sk} skills · {kn} knowledge entries on file."]
    if fresh:
        lines.append(f"{len(fresh)} source(s) new/changed since — /hansard:load refreshes ONLY these:")
        lines += [f"  [{s['state']}] {s['path']}" for s in fresh]
    else:
        lines.append("all sources unchanged — nothing to re-ingest.")
    return "\n".join(lines)


def _main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    cmd = args[0] if args else "status"
    name = args[1] if len(args) > 1 else paths.active_project()
    if not name:
        print("no active project — bind one with /hansard:use <name> or pass it explicitly")
        return
    if cmd == "discover":
        for s in discover(name):
            print(json.dumps(s, ensure_ascii=False))
    elif cmd == "mark":
        p = mark(name)
        print(f"manifest stamped: {p}" if p else "mark failed (fail-open, nothing written)")
    elif cmd == "digest":
        d = brief(name)
        if d:
            print(d)
    else:
        print(f"[load:{name}] " + status_text(name))


if __name__ == "__main__":
    try:
        _main()
    except Exception:
        pass
    sys.exit(0)
