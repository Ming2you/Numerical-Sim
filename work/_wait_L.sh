#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
TAGS="wf023 wf024 wf026 wf027 faru05 faru20 farf05 fg2 smax20 bias02 npb0 md095"
while :; do
  done=1
  for t in $TAGS; do
    f="outputs/_diag/L_${t}_190/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R33 LIVE-KNOB DONE ====="
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
print(f'R33 살아있는 노브  PFO={pfo:.2f}  현재최고={cur:.2f} ({cur-pfo:+.2f})')
rows=[(cur-pfo,'현재최고',cur)]
for t in ['wf023','wf024','wf026','wf027','faru05','faru20','farf05','fg2','smax20','bias02','npb0','md095']:
    d=load(f'L_{t}_190')
    if d is None: continue
    tot=W(d); ident='' if abs(tot-cur)>0.01 else ' [불변]'
    rows.append((tot-pfo,t+ident,tot))
for gap,t,tot in sorted(rows):
    print(f'  {t:16}: {tot:9.2f}  vsPFO {gap:+8.2f}{\"  ★WIN\" if gap<0 else \"\"}')
b=min(rows)
print(f'\n  최고: {b[1]} gap={b[0]:+.2f}' + ('  → High 돌파!' if b[0]<0 else ''))
"
