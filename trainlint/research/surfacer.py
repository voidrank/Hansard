#!/usr/bin/env python3
"""Readiness lint (outward) — just-in-time knowledge, gated by your frontier.

It takes the WALLS in the tree (problems you've actually hit) and matches them against
a knowledge library (papers/refs indexed by the PROBLEM they solve + prerequisites).
It surfaces "this may be readable now" — because external knowledge becomes meaningful
only once your own search reaches the matching frontier. Trigger = a wall, NOT recency.
Coach-only: it hints; it never makes you read anything.

A wall is a DUAL signal: the governor's stop-shape AND this surfacer's unlock key.
"""


def report(nodes, knowledge):
    walls = [(n["direction"], w) for n in nodes.values() for w in n.get("walls", [])]
    hints = []
    for direction, w in walls:
        for k in knowledge:
            if k.get("read"):
                continue
            keys = k.get("match", [])
            if any(str(kk).lower() in w.lower() for kk in keys):
                hints.append(
                    f"〔research-lint·就绪〕墙「{w}」(@{direction}) ↔ 「{k['title']}」"
                    f"——讲的就是 {k.get('problem', '')};前置 {k.get('prereqs', [])} 你大概已具备,"
                    f"也许现在读得懂(早读=cargo-cult)。")
    if not hints:
        hints.append("〔research-lint·就绪〕当前的墙暂未匹配到知识库条目(撞到新墙时再看)。")
    return hints
