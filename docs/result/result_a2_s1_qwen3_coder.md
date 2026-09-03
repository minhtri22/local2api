# A2.S1 — Qwen3-Coder-30B-A3B qualification, audited

Date: 2026-09-03. This report supersedes the conclusions in commit `a63a5ef`.

## Verdict and scope

**Final verdict: `SPARSE_INCONCLUSIVE`. Incremental short-task quality: `INCREMENTAL_QUALITY_SMALL`.**

Qwen3 scored 18/20 against the frozen A2.1 14B score of 17/20, recovering A04. It has not earned a separate local production tier. A reliable Qwen3 Vulkan inference path remains unqualified: primary Ollama attempts repeatedly failed startup allocation, and the successful CPuFriend runs were incorrectly labeled Vulkan in the earlier report. Backend discovery now shows no GPU device in that installation. Those successful measurements must be treated as CPU observations, subject to the retrospective assumption that the installation was unchanged.

The completed bounded experiment and audit do not prove Qwen3 is universally inferior to 14B. They do establish a real runtime blocker and insufficient evidence for promotion. Dense A2.2 32B remains **BLOCKED**. No router or Track B implementation was changed.

## Provenance and exact metadata

- Local file: `D:\WORK\RESEARCH\local2api\models\qwen3-coder-30b-a3b-instruct-q4_k_m.gguf`
- SHA256: `AB4FC2B27B2043483A9E346C802809DFBE9B775EFBEEA7CA74DC2FD1AA4A0F71`
- File size: **18,556,688,704 bytes** (17.282 GiB); no model downloaded.
- Tensor sum: **30,532,122,624 parameters**, 579 tensors, architecture `qwen3moe`, Q4_K_M.
- 48 layers; hidden size 2048; 32 attention heads; 4 KV heads; **head dimension 128** from explicit key/value metadata. The old value 64 was incorrect.
- 128 experts, 8 selected/token, shared-expert FFN length 0; no shared-expert tensors in the inventory.
- Expert FFN dimension 768; general FFN metadata 5472; context metadata 262144; RoPE base 10000000.
- Tokenizer: GPT2/BPE, `qwen2` pretokenizer; full chat template and scalar tokenizer metadata retained in `model_metadata.json`.

Local tensor inventory yields 28,991,029,248 routed-bank parameters, 1,811,939,328 selected-expert parameters/token, and 1,541,093,376 nonexpert resident parameters. The conventional structural active footprint is **3,353,032,704 parameters** including the full input embedding table. Counting only one input embedding row gives 3,041,869,824; neither is a measured FLOP count or per-token transfer volume. All expert banks still occupy storage/residency space.

Source evidence: cloned llama.cpp revision `7798007a29a90e3053e799394da48cf53a2f8e0f`, `src/models/qwen3moe.cpp` (`load_arch_tensors` and `graph`). Actual header/tensor evidence is in [gguf_header_audit.json](evidence/a2_s1/gguf_header_audit.json).

## Memory model and observed pressure

| Context, one sequence | f16 KV payload | q4_0 KV payload | q8_0 KV payload |
|---|---:|---:|---:|
| 1K | 96 MiB | 27 MiB | 51 MiB |
| 4K | 384 MiB | 108 MiB | 204 MiB |
| 8K | 768 MiB | 216 MiB | 408 MiB |
| 16K | 1536 MiB | 432 MiB | 816 MiB |

Formula: context × 48 layers × 4 KV heads × 128 elements × K/V. q4_0 uses 18 bytes per 32 elements; q8_0 uses 34. Block layouts are confirmed in cloned `ggml/src/ggml-common.h`. These are payload estimates, excluding padding, runtime workspaces and additional slots. The matched control logs show four default slots with 4096 context per slot; original direct slot configuration was not captured beyond the command/smoke response.

Planning reserve: 6 GiB Windows plus 4 GiB editor/browser (budgets, not measured per-app use). At 16K/q4 KV, weights + KV + these reserves already require about 27.70 GiB before runtime buffers. The model fitting in a 32 GB file-size budget does not establish practical residency.

The durable Qwen3 post-smoke snapshot records WS **18,504,175,616 bytes**, private bytes **14,432,628,736**, and only **572,256 KiB** available physical RAM. Classification: **`SYSTEM_PRESSURED`**, based on this low headroom. Peak WS, peak system commit, GPU shared memory, sustained pagefile/disk activity and window responsiveness during Qwen3 inference were **not captured**. The audit's 14B counters cannot substitute for them. Do not add shared GPU memory to WS on UMA as though they were independent allocations.

## Runtime support and corrections

Primary isolated Ollama 0.33.2 recognized `qwen3moe`, expert metadata and Arc/Vulkan, but never produced a successful Qwen3 completion in these attempts. At 16K/q4 KV it failed allocating 452,984,832 bytes for KV. At 4K with 32 GPU layers and batch 32 it still failed a 169,149,056-byte compute allocation. These errors are preserved in `load_smoke*.json`. Repeated failed startup attempts ended primary-path testing.

The successful direct binary was CPuFriend build 10726 / `85c55223c`. Its audited `--list-devices` returns `(none)` and no Vulkan DLL is installed in that directory. Passing `-ngl 32` was not proof of GPU execution. Requested settings were 4K, batch32, ubatch16, q4_0 KV, flash attention on; effective execution is CPU. The audit does not attribute success to microbatch reduction alone because the build/backend also changed.

Read-only device discovery with the existing Ollama binary and its own `GGML_BACKEND_PATH=.../vulkan/ggml-vulkan.dll` lists Arc 140V. No model was loaded for that check. Thus **Arc discovery YES; successful Qwen3 Vulkan inference NO**. Output parity between successful Ollama/Vulkan and direct/Vulkan remains unavailable.

## Quality method and comparison

All 20 intended-local prompt strings and contains-all criteria are byte-for-byte the canonical suite: 9 LOCAL_SAFE and 11 LOCAL_ACCEPTABLE. CLOUD_REQUIRED cases are outside the requested denominator. The exploratory 96-token run is archived; authoritative Qwen3 outputs use 128 tokens, temperature0, top_p1, top_k40, seed42, canonical ChatML, and cache_prompt=false. Quality was non-streaming, so TTFT is null rather than inferred from prompt time.

Because runtime/KV/context differed from A2.1, the audit reran all 20 affected 14B cases with the same CPuFriend CPU method. Models were never loaded concurrently for this repair. Matching configuration does not reproduce identical OS cache or background load; quality is compared, latency is not.

| Quality metric | Frozen A2.1 14B | Matched CPU 14B audit | Qwen3 CPU |
|---|---:|---:|---:|
| LOCAL_SAFE | 8/9 | 8/9 | 9/9 |
| LOCAL_ACCEPTABLE | 9/11 | 9/11 | 9/11 |
| Intended local | 17/20 | 17/20 | 18/20 |
| Mean manual score, audited rubric | historical mean not compared | 1.85 | 2.00 |

Manual rubric remains 0 wrong/unusable; 1 substantial repair; 2 mostly correct/minor repair; 3 production acceptable. The old published 2.65/2.55 means were too lenient to incomplete outputs and are withdrawn as incremental-quality evidence. Both models are reviewed under the same rubric in [manual_review_audit.json](evidence/a2_s1/manual_review_audit.json).

Qwen3 completes the core B05 helper before truncating optional extras; 14B's helper ends before its return value. Both fail to deliver the actual early-return refactor in B03 under this cap. Several keyword passes stop before a useful test assertion. Qwen3's D03 reasonably requests an absent diff but does not provide the requested general summary. Sixteen Qwen3 answers reach the cap; incomplete code/examples require cleanup and are not advertised as production-ready. No protocol-malformed or repetitive failure was observed; technical imprecision is documented per case.

## 14B Failure Recovery Analysis

Full original 14B output, failure reason, Qwen3 output, same-method 14B output and manual deltas are retained per case in [failure_recovery_analysis.json](evidence/a2_s1/failure_recovery_analysis.json).

| Case | Frozen 14B miss | Qwen3 outcome | Audited manual delta | Capability interpretation |
|---|---|---|---:|---|
| A04 | Identifies the empty branch but omits validation criterion (`valid`) | PASS; explicitly says empty input is sent without validation | 2 → 2 | Clearer diagnosis within the same usability band |
| D01 | Generic public interface answer omits `backend` | FAIL; generic HTTP interface discussion | 2 → 2 | No recovered backend-contract criterion |
| D05 | Session loss/scaling explanation omits `state` and `context` | FAIL; similar session-memory risks | 2 → 2 | No demonstrated context-reconstruction uplift |

Recovered **1/3** historical failures. This supports a small wording/task-completion improvement, not a demonstrated multi-file reasoning tier.

## Challenge-only control repair

The same three predeclared generic challenges were used at a 96-token cap: upstream-status invariant, context ownership record, and terminal SSE marker. Original 14B HTTP500 attempts were infrastructure failures, not quality zeros. They are retained alongside the repaired CPU control.

Keyword scores: **14B 1/3; Qwen3 1/3**. Manual assessment is recorded with each paired output. These short generic tasks do not contain a real 3–5-file repository, and cap truncation prevents a strong capability-ceiling claim. No challenge contributes to the canonical 20-case score.

## Performance and gate enforcement

| Qwen3 CPU observation | TTFT | Wall | Prompt tok/s | Decode tok/s | Runs |
|---|---:|---:|---:|---:|---:|
| 1K, 870 prompt tokens | 50.255 s | 60.526 s | 17.350 | 6.136 | 1 |
| 4K, 3573 prompt tokens | 333.053 s | 349.820 s | 10.728 | 3.758 | 1 |
| 8K | NOT COMPLETED | — | — | — | 0 |
| 16K | NOT COMPLETED | — | — | — | 0 |

These were loaded-model, uncached-prompt observations (`cache_n=0`), not cold-model TTFT. The 4K request exceeded the 300 s TTFT gate but the old harness failed to cancel it at that threshold. Larger direct runs were omitted afterwards. Cold-load TTFT, repeated cold/warm matrices and successful Qwen3 Vulkan throughput remain unmeasured. Optional CPU-MoE placement A/B was not run after repeated primary startup failure.

The old 14B Ollama measurements warmed up and repeated the same prompt without cache eviction; cached-token counts were not retained. CPU/Vulkan and build differences add further confounding. **The earlier 176x/697x TTFT ratios are withdrawn.** High apparent old prompt rates must not be called uncached prefill throughput.

## Primary comparison table

Historical latency columns below are context only and are not a controlled A/B with Qwen3.

| Metric | 7B historical | 14B dense | Qwen3 30B-A3B |
|---|---:|---:|---:|
| Total parameters | 7,615,616,512 | 14,770,033,664 | 30,532,122,624 |
| Active parameters/token | dense footprint, approx total | dense footprint, approx total | 3,353,032,704 structural convention |
| GGUF bytes | 4,683,074,048 | 8,988,110,272 | 18,556,688,704 |
| LOCAL_SAFE | 1/9 | 8/9 frozen | 9/9 |
| LOCAL_ACCEPTABLE | 2/11 | 9/11 frozen | 9/11 |
| Total intended local | 3/20 | 17/20 frozen | 18/20 |
| Audited mean manual score | not recorded | 1.85, CPU repair | 2.00, CPU |
| Challenge keyword score | N/A | 1/3 | 1/3 |
| TTFT 1K | 0.214 s warmed Ollama | 0.286 s warmed Ollama | 50.255 s uncached CPU |
| TTFT 4K | 0.322 s warmed Ollama | 0.478 s warmed Ollama | 333.053 s uncached CPU |
| TTFT 8K | 0.202 s warmed Ollama | 0.475 s warmed Ollama | not completed |
| TTFT 16K | 0.375 s warmed Ollama | 0.496 s warmed Ollama | not completed |
| Decode tok/s | 6.873–8.221 at 8K/16K | 2.753–3.949 historical | 3.758–6.136 CPU context samples |
| Peak system commit | not established here | 35.204 GB historical sampled | NOT PROVEN |
| System usability | no comparable classification | no UI qualification; audit counters retained | SYSTEM_PRESSURED, telemetry inference |
| Runtime complexity | established control | LOW relative to candidate | HIGH / unresolved GPU path |

7B file/header values were checked read-only against the original blob identified by `hw1_7b_prod_gate/input_parity.json`; no new 7B inference was run. Historical tables are from the frozen A2.1 comparison, not new performance measurements.

## Incremental value and next action

Quality/capability improvement is small on these bounded tasks. Weight storage increases by **9,568,578,432 bytes**, about **2.0646×** the 14B GGUF. Qwen3's successful CPU run leaves very little RAM, while the intended Vulkan path is unqualified. These facts prevent promotion; they do not establish a hardware-independent rejection or a valid numerical latency penalty over 14B.

No separate Qwen3 tier is qualified. Keep the existing 14B candidate pending its own production qualification. A2.S1's bounded run is COMPLETE with an inconclusive runtime verdict; a future experiment needs sufficient RAM headroom, explicit Arc device selection using a matching Vulkan DLL/build, captured offload logs, and cache-controlled cold/warm measurements. Dense 32B stays BLOCKED. Track B is unchanged.

## Reproducibility, evidence and QA

Required evidence files now include `model_metadata.json`, `runtime_config.json`, `quality_results.json`, `quality_outputs/`, `failure_recovery_analysis.json`, `challenge_14b_vs_qwen3.json`, `benchmark_runs.json`, `telemetry.json`, and `comparison_14b_vs_sparse.json`. Raw historical outputs and pre-audit interpretations remain separately named. See [audit_corrections.md](evidence/a2_s1/audit_corrections.md) for all corrections.

Audit scripts are `scripts/a2s1_artifact_audit.py` (local header/device audit), `scripts/a2s1_control_audit.py` (isolated 14B control), `scripts/a2s1_counter_sample.ps1` and `scripts/a2s1_finalize_audit.py`. These Windows audit scripts use the project Python 3.11+ venv and installed binaries; they never download a model or execute generated snippets.

Software QA: **15 tests passed** in the project venv; compileall and final JSON consistency validation passed (see `qa_validation.json`). These gates validate the gateway/artifacts, not model production quality.
