#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
TAGS="mtoff vsloff both gpoff mtd60 gt15"
while :; do
  done=1
  for t in $TAGS; do for cell in 170inc 190; do
    f="outputs/_diag/pr_${t}_${cell}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done; done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== PRICE SCREEN R14 ALL DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct):
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
print('R14 price channel screen — vs PFO (negative = WIN)')
for cell,nm in [('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF)); base=W(load(f'pstack4_{cell}',PS)); pc=W(load(f'pcent_{cell}','P-CENT'))
    print(f'--- {nm}({cell})  PFO={pfo:.0f}  base={base:.0f}  PCENT={pc if pc else 0:.0f} ---')
    rows=[]
    for t in ['mtoff','vsloff','both','gpoff','mtd60','gt15']:
        d=load(f'pr_{t}_{cell}',PS)
        if d is None: continue
        tot=W(d); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
        rows.append((tot-pfo,t,tot,fw,ur))
    for gap,t,tot,fw,ur in sorted(rows):
        mk=' WIN' if gap<0 else ''
        print(f'  {t:8}: {tot:7.0f} (fw {fw:6.0f}/ur {ur:6.0f})  vsPFO {gap:+7.0f}{mk}')
"
