# w36(T=5220) 매트릭스 롤링 큐 — t36_jobs.txt를 최대 동시 N개로 순차 발주 (2026-07-20)
param([int]$MaxConc = 10)
Set-Location "C:\Users\alsrj\Desktop\Numerical-Sim-offiter"
$PY = "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$jobs = Get-Content "work\t36_jobs.txt" | Where-Object { $_ -and -not $_.StartsWith("#") }
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
  Start-Process -FilePath $PY -ArgumentList "work/run_claude_style_five_controller.py --scenario $scen --T-total 5220 --controllers $ctrl --output outputs/$outdir" -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput "outputs\_logs\$tag.log" -RedirectStandardError "outputs\_logs\$tag.err"
  foreach ($k in $envnames) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
  Add-Content "outputs\_logs\t36_queue.log" "[$(Get-Date -Format 'HH:mm:ss')] dispatch $i/$total $tag"
  Start-Sleep -Seconds 2
}
"T36 QUEUE DISPATCH COMPLETE $(Get-Date)" | Out-File "outputs\_logs\t36_dispatch_done.txt"
