# 밤샘 full sweep 롤링 큐(2026-07-19) — paper3_jobs.txt를 최대 동시 N개로 순차 발주
param([int]$MaxConc = 10)
Set-Location "C:\Users\alsrj\Desktop\Numerical-Sim-offiter"
$PY = "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$jobs = Get-Content "work\paper3_jobs.txt" | Where-Object { $_ -and -not $_.StartsWith("#") }
$total = $jobs.Count; $i = 0
foreach ($job in $jobs) {
  $i += 1
  $parts = $job -split '\|'
  $envspec = $parts[0]; $scen = $parts[1]; $ctrl = $parts[2]; $outdir = $parts[3]; $tag = $parts[4]
  $rl = "outputs\" + ($outdir -replace '/','\') + "\$ctrl\run_log.csv"
  if (Test-Path $rl) { continue }
  while (@(Get-CimInstance Win32_Process -Filter "Name like 'py%'" | Where-Object { $_.CommandLine -like '*run_claude_style*' }).Count -ge $MaxConc) {
    Start-Sleep -Seconds 20
  }
  $envnames = @()
  foreach ($kv in ($envspec -split ';')) {
    if ($kv) { $k, $v = $kv -split '=', 2; Set-Item "Env:$k" $v; $envnames += $k }
  }
  Start-Process -FilePath $PY -ArgumentList "work/run_claude_style_five_controller.py --scenario $scen --T-total 10800 --controllers $ctrl --output outputs/$outdir" -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput "outputs\_logs\fs_$tag.log" -RedirectStandardError "outputs\_logs\fs_$tag.err"
  foreach ($k in $envnames) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
  Add-Content "outputs\_logs\paper3_queue.log" "[$(Get-Date -Format 'HH:mm:ss')] dispatch $i/$total $tag"
  Start-Sleep -Seconds 2
}
"QUEUE DISPATCH COMPLETE $(Get-Date)" | Out-File "outputs\_logs\paper3_dispatch_done.txt"
