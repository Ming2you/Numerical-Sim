#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
PAIRS="bfair:170inc bfair:190 bfair:170skew boff:170inc boff:190 boff:170skew bfairstrict:170inc bfairstrict:190"
while :; do
  done=1
  for p in $PAIRS; do
    t="${p%%:*}"; c="${p##*:}"
    f="outputs/_diag/bg_${t}_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R25 BUDGET COMPARISON DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct=PS):
    p=f'outputs/_diag/{fp}/{ct}/run_log.csv'; return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors='coerce').to_numpy()) if (d is not None and k in d.columns) else None
def W(d,col='cumulative_total_ttt'):
    if d is None: return None
    c=num(d,col); st=num(d,'step'); t=num(d,'time_sec')
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==4),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>14400: end=i-1; break
    return c[end]-c[bi]
print('='*88)
print('R25 — 예산 \"제거\" vs \"잘 배분\" (gap vs PFO, 음수=승)')
print('='*88)
print(f'{\"cell\":8}{\"PFO\":>8} | {\"현재(내최종)\":>13}{\"BUDGET_FAIR\":>13}{\"+strict\":>10}{\"BUDGET_OFF\":>12}')
for cell,nm in [('170skew','Skew'),('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF))
    cur=W(load(f'fin2_{cell}'))
    bf=W(load(f'bg_bfair_{cell}')); bs=W(load(f'bg_bfairstrict_{cell}')); bo=W(load(f'bg_boff_{cell}'))
    def g(v): return f'{v-pfo:+.0f}' if (v is not None and pfo is not None) else '--'
    print(f'{nm:8}{pfo:>8.0f} | {g(cur):>13}{g(bf):>13}{g(bs):>10}{g(bo):>12}')
print('-'*88)
print('  판정: BUDGET_FAIR가 BUDGET_OFF에 필적하면 → 예산은 무력한 게 아니라 배분이 편향됐던 것')
print('        (논문의 계층적 예산+가격 구조를 지키면서 이득 확보 가능)')
"
