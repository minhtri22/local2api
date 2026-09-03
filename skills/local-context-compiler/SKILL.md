# Local Context Compiler Skill (H3.D0 prototype)

Use this skill only when a repository/code task has enough raw context that local compaction may reduce what must be sent to a stronger cloud model.

## Invariants

1. Preserve the latest user task verbatim.
2. Preserve hard constraints verbatim; never summarize prohibitions, required compatibility, exact errors, test failures, or API contracts.
3. Prefer deterministic structural selection before semantic summarization.
4. Expand selected code through explicit imports/calls/config references under a fixed budget.
5. Every selected evidence block must retain provenance (`path`, `reason`).
6. If dependency coverage is uncertain, include more raw evidence or fall back to raw context. Do not guess.
7. The cloud agent remains responsible for diagnosis/patching. The compiler must not solve the task.

## Preferred flow

- For small context, skip compilation.
- For larger context, invoke `scripts/context_compile.py` locally before sending repository content to cloud.
- Send the resulting Context IR plus this policy; do not additionally attach the raw repository unless the compiler reports insufficient coverage.

## Context IR

Required sections: `task`, `hard_constraints`, `evidence`, `omitted`, `stats`, and `provenance`.
