# 고강도(220/240/280) NC 프로브 발주 — w36형(T=9000, 배수 실측) + 10800형(공식 기저선), 2026-07-20
Set-Location "C:\Users\alsrj\Desktop\Numerical-Sim-offiter"
$PY = "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
New-Item -ItemType Directory -Force "outputs\_hv" | Out-Null
foreach ($s in @("220", "240", "280")) {
  # w36형 프로브 (T=9000 = 50스텝, 쿨다운 관측 5580s)
  $rl = "outputs\_hv\ncw36_$s\NO-CONTROL\run_log.csv"
  if (-not (Test-Path $rl)) {
    $env:WARMUP_NC_STEPS = "5"; $env:FW_BUFFER = "8"; $env:TERM_ZG = "1"
    Start-Process -FilePath $PY -ArgumentList "work/run_claude_style_five_controller.py --scenario sweet_${s}_w36 --T-total 9000 --controllers NO-CONTROL --output outputs/_hv/ncw36_$s" -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput "outputs\_logs\hv_ncw36_$s.log" -RedirectStandardError "outputs\_logs\hv_ncw36_$s.err"
    Remove-Item Env:WARMUP_NC_STEPS, Env:FW_BUFFER, Env:TERM_ZG -ErrorAction SilentlyContinue
    Write-Output "dispatched ncw36_$s"
  }
  # 10800형 공식 NC
  $rl2 = "outputs\_hv\nc10800_$s\NO-CONTROL\run_log.csv"
  if (-not (Test-Path $rl2)) {
    $env:WARMUP_NC_STEPS = "20"; $env:FW_BUFFER = "8"; $env:TERM_ZG = "1"
    Start-Process -FilePath $PY -ArgumentList "work/run_claude_style_five_controller.py --scenario sweet_${s}_w --T-total 10800 --controllers NO-CONTROL --output outputs/_hv/nc10800_$s" -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput "outputs\_logs\hv_nc10800_$s.log" -RedirectStandardError "outputs\_logs\hv_nc10800_$s.err"
    Remove-Item Env:WARMUP_NC_STEPS, Env:FW_BUFFER, Env:TERM_ZG -ErrorAction SilentlyContinue
    Write-Output "dispatched nc10800_$s"
  }
}
