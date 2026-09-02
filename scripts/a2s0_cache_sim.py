from __future__ import annotations

import argparse
import json
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

EXPERT_BYTES = 17_547_264
PER_TOKEN = 1472


def lru(trace: list[int], cap: int) -> int:
    if cap <= 0:
        return 0
    cache: OrderedDict[int, None] = OrderedDict()
    hits = 0
    for key in trace:
        if key in cache:
            hits += 1
            cache.move_to_end(key)
        else:
            if len(cache) >= cap:
                cache.popitem(last=False)
            cache[key] = None
    return hits


def lfu(trace: list[int], cap: int) -> int:
    if cap <= 0:
        return 0
    cache: dict[int, tuple[int, int]] = {}
    hits = 0
    clock = 0
    for key in trace:
        clock += 1
        if key in cache:
            hits += 1
            freq, _ = cache[key]
            cache[key] = (freq + 1, clock)
        else:
            if len(cache) >= cap:
                victim = min(cache, key=lambda k: (cache[k][0], cache[k][1]))
                del cache[victim]
            cache[key] = (1, clock)
    return hits


def pinned_hot(trace: list[int], cap: int) -> int:
    if cap <= 0:
        return 0
    hot = {k for k, _ in Counter(trace).most_common(cap)}
    seen: set[int] = set()
    hits = 0
    for key in trace:
        if key in hot:
            if key in seen:
                hits += 1
            seen.add(key)
    return hits


def reuse_distance_summary(trace: list[int]) -> dict:
    last: dict[int, int] = {}
    distances: list[int] = []
    for i, key in enumerate(trace):
        if key in last:
            distances.append(i - last[key])
        last[key] = i
    if not distances:
        return {"samples": 0}
    arr = np.asarray(distances)
    return {
        "samples": len(distances),
        "p50_requests": int(np.percentile(arr, 50)),
        "p90_requests": int(np.percentile(arr, 90)),
        "p95_requests": int(np.percentile(arr, 95)),
        "p99_requests": int(np.percentile(arr, 99)),
        "max_requests": int(arr.max()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out", default="docs/result/evidence/a2_s0/cache_simulation.json")
    ap.add_argument("--ssd-mib-s", type=float, default=2495.92)
    args = ap.parse_args()
    raw = np.fromfile(args.trace, dtype=np.int32)
    pairs = raw.reshape(-1, 2)
    trace = ((pairs[:, 0].astype(np.int64) << 20) | pairs[:, 1].astype(np.int64)).tolist()
    n = len(trace)
    ntok = n / PER_TOKEN
    rows = []
    for gb in (0, 1, 2, 4, 8, 12):
        cap = int(gb * 1e9 // EXPERT_BYTES)
        entry = {"cache_gb": gb, "slots": cap}
        for name, fn in (("lru", lru), ("lfu", lfu), ("pinned_hot_upper_bound", pinned_hot)):
            hits = fn(trace, cap)
            misses = n - hits
            gb_tok = misses * EXPERT_BYTES / 1e9 / ntok
            entry[name] = {
                "hit_rate": round(hits / n, 6),
                "miss_rate": round(misses / n, 6),
                "gb_read_per_token": round(gb_tok, 4),
                "io_only_seconds_per_token": round(gb_tok * 1000 / args.ssd_mib_s, 4),
            }
        rows.append(entry)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trace_requests": n,
        "distinct_experts": len(set(trace)),
        "approx_tokens": round(ntok, 3),
        "expert_bytes": EXPERT_BYTES,
        "reuse_distance": reuse_distance_summary(trace),
        "rows": rows,
        "warning": "Pinned-hot uses future knowledge and is an upper bound; this Kimi trace must not be generalized to other models.",
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
