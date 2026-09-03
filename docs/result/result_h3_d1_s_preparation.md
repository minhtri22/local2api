# H3.D1-S — Real-repo Downstream A/B Preparation

## Status

**PREPARED / FROZEN, NOT CLOUD-EXECUTED.** Research-only on `research/architecture-challenge`; no `main` or production architecture change is authorized.

The sandbox prepared the experiment contract, frozen task/rubric set, real-repository payload builder, and OpenAI-compatible cloud A/B harness. The container itself could not clone GitHub (`Could not resolve host: github.com`), so the real-repository payload-generation preflight must be executed from a checkout with the repository files present. This limitation is explicit and no token-saving result is fabricated.

## Source freeze

- repository: `minhtri22/local2api`
- research source commit used to freeze tasks: `5c93548d81c9b9a93ae176fa3b9a0c68710ce20e`
- frozen tasks: 12
- dataset file: `docs/result/evidence/h3_d1/frozen_tasks.json`

Tasks cover real local2api behavior: routing precedence, model overrides, streaming vs non-streaming fallback, route observability, context ownership status, Track A/B contract, H3 evidence boundaries, skill-vs-tool privacy boundary, compiler limitations, privacy semantics, and proof-before-build governance.

## Frozen comparison

### Arm A — RAW

`exact task + exact hard constraints + raw eligible repository context -> fixed cloud model`

### Arm B — COMPILED

`exact task + exact hard constraints + small stable skill + structural Context IR -> same fixed cloud model`

Both arms must use the same model, temperature, output budget and task wording.

## Predeclared downstream gates

A final H3.D1 verdict requires all of the following to be measured from actual cloud execution:

1. median provider-reported input-token reduction >= 30% where the provider reports usage;
2. hard-constraint adherence in COMPILED is not worse than RAW;
3. task success degradation <= 1 task out of 12 in this first bounded run;
4. zero critical failures caused by missing compiled evidence;
5. every RAW-success / COMPILED-failure case must be investigated for omitted context before any promotion.

Proxy-token reduction from `prepare_payloads.py` is diagnostic only and must not be presented as billing-token reduction.

## Artifacts

- `docs/result/evidence/h3_d1/frozen_tasks.json` — frozen tasks and rubrics.
- `tests/h3_d1/prepare_payloads.py` — reads a real checkout and produces RAW payloads, Context IR, COMPILED payloads and `preflight.json`.
- `tests/h3_d1/run_cloud_ab.py` — provider-neutral OpenAI-compatible A/B execution harness.
- expected generated evidence:
  - `docs/result/evidence/h3_d1/raw_payloads/*.json`
  - `docs/result/evidence/h3_d1/compiled_payloads/*.json`
  - `docs/result/evidence/h3_d1/context_ir/*.json`
  - `docs/result/evidence/h3_d1/preflight.json`
  - `docs/result/evidence/h3_d1/cloud_runs_raw.json`
  - `docs/result/evidence/h3_d1/cloud_runs_compiled.json`

## Safety/reproducibility rules

- API keys are environment variables only and must never be committed.
- Do not download model artifacts for this task.
- Do not change task wording, rubrics, compiler budget ratios or focus paths after seeing cloud outputs.
- Do not tune the compiler against individual D1 tasks.
- Do not merge to `main`.
- Commit generated evidence only after removing secrets and verifying no private credentials or unrelated repository secrets are present.

## H3.D1-S verdict

**`H3_D1_DOWNSTREAM_AB_READY_FOR_EXTERNAL_EXECUTION`**

This is a readiness verdict only. It does **not** mean the skill-first approach has preserved downstream quality or saved provider tokens. Those claims require the external execution phase on a fixed cloud model.
