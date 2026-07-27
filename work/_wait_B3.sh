#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for t in fd0 prx; do for c in 155 170 170skew 170inc 190; do
    f="outputs/_diag/B3_${t}_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done; done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R47 BASE-3STEP DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe -c "
import os,pandas as pd,numpy as np
PS='P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'; FF='WU-FAITHFUL-FOLLOWER'
def load(fp,ct=PS):
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
print('='*94)
print('★3 vs 3 기준선 (리더도 3스텝). 감독자X · 예산O · 적응규칙X · spillback 없음')
print('='*94)
print(f'{\"cell\":8}{\"PFO@3\":>10} | {\"FAR_D0=1\":>10}{\"gap\":>9} | {\"proxy경로\":>10}{\"gap\":>9} | {\"참고:이산@3\":>12}')
wa=wb=0
for cell,nm in [('155','Low'),('170','Med'),('170skew','Skew'),('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF))
    a=W(load(f'B3_fd0_{cell}')); b=W(load(f'B3_prx_{cell}')); d=W(load(f'DD_{cell}'))
    def g(v):
        return f'{v-pfo:+9.1f}' if (v is not None and pfo is not None) else '       --'
    if a is not None and a<pfo: wa+=1
    if b is not None and b<pfo: wb+=1
    av=f'{a:>10.1f}' if a is not None else f'{\"--\":>10}'
    bv=f'{b:>10.1f}' if b is not None else f'{\"--\":>10}'
    dv=f'{d-pfo:+12.1f}' if (d is not None and pfo) else f'{\"--\":>12}'
    print(f'{nm:8}{pfo:>10.1f} | {av}{g(a)} | {bv}{g(b)} | {dv}')
print('-'*94)
print(f'  FAR_D0=1: {wa}/5 승   proxy경로: {wb}/5 승')
print('  → 더 나은 채점 경로를 3v3 튜닝의 출발점으로 삼는다')
"
