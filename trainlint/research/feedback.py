#!/usr/bin/env python3
"""Digest operator feedback captured in the report into classified, actionable insight.

The report records two feedback streams (via "Export memory" -> `viz.py <name> --absorb`):
  comments.<name>.jsonl — 🖍 highlight notes: {id, quote, comment, sec, ts}
  clarify.<name>.jsonl  — chat Q&A:          {dec, q, a, ts, focus?}

This module classifies each NEW item into WHY it was left, so the feedback actually gets used:
  confusion   — the reader didn't understand something -> what to explain / add to the glossary
                or a decision's `plain` field (the report's job is to be understood)
  correction  — the reader says something is WRONG -> what the agent must re-examine in the
                plan/decisions next session (a human-flagged doubt outranks a green metric)
  readability — the report itself reads badly -> the concrete rendering/wording change

Each classified line lands in feedback.<name>.jsonl:
  {src: comment|chat, key, quote, note, kind, insight, action, ts, digested}
Dedupe by (src, key): re-digesting is a no-op. The LLM ladder is shared with viz
(TRAINLINT_REPORT_LLM: kimi|codex|gemini|claude; none/off -> items recorded as 'unclassified'
so capture never blocks on a model). Run directly: python3 feedback.py <project> [digest]
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
import tree   # noqa: E402

CLASSIFY_SYS = (
    "You digest OPERATOR FEEDBACK left on a research status report. For EACH numbered item, "
    "decide WHY the operator left it:\n"
    "- confusion: they did not understand something. insight = what concept/claim lost them; "
    "action = the concrete explanation/glossary/plain-language fix.\n"
    "- correction: they believe something is WRONG or doubtful. insight = what claim/decision "
    "they dispute and what that implies; action = what to re-examine or verify in the plan.\n"
    "- readability: the report itself reads badly (structure, ordering, density, wording). "
    "insight = the readability failure; action = the concrete report change.\n"
    "Judge from the item text; when a note both disputes and asks, prefer correction. "
    "Output STRICT JSON: an array like [{\"i\": 1, \"kind\": \"confusion\", \"insight\": \"…\", "
    "\"action\": \"…\"}] covering every item exactly once. No prose outside the JSON.")


def _feedback_path(name):
    return paths.wfile(f"feedback.{name}.jsonl")


def _rows(path):
    """Parsed dict rows only — foreign junk (valid-JSON non-dicts) must never crash the loop."""
    return [e for e in (tree._load_jsonl(path) if path.exists() else []) if isinstance(e, dict)]


def _existing_keys(name):
    return {(e.get("src"), e.get("key")) for e in _rows(_feedback_path(name))}


def _ckey(cid, note):
    """Comment key carries a hash of the note text, so EDITING a highlight note (same id, new
    text) is a new item to digest — not silently deduped away."""
    import hashlib
    return f"{cid}|{hashlib.sha1((note or '').encode()).hexdigest()[:8]}"


def collect_new(name):
    """(items, records): the not-yet-digested feedback as LLM items + skeleton records.
    Every field is coerced defensively — one malformed line must not poison the whole digest."""
    have = _existing_keys(name)
    items, recs = [], []

    for e in _rows(paths.resolve(f"comments.{name}.jsonl")):
        cid = str(e.get("id") or "")
        note = str(e.get("comment") or "")
        quote = str(e.get("quote") or "")
        key = _ckey(cid, note)
        if not cid or not note or ("comment", key) in have:
            continue
        items.append(_item_text("comment", quote, note))
        recs.append({"src": "comment", "key": key, "quote": quote,
                     "note": note, "ts": str(e.get("ts") or "")})

    for e in _rows(paths.resolve(f"clarify.{name}.jsonl")):
        q = str(e.get("q") or "")
        key = f"{str(e.get('dec') or '')}|{q}"
        if not q or ("chat", key) in have:
            continue
        ctx = str(e.get("focus") or e.get("dec") or "")
        items.append(_item_text("chat", ctx, q))
        recs.append({"src": "chat", "key": key, "quote": ctx[:300],
                     "note": q, "ts": str(e.get("ts") or "")})
    return items, recs


def _item_text(src, quote, note):
    if src == "comment":
        return f"HIGHLIGHT NOTE on “{quote[:220]}” -> operator wrote: “{note}”"
    return f"QUESTION asked at «{quote[:220]}»: “{note}”"


def _classify(items):
    """items -> {index: {kind, insight, action}} via the shared LLM ladder; {} on any failure."""
    prov = os.environ.get("TRAINLINT_REPORT_LLM", "codex").strip().lower()
    if prov in ("", "none", "off", "0", "false", "template"):
        return {}
    try:
        import viz  # lazy: viz.absorb imports this module — avoid a load-time cycle
        user = "Feedback items:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
        raw = viz._llm(prov, CLASSIFY_SYS, user)
        s, e = raw.find("["), raw.rfind("]")
        out = {}
        for row in json.loads(raw[s:e + 1]):
            if isinstance(row, dict) and row.get("kind") in ("confusion", "correction", "readability"):
                out[int(row.get("i", 0)) - 1] = {"kind": row["kind"],
                                                 "insight": str(row.get("insight", "")).strip(),
                                                 "action": str(row.get("action", "")).strip()}
        return out
    except Exception:
        return {}


def digest(name):
    """Classify every new feedback item into feedback.<name>.jsonl — and RE-classify any
    earlier 'unclassified' rows (captured while no model was available), so the fallback never
    becomes permanent. Returns the records touched this run; capture is never dropped.

    The write is a LINE-PRESERVING merge on a fresh read of the file: '#' comments, blank and
    unparseable lines pass through untouched, rows another process appended meanwhile survive,
    and nothing is written at all when this run changed nothing."""
    p = _feedback_path(name)
    items, recs = collect_new(name)
    retry = [r for r in _rows(p) if r.get("kind") == "unclassified"]
    if not recs and not retry:
        return []
    verdicts = _classify(items + [_item_text(str(r.get("src") or ""), str(r.get("quote") or ""),
                                             str(r.get("note") or "")) for r in retry])
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    touched, updated = [], {}
    for i, r in enumerate(recs):
        v = verdicts.get(i, {})
        r.update({"kind": v.get("kind", "unclassified"), "insight": v.get("insight", ""),
                  "action": v.get("action", ""), "digested": now})
        touched.append(r)
    for j, r in enumerate(retry):
        v = verdicts.get(len(recs) + j)
        if v:  # only rewrite a retry row when the model actually classified it
            r.update({"kind": v["kind"], "insight": v["insight"], "action": v["action"],
                      "digested": now})
            updated[(r.get("src"), r.get("key"))] = r
            touched.append(r)
    if not recs and not updated:
        return []  # nothing new, nothing reclassified -> leave the file byte-identical

    raw = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    out, seen = [], set()
    for line in raw:
        st = line.strip()
        if st and not st.startswith("#"):
            try:
                obj = json.loads(st)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                k = (obj.get("src"), obj.get("key"))
                seen.add(k)
                if k in updated:
                    out.append(json.dumps(updated[k], ensure_ascii=False))
                    continue
        out.append(line)
    for r in recs:
        if (r.get("src"), r.get("key")) not in seen:
            out.append(json.dumps(r, ensure_ascii=False))
    tmp = p.with_suffix(".jsonl.tmp")  # write-then-rename: a crash never truncates the capture
    tmp.write_text(("\n".join(out) + "\n") if out else "", encoding="utf-8")
    tmp.replace(p)
    return touched


def summary(name):
    """One-line counts of the digested feedback, for absorb's close-out print."""
    rows = _rows(_feedback_path(name))
    if not rows:
        return "no operator feedback digested yet"
    kinds = {}
    for r in rows:
        kinds[r.get("kind", "?")] = kinds.get(r.get("kind", "?"), 0) + 1
    return ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))


if __name__ == "__main__":
    nm = sys.argv[1] if len(sys.argv) > 1 else None
    if not nm:
        sys.exit("usage: feedback.py <project> — digest new report feedback")
    added = digest(nm)
    for r in added:
        print(f"[{r['kind']:>12}] {r['note'][:70]}")
        if r.get("insight"):
            print(f"               insight: {r['insight'][:100]}")
        if r.get("action"):
            print(f"               action:  {r['action'][:100]}")
    print(f"{len(added)} new item(s) digested -> {_feedback_path(nm).name}  ({summary(nm)})")
