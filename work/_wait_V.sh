#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in 155 170 170skew 170inc; do
    f="outputs/_diag/V_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R37 UNIVERSAL DONE ====="
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
print('='*84)
print('R37 — 단일 설정(High 승리구성) 5셀 (감독자X · 예산O · 적응규칙X)')
print('='*84)
print(f'{\"cell\":8}{\"PFO\":>10}{\"단일설정\":>11}{\"gap\":>10}')
w=0;n=0
for cell,nm,src in [('155','Low','V_155'),('170','Med','V_170'),('170skew','Skew','V_170skew'),
                    ('170inc','Inc','V_170inc'),('190','High','K_offoff_190')]:
    pfo=W(load(f'pfosplit_{cell}',FF)); a=W(load(src))
    if a is None: print(f'{nm:8}{pfo:>10.1f}{\"미완\":>11}'); continue
    g=a-pfo; n+=1
    if g<0: w+=1
    print(f'{nm:8}{pfo:>10.1f}{a:>11.1f}{g:>+10.2f}{\"  WIN\" if g<0 else \"\"}')
print('-'*84)
print(f'  PFO {w}/{n} 승' + ('   ★★★5/5 단일설정 달성!' if w==5 and n==5 else ''))
"
