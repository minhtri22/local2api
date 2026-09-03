#!/usr/bin/env python3
"""Prepare frozen H3.D1 RAW/COMPILED payloads from the real local2api repository.
Research-only; does not call any cloud service.
"""
from __future__ import annotations
import importlib.util, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/result/evidence/h3_d1"
SKILL = ROOT / "skills/local-context-compiler/SKILL.md"
SOURCE_SUFFIXES = {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".example"}
EXCLUDE_PARTS = {".git", ".venv", "models", "docs/result/evidence"}


def load_compiler():
    p = ROOT / "scripts/context_compile.py"
    spec = importlib.util.spec_from_file_location("h3_context_compile", p)
    mod = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)
    return mod


def eligible(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(x in rel for x in EXCLUDE_PARTS): return False
    return path.is_file() and (path.suffix.lower() in SOURCE_SUFFIXES or path.name in {"README.md","plan.md",".env.example"})


def make_blocks(task: dict) -> list[dict]:
    focus = set(task.get("focus_paths", []))
    blocks = [
        {"id": f"REQ-{task['id']}", "path": "@request", "kind": "request", "content": task["task"]},
    ]
    for i,c in enumerate(task.get("hard_constraints", []),1):
        blocks.append({"id":f"CON-{task['id']}-{i}","path":f"@constraint/{i}","kind":"constraint","content":c})
    paths = sorted(p for p in ROOT.rglob("*") if eligible(p))
    for p in paths:
        rel = p.relative_to(ROOT).as_posix()
        try: text = p.read_text(encoding="utf-8")
        except Exception: continue
        # Keep real repository files whole in D1-S. The compiler may select/omit at file granularity.
        kind = "code" if p.suffix == ".py" else "doc"
        if rel.startswith("tests/"): kind = "test"
        if rel in focus and kind == "doc": kind = "api" if "index" in rel or rel == "README.md" else kind
        blocks.append({"id":"FILE:"+rel,"path":rel,"kind":kind,"content":text})
    return blocks


def raw_prompt(task: dict, blocks: list[dict]) -> str:
    files = [b for b in blocks if b["path"].startswith(("src/","tests/","docs/","README","plan","pyproject",".env"))]
    return task["task"] + "\n\nHARD CONSTRAINTS:\n" + "\n".join("- "+c for c in task.get("hard_constraints",[])) + "\n\nREPOSITORY CONTEXT:\n" + "\n\n".join(f"### {b['path']}\n{b['content']}" for b in files)


def compiled_prompt(task: dict, ir: dict, skill_text: str) -> str:
    ev = "\n\n".join(f"### {e['path']}\n{e['content']}" for e in ir["evidence"])
    return "LOCAL CONTEXT COMPILER POLICY:\n" + skill_text + "\n\nTASK (verbatim):\n" + task["task"] + "\n\nHARD CONSTRAINTS (verbatim):\n" + "\n".join("- "+c for c in task.get("hard_constraints",[])) + "\n\nCOMPILED EVIDENCE WITH PROVENANCE:\n" + ev


def main():
    compiler = load_compiler(); tasks_doc = json.loads((EVIDENCE/"frozen_tasks.json").read_text(encoding="utf-8")); skill = SKILL.read_text(encoding="utf-8")
    raw_dir = EVIDENCE/"raw_payloads"; comp_dir = EVIDENCE/"compiled_payloads"; ir_dir = EVIDENCE/"context_ir"; raw_dir.mkdir(parents=True,exist_ok=True); comp_dir.mkdir(parents=True,exist_ok=True); ir_dir.mkdir(parents=True,exist_ok=True)
    rows=[]
    for task in tasks_doc["tasks"]:
        fixture={"task":task["task"],"hard_constraints":task.get("hard_constraints",[]),"blocks":make_blocks(task)}
        ir=compiler.compile_fixture(fixture,budget_ratio=0.45,seed_ratio=0.20)
        rp=raw_prompt(task,fixture["blocks"]); cp=compiled_prompt(task,ir,skill)
        raw_payload={"messages":[{"role":"user","content":rp}],"temperature":0}
        comp_payload={"messages":[{"role":"user","content":cp}],"temperature":0}
        (raw_dir/f"{task['id']}.json").write_text(json.dumps(raw_payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        (comp_dir/f"{task['id']}.json").write_text(json.dumps(comp_payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        (ir_dir/f"{task['id']}.json").write_text(json.dumps(ir,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        raw_n=len(compiler.tokens(rp)); comp_n=len(compiler.tokens(cp)); rows.append({"id":task["id"],"raw_proxy_tokens":raw_n,"compiled_proxy_tokens":comp_n,"reduction_ratio":1-comp_n/max(1,raw_n),"compiler_stats":ir["stats"]})
    reductions=sorted(r["reduction_ratio"] for r in rows); median=reductions[len(reductions)//2] if reductions else None
    preflight={"schema":"local2api.h3_d1.preflight.v1","source_commit":tasks_doc["source_commit"],"task_count":len(rows),"token_measure":"deterministic lexical proxy; not billing tokens","median_payload_reduction_ratio":median,"rows":rows,"cloud_executed":False}
    (EVIDENCE/"preflight.json").write_text(json.dumps(preflight,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"task_count":len(rows),"median_payload_reduction_ratio":median},indent=2))

if __name__ == "__main__": main()
