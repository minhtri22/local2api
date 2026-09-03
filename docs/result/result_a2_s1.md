# A2.S1 Sparse Qualification — Qwen3-Coder-30B-A3B vs 14B Dense Control

Date: 2026-09-03

## Verdict

**A2.S1 final verdict: `SPARSE_NOT_JUSTIFIED_OVER_14B`.**

The sparse candidate produces a small quality uplift over the A2.1 14B dense control, but the uplift is not large enough to pay for its memory pressure, long-context latency and runtime fragility on this laptop.

- Quality verdict: **`INCREMENTAL_QUALITY_SMALL`**.
- Canonical intended-local score: **18/20** vs **17/20** for 14B.
- Manual 0–3 average: **2.65** vs **2.55** for 14B.
- Qwen3 recovers the 14B A04 failure, but D01 and D05 remain mechanical failures.
- D03 is a mechanical false positive for Qwen3: it contains the expected words but asks for a diff instead of performing the requested summary.
- Dense A2.2 32B remains **BLOCKED**.

The practical local quality-tier candidate therefore remains **Qwen2.5-Coder 14B Q4_K_M**, used selectively rather than as a universal local default.

## Gate And Method

The A2.S1 gate was frozen before the run:

- primary control: A2.1 Qwen2.5-Coder 14B, 17/20 intended-local;
- primary criterion: incremental capability over 14B, not model size or sparsity;
- same 20 intended-local prompts and keyword criteria as A0/A2.1;
- dense 32B prohibited during A2.S1;
- early stop at TTFT >300 s, total wall >600 s, material Windows unusability, unsafe memory pressure or repeated runtime crashes.

An exploratory Qwen3 quality run used a 96-token cap. Because A2.1 used 128 tokens, that run is preserved as evidence but superseded for the canonical comparison by `quality_results_128.json`, which reran all 20 intended-local cases at the matching 128-token cap.

## Model Provenance

- Local GGUF: `D:\WORK\RESEARCH\local2api\models\qwen3-coder-30b-a3b-instruct-q4_k_m.gguf`
- GGUF size: `18,556,688,704` bytes
- SHA256: `AB4FC2B27B2043483A9E346C802809DFBE9B775EFBEEA7CA74DC2FD1AA4A0F71`
- Architecture: `qwen3moe`
- Total parameters: `30,532,122,624`
- Layers: `48`
- Hidden size: `2048`
- Attention heads / KV heads: `32 / 4`
- Experts: `128`
- Experts selected per token: `8`
- Context metadata: `262144`
- Quantization: `Q4_K_M`
- GGUF file size is about **2.06x** the 14B control artifact.

The local GGUF proves the routing shape but does not encode one authoritative scalar for active parameters per token. A2.S1 therefore does not invent an active-parameter count from marketing material.

## Runtime Qualification

### Ollama + Vulkan

Primary runtime attempt used isolated Ollama `0.33.2` with Intel Arc 140V Vulkan, flash attention, one loaded model and one parallel request.

The Qwen3 model was recognized correctly as `qwen3moe`, but startup did not become operational under the tested memory-conservative configurations:

- 16K + q4_0 KV: Vulkan allocation failed while allocating a `452,984,832` byte KV buffer.
- 4K + q4_0 KV: startup failed allocating a `257,517,568` byte Vulkan compute buffer.
- 4K + `num_gpu=32` + batch 32: startup still failed allocating a `169,149,056` byte Vulkan compute buffer.
- Reducing GPU layers and batch size alone did not make the Ollama path operational.

This is a runtime result, not a claim that the model architecture is fundamentally incompatible with Arc/Vulkan.

### Direct llama-server + Vulkan

The CPuFriend binary was then used as a diagnostic/runtime control:

- `llama-server 0.3.0-dev`, build 10726, commit `85c55223c`;
- `ctx=4096`;
- `ngl=32`;
- `batch=32`;
- `ubatch=16`;
- q4_0 K/V cache;
- flash attention on.

This configuration initialized successfully and returned the exact smoke phrase. The first smoke generated 10 tokens at about **3.54 tok/s** with roughly **7.5 s** wall time.

The decisive runtime difference was control of physical micro-batch size (`ubatch=16`), which let direct llama-server initialize where the tested Ollama path still failed its Vulkan compute-buffer allocation.

## Canonical Quality Comparison

| Class | 14B control | Qwen3 sparse | Delta |
|---|---:|---:|---:|
| LOCAL_SAFE | 8/9 | 9/9 | +1 |
| LOCAL_ACCEPTABLE | 9/11 | 9/11 | 0 |
| Intended-local total | 17/20 | 18/20 | +1 |
| Manual average (0–3) | 2.55 | 2.65 | +0.10 |

Qwen3's quality gain is real but small:

- **A04 improves**: Qwen3 correctly identifies that falsy/empty messages are forwarded to `backend.chat()` without validation.
- **A03 improves manually**: Qwen3 stays in software/router testing semantics instead of the 14B control's packet-routing drift.
- **D01 remains weak**: the answer stays broad and never reaches the backend contract required by the mechanical criterion.
- **D05 remains a keyword miss but is manually good**, as with 14B.
- **D03 regresses manually**: Qwen3 asks the user to provide the diff. The keyword harness marks it pass only because the refusal repeats `route-reason response header`.

Manual score distribution for Qwen3:

| Score | Count |
|---|---:|
| 0 unusable/wrong | 0 |
| 1 mostly wrong/incomplete | 1 |
| 2 usable with caveats | 5 |
| 3 directly useful | 14 |

Sixteen answers reached the 128-token generation cap. This is recorded as an output-efficiency/verbosity issue; it is not automatically treated as a quality failure when the requested core answer was already complete.

## Context Performance

The same A0/A2.1 context fixtures were reused. Direct Qwen3 was intentionally limited to one measured sample per level because the 1K run was already slow and the predeclared early-stop rule applied.

| Context | 14B TTFT | Qwen3 TTFT | 14B wall | Qwen3 wall | 14B gen tok/s | Qwen3 gen tok/s |
|---|---:|---:|---:|---:|---:|---:|
| 1K / 870 tokens | 0.286 s | 50.255 s | 16.601 s | 60.526 s | 3.949 | 6.136 |
| 4K / 3573 tokens | 0.478 s | 333.053 s | 19.400 s | 349.820 s | 3.360 | 3.758 |

Qwen3 can generate at competitive or higher token/s once generation begins, but prompt ingestion dominates end-to-end behavior under the working partial-offload configuration. At 4K, TTFT is about **697x** the 14B control and exceeds the frozen **300 s** early-stop threshold.

Therefore:

- 8K direct benchmark: **NOT RUN after 4K early-stop trigger**.
- 16K direct benchmark: **NOT RUN after 4K early-stop trigger**; the Ollama 16K q4-KV startup had already failed OOM.
- CPU-MoE placement A/B: **NOT RUN** after the candidate failed the practical runtime gate.
- Long-context f16-vs-quantized-KV performance A/B: **NOT COMPLETED**; q4_0 was needed for the working direct configuration and did not rescue the tested Ollama startup path.

This is intentional early stopping, not missing data presented as success.

## Memory And Stability

After the successful direct 4K smoke:

- llama-server working set: `18,504,175,616` bytes;
- llama-server private bytes: `14,432,628,736` bytes;
- free physical memory: `572,256 KiB` (about 559 MiB).

During the later canonical run, the direct server was observed around 19–20 GiB working set. Because that observation was not captured with the same high-frequency profiler as A2.1, the report does not claim a synchronized peak-memory comparison.

Page faults, thermals, package power and GPU utilization percentage remain **NOT PROVEN**.

## Challenge-Only Suite

Three challenge-only cases were predeclared and excluded from the canonical score. The attempted 14B control endpoint returned HTTP 500 for all three calls, while Qwen3 returned outputs. Because the control side was invalid, this A/B is **NON_DECISION_GRADE** and is not used to claim an incremental capability win.

## Decision

The sparse candidate does not earn a new premium or specialist production tier on this hardware. A +1/20 mechanical gain and +0.10 manual-score gain do not compensate for the roughly 18.6 GB model artifact, near-exhaustion of system RAM in the working direct configuration, Ollama startup failures, and 333-second 4K TTFT.

Use the A2.1 14B dense model as the current selective local quality-tier candidate. Keep 7B as the utility/control baseline. Keep dense 32B blocked; A2.S1 provides no evidence that spending an even tighter memory/active-compute budget on dense 32B is justified.

The product-development path can now return to **B1 Context Ownership**. If Track A resumes, the next meaningful step is A3 production qualification of the chosen 14B profile rather than another larger-model experiment.

## Evidence

- `docs/result/evidence/a2_s1/quality_gate_predeclared.json`
- `docs/result/evidence/a2_s1/model_metadata.json`
- `docs/result/evidence/a2_s1/runtime_config.json`
- `docs/result/evidence/a2_s1/quality_results_128.json` — canonical 128-token quality run
- `docs/result/evidence/a2_s1/quality_results.json` — exploratory 96-token run, superseded for comparison
- `docs/result/evidence/a2_s1/manual_quality_review.json`
- `docs/result/evidence/a2_s1/comparison_14b_vs_qwen3.json`
- `docs/result/evidence/a2_s1/benchmark_direct_llama_server_minimal.json`
- `docs/result/evidence/a2_s1/direct_llama_server_smoke_4k.json`
- `docs/result/evidence/a2_s1/load_smoke_q4kv_16k.json`
- `docs/result/evidence/a2_s1/load_smoke_q4kv_4k.json`
- `docs/result/evidence/a2_s1/load_smoke_q4kv_4k_batch_32.json`
- `docs/result/evidence/a2_s1/process_after_direct_smoke_4k.json`
- `docs/result/evidence/a2_s1/system_after_direct_smoke_4k.json`
- `docs/result/evidence/a2_s1/challenge_14b_vs_qwen3.json`
