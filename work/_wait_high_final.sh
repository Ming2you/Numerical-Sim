#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
T31="wu175 wu225 nref700 nref900 nref1000 lead040 lead060 gt4 gt8 gt12 pf8 pf16"
while :; do
  done=1
  for t in $T31; do
    f="outputs/_diag/T_${t}_190/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  for t in pf8 pf16 pf32 pf16bf; do
    f="outputs/_diag/pf_${t}_190/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== HIGH FINAL SWEEP DONE ====="
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
pfo=W(load('pfosplit_190',FF)); cur=W(load('al_bfair_190'))
print(f'High 마감 스윕  PFO={pfo:.2f}  현재최고={cur:.2f} ({cur-pfo:+.2f})')
rows=[]
for t in ['wu175','wu225','nref700','nref900','nref1000','lead040','lead060','gt4','gt8','gt12','pf8','pf16']:
    d=load(f'T_{t}_190')
    if d is not None: rows.append((W(d)-pfo,'T:'+t,W(d)))
for t in ['pf8','pf16','pf32','pf16bf']:
    d=load(f'pf_{t}_190')
    if d is not None: rows.append((W(d)-pfo,'pf:'+t,W(d)))
rows.append((cur-pfo,'현재최고(bfair)',cur))
for gap,t,tot in sorted(rows)[:10]:
    print(f'  {t:18}: {tot:8.2f}  vsPFO {gap:+8.2f}{\"  ★WIN\" if gap<0 else \"\"}')
best=min(rows)
print()
print(f'  최고: {best[1]} gap={best[0]:+.2f}' + ('  → High 돌파! 5/5 가능' if best[0]<0 else '  → 아직 미달'))
"
