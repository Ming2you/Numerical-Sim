#!/usr/bin/env bash
# R30 — ★노선 A: 가격을 켠 채 **가격이 링크 예산을 배분** (사용자 선택)
# 가설: 지금까지 High에서 metering 가격을 꺼야 했던 이유는 가격이 나빠서가 아니라
#   배분 권한이 없어서(ω_F가 density 휴리스틱으로 선점) 가격이 과보호만 유발했기 때문.
#   배분을 가격이 하면(ω_l ∝ exp(−β·p̄_l)) 가격을 켠 채로도(또는 켜야) 좋아져야 한다.
# 조건: 감독자 없음 · 예산 켬.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5 BUDGET_FAIR=1)
run() { local tag="$1"; shift
  local out="outputs/_diag/A_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF -u METER_PRICE \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# metering 가격 ON + 가격기반 배분. β 스윕(가격 스케일 0.001~0.01 → β가 지수 감도)
run b200   VSL_PRICE=0 LINK_SHARE=price SPILLBACK_WF=0.25
run b50    VSL_PRICE=0 LINK_SHARE=price LINK_SHARE_BETA=50   SPILLBACK_WF=0.25
run b1000  VSL_PRICE=0 LINK_SHARE=price LINK_SHARE_BETA=1000 SPILLBACK_WF=0.25
run b3000  VSL_PRICE=0 LINK_SHARE=price LINK_SHARE_BETA=3000 SPILLBACK_WF=0.25
# 전 가격 ON(VSL까지) + 가격배분
run allp   LINK_SHARE=price SPILLBACK_WF=0.25
# 가격배분이면 spillback freeway가중 불필요할 수도
run b200wf0 VSL_PRICE=0 LINK_SHARE=price SPILLBACK_WF=0
# 대조군: 가격 ON + density 배분(기존) — 가격배분의 순효과 격리
run ctrl_density VSL_PRICE=0 SPILLBACK_WF=0.25
wait
echo "===== R30 (노선 A) DONE ====="
