from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import time
from pathlib import Path


MIB = 1024 ** 2


def sequential(path: Path, passes: int, block_mib: int) -> list[float]:
    rates = []
    block = block_mib * MIB
    for _ in range(passes):
        total = 0
        t0 = time.perf_counter()
        with path.open("rb", buffering=0) as f:
            while True:
                data = f.read(block)
                if not data:
                    break
                total += len(data)
        dt = time.perf_counter() - t0
        rates.append(round(total / MIB / dt, 2))
    return rates


def random_reads(path: Path, samples: int, block_kib: int, seed: int = 42) -> dict:
    block = block_kib * 1024
    size = path.stat().st_size
    rng = random.Random(seed)
    lat_ms = []
    with path.open("rb", buffering=0) as f:
        for _ in range(samples):
            offset = rng.randrange(0, max(1, size - block))
            t0 = time.perf_counter()
            f.seek(offset)
            f.read(block)
            lat_ms.append((time.perf_counter() - t0) * 1000)
    lat_ms.sort()
    return {
        "samples": samples,
        "block_kib": block_kib,
        "median_latency_ms": round(statistics.median(lat_ms), 4),
        "p95_latency_ms": round(lat_ms[int(0.95 * (len(lat_ms) - 1))], 4),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--passes", type=int, default=3)
    p.add_argument("--block-mib", type=int, default=8)
    p.add_argument("--random-samples", type=int, default=2048)
    p.add_argument("--random-block-kib", type=int, default=64)
    a = p.parse_args()
    if not a.file.is_file():
        raise SystemExit(f"benchmark file not found: {a.file}")
    seq = sequential(a.file, a.passes, a.block_mib)
    out = {
        "schema": "local2api.a1.ssd_benchmark.v1",
        "file": str(a.file),
        "file_size_bytes": a.file.stat().st_size,
        "sequential_passes": a.passes,
        "sequential_block_mib": a.block_mib,
        "sequential_read_mib_s": seq,
        "sequential_min_mib_s": min(seq),
        "sequential_median_mib_s": round(statistics.median(seq), 2),
        "random_read": random_reads(a.file, a.random_samples, a.random_block_kib),
        "notes": "Read-only lightweight benchmark over an existing local GGUF. Buffered OS/cache effects may remain; minimum full-file pass is used for conservative I/O modeling.",
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, indent=2))
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
