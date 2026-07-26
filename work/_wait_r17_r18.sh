#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
R17="wf010 wf015 wf035 wf050 wf025sup wf025n500 wf025n1k wf025wu15 wf025wu3 wf025gt3"
R18="155 170 170skew 170inc"
while :; do
  done=1
  for t in $R17; do
    f="outputs/_diag/pr_${t}_190/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  for c in $R18; do
    f="outputs/_diag/auth_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R17 + R18 ALL DONE ====="
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
pfo190=W(load('pfosplit_190',FF))
print('R17 High fine sweep (PFO=%.0f)'%pfo190)
rows=[]
for t in ['bothsbwf','wf010','wf015','wf035','wf050','wf025sup','wf025n500','wf025n1k','wf025wu15','wf025wu3','wf025gt3']:
    d=load(f'pr_{t}_190',PS)
    if d is None: continue
    tot=W(d); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
    rows.append((tot-pfo190,t,tot,fw,ur))
for gap,t,tot,fw,ur in sorted(rows):
    print(f'  {t:12}: {tot:7.0f} (fw {fw:6.0f}/ur {ur:6.0f})  vsPFO {gap:+7.0f}{\" WIN\" if gap<0 else \"\"}')
print()
print('R18 AUTH_ADAPT 단일규칙 (셀별 튜닝 아님)')
print(f'{\"cell\":8}{\"PFO\":>8}{\"AUTH\":>8}{\"gap\":>8}   셀별최고(참고)')
BEST={'155':-6,'170':-95,'170skew':-26,'170inc':-47}
wins=0
for cell,nm in [('155','Low'),('170','Med'),('170skew','Skew'),('170inc','Inc')]:
    pfo=W(load(f'pfosplit_{cell}',FF)); a=W(load(f'auth_{cell}',PS))
    if a is None: print(f'{nm:8}{pfo:>8.0f}{\"--\":>8}'); continue
    g=a-pfo
    if g<0: wins+=1
    print(f'{nm:8}{pfo:>8.0f}{a:>8.0f}{g:>+8.0f}   ({BEST[cell]:+d})' + ('  WIN' if g<0 else ''))
print(f'  AUTH_ADAPT 4셀 중 {wins} 승')
"
