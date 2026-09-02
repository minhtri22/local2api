# local2api — Project Documentation

## 1. Purpose

`local2api` is an OpenAI-compatible local gateway for a 32 GB developer laptop. The primary goal is not to make every prompt local; it is to select the cheapest/most private backend that is capable of the task, while preserving a stable API for VS Code, Continue-like clients, Open WebUI, and custom tools.

The target workstation for the first real-device benchmark is:

- Intel Core Ultra 7 258V
- Intel Arc 140V integrated GPU / unified memory
- 32 GB LPDDR5X RAM
- Windows 11

Public `llama.cpp` results on the same CPU/iGPU show that 7B-class Q4 models are practical, while larger models become progressively slower and can expose backend-specific GPU allocation/fused-kernel issues. Therefore v0.0.1 treats a 7B/8B Q4 local model as the default target rather than assuming a fixed 12–14 GB model allocation.

## 2. Architecture

```text
VS Code / Open WebUI / Client
            |
            v
+-----------------------------+
| local2api OpenAI Gateway    |
| /v1/chat/completions        |
| /v1/models                  |
| /health                     |
+-------------+---------------+
              |
        RoutingDecision
       /               \
      v                 v
Local LLM adapter     External API adapter
(llama.cpp etc.)      (official API or user-supplied compatible service)
```

### Design rule

**Task capability, not prompt length alone, decides routing.** Length remains one signal only.

v0.0.1 uses a deterministic rules router so every decision can be inspected and tested. Later versions may add context-aware scoring.

## 3. Backend policy

### Local backend

Recommended first target: a coding-capable 7B/8B GGUF Q4 model via `llama.cpp` or another OpenAI-compatible local runtime. Exact model/runtime must be benchmarked on the target Windows laptop before being promoted to the default configuration.

### External backend

Core local2api accepts an OpenAI-compatible HTTP endpoint. This can be an official cloud API or another service the user is authorized to operate.

Web-account-to-API wrappers based on browser cookies/session tokens are **experimental integrations**, not a reliability or zero-cost guarantee. They can break when upstream services change and may conflict with provider terms if they automate extraction, bypass safeguards, or circumvent usage limits. local2api v0.0.1 does not implement CAPTCHA bypass, rate-limit circumvention, or automated credential extraction.

## 4. Routing and fallback

The client can select:

- `model=local2api-auto` — router decides.
- `model=local` — force local backend.
- `model=cloud` — force external backend.

Response headers expose the decision:

```text
X-Local2API-Backend: local|cloud
X-Local2API-Route-Reason: <reason>
```

Fallback is capability-aware. A cloud outage does **not** automatically send architecture/repository reasoning to a weaker local model. Safe, degradable work may fall back; high-complexity work returns a clear `503 backend_unavailable` instead of silently returning lower-quality output.

## 5. Streaming

`stream=true` is supported as SSE pass-through in v0.0.1. Once stream bytes have started, switching backends is unsafe because it could mix two generations. Streaming fallback therefore remains conservative.

## 6. Privacy

Local requests remain on the configured local inference endpoint. Requests routed to any external backend leave the laptop and inherit that provider's privacy/data-use policy. The router cannot make an external request private merely because it passes through localhost.

## 7. Operational limitations in v0.0.1

- No persistent conversation/context brain yet.
- No circuit breaker or adaptive health scoring.
- No semantic/result cache.
- No automatic browser-cookie harvesting or CAPTCHA handling.
- No claim that the system uses only 12–14 GB RAM; memory depends on the selected model, context, KV cache, runtime and OS.

## 8. Run

```bash
pip install -e ".[test]"
python -m local2api.main
```

Environment options are shown in `.env.example`.
