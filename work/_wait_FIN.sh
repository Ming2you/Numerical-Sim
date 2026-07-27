#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in 155 170 170skew 170inc 190; do
    f="outputs/_diag/FIN_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R38 FINAL DONE ====="
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
print('='*90)
print('★최종 AUTH_ADAPT 3-분기 — 감독자X · 예산O · 새 메커니즘 없음')
print('='*90)
print(f'{\"cell\":8}{\"PFO\":>10}{\"PS4base\":>10}{\"최종\":>10}{\"P-CENT\":>9}{\"gap\":>10}')
w=0;n=0
for cell,nm in [('155','Low'),('170','Med'),('170skew','Skew'),('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF)); base=W(load(f'pstack4_{cell}')); pc=W(load(f'pcent_{cell}','P-CENT'))
    a=W(load(f'FIN_{cell}'))
    def f(v,w2=10): return f'{v:>{w2}.1f}' if v is not None else f'{\"--\":>{w2}}'
    if a is None: print(f'{nm:8}{f(pfo)}{f(base)}{\"미완\":>10}'); continue
    g=a-pfo; n+=1
    if g<0: w+=1
    print(f'{nm:8}{f(pfo)}{f(base)}{f(a)}{f(pc,9)}{g:>+10.2f}{\"  WIN\" if g<0 else \"\"}')
print('-'*90)
print(f'  PFO {w}/{n} 셀' + ('   ★★★ 5/5 달성 — 감독자 없음 + 예산 유지! ★★★' if w==5 and n==5 else ''))
"
