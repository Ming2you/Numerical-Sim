#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in n400_170inc n500_170inc n600_170inc n400_190 n500_190; do
    f="outputs/_diag/nref_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R11 ALL DONE ====="
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
print('R11 nref_u calibration — 승자 운영점(uAcc 400대) 조준')
for cell,nm,combos in [('170inc','Inc',['n400','n500','n600']),('190','High',['n400','n500'])]:
    pfo=W(load(f'pfosplit_{cell}',FF)); pc=W(load(f'pcent_{cell}','P-CENT'))
    sp=W(load(f'spill_wu2_{cell}',PS))
    print(f'--- {nm}({cell}) PFO={pfo:.0f} PCENT={pc if pc else 0:.0f} spill(nref800)={sp:.0f} ---')
    for combo in combos:
        d=load(f'nref_{combo}_{cell}',PS)
        if d is None: continue
        tot=W(d); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
        ua=num(d,'urban_accumulation_veh'); st=num(d,'step')
        idx=[i for i in range(len(st)) if 35<=int(st[i])<=50]
        uapk=ua[idx].max() if len(idx) else float('nan')
        mark=' WIN' if (pfo and tot and tot<pfo) else ''
        print(f'  {combo}: {tot:.0f} (fw {fw:.0f}/ur {ur:.0f}) vsPFO {tot-pfo:+.0f}{mark}  uAcc_peak(35-50)={uapk:.0f}')
print()
print('참고 uAcc_peak: PFO~427 camp~457 (승자) / base~921 spill~860 (패자)')
"
