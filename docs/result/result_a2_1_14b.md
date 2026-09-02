# A2.1 14B Dense Control Qualification

Date: 2026-09-03

## Verdict

**A2.1 verdict: `A2_14B_SCALING_PROMISING`.**

Qwen2.5-Coder 14B Q4_K_M shows a strong quality uplift over the 7B control and is worth keeping as the dense local quality tier candidate. It is **not** promoted to a production default yet because throughput and memory cost are materially higher than 7B.

Dense 32B remains **BLOCKED**. Sparse A2.S1 is **UNBLOCKED** as the next model qualification step because 14B proves that scaling improves local quality enough to justify testing the already-planned sparse candidate before any dense 32B run.

## Model Provenance

- Local file: `D:\WORK\RESEARCH\local2api\models\qwen2.5-coder-14b-instruct-q4_k_m.gguf`
- GGUF size: `8,988,110,272` bytes
- SHA256: `C1E659736D89AC1065FB495330FB824D94001974A4BFA78E7270E43476A8D940`
- Imported Ollama model: `local2api-qwen2.5-coder-14b:a2.1`
- No model download was performed for A2.1.
- Qwen3-Coder-30B-A3B was not touched, imported, hashed, or benchmarked in this run.

Exact metadata from the local GGUF/Ollama:

| Field | Value |
|---|---:|
| Architecture | `qwen2` |
| Parameters | `14,770,033,664` |
| Layers | `48` |
| Hidden size | `5120` |
| Attention heads | `40` |
| KV heads | `8` |
| Head dim | `128` |
| Context limit | `131072` |
| RoPE freq base | `1000000` |
| Quantization | `Q4_K_M` |
| Tensor count | `579` |

## Runtime

Primary runtime was isolated Ollama `0.33.2` on `127.0.0.1:11435`:

- `OLLAMA_IGPU_ENABLE=1`
- `OLLAMA_VULKAN=1`
- `OLLAMA_FLASH_ATTENTION=true`
- `OLLAMA_KV_CACHE_TYPE=f16`
- `OLLAMA_CONTEXT_LENGTH=16384`
- `OLLAMA_NUM_PARALLEL=1`
- `OLLAMA_MAX_LOADED_MODELS=1`

Arc/Vulkan device discovery was verified in the Ollama server log:

- backend library: `Vulkan`
- device: `Vulkan0`
- GPU: `Intel(R) Arc(TM) 140V GPU (16GB)`
- type: `iGPU`
- reported total: `18.0 GiB`
- reported available: `17.3 GiB`

A short post-restart generation returned `OK` with `load_duration_ns=8457223900`.

## Quality Gate

Quality was evaluated first, before performance, using the unchanged 25-case A0/HW1 suite and the same canonical ChatML prompt rendering.

| Class | 7B Ollama | 14B Ollama | Delta |
|---|---:|---:|---:|
| LOCAL_SAFE | 1/9 | 8/9 | +7 |
| LOCAL_ACCEPTABLE | 2/11 | 9/11 | +7 |
| Intended local total | 3/20 | 17/20 | +14 |
| CLOUD_REQUIRED keyword pass | 1/5 | 3/5 | Not production-deciding |

**Quality verdict: `QUALITY_STRONG_UPLIFT`.**

Manual 0-3 rubric across the 20 intended-local cases:

| Score | Count |
|---|---:|
| 0 unusable/wrong | 0 |
| 1 mostly wrong or unsafe | 0 |
| 2 usable with caveats | 9 |
| 3 directly useful | 11 |

Manual findings:

- No malformed responses observed.
- No repetition failure observed.
- Two responses were truncated by the 128-token harness limit but still usable.
- One response had minor domain drift by talking about packet routing instead of local/cloud routing.
- The remaining caveats were mostly verbosity or generic examples, not catastrophic reasoning failure.

## Performance

Same context fixtures as the 7B control were reused. Each level used one warm-up plus three measured runs.

| Context | 14B median TTFT | 14B median wall | 14B prompt tok/s | 14B gen tok/s |
|---|---:|---:|---:|---:|
| 1K | 285.997 ms | 16.601 s | 3,645.766 | 3.949 |
| 4K | 477.937 ms | 19.400 s | 12,686.994 | 3.360 |
| 8K | 474.771 ms | 23.737 s | 23,219.100 | 2.753 |
| 16K | 495.736 ms | 21.050 s | 46,746.626 | 3.116 |

For comparison, the prior 7B Ollama control produced:

| Context | 7B median TTFT | 7B median wall | 7B gen tok/s |
|---|---:|---:|---:|
| 1K | 213.925 ms | 3.263 s | Not recorded |
| 4K | 322.012 ms | 4.034 s | Not recorded |
| 8K | 201.904 ms | 7.987 s | 8.221 |
| 16K | 375.131 ms | 9.551 s | 6.873 |

Interpretation: 14B quality improved dramatically, but generation throughput is roughly 2-3x slower than the measured 7B long-context runs. The right use is selective quality-sensitive local coding/control work, not low-latency default routing.

## Memory And Stability

Sampled peak during the 25-case quality run:

- llama-server child working set: about `12,796,583,936` bytes
- llama-server child private bytes: about `12,896,735,232` bytes
- system committed bytes: about `35,203,911,680`
- minimum sampled available RAM: about `5,814 MB`

These are sampled telemetry points, not a high-frequency profiler. Page faults, thermal throttling, package power and GPU utilization percentage are **NOT PROVEN** in this run.

## Direct llama-server Control

The CPuFriend `llama-server.exe` was tested as a short secondary control with the same GGUF:

- command class: `llama-server -m <14B GGUF> -c 4096 -ngl 999 --host 127.0.0.1 --port 11437`
- model loaded and listened on `127.0.0.1:11437`
- short parity prompt produced the same text as Ollama
- llama-server TTFT: `4025.618 ms`
- llama-server generation: `4.108 tok/s`
- Ollama TTFT on the same short parity prompt: `972.306 ms`
- Ollama generation: `5.772 tok/s`

Preferred runtime for A2.1 remains **Ollama + Vulkan**. Direct llama-server is viable for diagnostics but was slower on this short control and previously became pathological at long context in A0/HW1.

## Evidence Files

- `docs/result/evidence/a2_1_14b/model_metadata.json`
- `docs/result/evidence/a2_1_14b/quality_gate_predeclared.json`
- `docs/result/evidence/a2_1_14b/quality_results.json`
- `docs/result/evidence/a2_1_14b/quality_outputs/`
- `docs/result/evidence/a2_1_14b/manual_quality_review.json`
- `docs/result/evidence/a2_1_14b/benchmark_runs_combined.json`
- `docs/result/evidence/a2_1_14b/benchmark_runs.json`
- `docs/result/evidence/a2_1_14b/benchmark_16k.json`
- `docs/result/evidence/a2_1_14b/parity_llama_server_short.json`
- `docs/result/evidence/a2_1_14b/telemetry.json`
- `docs/result/evidence/a2_1_14b/comparison_7b_vs_14b.json`
- `docs/result/evidence/a2_1_14b/runtime_config.json`

## Final Decision

14B passes the dense control quality gate and proves the local tier should not stop at 7B. However, its cost profile is too heavy to make it the blanket local default.

Next:

1. Run **A2.S1 sparse qualification** with the same quality/context methodology.
2. Keep **A2.2 dense 32B BLOCKED** until sparse-vs-14B evidence shows dense 32B is still worth testing.
3. Feed the 14B capability profile into Track B routing as a selective quality tier candidate, not as a universal fallback.
