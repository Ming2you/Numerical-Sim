#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in FW03_170inc FW03_190 FW00_170inc FW00_190; do
    f="outputs/_diag/probe_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== PROBE ALL DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct):
    p=f'outputs/_diag/{fp}/{ct}/run_log.csv'; return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors='coerce').to_numpy()) if (d is not None and k in d.columns) else None
def W(d,col):
    c=num(d,col); st=num(d,'step'); t=num(d,'time_sec')
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==4),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>14400: end=i-1; break
    return c[end]-c[bi]
print('probe: far_fw 가중 하향이 PS4를 PFO 방향(freeway 수용/urban 보호)으로 미는가')
print(f'{\"cell/ctrl\":22}{\"total\":>8}{\"freeway\":>9}{\"urban\":>8}{\"urban%\":>8}')
for cell in ['170inc','190']:
    refs=[('PFO(승)',f'pfosplit_{cell}',FF),('PS4base',f'pstack4_{cell}',PS),
          ('PCENT',f'pcent_{cell}','P-CENT'),
          ('FW03',f'probe_FW03_{cell}',PS),('FW00',f'probe_FW00_{cell}',PS)]
    print(f'--- {cell} ---')
    for nm,fp,ct in refs:
        d=load(fp,ct)
        if d is None: print(f'  {nm:20} 미완'); continue
        tot=W(d,'cumulative_total_ttt'); fw=W(d,'cumulative_freeway_ttt'); ur=W(d,'cumulative_urban_ttt')
        print(f'  {nm:20}{tot:>8.0f}{fw:>9.0f}{ur:>8.0f}{100*ur/tot:>7.1f}%')
"
