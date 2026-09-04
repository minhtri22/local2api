#!/usr/bin/env python3
"""H3.D1-R corrected payload preparation: same canonical corpus for RAW and COMPILED.

Research-only; does not call any cloud service.
"""
from __future__ import annotations
import hashlib, importlib.util, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/result/evidence/h3_d1_r"
SKILL = ROOT / "skills/local-context-compiler/SKILL.md"
SOURCE_SUFFIXES = {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".example"}
EXCLUDE_PARTS = {".git", ".venv", "models", "docs/result/evidence", ".pytest_cache", ".research", "tests/h3_d1", "tests/h3_d1_r"}


def load_compiler():
    p = ROOT / "scripts/context_compile.py"
    spec = importlib.util.spec_from_file_location("h3_context_compile", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def eligible(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(x in rel for x in EXCLUDE_PARTS):
        return False
    return path.is_file() and (path.suffix.lower() in SOURCE_SUFFIXES or path.name in {"README.md", "plan.md", ".env.example"})


def make_corpus(task: dict) -> list[dict]:
    """Build the canonical source corpus C for a task."""
    focus = set(task.get("focus_paths", []))
    blocks = [
        {"id": f"REQ-{task['id']}", "path": "@request", "kind": "request", "content": task["task"]},
    ]
    for i, c in enumerate(task.get("hard_constraints", []), 1):
        blocks.append({"id": f"CON-{task['id']}-{i}", "path": f"@constraint/{i}", "kind": "constraint", "content": c})
    paths = sorted(p for p in ROOT.rglob("*") if eligible(p))
    for p in paths:
        rel = p.relative_to(ROOT).as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # Match RAW payload: only include src/, tests/ (original), docs/, README, plan, pyproject, .env
        if not (rel.startswith("src/") or rel.startswith("tests/") or rel.startswith("docs/") or rel in {"README.md", "plan.md", "pyproject.toml", ".env.example"}):
            continue
        kind = "code" if p.suffix == ".py" else "doc"
        if rel.startswith("tests/") and not rel.startswith("tests/h3_d1"):
            kind = "test"
        if rel in focus and kind == "doc":
            kind = "api" if "index" in rel or rel == "README.md" else kind
        blocks.append({"id": "FILE:" + rel, "path": rel, "kind": kind, "content": text})
    return blocks


def corpus_hash(blocks: list[dict]) -> str:
    """Deterministic SHA256 of the canonical corpus content."""
    h = hashlib.sha256()
    for b in sorted(blocks, key=lambda x: x["id"]):
        h.update(b["id"].encode())
        h.update(b["path"].encode())
        h.update(b["kind"].encode())
        h.update(b["content"].encode())
    return h.hexdigest()


def tokens(text: str) -> list[str]:
    """Same tokenization as compiler for proxy counts."""
    return re.findall(r"[A-Za-z_][A-Za-z0-9_./:-]*|\d+|[^\s]", text)


def raw_prompt(task: dict, blocks: list[dict]) -> str:
    """RAW prompt: task + constraints + entire corpus (excluding request/constraint blocks)."""
    files = [b for b in blocks if b["path"].startswith(("src/", "tests/", "docs/", "README", "plan", "pyproject", ".env"))]
    return (
        "[TASK]\n" + task["task"] +
        "\n\n[HARD CONSTRAINTS]\n" + "\n".join("- " + c for c in task.get("hard_constraints", [])) +
        "\n\n[RAW REPOSITORY CONTEXT]\n" + "\n\n".join(f"--- {b['path']} ---\n{b['content']}" for b in files)
    )


def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def skill_overhead_tokens() -> int:
    """Count tokens in the skill instruction overhead."""
    return len(tokens(skill_text()))


def compiled_prompt(task: dict, ir: dict, skill_overhead: int) -> tuple[str, int]:
    """COMPILED prompt: skill + task + constraints + selected evidence only."""
    ev_lines = []
    for e in ir["evidence"]:
        ev_lines.append(f"--- {e['path']} ---\n{e['content']}")
    evidence_text = "\n\n".join(ev_lines)
    compiled_total = (
        "[LOCAL CONTEXT COMPILER POLICY]\n" + skill_text() +
        "\n\n[TASK]\n" + task["task"] +
        "\n\n[HARD CONSTRAINTS]\n" + "\n".join("- " + c for c in task.get("hard_constraints", [])) +
        "\n\n[SELECTED EVIDENCE]\n" + evidence_text
    )
    evidence_tokens = len(tokens(evidence_text))
    return compiled_total, evidence_tokens


def main():
    compiler = load_compiler()
    tasks_doc = json.loads((ROOT / "docs/result/evidence/h3_d1/frozen_tasks.json").read_text(encoding="utf-8"))
    skill = skill_text()
    skill_oh = skill_overhead_tokens()

    raw_dir = EVIDENCE / "raw_payloads"
    comp_dir = EVIDENCE / "compiled_payloads"
    ir_dir = EVIDENCE / "context_ir"
    corp_dir = EVIDENCE / "corpora"
    raw_dir.mkdir(parents=True, exist_ok=True)
    comp_dir.mkdir(parents=True, exist_ok=True)
    ir_dir.mkdir(parents=True, exist_ok=True)
    corp_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for task in tasks_doc["tasks"]:
        # Build ONE canonical corpus
        corpus = make_corpus(task)
        c_hash = corpus_hash(corpus)

        # Save corpus hash for audit
        (corp_dir / f"{task['id']}.hash").write_text(c_hash + "\n", encoding="utf-8")

        # Run frozen compiler over the SAME corpus
        fixture = {"task": task["task"], "hard_constraints": task.get("hard_constraints", []), "blocks": corpus}
        ir = compiler.compile_fixture(fixture, budget_ratio=0.45, seed_ratio=0.20)

        # Build payloads from SAME corpus
        rp = raw_prompt(task, corpus)
        cp, evidence_toks = compiled_prompt(task, ir, skill_oh)

        raw_payload = {"messages": [{"role": "user", "content": rp}], "temperature": 0.2}
        comp_payload = {"messages": [{"role": "user", "content": cp}], "temperature": 0.2}

        (raw_dir / f"{task['id']}.json").write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (comp_dir / f"{task['id']}.json").write_text(json.dumps(comp_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (ir_dir / f"{task['id']}.json").write_text(json.dumps(ir, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        raw_n = len(tokens(rp))
        comp_total_n = len(tokens(cp))
        reduction = 1 - comp_total_n / max(1, raw_n)

        rows.append({
            "task_id": task["id"],
            "corpus_sha256": c_hash,
            "raw_proxy_tokens": raw_n,
            "compiled_evidence_proxy_tokens": evidence_toks,
            "skill_overhead_proxy_tokens": skill_oh,
            "compiled_total_proxy_tokens": comp_total_n,
            "reduction_ratio": reduction,
            "selected_file_count": len(ir["evidence"]),
            "raw_file_count": len([b for b in corpus if b["path"].startswith(("src/", "tests/", "docs/", "README", "plan", "pyproject", ".env"))]),
        })

    reductions = sorted(r["reduction_ratio"] for r in rows)
    median = reductions[len(reductions) // 2] if reductions else None

    # Count tasks meeting thresholds
    tasks_ge_20 = sum(1 for r in rows if r["reduction_ratio"] >= 0.20)
    tasks_compiled_gt_raw_10 = sum(1 for r in rows if r["compiled_total_proxy_tokens"] > r["raw_proxy_tokens"] * 1.10)

    preflight = {
        "schema": "local2api.h3_d1_r.preflight.v1",
        "source_commit": tasks_doc["source_commit"],
        "task_count": len(rows),
        "token_measure": "deterministic lexical proxy; not billing tokens",
        "median_reduction_ratio": median,
        "tasks_ge_20pct_reduction": tasks_ge_20,
        "tasks_compiled_gt_raw_10pct": tasks_compiled_gt_raw_10,
        "skill_overhead_proxy_tokens": skill_oh,
        "rows": rows,
        "cloud_executed": False,
        "preflight_gate": {
            "median_reduction_ge_30pct": median >= 0.30 if median is not None else False,
            "at_least_9_tasks_ge_20pct": tasks_ge_20 >= 9,
            "no_task_compiled_gt_raw_10pct": tasks_compiled_gt_raw_10 == 0,
        }
    }

    (EVIDENCE / "preflight.json").write_text(json.dumps(preflight, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    gate = preflight["preflight_gate"]
    passed = all(gate.values())
    print(json.dumps({
        "task_count": len(rows),
        "median_reduction_ratio": median,
        "tasks_ge_20pct": tasks_ge_20,
        "tasks_compiled_gt_raw_10pct": tasks_compiled_gt_raw_10,
        "preflight_passed": passed,
        "gate_details": gate
    }, indent=2))


if __name__ == "__main__":
    main()