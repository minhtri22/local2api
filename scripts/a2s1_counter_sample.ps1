$ErrorActionPreference = 'Stop'
$samples = Get-Counter '\Memory\Committed Bytes','\Memory\Commit Limit','\Memory\Available MBytes','\Memory\Pages Input/sec','\Memory\Pages Output/sec','\PhysicalDisk(_Total)\Disk Read Bytes/sec','\PhysicalDisk(_Total)\Disk Write Bytes/sec','\GPU Adapter Memory(*)\Shared Usage','\Paging File(_Total)\% Usage' -SampleInterval 2 -MaxSamples 3
$result = [ordered]@{
    phase = '14B CPU control audit; Qwen3 is not loaded'
    note = 'System-wide samples; GPU counters include desktop applications. Page input/output can include mapped files and are not exclusive pagefile I/O.'
    samples = @($samples | ForEach-Object {
        [ordered]@{
            timestamp = $_.Timestamp.ToUniversalTime().ToString('o')
            counters = @($_.CounterSamples | Select-Object Path,CookedValue,Status)
        }
    })
}
$target = Join-Path $PSScriptRoot '../docs/result/evidence/a2_s1/control_system_counters.json'
$json = $result | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText([IO.Path]::GetFullPath($target), $json, [Text.UTF8Encoding]::new($false))
