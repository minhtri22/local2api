# Architecture Challenge and Router Landscape

Status: research-only / proof-before-build

Branch intent: this document is deliberately isolated from the active implementation line. It records architectural criticism, market/repository comparison, hypotheses, and proof gates. Nothing here authorizes implementation by itself.

## 1. Current local2api architecture thesis

`local2api` is currently best understood as an OpenAI-compatible gateway with two independent tracks:

- **Track A — Local Engine**: qualify local models/runtimes and emit a measured `Local Capability Profile`.
- **Track B — Smart Router**: route by task/context/privacy/latency/backend capability and consume Track A's capability profile.

The current separation is correct. The primary architectural risk is no longer model size; it is whether the gateway can preserve context, predict capability boundaries, verify results, and recover safely across heterogeneous backends.

Current proven local evidence:

- 7B: feasible runtime, insufficient production coding/repository quality.
- Qwen2.5-Coder 14B Q4_K_M: 17/20 intended-local quality, Arc 140V + Vulkan proven; current selective quality-tier candidate.
- Qwen3-Coder-30B-A3B Q4_K_M: 18/20 but only small incremental quality; successful inference in the audited experiment was CPU-only; sparse tier remains inconclusive.
- Dense 32B: blocked.

Therefore **14B is the current proven practical tier, not an architectural ceiling**.

## 2. Architecture challenge: highest-risk breakpoints

### H1 — Context ownership is incomplete

Failure mode: routing a multi-turn session across local and cloud backends can fragment constraints, file references, unresolved decisions, and task state.

Hypothesis: the gateway must own canonical conversation/session state and reconstruct backend-independent context. Backends should be treated as near-stateless executors.

Proof before implementation:

- 20 controlled multi-turn sessions.
- Compare Local->Local, Cloud->Cloud, Local->Cloud, Cloud->Local, Local->Cloud->Local.
- Score retained constraints, file references, unresolved decisions, hallucinated prior decisions, and final task success.

Promotion gate: implement gateway-owned context only if cross-backend degradation is material and the proposed reconstruction measurably reduces it.

### H2 — Router rules are not yet a real capability contract

Failure mode: labels such as `14B`, task keywords, or prompt length do not uniquely determine whether a backend can serve a request safely.

Actual capability depends on at least:

- model + runtime + accelerator;
- task class;
- context size;
- output budget;
- concurrency;
- current host resource state;
- privacy and latency constraints.

Hypothesis: routing should become a capability-matching problem rather than a prompt-keyword problem.

Proof:

- Build an empirical `TASK x CONTEXT x RESOURCE_STATE -> success/latency` table from production qualification data.
- Compare its predictions against the existing deterministic heuristic router on a frozen replay set.

Promotion gate: capability matching must predict success/failure materially better without unacceptable routing overhead.

### H3 — HTTP success is not task success

Failure mode: a local model can return HTTP 200 while producing a wrong, incomplete, hallucinated, or unsafe answer.

Hypothesis: mechanically verifiable tasks should use **verification-aware escalation**:

`execute local -> verify -> accept | retry | escalate | fail explicitly`.

Candidate verifiers include tests, compile, lint, type checks, schema validation, structured-output validation, and exact extraction constraints.

Proof:

- Reuse frozen quality cases that have deterministic validators.
- Compare raw 14B result quality vs `14B + verifier + escalation`.
- Measure final correctness, cloud escalation rate, total latency, and unnecessary escalations.

Promotion gate: materially higher final correctness or lower cloud use at the same correctness.

### H4 — Context must be a subsystem, not merely request payload

Failure mode: repository tasks eventually exceed any practical local context if raw files are simply accumulated or truncated.

Hypothesis: introduce a Context Planner that assembles only task-relevant state from symbols, dependency/call graphs, touched files, test failures, recent diff, decisions, summaries, and retrieved snippets.

Proof:

- Select repo tasks with 20K-50K raw source context.
- Compare raw/truncated context, retrieval-only, symbol+dependency+retrieval, and summary+retrieval.
- Measure quality, tokens, TTFT, wall time, and constraint retention.

Promotion gate: preserve or improve quality while materially reducing context tokens and/or latency.

### H5 — Backend trust/availability is under-modeled

Failure mode: a Web2API/session-based backend can fail because of auth expiry, 429, provider UI/API changes, CAPTCHA, moderation, account state, or policy changes. Treating `cloud` as one uniformly reliable backend is unsafe.

Hypothesis: backend profiles need explicit dimensions such as quality, latency, availability, trust, privacy, auth stability, and cost.

Example classes:

- Local: private, zero marginal API cost, resource-constrained.
- Official paid API: externally hosted, high operational predictability, monetary cost.
- Web/session adapter: externally hosted, best-effort availability, fragile auth/session semantics.

Proof:

- Fault-injection matrix across backend classes.
- Verify task-specific fallback behavior and explicit failure when no safe destination exists.

### H6 — Fallback should be a task-specific execution plan, not a static chain

Failure mode: `backend A -> backend B` can silently downgrade a task to a model/backend that cannot satisfy its requirements.

Hypothesis: each request should produce a bounded execution plan with eligible backends and explicit escalation/failure semantics.

Proof:

- Replay a matrix of local unavailable, cloud unavailable, 429, timeout, memory pressure, context overflow, and verification failure across task classes.
- Predeclare expected next action for every cell.

Promotion gate: execution planning must reduce silent unsafe downgrade and ambiguous failures.

### H7 — Host resource state must participate in routing

Failure mode: a model may be capable in a clean benchmark but a poor choice when Windows, VS Code, browser, Docker, Unity, or another workload consumes RAM/GPU resources.

Hypothesis: capability matching needs a resource gate based on free RAM, system commit, model residency, accelerator availability, and optionally recent load latency.

Proof:

- Replay the same tasks under clean, normal developer load, and high-memory-pressure states.
- Compare static routing with resource-aware routing.

Promotion gate: better task completion/latency/system usability without excessive cloud spill.

### H8 — Model lifecycle is part of routing economics

Failure mode: always-resident 14B consumes host memory; unload/reload increases cold-start latency.

Hypothesis: model residency should eventually support explicit states such as HOT/WARM/COLD/EVICTED and a measured keepalive policy.

Proof:

- Measure load cost, idle memory cost, reuse frequency, and latency distribution.
- Compute a practical break-even idle interval before building predictive lifecycle logic.

### H9 — Evaluation can saturate and overfit

Failure mode: the canonical 20-case suite is excellent for comparability but has begun to saturate (14B 17/20, Qwen3 sparse 18/20).

Hypothesis: maintain three distinct layers:

1. frozen core production suite;
2. harder Capability Ceiling Suite;
3. hidden/late holdout used only at final gates.

Do not tune routing thresholds or prompts against the holdout.

### H10 — Product risk: a router alone may not be differentiated enough

If local2api remains only:

`request -> choose model -> return response`

then much of the value overlaps established gateways and routers.

A stronger product thesis is:

**Local-first AI Execution Gateway**

with separable planners:

1. Session/Context Owner
2. Task Requirement Analyzer
3. Context Planner
4. Execution Planner
5. Backend Adapters
6. Result Verifier
7. Telemetry/Capability Learning

Target lifecycle:

`request -> assemble context -> plan execution -> execute -> verify -> accept/retry/escalate/fail -> record evidence`

This is a research target, not an approved rewrite.

## 3. Architecture Challenge Track

### H0 — Current Architecture Baseline

Document current responsibilities, state ownership, routing inputs, fallback behavior, backend contracts, and observability.

### H1 — Context Ownership Proof

Prove or reject cross-backend context loss.

### H2 — Verification + Escalation Proof

Prove or reject whether verifiers materially improve final useful completion compared with raw local inference.

### H3 — Context Planner Proof

Prove or reject whether selective context assembly reduces token/resource costs without quality loss.

### H4 — Capability Routing Proof

Prove or reject capability-contract routing versus current heuristic routing.

### H5 — Resource-Aware Routing Proof

Prove or reject whether host state materially changes the optimal route.

### H6 — Execution Planner Simulation

Compare router-only versus planner+verification+escalation using frozen replay traffic.

Track architecture changes only if their proof phase passes.

## 4. External router/gateway landscape — 2026-09 snapshot

### 4.1 OpenRouter

What it already does well:

- one OpenAI-compatible managed endpoint across many models/providers;
- distinct model-routing and provider-routing layers;
- provider fallback and model fallback;
- routing by price, throughput, reliability and policy constraints;
- provider feature declarations and routing for capabilities such as tool calling;
- private model endpoints are available in enterprise offerings.

Lesson for local2api:

- keep **model selection** separate from **provider/execution selection**;
- represent provider capabilities explicitly;
- record routing reasons and actual selected backend;
- do not duplicate broad hosted-provider aggregation as the core differentiator.

Gap local2api can target:

- host-local inference/resource state;
- privacy-first local execution;
- gateway-owned repo/session context;
- verification-aware escalation;
- model lifecycle/residency.

### 4.2 LiteLLM

What it already does well:

- broad provider normalization behind OpenAI-compatible interfaces;
- Ollama/local endpoints as well as cloud providers;
- retries, fallbacks, load balancing, budgets/cost tracking, auth and observability hooks.

Lesson:

- local2api should not spend its research budget reimplementing a huge provider matrix, billing system, or generic enterprise proxy layer unless needed for the product thesis.
- backend adapters should remain thin and replaceable.

Potential differentiation:

- experimentally qualified local capability profiles;
- resource-aware local/cloud choice;
- repo-context planning;
- verification and escalation semantics.

### 4.3 Portkey AI Gateway

Existing strengths include conditional routing, fallbacks, retries, load balancing, observability and guardrails.

Lesson:

- reliability primitives are table stakes.
- local2api's value cannot be just retries + conditional rules.
- guard/verification decisions should be part of the execution plan, with explicit traces.

### 4.4 Cloudflare AI Gateway

Cloudflare provides analytics/logging, caching, rate limiting, retries, model fallback and dynamic conditional routing with versioned flows.

Lesson:

- versioned routing policy and testable route configuration are strong design patterns.
- local2api should separate policy from runtime code and make routing decisions replayable.
- generic cloud-gateway reliability is already a mature market category.

### 4.5 Vercel AI Gateway

Vercel provides one gateway across many providers with provider failover and routing controls around cost, TTFT/TPS, provider order, and data-retention constraints.

Lesson:

- latency, cost, availability and data-handling policy belong in the backend contract, not ad-hoc if-statements.
- local2api should treat privacy/locality as a first-class hard constraint rather than merely an optimization dimension.

### 4.6 Not Diamond

Not Diamond focuses on learned model routing: predicting which candidate model gives the best quality under cost/latency tradeoffs, including coding-agent routing and custom routers trained on application-specific data.

Lesson:

- a learned/adaptive router is plausible, but local2api should not jump to ML routing before it has a strong labeled dataset from real capability/outcome evidence.
- first build a deterministic capability contract and collect route/outcome telemetry; learned routing should be a later proof-driven step.

### 4.7 RouteLLM

RouteLLM is a research/open-source framework that learns whether a prompt should go to a strong or weak model under a cost-quality threshold.

Lesson:

- routing quality must be evaluated against a measurable strong-vs-weak baseline, not just classifier accuracy.
- a useful local2api replay benchmark should compare final task success and cloud-use reduction against simple baselines such as always-local, always-cloud, static threshold, and manual selection.

### 4.8 Local-first open-source routers

Several GitHub projects now directly overlap the original local2api idea:

- `sarmakska/local-llm-router`: OpenAI-compatible, local Ollama + cloud, deterministic classifier, declarative YAML policy, latency budgets, fallback, metrics, and A/B candidate promotion.
- `routelabsai/router`: local-first local/cloud gateway with privacy-aware routing, verification-aware escalation, route traces, Ollama/llama.cpp/LM Studio/vLLM support, and agent/tool policies.
- `lunargate-ai/gateway`: self-hosted OpenAI-compatible gateway with local Ollama support, weighted/conditional routing, retries, fallback and circuit breakers.
- other small local/cloud routers exist with complexity scoring and YAML policy.

This is important: **the original proposition 'OpenAI-compatible local-first router with cloud fallback' is no longer differentiated by itself.**

The closest architectural overlap is `routelabsai/router`, because it already claims verification-aware escalation and privacy-aware local-first execution. Therefore local2api must prove differentiation through depth, not feature labels.

## 5. Competitive conclusion

### What is already commodity/table stakes

- OpenAI-compatible gateway surface;
- multi-provider adapters;
- retries and health checks;
- static conditional routing;
- model/provider fallback;
- cost/latency metrics;
- local Ollama support;
- privacy rules;
- basic prompt-complexity classification.

### What remains promising as local2api research differentiation

1. **Measured Local Capability Profile tied to exact hardware/runtime**, not generic model labels.
2. **Resource-aware routing on the user's own machine**, including whether loading/keeping a model would degrade the workstation.
3. **Gateway-owned session/repository context that survives backend switching.**
4. **Context planning for coding/repository work**, reducing raw context before inference.
5. **Verification-aware execution**, where a local answer can be mechanically accepted, retried, escalated or rejected.
6. **Explicit task-specific execution plans** rather than blind fallback chains.
7. **Proof-driven architecture development**: every new subsystem requires a measured failure mode and predeclared promotion gate.

## 6. Product thesis after market comparison

Do not position local2api primarily as "another LLM router".

Candidate thesis:

> **local2api is a local-first AI execution gateway that decides not only where to run a task, but what context to send, whether the host can afford the local execution, how to verify the result, and when to escalate without losing session/repository state.**

The value test is not router classifier accuracy. It is whether the system beats manual/backend-static selection on useful task completion while reducing cloud usage, latency/cost, privacy exposure, or human repair.

## 7. Evaluation metric family

Use a multi-dimensional outcome rather than a single synthetic score:

- final task correct/useful;
- wall time / TTFT;
- local compute and host impact;
- cloud calls and monetary cost;
- external data exposure;
- human repair turns;
- fallback/escalation count;
- verification false-positive/false-negative rate.

A shorthand research label may be `UTCE` — Useful Task Completion Efficiency — but do not collapse the above dimensions into one scalar unless empirical evidence shows a stable weighting.

## 8. Research rules

- No architecture subsystem moves to implementation without a separately recorded proof.
- Prefer simple baselines before learned routing.
- Do not tune against the final holdout.
- Keep Track A and Track B separable; Track A continues to publish measured capability profiles.
- A3 production qualification of the current 14B candidate remains valid and independent.
- Dense 32B remains blocked unless a specific capability-ceiling gap provides a testable justification.

## 9. External sources reviewed

Official/product documentation and repositories reviewed for this snapshot:

- OpenRouter routing/fallback/provider documentation: https://openrouter.ai/docs/
- LiteLLM: https://docs.litellm.ai/
- Portkey AI Gateway: https://portkey.ai/features/ai-gateway
- Cloudflare AI Gateway / Dynamic Routing: https://developers.cloudflare.com/ai-gateway/
- Vercel AI Gateway: https://vercel.com/ai-gateway
- Not Diamond model routing: https://docs.notdiamond.ai/docs/what-is-model-routing
- RouteLLM: https://github.com/lm-sys/RouteLLM
- local-llm-router: https://github.com/sarmakska/local-llm-router
- RouteLabs Router: https://github.com/routelabsai/router
- LunarGate: https://github.com/lunargate-ai/gateway

This landscape is time-sensitive and should be rechecked before major product-positioning decisions.
