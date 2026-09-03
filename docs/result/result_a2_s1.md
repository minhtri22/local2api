# A2.S1 Sparse Qualification — superseded summary

Date: 2026-09-04

This legacy report path is retained for history and navigation. Its earlier conclusions were superseded by the audited A2.S1 report after backend discovery, matched 14B control repair, manual re-review, and evidence validation.

Canonical report: [result_a2_s1_qwen3_coder.md](result_a2_s1_qwen3_coder.md)

Current audited conclusions:

- A2.S1 final verdict: **`SPARSE_INCONCLUSIVE`**.
- Incremental quality verdict: **`INCREMENTAL_QUALITY_SMALL`**.
- Canonical intended-local quality: Qwen3 **18/20**, frozen 14B **17/20**.
- Historical 14B failure recovery: **1/3** (`A04` only).
- Matched challenge keyword score: **14B 1/3, Qwen3 1/3**.
- Audited manual mean: **14B 1.85/3, Qwen3 2.00/3**.
- Successful Qwen3 CPuFriend observations were **CPU-only** under the audited installation; successful Qwen3 Arc/Vulkan inference is **not qualified**.
- Qwen3 1K CPU observation: TTFT **50.255 s**, wall **60.526 s**, decode **6.136 tok/s**.
- Qwen3 4K CPU observation: TTFT **333.053 s**, wall **349.820 s**, decode **3.758 tok/s**; the 300 s TTFT gate was exceeded.
- 8K and 16K direct runs: **NOT COMPLETED** after the 4K gate violation.
- Durable post-smoke memory snapshot: working set **18,504,175,616 bytes**, private bytes **14,432,628,736 bytes**, available physical memory **572,256 KiB**; classification **`SYSTEM_PRESSURED`**. Qwen3 peak system commit was not captured.
- No separate Qwen3 local tier is qualified from current evidence.
- Dense A2.2 32B remains **BLOCKED**.

The earlier `SPARSE_NOT_JUSTIFIED_OVER_14B` verdict, 2.65/2.55 manual means, direct-Vulkan attribution, micro-batch causal claim, and 176x/697x cross-runtime TTFT ratios are withdrawn. See `docs/result/evidence/a2_s1/audit_corrections.md` for the correction record and the canonical report for full evidence and limitations.
