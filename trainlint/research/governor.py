#!/usr/bin/env python3
"""Directionality lint (inward) — shows the search SHAPE, never prescribes.

It surfaces, per notable branch: status, spend, recent marginal gains, walls hit,
explored siblings, missing trunk-checks, and the unexplored candidate moves. It NEVER
says "abandon" — research is non-monotonic; a plateau can precede a breakthrough.
Coach-only: correct the biases of unsupervised search (sunk-cost over-DFS, novelty
over-BFS) with INFORMATION, not control. The judgment stays with the agent.
"""


def report(nodes, facts):
    facts = facts or {}
    K = facts.get("thresholds", {}).get("window_K", 3)
    trunk_required = facts.get("trunk_checks", [])
    candidates = set(facts.get("candidate_moves", []))
    explored = set(nodes.keys())
    hints = []

    for n in sorted(nodes.values(), key=lambda x: -x["spend"]):
        if n["status"] == "open":          # only a wall, no experiments yet — nothing to shape
            continue
        deltas = n["deltas"][-K:]
        line = (f"〔research-lint·方向性〕[{n['direction']}] 状态={n['status']} · 跑了{n['spend']}次"
                + (f" · 近{len(deltas)}次增益{deltas}" if deltas else "")
                + (f" · 撞墙{n['walls']}" if n["walls"] else ""))
        if n["status"] == "stalled":
            missing = [c for c in trunk_required if c not in n["trunk"]]
            if missing:
                line += (f" · ⚠平了,但树干检查没记录{missing}——"
                         f"别在可能被污染的树干上判这支死(根因也许不在这条枝)")
        if n["siblings"]:
            line += f" · 同层已探{n['siblings']}"
        hints.append(line)

    unexplored = sorted(candidates - explored)
    if unexplored:
        hints.append(f"〔research-lint·方向性〕未探候选方向:{unexplored}")
    hints.append("(以上是搜索现状,判断在你——lint 只照形状,不替你剪枝。)")
    return hints
