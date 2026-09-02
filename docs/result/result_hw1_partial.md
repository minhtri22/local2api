# v0.0.1-HW1 partial result — Intel Core Ultra 7 258V / Arc 140V

Date: 2026-09-02

This is a real-device measurement on the target laptop, not a synthetic estimate.

## Runtime finding

The installed Ollama configuration had `OLLAMA_KV_CACHE_TYPE=q4_0` while `OLLAMA_FLASH_ATTENTION=false`. That combination caused model load to fail with:

```text
quantized V cache requires flash_attn to be enabled
```

For HW1, a separate Ollama instance was started on `127.0.0.1:11435` with Flash Attention enabled. Ollama also initially dropped the Intel integrated GPU. Setting `OLLAMA_IGPU_ENABLE=1` for the isolated benchmark instance made Ollama detect the Intel Arc 140V through Vulkan and report the loaded model as `100% GPU`.

No persistent Windows environment variables were changed.

## Measured results

Same prompt and deterministic sampling were used for each run. Each model received three runs. The first run includes cold model loading; later runs are warm.

| Model | Processor | Median TTFT | Median prompt tok/s | Median generation tok/s | Cold load |
| --- | --- | ---: | ---: | ---: | ---: |
| Qwen2.5-Coder 7B Q4_K_M | Arc 140V Vulkan, 100% GPU | 179.5 ms | 470.8 | 9.44 | 9.20 s |
| Llama 3.1 8B Q4 | Arc 140V Vulkan | 1682.6 ms | 410.3 | 9.07 | 9.32 s |

Qwen2.5-Coder 7B was also measured once as a CPU-only control before the iGPU issue was discovered. Its generation speed was roughly 6.1-6.45 tok/s, versus 9.3-9.8 tok/s on Arc 140V Vulkan.

The Llama median TTFT is inflated by one warm run that incurred about 1.1 s of load duration; its best warm TTFT was 175.7 ms. Therefore TTFT should be re-measured with explicit model residency controls before using it as a final selection criterion.

## Runtime A/B — Ollama vs llama-server

The exact Qwen2.5-Coder 7B Q4_K_M GGUF blob used by Ollama was also loaded directly by `llama-server`. The CPuFriend `llama-server` build is CPU-only; a second direct `llama-server` test used the Ollama-bundled llama.cpp runtime with its Vulkan backend loaded explicitly, so both Vulkan paths used the Arc 140V.

| Runtime | Processor | Runs | Median TTFT | Median generation tok/s |
| --- | --- | ---: | ---: | ---: |
| Ollama 0.33.2 | Arc 140V Vulkan | 5 | 452.6 ms | 8.832 |
| llama-server build d222767c7 | Arc 140V Vulkan | 5 | 140.8 ms | 9.387 |
| llama-server CPuFriend build 85c55223c | CPU | 3 | 176.9 ms | 6.180 |

The Vulkan A/B indicates similar sustained generation throughput: direct llama-server was about 6% ahead in this short run. Direct llama-server also showed lower warm TTFT in this sample. Early 15–16 tok/s Vulkan samples were transient and later runs converged around 8–10 tok/s, so those burst values are not treated as sustained performance.

This A/B remains preliminary because Ollama and raw llama-server do not yet render a byte-identical chat template/system prompt. A final runtime decision should rerun both paths with identical rendered prompt tokens and controlled thermal/power state.

Raw A/B evidence:

- `hw1_qwen2.5-coder-7b-ollama-vulkan-r2.json`
- `hw1_qwen2.5-coder-7b-llama-server-vulkan-r2.json`
- `hw1_qwen2.5-coder-7b-llama-server-cpu.json`

## 14B status

`qwen2.5-coder:14b` was selected as the 14B candidate because it keeps the family comparison with the 7B coding model. The model was not already installed. A pull was started but stopped after roughly 600 MB of the 9.0 GB blob because transfer throughput was too low to complete within this qualification pass. Ollama can resume the blob download on the next `ollama pull qwen2.5-coder:14b`.

Therefore HW1 is not complete and no final local-tier model is selected yet.

## Remaining qualification work

- Complete and benchmark `qwen2.5-coder:14b` with the same harness.
- Add OS telemetry for working set, commit memory, and page faults.
- Add thermal/package-power telemetry.
- Run a coding/repository quality suite; throughput alone is not sufficient to select the default model.

Raw timing data is stored next to this report in the HW1 JSON result files.
