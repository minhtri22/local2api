from __future__ import annotations

import argparse
import json
from pathlib import Path


GIB = 1024 ** 3

# Effective bits/weight observed from the HW1 Qwen2.5-Coder 7B Q4_K_M GGUF:
# 4.36 GiB / 7.62B parameters ~= 4.91 bits/weight. This includes block quantization overhead.
Q4_EFFECTIVE_BPW = 4.91

MODELS = {
    "14B_dense": {"params_b": 14.0, "layers": 48, "kv_heads": 8, "head_dim": 128},
    "32B_dense": {"params_b": 32.0, "layers": 64, "kv_heads": 8, "head_dim": 128},
    "70B_dense": {"params_b": 70.0, "layers": 80, "kv_heads": 8, "head_dim": 128},
    # Representative sparse MoE: Mixtral 8x7B family-scale accounting.
    "46.7B_moe": {"params_b": 46.7, "active_params_b": 12.9, "layers": 32, "kv_heads": 8, "head_dim": 128},
}

CONTEXTS = [4096, 8192, 16384, 32768]


def weight_gib(params_b: float, bpw: float = Q4_EFFECTIVE_BPW) -> float:
    return params_b * 1e9 * bpw / 8 / GIB


def kv_gib(layers: int, kv_heads: int, head_dim: int, tokens: int, bytes_per_element: float) -> float:
    # K + V for every layer and token.
    return 2 * layers * kv_heads * head_dim * tokens * bytes_per_element / GIB


def build() -> dict:
    reserve = {
        "windows_11_gib": 6.0,
        "vscode_gib": 2.5,
        "local2api_and_tools_gib": 0.5,
        "filesystem_cache_gib": 2.0,
    }
    physical = 32.0
    reserve_total = sum(reserve.values())
    practical = physical - reserve_total
    rows = {}
    for name, cfg in MODELS.items():
        wg = weight_gib(cfg["params_b"])
        rows[name] = {
            **cfg,
            "q4_effective_bpw": Q4_EFFECTIVE_BPW,
            "q4_weight_gib": round(wg, 3),
            "q4_overhead_vs_ideal_4bit_pct": round((Q4_EFFECTIVE_BPW / 4 - 1) * 100, 2),
            "kv_f16_gib": {
                str(ctx): round(kv_gib(cfg["layers"], cfg["kv_heads"], cfg["head_dim"], ctx, 2.0), 3)
                for ctx in CONTEXTS
            },
            "kv_q4_approx_gib": {
                str(ctx): round(kv_gib(cfg["layers"], cfg["kv_heads"], cfg["head_dim"], ctx, 0.5), 3)
                for ctx in CONTEXTS
            },
            "modeled_runtime_buffer_gib": 2.0,
            "fits_practical_budget_weights_only": wg <= practical,
        }
    return {
        "schema": "local2api.a1.memory_model.v1",
        "physical_ram_gib": physical,
        "reserve_assumptions": reserve,
        "practical_model_runtime_budget_gib": practical,
        "formulae": {
            "weights": "params * effective_bits_per_weight / 8",
            "kv": "2(K+V) * layers * kv_heads * head_dim * tokens * bytes_per_element",
            "q4_effective_bpw_basis": "HW1 7B Q4_K_M: 4.36 GiB / 7.62B params ~= 4.91 bits/weight",
        },
        "models": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    data = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2))
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
