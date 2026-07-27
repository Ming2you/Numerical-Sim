#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
TAGS="b200 b50 b1000 b3000 allp b200wf0 ctrl_density"
while :; do
  done=1
  for t in $TAGS; do
    f="outputs/_diag/A_${t}_190/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R30 (노선 A) DONE ====="
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
ref=W(load('al_bfair_190'))   # 가격 OFF + BUDGET_FAIR = +0.57 (현재 최고)
print(f'R30 노선A: 가격 ON + 가격기반 배분   PFO={pfo:.2f}   현재최고(가격off+bfair)={ref:.2f} ({ref-pfo:+.2f})')
print(f'{\"cand\":14}{\"TTT\":>9}{\"fw\":>8}{\"urban\":>8}{\"vsPFO\":>9}  가격컬럼')
rows=[]
for t in ['b200','b50','b1000','b3000','allp','b200wf0','ctrl_density']:
    d=load(f'A_{t}_190')
    if d is None: continue
    tot=W(d); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
    npx=len([c for c in d.columns if 'meter_price' in c])
    rows.append((tot-pfo,t,tot,fw,ur,npx))
for gap,t,tot,fw,ur,npx in sorted(rows):
    print(f'  {t:12}{tot:>9.1f}{fw:>8.0f}{ur:>8.0f}{gap:>+9.1f}{\" WIN\" if gap<0 else \"\"}   {npx}개')
print()
print('  핵심비교: b*(가격배분) vs ctrl_density(가격ON+기존배분) → 배분방식의 순효과')
"
