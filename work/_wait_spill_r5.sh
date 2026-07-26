#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in A_170 A_170inc A_190 B_170 B_170inc B_190; do
    f="outputs/_diag/spill_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== SPILLBACK R5 ALL DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct):
    p=f'outputs/_diag/{fp}/{ct}/run_log.csv'; return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors='coerce').to_numpy()) if (d is not None and k in d.columns) else None
def W(d,col):
    c=num(d,col); st=num(d,'step'); t=num(d,'time_sec')
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==4),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>14400: end=i-1; break
    return c[end]-c[bi]
print('R5 spillback — 성공기준 PFO 이김. 목표=freeway/urban 균형(P-CENT쪽).')
for cell,nm in [('170','Med'),('170inc','Inc'),('190','High')]:
    print(f'--- {nm}({cell}) ---')
    print(f'  {\"ctrl\":16}{\"total\":>8}{\"freeway\":>9}{\"urban\":>8}{\"urban%\":>7} | vsPFO')
    pfo=W(load(f'pfosplit_{cell}',FF),'cumulative_total_ttt')
    rows=[('PFO',f'pfosplit_{cell}',FF),('PS4base',f'pstack4_{cell}',PS),('PCENT',f'pcent_{cell}','P-CENT'),
          ('A urban-only',f'spill_A_{cell}',PS),('B symmetric',f'spill_B_{cell}',PS)]
    for lbl,fp,ct in rows:
        d=load(fp,ct)
        if d is None: print(f'  {lbl:16} 미완'); continue
        tot=W(d,'cumulative_total_ttt'); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
        vs=f'{tot-pfo:+.0f}' if (pfo and tot) else '-'
        mark=' ✓' if (pfo and tot and tot<pfo) else ''
        print(f'  {lbl:16}{tot:>8.0f}{fw:>9.0f}{ur:>8.0f}{100*ur/tot:>6.1f}% | {vs}{mark}')
"
