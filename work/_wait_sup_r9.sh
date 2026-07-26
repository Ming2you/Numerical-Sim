#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT; FF=WU-FAITHFUL-FOLLOWER
while :; do
  done=1
  for c in 155 170 170skew 170inc 190; do
    f="outputs/_diag/sup_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R9 ALL DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct):
    p=f'outputs/_diag/{fp}/{ct}/run_log.csv'; return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors='coerce').to_numpy()) if (d is not None and k in d.columns) else None
def W(d,col='cumulative_total_ttt'):
    c=num(d,col); st=num(d,'step'); t=num(d,'time_sec')
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==4),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>14400: end=i-1; break
    return c[end]-c[bi]
print('R9 spillback+SUP_PFO 전 5셀 — 성공기준 PFO 전부 이김')
print(f'{\"cell\":8}{\"PFO\":>8}{\"spill만\":>9}{\"+SUP\":>9}{\"PCENT\":>8} | vsPFO')
wins=0
for cell,nm in [('155','Low'),('170','Med'),('170skew','Skew'),('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF))
    sp=W(load(f'spill_wu2_{cell}',PS)) if cell in('170inc','190') else (W(load(f'spill_A_{cell}',PS)) if cell in('170',) else None)
    sup=W(load(f'sup_{cell}',PS))
    pc=W(load(f'pcent_{cell}','P-CENT'))
    def f(v): return f'{v:>8.0f}' if v is not None else f'{\"--\":>8}'
    vs=f'{sup-pfo:+.0f}' if (sup and pfo) else '-'
    mark=' WIN' if (sup and pfo and sup<pfo) else ''
    if sup and pfo and sup<pfo: wins+=1
    print(f'{nm:8}{f(pfo)}{f(sp):>9}{f(sup):>9}{f(pc)} | {vs}{mark}')
print(f'  === PFO {wins}/5 이김 ===' + ('  전부 이김!' if wins==5 else ''))
"
