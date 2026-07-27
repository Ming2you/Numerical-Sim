#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for t in sbw2 sbw1 sbw4 sbwf05 sbn400 offp; do for c in 155 170skew; do
    f="outputs/_diag/T3_${t}_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done; done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R48 3v3 RETUNE DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct=PS):
    p=f'outputs/_diag/{fp}/{ct}/run_log.csv'; return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors='coerce').to_numpy()) if (d is not None and k in d.columns) else None
def W(d):
    if d is None: return None
    c=num(d,'cumulative_total_ttt'); st=num(d,'step'); t=num(d,'time_sec')
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==4),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>14400: end=i-1; break
    return c[end]-c[bi]
print('R48 — 3v3 재튜닝 (Low/Skew). 음수=PFO 이김')
for cell,nm,ref in [('155','Low',25.4),('170skew','Skew',12.0)]:
    pfo=W(load(f'pfosplit_{cell}',FF))
    print(f'--- {nm}  PFO={pfo:.1f}  (기존 튜닝 {ref:+.1f}) ---')
    rows=[]
    for t in ['sbw2','sbw1','sbw4','sbwf05','sbn400','offp']:
        d=load(f'T3_{t}_{cell}')
        if d is None: continue
        v=W(d); rows.append((v-pfo,t,v))
    for gap,t,v in sorted(rows):
        print(f'   {t:8}: {v:8.1f}  vsPFO {gap:+8.1f}{\"  ★WIN\" if gap<0 else \"\"}')
"
