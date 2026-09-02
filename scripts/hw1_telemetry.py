from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


PS = r'''
$needle = $env:HW1_MATCH
$rows = Get-CimInstance Win32_Process | Where-Object { ($_.Name + ' ' + $_.CommandLine) -like "*$needle*" } | ForEach-Object {
  $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
  if ($p) {
    [pscustomobject]@{
      pid=$p.Id; name=$p.ProcessName; working_set=$p.WorkingSet64; private=$p.PrivateMemorySize64;
      paged=$p.PagedMemorySize64; page_faults=$p.PageFaults; cpu_s=$p.CPU;
      read_ops=$p.ReadOperationCount; write_ops=$p.WriteOperationCount
    }
  }
}
$commit=(Get-Counter '\Memory\Committed Bytes').CounterSamples[0].CookedValue
[pscustomobject]@{processes=@($rows); system_commit=$commit} | ConvertTo-Json -Depth 4 -Compress
'''


def snapshot(match: str) -> dict:
    env = dict(os.environ)
    env['HW1_MATCH'] = match
    out = subprocess.check_output(['powershell', '-NoProfile', '-Command', PS], text=True, timeout=15, env=env)
    return json.loads(out)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--match', required=True)
    p.add_argument('--duration', type=int, default=900)
    p.add_argument('--interval', type=float, default=2)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ['ts','pid','name','working_set_mb','private_mb','paged_mb','page_faults','cpu_s','read_ops','write_ops','system_commit_mb']
    with a.output.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        end = time.time() + a.duration
        while time.time() < end:
            try:
                s = snapshot(a.match)
            except Exception:
                time.sleep(a.interval)
                continue
            for pr in s.get('processes', []):
                w.writerow({
                    'ts': datetime.now(timezone.utc).isoformat(), 'pid': pr['pid'], 'name': pr['name'],
                    'working_set_mb': round((pr.get('working_set') or 0)/2**20, 2),
                    'private_mb': round((pr.get('private') or 0)/2**20, 2),
                    'paged_mb': round((pr.get('paged') or 0)/2**20, 2), 'page_faults': pr.get('page_faults'),
                    'cpu_s': pr.get('cpu_s'), 'read_ops': pr.get('read_ops'), 'write_ops': pr.get('write_ops'),
                    'system_commit_mb': round((s.get('system_commit') or 0)/2**20, 2),
                })
                f.flush()
            time.sleep(a.interval)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
