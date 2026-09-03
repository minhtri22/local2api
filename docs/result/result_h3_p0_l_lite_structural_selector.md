# H3.P0-L-lite — Dependency-aware Structural Selector Sandbox Proof

## Status

**Executed in sandbox on 2026-09-04.** Research-only on branch `research/architecture-challenge`. No production code or `main` changes are authorized by this result.

## Question

Can dependency-aware structural evidence selection repair the H3.P0-S fidelity gap without giving up material context reduction?

H3.P0-S left the strongest HYBRID baseline at ~55.9% median reduction but only 91.7% mean required-evidence recall on the frozen 12-task adversarial indirect-module holdout, below the predeclared 95% gate.

## Frozen gates

- median context reduction >= 30%
- hard-constraint retention = 100%
- mean required-evidence recall >= 95%
- deterministic replay = PASS

The selector is forbidden from reading `required_ids` or the synthetic `Block.required` labels.

## Method

`STRUCTURAL_HYBRID` keeps the previous lossless zone (exact request/constraints plus error/test evidence), takes a bounded lexical seed, then performs bounded dependency closure using generic repository-like signals:

1. function call -> exact function definition provider;
2. selected code/test/error quoted anchor -> exact code/config block carrying the same anchor;
3. stable source ordering and a fixed context budget;
4. remaining budget filled by the prior lexical ranking.

No small LLM is used. The current prototype extractor is deliberately lightweight regex over Python/YAML-like fixtures; it is not proposed as production parsing code.

Two structural budgets were measured. `STRUCTURAL_HYBRID_TIGHT` uses a 45% raw-context budget and 20% lexical seed, while the looser version uses 55% / 28%.

## Frozen H3.P0-S holdout result

| Pipeline | Median reduction | Mean evidence recall | Min recall | Hard constraints | Full-evidence tasks | Gate |
|---|---:|---:|---:|---:|---:|---|
| HYBRID baseline | 55.90% | 91.67% | 75% | 100% | 8/12 | FAIL |
| STRUCTURAL_HYBRID | 46.09% | 100% | 100% | 100% | 12/12 | PASS |
| **STRUCTURAL_HYBRID_TIGHT** | **56.69%** | **100%** | **100%** | **100%** | **12/12** | **PASS** |

The tight structural selector recovered the missing indirect config evidence in H02, H03, H08 and H09 while preserving approximately the same compression ratio as the old HYBRID baseline.

## Post-freeze structural validation v2

Because the original 12-task holdout is frozen but not blinded to the researcher, a separate 18-task synthetic validation was generated **after the selector file had been frozen**. It uses two-hop call chains (`entry -> bridge -> profile selector -> config`) plus same-module and documentation distractors.

`STRUCTURAL_HYBRID_TIGHT` result:

- median reduction: **56.12%**
- mean evidence recall: **100%**
- minimum evidence recall: **100%**
- hard-constraint retention: **100%**
- full-evidence tasks: **18/18**
- all fidelity gates: **PASS**

This is stronger evidence than the original known holdout, but it is still synthetic and not a real-repository or downstream-model proof.

## Verdict

**`H3_STRUCTURAL_SELECTOR_FIDELITY_GATE_PASS`**

The specific H3.P0-S fidelity gap is repaired in the bounded synthetic setting without an LLM: dependency-aware structural selection improved the frozen holdout from 91.7% to 100% evidence recall while retaining ~56.7% median context reduction.

This materially changes the next-step priority. A small LLM is **not yet justified** merely to repair indirect-dependency recall. Structural/symbol-aware context planning should remain the control baseline for any future semantic-model experiment.

## What is now supported

- material context reduction and high evidence fidelity can coexist in these synthetic repository contexts;
- simple lexical/path rules were insufficient, but explicit dependency closure repairs the observed failure mode;
- exact hard constraints can remain outside the lossy selector;
- a structural-only method is strong enough to become the baseline that a small-model semantic selector must beat.

## What is NOT proven

- downstream cloud task success is preserved;
- provider billing-token reduction or prompt-cache economics;
- performance on real repositories/languages/build systems;
- structural extraction quality with production parsers (tree-sitter/LSP/static analysis);
- local compiler latency, Arc 140V utilization, RAM or energy economics;
- whether a 1.5B/3B/7B semantic selector adds useful recall beyond the structural baseline.

## Next proof

Do **not** implement Context Compiler product code yet.

Recommended next step: **H3.P0-C — Downstream Cloud A/B**, using the structural-tight compiler as the frozen compiled-context baseline:

1. `RAW -> same cloud model`;
2. `STRUCTURAL_COMPILED -> same cloud model`;
3. identical tasks, answer rubric and output budget;
4. measure real input tokens, task success, hard-constraint adherence, TTFT/wall time, cache behavior where observable, and external context exposure.

A small-model semantic-selector experiment should be reopened only if real repositories expose gaps that the structural baseline cannot cover, or if it materially improves downstream success at similar compression.

Hardware economics remain deferred to H3.P0-H on the target workstation.
