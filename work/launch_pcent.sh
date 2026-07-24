set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
declare -A SC=([170]=sweet_170_w [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 NASH_SMAX=10
  PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=6 OPENBLAS_NUM_THREADS=6 MKL_NUM_THREADS=6)
for cell in 170inc 190 170; do
  out="outputs/_diag/pcent_${cell}"; mkdir -p "$out"
  env "${BASE_ENV[@]}" "$PY" -u work/run_claude_style_five_controller.py \
    --scenario "${SC[$cell]}" --T-total 14400 --controllers P-CENT --output "$out" \
    > "$out.log" 2>&1 &
done
wait
echo "===== P-CENT 3CELL DONE ====="
for cell in 170inc 190 170; do
  out="outputs/_diag/pcent_${cell}"
  echo "  ${cell} rows=$(wc -l < "$out/P-CENT/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done
