# local2api Implementation Plan

## Product objective

Build a small, observable OpenAI-compatible inference gateway for a 32 GB laptop. Prefer local inference for tasks that fit the local model's capabilities; use an authorized external backend for harder workloads; do not silently degrade tasks that require stronger reasoning.

## v0.0.1 — Reliable Gateway Foundation

- [x] FastAPI application/package structure.
- [x] `POST /v1/chat/completions` pass-through.
- [x] `stream=false` support.
- [x] `stream=true` SSE pass-through.
- [x] `GET /v1/models`.
- [x] `GET /health`.
- [x] Local and external HTTP backend adapters.
- [x] Deterministic rules router with explicit route reason.
- [x] Explicit local/cloud model override.
- [x] Capability-aware safe fallback.
- [x] Preserve upstream HTTP status/body for non-transport failures.
- [x] Unit/integration tests using mocked backends.
- [x] QA report generated only from tests actually executed.

### v0.0.1 acceptance criteria

1. Short/local-safe tasks route local.
2. Architecture/repository tasks route external.
3. Unsafe cloud failures return a clear error instead of silent local downgrade.
4. Safe degradable cloud failures can fall back local.
5. SSE streaming passes through correctly.
6. Route backend/reason are observable in headers.
7. Test suite passes in a clean Python environment.

## v0.0.2 — Context Ownership

- [ ] Add `conversation_id` and canonical gateway-owned conversation state.
- [ ] Add context builder and backend-independent message reconstruction.
- [ ] Add token estimation and per-backend context limits.
- [ ] Add capability registry (`tools`, context window, structured output, vision, coding tier).
- [ ] Ensure backend switching does not depend on hidden server-side session memory.
- [ ] Add routing-decision trace endpoint/log schema.

## v0.0.3 — Reliability

- [ ] Circuit breaker per backend.
- [ ] Retry/backoff for safe transport failures and 429 responses.
- [ ] Health/latency rolling metrics.
- [ ] Backend availability score.
- [ ] Configurable fallback policies by task class.

## v0.0.4 — Smart Routing

- [ ] Replace keyword-only rules with a tested task classifier/complexity score.
- [ ] Use context size, task class, backend capability, latency and availability in scoring.
- [ ] Add quality-feedback telemetry without storing source code by default.

## v0.1.0 — Adaptive Local/Cloud Router

- [ ] Candidate local model selected from real target-laptop benchmarks.
- [ ] Optional official free/low-cost cloud tier adapters.
- [ ] Optional third-party adapters only where operation complies with upstream terms.
- [ ] End-to-end VS Code coding workflow benchmark.

## Non-goals

- Bypassing CAPTCHA or anti-bot systems.
- Circumventing provider rate limits.
- Extracting browser credentials without explicit, compliant authorization.
- Owning raw llama.cpp KV cache in the gateway before benchmarks prove a need.

## Next action after v0.0.1

Run the **real-device qualification benchmark on the Intel Core Ultra 7 258V / 32 GB Windows laptop** in gated stages. First prove the 7B local tier on the target hardware, including runtime A/B, telemetry, and coding quality. Only after the 7B gate passes should a 14B candidate be downloaded and qualified. Record TTFT, prompt tokens/s, generation tokens/s, working set, commit memory, page faults and thermal/power behavior. Use those measurements to select the default local model and define v0.0.2 capability limits.

### v0.0.1-HW1 progress

- [x] Add a reproducible Ollama benchmark harness for TTFT and Ollama-reported prompt/generation throughput.
- [x] Demonstrate Qwen2.5-Coder 7B Q4_K_M hardware/runtime feasibility on the target laptop with Arc 140V Vulkan.
- [x] Run same-model Ollama vs llama-server A/B on Arc 140V Vulkan; sustained generation is approximately 9 tok/s on both paths.
- [ ] Complete the 7B gate with byte-identical runtime input, OS memory/page-fault telemetry, thermal/power telemetry, and coding/repository quality tests.
- [ ] Only after the 7B gate passes, download and benchmark the 14B candidate.
- [ ] Record Ollama CPU/GPU processor allocation for each candidate. Arc 140V Vulkan / `100% GPU` is confirmed for Qwen2.5-Coder 7B; complete the same check for all candidates.
- [ ] Capture working set, commit memory and page faults with OS telemetry.
- [ ] Capture thermal/power behavior with hardware telemetry.
- [ ] Run a coding/repository quality suite before selecting the default local tier.
