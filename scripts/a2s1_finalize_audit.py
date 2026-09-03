"""Assemble reviewed A2.S1 artifacts without rerunning inference or changing raw outputs."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from hw1_quality import CASES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/result/evidence/a2_s1'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def save(name, value):
    with (OUT / name).open('w', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def archive(name, archived):
    if not (OUT / archived).exists():
        save(archived, read(name))


def summary(rows):
    return {cls: {'passed': sum(bool(r['mechanical_pass']) for r in rows
                               if cls == 'INTENDED_LOCAL' or r['class'] == cls),
                  'total': sum(cls == 'INTENDED_LOCAL' or r['class'] == cls for r in rows)}
            for cls in ['LOCAL_SAFE', 'LOCAL_ACCEPTABLE', 'INTENDED_LOCAL']}


def main():
    candidate = read('quality_results_128.json')
    control = read('control_14b_cpu_results.json')
    review = read('manual_review_audit.json')
    expected = [(i, c, p, {'contains_all': n}) for i, c, p, n in CASES if c != 'CLOUD_REQUIRED']
    for rows in [candidate['cases'], control['cases']]:
        assert [(r['task_id'], r['class'], r['prompt'], r['criteria']) for r in rows] == expected
        assert all(r['status'] == 'ok' for r in rows)
        assert all(r['mechanical_pass'] == all(x.lower() in r['output'].lower()
                   for x in r['criteria']['contains_all']) for r in rows)
    assert len(control['challenge_cases']) == 3
    assert review['status'] == 'complete'
    assert len(review['candidate']) == len(review['control']) == 20
    archive('quality_results.json', 'quality_results_96_exploratory.json')
    archive('manual_quality_review.json', 'manual_quality_review_pre_audit.json')
    archive('comparison_14b_vs_qwen3.json', 'comparison_pre_audit.json')
    archive('runtime_config.json', 'runtime_config_predeclared.json')
    archive('model_metadata.json', 'model_metadata_pre_audit.json')
    candidate['source_raw'] = 'quality_results_128.json'
    candidate['effective_backend'] = 'CPU; see backend_discovery_audit.json'
    candidate['runtime_config']['ngl_effective'] = 0
    candidate['runtime_config']['ngl_note'] = '32 requested, but no GPU backend available in CPuFriend installation.'
    (OUT / 'quality_outputs').mkdir(exist_ok=True)
    for r in candidate['cases']:
        score = review['candidate'][r['task_id']]
        r['manual_score'] = score['score']
        r['manual_note'] = score['note']
        r['truncation_basis'] = 'output token count reached cap and manual inspection; stop_type was not retained in raw run'
        r['ttft_note'] = 'Not measured by the non-streaming quality request.'
        with (OUT / 'quality_outputs' / (r['task_id'] + '.txt')).open('w', encoding='utf-8', newline='\n') as f:
            f.write(r['output'])
    save('quality_results.json', candidate)
    manual = {'schema': 'local2api.a2_s1.manual_quality.v2', 'rubric': review['rubric'],
              'candidate_cases': review['candidate'], 'matched_control_cases': review['control'],
              'policy': review['policy'], 'malformed_protocol_count': 0,
              'repetition_failure_count': 0,
              'candidate_generation_cap_reached_count': sum(r['truncation'] for r in candidate['cases'])}
    for label in ['candidate', 'control']:
        scores = [r['score'] for r in review[label].values()]
        manual[label + '_mean'] = statistics.mean(scores)
        manual[label + '_distribution'] = dict(Counter(scores))
    save('manual_quality_review.json', manual)
    old = json.loads((ROOT / 'docs/result/evidence/a2_1_14b/quality_results.json').read_text(encoding='utf-8-sig'))
    original_failures = [r for r in old['cases'] if r['class'] != 'CLOUD_REQUIRED' and not r['pass']]
    assert [r['id'] for r in original_failures] == ['A04', 'D01', 'D05']
    recovery = []
    for old_row in original_failures:
        cid = old_row['id']
        new = next(r for r in candidate['cases'] if r['task_id'] == cid)
        matched = next(r for r in control['cases'] if r['task_id'] == cid)
        before = review['historical_14b_failure_review'][cid]
        after = review['candidate'][cid]
        recovery.append({'task_id': cid, 'prompt': old_row['prompt'],
                         'expected_criteria': old_row['criteria'], '14b_output': old_row['response'],
                         'missing_keywords_14b': [k for k in old_row['criteria']['contains_all'] if k.lower() not in old_row['response'].lower()],
                         '14b_failure_reason': before['note'], 'qwen3_output': new['output'],
                         'qwen3_mechanical_pass': new['mechanical_pass'],
                         'manual_14b_score': before['score'], 'manual_qwen3_score': after['score'],
                         'manual_score_delta': after['score'] - before['score'],
                         'capability_delta': 'Clearer empty-input validation framing; no change in usability band.' if cid == 'A04' else 'No recovered backend/context reasoning criterion.',
                         'matched_control_output': matched['output'],
                         'matched_control_mechanical_pass': matched['mechanical_pass']})
    save('failure_recovery_analysis.json', {'cases': recovery, 'recovered': sum(r['qwen3_mechanical_pass'] for r in recovery), 'total': 3})
    challenge = read('challenge_14b_vs_qwen3.json')
    if 'original_failed_control_attempts' not in challenge:
        challenge['original_failed_control_attempts'] = challenge['runs']['14b_control']
    challenge['runs']['14b_control'] = {r['task_id']: r for r in control['challenge_cases']}
    challenge['audit_note'] = 'Same three predeclared prompts/criteria and 96-token cap, CPuFriend CPU runtime. Candidate outputs retained; control rerun with Qwen3 unloaded. Separate sessions, no latency comparison. Generic challenges do not establish multi-file repository capability.'
    challenge['manual_review'] = review['challenge']
    for label in ['14b_control', 'qwen3_sparse']:
        rows = list(challenge['runs'][label].values())
        challenge[label + '_keyword_score'] = {'passed': sum(r['mechanical_pass'] is True for r in rows), 'total': 3}
    save('challenge_14b_vs_qwen3.json', challenge)
    header = read('gguf_header_audit.json')
    metadata = read('model_metadata.json')
    metadata.update(head_dim=128, shared_experts=0,
        active_parameters_per_token=header['structural_active_parameters_including_embedding_table'],
        active_parameters_source='Derived from local GGUF tensor inventory; conventional active footprint includes the whole input embedding table.',
        active_parameters_note=header['active_count_note'],
        all_expert_parameters=header['all_expert_parameters'],
        selected_expert_parameters_per_token=header['selected_expert_parameters_per_token'],
        nonexpert_parameters_resident=header['nonexpert_parameters_resident'],
        touched_parameter_estimate_one_embedding_row=header['touched_parameter_estimate_one_embedding_row'],
        audit_source='gguf_header_audit.json')
    metadata['ffn_dimensions']['expert_shared_feed_forward_length'] = 0
    assert metadata['gguf_sha256'].lower() == header['sha256']
    save('model_metadata.json', metadata)
    runtime = {'schema': 'local2api.a2_s1.runtime_config.v2',
        'predeclared_config': 'runtime_config_predeclared.json',
        'device_discovery': 'backend_discovery_audit.json',
        'primary_ollama': {'version': '0.33.2', 'device': 'Arc 140V/Vulkan', 'result': 'Repeated startup OOM; no successful Qwen3 completion'},
        'successful_candidate_runtime': {'path': 'D:/WORK/RESEARCH/CPuFriend/bin/llama-server.exe', 'build': '10726 / 85c55223c', 'backend': 'CPU', 'requested_ctx': 4096, 'requested_ngl': 32, 'effective_ngl': 0, 'batch': 32, 'ubatch': 16, 'kv': 'q4_0', 'flash_attn_requested': 'on', 'n_parallel': 'not specified; audit control logs show 4 default slots'},
        'quality': {'max_tokens': 128, 'temperature': 0, 'top_p': 1, 'top_k': 40, 'seed': 42, 'template': 'hw1_prod_gate.render_chat', 'stream': False, 'cache_prompt': False},
        'challenge': {'max_tokens': 96, 'control_repaired': True},
        'early_stop': {'ttft_seconds': 300, 'wall_seconds': 600, 'historical_4k_enforced': False, 'larger_contexts': 'NOT_COMPLETED'},
        'qwen3_vulkan_inference_qualified': False, 'dense_32b': 'BLOCKED'}
    save('runtime_config.json', runtime)
    perf = read('benchmark_direct_llama_server_minimal.json')
    perf['provider'] = 'direct_llama_server_CPU'
    perf['source_raw'] = 'benchmark_direct_llama_server_minimal.json'
    perf['runtime_config']['effective_ngl'] = 0
    perf['runtime_config']['requested_ngl'] = perf['runtime_config'].pop('ngl')
    perf['cold_load_ttft_ms'] = None
    perf['cache_policy'] = 'model previously loaded; cache_prompt=false; raw cache_n=0. Not cold disk/model startup.'
    perf['comparison_limit'] = 'Historical Ollama control used repeated warmed prompts; cache counts not retained. No cross-runtime speed ratios.'
    perf['levels']['4k']['gate'] = {'status': 'COMPLETED_BUT_TTFT_GATE_EXCEEDED', 'threshold_ms': 300000, 'cancellation_enforced': False}
    for label in ['8k', '16k']:
        perf['levels'][label] = {'status': 'NOT_COMPLETED', 'reason': 'No larger direct run after 4K exceeded TTFT threshold.'}
    attempts = []
    for file in sorted(OUT.glob('load_smoke*.json')):
        item = json.loads(file.read_text(encoding='utf-8-sig'))
        attempts.append({'file': file.name, 'options': item['request']['options'], 'status': item.get('status', 'error'), 'wall_ms': item.get('wall_ms'), 'error': item.get('error_body', item.get('error'))})
    perf['ollama_attempts'] = attempts
    perf['optional_cpu_moe_ab'] = 'NOT_RUN: repeated primary OOM and no qualified GPU baseline.'
    save('benchmark_runs.json', perf)
    process = read('process_after_direct_smoke_4k.json')
    system = read('system_after_direct_smoke_4k.json')
    row = next(r for r in process if r['ProcessName'] == 'llama-server')
    telemetry = {'qwen3_source': 'post-smoke snapshots, not peak trace',
        'qwen3_working_set_bytes': row['WorkingSet64'], 'qwen3_private_bytes': row['PrivateMemorySize64'],
        'qwen3_available_ram_bytes': system['FreePhysicalMemory'] * 1024,
        'qwen3_peak_working_set_bytes': None, 'qwen3_peak_system_commit_bytes': None,
        'qwen3_gpu_shared_bytes': None, 'qwen3_pagefile_activity': None, 'qwen3_disk_activity': None,
        'qwen3_system_usability': 'SYSTEM_PRESSURED',
        'classification_basis': 'Only about 559 MiB available after smoke; no direct window responsiveness test or sustained pagefile measurement.',
        'control_audit_sources': ['control_audit_telemetry.json', 'control_system_counters.json'],
        'control_data_must_not_be_attributed_to_qwen3': True}
    trace = read('control_audit_telemetry.json')['samples']
    telemetry['control_sampled_peak_commit_bytes'] = max(r['committed_bytes'] for r in trace)
    telemetry['control_sampled_min_available_bytes'] = min(r['available_physical_bytes'] for r in trace)
    save('telemetry.json', telemetry)
    comparison = {'schema': 'local2api.a2_s1.audited_comparison.v1',
        'canonical_14b_historical': {'LOCAL_SAFE': {'passed': 8, 'total': 9}, 'LOCAL_ACCEPTABLE': {'passed': 9, 'total': 11}, 'INTENDED_LOCAL': {'passed': 17, 'total': 20}},
        'canonical_14b_matched_cpu': summary(control['cases']), 'canonical_qwen3_cpu': summary(candidate['cases']),
        'manual_qwen3_mean': manual['candidate_mean'], 'manual_matched_14b_mean': manual['control_mean'],
        'failure_recovery': '1/3 historical failures; A04 only',
        'quality_verdict': 'INCREMENTAL_QUALITY_SMALL',
        'quality_scope': 'Small validation-wording improvement; generic short challenges do not establish a new capability tier.',
        'final_verdict': 'SPARSE_INCONCLUSIVE',
        'verdict_reason': 'Qwen3 Vulkan startup failed repeatedly; successful direct observations were CPU-only. No valid successful Vulkan execution/performance/control comparison exists. Candidate is not promoted, but a general hardware-tier rejection is not established.',
        'resource_penalty': {'gguf_ratio_vs_14b': 18556688704 / 8988110272, 'extra_weight_bytes': 18556688704 - 8988110272, 'qwen3_usability': 'SYSTEM_PRESSURED'},
        'separate_tier_qualified': False, 'dense_32b': 'BLOCKED',
        'invalid_old_ttft_ratios': 'WITHDRAWN: cache policy, backend and sampling differ',
        'audit_corrections': 'audit_corrections.md'}
    save('comparison_14b_vs_sparse.json', comparison)
    save('comparison_14b_vs_qwen3.json', {'status': 'SUPERSEDED', 'canonical': 'comparison_14b_vs_sparse.json', 'historical': 'comparison_pre_audit.json', 'reason': 'Old GPU labels, TTFT ratios and manual means were not adequately supported.'})
    qs, cs = summary(candidate['cases']), summary(control['cases'])
    challenge_q = challenge['qwen3_sparse_keyword_score']['passed']
    challenge_c = challenge['14b_control_keyword_score']['passed']
    report = f'''# A2.S1 — Qwen3-Coder-30B-A3B qualification, audited

Date: 2026-09-03. This report supersedes the conclusions in commit `a63a5ef`.

## Verdict and scope

**Final verdict: `SPARSE_INCONCLUSIVE`. Incremental short-task quality: `INCREMENTAL_QUALITY_SMALL`.**

Qwen3 scored 18/20 against the frozen A2.1 14B score of 17/20, recovering A04. It has not earned a separate local production tier. A reliable Qwen3 Vulkan inference path remains unqualified: primary Ollama attempts repeatedly failed startup allocation, and the successful CPuFriend runs were incorrectly labeled Vulkan in the earlier report. Backend discovery now shows no GPU device in that installation. Those successful measurements must be treated as CPU observations, subject to the retrospective assumption that the installation was unchanged.

The completed bounded experiment and audit do not prove Qwen3 is universally inferior to 14B. They do establish a real runtime blocker and insufficient evidence for promotion. Dense A2.2 32B remains **BLOCKED**. No router or Track B implementation was changed.

## Provenance and exact metadata

- Local file: `D:\\WORK\\RESEARCH\\local2api\\models\\qwen3-coder-30b-a3b-instruct-q4_k_m.gguf`
- SHA256: `AB4FC2B27B2043483A9E346C802809DFBE9B775EFBEEA7CA74DC2FD1AA4A0F71`
- File size: **18,556,688,704 bytes** (17.282 GiB); no model downloaded.
- Tensor sum: **30,532,122,624 parameters**, 579 tensors, architecture `qwen3moe`, Q4_K_M.
- 48 layers; hidden size 2048; 32 attention heads; 4 KV heads; **head dimension 128** from explicit key/value metadata. The old value 64 was incorrect.
- 128 experts, 8 selected/token, shared-expert FFN length 0; no shared-expert tensors in the inventory.
- Expert FFN dimension 768; general FFN metadata 5472; context metadata 262144; RoPE base 10000000.
- Tokenizer: GPT2/BPE, `qwen2` pretokenizer; full chat template and scalar tokenizer metadata retained in `model_metadata.json`.

Local tensor inventory yields 28,991,029,248 routed-bank parameters, 1,811,939,328 selected-expert parameters/token, and 1,541,093,376 nonexpert resident parameters. The conventional structural active footprint is **3,353,032,704 parameters** including the full input embedding table. Counting only one input embedding row gives 3,041,869,824; neither is a measured FLOP count or per-token transfer volume. All expert banks still occupy storage/residency space.

Source evidence: cloned llama.cpp revision `7798007a29a90e3053e799394da48cf53a2f8e0f`, `src/models/qwen3moe.cpp` (`load_arch_tensors` and `graph`). Actual header/tensor evidence is in [gguf_header_audit.json](evidence/a2_s1/gguf_header_audit.json).

## Memory model and observed pressure

| Context, one sequence | f16 KV payload | q4_0 KV payload | q8_0 KV payload |
|---|---:|---:|---:|
| 1K | 96 MiB | 27 MiB | 51 MiB |
| 4K | 384 MiB | 108 MiB | 204 MiB |
| 8K | 768 MiB | 216 MiB | 408 MiB |
| 16K | 1536 MiB | 432 MiB | 816 MiB |

Formula: context × 48 layers × 4 KV heads × 128 elements × K/V. q4_0 uses 18 bytes per 32 elements; q8_0 uses 34. Block layouts are confirmed in cloned `ggml/src/ggml-common.h`. These are payload estimates, excluding padding, runtime workspaces and additional slots. The matched control logs show four default slots with 4096 context per slot; original direct slot configuration was not captured beyond the command/smoke response.

Planning reserve: 6 GiB Windows plus 4 GiB editor/browser (budgets, not measured per-app use). At 16K/q4 KV, weights + KV + these reserves already require about 27.70 GiB before runtime buffers. The model fitting in a 32 GB file-size budget does not establish practical residency.

The durable Qwen3 post-smoke snapshot records WS **18,504,175,616 bytes**, private bytes **14,432,628,736**, and only **572,256 KiB** available physical RAM. Classification: **`SYSTEM_PRESSURED`**, based on this low headroom. Peak WS, peak system commit, GPU shared memory, sustained pagefile/disk activity and window responsiveness during Qwen3 inference were **not captured**. The audit's 14B counters cannot substitute for them. Do not add shared GPU memory to WS on UMA as though they were independent allocations.

## Runtime support and corrections

Primary isolated Ollama 0.33.2 recognized `qwen3moe`, expert metadata and Arc/Vulkan, but never produced a successful Qwen3 completion in these attempts. At 16K/q4 KV it failed allocating 452,984,832 bytes for KV. At 4K with 32 GPU layers and batch 32 it still failed a 169,149,056-byte compute allocation. These errors are preserved in `load_smoke*.json`. Repeated failed startup attempts ended primary-path testing.

The successful direct binary was CPuFriend build 10726 / `85c55223c`. Its audited `--list-devices` returns `(none)` and no Vulkan DLL is installed in that directory. Passing `-ngl 32` was not proof of GPU execution. Requested settings were 4K, batch32, ubatch16, q4_0 KV, flash attention on; effective execution is CPU. The audit does not attribute success to microbatch reduction alone because the build/backend also changed.

Read-only device discovery with the existing Ollama binary and its own `GGML_BACKEND_PATH=.../vulkan/ggml-vulkan.dll` lists Arc 140V. No model was loaded for that check. Thus **Arc discovery YES; successful Qwen3 Vulkan inference NO**. Output parity between successful Ollama/Vulkan and direct/Vulkan remains unavailable.

## Quality method and comparison

All 20 intended-local prompt strings and contains-all criteria are byte-for-byte the canonical suite: 9 LOCAL_SAFE and 11 LOCAL_ACCEPTABLE. CLOUD_REQUIRED cases are outside the requested denominator. The exploratory 96-token run is archived; authoritative Qwen3 outputs use 128 tokens, temperature0, top_p1, top_k40, seed42, canonical ChatML, and cache_prompt=false. Quality was non-streaming, so TTFT is null rather than inferred from prompt time.

Because runtime/KV/context differed from A2.1, the audit reran all 20 affected 14B cases with the same CPuFriend CPU method. Models were never loaded concurrently for this repair. Matching configuration does not reproduce identical OS cache or background load; quality is compared, latency is not.

| Quality metric | Frozen A2.1 14B | Matched CPU 14B audit | Qwen3 CPU |
|---|---:|---:|---:|
| LOCAL_SAFE | 8/9 | {cs['LOCAL_SAFE']['passed']}/9 | 9/9 |
| LOCAL_ACCEPTABLE | 9/11 | {cs['LOCAL_ACCEPTABLE']['passed']}/11 | 9/11 |
| Intended local | 17/20 | {cs['INTENDED_LOCAL']['passed']}/20 | 18/20 |
| Mean manual score, audited rubric | historical mean not compared | {manual['control_mean']:.2f} | {manual['candidate_mean']:.2f} |

Manual rubric remains 0 wrong/unusable; 1 substantial repair; 2 mostly correct/minor repair; 3 production acceptable. The old published 2.65/2.55 means were too lenient to incomplete outputs and are withdrawn as incremental-quality evidence. Both models are reviewed under the same rubric in [manual_review_audit.json](evidence/a2_s1/manual_review_audit.json).

Qwen3 completes the core B05 helper before truncating optional extras; 14B's helper ends before its return value. Both fail to deliver the actual early-return refactor in B03 under this cap. Several keyword passes stop before a useful test assertion. Qwen3's D03 reasonably requests an absent diff but does not provide the requested general summary. Sixteen Qwen3 answers reach the cap; incomplete code/examples require cleanup and are not advertised as production-ready. No protocol-malformed or repetitive failure was observed; technical imprecision is documented per case.

## 14B Failure Recovery Analysis

Full original 14B output, failure reason, Qwen3 output, same-method 14B output and manual deltas are retained per case in [failure_recovery_analysis.json](evidence/a2_s1/failure_recovery_analysis.json).

| Case | Frozen 14B miss | Qwen3 outcome | Audited manual delta | Capability interpretation |
|---|---|---|---:|---|
| A04 | Identifies the empty branch but omits validation criterion (`valid`) | PASS; explicitly says empty input is sent without validation | 2 → 2 | Clearer diagnosis within the same usability band |
| D01 | Generic public interface answer omits `backend` | FAIL; generic HTTP interface discussion | 2 → 2 | No recovered backend-contract criterion |
| D05 | Session loss/scaling explanation omits `state` and `context` | FAIL; similar session-memory risks | 2 → 2 | No demonstrated context-reconstruction uplift |

Recovered **1/3** historical failures. This supports a small wording/task-completion improvement, not a demonstrated multi-file reasoning tier.

## Challenge-only control repair

The same three predeclared generic challenges were used at a 96-token cap: upstream-status invariant, context ownership record, and terminal SSE marker. Original 14B HTTP500 attempts were infrastructure failures, not quality zeros. They are retained alongside the repaired CPU control.

Keyword scores: **14B {challenge_c}/3; Qwen3 {challenge_q}/3**. Manual assessment is recorded with each paired output. These short generic tasks do not contain a real 3–5-file repository, and cap truncation prevents a strong capability-ceiling claim. No challenge contributes to the canonical 20-case score.

## Performance and gate enforcement

| Qwen3 CPU observation | TTFT | Wall | Prompt tok/s | Decode tok/s | Runs |
|---|---:|---:|---:|---:|---:|
| 1K, 870 prompt tokens | 50.255 s | 60.526 s | 17.350 | 6.136 | 1 |
| 4K, 3573 prompt tokens | 333.053 s | 349.820 s | 10.728 | 3.758 | 1 |
| 8K | NOT COMPLETED | — | — | — | 0 |
| 16K | NOT COMPLETED | — | — | — | 0 |

These were loaded-model, uncached-prompt observations (`cache_n=0`), not cold-model TTFT. The 4K request exceeded the 300 s TTFT gate but the old harness failed to cancel it at that threshold. Larger direct runs were omitted afterwards. Cold-load TTFT, repeated cold/warm matrices and successful Qwen3 Vulkan throughput remain unmeasured. Optional CPU-MoE placement A/B was not run after repeated primary startup failure.

The old 14B Ollama measurements warmed up and repeated the same prompt without cache eviction; cached-token counts were not retained. CPU/Vulkan and build differences add further confounding. **The earlier 176x/697x TTFT ratios are withdrawn.** High apparent old prompt rates must not be called uncached prefill throughput.

## Primary comparison table

Historical latency columns below are context only and are not a controlled A/B with Qwen3.

| Metric | 7B historical | 14B dense | Qwen3 30B-A3B |
|---|---:|---:|---:|
| Total parameters | 7,615,616,512 | 14,770,033,664 | 30,532,122,624 |
| Active parameters/token | dense footprint, approx total | dense footprint, approx total | 3,353,032,704 structural convention |
| GGUF bytes | 4,683,074,048 | 8,988,110,272 | 18,556,688,704 |
| LOCAL_SAFE | 1/9 | 8/9 frozen | 9/9 |
| LOCAL_ACCEPTABLE | 2/11 | 9/11 frozen | 9/11 |
| Total intended local | 3/20 | 17/20 frozen | 18/20 |
| Audited mean manual score | not recorded | {manual['control_mean']:.2f}, CPU repair | {manual['candidate_mean']:.2f}, CPU |
| Challenge keyword score | N/A | {challenge_c}/3 | {challenge_q}/3 |
| TTFT 1K | 0.214 s warmed Ollama | 0.286 s warmed Ollama | 50.255 s uncached CPU |
| TTFT 4K | 0.322 s warmed Ollama | 0.478 s warmed Ollama | 333.053 s uncached CPU |
| TTFT 8K | 0.202 s warmed Ollama | 0.475 s warmed Ollama | not completed |
| TTFT 16K | 0.375 s warmed Ollama | 0.496 s warmed Ollama | not completed |
| Decode tok/s | 6.873–8.221 at 8K/16K | 2.753–3.949 historical | 3.758–6.136 CPU context samples |
| Peak system commit | not established here | 35.204 GB historical sampled | NOT PROVEN |
| System usability | no comparable classification | no UI qualification; audit counters retained | SYSTEM_PRESSURED, telemetry inference |
| Runtime complexity | established control | LOW relative to candidate | HIGH / unresolved GPU path |

7B file/header values were checked read-only against the original blob identified by `hw1_7b_prod_gate/input_parity.json`; no new 7B inference was run. Historical tables are from the frozen A2.1 comparison, not new performance measurements.

## Incremental value and next action

Quality/capability improvement is small on these bounded tasks. Weight storage increases by **9,568,578,432 bytes**, about **2.0646×** the 14B GGUF. Qwen3's successful CPU run leaves very little RAM, while the intended Vulkan path is unqualified. These facts prevent promotion; they do not establish a hardware-independent rejection or a valid numerical latency penalty over 14B.

No separate Qwen3 tier is qualified. Keep the existing 14B candidate pending its own production qualification. A2.S1's bounded run is COMPLETE with an inconclusive runtime verdict; a future experiment needs sufficient RAM headroom, explicit Arc device selection using a matching Vulkan DLL/build, captured offload logs, and cache-controlled cold/warm measurements. Dense 32B stays BLOCKED. Track B is unchanged.

## Reproducibility, evidence and QA

Required evidence files now include `model_metadata.json`, `runtime_config.json`, `quality_results.json`, `quality_outputs/`, `failure_recovery_analysis.json`, `challenge_14b_vs_qwen3.json`, `benchmark_runs.json`, `telemetry.json`, and `comparison_14b_vs_sparse.json`. Raw historical outputs and pre-audit interpretations remain separately named. See [audit_corrections.md](evidence/a2_s1/audit_corrections.md) for all corrections.

Audit scripts are `scripts/a2s1_artifact_audit.py` (local header/device audit), `scripts/a2s1_control_audit.py` (isolated 14B control), `scripts/a2s1_counter_sample.ps1` and `scripts/a2s1_finalize_audit.py`. These Windows audit scripts use the project Python 3.11+ venv and installed binaries; they never download a model or execute generated snippets.

Software QA: **15 tests passed** in the project venv; compileall and final JSON consistency validation passed (see `qa_validation.json`). These gates validate the gateway/artifacts, not model production quality.
'''
    with (ROOT / 'docs/result/result_a2_s1_qwen3_coder.md').open('w', encoding='utf-8', newline='\n') as f:
        f.write(report)
    print(json.dumps({'manual': {k: v for k, v in manual.items() if 'mean' in k}, 'comparison': comparison, 'challenge': {k: v for k, v in challenge.items() if 'score' in k}}, indent=2))


if __name__ == '__main__':
    main()
