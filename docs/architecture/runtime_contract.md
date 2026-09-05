# Canonical Runtime Contract

## Canonical Runtime: `llama-server`

This document defines the canonical runtime for local2api production acceptance.

## Contract

| Field | Value |
|-------|-------|
| `canonical_runtime` | `llama-server` |
| `production_acceptance_runtime` | `llama-server` |
| `ollama_status` | `historical_control_only` |
| `fallback_to_ollama` | `false` |
| `acceptance_requires_llama_server` | `true` |

## Rationale

The canonical runtime for local2api production acceptance is `llama-server` (from llama.cpp). 

Ollama is designated as **historical control only** - it was used in earlier research phases (A3) but is NOT the canonical runtime for production acceptance.

Key reasons:
1. **Reproducibility**: llama-server provides direct control over llama.cpp parameters
2. **Vulkan/GPU control**: Explicit GPU layer offload, tensor split, flash-attn control
3. **Flash-attention**: Native flash-attn support without Ollama abstraction layer
4. **Quantized KV cache**: Direct control over KV cache quantization (q4_0, fp16, etc.)
4. **Deterministic behavior**: Direct llama.cpp parameter control for reproducibility

Ollama remains available as a historical reference but MUST NOT be used for acceptance testing.