#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
TAGS="lprice lprice50 lprice500 lsearch bfair lpricebf lsbf strict npit8 lsbfstrict"
while :; do
  done=1
  for t in $TAGS; do
    f="outputs/_diag/al_${t}_190/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R26 ALLOC (High) DONE ====="
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
pfo=W(load('pfosplit_190',FF)); base=W(load('pr_bothsbwf_190'))
print(f'R26 High 배분 레버 (감독자없음·예산켬)  PFO={pfo:.0f}  base(bothsbwf)={base:.0f} (+{base-pfo:.0f})')
rows=[]
for t in ['lprice','lprice50','lprice500','lsearch','bfair','lpricebf','lsbf','strict','npit8','lsbfstrict']:
    d=load(f'al_{t}_190')
    if d is None: continue
    tot=W(d); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
    ident=' [base와 동일]' if (base is not None and abs(tot-base)<0.5) else ''
    rows.append((tot-pfo,t,tot,fw,ur,ident))
for gap,t,tot,fw,ur,ident in sorted(rows):
    print(f'  {t:12}: {tot:7.0f} (fw {fw:6.0f}/ur {ur:6.0f})  vsPFO {gap:+7.0f}{\" WIN\" if gap<0 else \"\"}{ident}')
print()
print('  ※ [base와 동일] 표시가 뜨면 그 훅은 불발(선택 불변)')
"
