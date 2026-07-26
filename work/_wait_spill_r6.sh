#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in wu2_170inc wu2_190 wu3_170inc wu3_190 wu4_170inc wu4_190 wu4_170; do
    f="outputs/_diag/spill_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R6 ALL DONE ====="
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
print('R6 w_u sweep — PFO win? (freeway/urban balance)')
for cell,nm in [('170','Med'),('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF),'cumulative_total_ttt')
    pc=W(load(f'pcent_{cell}','P-CENT'),'cumulative_total_ttt')
    base=W(load(f'pstack4_{cell}',PS),'cumulative_total_ttt')
    print(f'--- {nm}({cell})  PFO={pfo:.0f} PCENT={pc if pc else 0:.0f} base={base:.0f} ---')
    for combo in ['wu2','wu3','wu4']:
        d=load(f'spill_{combo}_{cell}',PS)
        if d is None: continue
        tot=W(d,'cumulative_total_ttt'); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
        vs=f'{tot-pfo:+.0f}' if (pfo and tot) else '-'
        mark=' WIN' if (pfo and tot and tot<pfo) else ''
        print(f'  {combo}: {tot:.0f} (fw {fw:.0f}/ur {ur:.0f}) vsPFO {vs}{mark}')
"
