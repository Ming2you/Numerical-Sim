# w36 타임라인(T=5220) walk-MVG 5런 발주 — 원래 flagship 플래그, 2026-07-20
Set-Location "C:\Users\alsrj\Desktop\Numerical-Sim-offiter"
$PY = "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
New-Item -ItemType Directory -Force "outputs\_t36" | Out-Null
$cells = @("155_w36", "170_w36", "170_skew15_w36", "170_incident_w36", "190_w36")
foreach ($c in $cells) {
  $rl = "outputs\_t36\wmvg_$c\P-STACK-WU-FAITHFUL-ALLPRICE-JOINT\run_log.csv"
  if (Test-Path $rl) { continue }
  $env:WARMUP_NC_STEPS = "5"; $env:FW_BUFFER = "8"; $env:TERM_ZG = "1"
  $env:BOX_WALK = "1"; $env:BOX_WALK_VG = "1"; $env:VSL_BOX = "10"; $env:METER_BOX = "300"
  $env:NP_PD_ITER = "4"; $env:NP_BIAS = "1"; $env:CROSS_OFF = "1"; $env:FAR_STATE_AWARE = "1"; $env:SEG13 = "1"
  Start-Process -FilePath $PY -ArgumentList "work/run_claude_style_five_controller.py --scenario sweet_$c --T-total 5220 --controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT --output outputs/_t36/wmvg_$c" -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput "outputs\_logs\t36_wm_$c.log" -RedirectStandardError "outputs\_logs\t36_wm_$c.err"
  foreach ($k in @("WARMUP_NC_STEPS","FW_BUFFER","TERM_ZG","BOX_WALK","BOX_WALK_VG","VSL_BOX","METER_BOX","NP_PD_ITER","NP_BIAS","CROSS_OFF","FAR_STATE_AWARE","SEG13")) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
  Write-Output "dispatched wmvg_$c"
}
