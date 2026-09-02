# v0.0.1-HW1 — Real-device qualification

Run this benchmark on the target Windows laptop before selecting the default local tier.

## Scope

- Two local coding-capable models in the 7B/8B class.
- One 14B candidate.
- Same prompt, generation cap, and number of measured runs for every model.
- Record Ollama-reported prompt evaluation throughput and generation throughput.
- Measure client-observed time to first generated content token (TTFT) and wall time.

Runtime-reported timings are authoritative for model evaluation durations when available. Client TTFT also includes local HTTP and streaming overhead, which is intentional because local2api ultimately cares about user-observed latency.

## Command

```powershell
.\.venv\Scripts\python.exe scripts\hw1_benchmark.py `
  --provider ollama `
  --models qwen2.5-coder:7b llama3.1:8b qwen2.5-coder:14b `
  --runs 3 `
  --num-predict 128 `
  --output docs\result\hw1_ollama.json
```

The same harness can benchmark an OpenAI-compatible `llama-server`:

```powershell
.\.venv\Scripts\python.exe scripts\hw1_benchmark.py `
  --provider openai `
  --base-url http://127.0.0.1:11437 `
  --models qwen2.5-coder:7b `
  --runs 5 `
  --num-predict 128 `
  --output docs\result\hw1_llama_server.json
```

On the tested Intel Arc setup, a dynamically loaded Vulkan backend requires `GGML_BACKEND_PATH` to point directly to `ggml-vulkan.dll`, not merely to its containing directory.

Immediately after each model is loaded, use `ollama ps` to record whether Ollama reports CPU, GPU, or a split processor allocation. Working set, commit, page faults, package power, and temperature require a separate OS/hardware telemetry pass; do not infer them from Ollama API timings.

## Qualification rule

Do not select a model from parameter count alone. Prefer the smallest model that clears the coding/repository quality suite and has acceptable TTFT and generation throughput on the target laptop. Treat the 14B model as a candidate, not a requirement for the default tier.
