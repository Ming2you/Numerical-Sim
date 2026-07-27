#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1; cnt=$(ls -d outputs/_diag/K_*_190 2>/dev/null | wc -l)
  [ "$cnt" -lt 12 ] && done=0
  for d in $(ls -d outputs/_diag/K_*_190 2>/dev/null); do
    n=$( [ -f "$d/$PS/run_log.csv" ] && wc -l < "$d/$PS/run_log.csv" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R36 DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,glob,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(p): return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors='coerce').to_numpy()) if (d is not None and k in d.columns) else None
def W(d,col='cumulative_total_ttt'):
    if d is None: return None
    c=num(d,col); st=num(d,'step'); t=num(d,'time_sec')
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==4),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>14400: end=i-1; break
    return c[end]-c[bi]
pfo=W(load(f'outputs/_diag/pfosplit_190/{FF}/run_log.csv'))
base=W(load(f'outputs/_diag/F_f050wf020_190/{PS}/run_log.csv'))
rows=[(base-pfo,'기준(+0.17)')]
for d in sorted(glob.glob('outputs/_diag/K_*_190')):
    t=os.path.basename(d)[2:-4]
    v=W(load(f'{d}/{PS}/run_log.csv'))
    if v is None: continue
    ident=' [불변]' if abs(v-base)<0.01 else ''
    rows.append((v-pfo,t+ident))
print(f'R36 미탐색 노브  PFO={pfo:.2f}')
for gap,t in sorted(rows):
    print(f'  {t:18}: vsPFO {gap:+9.2f}{\"  ★WIN\" if gap<0 else \"\"}')
b=min(rows); print(f'\n  최고: {b[1]} gap={b[0]:+.2f}' + ('  → ★★High 돌파!' if b[0]<0 else ''))
"
