#!/usr/bin/env python3
"""H3.D0 research prototype: deterministic dependency-aware context compiler.

Not production code. Standard-library only. It reads a JSON fixture describing blocks and
selects a bounded Context IR without consulting required-evidence labels.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./:-]*|\d+|[^\s]")
CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
DEF_RE = re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
IMPORT_RE = re.compile(r"\b(?:from\s+([A-Za-z0-9_.]+)\s+import|import\s+([A-Za-z0-9_.]+))")
ANCHOR_RE = re.compile(r"\b(?:CONFIG|POLICY|ROUTE|PROFILE|TIMEOUT|RETRY)_[A-Z0-9_]+\b")

def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)

def norm_terms(text: str) -> set[str]:
    return {t.lower() for t in tokens(text) if len(t) >= 3 and (t[0].isalnum() or t[0] == "_")}

def lexical_score(query_terms: set[str], block: dict[str, Any]) -> float:
    bt = norm_terms(block.get("path", "") + "\n" + block.get("content", ""))
    return 0.0 if not query_terms or not bt else len(query_terms & bt) / max(1, len(query_terms))

def build_indices(blocks: list[dict[str, Any]]):
    defs: dict[str, list[int]] = {}; anchors: dict[str, list[int]] = {}; modules: dict[str, list[int]] = {}
    for i, b in enumerate(blocks):
        content = b.get("content", "")
        for d in DEF_RE.findall(content): defs.setdefault(d, []).append(i)
        for a in ANCHOR_RE.findall(content): anchors.setdefault(a, []).append(i)
        modules.setdefault(Path(b.get("path", "")).stem.lower(), []).append(i)
    return defs, anchors, modules

def structural_neighbors(i: int, blocks: list[dict[str, Any]], indices) -> set[int]:
    defs, anchors, modules = indices; content = blocks[i].get("content", ""); out: set[int] = set()
    for c in CALL_RE.findall(content): out.update(defs.get(c, []))
    for a in ANCHOR_RE.findall(content): out.update(anchors.get(a, []))
    for m1, m2 in IMPORT_RE.findall(content): out.update(modules.get((m1 or m2).split(".")[-1].lower(), []))
    out.discard(i); return out

def compile_fixture(data: dict[str, Any], budget_ratio: float = 0.45, seed_ratio: float = 0.20) -> dict[str, Any]:
    blocks = data["blocks"]; raw_tokens = sum(len(tokens(b["content"])) for b in blocks); budget = max(1, int(raw_tokens * budget_ratio))
    task = data["task"]; constraints = list(data.get("hard_constraints", [])); query_terms = norm_terms(task + "\n" + "\n".join(constraints))
    selected: set[int] = set(); reasons: dict[int, list[str]] = {}
    for i, b in enumerate(blocks):
        if b.get("kind") in {"request", "constraint", "error", "test", "api"}:
            selected.add(i); reasons.setdefault(i, []).append("lossless")
    ranked = sorted(range(len(blocks)), key=lambda i: (-lexical_score(query_terms, blocks[i]), blocks[i]["path"]))
    seed_budget = max(1, int(raw_tokens * seed_ratio)); used_seed = 0
    for i in ranked:
        if i in selected: continue
        n = len(tokens(blocks[i]["content"]))
        if used_seed + n > seed_budget and used_seed > 0: continue
        if lexical_score(query_terms, blocks[i]) <= 0: continue
        selected.add(i); reasons.setdefault(i, []).append("lexical_seed"); used_seed += n
    indices = build_indices(blocks); changed = True
    while changed:
        changed = False
        for i in list(selected):
            for j in structural_neighbors(i, blocks, indices):
                if j not in selected:
                    selected.add(j); reasons.setdefault(j, []).append(f"dependency_from:{blocks[i]['path']}"); changed = True
    def priority(i: int):
        rs = reasons.get(i, []); p = 0 if "lossless" in rs else (1 if any(r.startswith("dependency_from:") for r in rs) else 2)
        return (p, -lexical_score(query_terms, blocks[i]), blocks[i]["path"])
    packed: list[int] = []; used = 0
    for i in sorted(selected, key=priority):
        n = len(tokens(blocks[i]["content"])); mandatory = "lossless" in reasons.get(i, [])
        if mandatory or used + n <= budget: packed.append(i); used += n
    for i in ranked:
        if i in packed: continue
        n = len(tokens(blocks[i]["content"]))
        if used + n <= budget and lexical_score(query_terms, blocks[i]) > 0:
            packed.append(i); used += n; reasons.setdefault(i, []).append("lexical_fill")
    packed = sorted(set(packed), key=lambda i: blocks[i]["path"])
    evidence = [{"id": blocks[i]["id"], "path": blocks[i]["path"], "content": blocks[i]["content"], "reason": reasons.get(i, [])} for i in packed]
    omitted = [{"id": b["id"], "path": b["path"]} for i,b in enumerate(blocks) if i not in packed]
    compiled_tokens = sum(len(tokens(x["content"])) for x in evidence) + len(tokens(task)) + sum(len(tokens(c)) for c in constraints)
    return {"task": task, "hard_constraints": constraints, "evidence": evidence, "omitted": omitted, "provenance": {x["id"]: {"path": x["path"], "reason": x["reason"]} for x in evidence}, "stats": {"raw_tokens_proxy": raw_tokens, "compiled_tokens_proxy": compiled_tokens, "reduction_ratio": 1 - compiled_tokens / max(1, raw_tokens)}}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("fixture", type=Path); ap.add_argument("--budget-ratio", type=float, default=0.45); ap.add_argument("--seed-ratio", type=float, default=0.20); ap.add_argument("--out", type=Path); args = ap.parse_args()
    data = json.loads(args.fixture.read_text(encoding="utf-8")); out = compile_fixture(data, args.budget_ratio, args.seed_ratio); s = json.dumps(out, indent=2, ensure_ascii=False)
    args.out.write_text(s + "\n", encoding="utf-8") if args.out else print(s)

if __name__ == "__main__": main()
