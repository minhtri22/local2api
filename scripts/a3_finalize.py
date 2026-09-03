from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
A3 = ROOT / "docs/result/evidence/a3_14b"
CEILING = ROOT / "docs/result/evidence/capability_ceiling_v1"


MANUAL = {
    "CC01": (1, "Generic file descriptions do not trace the actual route/error flow and misstate router.py as path/method routing.", "repo-grounded call-path reasoning failure", False, True, True),
    "CC02": (2, "Useful inspection plan, but it does not localize the likely streaming boundary or reach a concrete evidence-backed fix before truncation.", "cross-module localization remains generic", False, False, True),
    "CC03": (0, "Invents gateway-service-config.yaml, gateway-service.py and router-config.yaml despite the explicit no-invention constraint.", "fabricated files/APIs", True, True, True),
    "CC04": (1, "Falls back to generic rate-limit/service-load hypotheses instead of the supplied 429->503 code-path evidence and smallest patch location.", "insufficient repo-specific diagnosis", False, False, True),
    "CC05": (2, "Correctly identifies loss of status/headers and begins streaming impact, but the capped answer omits several required consumers such as health/tests and full dependency impact.", "major dependency omissions", False, False, True),
    "CC06": (4, "Correctly separates what can and cannot be concluded from one 500 with no logs and asks for evidence before code changes.", "minor incompleteness only", False, False, False),
    "CC07": (2, "Prioritizes router.py/chat.py/http.py correctly but invents auth.py while the prompt did not provide that file summary.", "wrong-file invention under incomplete context", True, True, True),
    "CC08": (2, "Preserves several invariants but broadens the no-local-fallback rule to all tasks, violating the narrower architecture-task constraint.", "competing-constraint loss", True, False, False),
    "CC09": (2, "Provides a generic migration plan but invents registry CRUD/security work and does not reach the required concrete rollback/preservation plan within the cap.", "repo-wide planning too generic", False, True, True),
    "CC10": (0, "Explicit adversarial failure: claims it can verify OAuth refresh logic in unseen config.py when the prompt says the file was not shown.", "hallucinated verification", True, True, False),
    "CC11": (2, "Names the major components but remains generic and does not finish the degradable/non-degradable final HTTP semantics requested.", "incomplete failure-semantics reasoning", False, False, True),
    "CC12": (3, "Covers request schema, token budgeting, backend switching, retries and observability; privacy and deeper failure boundaries are incomplete under the cap.", "minor-to-moderate impact omissions", False, False, True),
    "CC13": (2, "Three-commit structure is plausible but suggests optional new endpoints and does not firmly enforce backend-session independence across the sequence.", "constraint retention incomplete", True, False, True),
    "CC14": (4, "Correctly refuses to fabricate an absent diff, states the blocker and gives the appropriate general next step.", "minor wording imprecision only", False, False, False),
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    results_path = CEILING / "ceiling_suite_results_14b.json"
    results = load(results_path)
    audit_rows = []
    total = 0
    for case in results["cases"]:
        task_id = case["task_id"]
        score, rationale, failure, constraint, hallucination, missing = MANUAL[task_id]
        case["mechanical_score_0_5"] = case.get("mechanical_score_0_5", case.pop("score_0_5", None))
        case["final_manual_score_0_5"] = score
        case["manual_rationale"] = rationale
        case["main_failure"] = failure
        case["manual_constraint_violation"] = constraint
        case["manual_hallucination"] = hallucination
        case["manual_wrong_file_attribution"] = hallucination and task_id in {"CC03", "CC07", "CC10"}
        case["manual_missing_dependency"] = missing
        total += score
        audit_rows.append({
            "task_id": task_id,
            "category": case["category"],
            "mechanical_score": case["mechanical_score_0_5"],
            "final_manual_score": score,
            "manual_rationale": rationale,
            "main_failure": failure,
            "constraint_violation": constraint,
            "hallucination": hallucination,
            "wrong_file_attribution": case["manual_wrong_file_attribution"],
            "missing_dependency": missing,
        })
    results["mechanical_score"] = results.get("mechanical_score", results.pop("score", None))
    results["mechanical_mean"] = results.get("mechanical_mean", results.pop("mean", None))
    results["final_manual_score"] = total
    results["final_manual_mean"] = total / len(results["cases"])
    results["suite_frozen"] = True
    results["freeze_reason"] = "14 cases expose multiple concrete 14B failure modes; prompts were not changed after observing results."
    save(results_path, results)
    save(CEILING / "manual_review.json", {
        "schema": "local2api.capability_ceiling.v1.manual_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rubric": results["rubric"],
        "cases": audit_rows,
        "mechanical_total": results["mechanical_score"],
        "manual_total": total,
        "max_score": results["max_score"],
        "manual_mean": results["final_manual_mean"],
        "suite_frozen": True,
    })

    suite = load(CEILING / "suite_definition.json")
    suite["frozen"] = True
    suite["frozen_at"] = datetime.now(timezone.utc).isoformat()
    suite["freeze_rule"] = "Future candidates must use these exact prompts, fixtures and rubric; no candidate-specific tuning."
    save(CEILING / "suite_definition.json", suite)

    save(A3 / "failure_recovery_audit.json", {
        "schema": "local2api.a3.failure_recovery_audit.v1",
        "runtime_unavailable": {"status": "PASS", "evidence": "Existing gateway fake-backend tests return 503 and prohibit unsafe fallback for non-degradable tasks."},
        "wrong_backend_port": {"status": "PASS", "evidence": "A3 wrong-port probe timed out and produced no false success."},
        "request_timeout": {"status": "PARTIAL", "evidence": "Timeout path observed through wrong-port probe and adapter normalization; no dedicated live slow-upstream injector."},
        "model_not_loaded": {"status": "PARTIAL", "evidence": "Cold unload/reload lifecycle succeeded; an invalid/missing model identifier was not injected."},
        "malformed_upstream_response": {"status": "NOT TESTED", "evidence": "No safe malformed-response injection point was exercised against live Ollama."},
        "connection_reset": {"status": "NOT TESTED", "evidence": "No destructive live connection-reset injector was used; only generic transport-error handling is covered by software tests."},
        "restart_behavior": {"status": "PARTIAL", "evidence": "Unload/reload recovery succeeded outside an active generation; restart-during-request was not executed."},
    })

    save(A3 / "local_capability_profile.json", {
        "schema": "local2api.local_capability_profile.v1",
        "model_tier": "local-standard",
        "model": "Qwen2.5-Coder-14B-Instruct Q4_K_M",
        "production_status": "14B_PRODUCTION_READY_WITH_LIMITS",
        "quality_baseline": {"local_safe": "8/9", "local_acceptable": "9/11", "total": "17/20"},
        "recommended_context_tokens": 4096,
        "soft_context_ceiling": 8192,
        "hard_context_ceiling": 12288,
        "recommended_max_output_tokens": 256,
        "hard_output_ceiling": 512,
        "recommended_max_concurrency": 1,
        "expected_ttft_range_ms": [17000, 60000],
        "soft_ceiling_ttft_ms_observed": 141975,
        "expected_decode_tps_range": [4.6, 5.3],
        "minimum_free_ram_gib_before_load": 8,
        "recommended_free_ram_gib_before_load": 10,
        "ram_contract_note": "Conservative pre-load contract inferred from successful loaded runs with roughly 5.5-8.5 GiB available RAM; exact pre-load failure threshold is NOT PROVEN.",
        "runtime": "Ollama 0.33.2",
        "accelerator": "Intel Arc 140V / Vulkan",
        "arc_vulkan_verified": True,
        "supported_task_classes": [
            "short code explanation and review",
            "small bounded edits",
            "unit-test generation",
            "bounded bug localization",
            "2-3 file reasoning with supplied context",
            "diff summary and structured extraction",
            "short repository questions",
        ],
        "cloud_preferred_task_classes": [
            "repository-wide or architecture-wide refactors",
            "ambiguous multi-module debugging",
            "long-horizon agentic repair loops",
            "contexts above 8K tokens",
            "tasks requiring strong multi-turn constraint retention without gateway reconstruction",
            "security-critical decisions from incomplete evidence",
        ],
        "known_limitations": [
            "multi-turn consistency gate passed only 2/5 sessions",
            "realistic context TTFT rises from about 35 s at 2K to 142 s at 8K and 390 s at 12K",
            "concurrency 2 technically completes but serializes/starves one request and increases group latency",
            "manual Ceiling Suite exposes hallucinated files/evidence and weak repo-grounded multi-file reasoning",
            "thermal, package power and practical editor/browser responsiveness are NOT PROVEN",
        ],
        "context_ownership_required": True,
        "fallback_policy": "Use local only inside this capability envelope. Non-degradable or cloud-preferred tasks must not silently fall back to 14B when their required capability is unavailable.",
        "dense_32b_status": "BLOCKED",
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
