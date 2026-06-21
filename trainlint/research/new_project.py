#!/usr/bin/env python3
"""Scaffold Trainlint for a NEW project — writes template facts/knowledge/log/goal and
sets it active. The mechanism never changes; you only fill these per-project facts.

  python3 new_project.py <name>

Then edit the TODOs (see project.mimo.json / research/facts.mimo.json as worked examples)
and start working — flow.py kicks in (context / hint / viz-on-change / quiz kickoff).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

ACTION_FACTS = {
    "_comment": "PROJECT FACTS for <name>. The rules never change, only this file. See project.mimo.json for a worked example. Fill every TODO; regex fields use JSON-escaped backslashes (\\\\.).",
    "reference_impl": "TODO: your verified reference implementation",
    "frozen_component": "TODO: e.g. your frozen tokenizer / pretrained encoder",
    "good_storage": "TODO: fast, reliable storage path",
    "bad_storage": "TODO: unreliable storage label",
    "launch_re": "sbatch|torchrun|deepspeed |accelerate launch|python\\S*\\s[^|;&]*train",
    "bad_storage_re": "TODO-regex e.g. /slowfs/|/nfs/",
    "data_file_ext_re": "jsonl|json|npy|wav|tar|arrow|bin",
    "locked_configs_re": "deepspeed.*\\.json|ds_config|tokenizer_config\\.json",
    "preproc_trap_re": "TODO-regex: the preprocessing call to watch (e.g. MelSpectrogram\\(|Normalize\\()",
    "preproc_ok_re": "TODO-regex: the correct setting (e.g. power\\s*=\\s*1\\.0)",
    "preproc_example": "TODO: what goes wrong if the preproc doesn't match the frozen component",
    "pad_ood_re": "np\\.zeros",
    "pad_ood_example": "TODO: what your padding/no-op encodes to OOD",
    "project_forward_re": "TODO|forward-logic|symbols|to|escalate-on",
    "forward_example": "TODO: forward/mask/sampling traps specific to this project",
    "target_dist_traps": "TODO: the loss-weight / field traps",
    "config_override_example": "TODO: where config silently overrides",
    "regime_example": "TODO: an hparam that doesn't transfer across regimes",
    "poison_example": "TODO: what makes a ckpt poisoned here",
    "demo_param": "TODO: the key preprocessing param a demo must state",
    "code_align_example": "TODO: custom-vs-reference traps",
    "codec_quirks": "TODO: frozen-component quirks (or leave generic)",
    "eval_region_example": "TODO: a metric hijacked by a trivial majority",
    "eval_crutch_example": "TODO: eval crutches deployment won't have",
    "eval_deploy_example": "TODO: offline-vs-deployment mismatch"
}

RESEARCH_FACTS = {
    "_comment": "Research facts for <name>: how to read directions + progress from this project's traces.",
    "thresholds": {"patience_P": 3, "window_K": 3, "flat_eps": 0.01},
    "runs_glob": "TODO: glob to your run dirs, e.g. /path/to/runs/*",
    "direction_regex": "TODO: regex extracting (lineage)(_knob) from a run dir name",
    "trunk_checks": ["diff-vs-reference", "verify-data-distribution", "trained-enough"],
    "candidate_moves": []
}


def main():
    if len(sys.argv) < 2:
        print("usage: new_project.py <name>")
        sys.exit(2)
    name = sys.argv[1]

    def w(p, s):
        if p.exists():
            print("exists, skip:", p.name)
            return
        p.write_text(s.replace("<name>", name), encoding="utf-8")
        print("wrote:", p.relative_to(ROOT))

    w(ROOT / f"project.{name}.json", json.dumps(ACTION_FACTS, ensure_ascii=False, indent=2))
    w(HERE / f"facts.{name}.json", json.dumps(RESEARCH_FACTS, ensure_ascii=False, indent=2))
    w(HERE / f"knowledge.{name}.jsonl",
      "# papers/refs indexed by the PROBLEM they solve. one JSON object per line.\n"
      "# fields: id | title | problem | concepts[] | prereqs[] | match[] (wall keywords) | read(bool)\n")
    w(HERE / f"log.{name}.jsonl",
      "# durable append-only annotation log (harvested from sessions). starts empty.\n")
    w(HERE / f"goal.{name}.txt", "TODO: one line — what is this project trying to build?\n")
    (ROOT / ".active-project").write_text(name + "\n", encoding="utf-8")
    print(f"\nactive project set to '{name}'. Fill the TODOs, then start working — "
          f"flow.py will kick in (context / hint / viz-on-change / quiz).")


if __name__ == "__main__":
    main()
