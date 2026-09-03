"""Repair the A2.S1 control gap with the existing local CPU runtime only.

Preserves historical candidate outputs; never downloads models or executes generated code.
Run from the repository root with the project venv.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from hw1_quality import CASES
from hw1_prod_gate import render_chat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/result/evidence/a2_s1'
EXE = Path('D:/WORK/RESEARCH/CPuFriend/bin/llama-server.exe')
MODEL = ROOT / 'models/qwen2.5-coder-14b-instruct-q4_k_m.gguf'
URL = 'http://127.0.0.1:11437'


def save(name, obj):
    with (OUT / name).open('w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')


class PerformanceInfo(ctypes.Structure):
    _fields_ = [('cb', w.DWORD)] + [(n, ctypes.c_size_t) for n in (
        'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal',
        'PhysicalAvailable', 'SystemCache', 'KernelTotal', 'KernelPaged',
        'KernelNonpaged', 'PageSize')] + [(n, w.DWORD) for n in (
        'HandleCount', 'ProcessCount', 'ThreadCount')]


class ProcessMemory(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('PageFaultCount', w.DWORD)] + [
        (n, ctypes.c_size_t) for n in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
        'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
        'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]


def snapshot(pid=None):
    perf = PerformanceInfo()
    perf.cb = ctypes.sizeof(perf)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    if not psapi.GetPerformanceInfo(ctypes.byref(perf), perf.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    row = {'utc': datetime.now(timezone.utc).isoformat(),
           'committed_bytes': perf.CommitTotal * perf.PageSize,
           'commit_limit_bytes': perf.CommitLimit * perf.PageSize,
           'available_physical_bytes': perf.PhysicalAvailable * perf.PageSize}
    if pid:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD]
        handle = kernel.OpenProcess(0x410, False, pid)
        if handle:
            try:
                mem = ProcessMemory()
                mem.cb = ctypes.sizeof(mem)
                if psapi.GetProcessMemoryInfo(handle, ctypes.byref(mem), mem.cb):
                    row.update(pid=pid, working_set_bytes=mem.WorkingSetSize,
                               private_bytes=mem.PrivateUsage,
                               page_fault_count=mem.PageFaultCount)
            finally:
                kernel.CloseHandle(handle)
    return row


def post(path, body, timeout=290):
    req = urllib.request.Request(URL + path, json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def infer(cid, cls, prompt, criteria, cap):
    payload = {'prompt': render_chat(prompt), 'stream': False, 'temperature': 0,
               'top_p': 1, 'top_k': 40, 'seed': 42, 'n_predict': cap,
               'cache_prompt': False}
    started = time.monotonic()
    row = {'task_id': cid, 'class': cls, 'prompt': prompt, 'criteria': criteria,
           'request': payload, 'ttft_ms': None,
           'ttft_note': 'Non-streaming matched historical Qwen3 quality method; not measured.'}
    try:
        data = post('/completion', payload)
        output = data.get('content', '')
        tim = data.get('timings', {})
        row.update(status='ok', output=output, raw_response=data,
                   mechanical_pass=all(x.lower() in output.lower() for x in criteria['contains_all']),
                   output_tokens=tim.get('predicted_n'),
                   truncation=data.get('stop_type') == 'limit',
                   wall_ms=round(1000 * (time.monotonic() - started), 3))
    except Exception as exc:
        row.update(status='error', error=repr(exc), mechanical_pass=None,
                   wall_ms=round(1000 * (time.monotonic() - started), 3))
        if isinstance(exc, urllib.error.HTTPError):
            row['error_body'] = exc.read().decode('utf-8', 'replace')
    print(cid, row['status'], row['mechanical_pass'], row['wall_ms'], flush=True)
    return row


def main():
    initial = snapshot()
    if initial['available_physical_bytes'] < 11 * 1024**3:
        raise RuntimeError('Insufficient baseline RAM for isolated 14B control audit')
    command = [str(EXE), '-m', str(MODEL), '--host', '127.0.0.1', '--port', '11437',
               '-c', '4096', '-ngl', '32', '-b', '32', '-ub', '16',
               '--cache-type-k', 'q4_0', '--cache-type-v', 'q4_0',
               '--flash-attn', 'on', '--no-webui', '--log-verbosity', '3']
    audit = {'created_at': initial['utc'], 'command': command,
             'exe_sha256': hashlib.file_digest(EXE.open('rb'), 'sha256').hexdigest(),
             'list_devices': subprocess.run([str(EXE), '--list-devices'], capture_output=True,
                 text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout,
             'effective_backend': 'CPU; no GPU devices available',
             'samples': [initial], 'note': 'PageFaultCount includes soft faults; not pagefile I/O.'}
    done = threading.Event()
    proc = None
    monitor = None
    try:
        with (OUT / 'control_cpu_runtime.txt').open('w', encoding='utf-8') as log:
            proc = subprocess.Popen(command, stdout=log, stderr=log,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        def sample():
            while not done.wait(5):
                audit['samples'].append(snapshot(proc.pid))
                save('control_audit_telemetry.json', audit)
        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
        started = time.monotonic()
        while True:
            if proc.poll() is not None or time.monotonic() - started > 120:
                raise RuntimeError('14B control startup failed/timeout')
            try:
                with urllib.request.urlopen(URL + '/health', timeout=2) as r:
                    if r.status == 200:
                        break
            except (OSError, urllib.error.HTTPError):
                time.sleep(1)
        audit['load_to_health_ms'] = 1000 * (time.monotonic() - started)
        with urllib.request.urlopen(URL + '/props', timeout=5) as r:
            audit['props'] = json.load(r)
        result = {'schema': 'local2api.a2_s1.control_cpu_audit.v1',
                  'method': 'Same direct CPU binary, context, KV, batch, template, sampler and cap as Qwen3.',
                  'command': command, 'cases': [], 'challenge_cases': []}
        tasks = [(cid, cls, p, {'contains_all': need}, 128, 'cases')
                 for cid, cls, p, need in CASES if cls != 'CLOUD_REQUIRED']
        challenge = json.loads((OUT / 'challenge_14b_vs_qwen3.json').read_text(encoding='utf-8-sig'))
        tasks += [(c['task_id'], 'CHALLENGE_ONLY', c['prompt'],
                   {'contains_all': c['criteria']}, 96, 'challenge_cases') for c in challenge['cases']]
        for cid, cls, prompt, criteria, cap, group in tasks:
            current = snapshot(proc.pid)
            if (current['available_physical_bytes'] < 512 * 1024**2 or
                    current['committed_bytes'] > .95 * current['commit_limit_bytes']):
                result['early_stop'] = current
                break
            row = infer(cid, cls, prompt, criteria, cap)
            result[group].append(row)
            save('control_14b_cpu_results.json', result)
            if row['status'] != 'ok' or row['wall_ms'] > 300000:
                result['early_stop'] = 'request failed or exceeded 300 seconds'
                break
        save('control_14b_cpu_results.json', result)
    finally:
        done.set()
        if monitor:
            monitor.join(timeout=10)
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=20)
        audit['after_cleanup'] = snapshot()
        save('control_audit_telemetry.json', audit)


if __name__ == '__main__':
    main()
