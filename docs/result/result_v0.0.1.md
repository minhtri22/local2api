# QA Test Result Report — v0.0.1

- **Date**: 2026-09-02
- **Role**: AI QA / sandbox tester
- **Scope**: gateway software behavior with deterministic mock backends

## 1. Environment

| Component | Version / value |
|---|---|
| Python | 3.13.5 |
| FastAPI | 0.128.2 |
| HTTPX | 0.28.1 |
| Uvicorn | 0.48.0 |
| pytest | 9.0.2 |
| pytest-asyncio | 1.3.0 |
| Backend under test | in-process fake local + fake cloud adapters |

The sandbox has no Internet package access. `pip install -e ".[test]"` therefore could not download build dependencies. The source was tested directly using `PYTHONPATH=src`; required runtime/test libraries were already installed in the sandbox.

## 2. Executed tests

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m compileall -q src tests
```

Result:

```text
............                                                             [100%]
12 passed in 0.25s
```

`compileall` completed without syntax errors.

## 3. Functional result

| Area | Status | Evidence |
|---|---|---|
| Short/local routing | PASS | local fake backend selected; route header asserted |
| Complex architecture routing | PASS | cloud fake backend selected |
| Explicit model override | PASS | deterministic router tests |
| Backend model alias mapping | PASS | `local2api-auto` translated to configured backend model ID |
| Unsafe fallback protection | PASS | architecture cloud failure returns 503 and does not call local |
| Safe fallback | PASS | degradable large-context cloud transport failure falls back local |
| SSE streaming | PASS | SSE payload and `[DONE]` observed |
| `/v1/models` | PASS | auto/local/cloud aliases exposed |
| Invalid request handling | PASS | invalid `messages` returns HTTP 400 |
| Upstream non-2xx propagation | PASS | fake local HTTP 429 preserved |
| `/health` | PASS | local/cloud health state reported |
| Import/syntax validation | PASS | `compileall` successful |

## 4. Mock gateway overhead check

100 in-process requests using ASGI transport and a no-compute fake backend:

```text
n=100 p50_ms=0.233 p95_ms=0.368 min_ms=0.205 max_ms=1.451
```

This is router/gateway test overhead only. It is not LLM latency, TTFT, network latency, RAM consumption, iGPU throughput, or a prediction of the target laptop's end-to-end performance.

## 5. Not tested in this sandbox

- local model RAM/VRAM/unified-memory usage
- SSD mmap behavior
- TTFT and token generation speed
- Intel Arc 140V SYCL/Vulkan behavior
- sustained thermal/power behavior
- VS Code end-to-end usability
- real external API/Web2API sessions, rate limits, cookie expiry, CAPTCHA or provider availability

No fabricated values such as “13.2 GB peak RAM” or “<120 ms first token” are included.

## 6. QA verdict

**v0.0.1 software foundation: PASS for commit.**

It should not yet be described as a fully qualified Intel 258V hybrid-LLM solution until the real-device benchmark is completed.

## 7. Risks found during review

1. Browser-session Web2API adapters are fragile and may be inconsistent with upstream provider terms depending on how they automate access.
2. Blanket `cloud -> local` fallback can silently reduce answer quality; architecture/repository-class tasks therefore do not fall back in v0.0.1.
3. Prompt length alone is not a sufficient complexity signal.
4. Backend model aliases must be translated before forwarding; this was fixed during QA.
5. Streaming cannot safely switch models after output bytes are emitted.

## 8. Recommended next action

Run **Target Laptop Qualification v0.0.1-HW1** on Windows 11 / Intel Core Ultra 7 258V / 32 GB. Test at least two coding-focused 7B/8B Q4 models and one 14B Q4 candidate with identical workloads, recording TTFT, prompt tokens/s, generation tokens/s, process working set, committed memory, page faults/s, CPU/iGPU utilization, p50/p95 latency and failure rate. Select the default local model from evidence, then implement v0.0.2 Context Ownership so switching local/cloud does not fragment project conversation state.
