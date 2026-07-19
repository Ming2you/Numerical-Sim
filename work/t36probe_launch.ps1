# w36 타임라인 NC 프로브 5런 발주(T=6300, cooldown 배수 실측용) — 2026-07-20
Set-Location "C:\Users\alsrj\Desktop\Numerical-Sim-offiter"
$PY = "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
New-Item -ItemType Directory -Force "outputs\_t36probe" | Out-Null
New-Item -ItemType Directory -Force "outputs\_logs" | Out-Null
$cells = @("155_w36", "170_w36", "170_skew15_w36", "170_incident_w36", "190_w36")
foreach ($c in $cells) {
  $rl = "outputs\_t36probe\nc_$c\NO-CONTROL\run_log.csv"
  if (Test-Path $rl) { continue }
  $env:WARMUP_NC_STEPS = "5"; $env:FW_BUFFER = "8"; $env:TERM_ZG = "1"
  Start-Process -FilePath $PY -ArgumentList "work/run_claude_style_five_controller.py --scenario sweet_$c --T-total 6300 --controllers NO-CONTROL --output outputs/_t36probe/nc_$c" -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput "outputs\_logs\t36p_$c.log" -RedirectStandardError "outputs\_logs\t36p_$c.err"
  Remove-Item Env:WARMUP_NC_STEPS, Env:FW_BUFFER, Env:TERM_ZG -ErrorAction SilentlyContinue
  Write-Output "dispatched nc_$c"
}
