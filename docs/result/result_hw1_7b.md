# v0.0.1-HW1-7B — Local runtime qualification report

Date: 2026-09-02

Target device:

- Intel Core Ultra 7 258V
- 32 GB RAM
- Intel Arc 140V integrated GPU (16 GB reported by driver/runtime)
- Windows 11

## Objective

Qualify the 7B local tier before any 14B work. The candidate model is fixed to `Qwen2.5-Coder 7B Q4_K_M` so the experiment compares runtime behavior rather than model quality differences.

The current question is whether the laptop can run the 7B model reliably enough to justify continuing the local-first architecture and, only after that gate passes, testing a 14B candidate.

## Runtime configuration finding

The pre-existing Ollama environment contained an invalid combination for the selected KV cache:

```text
OLLAMA_KV_CACHE_TYPE=q4_0
OLLAMA_FLASH_ATTENTION=false
```

This produced:

```text
quantized V cache requires flash_attn to be enabled
```

The benchmark therefore used an isolated Ollama instance with:

```text
OLLAMA_FLASH_ATTENTION=true
OLLAMA_IGPU_ENABLE=1
OLLAMA_VULKAN=1
OLLAMA_CONTEXT_LENGTH=16384
```

No persistent Windows environment variables were changed.

## Same-model runtime A/B

Both Vulkan paths used the same Ollama-owned Qwen2.5-Coder 7B GGUF blob. The direct llama-server Vulkan backend was loaded through `ggml-vulkan.dll` and detected:

```text
Vulkan0: Intel(R) Arc(TM) 140V GPU (16GB)
```

Five-run sustained measurements:

| Runtime | Backend | Runs | Median TTFT | Median generation throughput |
| --- | --- | ---: | ---: | ---: |
| Ollama 0.33.2 | Arc 140V / Vulkan | 5 | 452.6 ms | 8.832 tok/s |
| llama-server build d222767c7 | Arc 140V / Vulkan | 5 | 140.8 ms | 9.387 tok/s |

Direct llama-server was about 6% faster in median sustained generation throughput in this sample and showed materially lower median TTFT.

Early Vulkan runs briefly reached about 15–16 tok/s, but later measurements converged around 8–10 tok/s. Those burst values are therefore not treated as sustained performance.

## CPU control

The CPuFriend llama-server binary was also tested as a CPU-only control with the same Qwen2.5-Coder 7B blob:

| Runtime | Backend | Runs | Median TTFT | Median generation throughput |
| --- | --- | ---: | ---: | ---: |
| llama-server CPuFriend build 85c55223c | CPU | 3 | 176.9 ms | 6.180 tok/s |

This confirms that Arc 140V Vulkan materially improves generation speed versus CPU-only execution on this laptop.

## Evidence files

- `hw1_qwen2.5-coder-7b-ollama-vulkan-r2.json`
- `hw1_qwen2.5-coder-7b-llama-server-vulkan-r2.json`
- `hw1_qwen2.5-coder-7b-llama-server-cpu.json`
- `hw1_qwen2.5-coder-7b-igpu.json`
- `hw1_qwen2.5-coder-7b.json`

The reproducible harness is `scripts/hw1_benchmark.py` and supports both Ollama and OpenAI-compatible llama-server endpoints.

## Gate assessment

### Performance feasibility: PASS

The 7B model runs successfully on the target laptop through Arc 140V Vulkan. Sustained generation around 9 tok/s is demonstrated on both Ollama and direct llama-server, and GPU acceleration is measurably better than the CPU control.

### Runtime stability: PASS for short qualification runs

Both Vulkan runtimes completed repeated local inference runs without model/runtime crashes during the measured benchmark after correcting the Flash Attention configuration.

### Final 7B production qualification: NOT YET COMPLETE

The following evidence is still required before calling the full 7B gate complete:

1. byte-identical rendered prompt/token input for Ollama vs direct llama-server;
2. working set, commit memory and page-fault telemetry;
3. thermal/power behavior during sustained runs;
4. coding/repository quality suite.

Accordingly, this report establishes **7B hardware/runtime feasibility**, but does not yet authorize moving to the 14B qualification stage.

## Decision

Do not download or benchmark 14B yet.

Complete the remaining 7B telemetry and quality gates first. If those pass, select the preferred 7B runtime and then run the 14B experiment with the same measurement protocol.
