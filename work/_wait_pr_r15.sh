#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
PAIRS="gt15mt:170inc gt15both:170inc gt10:170inc gt30:170inc gt15sb:170inc gt12both:190 gt12:190 bothsb:190 gt24both:190 gt15:155 gt15:170 gt15:170skew"
while :; do
  done=1
  for p in $PAIRS; do
    t="${p%%:*}"; c="${p##*:}"
    f="outputs/_diag/pr_${t}_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R15 ALL DONE ====="
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
CAND={'170inc':['gt15','gt15mt','gt15both','gt10','gt30','gt15sb','both','mtd60'],
      '190':['both','gt12both','gt12','bothsb','gt24both','mtoff'],
      '155':['gt15'],'170':['gt15'],'170skew':['gt15']}
print('R15 — vs PFO (negative = WIN)')
for cell,nm in [('155','Low'),('170','Med'),('170skew','Skew'),('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF)); base=W(load(f'pstack4_{cell}',PS)); pc=W(load(f'pcent_{cell}','P-CENT'))
    print(f'--- {nm}({cell})  PFO={pfo:.0f}  base={base:.0f}  PCENT={pc if pc else 0:.0f} ---')
    rows=[]
    for t in CAND.get(cell,[]):
        d=load(f'pr_{t}_{cell}',PS)
        if d is None: continue
        tot=W(d); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
        rows.append((tot-pfo,t,tot,fw,ur))
    for gap,t,tot,fw,ur in sorted(rows):
        mk=' WIN' if gap<0 else ''
        print(f'  {t:10}: {tot:7.0f} (fw {fw:6.0f}/ur {ur:6.0f})  vsPFO {gap:+7.0f}{mk}')
"
