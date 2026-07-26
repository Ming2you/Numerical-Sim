#!/usr/bin/env bash
# Round 8 — spillback(urban보호) + far_fw 하향(freeway 희생 허용) 조합 (2026-07-25)
# 진단: spillback이 Inc +255 포화는 base freeway 비용이 freeway 희생을 막아서. camp_s10off가
# fw3584/ur1806(PFO식 freeway희생)로 Inc 이김(5390). far_fw는 gated(Inc/High만)라 Med/Skew 자동보존.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([170]=sweet_170_w [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
  SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run_one() { local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/combo_${combo}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# far_fw 하향 sweep on Inc(타깃) + High/Med 보존확인(f025)
for cell in 170inc; do run_one f05 "$cell" MFD_FAR_W_FREEWAY=0.5; done
for cell in 170inc 190 170; do run_one f025 "$cell" MFD_FAR_W_FREEWAY=0.25; done
for cell in 170inc; do run_one f00 "$cell" MFD_FAR_W_FREEWAY=0.0; done
wait
echo "===== COMBO R8 DONE ====="
for c in f05_170inc f025_170inc f025_190 f025_170 f00_170inc; do
  out="outputs/_diag/combo_${c}"
  echo "  ${c} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done
