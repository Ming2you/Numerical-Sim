#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
TAGS="f000 f010 f025 f040 f060 f075 f025wf020 f025wf030 f050wf020 f050wf030 u15 u30"
while :; do
  done=1
  for t in $TAGS; do
    f="outputs/_diag/F_${t}_190/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R34 DONE ====="
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
pfo=W(load('pfosplit_190',FF))
rows=[(W(load('al_bfair_190'))-pfo,'기준(farf1.0)',W(load('al_bfair_190'))),
      (W(load('L_farf05_190'))-pfo,'farf0.5',W(load('L_farf05_190')))]
for t in ['f000','f010','f025','f040','f060','f075','f025wf020','f025wf030','f050wf020','f050wf030','u15','u30']:
    d=load(f'F_{t}_190')
    if d is not None: rows.append((W(d)-pfo,t,W(d)))
print(f'R34 far-freeway 축  PFO={pfo:.2f}')
for gap,t,tot in sorted(rows):
    print(f'  {t:16}: {tot:9.2f}  vsPFO {gap:+8.2f}{\"  ★WIN\" if gap<0 else \"\"}')
b=min(rows); print(f'\n  최고: {b[1]} gap={b[0]:+.2f}' + ('  → ★High 돌파! 5/5' if b[0]<0 else '  → 계속'))
"
