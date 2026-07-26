#!/usr/bin/env bash
# Round 13 — ★공정 지평 심화(옵션 B): HORIZON을 세 컨트롤러에 동일 적용 (2026-07-25)
# 근거: H3(540s)엔 Inc 좋은결정/나쁜결정 구별정보가 물리적으로 없음(ΔN_UF +2700이 말단 uAcc +10veh).
#   → 목적함수 항/calibration으로 못 넘음(far_fw·nref 전부 bit-identical 실증).
# 공정성: HORIZON env는 cfg.mpc.horizon_steps 전역 설정 → PFO(WuFaithfulFollower)·P-Stack·P-CENT
#   모두 동일 지평. "리더만 깊게"(LEADER_V_DEPTH)와 달리 공정 비교 유지. leader_value_depth=0 불변.
# 핵심질문: 같은 만큼 깊어지면 계층이 분산보다 더 얻는가?
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
FF=WU-FAITHFUL-FOLLOWER
declare -A SC=([170]=sweet_170_w [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2)
SPILL_ENV=(SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)

run_ps() {  # $1=cell $2=H
  local cell="$1"; local H="$2"
  local out="outputs/_diag/fh_ps_H${H}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "${SPILL_ENV[@]}" HORIZON="$H" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
run_pfo() {  # $1=cell $2=H  (PFO는 leader 없음 — spillback 무관, 동일 HORIZON만)
  local cell="$1"; local H="$2"
  local out="outputs/_diag/fh_pfo_H${H}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" HORIZON="$H" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$FF" --output "$out" \
      > "$out.log" 2>&1 & }

# H=6 (1080s): 양쪽 동일 심화. Inc(핵심)·High·Med(보존).
for cell in 170inc 190 170; do run_ps "$cell" 6; run_pfo "$cell" 6; done
wait
echo "===== FAIR-HORIZON R13 (H6) DONE ====="
for cell in 170inc 190 170; do
  for k in ps pfo; do
    out="outputs/_diag/fh_${k}_H6_${cell}"
    c=$([ "$k" = ps ] && echo "$PS" || echo "$FF")
    echo "  ${k} H6 ${cell} rows=$(wc -l < "$out/$c/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
  done
done
