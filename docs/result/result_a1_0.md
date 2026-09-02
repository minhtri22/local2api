# A1.0 — Adaptive Local Engine Feasibility Study

Date: 2026-09-02

## Executive summary

**Verdict: `GO_EXISTING_RUNTIME_ONLY`.**

The target laptop can plausibly run a 14B Q4 model and may fit a tightly configured 32B Q4 model using existing llama.cpp/Ollama mechanisms, but the measured NVMe bandwidth makes AirLLM-style dense weight streaming unattractive. With a conservative measured sequential read rate of 2,495.92 MiB/s, reading all Q4 weights once per generated token imposes I/O-only ceilings of about 0.305 tok/s for 14B, 0.133 tok/s for 32B and 0.061 tok/s for 70B. Even 75% residency only raises those bounds to about 1.22, 0.53 and 0.24 tok/s respectively, before device copy and compute.

Therefore A1.1 is not opened. The correct next Track-A step is A2: benchmark 14B using existing llama.cpp/Ollama mmap/offload first. A custom residency engine is not justified by current evidence.

## A0 baseline

A0 established:

- 7B hardware/runtime feasibility: **PASS**;
- 7B coding/repository production quality: **FAIL**;
- Arc 140V Vulkan acceleration works;
- Ollama was operationally better than the tested direct llama-server configuration at long context;
- 7B remains a baseline/control/utility model, not the production coding target.

This means A1.0 is not trying to make 7B faster. It asks whether larger models can create useful local capability on the same 32 GB machine.

## P0.1 — Memory economics

### Weight model

The Q4 weight estimate is based on the exact HW1 Qwen2.5-Coder 7B Q4_K_M artifact: 4.36 GiB for 7.62B parameters, approximately **4.91 effective bits/weight**. This captures block-quantization metadata overhead and is 22.75% above an idealized 4-bit packing assumption.

Formula:

`weight_bytes = parameter_count * 4.91 / 8`

| Representative model | Q4 weight estimate |
|---|---:|
| 14B dense | 8.00 GiB |
| 32B dense | 18.29 GiB |
| 70B dense | 40.01 GiB |
| 46.7B MoE representative | 26.69 GiB total weights |

### Practical RAM budget

A planning reserve of 11 GiB is held outside model/runtime memory:

- Windows 11: 6.0 GiB;
- VS Code: 2.5 GiB;
- local2api/tools: 0.5 GiB;
- filesystem cache reserve: 2.0 GiB.

This leaves **21 GiB** as the practical model/runtime budget on a 32 GiB system. The reserve is an explicit planning assumption, not a measured Windows minimum.

### KV cache model

Formula for a conventional GQA transformer cache:

`KV bytes = 2 * layers * kv_heads * head_dim * tokens * bytes_per_element`

Representative architecture assumptions are Qwen/Llama-family scale values: 48/64/80 layers for the 14B/32B/70B classes, 8 KV heads and head dimension 128. F16 uses 2 bytes/element; the q4 column is an approximate 0.5 bytes/element lower-storage case and excludes block metadata.

| Model | 4K F16 KV | 8K | 16K | 32K |
|---|---:|---:|---:|---:|
| 14B | 0.75 GiB | 1.50 | 3.00 | 6.00 |
| 32B | 1.00 GiB | 2.00 | 4.00 | 8.00 |
| 70B | 1.25 GiB | 2.50 | 5.00 | 10.00 |

Approximate q4 KV is one quarter of the F16 figures.

### Memory conclusion

14B Q4 is comfortably inside the practical budget at useful contexts. 32B Q4 weights alone fit the 21 GiB planning budget, but leave only ~2.7 GiB for KV and runtime buffers; at 16K F16 KV it does not fit this safety model, while q4 KV plus tight buffers may. 70B Q4 cannot be resident within the practical budget.

Machine-readable calculations: `docs/result/evidence/a1_0/memory_model.json`.

## P0.2 — I/O economics

### Measured SSD

Physical disk reported by Windows: **KINGSTON OM8PGP41024Q-AA, NVMe SSD**.

A read-only benchmark scanned the existing 4,683,074,048-byte HW1 GGUF three times using 8 MiB reads; no large benchmark file was written.

Sequential read results:

- 2,629.07 MiB/s;
- 2,495.92 MiB/s;
- 2,511.06 MiB/s.

Median: **2,511.06 MiB/s**. For lower-bound modeling, the slowest measured full pass, **2,495.92 MiB/s**, is used.

Random 64 KiB buffered reads over 2,048 samples measured 0.0118 ms median / 0.0221 ms p95. These random figures are strongly cache-sensitive and are recorded only as a local observation, not as raw-NVMe latency.

The sequential test is also subject to Windows/filesystem cache effects; therefore it is evidence of observed host read bandwidth, not a guaranteed cold-device specification.

### Naive full streaming lower bound

Formula:

`minimum_seconds_per_token = bytes_read_per_token / 2,495.92 MiB/s`

This is an optimistic I/O-only bound: device transfer, decompression/dequantization, graph work and compute can only add time unless overlapped.

| Dense model | Stream/token | I/O-only minimum | Theoretical max |
|---|---:|---:|---:|
| 14B Q4 | 8.00 GiB | 3.283 s | **0.305 tok/s** |
| 32B Q4 | 18.29 GiB | 7.504 s | **0.133 tok/s** |
| 70B Q4 | 40.01 GiB | 16.416 s | **0.061 tok/s** |

Naive dense streaming is therefore physically incompatible with an interactive coding tier.

### Partial residency

| Model | 25% resident | 50% resident | 75% resident |
|---|---:|---:|---:|
| 14B | 0.406 tok/s | 0.609 | 1.218 |
| 32B | 0.178 tok/s | 0.267 | 0.533 |
| 70B | 0.081 tok/s | 0.122 | 0.244 |

Even 75% residency leaves dense 32B below 1 tok/s on the I/O-only bound. For 14B, 75% residency is slower than simply fitting the whole model in ordinary memory, which the memory model says is already practical.

### Layer-group prefetch

Prefetch can hide I/O only if:

`read_time(next group) + host/device transfer <= compute_time(current group)`

and enough staging memory exists to hold the current and prefetched groups concurrently.

For dense decoding, total I/O volume per token does not disappear. At 32B, non-resident streaming of even half the model requires ~9.15 GiB/token. Full overlap would require several seconds of compute/token, which would itself imply sub-interactive generation. Prefetch improves pipeline utilization but does not change the fundamental bandwidth equation.

Machine-readable calculations: `ssd_benchmark.json` and `io_model.json`.

## P0.3 — Accelerator-path feasibility

### llama.cpp Vulkan

Already proven locally in A0/HW1 on Arc 140V. Source inspection shows model placement is abstracted through GGML backend buffer types, while Vulkan implements buffer allocation, tensor set/get/copy and graph dispatch in `ggml-vulkan.cpp`. This is a viable compute substrate.

### llama.cpp SYCL / oneAPI

The cloned llama.cpp tree contains a full Intel-targeted SYCL backend (`GGML_SYCL_TARGET=INTEL`) with Level Zero, oneDNN options, host-pinned memory and device-buffer code under `ggml/src/ggml-sycl/`. Official llama.cpp SYCL documentation lists Windows 11 and Lunar Lake built-in Arc GPUs as supported/verified classes. This makes SYCL a credible A2 runtime A/B candidate, but A1.0 does not claim it is faster than Vulkan on this specific machine because no local SYCL benchmark was run.

Source: https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/SYCL.md

### PyTorch XPU

PyTorch now provides `torch.xpu` for Intel GPU, with official Windows 11 support for Core Ultra Series 2 / Lunar Lake and XPU wheels. Thus an AirLLM-style port is technically possible at the PyTorch device layer by migrating CUDA device references to XPU. The project venv does not currently contain PyTorch, so no local XPU execution result is claimed.

Sources:

- https://docs.pytorch.org/docs/stable/xpu.html
- https://docs.pytorch.org/docs/main/notes/get_start_xpu.html

### AirLLM on Intel Arc

**Stock AirLLM: not viable as-is for the desired path.**

Source evidence:

- default `device="cuda:0"`;
- pinned-memory optimization is gated by `torch.cuda.is_available()`;
- optional 4/8-bit `compress_layer_state_dict()` requires bitsandbytes and explicitly calls `v.cuda()`;
- compression disables prefetch;
- the whole execution model is PyTorch/Transformers/safetensors rather than GGUF/GGML.

Because PyTorch XPU exists, a port is technically possible. It is not attractive here: it would duplicate llama.cpp loader, quantization, backend, KV, server and sampling infrastructure while offering no escape from the measured dense streaming bandwidth bound.

### AirLLM source implementation map

| Concept | AirLLM implementation | File/function | Có thể reuse idea? | Có thể reuse code? | Intel Arc blocker |
|---|---|---|---|---|---|
| Model splitting / layer sharding | Per-module safetensors split or hard-link/copy passthrough | `air_llm/airllm/utils.py::split_and_save_layers` | Yes | License permits, but not useful for GGUF path | PyTorch/safetensors format instead of GGUF |
| Layer loading from disk | Load complete module shard; selective safetensors reads for subsets | `utils.py::load_layer`, `load_layer_subset` | Yes | Prefer clean reimplementation | Produces PyTorch tensors |
| Layer unload / memory release | Move streamed parameters back to `meta` after forward | `airllm_base.py::_post_hook`, `_expert_post_hook` | Yes | No direct reuse | GGML has a different tensor/buffer lifecycle |
| Prefetch | One worker reads the next streamed module while current module computes | `AirLLMBaseModel.__init__`, `_pre_hook` | Yes | Reimplement | Python executor and PyTorch state dicts |
| CPU -> accelerator transfer | Materialize state dict on configured execution device | `airllm_base.py::move_layer_to_device` | Yes | No | Stock device assumptions are CUDA-oriented |
| Compression path | bitsandbytes NF4/8-bit conversion; compression disables prefetch | `utils.py::compress_layer_state_dict`, constructor | Concept only | No | Explicit `.cuda()` plus bitsandbytes dependency |
| Skeleton / meta tensors | Instantiate HF model with empty weights on `meta` | `_instantiate_on_meta`, `init_model` | Yes conceptually | No | llama.cpp already has GGUF tensor metadata/model graph abstractions |
| Expert streaming for MoE | Load only routed expert tensors, then evict expert after use | `_setup_expert_streaming`, `_expert_pre_hook`, `_expert_post_hook` | **Strong candidate** | Reimplement | Requires expert-aware GGUF/backend-buffer residency |
| Caching / residency | Current module resident, next module optionally host-prefetched; selected modules can stay resident | `_pre_hook`, `_post_hook`, resident-module setup | Yes | Reimplement | No general device-neutral cache planner |
| Generate loop | Delegates to Transformers; hooks execute on every model traversal/token | `generate`, underlying HF forward | Yes as evidence | No | Forces repeated streaming in dense models |
| CUDA assumption | Default `cuda:0`, CUDA availability tests | constructor, `load_layer_to_cpu` | No | No | Must port to XPU/device-neutral path |
| Pinned memory | Pins prefetched CPU tensors below 2 GiB threshold | `load_layer_to_cpu` | Yes | Reimplement | CUDA-specific gating in stock implementation |
| bitsandbytes | Optional 4/8-bit compression backend | constructor, `compress_layer_state_dict` | No | No | Stock code path explicitly requires CUDA-style operations |
| PyTorch device model | Parameters cycle CPU/device/meta under HF module hooks | `AirLLMBaseModel` | Concept only | No | Duplicates GGML/Vulkan/SYCL execution stack |

### Can AirLLM ideas be ported while retaining llama.cpp compute?

Yes, technically. The reusable ideas are residency policy, next-group prefetch and especially per-expert on-demand loading. llama.cpp already has mmap/direct-I/O, backend buffer abstractions, asynchronous graph execution, partial GPU layer placement and selected lazy-read tensor support. Therefore any future adaptive scheduler should sit around llama.cpp model-loader/backend-buffer abstractions instead of reimplementing kernels.

## P0.4 — Residency strategy comparison

| Strategy | RAM | SSD I/O during decode | GPU use | Complexity | Throughput/TTFT expectation | Long-context fit |
|---|---|---|---|---|---|---|
| Fully resident | Highest | Minimal after load | Best | Low | Best decode; normal load TTFT | KV becomes main growth term |
| llama.cpp mmap | Host virtual residency + OS cache | Demand paging, reusable across tokens | CPU/GPU split | Low | Better than explicit reread; page faults possible | Good if RAM reserve maintained |
| Partial GPU offload | Weights stay CPU/mmap, subset GPU | No mandatory disk reread if host-resident | Mixed | Low | Existing practical baseline | KV + host weights compete for unified memory |
| OS page cache/lazy access | Flexible | Workload-dependent faults | Mixed | Low | Can degrade sharply under pressure | Sensitive to swap/cache eviction |
| Explicit dense layer streaming | Low resident weight RAM | Very high every token | Bursty | High | **Rejected by measured I/O bound** | Weight problem improves; context problem unchanged |
| Layer-group residency | Tunable | High for non-resident groups | Better batching | Medium/high | Still bandwidth-bound when large fraction non-resident | KV unchanged |
| Prefetch | Adds staging RAM | Same bytes, overlapped | Higher utilization | Medium | Helps only when compute hides I/O | KV unchanged |
| MoE expert streaming/cache | Total weights may exceed RAM; hot experts resident | Only cold/active experts | Potentially useful | High | Potentially viable if routing locality is strong | KV still independent |

## P0.5 — Context vs weight bottleneck

These are separate problems.

**Weight residency problem:** model weights do not fit the chosen host/device memory budget. mmap, CPU/GPU split, expert residency or explicit streaming can address this.

**Context/prefill problem:** long prompts require more attention/prefill work and larger KV. Weight streaming does not reduce attention complexity, prompt processing cost or KV growth. A larger model generally increases per-token compute and often increases KV per token/layer.

For 14B, weights fit but F16 KV grows from ~0.75 GiB at 4K to ~6 GiB at 32K. For 32B, 16K F16 KV is ~4 GiB, enough to push the practical model over the 21 GiB safe model/runtime budget when combined with weights and buffers. Quantized KV can postpone that boundary but does not eliminate prefill compute.

Therefore an AirLLM-like mechanism cannot be described as a solution to large context.

## P0.6 — Dense vs MoE

The representative sparse case is Mixtral-scale 46.7B total / ~12.9B active parameters per token. Its Q4 total-weight estimate is ~26.7 GiB, above the practical resident budget, but active compute is far below a same-total-parameter dense model.

MoE can be more favorable only if experts are independently addressable and routing has locality. AirLLM's `load_layer_subset()` plus per-expert hooks demonstrates the architectural possibility: selected expert tensors can be loaded without the full layer. llama.cpp would need an expert-aware residency/cache policy to obtain that benefit.

However, “active parameters” do not directly equal storage traffic. If routing changes experts frequently and the resident expert cache misses, SSD reads can dominate. A large shared attention trunk and KV remain resident costs. Thus MoE is a **more promising future adaptive-residency target than dense 70B**, but it is not automatically practical on this laptop.

## P0.7 — Implementation options

| Option | Arc compatibility | Reuse mature stack | Maintenance | Expected value | Decision |
|---|---|---|---|---|---|
| A. Existing Ollama/llama.cpp | Proven Vulkan; SYCL available | Maximum | Low | High for 14B / constrained 32B | **Select now** |
| B. Extend llama.cpp residency | Strong | GGUF, KV, kernels, graph, server retained | Medium/high | Useful mainly for sparse/expert or special lazy tensors | Defer unless A2 exposes a concrete gap |
| C. Fork/port AirLLM | PyTorch XPU technically possible; stock code CUDA-centric | Low | High | Dense streaming still I/O-bound | Reject |
| D. New runtime | Must recreate device + model stack | Minimal | Very high | No evidence of unique benefit | Reject |

Answer to the architecture question: **if adaptive residency is ever justified, extend llama.cpp rather than create a new runtime; for current A1.0, do not build adaptive residency at all.**

## P0.8 — GO / NO-GO criteria

Thresholds are derived from intended use, not retrofitted to the result:

### Throughput classes

- **Interactive:** >= 8 tok/s — around the observed 7B local baseline; suitable for live coding/chat.
- **Slow interactive:** 3–8 tok/s — usable for deliberate private reasoning.
- **Batch/offline:** 1–3 tok/s — useful only where privacy/cost outweighs delay.
- **Unusable as a production tier:** < 1 tok/s sustained decode.

The <1 tok/s boundary is chosen because even a modest 200-token answer requires >200 seconds before accounting for TTFT, making it unsuitable for the project's interactive coding goal.

### TTFT targets

- short coding request: target <= 3 s;
- deep/private reasoning: <= 15 s can be acceptable;
- batch/offline: <= 60 s when explicitly chosen.

### Resource safety

- maintain the 11 GiB planning reserve where possible;
- no sustained swap storm/page-fault thrash;
- Windows/VS Code must remain usable;
- context allocation must not silently consume the reserve.

### Implementation viability

- no rewrite of GGUF/tokenizer/KV/kernels/sampler/server;
- prototype must expose measurable residency/transfer telemetry;
- result must be reproducible against an existing-runtime baseline.

## Final A1.0 verdict

# `GO_EXISTING_RUNTIME_ONLY`

Reasons:

1. 14B Q4 fits the practical memory model without adaptive streaming.
2. 32B Q4 is tight but potentially testable using mmap/offload/quantized KV; that should be proven before custom engineering.
3. Dense AirLLM-style streaming is physically bounded to ~0.305/0.133/0.061 tok/s for 14B/32B/70B on measured host read bandwidth.
4. llama.cpp already supplies the loader, mmap/direct-I/O, backend buffers, Vulkan/SYCL kernels, KV and graph execution needed for the next experiment.
5. AirLLM's strongest unique idea is per-expert residency for MoE, which is interesting but not required to answer the immediate 14B/32B feasibility question.

### Required A1.1 choice

**5. không build adaptive engine.** A1.1 remains closed under the roadmap gate. If later MoE evidence justifies reopening adaptive work, the preferred implementation would then be **1. patch/extend llama.cpp**, not a wrapper that cannot control tensor residency, not an AirLLM fork, and not a new runtime.

## Limitations

- No 14B/32B/70B model was downloaded or benchmarked.
- SSD results use ordinary read-only file I/O and can contain OS cache effects; the conservative minimum observed full-file pass is used.
- The 4.91 effective bpw is calibrated from one Q4_K_M artifact; exact GGUF sizes vary by architecture/tensor mix.
- KV formulas use representative GQA architecture dimensions, not a specific future model config.
- PyTorch XPU was researched from official documentation but not locally executed because the project environment does not contain PyTorch.
- SYCL is source/documentation-feasible for Lunar Lake but was not A/B benchmarked in A1.0.
- MoE viability depends on model-specific expert layout and routing locality and remains theoretical here.

## Recommended next action

Proceed to **A2 with 14B only**, using existing Ollama/llama.cpp first. Benchmark Vulkan and, if setup cost is reasonable, SYCL using identical prompts/context and quality gates. Only if 14B establishes value should 32B be downloaded/tested. Keep Track B independent and continue B1 Context Ownership in parallel.

## Evidence and reproducibility

- `docs/result/evidence/a1_0/reference_architecture.md`
- `docs/result/evidence/a1_0/runtime_capabilities.json`
- `docs/result/evidence/a1_0/memory_model.json`
- `docs/result/evidence/a1_0/ssd_benchmark.json`
- `docs/result/evidence/a1_0/io_model.json`
- `scripts/a1_memory_model.py`
- `scripts/a1_ssd_benchmark.py`
- `scripts/a1_io_model.py`

Reference source revisions are pinned in `reference_architecture.md`.
