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

### A2 — Large-model Feasibility — NEXT TRACK-A GATE

Candidate ladder:

- 14B first;
- 32B only if 14B demonstrates useful quality/performance;
- dense vs MoE when a specific candidate offers a credible capability benefit.

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

Track A: A2 should test a 14B candidate with existing runtimes first; 32B remains gated by the 14B result. Track B can proceed independently with B1 Context Ownership.
