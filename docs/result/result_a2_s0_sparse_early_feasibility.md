# A2.S0 — Sparse/MoE Early Feasibility

Date: 2026-09-02

## Executive summary

**Verdict: `TEST_SPARSE_BEFORE_DENSE_32B`.**

The study found one concrete sparse candidate that changes the economics on the target Intel Core Ultra 7 258V / 32 GB / Arc 140V laptop: **Qwen3-Coder-30B-A3B-Instruct**. It is approximately 30.5B total parameters but 3.3B active per token, has a Q4_K_M-class artifact around 18.6 GB, and is supported by the current llama.cpp Qwen3-MoE architecture. Unlike Kimi K3, its full quantized weights are plausibly resident inside the existing 21 GiB model/runtime planning budget, so the first experiment does not need expert streaming from NVMe at all.

That is the key result. Sparse does not win here because a 1.5 TB model can be streamed from SSD. It becomes interesting because a coding-specialized ~30B-total MoE can fit at roughly dense-32B storage cost while executing only ~3.3B active parameters/token and using a smaller conventional KV footprint.

Kimi K3 remains valuable as a reference architecture. Source and trace evidence verify selective expert reads, direct packed MXFP4 compute, explicit trunk/cache residency, O_DIRECT preads, routing traces and offline cache simulation. But its own measured 8 GB configuration is about 32.69 s/token, and the supplied real routing trace shows LRU expert-cache locality essentially flat around 36.2% from 4–64 GB. It is therefore not a practical target runtime/model for this laptop.

Dense A2.1 14B remains the next low-risk control. Dense A2.2 32B remains blocked. Before spending on dense 32B, qualify Qwen3-Coder-30B-A3B-Instruct with the exact same local2api quality and context suite.

## 1. Baseline and references

local2api baseline pulled before research:

- `7ad60baab324d714c4f6fecdfe225a35bb3b6e4c`
- `docs: add Kimi K3 sparse inference research note`

Reference repos were cloned/updated under ignored `.research/` and were not committed:

| Reference | Commit | License |
|---|---|---|
| kimi-k3-in-c | `117e9d29bde14db9742f54fb66a191fd0bf03903` | Apache-2.0 |
| llama.cpp | `7798007a29a90e3053e799394da48cf53a2f8e0f` | MIT |
| AirLLM | `fd1bd87216488e053b87691bbb6318fa9bf77a4b` | Apache-2.0 |

Local runtime observations:

- Ollama `0.33.2`.
- CPuFriend direct `llama-server`: `0.3.0-dev`, build 10726, commit `85c55223c`.
- A0 already proved Intel Arc 140V Vulkan execution with Qwen2.5-Coder 7B Q4_K_M.

Machine-readable provenance: `docs/result/evidence/a2_s0/reference_revisions.json`.

## 2. Predeclared decision criteria

The gate was declared before final candidate analysis:

- `CONTINUE_DENSE_14B`: sparse runtime/working-set/quality advantage is not credible enough.
- `TEST_SPARSE_BEFORE_DENSE_32B`: at least one concrete sparse candidate has materially better expected quality/resource economics, a practical active set/context cost, and an existing-runtime path close enough to usable.
- `PARALLEL_DENSE_AND_SPARSE`: both paths have strong, distinct value and both experiments are justified.
- `STOP_LARGE_LOCAL`: neither dense nor sparse has credible economics.

Estimated decode classes used for planning, not as measured performance:

- `INTERACTIVE`: >=5 tok/s.
- `SLOW_INTERACTIVE`: 2–5 tok/s.
- `BATCH_ONLY`: 0.5–2 tok/s.
- `UNUSABLE`: <0.5 tok/s.

TTFT/prefill is separate and must be measured in the qualification run. These thresholds are intentionally more tolerant than A1.0's >=8 tok/s “interactive” label because a larger reasoning/coding tier can still be useful at 5–8 tok/s if quality uplift is substantial.

## 3. Kimi K3 source map

| Concept | File | Function / implementation | Why it matters to local2api |
|---|---|---|---|
| Checkpoint mapping/index | `src/io/k3_st.c` | `scan_shard`, `k3_st_open` | Reads safetensors headers and records tensor offsets instead of materializing the checkpoint. |
| Expert offset mapping | `src/io/k3_load.c` | `k3_expert_ref` | Resolves one routed expert into exact packed tensor subranges. |
| Direct expert read | `src/io/k3_load.c` | `k3_expert_load_direct` | Reads only selected expert bytes with aligned direct-I/O fallback behavior. |
| Dense trunk | `src/io/k3_trunk.c` | `k3_trunk_open`, `k3_trunk_bind` | Treats always-active trunk independently from routed experts. |
| Trunk prefetch | `src/io/k3_trunk.c` | `trunk_io_main`, `k3_trunk_prefetch` | Reads layer L+1 while L computes when ring capacity permits. |
| Router | `src/core/k3_ops.c` | `k3_router` | Sigmoid/bias selection over 896 experts, top-16, optional renormalization. |
| MoE dispatch | `src/core/k3_ops.c` | `k3_moe`, `k3_moe_prefill` | Routes and executes only selected experts. |
| Packed compute | `src/core/k3_ops.c` | `k3_matmul_mxfp4` | Consumes MXFP4 nibbles/scales directly; no whole-expert FP16/BF16 inflation. |
| Expert cache | `src/cache/k3_cache.c` | `pick_victim`, `admit`, `cache_get` | Whole-expert LRU residency. |
| Batched expert I/O | `src/cache/k3_cache.c` | `cache_getmany` | Reserve serially, parallel `pread`, publish only successful reads; sorted by disk offset. |
| Cache trace | `src/cache/k3_cache.c` | `k3_cache_dump_trace` | Records requested `(layer, expert)` sequence independently of cache outcome. |
| Cache simulation | `tools/sim_cache.py` | `lru`, `belady`, `pinned_lru` | Replays one real trace across cache capacities/policies. |
| KDA state | `src/core/k3_ops.c` | `k3_kda_step`, `k3_kda_layer` | Recurrent state does not grow with sequence length. |
| MLA context | `src/core/k3_ops.c` | `k3_mla_cached` | Released implementation caches expanded per-head K/V; context still grows linearly. |
| Model/layer binding | `src/model/k3_bind.c` | `plan_resolve`, `plan_load`, `k3_bind_layer_mem` | Separates in-place packed weights from weights widened for kernels such as router gate. |
| Generation traversal | `src/cli/k3_run.c` | layer loop around `k3_trunk_bind` / `k3_trunk_prefetch` | Every generated token still traverses all 93 layers; sparsity is inside 92 MoE FFNs. |

CPU assumptions are explicit: CMake documents AVX2+FMA as the x86 baseline; OpenMP is used when available. The runtime is CPU-native C99 rather than PyTorch/CUDA.

### Verified Kimi architecture claims

The released configuration fallback and config loader agree on the relevant shape:

- hidden 7168;
- 93 layers: 69 KDA + 24 Gated MLA;
- layer 0 dense FFN; 92 routed-MoE layers;
- 896 routed experts/layer;
- top-16 selected experts/token/layer;
- 2 shared experts;
- routed expert latent width 3584, expert intermediate 3072;
- one routed expert occupies 17,547,264 packed bytes in the released checkpoint.

Repository evidence reports 2.78T total parameters, 1.56 TB checkpoint, ~104B active parameters/token, ~1.45 TB routed experts, ~108.81 GB dense trunk, and ~626 MB fixed recurrent state. These claims are backed by source/config/checkpoint-census evidence in the repo; this study did not download the 1.56 TB checkpoint and therefore did not independently recensus the model files.

The important performance claim is also explicit rather than hidden: the repository's 8 GB ladder row is ~32.69 s/token. “Runs in 8 GB” means proof-of-life, not interactive inference.

## 4. Kimi cache/locality experiment

The included `tests/fixtures/expert_trace.bin` contains 100,096 expert requests, about 68 decode tokens, touching 10,010 distinct experts out of 82,432.

The official simulator was replayed with this laptop's A1.0 conservative measured SSD bandwidth, 2,495.92 MiB/s. With no cache the routed-expert traffic is 25.83 GB/token. LRU at 8/16/32/64 GB remains ~36.24% hit and ~16.47 GB/token, an I/O-only minimum of ~6.60 s/token before compute. The trace has 90% repeat requests, but reuse distance is long: p50 ~9,505 requests and p95 ~16,880 requests.

Requested small-cache replay produced:

| Cache | LRU hit | Expert GB/token | I/O-only s/token @ measured SSD |
|---:|---:|---:|---:|
| 0 GB | 0.0% | 25.83 | 10.35 |
| 1 GB | 35.33% | 16.70 | 6.69 |
| 2 GB | 36.20% | 16.48 | 6.60 |
| 4 GB | 36.24% | 16.47 | 6.60 |
| 8 GB | 36.24% | 16.47 | 6.60 |
| 12 GB | 36.24% | 16.47 | 6.60 |

`LFU` and a future-aware pinned-hot toy policy were also replayed for sensitivity, but neither is the engine's production policy and the pinned policy is an upper-bound construction. The official simulator's Belady/pinned+LRU results are the stronger policy ceiling.

Conclusion: Kimi K3 has real expert reuse, but the working set is far larger than the laptop's useful cache budget. Do not project Kimi locality onto another model.

Evidence: `cache_simulation.json` plus the reference repo's `tools/sim_cache.py`.

## 5. Candidate survey

Three practical sparse classes were retained for comparison.

### Qwen3-Coder-30B-A3B-Instruct — preferred

- 30.5B total / 3.3B activated parameters (official model family metadata).
- 48 layers, hidden 2048, 32 attention heads / 4 KV heads, head_dim 128.
- 128 experts, top-8, expert intermediate 768.
- coding-specialized family; strongest product fit of the surveyed sparse candidates.
- Q4_K_M-class GGUF listing is approximately 18.6 GB decimal (~17.3 GiB).
- current llama.cpp has native `qwen3moe` architecture support.

### Qwen3-30B-A3B

- same 30.5B / 3.3B active MoE economics, 128 experts / top-8.
- official config observed locally over HTTPS: 48 layers, hidden 2048, 4 KV heads, 40,960 max positions.
- strong general reasoning candidate but less directly aligned with coding/repository tasks than Qwen3-Coder.

### Qwen3-Next-80B-A3B-Instruct

- 80B total / ~3B active class.
- official config observed: 48 layers, hidden 2048, 512 experts, top-10, shared expert, hybrid DeltaNet/full-attention architecture; full attention every 4th layer (12 layers), 2 KV heads, head_dim 256, 262,144 max positions.
- Q4_K_M-class artifact is roughly 48.4 GB, far beyond the 21 GiB model/runtime planning budget.
- active compute is attractive, but total weight residency is not; expert streaming would reintroduce storage/runtime risk.

Kimi K3 itself was deliberately not promoted to the practical candidate list because the model is ~1.56 TB on disk and its measured low-memory path is non-interactive.

## 6. Dense controls

From A1.0, using the observed 4.91 effective bpw calibration:

- Dense 14B Q4 estimate: **8.00 GiB**, all 14B active/token.
- Dense 32B Q4 estimate: **18.29 GiB**, all 32B active/token.

Both can use ordinary llama.cpp/Ollama mmap/offload. 14B has comfortable memory margin; 32B weights alone nearly consume the 21 GiB model/runtime budget and become risky as KV/runtime buffers grow.

If either were naïvely streamed from SSD each token, the A1.0 I/O-only ceilings are ~0.305 tok/s and ~0.133 tok/s respectively. The intended path is therefore residency/mmap, not dense weight streaming.

## 7. Active-weight and memory economics

For Qwen3 30B-A3B, the routed expert matrices implied by the config are approximately 28.991B parameters total. Top-8/128 activates ~1.812B routed-expert parameters/token. Subtracting that from the reported ~3.3B active total gives a planning estimate of ~1.49B always-active/non-routed parameters.

Scaling the ~18.6 GB Q4 artifact by those fractions gives a rough weight-access model:

- always-active weight class: ~0.92 GB;
- selected routed-expert weight class: ~1.10 GB/token;
- full artifact: ~18.6 GB decimal (~17.3 GiB).

These proportional byte figures are estimates, not a tensor-level GGUF census. The full-artifact residency result is more important: it plausibly fits, so expected steady decode should not be SSD-bound if Windows/runtime pressure stays controlled.

Conventional F16 KV estimates for the 48-layer / 4-KV-head architecture are:

| Context | Qwen3 30B-A3B F16 KV |
|---:|---:|
| 1K | 0.094 GiB |
| 4K | 0.375 GiB |
| 8K | 0.750 GiB |
| 16K | 1.500 GiB |

At 16K, ~17.3 GiB weights + ~1.5 GiB F16 KV leaves only ~2.2 GiB inside the 21 GiB model/runtime planning budget. That is plausible but tight. Quantized KV should therefore be part of the actual qualification A/B if supported by the selected runtime.

Qwen3-Next's ordinary-attention KV is small because only one in four layers is full attention, but its DeltaNet recurrent state and exact current runtime buffers are **NOT PROVEN** here. More importantly, the ~48.4 GB weight artifact does not fit.

Machine-readable calculations: `candidate_architectures.json` and `memory_comparison.json`.

## 8. Storage / I/O economics

The sparse I/O model distinguishes two regimes:

1. **Resident Qwen3-Coder 30B-A3B:** steady-state SSD expert traffic should be near zero after paging settles; quality/performance becomes primarily compute + memory-bandwidth + runtime-placement constrained.
2. **Forced expert streaming:** the selected routed expert class is estimated at ~1.10 GB/token. At the measured 2,495.92 MiB/s, the I/O-only ceiling is ~2.37 tok/s at 0% expert-cache hit, ~3.17 at 25%, ~4.75 at 50%, ~9.50 at 75%, and ~23.7 at 90%, before compute/transfer.

These are explicitly I/O-only upper bounds. They are not throughput predictions.

Qwen3-Next has an estimated ~0.91 GB selected-expert bytes/token and an I/O-only no-cache ceiling ~2.87 tok/s, but its large non-expert/resident footprint and hybrid state make a streaming deployment materially riskier than Qwen3-Coder 30B-A3B.

Evidence: `io_comparison.json`.

## 9. Trunk versus expert RAM allocation

Kimi K3's own measurements settle the Kimi-specific question: RAM given to its 108.81 GB always-active trunk is generally more valuable than a small expert cache. The repo reports 108.81 GB trunk bytes/token versus 25.83 GB no-cache expert bytes/token; its fixed-budget experiments favor trunk-first allocation.

That conclusion must **not** be transferred blindly to Qwen3-Coder 30B-A3B. On this laptop the preferred policy is simpler: keep the whole ~17.3 GiB Q4 model resident/mapped if practical, rather than creating a custom trunk/expert split. If memory pressure forces partial residency, llama.cpp's existing tensor placement and `--n-cpu-moe` controls should be tested before any cache scheduler is built.

## 10. Packed-weight compute feasibility

### kimi-k3-in-c

`k3_matmul_mxfp4` consumes packed MXFP4 weights and scales directly. The hot expert path does not inflate a 17.55 MB packed expert to FP16/BF16 first. This is a core reason the streamed active set remains manageable.

### llama.cpp

Current source already contains the analogous building blocks for GGUF quantization:

- CPU quantized `MUL_MAT_ID` / expert paths;
- Vulkan top-k MoE and expert-count grouping shaders;
- Vulkan quantized matmul expert shaders (`mul_mmq.comp`, `mul_mm_id_funcs.glsl`);
- SYCL top-k MoE and quantized expert vector/matmul paths.

Therefore a Q4/Q5 MoE does **not** require global expansion to FP16/BF16 before compute.

Can sparse expert tensors compute directly from mapped/paged buffers? On CPU, mapped host weights are compatible with the loader/backend model. On Arc Vulkan, current source reports `mmap_support=false` for an integrated GPU device buffer, so the GPU path should be understood as host-loaded/mapped data plus backend transfer/offload rather than zero-copy direct execution from the file mapping. Exact page/transfer behavior for Qwen3-Coder on Arc remains **NOT PROVEN** until measured.

## 11. Existing runtime support

At llama.cpp commit `7798007...`:

- `LLM_ARCH_QWEN3MOE`, `LLM_ARCH_QWEN3NEXT` and `LLM_ARCH_KIMI_K3` are registered.
- `qwen3moe.cpp`, `qwen3next.cpp`, and `kimi-k3.cpp` model implementations exist.
- `llama-bench` exposes `--n-cpu-moe`.
- load modes include mmap/mlock/direct-I/O variants.
- `ggml-backend.cpp` explicitly optimizes MoE offload by identifying used experts and copying only those experts, grouping adjacent experts where possible.
- Vulkan and SYCL both contain MoE top-k and quantized expert kernels.

Candidate classification:

| Candidate | llama.cpp | Ollama | Arc Vulkan |
|---|---|---|---|
| Qwen3-Coder-30B-A3B | `SUPPORTED_NOW` | `SUPPORTED_WITH_LIMITATIONS` | `SUPPORTED_WITH_LIMITATIONS` |
| Qwen3-30B-A3B | `SUPPORTED_NOW` | `SUPPORTED_WITH_LIMITATIONS` | `SUPPORTED_WITH_LIMITATIONS` |
| Qwen3-Next-80B-A3B | `SUPPORTED_NOW` | `SUPPORTED_WITH_LIMITATIONS` | `SUPPORTED_WITH_LIMITATIONS` |

“With limitations” means the architecture/import path exists, but this exact quantized model was not loaded on this Arc 140V in A2.S0. A2.S0 intentionally did not download large candidate weights.

Evidence: `runtime_support.json`.

## 12. CPU versus Arc 140V execution

Do not assume all-MoE-on-GPU is optimal. Lunar Lake uses unified physical memory, but backend allocation/transfer semantics still matter.

The first qualification should test, in order:

1. Ollama/Vulkan automatic placement, because A0 established it as the operationally strongest local path.
2. direct current llama.cpp Vulkan with the same GGUF and context fixture.
3. llama.cpp CPU-MoE split via `--n-cpu-moe` while keeping compatible dense/attention work on Arc, because current source explicitly supports this control.
4. SYCL only if the current build can be obtained without turning the experiment into a toolchain project.

No custom Arc kernel is justified in A2.S0.

## 13. Context cost

Sparse FFNs reduce decode compute but do not automatically reduce prefill/attention cost.

- Qwen3-Coder 30B-A3B uses conventional GQA. KV is modest because it has only 4 KV heads, but prefill still has ordinary attention complexity and must be measured at 1K/4K/8K/16K.
- Qwen3-30B-A3B has the same architectural shape; observed official config advertises 40,960 positions.
- Qwen3-Next uses a hybrid of DeltaNet and periodic full attention, so its sequence-growing KV is much lower, but recurrent-state implementation cost and long-context prefill on llama.cpp/Arc are not yet measured.
- Kimi K3 has 69 fixed-state KDA layers, but 24 MLA layers still maintain sequence-dependent context. The released C runtime caches expanded keys/values, ~2.37 MB per position across those layers, so long context remains a major RAM cost.

Decode advantage and prefill advantage must therefore be evaluated separately.

## 14. Quality potential

Quality remains product criterion #1.

| Candidate | Coding evidence | Reasoning evidence | Context evidence | Confidence |
|---|---|---|---|---|
| Qwen3-Coder-30B-A3B | coding-specialized family, agentic coding positioning | strong family-level preselection | long-context coding design | HIGH for preselection only |
| Qwen3-30B-A3B | general model, not coding-specialized | strong Qwen3 family | 40,960 config observed | MEDIUM |
| Qwen3-Next-80B-A3B | general instruct, not chosen for coding specialization | newer hybrid architecture | 262,144 config observed | MEDIUM |

No candidate is declared production-quality from a model card or leaderboard. The unchanged local2api 25-case suite and manual rubric remain mandatory.

The A0 control remains extremely weak: 7B `LOCAL_SAFE` 1/9, `LOCAL_ACCEPTABLE` 2/11, intended-local 3/20. That makes the next candidate's quality uplift easy to detect, but does not lower the production bar.

Evidence: `quality_evidence.json`.

## 15. Quality-per-resource research metrics

The useful qualitative comparison is:

- Dense 14B: 14B active for ~8 GiB weights; easiest runtime and memory fit.
- Dense 32B: 32B active for ~18.3 GiB weights; high active compute and tight memory.
- Qwen3-Coder 30B-A3B: ~3.3B active for ~17.3 GiB resident weights; significantly lower active compute while retaining ~30B-total capacity and coding specialization.
- Qwen3-Next 80B-A3B: ~3B active but ~48 GB artifact; active compute is attractive but storage/residency risk dominates this machine.

“Quality / active params”, “quality / RAM” and “quality / estimated bytes/token” remain research lenses only. Quality has not yet been measured locally for the sparse candidates, so no fabricated numeric quality-efficiency score is emitted.

## 16. Implementation complexity

| Path | Complexity | Reason |
|---|---|---|
| Dense 14B existing runtime | LOW | ordinary resident/mmap GGUF; already proven family of mechanisms |
| Dense 32B existing runtime | LOW–MEDIUM | no new runtime, but memory/KV pressure and placement tuning are tight |
| Sparse Qwen3 30B-A3B existing runtime | MEDIUM | architecture/kernels exist; requires model-specific Arc/CPU placement qualification |
| Sparse MoE requiring llama.cpp patch | HIGH | tensor residency/expert paging behavior becomes maintenance-sensitive |
| Custom Kimi-style runtime | EXTREME | custom loader, packed kernels, router, cache, direct-I/O scheduler, context implementation and parity burden |

The study found no reason to fork AirLLM or build a new runtime.

## 17. Source-copy assessment

| Kimi-K3 concept | Reuse idea | Reuse code | Reason |
|---|---|---|---|
| packed compute | YES | NO now | llama.cpp already supplies quantized kernels; copy would duplicate backend work |
| expert indexing | YES | NO now | useful architecture pattern, but GGUF tensor model differs |
| cache simulator | YES | MAYBE later | Apache-2.0 permits reuse with obligations, but a clean model-specific simulator is simpler |
| trunk residency | YES | NO | policy concept is transferable; implementation is Kimi container-specific |
| direct I/O | YES | NO | llama.cpp already has load-mode/direct-I/O infrastructure |
| routing trace | YES | NO now | trace/replay methodology is valuable; instrumentation should fit llama.cpp/local2api evidence format |

Kimi and AirLLM are Apache-2.0; llama.cpp is MIT. No source was copied into local2api in A2.S0.

## 18. Master comparison table

| Metric | Dense 14B | Dense 32B | Qwen3-Coder 30B-A3B | Qwen3-30B-A3B | Qwen3-Next 80B-A3B |
|---|---:|---:|---:|---:|---:|
| Total params | 14B | 32B | 30.5B | 30.5B | ~80B |
| Active params/token | 14B | 32B | ~3.3B | ~3.3B | ~3.0B |
| Total Q4 size | ~8.00 GiB | ~18.29 GiB | ~18.6 GB (~17.3 GiB) | ~18.6 GB class | ~48.4 GB class |
| Always-active size | ~8.00 GiB | ~18.29 GiB | ~0.92 GB est. | ~0.92 GB est. | ~1.63 GB est. excluding fixed state |
| Active expert bytes/token | N/A | N/A | ~1.10 GB est. | ~1.10 GB est. | ~0.91 GB est. |
| KV @ 8K F16 | ~1.50 GiB | ~2.00 GiB | ~0.75 GiB | ~0.75 GiB | ~0.19 GiB conventional attention + recurrent state NOT PROVEN |
| KV @ 16K F16 | ~3.00 GiB | ~4.00 GiB | ~1.50 GiB | ~1.50 GiB | ~0.38 GiB conventional attention + recurrent state NOT PROVEN |
| RAM fit | GOOD | TIGHT | PLAUSIBLE/TIGHT | PLAUSIBLE/TIGHT | NO full residency |
| SSD bytes/token | ~0 when resident; 8 GiB if fully streamed | ~0 when resident; 18.29 GiB if fully streamed | ~0 preferred resident; ~1.10 GB expert class if forced streaming | same class | streaming required; exact total NOT PROVEN |
| I/O ceiling tok/s | 0.305 if fully streamed | 0.133 if fully streamed | ~2.37 if selected experts streamed with 0% hits; N/A resident | ~2.37 modeled | ~2.87 expert-only modeled; trunk/state excluded |
| Context risk | MEDIUM | HIGH | MEDIUM | MEDIUM | MEDIUM/NOT PROVEN |
| llama.cpp support | SUPPORTED_NOW | SUPPORTED_NOW | SUPPORTED_NOW | SUPPORTED_NOW | SUPPORTED_NOW |
| Ollama support | SUPPORTED_NOW class | SUPPORTED_NOW class | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS |
| Arc Vulkan support | existing dense path proven at 7B | model-specific NOT PROVEN | kernels/path exist; exact model NOT PROVEN | same | same |
| Quality potential | MEDIUM–HIGH candidate-dependent | HIGH candidate-dependent | **HIGH for coding preselection** | MEDIUM–HIGH | HIGH general, coding fit less direct |
| Implementation cost | LOW | LOW–MEDIUM | MEDIUM | MEDIUM | HIGH if streaming required |
| Main risk | insufficient quality uplift | RAM/compute pressure | exact Arc throughput + production quality | coding quality vs Coder | weight residency/streaming + hybrid state |
| Recommendation | **run as A2.1 control** | **BLOCKED** | **qualify before dense 32B** | runner-up | defer |

No empty cells are intentionally left unresolved; uncertain entries are explicitly marked `NOT PROVEN` or modeled.

## 19. Practical tests completed

- Updated and pinned all three reference repos.
- Replayed Kimi's included real expert-routing trace with the target SSD measurement.
- Ran an additional deterministic 0/1/2/4/8/12 GB cache replay and reuse-distance analysis.
- Verified Kimi source paths for direct I/O, router, expert cache, prefetch, MXFP4 and KDA/MLA state.
- Verified current llama.cpp architecture registry for Qwen3MoE/Qwen3Next/Kimi-K3.
- Verified current llama.cpp CPU-MoE control, selective expert transfer and Vulkan/SYCL MoE kernels.
- Verified local Ollama and direct llama-server versions.
- Kimi C build was **NOT RUN** because `cmake` and GCC are not present in this shell; MSVC `cl` exists. This is not a blocker to the source/modeling gate and no toolchain was installed merely to make a fixture test pass.
- No Kimi weights or hundreds-of-GB models were downloaded.
- Repository QA in the project venv: **15 passed in 0.75 s**; `python -m compileall -q src tests scripts`: PASS; all 8 A2.S0 JSON files parse successfully; generated-modeling JSON hashes were unchanged after rerun.
- A first bare `pytest` invocation used the global Miniforge interpreter and failed collection because the editable local package was absent from that interpreter. The project `.venv` is the repository's valid QA environment; no source fix was made for the global-environment failure.

## 20. Main uncertainties / NOT PROVEN

- Production coding/repository quality of every sparse candidate.
- Actual Qwen3-Coder 30B-A3B TTFT, prompt tok/s, generation tok/s, Arc utilization and sustained memory on this laptop.
- Exact GGUF tensor-by-tensor always-active/expert byte census; proportional estimates are used for active byte modeling.
- Exact Windows page-fault/swap behavior at ~17–19 GiB model residency.
- Arc Vulkan versus CPU-MoE versus SYCL winner for Qwen3-Coder.
- Qwen3-Next fixed recurrent-state bytes and practical hybrid-attention performance in the current runtime.
- Routing locality for Qwen3-Coder/Qwen3/Qwen3-Next. Kimi's trace is not evidence for them.
- Thermal/power behavior remains unmeasured.

## 21. Final gate decision

# `TEST_SPARSE_BEFORE_DENSE_32B`

Why:

1. A concrete coding-specific sparse model now exists whose **full Q4 artifact plausibly fits** the laptop, avoiding the central Kimi/AirLLM storage-streaming penalty.
2. Its ~3.3B active parameter workload is radically smaller than a dense 32B control at roughly the same total Q4 storage class.
3. llama.cpp already has the model architecture, quantized MoE compute, Vulkan/SYCL MoE kernels, CPU-MoE placement controls and selective expert transfer. The first test does not require a custom engine.
4. Kimi K3 proves useful runtime patterns but also proves that huge-model low-RAM streaming remains far too slow for this product target.
5. Quality potential is promising enough to justify a real test, but remains explicitly unproven. Therefore the result is a **qualification decision**, not a production endorsement.

### Exact next experiment

Keep A2.1 14B as the dense control, then qualify **Qwen3-Coder-30B-A3B-Instruct Q4_K_M** before dense A2.2 32B. Use the identical local2api quality suite, deterministic generation settings and 1K/4K/8K/16K fixtures. Run Ollama/Vulkan first, then direct llama.cpp Vulkan; add `--n-cpu-moe` placement A/B if the full-GPU/automatic path shows memory or throughput pressure. Measure quality first, then TTFT/decode, memory/commit, failures and context scaling.

Dense A2.2 32B stays **BLOCKED** until the 14B control and sparse qualification show whether spending ~18 GiB of weight capacity on dense 32B is better or worse than spending it on a 30B-total/3B-active MoE.

## Evidence index

- `docs/result/evidence/a2_s0/reference_revisions.json`
- `docs/result/evidence/a2_s0/candidate_architectures.json`
- `docs/result/evidence/a2_s0/memory_comparison.json`
- `docs/result/evidence/a2_s0/io_comparison.json`
- `docs/result/evidence/a2_s0/cache_simulation.json`
- `docs/result/evidence/a2_s0/runtime_support.json`
- `docs/result/evidence/a2_s0/quality_evidence.json`
- `docs/result/evidence/a2_s0/decision_matrix.json`
- `scripts/a2s0_compare.py`
- `scripts/a2s0_cache_sim.py`

External candidate references used for preselection include the official Qwen Hugging Face model/config repositories and current GGUF listings. They are preselection/provenance sources only; all production conclusions remain gated on local measurement.
