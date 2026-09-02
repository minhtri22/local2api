# A1.0 reference architecture reverse-engineering

Reference revisions:

- AirLLM `fd1bd87216488e053b87691bbb6318fa9bf77a4b` — Apache-2.0.
- llama.cpp `0f3a71be15af836d277c9f918adfafb45732677e` — MIT.

The repositories were cloned under `.research/` and are excluded from Git. Conclusions below are based on source inspection, not README claims.

## AirLLM execution flow

AirLLM's current core is `AirLLMBaseModel` in `air_llm/airllm/airllm_base.py`. It constructs the real Hugging Face causal-LM architecture under `accelerate.init_empty_weights()` on the `meta` device in `_instantiate_on_meta()`. The model retains Transformers' forward/generation semantics without materializing all parameters.

The checkpoint is converted into per-module safetensors by `split_and_save_layers()` in `air_llm/airllm/utils.py`. At inference, streamed modules have forward pre/post hooks. `_pre_hook()` obtains a prefetched shard or calls `_load_streamed_layer()`, then `move_layer_to_device()` materializes weights on the execution device. `_post_hook()` moves those parameters back to `meta` and performs memory cleanup. `generate()` delegates to the underlying Transformers model, so each generated token triggers another model forward and traverses the streamed decoder modules again.

Prefetch is explicit but simple: `ThreadPoolExecutor(max_workers=1)` starts loading the next streamed layer while the current module executes. `load_layer_to_cpu()` may call `.pin_memory()` when CUDA is available and the layer is below a 2 GiB safety limit. Compression and prefetch are mutually disabled in the constructor.

Compression is not accelerator-neutral. `compress_layer_state_dict()` uses bitsandbytes and explicitly calls `v.cuda()` for both 4-bit and 8-bit compression. The default runtime device is also `cuda:0`. This makes the stock compression path unsuitable for Intel Arc without rework.

AirLLM also has an MoE-specific path. `_setup_expert_streaming()` attaches hooks to individual experts; `_expert_pre_hook()` uses `load_layer_subset()` so safetensors seeks only selected expert tensors, and `_expert_post_hook()` evicts them back to `meta`. This is the strongest reusable architectural idea for sparse models because total weights can exceed memory while active experts/token remain small.

## AirLLM implementation map

| Concept | AirLLM implementation | File/function | Có thể reuse idea? | Có thể reuse code? | Intel Arc blocker |
|---|---|---|---|---|---|
| Model splitting/layer sharding | Rewrites or links checkpoint tensors into per-module safetensors | `airllm/utils.py::split_and_save_layers` | Yes | Technically yes under Apache-2.0, but unnecessary for GGUF | PyTorch/safetensors format mismatch with llama.cpp |
| Layer loading from disk | Persister loads per-layer state dict; safetensors subset loader for experts | `utils.py::load_layer`, `load_layer_subset` | Yes | Not recommended | PyTorch tensor path |
| Unload/memory release | Parameters returned to `meta` after forward | `airllm_base.py::_post_hook`, `_expert_post_hook` | Yes | No direct reuse | No equivalent `meta` tensor lifecycle in GGML |
| Prefetch | Single worker preloads next layer | `AirLLMBaseModel.__init__`, `_pre_hook` | Yes | Reimplement | Existing implementation is Python/PyTorch oriented |
| CPU -> accelerator transfer | Materialize state dict onto configured device | `move_layer_to_device` | Yes | No | Different GGML buffer APIs; stock defaults to CUDA |
| Compression | bitsandbytes NF4/8-bit preprocessing | `utils.py::compress_layer_state_dict` | Concept only | No for Arc path | Requires bitsandbytes and explicit `.cuda()` |
| Model skeleton/meta tensors | HF model instantiated under empty weights | `_instantiate_on_meta`, `init_model` | Yes conceptually | No | GGML creates tensor metadata differently |
| Expert streaming | Per-expert pre/post hooks and safetensors subset reads | `_setup_expert_streaming`, `_expert_pre_hook` | Strong candidate for MoE | Reimplement | Needs GGUF tensor/expert mapping and backend-buffer lifecycle |
| Caching/residency | Current module materialized; optional next-layer host prefetch; selected resident modules supported | `_pre_hook`, `_post_hook`, resident-module setup | Yes | Reimplement | Not a device-agnostic cache planner |
| Generate loop | Delegates to Transformers; every decode forward traverses model again | `generate`, HF forward hooks | Yes as behavior evidence | No | Python/Transformers runtime |
| CUDA assumption | `device="cuda:0"`, `torch.cuda.is_available()` and CUDA pinning | constructor, `load_layer_to_cpu` | No | No | Arc/XPU requires different device/runtime path |
| Pinned memory | Pins small prefetched layers | `load_layer_to_cpu` | Yes | Reimplement | CUDA-specific gating in stock path |
| bitsandbytes | Required for optional 4/8-bit compression | constructor, `compress_layer_state_dict` | No | No | Current BnB path is CUDA-centric here |
| PyTorch device model | HF parameters move among CPU/device/meta | whole `AirLLMBaseModel` | Concept only | No | Duplicates llama.cpp/GGML execution stack |

## llama.cpp execution flow

`llama_model_loader` opens GGUF files and configures mmap or direct-I/O according to load mode. `init_mappings()` creates mappings and may prefetch mapped ranges. `load_all_data()` binds mmap-backed tensors directly where possible or copies/uploads data into backend buffers. There is an asynchronous upload path for non-mmap loads.

`llama_model_base::load_tensors()` in `src/llama-model.cpp` chooses buffer types and devices per layer according to `n_gpu_layers`, allocates backend buffers, and loads model data. The selected backend can be CPU, Vulkan, SYCL or another registered GGML backend. Tensor storage, transfer and execution therefore already sit behind GGML abstractions.

Inference graphs are scheduled through `ggml_backend_sched_graph_compute_async()` in `ggml-backend.cpp`. Vulkan implements buffer allocation, set/get/copy operations and graph dispatch in `ggml-vulkan.cpp`; the same higher layer can also target the Intel-oriented SYCL backend under `ggml/src/ggml-sycl/`.

KV cache allocation is independent of model weights. `llama_kv_cache` creates K and V tensors with configurable `ggml_type`; the code explicitly handles quantized K/V. Weight-residency experiments should preserve llama.cpp's KV implementation rather than invent another cache.

Recent llama.cpp also contains `LLAMA_LOAD_MODE_DIRECT_IO` and `TENSOR_READ_LAZY`. The latter can read rows of selected tensors on demand from mmap. Current model code uses it only for specific large table-like tensors, so it demonstrates lazy storage semantics but is not a ready-made general dense-layer streaming scheduler.

## Similarities and differences

Both systems separate tensor metadata from where bytes ultimately reside and both can avoid keeping every weight in accelerator memory. AirLLM makes residency a per-forward-module policy in Python and aggressively evicts modules after each traversal. llama.cpp decides placement at model load, then keeps tensors resident in CPU/GPU buffers while GGML builds and executes graphs.

AirLLM-like dense streaming therefore forces large storage traffic for every generated token. llama.cpp mmap/partial-offload lets OS page cache and CPU-resident weights remain reusable across tokens and avoids a mandatory full disk reread.

## Candidate integration points for A1.1

If adaptive work is ever reopened:

1. Extend placement around `llama_model_base::load_tensors()` and `llama_model_loader::load_all_data()` rather than replacing GGUF parsing.
2. Add residency policy above GGML backend buffers while retaining Vulkan/SYCL kernels.
3. Reuse backend tensor transfer APIs (`ggml_backend_tensor_set*`/copy) for staged uploads.
4. Explore `TENSOR_READ_LAZY`-like semantics for expert tensors before dense layer streaming.
5. Preserve `llama_kv_cache` and graph scheduler unless measurements prove they are bottlenecks.

## Code paths worth testing later

- `src/llama-model-loader.cpp`: `lazy_read`, mmap mappings, direct-I/O, async upload.
- `src/llama-model.cpp`: device/buffer selection and `n_gpu_layers` placement.
- `ggml/src/ggml-backend.cpp`: graph splits and asynchronous compute.
- `ggml/src/ggml-vulkan/ggml-vulkan.cpp`: transfer/copy and graph execution primitives.
- `ggml/src/ggml-sycl/`: Intel backend as an A/B alternative to Vulkan.
- MoE tensor definitions to determine whether experts can be independently mapped/loaded without rebuilding the inference stack.

## Do not rewrite

Do not rewrite GGUF parsing, quantized matmul kernels, Vulkan/SYCL kernels, tokenizer/sampler/server, KV cache, or GGML graph scheduling. These are mature backend-specific components and are orthogonal to the residency question.

## Architectural answer

An AirLLM-like residency policy can technically be added around llama.cpp's loader/backend-buffer abstractions; a separate runtime is not required. However, A1.0 I/O economics show generic dense layer streaming is not attractive on this machine. If adaptive work is ever reopened, target sparse/expert residency or narrowly scoped lazy tensors, not AirLLM's dense every-layer-per-token streaming loop.
