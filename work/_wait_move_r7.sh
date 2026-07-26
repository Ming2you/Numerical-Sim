#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in m05_170inc m05_190 m10_170inc m10_190 m10_170 m20_170inc; do
    f="outputs/_diag/move_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R7 ALL DONE ====="
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
def vol(d):
    mf=num(d,'total_metering_flow'); st=num(d,'step')
    idx=[i for i in range(len(st)) if 20<=int(st[i])<=50]
    return np.abs(np.diff(mf[idx])).mean()
print('R7 spillback+move — PFO 이기나 + metering 평활(|Δ|, 오라클 Inc~300)')
for cell,nm,combos in [('170inc','Inc',['m05','m10','m20']),('190','High',['m05','m10']),('170','Med',['m10'])]:
    pfo=W(load(f'pfosplit_{cell}',FF),'cumulative_total_ttt')
    pc=W(load(f'pcent_{cell}','P-CENT'),'cumulative_total_ttt')
    base=W(load(f'pstack4_{cell}',PS),'cumulative_total_ttt')
    print(f'--- {nm}({cell}) PFO={pfo:.0f} PCENT={pc if pc else 0:.0f} base={base:.0f} ---')
    for combo in combos:
        d=load(f'move_{combo}_{cell}',PS)
        if d is None: continue
        tot=W(d,'cumulative_total_ttt'); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt'); v=vol(d)
        mark=' WIN' if (pfo and tot and tot<pfo) else ''
        print(f'  {combo}: {tot:.0f} (fw {fw:.0f}/ur {ur:.0f}) vsPFO {tot-pfo:+.0f}{mark}  metering|Δ|={v:.0f}')
"
