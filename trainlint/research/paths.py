#!/usr/bin/env python3
"""Where a PROJECT's data lives — decoupled from the plugin's versioned code dir.

Per-project files (goal / plan / log / focus / pipeline / glossary / facts / knowledge /
motivation / clarify / tag_* / project.<name>.json / .active-project / .state) must NOT sit
under the versioned plugin cache (`.../trainlint/<version>/`), which an upgrade wipes. They live
in a STABLE data dir:

    $TRAINLINT_DATA_DIR                              if set (point it at your own repo to keep the
                                                     project's data WITH the project)
    else ~/.claude/plugins/data/trainlint-trainlint  (Claude Code's persistent plugin-data dir,
                                                     which survives version upgrades)

The plugin's CODE and SHARED files (plan.py, viz.py, quiz.jsonl, principles.jsonl, …) stay in the
plugin — only per-project DATA moves out.

MIGRATION-SAFE: `resolve()` returns the data-dir path if the file is there, else falls back to the
LEGACY in-plugin location, so a half-migrated tree (or an un-updated module) still reads correctly.
WRITES always target the data dir via `wfile()`.
"""
import os
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent          # .../trainlint/<version>/research
_PLUGIN = _RESEARCH.parent                            # .../trainlint/<version>


def data_root() -> Path:
    d = os.environ.get("TRAINLINT_DATA_DIR", "").strip()
    base = Path(d).expanduser() if d else (Path.home() / ".claude" / "plugins" / "data" / "trainlint-trainlint")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base


def resolve(fname: str) -> Path:
    """READ path for a per-project data file: data_root()/fname if it exists, else the legacy
    in-plugin path (research/ then plugin root), else data_root()/fname (a not-yet-created file)."""
    new = data_root() / fname
    if new.exists():
        return new
    for legacy in (_RESEARCH / fname, _PLUGIN / fname):
        if legacy.exists():
            return legacy
    return new


def wfile(fname: str) -> Path:
    """WRITE path — always the data dir. Ensures the parent exists."""
    p = data_root() / fname
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def state_dir() -> Path:
    """Per-project runtime state (progress etc.) — under the data dir, not the plugin."""
    s = data_root() / ".state"
    try:
        s.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return s


def active_project() -> str:
    """The active project name: $HARNESS_PROJECT, else data_root()/.active-project, else the legacy
    plugin-root/.active-project."""
    n = os.environ.get("HARNESS_PROJECT", "").strip()
    if n:
        return n
    for p in (data_root() / ".active-project", _PLUGIN / ".active-project"):
        try:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""
