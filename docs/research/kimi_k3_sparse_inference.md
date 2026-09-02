# Kimi-K3-in-C: Sparse CPU Inference Lessons for local2api

Date: 2026-09-02

## Purpose

This document records an architectural research finding relevant to Track A (Local Engine): `kimi-k3-in-c` demonstrates that a very large Mixture-of-Experts (MoE) model can be executed on CPU-only hardware with limited RAM by making inference cost depend on the **active working set per token**, not on total parameter count.

This is not evidence that multi-trillion-parameter local inference is interactive or production-fast. It is evidence that **sparsity-aware execution, selective expert loading, packed-weight compute, and explicit residency policies** create a different feasibility envelope from dense full-weight streaming.

The practical question for `local2api` is therefore no longer only:

> How large a dense model can fit in 32 GB RAM?

It is also:

> Can a sparse/MoE model with a much larger total parameter count but a much smaller active parameter set per token deliver better quality-per-resource than a dense 14B/32B model on Intel Core Ultra 7 258V + 32 GB RAM + Arc 140V + NVMe?

---

## 1. Why kimi-k3-in-c can run without a GPU

The reference project is a C99 CPU inference engine for Kimi K3. Its feasibility comes from a combination of model architecture and runtime policy rather than from raw CPU compute power.

Key ideas:

1. **MoE sparsity**
   - Only a small subset of experts is active for each token.
   - The runtime does not need every expert resident in RAM or loaded from storage for every token.

2. **Selective expert loading**
   - Routed expert weights are accessed only for the experts selected by the router.
   - The total model may be enormous while the active expert working set is much smaller.

3. **Packed low-bit expert weights**
   - Expert weights remain in packed low-bit form for storage and compute paths rather than being fully expanded into BF16/FP16 first.
   - This reduces both storage traffic and working-set size.

4. **Explicit dense-trunk residency**
   - Always-active weights are treated differently from routed experts.
   - RAM is preferentially used for dense trunk weights because every byte kept resident there avoids repeated I/O on every token.

5. **Expert cache as a secondary optimization**
   - Expert caching only helps when routing locality produces useful cache hit rates.
   - Cache allocation must be evidence-driven; a small expert cache can be less valuable than using the same RAM to pin always-active trunk weights.

6. **CPU-native implementation**
   - The runtime is written around CPU vectorization and threading rather than requiring CUDA/PyTorch.
   - GPU absence is therefore not a functional blocker, although performance remains slow compared with production interactive inference.

The core lesson is:

> Total parameter count is not the primary runtime-cost variable for sparse models. Active parameters/token, always-active trunk size, storage traffic/token, context-state cost, and cache locality are more informative.

---

## 2. Why this does not invalidate A1.0

A1.0 concluded `GO_EXISTING_RUNTIME_ONLY` for dense large-model inference because dense layer streaming is fundamentally limited by SSD bandwidth.

Measured SSD bandwidth on the target laptop was approximately 2.5 GiB/s. The A1.0 I/O model showed naive dense full-weight streaming ceilings of roughly:

| Dense model | I/O-only theoretical ceiling |
|---|---:|
| 14B Q4 | ~0.30 tok/s |
| 32B Q4 | ~0.13 tok/s |
| 70B Q4 | ~0.06 tok/s |

Even at 75% weight residency, the remaining streamed fraction remained too expensive for interactive dense inference.

`kimi-k3-in-c` does not contradict this. It succeeds because the largest part of the model is **sparse and selectively activated**. A dense 32B model still needs all dense layers for every token; a sparse MoE model may only need a small expert subset in addition to an always-active trunk.

Therefore:

- **Dense AirLLM-style full layer streaming remains not justified.**
- **Sparse expert-selective loading is a separate research direction and remains open.**

---

## 3. New variables Track A should care about

For dense models, local2api has mainly tracked:

- total parameter count;
- GGUF size;
- RAM footprint;
- KV cache size;
- prompt-eval speed;
- decode tokens/s.

For sparse/MoE models, Track A should additionally track:

- total parameters;
- active parameters/token;
- always-active trunk size;
- experts per layer;
- experts selected/token;
- expert weight bytes/token;
- expert routing locality;
- expert cache hit rate;
- dense-trunk residency ratio;
- bytes read from SSD/token;
- packed-weight compute support;
- context-state architecture and growth behavior.

A more useful runtime-cost model becomes:

`token_cost ~= trunk_compute + active_expert_compute + trunk_storage_traffic + expert_storage_traffic + context_state_cost`

rather than:

`token_cost ~= total_model_size`

---

## 4. Architectural patterns worth learning

### 4.1 Active-set inference

Inference policy should be based on the weights actually required for a token, not total model size.

This makes a large sparse model potentially more practical than a much smaller dense model.

### 4.2 Weight classes

A local engine should classify weights into at least:

- `ALWAYS_RESIDENT_CANDIDATE`
- `STREAMABLE`
- `CACHEABLE`
- `EPHEMERAL`

For MoE, the dense trunk and routed experts should not share one residency policy.

### 4.3 Direct packed-weight compute

Avoid workflows that load Q4/MXFP4 weights from SSD and immediately expand the entire working set into BF16/FP16.

A useful engine should prefer direct or block-wise low-bit compute paths where the backend supports them.

### 4.4 Evidence-driven RAM allocation

RAM should be allocated to the structures that reduce the most repeated I/O or compute.

Candidate priority order should be measured rather than assumed, for example:

1. dense/always-active trunk;
2. KV/context state;
3. staging/prefetch buffers;
4. expert cache;
5. filesystem cache/reserve.

### 4.5 Trace-based cache simulation

Instead of repeatedly running a huge model to test expert-cache sizes, record an expert-routing trace once and replay it offline under multiple cache policies.

This allows cheap evaluation of:

- cache capacity;
- LRU/LFU alternatives;
- pinned experts;
- locality windows;
- expected hit rate;
- bytes avoided from SSD.

### 4.6 Storage-aware runtime

The runtime should measure the actual I/O pattern it creates, not rely only on headline SSD sequential bandwidth.

Relevant measurements include:

- sequential throughput;
- aligned/direct I/O throughput;
- random/subrange read latency;
- queue depth;
- read amplification;
- effective bytes/token.

---

## 5. Context architecture matters independently of MoE

Sparse weights solve only part of the local-inference problem.

A model can have efficient expert activation and still become unusable if long-context prefill or KV/context state dominates latency and memory.

Therefore any sparse/MoE candidate must also be evaluated for:

- attention architecture;
- KV growth with sequence length;
- recurrent/linear/state-space components if present;
- prefill throughput at 1K/4K/8K/16K+ contexts;
- context-state residency and memory pressure.

`local2api` must not assume that "MoE" automatically solves the context problem.

---

## 6. Implication for Track A roadmap

The current dense path should remain:

```text
A0 — 7B baseline
A1.0 — architecture feasibility
      verdict: GO_EXISTING_RUNTIME_ONLY
A2.1 — 14B dense qualification
A2.2 — 32B dense qualification (only if justified)
```

However a new **early sparse/MoE feasibility branch** should be evaluated before blindly committing to 32B dense:

```text
A2.S0 — Sparse/MoE Early Feasibility
  - candidate architecture survey
  - active-parameter economics
  - expert I/O model
  - context-state model
  - existing runtime support
  - cache/residency simulation
  - quality potential vs dense 14B/32B
```

A2.S0 is a research gate, not an implementation commitment.

It should decide whether the next expensive experiment should be:

- dense 14B;
- dense 32B;
- sparse/MoE candidate;
- or no larger local model at all.

---

## 7. Early comparison framework

Any decision between dense and sparse candidates should compare at least:

| Dimension | Dense 14B | Dense 32B | Sparse/MoE candidate |
|---|---:|---:|---:|
| Total parameters | | | |
| Active parameters/token | all | all | |
| Q4/packed total size | | | |
| Always-active weight size | | | |
| Active expert bytes/token | n/a | n/a | |
| KV/context-state @ 4K/8K/16K | | | |
| Expected SSD bytes/token | | | |
| Estimated I/O ceiling | | | |
| Existing Ollama/llama.cpp support | | | |
| Intel Arc/Vulkan path | | | |
| Quality expectation | | | |
| Coding/repository suitability | | | |
| Implementation complexity | low | low | |
| Production risk | | | |

Quality remains the primary product criterion.

A candidate that is technically clever but fails coding/repository quality should not advance.

---

## 8. Required early tests before changing direction

Before changing `plan.md` to prioritize sparse/MoE, run a lightweight but evidence-backed feasibility study.

Required tests:

### T1 — Architecture verification

For each candidate, verify from config/source/model card:

- total parameters;
- active parameters/token;
- expert count;
- selected experts/token;
- always-active/shared experts;
- attention/context architecture.

### T2 — Memory model

Calculate:

- total packed weight size;
- always-active resident budget;
- KV/context-state at 1K/4K/8K/16K;
- Windows/VS Code/local2api reserve.

### T3 — Expert I/O model

Calculate lower and upper bounds for:

- bytes of expert weights required/token;
- storage traffic with 0%, 25%, 50%, 75% expert-cache hit rates;
- theoretical tok/s ceiling using measured target-laptop SSD bandwidth.

### T4 — Routing trace/cache simulation

If an accessible smaller model or published trace can represent the candidate architecture, measure/simulate:

- expert reuse distance;
- cache hit rate vs cache size;
- SSD bytes saved;
- whether expert caching is actually useful.

If no trace is available, mark this `NOT PROVEN` rather than inventing locality.

### T5 — Runtime support

Check exact support in current versions of:

- llama.cpp/GGUF;
- Ollama;
- Vulkan/Intel Arc;
- quant format;
- expert offload/loading behavior.

### T6 — CPU/GPU execution economics

Estimate or measure the active compute workload and determine whether Arc 140V or CPU is the practical execution path.

### T7 — Context scaling risk

Estimate/measure prefill and context-state cost independently of expert sparsity.

### T8 — Quality evidence

Use available public evaluation/model-card evidence only as preselection evidence.

Do not declare production suitability without running the same local2api coding/repository quality suite used for the dense control.

---

## 9. Decision gate

The early sparse/MoE study should end with one of:

### `CONTINUE_DENSE_14B`

Use when the sparse path offers no clear expected quality/resource advantage or runtime support is immature.

### `TEST_SPARSE_BEFORE_DENSE_32B`

Use when a specific sparse/MoE candidate has:

- meaningfully larger quality potential;
- active working set compatible with the machine;
- plausible storage traffic;
- viable llama.cpp/Ollama/Arc path;
- acceptable implementation risk.

### `PARALLEL_DENSE_AND_SPARSE`

Use only when both paths have materially different value propositions worth measuring.

### `STOP_LARGE_LOCAL`

Use when neither dense nor sparse candidates have credible quality-per-resource economics.

No roadmap direction should be changed before this gate is completed.

---

## 10. Relationship to Smart Router (Track B)

Track B remains independent.

The sparse/MoE research only changes the `Local Capability Profile` produced by Track A.

Possible future local tiers could become:

```text
utility-small       -> narrow/verifiable model
local-dense         -> 14B/32B resident or mmap/offload
local-sparse        -> MoE/expert-selective runtime
cloud               -> high-quality latency-sensitive backend
```

Track B should route by capability, quality, privacy, context and latency rather than by parameter count.

---

## 11. Current recommendation

Do **not** abandon A2.1 14B solely because of `kimi-k3-in-c`.

Do **not** proceed automatically from 14B to dense 32B either.

Instead, perform an **early sparse/MoE feasibility comparison now**, before committing to the next expensive model download/benchmark sequence.

The decision must be evidence-driven and must compare:

- quality potential;
- active working set;
- storage traffic/token;
- context-state cost;
- existing runtime support;
- Intel Arc feasibility;
- implementation complexity.

The main lesson from `kimi-k3-in-c` is not "run a huge model on CPU". It is:

> Design and evaluate local inference around the active working set and repeated storage traffic per token, not around total model size alone.

---

## 12. A2.S0 verification update — 2026-09-02

The subsequent source/trace study in `docs/result/result_a2_s0_sparse_early_feasibility.md` sharpened this hypothesis in two important ways.

First, Kimi K3 is a valid proof of sparse low-RAM execution but **not** evidence for interactive large-model inference on the target laptop. The reference repo's own memory ladder reports about 32.69 s/token at an 8 GB budget. Its included real expert-routing trace also shows that a small LRU cache has poor marginal value: replayed at the target laptop's measured ~2.5 GiB/s SSD rate, 4–12 GB of expert cache still leaves about 16.47 GB of routed-expert reads per token before trunk traffic and compute. Kimi-specific locality therefore must not be generalized to another MoE.

Second, the more promising sparse direction is not necessarily a Kimi-style out-of-core engine. A model such as Qwen3-Coder-30B-A3B-Instruct has a ~30.5B total / ~3.3B active architecture while a Q4_K_M-class artifact is around the resident-capacity boundary of this machine. Current llama.cpp source already includes Qwen3-MoE support, CPU-MoE placement controls, Vulkan/SYCL MoE kernels and selective transfer of used experts. That creates a much lower-risk experiment: test a **resident sparse model with an existing runtime** before considering any expert-streaming engine.

This update does not overwrite the original hypothesis; it narrows it. The transferable Kimi lesson is active-working-set accounting and trace-based evidence, not the assumption that custom expert streaming is the preferred implementation.
