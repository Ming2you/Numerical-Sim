set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
export WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111 \
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1 \
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1 \
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 MFD_FAR_W_FREEWAY=0.25 MFD_FAR_W_URBAN=1.0 \
  PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 MKL_NUM_THREADS=3
unset SEG13 METER_BOX VSL_BOX SUP_PFO SUP_GATE
OUT=outputs/_diag/farsplit_verify_170inc; mkdir -p "$OUT"
"$PY" -u work/run_claude_style_five_controller.py --scenario sweet_170_incident_w --T-total 14400 \
  --controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT --output "$OUT" > "$OUT.log" 2>&1
echo "VERIFY rc=$? rows=$(wc -l < "$OUT/P-STACK-WU-FAITHFUL-ALLPRICE-JOINT/run_log.csv" 2>/dev/null)"
