#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in f05_170inc f025_170inc f025_190 f025_170 f00_170inc; do
    f="outputs/_diag/combo_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R8 ALL DONE ====="
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
print('R8 spillback+far_fw하향 — Inc 이기나(freeway희생/urban보호) + High/Med 보존')
for cell,nm,combos in [('170inc','Inc',['f05','f025','f00']),('190','High',['f025']),('170','Med',['f025'])]:
    pfo=W(load(f'pfosplit_{cell}',FF),'cumulative_total_ttt')
    pc=W(load(f'pcent_{cell}','P-CENT'),'cumulative_total_ttt')
    base=W(load(f'pstack4_{cell}',PS),'cumulative_total_ttt')
    sp=W(load(f'spill_wu2_{cell}',PS),'cumulative_total_ttt') if cell in('170inc','190') else None
    extra=f' spill_wu2={sp:.0f}' if sp else ''
    print(f'--- {nm}({cell}) PFO={pfo:.0f} PCENT={pc if pc else 0:.0f} base={base:.0f}{extra} ---')
    for combo in combos:
        d=load(f'combo_{combo}_{cell}',PS)
        if d is None: continue
        tot=W(d,'cumulative_total_ttt'); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
        mark=' WIN' if (pfo and tot and tot<pfo) else ''
        print(f'  {combo}: {tot:.0f} (fw {fw:.0f}/ur {ur:.0f}) vsPFO {tot-pfo:+.0f}{mark}')
"
