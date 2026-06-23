#!/usr/bin/env python3
"""Opt-in Haiku judge — a CLASSIFICATION (routing) refinement, NEVER a correctness judge.

Some FP filters are fuzzy for regex: it can't tell a data-pipeline script that `import torch` from
real model-forward code. A small fast model reads the diff and classifies which kind it is. This is
allowed under the design rule — the model only ROUTES/classifies ("which kind of code"), it NEVER
judges whether the code is correct (that stays human, via the escalation it gates).

Opt-in: HARNESS_MODEL=1 + ANTHROPIC_API_KEY. Fail-OPEN: off / unavailable / error / unsure -> returns
False, so the deterministic regex floor stands and recall is never lost. It can only SUPPRESS a
regex false-positive, never add a fire.
"""
import os


def enabled():
    return (os.environ.get("HARNESS_MODEL", "").strip().lower() in ("1", "on", "true")
            and bool(os.environ.get("ANTHROPIC_API_KEY")))


def is_not_model_code(text):
    """True ONLY if the model is enabled and CONFIDENTLY classifies this edit as a data-pipeline /
    config / eval / probe script (not model forward/mask/sampling code). Off / error / 'model code'
    / anything unsure -> False (keep the deterministic fire)."""
    if not enabled() or not text:
        return False
    try:
        import anthropic
        client = anthropic.Anthropic(timeout=8)
        r = client.messages.create(
            model="claude-haiku-4-5", max_tokens=8,
            system=("Classify a code edit with ONE word. MODEL = it edits a neural network's forward / "
                    "attention-mask / sampling / generate logic. OTHER = it is a data-pipeline, "
                    "config/yaml, eval, or probe script that merely mentions those words. Do NOT judge "
                    "whether the code is correct — only classify which kind it is."),
            messages=[{"role": "user", "content": str(text)[:1500]}])
        ans = "".join(getattr(b, "text", "") for b in r.content).strip().upper()
        return ans.startswith("OTHER")
    except Exception:
        return False
