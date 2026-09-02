# v0.0.1-HW1-7B — Local production-gate qualification

Date: 2026-09-02

## Verdict

**Hardware/runtime feasibility: PASS.**

**7B production gate: FAIL / not qualified for general local coding use.**

**14B qualification: BLOCKED.** The project rule remains: do not start 14B until the 7B production gate is genuinely passed or the gate definition is explicitly revised.

The decisive result is not a crash or inability to load the model. Qwen2.5-Coder 7B Q4_K_M runs on the Intel Arc 140V, but the tested 7B model produced poor answers on the coding/repository capability suite and direct llama-server became impractically slow as context grew. Ollama handled long-context prompt ingestion much better, but generation remained only about 7–8 tok/s and quality was still inadequate.

## Target and provenance

- CPU: Intel Core Ultra 7 258V
- RAM: approximately 32 GB
- iGPU: Intel Arc 140V, Vulkan runtime reports 16 GB class device memory
- OS: Windows 11
- model: `Qwen2.5-Coder 7B Instruct`, Q4_K_M
- GGUF SHA256: `60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463`
- Ollama: `0.33.2`
- bundled llama-server: `0.3.0-dev`, build 1, commit `d222767c7`
- benchmark context: 16,384 tokens
- generation: temperature 0, top_p 1, seed 42

The same Ollama-owned GGUF blob was used for both runtimes.

## Corrected Ollama configuration

Two environment findings materially affected the benchmark.

First, `OLLAMA_KV_CACHE_TYPE=q4_0` with `OLLAMA_FLASH_ATTENTION=false` is invalid in this Ollama/llama-server build and caused HTTP 500 with:

```text
quantized V cache requires flash_attn to be enabled
```

Second, `OLLAMA_INTEL_GPU=true` did not enable the Arc 140V in Ollama 0.33.2. The runtime log explicitly requested `OLLAMA_IGPU_ENABLE=1`. The authoritative Ollama rerun therefore used:

```text
OLLAMA_FLASH_ATTENTION=true
OLLAMA_IGPU_ENABLE=1
OLLAMA_VULKAN=1
OLLAMA_KV_CACHE_TYPE=q4_0
OLLAMA_CONTEXT_LENGTH=16384
OLLAMA_NUM_PARALLEL=1
```

The startup log then identified `Vulkan0: Intel(R) Arc(TM) 140V GPU (16GB)` and projected roughly 4.7 GiB of device memory for the 7B model/runtime context.

## Input parity

The production-gate harness pre-renders canonical ChatML before sending requests so both runtimes receive the same prompt bytes. The fixture stores:

- rendered prompt SHA256;
- llama.cpp token IDs and token count;
- exact GGUF SHA256;
- fixed generation parameters.

Measured fixture sizes were:

| Label | Actual tokens |
| --- | ---: |
| 1K | 870 |
| 4K | 3,573 |
| 8K | 7,192 |
| 16K | 14,452 |

This closes the earlier input-parity gap.

## Context-scaling A/B

Each authoritative row below is the median of three measured requests after a warm-up request, with zero request failures.

| Context | Runtime | Median TTFT | Median wall | Prompt tok/s | Generation tok/s |
| --- | --- | ---: | ---: | ---: | ---: |
| 870 | Ollama / Vulkan | 213.93 ms | 3.263 s | telemetry unavailable | telemetry unavailable |
| 870 | direct llama-server / Vulkan | 6.806 s | 13.167 s | 127.99 | 9.74 |
| 3,573 | Ollama / Vulkan | 322.01 ms | 4.034 s | telemetry unavailable | telemetry unavailable |
| 3,573 | direct llama-server / Vulkan | 31.605 s | 38.393 s | 113.10 | 9.79 |
| 7,192 | Ollama / Vulkan | 201.90 ms | 7.987 s | 56,083.66* | 8.22 |
| 7,192 | direct llama-server / Vulkan | 61.840 s | 68.184 s | 116.39 | 9.94 |
| 14,452 | Ollama / Vulkan | 375.13 ms | 9.551 s | 103,091.61* | 6.87 |
| 14,452 | direct llama-server / Vulkan | 232.047 s | 243.377 s | 62.34 | 6.37 |

`*` Ollama's reported prompt timing at 8K/16K is strongly affected by its internal prompt-cache behavior during repeated identical prompts. It should not be interpreted as cold-prefill throughput. At 1K/4K, the streaming endpoint did not reliably expose native final timing fields, so prompt/generation throughput is deliberately recorded as unavailable instead of inferred.

### Runtime interpretation

Direct llama-server is not production-viable for long-context interactive use under this tested configuration: median TTFT rose from 6.8 s at 870 tokens to 232 s at 14,452 tokens.

Ollama is the better runtime candidate on this machine because its repeated-context behavior keeps TTFT below 0.4 s in this test. However, this does not rescue the 7B production gate because output generation remains roughly 7–8 tok/s at long context and, more importantly, the capability suite fails badly.

## Sustained OS telemetry

The isolated Ollama/Vulkan telemetry capture produced 171 process samples. Peak observations included:

| Process | Samples | Peak working set | Peak private memory |
| --- | ---: | ---: | ---: |
| llama-server child | 23 | 19,951.48 MB | 19,981.75 MB |
| ollama host | 20 | 89.55 MB | 108.45 MB |

Peak system committed memory observed during the capture was 45,506.85 MB.

These Windows process figures include unified-memory behavior around the iGPU/runtime and should not be interpreted as 20 GB of model weights. They are useful as an operational pressure signal: a 32 GB unified-memory laptop can run this workload, but system commit can materially exceed physical RAM.

The current PowerShell/CIM capture did not return usable page-fault counters, so page-fault behavior remains **not proven**. Thermal/power telemetry was also not captured in a trustworthy hardware source and remains **not proven**. No value is fabricated for either gate.

## Coding/repository capability suite

The 25-case deterministic smoke suite was run against the corrected Ollama/Arc 140V configuration.

| Intended class | Passed | Total | Mechanical pass rate |
| --- | ---: | ---: | ---: |
| LOCAL_SAFE | 1 | 9 | 11.1% |
| LOCAL_ACCEPTABLE | 2 | 11 | 18.2% |
| CLOUD_REQUIRED | 1 | 5 | 20.0% |

The scorer only checks required substrings, so these percentages are not claimed as a rigorous semantic benchmark. Manual inspection makes the conclusion more conservative, not less: several basic responses were malformed, repetitive, misunderstood the prompt, or produced incorrect code. Examples include an incorrect clamp helper, a FastAPI endpoint returning the wrong key, and failures to identify straightforward interface or test-contract issues.

Therefore the tested 7B model is **not qualified as a general local coding/repository backend**.

The safe routing policy from this evidence is:

- keep `CLOUD_REQUIRED` on cloud with no silent downgrade;
- do not classify repository reasoning or non-trivial code modification as `LOCAL_SAFE` for this 7B model;
- if 7B remains available, restrict it to explicitly degradable low-risk tasks where incorrect output can be cheaply verified;
- prefer Ollama over direct llama-server for the current 7B runtime path on this laptop.

## Gate matrix

| Gate | Status | Evidence |
| --- | --- | --- |
| Model loads/runs on Arc 140V | PASS | Vulkan model load and repeated requests |
| Same-model runtime A/B | PASS | clean Ollama and direct llama-server runs |
| Byte-identical fixture/provenance | PASS | prompt hashes, token IDs, GGUF hash |
| 1K/4K/8K/16K scaling | PASS as measurement | all four levels completed, zero request failures |
| Long-context direct llama-server usability | FAIL | 16K median TTFT ~232 s |
| OS memory/commit telemetry | PARTIAL PASS | captured; high unified-memory pressure observed |
| Page-fault telemetry | NOT PROVEN | counter unavailable in current harness |
| Thermal/power telemetry | NOT PROVEN | no trustworthy sensor evidence captured |
| Coding/repository quality | FAIL | 3/20 across intended local classes by mechanical scorer plus visibly poor manual outputs |
| 7B production qualification | **FAIL** | quality failure is sufficient to block the gate |
| 14B qualification | **BLOCKED** | gated on 7B production qualification |

## Authoritative evidence

Primary evidence for this conclusion:

- `docs/result/evidence/hw1_7b_prod_gate/input_parity.json`
- `docs/result/evidence/hw1_7b_prod_gate/context_fixture.json`
- `docs/result/evidence/hw1_7b_prod_gate/context_scaling_ollama_gpu_clean.json`
- `docs/result/evidence/hw1_7b_prod_gate/context_scaling_llama_server_clean.json`
- `docs/result/evidence/hw1_7b_prod_gate/sustained_ollama_gpu_telemetry.csv`
- `docs/result/evidence/hw1_7b_prod_gate/quality_ollama_gpu.json`

Older files in the same evidence directory are exploratory runs generated while isolating runtime contention/configuration problems. They are not used for the final gate verdict.

## Decision

Do not proceed to 14B under the current phase rule.

The evidence changes the architectural conclusion: **the laptop can execute a 7B local model, but “can run” is not equivalent to “useful production local engine.”** For local2api, the stronger next design question is whether Track A should narrow the local tier to cheap/verifiable tasks while Track B focuses on smart cloud routing, rather than optimizing a 7B coding model that has failed the capability gate.
