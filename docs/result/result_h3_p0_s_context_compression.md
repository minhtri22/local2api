# H3.P0-S — Local Context Compression Sandbox Feasibility

## Status

**Executed in sandbox on 2026-09-04.** This is a bounded research proof on branch `research/architecture-challenge`; it does not modify `main` and does not authorize production implementation.

## Question

Can a local context-compilation layer materially reduce context sent to cloud while preserving hard constraints and task-relevant evidence?

## Predeclared fidelity gates

- median context reduction >= 30%
- hard-constraint retention = 100%
- mean required-evidence recall >= 95%
- deterministic lossless sections / provenance retained

Token counts use a deterministic regex lexical-token proxy. They are suitable for within-experiment reduction ratios, **not provider billing-token claims**.

## Pipelines

1. `RAW` — full context.
2. `RULES` — deterministic trimming based on block kind/path.
3. `RETRIEVAL` — TF-IDF relevance selection under a fixed budget.
4. `HYBRID` — lossless task/constraints/errors/tests + relevance selection + deterministic history extraction; stable source ordering.

No small local LLM model was available in the sandbox, so the LLM compression arm was **not executed**. No downstream cloud model was called, so this proof does **not** claim task-success preservation. Hardware/Arc/latency economics are also out of scope.

## Pilot — 30 labeled realistic synthetic repository contexts

| Pipeline | Median reduction | Mean evidence recall | Hard constraints | Full-evidence tasks | Gate |
|---|---:|---:|---:|---:|---|
| RAW | 0.0% | 100.0% | 100.0% | 30/30 | reduction FAIL |
| RULES | 76.8% | 100.0% | 100.0% | 30/30 | PASS |
| RETRIEVAL | 58.4% | 87.5% | 100.0% | 20/30 | evidence FAIL |
| HYBRID | 57.6% | 100.0% | 100.0% | 30/30 | PASS |

The pilot superficially suggested `RULES` was sufficient. That result was treated as potentially fixture-biased rather than promoted.

## Adversarial holdout — 12 indirect-module contexts

After the pilot, a separate adversarial holdout was created with required evidence deliberately crossing obvious category paths (shared dispatcher/config evidence) and with high-overlap near distractors. **Pipeline algorithms were not changed before the holdout run.**

| Pipeline | Median reduction | Mean evidence recall | Min recall | Hard constraints | Full-evidence tasks | Gate |
|---|---:|---:|---:|---:|---:|---|
| RAW | 0.0% | 100.0% | 100.0% | 100.0% | 12/12 | reduction FAIL |
| RULES | 70.6% | 50.0% | 50.0% | 100.0% | 0/12 | evidence FAIL |
| RETRIEVAL | 57.9% | 66.7% | 25.0% | 100.0% | 4/12 | evidence FAIL |
| HYBRID | 55.9% | 91.7% | 75.0% | 100.0% | 8/12 | evidence FAIL |

The holdout invalidates the pilot-only conclusion that deterministic rules are sufficient. `HYBRID` remains the strongest bounded candidate: ~56% median reduction, 100% hard-constraint retention, but only 91.7% mean required-evidence recall, below the predeclared 95% gate.

## Verdict

**`H3_CONTEXT_COMPILER_PROMISING_BUT_FIDELITY_GATE_NOT_MET`**

The core hypothesis survives, but it is **not proven enough to implement**. The experiment demonstrates that large material context reduction is feasible, but the hard part is evidence recall across indirect dependencies, not prompt rewriting.

The result also rejects a simplistic design:

`raw context -> summarize -> cloud`

Instead, any next experiment must preserve a lossless zone and improve dependency-aware evidence selection.

## What is proven

- Material reduction is easy: all non-RAW approaches exceeded the 30% reduction gate.
- Exact hard constraints can be preserved deterministically (100% in pilot and holdout).
- Pure lexical retrieval is unsafe as a sole selector on indirect-module tasks.
- Simple path/kind rules overfit obvious repository layouts and collapse on indirect evidence.
- A hybrid structured compiler is directionally better, but current evidence recall is below production threshold.

## What is NOT proven

- cloud downstream task success is preserved;
- real provider input-token savings or prompt-cache economics;
- a 1.5B/3B/7B local LLM improves evidence recall;
- local compiler latency or Arc 140V efficiency;
- privacy improvement beyond reduced selected context;
- performance on real large repositories.

## Next proof — do not implement product code yet

Recommended next experiment: **H3.P0-L — Semantic Selector / Small-Model Proof**.

Freeze the current adversarial holdout and compare, without tuning on it:

1. current HYBRID baseline;
2. dependency/symbol-aware deterministic selector;
3. small local model used only for relevance/evidence classification, not solving;
4. hybrid deterministic + small-model selector.

Only proceed toward H3.P1 if the frozen holdout reaches >=95% mean evidence recall, 100% hard constraints, >=30% median reduction, then a downstream cloud A/B demonstrates task-success preservation.

Hardware economics belong in the later H3.P0-H step.
