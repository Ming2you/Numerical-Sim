#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT; FF=WU-FAITHFUL-FOLLOWER
while :; do
  done=1
  for H in 4 6; do
    for cell in 170inc 190 170; do
      f="outputs/_diag/fh_ps_H${H}_${cell}/$PS/run_log.csv"
      n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
      g="outputs/_diag/fh_pfo_H${H}_${cell}/$FF/run_log.csv"
      m=$( [ -f "$g" ] && wc -l < "$g" || echo 0 ); [ "$m" -lt 80 ] && done=0
    done
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== FAIR-HORIZON (H4+H6) ALL DONE ====="
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
def pfo(cell,H): return W(load(f'pfosplit_{cell}',FF)) if H==3 else W(load(f'fh_pfo_H{H}_{cell}',FF))
def ps(cell,H):
    if H==3:
        return W(load(f'spill_wu2_{cell}',PS)) or W(load(f'spill_A_{cell}',PS))
    return W(load(f'fh_ps_H{H}_{cell}',PS))
print('='*92)
print('FAIR HORIZON — same H, PFO vs P-Stack(spillback). negative = hierarchy wins')
print('='*92)
for cell,nm in [('170','Med'),('170inc','Inc'),('190','High')]:
    print(f'--- {nm}({cell}) ---')
    print(f'  {\"H\":>4}{\"PFO\":>9}{\"P-Stack\":>10}{\"diff\":>9}')
    for H in [3,4,6,9,12]:
        p=pfo(cell,H); s=ps(cell,H)
        if p is None and s is None: continue
        ds=f'{s-p:+.0f}' if (p and s) else '--'
        mk='  <- HIER WIN' if (p and s and s<p) else ''
        sp=f'{s:>10.0f}' if s else f'{\"--\":>10}'
        pp=f'{p:>9.0f}' if p else f'{\"--\":>9}'
        print(f'  {H:>4}{pp}{sp}{ds:>9}{mk}')
print()
print('='*92)
print('DEPTH GAIN vs H3 (positive = deeper is better)')
print(f'{\"cell\":7}| {\"PFO H3-4\":>10}{\"H3-6\":>8} | {\"PS H3-4\":>10}{\"H3-6\":>8}')
for cell,nm in [('170','Med'),('170inc','Inc'),('190','High')]:
    p3,p4,p6=pfo(cell,3),pfo(cell,4),pfo(cell,6)
    s3,s4,s6=ps(cell,3),ps(cell,4),ps(cell,6)
    def g(a,b): return f'{a-b:+.0f}' if (a and b) else '--'
    print(f'{nm:7}| {g(p3,p4):>10}{g(p3,p6):>8} | {g(s3,s4):>10}{g(s3,s6):>8}')
"
