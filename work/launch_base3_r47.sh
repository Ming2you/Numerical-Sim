#!/usr/bin/env bash
# R47 — ★3 vs 3 기준선 확립 (리더도 3스텝 = LEADER_V_DEPTH=0)
#  A) fd0: FAR_D0=1 → 목적 = rollout_ttt(3) + far + spillback (depth3과 같은 채점 형태)
#  B) prx: FAR_D0 없음 → 목적 = follower 응답 proxy(legacy 경로)
# 둘 중 어느 채점 경로가 3스텝에서 나은지부터 확인. 감독자X · 예산O · 적응규칙X.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  LEADER_V_DEPTH=0)
run() { local tag="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/B3_${tag}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u AUTH_SMOOTH \
    -u BUDGET_OFF -u SPILLBACK -u METER_PRICE -u VSL_PRICE -u OFFSET_PRICE \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py --scenario "${SC[$cell]}" --T-total 14400 \
      --controllers "$PS" --output "$out" > "$out.log" 2>&1 & }
for cell in 155 170 170skew 170inc 190; do
  run fd0 "$cell" FAR_D0=1
  run prx "$cell"
done
wait
echo "===== R47 BASE-3STEP DONE ====="
