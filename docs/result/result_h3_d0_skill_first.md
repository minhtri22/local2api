# H3.D0 — Skill-first Delivery Prototype + A/B

## Status

**Executed in sandbox on 2026-09-04.** Research-only on branch `research/architecture-challenge`. This experiment does not modify `main`, does not authorize production integration, and does not claim downstream cloud quality preservation.

## Question

Can the H3 structural context-compiler idea be delivered as an agent skill plus a tiny local deterministic tool, rather than first building a full local2api context subsystem?

The critical distinction is where compaction happens. A cloud-only skill cannot reduce the first request's cloud input if the raw repository/context must already be uploaded for the cloud agent to decide what to remove. A skill that invokes a local tool can compact before external handoff.

## Prototype

The sandbox prototype contains:

- `skills/local-context-compiler/SKILL.md` — policy/invariants and when to invoke local compaction;
- `scripts/context_compile.py` — standard-library-only dependency-aware compiler prototype;
- `tests/h3_d0/run_h3_d0.py` — 24-task A/B harness;
- `docs/result/evidence/h3_d0/summary.json` — machine-readable aggregate evidence;
- `docs/result/evidence/h3_d0/context_ir_schema.json` — Context IR schema.

The tool preserves a lossless zone, selects lexical seeds, expands explicit structural dependencies (function definition providers, imports and exact policy/config anchors), packs to a fixed budget, and emits provenance. It is intentionally research code, not a production parser.

## Comparison

Three delivery paths were compared on 24 new synthetic repository tasks with two-hop indirect dependencies and high-overlap distractors:

1. `RAW` — raw task/context sent to cloud.
2. `SKILL_ONLY` — the cloud agent receives skill instructions plus raw context and performs any selection itself.
3. `SKILL_PLUS_LOCAL_TOOL` — the skill invokes the local structural compiler first; cloud receives the skill policy plus Context IR only.

Required evidence labels are used only by the evaluator; the compiler cannot read them.

### Gates for the local-tool arm

- median external/cloud input reduction >= 30% versus RAW;
- mean required-evidence recall >= 95%;
- hard-constraint retention = 100%;
- deterministic replay = PASS.

Token measurement uses a deterministic lexical-token proxy. It is **not** provider billing-token evidence.

## Results

| Delivery path | Cloud input effect vs RAW | Evidence recall | Hard constraints | Interpretation |
|---|---:|---:|---:|---|
| RAW | baseline | 100% available | 100% available | No compaction |
| SKILL_ONLY | **+13.36% median** | raw remains available | raw remains available | Skill instructions add tokens; first-request input is not reduced because cloud already needs raw context |
| **SKILL_PLUS_LOCAL_TOOL** | **-43.61% median** | **100% mean / 100% min** | **100%** | All bounded gates PASS |

The skill text itself costs ~228 lexical proxy tokens. This is material: structural selection can remove roughly half of repository context in these fixtures, but policy instructions consume some of that gain. The skill should therefore remain compact and stable.

Python syntax compilation passed for the prototype and harness. Repeated execution produced byte-identical aggregate evidence, so deterministic replay passed.

## Verdict

**`H3_SKILL_PLUS_LOCAL_TOOL_DELIVERY_FEASIBLE`**

The bounded deployment hypothesis passes: a skill + local deterministic compiler can preserve the H3 structural-selection benefit without requiring a gateway rewrite, while a cloud-only prompt skill does **not** solve first-request token minimization and increases input size in this experiment.

This does **not** mean a production skill is ready. The correct conclusion is narrower:

> Skill-first is a credible low-cost delivery mechanism for proving Context Compiler value before embedding it into local2api core.

## Architectural implication

Preferred research architecture:

```text
cloud agent
    |
    | reads compact policy skill
    v
local context compiler tool
    |
    | lossless constraints + dependency-aware Context IR
    v
cloud model / existing router
```

Responsibility split:

- **Skill:** when to compile, what is lossless, when to fall back to raw context.
- **Local tool:** file/dependency selection, budgeting, provenance and deterministic mechanics.
- **Cloud agent/model:** diagnosis, reasoning, patching and review.

This avoids turning local2api into a broad agent framework and avoids duplicating provider/model-routing products.

## What this weakens

A pure cloud-side “context compression skill” is not sufficient for the original token/data-minimization thesis on the initial handoff. If raw context is already visible to cloud, the input-token and external-exposure savings have already been lost for that request.

## What is still NOT proven

- downstream cloud task success is preserved;
- real provider tokenizer/billing savings;
- prompt-cache economics;
- real Claude/Codex/Gemini/Cline/Continue skill/tool integration behavior;
- real repositories, languages and build systems;
- latency/setup friction in an actual agent loop;
- security/redaction quality;
- whether Context IR causes subtle reasoning losses not represented by evidence-recall labels.

## Recommended next proof

Do not build a full gateway subsystem yet.

Proceed to **H3.D1 — Real Agent/Cloud Downstream A/B** when an external agent/cloud path is available without disturbing the user's workstation:

1. same repository task and same cloud model;
2. RAW vs SKILL_PLUS_LOCAL_TOOL;
3. measure provider-reported input tokens where available;
4. score final task success, constraint adherence and repair turns;
5. record TTFT/wall time and prompt-cache behavior;
6. keep the structural compiler frozen during the comparison.

If H3.D1 preserves downstream task quality with material real-token savings, the skill-first artifact can be tested across multiple agent ecosystems before deciding whether local2api core should own it.
