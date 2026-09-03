# A3 — 14B Production Qualification

Date: 2026-09-04

## 1. Executive summary

**A3 verdict: `14B_PRODUCTION_READY_WITH_LIMITS`.**

Qwen2.5-Coder-14B-Instruct Q4_K_M is stable enough to hand to Track B as a bounded local backend. It completed 32/32 sustained requests and 5/5 controlled repository workflows. The production contract is intentionally narrow because multi-turn consistency was only 2/5, realistic repository-context TTFT rises sharply beyond 4K, long outputs are slow, and concurrency 2 increases queueing/starvation behavior.

Track B/B1 must own canonical conversation/task context and reconstruct it on every request. Backend/model hidden state is not a production context contract.

## 2. Baseline

The A2.1 frozen quality baseline remains LOCAL_SAFE 8/9, LOCAL_ACCEPTABLE 9/11, total 17/20. A3 does not redefine the architectural ceiling of local2api as 14B. Dense 32B remains BLOCKED; larger-model research moves to a reopen-condition-driven A4 frontier.

## 3. Artifact/runtime

- Model: Qwen2.5-Coder-14B-Instruct Q4_K_M
- GGUF: `models/qwen2.5-coder-14b-instruct-q4_k_m.gguf`
- SHA256: `C1E659736D89AC1065FB495330FB824D94001974A4BFA78E7270E43476A8D940`
- Size: 8,988,110,272 bytes
- Runtime: Ollama 0.33.2
- Accelerator: Intel Arc 140V / Vulkan
- Arc/Vulkan: verified by Ollama device discovery and successful loaded-model inference evidence carried forward from A2.1 and reconfirmed at A3 start.

Cold lifecycle: cold TTFT 24.6 s / load 22.5 s; warm TTFT 6.1 s; short post-idle reuse TTFT 0.35 s; explicit unload/reload TTFT 14.7 s. Current gateway has no complete READY/LOADING/UNAVAILABLE/DEGRADED state model; that remains a Track B observability gap.

## 4. Sustained reliability

32/32 consecutive mixed requests succeeded with no recorded backend crash or restart. Median TTFT was 17.2 s, p95 TTFT 21.5 s, median decode 4.87 tok/s. System commit moved from 35.95 GB to 38.08 GB across the run while available physical RAM ended at 6.40 GB; no monotonic leak was demonstrated by the endpoint snapshots.

## 5. Repository workflows

Five multi-step controlled workflows all passed: 5 PASS / 0 PARTIAL / 0 FAIL. They covered status propagation, validation/test addition, async interface mismatch, safe fallback constraints, and targeted call-path edits.

These fixtures show strong bounded engineering usefulness when relevant context and deterministic success criteria are supplied.

## 6. Multi-turn/context ownership

Only 2/5 controlled five-turn sessions met the consistency gate. Each request reconstructed prior transcript context explicitly; no backend session memory was relied upon.

Production requirement: **Gateway must own canonical conversation/task context.** Track B/B1 must not rely on model hidden state, backend-specific session memory, or implicit continuity when switching backends.

## 7. Context operating envelope

Realistic repository-context measurements:

| Context | Prompt tokens observed | TTFT | Wall | Decode |
|---|---:|---:|---:|---:|
| 2K | 1,860 | 35.4 s | 53.5 s | 5.31 tok/s |
| 4K | 3,674 | 60.0 s | 80.1 s | 4.79 tok/s |
| 8K | 7,304 | 142.0 s | 164.7 s | 4.22 tok/s |
| 12K | 10,933 | 390.4 s | 428.7 s | 2.50 tok/s |
| 16K | 14,562 | 648.6 s | 694.3 s | 2.10 tok/s |

Production contract:

- recommended context: **<= 4K tokens**;
- soft context ceiling: **8K** for deliberate quality-sensitive local work;
- hard context ceiling: **12K**; at/above this boundary the request should be cloud-preferred rather than normal local production routing.

## 8. Output envelope

128 tokens took 45.4 s wall; 256 took 56.8 s; 512 took 122.8 s; a requested 1024 generation stopped naturally at 770 tokens after 190.2 s.

Production contract: **256 recommended max output tokens; 512 hard output ceiling**. Longer generations are technically possible but are not responsive enough for the intended local tier.

## 9. Concurrency

Concurrency 1 completed in 23.1 s group wall. Concurrency 2 completed both requests, but one request waited ~21.7 s for first token and the group wall rose to 40.8 s. RAM/commit did not fail, but the observed queueing/starvation makes concurrency 2 an unsuitable default.

Production contract: **recommended max concurrency = 1**.

## 10. Resource/system behavior

A2.1 sampled the loaded runtime at ~12.8 GB process working set and ~12.9 GB private bytes with minimum sampled available RAM ~5.8 GB. A3 context telemetry showed available RAM from ~8.5 GB at 2K down to ~5.9 GB at 16K, with committed bytes reaching ~39.4 GB at 16K.

System classification: **SYSTEM_PRESSURED** for the production tier. No evidence shows Windows became unusable, but VS Code/browser responsiveness was not instrumented and is NOT PROVEN. Thermal, package power, GPU utilization percentage and throttling remain NOT PROVEN.

Conservative pre-load contract: **minimum 8 GiB free RAM; recommended 10 GiB free RAM**. This is an operating reserve derived from successful loaded-run headroom, not a measured exact allocation failure threshold.

## 11. Failure/recovery

- runtime unavailable: PASS through existing gateway fake-backend failure semantics;
- wrong backend port: PASS; A3 timed out with no false success;
- request timeout: PARTIAL; timeout/normalization path observed, no dedicated live slow-upstream injector;
- model not loaded: PARTIAL; explicit unload/reload recovered, invalid model id not injected;
- malformed upstream: NOT TESTED live;
- connection reset: NOT TESTED live;
- restart behavior: PARTIAL; restart/reload outside active generation succeeded, restart-during-request not executed.

Existing gateway tests preserve upstream non-2xx responses, prohibit unsafe architecture-task fallback, and verify SSE `[DONE]` pass-through.

## 12. Quality regression

The A2.1 canonical 17/20 quality baseline is retained. A3 did not change model artifact, quantization, chat template, or the production runtime family, so a full 20-case rerun was not required. A3's 32-request mixed workload and 5/5 bounded repository workflows provide additional regression evidence that the selected production configuration remains useful. Capability Ceiling Suite v1 is intentionally harder and is reported separately rather than treated as a regression failure.

## 13. Production contract

The machine-readable handoff is `docs/result/evidence/a3_14b/local_capability_profile.json`.

Supported local production classes: short code explanation/review, small bounded edits, unit-test generation, bounded bug localization, 2-3 file reasoning with supplied context, diff summary/structured extraction, and short repository questions.

Cloud-preferred classes: repository-wide or architecture-wide refactors, ambiguous multi-module debugging, long-horizon agentic repair, contexts above 8K, work that depends on strong multi-turn retention without gateway reconstruction, and security-critical decisions from incomplete evidence.

## 14. Final verdict

**`14B_PRODUCTION_READY_WITH_LIMITS`**.

The reliability and bounded workflow evidence justify a real production local tier. The explicit context, output, concurrency, RAM, context-ownership and task-class limits are mandatory parts of that tier.

## 15. Limitations

No active-request runtime restart fault was injected. Malformed live upstream and connection-reset scenarios were not exercised. UI responsiveness, thermals and power are not proven. Context payloads are controlled repository-like fixtures rather than whole real-world repositories.

## 16. Track B handoff

B1 must implement gateway-owned canonical context, backend-independent reconstruction, token budgeting and backend capability accounting. The Local Capability Profile should be treated as a routing contract, not a claim that every task inside the raw model context limit belongs on local.

## 17. Beyond-14B implications

Capability Ceiling Suite v1 freezes 14 concrete gaps with a 14B manual baseline of **27/70 (1.93/5)**. Future models should be reopened only when runtime/hardware economics improve or when a larger candidate plausibly solves one or more frozen gaps. Qwen3.8-27B is recorded as WATCH / NOT YET QUALIFIED; it is not downloaded or benchmarked in A3 closure. Dense 32B remains BLOCKED.
