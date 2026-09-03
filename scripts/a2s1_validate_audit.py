"""Validate A2.S1 deliverables, retaining executable QA evidence; no inference."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import sys

from hw1_quality import CASES
from hw1_prod_gate import render_chat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/result/evidence/a2_s1'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def validate():
    required = ['model_metadata.json', 'runtime_config.json', 'quality_results.json',
                'failure_recovery_analysis.json', 'challenge_14b_vs_qwen3.json',
                'benchmark_runs.json', 'telemetry.json', 'comparison_14b_vs_sparse.json']
    assert all((OUT / name).is_file() for name in required)
    paths = list((ROOT / 'docs/result/evidence').rglob('*.json'))
    for path in paths:
        json.loads(path.read_text(encoding='utf-8-sig'))
    expected = [(i, c, p, {'contains_all': n}) for i, c, p, n in CASES if c != 'CLOUD_REQUIRED']
    candidate = read('quality_results.json')
    raw = read('quality_results_128.json')
    control = read('control_14b_cpu_results.json')
    review = read('manual_review_audit.json')
    manual = read('manual_quality_review.json')
    comparison = read('comparison_14b_vs_sparse.json')
    assert review['status'] == 'complete'
    for label, result, key in [('candidate', candidate, 'canonical_qwen3_cpu'),
                                ('control', control, 'canonical_14b_matched_cpu')]:
        rows = result['cases']
        assert [(r['task_id'], r['class'], r['prompt'], r['criteria']) for r in rows] == expected
        assert all(r['status'] == 'ok' for r in rows)
        assert set(review[label]) == {r['task_id'] for r in rows}
        assert all(type(v['score']) is int and 0 <= v['score'] <= 3 and v['note']
                   for v in review[label].values())
        assert statistics.mean(r['score'] for r in review[label].values()) == manual[label + '_mean']
        for cls, summary in comparison[key].items():
            selected = [r for r in rows if cls == 'INTENDED_LOCAL' or r['class'] == cls]
            assert len(selected) == summary['total']
            assert sum(r['mechanical_pass'] for r in selected) == summary['passed']
        for row in rows:
            assert row['mechanical_pass'] == all(n.lower() in row['output'].lower()
                                                  for n in row['criteria']['contains_all'])
            assert row['ttft_ms'] is None
    for row, original in zip(candidate['cases'], raw['cases']):
        assert row['output'] == original['output']
        assert (OUT / 'quality_outputs' / (row['task_id'] + '.txt')).read_text(encoding='utf-8') == row['output']
        assert row['manual_score'] == review['candidate'][row['task_id']]['score']
        assert all(k in row for k in ['malformed', 'hallucination', 'repetition', 'truncation', 'wall_ms', 'output_tokens'])
    for row in control['cases'] + control['challenge_cases']:
        assert row['request']['prompt'] == render_chat(row['prompt'])
        assert row['request']['cache_prompt'] is False
        assert row['request']['n_predict'] == (96 if row['class'] == 'CHALLENGE_ONLY' else 128)
    challenge = read('challenge_14b_vs_qwen3.json')
    assert len(challenge['cases']) == 3
    for label in ['qwen3_sparse', '14b_control']:
        assert set(review['challenge'][label]) == {r['task_id'] for r in challenge['cases']}
        passed = 0
        for case in challenge['cases']:
            row = challenge['runs'][label][case['task_id']]
            assert row['status'] == 'ok'
            assert row['mechanical_pass'] == all(n.lower() in row['output'].lower() for n in case['criteria'])
            passed += row['mechanical_pass']
        assert challenge[label + '_keyword_score'] == {'passed': passed, 'total': 3}
    recovery = read('failure_recovery_analysis.json')
    assert [r['task_id'] for r in recovery['cases']] == ['A04', 'D01', 'D05']
    assert recovery['recovered'] == sum(r['qwen3_mechanical_pass'] for r in recovery['cases']) == 1
    meta, header = read('model_metadata.json'), read('gguf_header_audit.json')
    assert meta['gguf_sha256'].lower() == header['sha256']
    assert meta['head_dim'] == 128
    assert header['total_parameters'] == sum(t['parameters'] for t in header['tensors']) == 30532122624
    assert meta['active_parameters_per_token'] == 3353032704
    assert read('runtime_config.json')['qwen3_vulkan_inference_qualified'] is False
    perf = read('benchmark_runs.json')
    assert perf['levels']['4k']['gate']['cancellation_enforced'] is False
    assert all(perf['levels'][k]['status'] == 'NOT_COMPLETED' for k in ['8k', '16k'])
    assert read('telemetry.json')['qwen3_peak_system_commit_bytes'] is None
    assert comparison['final_verdict'] == 'SPARSE_INCONCLUSIVE'
    assert comparison['dense_32b'] == 'BLOCKED'
    assert 'after_cleanup' in read('control_audit_telemetry.json')
    tracked = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()
    assert not any(p.startswith(('models/', '.research/')) or p.lower().endswith('.gguf') for p in tracked)
    return {'json_files_validated': len(paths), 'canonical_cases_per_model': 20,
            'matched_challenges_per_model': 3, 'artifact_consistency': 'PASS'}


def main():
    result = {'utc': datetime.now(timezone.utc).isoformat(), 'python': sys.executable, 'commands': []}
    for args in [['-m', 'pytest', '-q'], ['-m', 'compileall', '-q', 'src', 'tests', 'scripts']]:
        command = [sys.executable, *args]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        result['commands'].append({'command': command, 'exit_code': run.returncode,
                                   'stdout': run.stdout, 'stderr': run.stderr})
    try:
        result['validation'] = validate()
    except Exception as exc:
        result['validation'] = {'status': 'FAIL', 'error': repr(exc)}
        raise
    finally:
        result['passed'] = (all(r['exit_code'] == 0 for r in result['commands']) and
                            result['validation'].get('artifact_consistency') == 'PASS')
        with (OUT / 'qa_validation.json').open('w', encoding='utf-8', newline='\n') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
