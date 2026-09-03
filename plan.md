# local2api roadmap

## Product objective

Build a small, observable OpenAI-compatible inference gateway that can use a constrained local tier without assuming local inference is always the best backend. Local execution and routing evolve as independent tracks. Their only contract is:

`Track A -> Local Capability Profile -> Track B`

Track B remains useful even if Track A never produces a large-model local engine.

## Track A — Local Engine

### A0 — 7B Baseline — COMPLETE

- Hardware/runtime feasibility: **PASS** on Intel Core Ultra 7 258V / 32 GB / Arc 140V.
- Production coding/repository quality: **FAIL**.
- Qwen2.5-Coder 7B Q4_K_M is no longer a production coding target.
- Keep 7B as a baseline/control model, runtime benchmark, and utility model for narrow/easily verified tasks.

Conclusion: **7B chạy được nhưng không đủ chất lượng cho coding/repository production. Tối ưu tiếp 7B không còn là mục tiêu chính.**

### A1 — Adaptive Local Engine

#### A1.0 — Feasibility Study — COMPLETE

Goal: prove or reject whether 32 GB RAM + Intel Arc 140V + NVMe can run models beyond normal resident capacity with useful throughput.

Verdict: **GO_EXISTING_RUNTIME_ONLY**.

The measured storage lower bound makes generic dense per-token weight streaming too slow for a useful interactive tier, while 14B and potentially constrained 32B configurations remain plausible with existing llama.cpp/Ollama mmap/offload mechanisms. No adaptive engine prototype is justified by current evidence.

#### A1.1 — Prototype — CLOSED

A1.1 opens only for `GO_ADAPTIVE_RESIDENCY`. Current A1.0 does not satisfy that gate.

If future sparse-model evidence reopens it, prototype scope may include expert residency/cache, layer-group scheduling, prefetch, weight streaming, KV/context budgeting and telemetry while retaining llama.cpp compute kernels.

### A2 — Large-model Feasibility

#### A2.S0 — Sparse/MoE Early Feasibility — COMPLETE

Verdict: **`TEST_SPARSE_BEFORE_DENSE_32B`**.

Source/trace/runtime research found a concrete sparse candidate that changes the economics without requiring a custom runtime: Qwen3-Coder-30B-A3B-Instruct is ~30.5B total / ~3.3B active and its Q4_K_M-class artifact is plausibly resident on the target 32 GB machine. Current llama.cpp already has Qwen3-MoE, quantized MoE kernels, CPU-MoE placement and selective expert transfer.

Kimi K3 remains a reference architecture only. Its included low-memory measurements and routing trace show that Kimi-style expert streaming/cache is non-interactive at laptop-scale RAM; A1.1 remains closed.

Decision order after A2.S0:

1. **A2.1 dense 14B is COMPLETE** as the dense quality/control experiment.
2. **A2.S1 bounded sparse qualification is COMPLETE** with `SPARSE_INCONCLUSIVE`: short-task quality uplift is small, and successful Qwen3 Vulkan inference remains unqualified. The evidence does not promote a separate tier or establish a general hardware-tier rejection.
3. **A2.2 dense 32B remains BLOCKED**: no larger dense experiment is authorized or justified by this incomplete sparse runtime qualification.

#### A2.1 — Dense 14B Control — COMPLETE

Verdict: **`A2_14B_SCALING_PROMISING`**.

Qwen2.5-Coder 14B Q4_K_M on Ollama/Vulkan produced a strong quality uplift over the 7B control: intended-local quality improved from 3/20 to 17/20, with LOCAL_SAFE 8/9 and LOCAL_ACCEPTABLE 9/11. This proves dense scaling is useful for local coding/control quality on the target machine.

The model is not a production default yet. It is materially slower than 7B, with measured Ollama generation around 2.75-3.95 tok/s across the reused 1K/4K/8K/16K fixtures, and sampled llama-server child memory around 12.8 GB working set during quality evaluation.

Conclusion: keep 14B as a selective quality-sensitive local tier candidate and use it to inform Track B capability routing. This result originally unblocked A2.S1; the sparse qualification below has now completed and does not displace 14B.

#### A2.S1 — Sparse 30B-A3B Qualification — COMPLETE

Verdict: **`SPARSE_INCONCLUSIVE`**. This audited verdict supersedes `a63a5ef`; see [the canonical report](docs/result/result_a2_s1_qwen3_coder.md).

Qwen3-Coder-30B-A3B-Instruct Q4_K_M scored 18/20 versus 17/20 for both the frozen 14B control and a repaired same-runtime CPU control. Only A04 was recovered among the three historical failures. Audited manual scores are 2.00 versus 1.85/3; both models score 1/3 on the separate short challenges. Quality verdict: **`INCREMENTAL_QUALITY_SMALL`**. The earlier 2.65/2.55 means are withdrawn as comparative evidence because incomplete outputs were over-credited.

The successful CPuFriend direct profile requested 4K context, 32 GPU layers, batch 32, ubatch 16 and q4_0 KV, but device discovery shows no GPU backend in that installation: treat these as CPU observations, not verified Vulkan offload. Its 4K fixture reached about 333 seconds TTFT; the old harness failed to cancel at the 300-second gate, and larger direct contexts were omitted. Ollama/Vulkan attempts repeatedly failed allocations. Old cross-runtime TTFT ratios are invalid because cache policy and backend differed.

Conclusion: keep Qwen2.5-Coder 14B as the selective local quality-tier candidate. Do not promote a Qwen3 premium/specialist tier from current evidence. Successful Arc inference and usable memory headroom remain real qualification blockers, not proof that the model can never be useful on this hardware. Dense 32B remains blocked.

Candidate ladder result:

- 14B: selected as the current selective local quality-tier candidate;
- sparse Qwen3-Coder-30B-A3B: short CPU tasks tested; no additional production tier qualified, intended GPU path unresolved;
- dense 32B: remains blocked because the 14B/sparse comparison does not justify the additional active-compute and memory pressure.

Use existing runtimes first: Ollama/llama.cpp with mmap, partial offload, quantized KV where supported, and measured Vulkan/SYCL configurations. Determine max practical model, context, usable throughput and Local Capability Profile. Do not infer production usefulness merely from successful model loading.

### A3 — Production Qualification

- sustained stability;
- coding/repository quality;
- latency/TTFT;
- memory/swap pressure;
- thermal/power;
- production Local Capability Profile.

## Track B — Smart Router

### B0 — Reliable Router — COMPLETE BASELINE

Existing v0.0.1 provides OpenAI-compatible API, SSE streaming, backend abstraction, safe fallback and routing observability.

### B1 — Context Ownership

- `conversation_id` and canonical gateway-owned context;
- backend-independent reconstruction;
- token/context budgeting;
- backend capability registry;
- routing decision trace.

### B2 — Capability Router

Route on task class, context requirement, privacy, latency, backend capability and the Local Capability Profile produced by Track A.

### B3 — Adaptive Routing

- backend health;
- rate limits/retry policy;
- latency;
- cost;
- quality feedback;
- explicit fallback policy by capability class.

## Non-goals

- CAPTCHA/anti-bot bypass or provider rate-limit circumvention.
- Browser credential extraction.
- Treating a local model as production-capable without measured quality evidence.
- Rewriting llama.cpp's GGUF loader, kernels, tokenizer, sampler, server, graph scheduler or KV cache without proof that replacement is necessary.

## Current next action

Track A: the bounded A2.S1 run and audit are complete with `SPARSE_INCONCLUSIVE`; A2.2 dense 32B remains blocked. The selected local quality-tier candidate remains A2.1 14B. A follow-up sparse test requires sufficient RAM headroom, a matching Vulkan build/DLL, explicit Arc device/offload evidence, and cache-controlled measurements before any larger matrix. Alternatively, qualify the 14B candidate for production under A3. Track B remains independent and unchanged by A2.S1.
