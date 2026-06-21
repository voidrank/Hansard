#!/usr/bin/env python3
"""Visualize the search tree + knowledge coupling — ANY TIME, on demand.

  python3 viz.py [project]

Always prints an ASCII tree (zero deps). Also writes a Graphviz .dot of the search tree
with the knowledge-readiness edges (wall -> paper) overlaid, and renders a .png if
graphviz `dot` is installed. The full picture lives here so the SessionStart lint can
stay a one-line hint (see lint.py --brief).
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tree  # noqa: E402

ICON = {"open": "·", "deepening": "▸", "stalled": "⚠", "abandoned": "✗", "won": "★"}
FILL = {"open": "#dddddd", "deepening": "#9ec5fe", "stalled": "#ffd43b",
        "abandoned": "#ffc9c9", "won": "#69db7c"}


def _esc(s):
    return str(s).replace('"', "'").replace("\n", " ")


def ascii_tree(nodes, facts):
    trunk_req = facts.get("trunk_checks", [])
    by_parent = {}
    for n in nodes.values():
        by_parent.setdefault(n.get("parent"), []).append(n)
    out = []
    for parent in sorted(by_parent, key=lambda x: (x is None, str(x))):
        out.append(f"{parent or '(root)'}")
        kids = sorted(by_parent[parent], key=lambda n: n["direction"])
        for i, n in enumerate(kids):
            br = "└─" if i == len(kids) - 1 else "├─"
            extra = []
            g = n["deltas"][-3:]
            if g:
                extra.append(f"gains{g}")
            if n["walls"]:
                extra.append(f"walls:{len(n['walls'])}")
            if n["status"] == "stalled" and any(c not in n["trunk"] for c in trunk_req):
                extra.append("trunk-unchecked")
            out.append(f"  {br} {ICON.get(n['status'], '?')} {n['direction']:<16} "
                       f"[{n['status']}] {n['spend']}run  " + "  ".join(extra))
    return "\n".join(out)


def knowledge_block(nodes, knowledge):
    walls = [(d, w) for d, n in nodes.items() for w in n.get("walls", []) for d in [n["direction"]]]
    out = ["", "knowledge readiness (wall -> paper you could read now):"]
    hit = False
    for direction, w in {(d, w) for d, w in [(n["direction"], w) for n in nodes.values() for w in n.get("walls", [])]}:
        for k in knowledge:
            if any(str(m).lower() in w.lower() for m in k.get("match", [])):
                hit = True
                out.append(f"  ⟂ [{direction}] \"{w[:40]}\"  ->  {k['title']}")
    if not hit:
        out.append("  (no wall matches a library entry yet)")
    return "\n".join(out)


def dot(nodes, knowledge):
    # portrait (top-down) + larger fonts + high dpi → legible on a phone screen
    L = ["digraph search {",
         '  graph [rankdir=TB, bgcolor=white, dpi=170, ranksep=0.5, nodesep=0.3, margin=0.2];',
         '  node [shape=box, style="filled,rounded", fontname="Helvetica-Bold", fontsize=14, margin="0.12,0.07"];',
         '  edge [fontname=Helvetica, fontsize=11];']
    for d, n in nodes.items():
        lbl = f"{d}\\n[{n['status']}] {n['spend']}run"
        if n["deltas"][-3:]:
            lbl += f"\\ngains {n['deltas'][-3:]}"
        L.append(f'  "{d}" [label="{lbl}", fillcolor="{FILL.get(n["status"], "#eee")}"];')
        if n.get("parent"):
            L.append(f'  "{n["parent"]}" -> "{d}";')
    wi = 0
    for n in nodes.values():
        for w in n.get("walls", []):
            wn = f"wall{wi}"
            wi += 1
            L.append(f'  "{wn}" [label="WALL\\n{_esc(w[:34])}", shape=note, fillcolor="#ffe066"];')
            L.append(f'  "{n["direction"]}" -> "{wn}" [style=dotted, arrowhead=none];')
            for k in knowledge:
                if any(str(m).lower() in w.lower() for m in k.get("match", [])):
                    kn = "kn_" + k["id"]
                    L.append(f'  "{kn}" [label="READ?\\n{_esc(k["title"][:30])}", shape=ellipse, fillcolor="#b2f2bb"];')
                    L.append(f'  "{wn}" -> "{kn}" [style=dashed, label="ready"];')
    L.append("}")
    return "\n".join(L)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    name = tree._active(args[0] if args else None)
    facts = tree.load_facts(name)
    nodes = tree.build_tree(tree.load_events(name, facts), facts)
    know = tree._load_jsonl(Path(__file__).resolve().parent / f"knowledge.{name}.jsonl")

    print(f"# search tree ({name}) — {len(nodes)} directions  "
          f"[· open  ▸ deepening  ⚠ stalled  ✗ abandoned  ★ won]\n")
    print(ascii_tree(nodes, facts))
    print(knowledge_block(nodes, know))

    outdir = Path(__file__).resolve().parent / "viz"
    outdir.mkdir(exist_ok=True)
    dotp = outdir / f"{name}.dot"
    dotp.write_text(dot(nodes, know), encoding="utf-8")
    print(f"\nDOT: {dotp}")
    if shutil.which("dot"):
        png = outdir / f"{name}.png"
        try:
            subprocess.run(["dot", "-Tpng", str(dotp), "-o", str(png)], check=True,
                           capture_output=True)
            print(f"PNG: {png}")
        except Exception as e:
            print(f"(graphviz render failed: {e})")
    else:
        print("(install graphviz `dot` for a PNG, or paste the .dot into any Graphviz viewer)")


if __name__ == "__main__":
    main()
