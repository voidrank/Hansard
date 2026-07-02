#!/usr/bin/env python3
"""Bind THIS session to a project — the explicit-switch half of session-project-lock.

  python3 use.py <name> [--home DIR]

Sticky + explicit: a session stays on whatever it's bound to until you run this again (or
/trainlint:plan <other>). No cwd auto-switch [switch-semantics]. It does three things:
  1. stamps the project's `home` (= --home, else its existing home, else cwd) — the context->project
     link [project-home-field];
  2. writes the per-session lock data_root()/sessions/<session_id>.json [session-lock-store], keyed by
     the session id from $CLAUDE_CODE_SESSION_ID (the CLI exposes it, so a plain script can bind);
  3. TRANSITIONAL during cutover: also sets the old global .active-project, so /use takes effect NOW
     under the not-yet-rewired resolver. This write is removed in the final remove-global cut — until
     then it's the fallback that keeps every project resolvable [remove-global rollout order].
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paths  # noqa: E402


def bind(name, home=None, session_id=None):
    """Bind `name` to this session. Returns (ok, message). Fail-soft: reports what it couldn't do
    rather than raising."""
    if not name:
        return False, "usage: use.py <name> [--home DIR]"
    # the project must exist (registered) — /use switches to an EXISTING project, it doesn't create one
    if not paths.resolve(f"project.{name}.json").exists():
        return False, (f"no project '{name}' — register it with /trainlint:plan first "
                       f"(nothing to switch to)")
    home = (home or paths.project_home(name) or os.getcwd())
    paths.set_project_home(name, home)
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    lock = paths.write_session_lock(sid, name, home=home, bound_by="use") if sid else None
    # transitional global write (removed in remove-global) so the current resolver picks it up now
    try:
        paths.wfile(".active-project").write_text(name + "\n", encoding="utf-8")
    except Exception:
        pass
    where = ("this session (%s)" % sid[:8]) if sid else "the global pointer (no session id in env)"
    return True, (f"bound '{name}' -> {where}\n  home: {home}"
                  + ("" if lock else "\n  (no CLAUDE_CODE_SESSION_ID; wrote the transitional global only)"))


def main():
    args = sys.argv[1:]
    home = None
    if "--home" in args:
        i = args.index("--home")
        home = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
    name = args[0] if args else None
    ok, msg = bind(name, home=home)
    print(msg)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
