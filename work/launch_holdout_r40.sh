#!/usr/bin/env bash
# R40 — ★일반화(hold-out) 시험: 튜닝에 쓰지 않은 6개 시나리오에서 재튜닝 없이 PFO를 이기나
# 사용자 지적: 3-분기 규칙이 분기=시나리오라 룩업테이블에 가깝다 → 견고성은 hold-out으로만 검증된다.
# 튜닝 셀(155/170/170skew/170inc/190)은 제외. 파라미터는 그대로 고정.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
FF=WU-FAITHFUL-FOLLOWER
CELLS=(sweet_140_w sweet_160_w sweet_200_w sweet_220_w sweet_155_incident_w sweet_155_skew15_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1)
CTRL_ENV=(SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
  AUTH_ADAPT=1 AUTH_DEM_LOW=22500 AUTH_DEM_HIGH=23900 AUTH_TRUST_BIG=6.0 AUTH_TRUST_SMALL=1.5)
for sc in "${CELLS[@]}"; do
  # PFO 기준선
  out="outputs/_diag/HO_pfo_${sc}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u SPILLBACK \
    "${BASE_ENV[@]}" \
    "$PY" -u work/run_claude_style_five_controller.py --scenario "$sc" --T-total 14400 \
      --controllers "$FF" --output "$out" > "$out.log" 2>&1 &
  # 최종 규칙(파라미터 고정, 재튜닝 없음)
  out2="outputs/_diag/HO_ps_${sc}"; mkdir -p "$out2"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u BUDGET_OFF \
    -u METER_PRICE -u VSL_PRICE -u OFFSET_PRICE -u SPILLBACK_WF -u MFD_FAR_W_FREEWAY \
    "${BASE_ENV[@]}" "${CTRL_ENV[@]}" \
    "$PY" -u work/run_claude_style_five_controller.py --scenario "$sc" --T-total 14400 \
      --controllers "$PS" --output "$out2" > "$out2.log" 2>&1 &
done
wait
echo "===== R40 HOLD-OUT DONE ====="
