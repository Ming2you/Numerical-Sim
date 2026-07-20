# w60(Zhai식: 3600s 플래토 + 완전배수 cooldown) NC 프로브 6런 — 배수 실측용, 2026-07-20
Set-Location "C:\Users\alsrj\Desktop\Numerical-Sim-offiter"
$PY = "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
New-Item -ItemType Directory -Force "outputs\_w60" | Out-Null
$cells = @{ "155_w60" = 9900; "170_w60" = 9900; "170_skew15_w60" = 9900; "170_incident_w60" = 9900; "190_w60" = 9900; "220_w60" = 12600 }
foreach ($c in $cells.Keys) {
  $rl = "outputs\_w60\nc_$c\NO-CONTROL\run_log.csv"
  if (Test-Path $rl) { continue }
  $env:WARMUP_NC_STEPS = "5"; $env:FW_BUFFER = "8"; $env:TERM_ZG = "1"
  Start-Process -FilePath $PY -ArgumentList "work/run_claude_style_five_controller.py --scenario sweet_$c --T-total $($cells[$c]) --controllers NO-CONTROL --output outputs/_w60/nc_$c" -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput "outputs\_logs\w60_nc_$c.log" -RedirectStandardError "outputs\_logs\w60_nc_$c.err"
  Remove-Item Env:WARMUP_NC_STEPS, Env:FW_BUFFER, Env:TERM_ZG -ErrorAction SilentlyContinue
  Write-Output "dispatched nc_$c ($($cells[$c])s)"
}
