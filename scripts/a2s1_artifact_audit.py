"""Read the local GGUF header and audit installed backend discovery; no inference."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/result/evidence/a2_s1'


def save(name, obj):
    with (OUT / name).open('w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def header(path):
    formats = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'f',
               7: '?', 10: 'Q', 11: 'q', 12: 'd'}
    with path.open('rb') as f:
        def number(fmt):
            return struct.unpack('<' + fmt, f.read(struct.calcsize('<' + fmt)))[0]
        def string(skip=False):
            size = number('Q')
            if skip:
                f.seek(size, 1)
                return None
            return f.read(size).decode('utf-8')
        def value(kind, skip=False):
            if kind == 8:
                return string(skip)
            if kind == 9:
                item_type, count = number('I'), number('Q')
                if item_type in formats:
                    f.seek(count * struct.calcsize('<' + formats[item_type]), 1)
                else:
                    for _ in range(count):
                        value(item_type, True)
                return {'omitted_array_elements': count, 'element_type': item_type}
            return number(formats[kind])
        assert f.read(4) == b'GGUF'
        version, tensors_n, metadata_n = number('I'), number('Q'), number('Q')
        assert version == 3
        metadata = {}
        for _ in range(metadata_n):
            key = string()
            metadata[key] = value(number('I'))
        tensors = []
        for _ in range(tensors_n):
            name, dims_n = string(), number('I')
            dims = [number('Q') for _ in range(dims_n)]
            tensors.append({'name': name, 'shape': dims, 'type': number('I'),
                            'offset': number('Q'), 'parameters': math.prod(dims)})
        return metadata, tensors, f.tell()


def main():
    model = ROOT / 'models/qwen3-coder-30b-a3b-instruct-q4_k_m.gguf'
    meta, tensors, header_end = header(model)
    expert = [t for t in tensors if '_exps.weight' in t['name']]
    assert len(expert) == 48 * 3
    assert all(t['shape'][-1] == 128 for t in expert)
    total = sum(t['parameters'] for t in tensors)
    expert_total = sum(t['parameters'] for t in expert)
    routed = expert_total // 128 * 8
    nonexpert = total - expert_total
    embedding = next(t['parameters'] for t in tensors if t['name'] == 'token_embd.weight')
    with model.open('rb') as f:
        sha = hashlib.file_digest(f, 'sha256').hexdigest()
    save('gguf_header_audit.json', {
        'utc': datetime.now(timezone.utc).isoformat(), 'path': str(model),
        'file_size_bytes': model.stat().st_size, 'sha256': sha,
        'header_end': header_end, 'metadata': meta, 'tensors': tensors,
        'total_parameters': total, 'all_expert_parameters': expert_total,
        'selected_expert_parameters_per_token': routed,
        'nonexpert_parameters_resident': nonexpert,
        'structural_active_parameters_including_embedding_table': nonexpert + routed,
        'embedding_table_parameters': embedding,
        'touched_parameter_estimate_one_embedding_row': nonexpert + routed - embedding + 2048,
        'active_count_note': 'Structural count derived from real tensor dimensions and 8/128 routing. Full embedding table is counted in the conventional nonexpert footprint, but an input token looks up one row. Neither count is a measured FLOP count or weight-I/O volume.',
        'source_revision': '7798007a29a90e3053e799394da48cf53a2f8e0f',
        'source_paths': ['src/models/qwen3moe.cpp:load_arch_tensors', 'src/models/qwen3moe.cpp:graph']})
    cpu = Path('D:/WORK/RESEARCH/CPuFriend/bin/llama-server.exe')
    ollama = Path(os.environ['LOCALAPPDATA']) / 'Programs/Ollama/lib/ollama/llama-server.exe'
    vk = ollama.parent / 'vulkan/ggml-vulkan.dll'
    env = os.environ.copy()
    env['GGML_BACKEND_PATH'] = str(vk)
    rows = []
    for exe, flag, settings in [(cpu, '--version', None), (cpu, '--list-devices', None),
                                (ollama, '--list-devices', None), (ollama, '--list-devices', env)]:
        r = subprocess.run([str(exe), flag], capture_output=True, text=True,
                           env=settings, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
        with exe.open('rb') as f:
            exe_sha = hashlib.file_digest(f, 'sha256').hexdigest()
        rows.append({'command': [str(exe), flag], 'exe_sha256': exe_sha,
                     'GGML_BACKEND_PATH': settings.get('GGML_BACKEND_PATH') if settings else os.getenv('GGML_BACKEND_PATH'),
                     'stdout': r.stdout, 'stderr': r.stderr, 'exit_code': r.returncode})
    save('backend_discovery_audit.json', {'utc': datetime.now(timezone.utc).isoformat(),
         'checks': rows, 'cpu_directory_dlls': [p.name for p in cpu.parent.glob('*.dll')],
         'vulkan_dll_path': str(vk), 'conclusion': 'CPuFriend direct measurements are CPU-only under the captured environment. Explicit Ollama backend DLL discovery recognizes Arc, but this check performs no inference.'})
    # K and V each have 4 heads * 128 dimensions across 48 layers.
    levels = {}
    for context in [1024, 4096, 8192, 16384]:
        elements = context * 48 * 4 * 128 * 2
        levels[str(context)] = {'f16_bytes': elements * 2,
                                'q4_0_bytes': elements // 32 * 18,
                                'q8_0_bytes': elements // 32 * 34}
    save('memory_model.json', {'source': 'gguf_header_audit.json',
         'weights_bytes': model.stat().st_size, 'kv_payload_by_context': levels,
         'kv_formula': 'context * 48 layers * 4 KV heads * 128 head dimension * (K+V); f16=2 bytes, q4_0=18 bytes/32 elements, q8_0=34/32',
         'kv_limits': 'Payload only, one sequence; allocation padding, multiple slots and runtime buffers add overhead.',
         'windows_reserve_budget_bytes': 6 * 1024**3,
         'editor_browser_reserve_budget_bytes': 4 * 1024**3,
         'reserve_note': 'Planning budgets, not measured per-app consumption. Do not sum GPU shared memory and process WS as independent physical allocations on UMA.',
         'runtime_buffers_measured_bytes': None,
         'runtime_buffer_evidence': 'Ollama allocation errors record failed KV/compute requests, not a successful complete allocation.',
         'resident_practical_verdict': 'Not established; historical direct CPU smoke left only 572256 KiB physical memory available.',
         'gpu_shared_allocation_bytes': None,
         'sustained_paging_proven': False})
    print('HEADER', total, 'ACTIVE_STRUCTURAL', nonexpert + routed, 'SHA', sha, flush=True)


if __name__ == '__main__':
    main()
