from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--memory-model", type=Path, required=True)
    p.add_argument("--ssd-benchmark", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()

    mem = json.loads(a.memory_model.read_text(encoding="utf-8"))
    ssd = json.loads(a.ssd_benchmark.read_text(encoding="utf-8"))
    # Conservative measured sequential bandwidth: slowest full sequential pass.
    bandwidth_mib_s = min(ssd["sequential_read_mib_s"])
    bandwidth_b_s = bandwidth_mib_s * 1024 ** 2

    models = {}
    for name, m in mem["models"].items():
        weight_bytes = m["q4_weight_gib"] * 1024 ** 3
        strategies = {}
        for resident in (0.0, 0.25, 0.50, 0.75):
            streamed = weight_bytes * (1 - resident)
            min_s_token = streamed / bandwidth_b_s
            strategies[str(int(resident * 100))] = {
                "resident_fraction": resident,
                "streamed_gib_per_token": round(streamed / 1024 ** 3, 3),
                "minimum_seconds_per_token_io_only": round(min_s_token, 4),
                "theoretical_max_tokens_per_second_io_only": round(1 / min_s_token, 4) if min_s_token else None,
            }
        models[name] = strategies

    out = {
        "schema": "local2api.a1.io_model.v1",
        "measured_bandwidth_mib_s_conservative": bandwidth_mib_s,
        "lower_bound_formula": "streamed_bytes_per_token / measured_sustained_bytes_per_second",
        "warning": "I/O-only bound excludes device-copy, dequantization, graph scheduling and compute; real throughput can only be lower unless I/O overlaps compute.",
        "models": models,
        "prefetch_condition": "I/O for next layer/group can be fully hidden only when its read+transfer time <= compute time of current layer/group and sufficient staging memory exists.",
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, indent=2))
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
