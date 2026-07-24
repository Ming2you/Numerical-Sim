#!/usr/bin/env bash
# TTT-only(far/terminal cost OFF) 확인용 — unset FAR_GATE + MFD_FAR=0 (2026-07-24)
# PS4 / PS4(supF) / PFO(4) 각 5셀. leader V = 순수 rollout TTT, 링크 follower TC도 제거.
# 주의: far off면 SUP_GATE=fargate가 절대 안 걸려 supF ≡ 감독자 always-on.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT; FF=WU-FAITHFUL-FOLLOWER
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)

# base = P-Stack(4)에서 FAR_GATE 제거 + MFD_FAR=0. (BOX_WALK류는 far와 무관, inert면 유지)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 MFD_FAR=0 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1)

run_one() {  # $1=cell $2=tag(ps4|supF|pfo)
  local cell="$1" tag="$2" out ctrl extra=()
  case "$tag" in
    ps4)  out="outputs/_diag/pstack4faroff_${cell}";     ctrl=$PS ;;
    supF) out="outputs/_diag/pstack4faroffsupF_${cell}"; ctrl=$PS; extra=(SUP_PFO=1 SUP_GATE=fargate) ;;
    pfo)  out="outputs/_diag/pfofaroff_${cell}";          ctrl=$FF ;;
  esac
  mkdir -p "$out"
  env -u FAR_GATE -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "${extra[@]}" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$ctrl" --output "$out" \
      > "$out.log" 2>&1 &
}
for cell in 155 170 170skew 170inc 190; do
  run_one "$cell" ps4
  run_one "$cell" supF
  run_one "$cell" pfo
done
wait
echo "===== FAROFF TTT-ONLY DONE ====="
for tag in ps4 supF pfo; do for cell in 155 170 170skew 170inc 190; do
  case "$tag" in ps4) d="pstack4faroff_${cell}"; ctrl=$PS;; supF) d="pstack4faroffsupF_${cell}"; ctrl=$PS;; pfo) d="pfofaroff_${cell}"; ctrl=$FF;; esac
  out="outputs/_diag/$d"
  echo "  ${tag} ${cell} rows=$(wc -l < "$out/$ctrl/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done; done
