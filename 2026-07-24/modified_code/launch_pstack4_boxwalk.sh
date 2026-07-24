#!/usr/bin/env bash
# P-Stack(4) + LINK_BOX_WALK (leader 다중스텝 도달 fallback) × {no-sup, supF, supA} × 5셀 = 15런 (2026-07-24)
# b13 leader와 도달모델 정합시켜 granularity만 순수 격리. b13/PFO(4) 참조는 재실행 불필요(불변).
#   nosup → pstack4bw_<cell>      (leader+box-walk, 감독자 없음)
#   supF  → pstack4bwsupF_<cell>  (+ 감독자 fargate)
#   supA  → pstack4bwsupA_<cell>  (+ 감독자 always)
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)

# P-Stack(4) base + LINK_BOX_WALK=1. BLAS 캡 — 15 병렬 OMP=1 = 15 core
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 LINK_BOX_WALK=1 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1)

run_one() {  # $1=cell  $2=tag(nosup|supF|supA)
  local cell="$1" tag="$2" out extra=()
  case "$tag" in
    nosup) out="outputs/_diag/pstack4bw_${cell}" ;;
    supF)  out="outputs/_diag/pstack4bwsupF_${cell}"; extra=(SUP_PFO=1 SUP_GATE=fargate) ;;
    supA)  out="outputs/_diag/pstack4bwsupA_${cell}"; extra=(SUP_PFO=1) ;;
  esac
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "${extra[@]}" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$CTRL" --output "$out" \
      > "$out.log" 2>&1 &
}

for cell in 155 170 170skew 170inc 190; do
  run_one "$cell" nosup
  run_one "$cell" supF
  run_one "$cell" supA
done
wait
echo "===== PSTACK4 BOXWALK 15RUN DONE ====="
for tag in nosup supF supA; do for cell in 155 170 170skew 170inc 190; do
  case "$tag" in nosup) d="pstack4bw_${cell}";; supF) d="pstack4bwsupF_${cell}";; supA) d="pstack4bwsupA_${cell}";; esac
  out="outputs/_diag/$d"
  rows=$(wc -l < "$out/$CTRL/run_log.csv" 2>/dev/null)
  err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)
  echo "  ${tag} ${cell} rows=$rows err=$err"
done; done
