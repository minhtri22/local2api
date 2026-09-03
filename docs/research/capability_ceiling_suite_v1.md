# Capability Ceiling Suite v1

Date: 2026-09-04

## Purpose

Capability Ceiling Suite v1 is a separate research benchmark for finding where the current 14B local tier stops being sufficient. It does not replace the frozen production-local 20-case suite used for A2 quality qualification.

The suite contains 14 realistic engineering cases spanning multi-file call paths, cross-module localization, constrained architecture change, multi-step repair planning, dependency impact, incomplete evidence, context prioritization, competing constraints, repository-wide planning, and hallucination resistance.

## Scoring

The frozen rubric is:

- 0: incorrect or hallucinated;
- 1: partial issue identification but unusable;
- 2: mostly correct with major omissions;
- 3: correct with minor omissions;
- 4: strong production-quality answer;
- 5: expert-level complete answer.

Mechanical keyword scoring is retained as provenance only. Final baseline uses manual review because several answers mention expected words while violating task constraints or inventing unseen repository facts.

| Case | Category | Mechanical | Final manual | Main finding |
|---|---|---:|---:|---|
| CC01 | C1 | 3 | 1 | Generic call-path description; wrong router semantics |
| CC02 | C2 | 4 | 2 | Evidence plan useful, localization still generic |
| CC03 | C3 | 4 | 0 | Fabricated files/configuration |
| CC04 | C4 | 4 | 1 | Generic diagnosis, not repo-specific smallest fix |
| CC05 | C5 | 2 | 2 | Major dependency omissions under cap |
| CC06 | C6 | 4 | 4 | Strong incomplete-evidence handling |
| CC07 | C7 | 4 | 2 | Correct priorities plus invented file |
| CC08 | C8 | 3 | 2 | Loses narrower fallback constraint |
| CC09 | C9 | 3 | 2 | Generic refactor plan; weak rollback/preservation detail |
| CC10 | C10 | 4 | 0 | Hallucinated verification of unseen OAuth logic |
| CC11 | C1/C5 | 4 | 2 | Incomplete degradable/non-degradable HTTP semantics |
| CC12 | C5 | 3 | 3 | Good context-ownership impact analysis; incomplete privacy depth |
| CC13 | C8 | 3 | 2 | Migration plausible but constraint retention incomplete |
| CC14 | C10 | 2 | 4 | Correctly refuses to fabricate absent diff |

Final 14B baseline: **27/70**, mean **1.93/5**. Mechanical provenance score: **47/70**.

## Freeze decision

**SUITE_FROZEN = YES.**

The suite is not near-perfect, exposes multiple concrete failure modes, covers realistic repository engineering, and has a reproducible rubric. The prompts and fixtures were not changed after observing CC01-CC11. CC12-CC14 used the same predeclared definitions already present in the A3 runner.

Future candidates must run these exact prompts/fixtures and be manually reviewed under the same rubric. Candidate-specific prompt tuning, category weighting, or changing expected evidence after seeing outputs invalidates comparison.

## Main capability gaps exposed

1. Gateway-independent multi-turn constraint retention is weak: A3 consistency passed only 2/5 sessions.
2. Repo-grounded multi-file reasoning degrades into generic architecture prose or invented files under harder tasks (CC01, CC03, CC04, CC09).
3. Hallucination resistance is inconsistent when a prompt asserts evidence that was not supplied (CC10 versus strong CC14).
4. Competing constraints are not retained reliably, especially fallback and migration constraints (CC08, CC13).
5. Long-context usefulness is bounded by realistic prefill cost: TTFT rises to ~142 s at 8K, ~390 s at 12K and ~649 s at 16K.

Evidence:

- `docs/result/evidence/capability_ceiling_v1/suite_definition.json`
- `docs/result/evidence/capability_ceiling_v1/ceiling_suite_results_14b.json`
- `docs/result/evidence/capability_ceiling_v1/manual_review.json`
