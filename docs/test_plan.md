# QA / Tester Plan — v0.0.1

## 1. Scope

Validate the gateway software independently from a real LLM. The sandbox test suite uses fake backend adapters so routing, fallback, HTTP semantics and SSE can be deterministic. Hardware/model performance is a separate real-device benchmark and must not be fabricated from sandbox results.

## 2. Test environments

### A. Sandbox software QA

- Python 3.10+
- FastAPI + HTTPX
- Mock local backend
- Mock external backend

### B. Target-laptop qualification (next action)

- Windows 11
- Intel Core Ultra 7 258V
- 32 GB RAM
- Candidate `llama.cpp`/compatible runtime
- 7B/8B Q4 coding model baseline; optional 14B comparison

## 3. Functional cases

| ID | Test | Expected |
|---|---|---|
| TC01 | Short rewrite/autocomplete request | Routed to local; route header present |
| TC02 | Architecture/repository request | Routed to cloud/external |
| TC03 | Explicit `model=local` / `model=cloud` | Router override respected |
| TC04 | Cloud transport failure on non-degradable architecture task | HTTP 503; no silent local fallback |
| TC05 | Cloud transport failure on safe large-context task | Local fallback succeeds; fallback reason exposed |
| TC06 | `stream=true` | SSE chunks and `[DONE]` pass through |
| TC07 | `/v1/models` | Advertises auto/local/cloud aliases |
| TC08 | Invalid request body | 4xx normalized error |
| TC09 | Upstream non-2xx response | Status/body preserved where transport succeeded |
| TC10 | `/health` | Reports backend health and gateway version |

## 4. Sandbox execution

```bash
python -m venv .venv
pip install -e ".[test]"
pytest -q
```

Record exact Python/package versions and test output in `docs/result/result_v0.0.1.md`.

## 5. Real-device performance plan

Do not use a fixed claim such as “RAM <= 14 GB” as the sole pass/fail rule. Measure:

- model file size / quantization
- context length
- time to first token (TTFT)
- prompt processing tokens/s
- generation tokens/s
- process working set
- system committed memory
- page faults / swap pressure
- CPU/iGPU utilization
- temperature/power mode where available
- p50/p95 request latency
- failure rate over a repeatable workload

### Qualification target

The local tier should feel responsive enough for inline edits and short coding/chat tasks while leaving enough memory for Windows + VS Code. The final thresholds must be set from actual measurements on the user's laptop, not assumed in advance.
