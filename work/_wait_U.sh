#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in 170 170skew 170inc 190; do
    f="outputs/_diag/U_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R32 UNIFORM DONE ====="
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
print('='*80)
print('R32 균일 파라미터 (적응규칙X, 감독자X, 예산O) — spillback WU2/WF1.0/nref800/lead0.5')
print('='*80)
print(f'{\"cell\":8}{\"PFO\":>9}{\"균일\":>10}{\"gap\":>9}')
w=0;n=0
for cell,nm,src in [('155','Low','lo_t6base_155'),('170','Med','U_170'),('170skew','Skew','U_170skew'),
                    ('170inc','Inc','U_170inc'),('190','High','U_190')]:
    pfo=W(load(f'pfosplit_{cell}',FF)); a=W(load(src))
    if a is None: print(f'{nm:8}{pfo:>9.0f}{\"미완\":>10}'); continue
    g=a-pfo; n+=1
    if g<0: w+=1
    print(f'{nm:8}{pfo:>9.1f}{a:>10.1f}{g:>+9.1f}{\"  WIN\" if g<0 else \"\"}')
print('-'*80)
print(f'  PFO {w}/{n} 승' + ('   ★★★5/5 — 균일 파라미터만으로 달성!' if w==5 and n==5 else ''))
"
