#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for cell in 170inc 190 170; do
    f="outputs/_diag/fh_psbase_H6_${cell}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== CONTROL (base@H6, no spillback) DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct):
    p=f'outputs/_diag/{fp}/{ct}/run_log.csv'; return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors='coerce').to_numpy()) if (d is not None and k in d.columns) else None
def W(d):
    if d is None: return None
    c=num(d,'cumulative_total_ttt'); st=num(d,'step'); t=num(d,'time_sec')
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==4),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>14400: end=i-1; break
    return c[end]-c[bi]
print('CONTROL: is P-Stack depth degradation caused by spillback miscalibration, or by depth itself?')
print(f'{\"cell\":7}{\"base@H3\":>10}{\"base@H6\":>10}{\"gain\":>8} | {\"spill@H3\":>10}{\"spill@H6\":>10}{\"gain\":>8} | {\"PFO@H6\":>9}')
for cell,nm in [('170','Med'),('170inc','Inc'),('190','High')]:
    b3=W(load(f'pstack4_{cell}',PS)); b6=W(load(f'fh_psbase_H6_{cell}',PS))
    s3=W(load(f'spill_wu2_{cell}',PS)) or W(load(f'spill_A_{cell}',PS))
    s6=W(load(f'fh_ps_H6_{cell}',PS)); p6=W(load(f'fh_pfo_H6_{cell}',FF))
    def f(v,w=10): return f'{v:>{w}.0f}' if v is not None else f'{\"--\":>{w}}'
    def g(a,b): return f'{a-b:+.0f}' if (a and b) else '--'
    print(f'{nm:7}{f(b3)}{f(b6)}{g(b3,b6):>8} | {f(s3)}{f(s6)}{g(s3,s6):>8} | {f(p6,9)}')
print()
print('  If base@H6 also degrades (gain negative) -> depth itself hurts the leader (not a spillback calibration artifact).')
print('  If base@H6 improves but spill@H6 degrades -> spillback is miscalibrated at deeper horizon.')
"
