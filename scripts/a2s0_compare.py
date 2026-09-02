from __future__ import annotations

import json
from pathlib import Path

GIB = 1024**3
SSD_MIB_S = 2495.92
SSD_B_S = SSD_MIB_S * 1024**2
MODEL_BUDGET_GIB = 21.0


def kv_gib(layers: int, kv_heads: int, head_dim: int, tokens: int, bytes_per_elem: float = 2.0) -> float:
    return 2 * layers * kv_heads * head_dim * tokens * bytes_per_elem / GIB


def qwen3_moe(name: str, total_b: float, active_b: float, q4_gb: float, experts: int, topk: int,
              moe_layers: int = 48, attention_layers: int = 48, hidden: int = 2048,
              expert_ff: int = 768, kv_heads: int = 4, head_dim: int = 128) -> dict:
    routed_b = 3 * hidden * expert_ff * experts * moe_layers / 1e9
    active_expert_b = routed_b * topk / experts
    always_b = max(active_b - active_expert_b, 0.0)
    routed_fraction = routed_b / total_b
    active_expert_gb = q4_gb * routed_fraction * topk / experts
    always_gb = q4_gb * (1.0 - routed_fraction)
    return {
        "name": name,
        "kind": "sparse_moe",
        "total_params_b": total_b,
        "active_params_b": active_b,
        "always_active_params_b_est": round(always_b, 3),
        "routed_expert_params_b_calc": round(routed_b, 3),
        "active_routed_params_b_calc": round(active_expert_b, 3),
        "experts": experts,
        "experts_per_token": topk,
        "q4_artifact_gb": q4_gb,
        "always_active_weight_gb_est": round(always_gb, 3),
        "active_expert_weight_gb_per_token_est": round(active_expert_gb, 3),
        "kv_f16_gib": {str(k): round(kv_gib(attention_layers, kv_heads, head_dim, k), 4) for k in (1024, 4096, 8192, 16384)},
        "fits_21gib_weight_budget": q4_gb / (1024**3 / 1e9) <= MODEL_BUDGET_GIB,
        "no_cache_io_ceiling_tok_s": round(SSD_B_S / (active_expert_gb * 1e9), 3),
    }


def dense(name: str, total_b: float, q4_gib: float, layers: int, kv_heads: int = 8, head_dim: int = 128) -> dict:
    return {
        "name": name,
        "kind": "dense_control",
        "total_params_b": total_b,
        "active_params_b": total_b,
        "q4_artifact_gib_est": q4_gib,
        "always_active_weight_gib_est": q4_gib,
        "active_expert_weight_gb_per_token_est": 0.0,
        "kv_f16_gib": {str(k): round(kv_gib(layers, kv_heads, head_dim, k), 4) for k in (1024, 4096, 8192, 16384)},
        "fits_21gib_weight_budget": q4_gib <= MODEL_BUDGET_GIB,
        "full_stream_io_ceiling_tok_s": round(SSD_B_S / (q4_gib * GIB), 3),
    }


def main() -> None:
    out = Path("docs/result/evidence/a2_s0")
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        dense("Dense 14B representative", 14.0, 8.00, 48),
        dense("Dense 32B representative", 32.0, 18.29, 64),
        qwen3_moe("Qwen3-Coder-30B-A3B-Instruct", 30.5, 3.3, 18.557, 128, 8),
        qwen3_moe("Qwen3-30B-A3B", 30.5, 3.3, 18.557, 128, 8),
    ]
    # Qwen3-Next uses 12 full-attention layers in a 48-layer hybrid layout; fixed
    # DeltaNet recurrent state is deliberately excluded because exact runtime bytes
    # require model/runtime inspection and are reported as NOT PROVEN.
    next_row = qwen3_moe("Qwen3-Next-80B-A3B-Instruct", 80.0, 3.0, 48.4, 512, 10,
                         moe_layers=48, attention_layers=12, hidden=2048, expert_ff=512,
                         kv_heads=2, head_dim=256)
    next_row["recurrent_state_bytes"] = "NOT PROVEN"
    rows.append(next_row)

    payload = {
        "assumptions": {
            "ssd_mib_s": SSD_MIB_S,
            "model_runtime_budget_gib": MODEL_BUDGET_GIB,
            "dense_q4_sizes_source": "A1.0 calibrated 4.91 effective bpw",
            "sparse_q4_sizes_unit": "decimal GB from published GGUF artifact listings",
            "kv_dtype": "F16",
        },
        "candidates": rows,
    }
    (out / "candidate_architectures.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    io = {}
    for row in rows:
        if row["kind"] == "sparse_moe":
            active = row["active_expert_weight_gb_per_token_est"] * 1e9
            io[row["name"]] = {}
            for hit in (0, 25, 50, 75, 90):
                miss = 1 - hit / 100
                b = active * miss
                io[row["name"]][str(hit)] = {
                    "expert_cache_hit_pct": hit,
                    "expert_ssd_gb_per_token": round(b / 1e9, 4),
                    "io_only_ceiling_tok_s": None if b == 0 else round(SSD_B_S / b, 3),
                }
    (out / "io_comparison.json").write_text(json.dumps({"io_only_upper_bound": True, "rows": io}, indent=2) + "\n", encoding="utf-8")

    mem = {r["name"]: {"weight": r.get("q4_artifact_gb", r.get("q4_artifact_gib_est")), "kv_f16_gib": r["kv_f16_gib"],
                       "fits_21gib_weight_budget": r["fits_21gib_weight_budget"]} for r in rows}
    (out / "memory_comparison.json").write_text(json.dumps(mem, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
