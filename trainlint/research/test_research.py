#!/usr/bin/env python3
"""Tests for the research-lint: tree reconstruction, governor shape, surfacer coupling."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tree
import governor
import surfacer


def main():
    fails = 0

    def check(cond, msg):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        if not cond:
            fails += 1

    facts = tree.load_facts("mimo")
    # build from the durable log only (structured derive degrades to [] off-cluster)
    nodes = tree.build_tree(tree.load_annotations("mimo"), facts)

    check("loss-weights" in nodes, "loss-weights direction reconstructed")
    check(nodes["loss-weights"]["status"] == "stalled",
          f"loss-weights is STALLED (got {nodes['loss-weights']['status']})")
    check(nodes["layout-chunk"]["status"] == "abandoned", "layout-chunk is ABANDONED (backtracked)")
    check(nodes["layout-stream"]["status"] == "deepening", "layout-stream is DEEPENING")
    check(nodes["nofreeze"]["status"] == "deepening", "nofreeze is DEEPENING")

    gov = "\n".join(governor.report(nodes, facts))
    check("树干检查没记录" in gov and "loss-weights" in gov,
          "governor warns 'check trunk before judging stalled branch dead'")
    prescribes = any(p in gov for p in ("建议放弃", "该放弃", "应该放弃", "放弃这", "停掉这"))
    check("未探候选方向" in gov and not prescribes,
          "governor surfaces unexplored moves and never PRESCRIBES abandonment (lint, not prune)")

    know = tree._load_jsonl(Path(__file__).resolve().parent / "knowledge.mimo.jsonl")
    surf = "\n".join(surfacer.report(nodes, know))
    check("frozen-codec" in surf or "context-dependent" in surf,
          "surfacer couples the 351-OOD wall to the frozen-tokenizer entry")
    check("Inner Monologue" in surf, "surfacer couples the 'rambling' wall to Moshi inner-monologue")

    total = 9
    print(f"\n{total - fails}/{total} passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
