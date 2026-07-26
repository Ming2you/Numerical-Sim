#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in 155 170 170skew 170inc; do
    f="outputs/_diag/fin_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== FINAL RULE ALL DONE ====="
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
print('='*86)
print('★최종 AUTH_ADAPT 단일 규칙 — 5셀 (음수 = PFO 이김)')
print('='*86)
print(f'{\"cell\":8}{\"PFO\":>8}{\"PS4base\":>9}{\"FINAL\":>8}{\"PCENT\":>8}{\"gap\":>10}')
wins=0; done=0
for cell,nm,src in [('155','Low','fin_155'),('170','Med','fin_170'),('170skew','Skew','fin_170skew'),
                    ('170inc','Inc','fin_170inc'),('190','High','a22_d239t15_190')]:
    pfo=W(load(f'pfosplit_{cell}',FF)); base=W(load(f'pstack4_{cell}',PS))
    a=W(load(src,PS)); pc=W(load(f'pcent_{cell}','P-CENT'))
    def f(v,w=8): return f'{v:>{w}.0f}' if v is not None else f'{\"--\":>{w}}'
    if a is not None and pfo is not None:
        done+=1; g=a-pfo
        if g<0: wins+=1
        gs=f'{g:+.0f}'+(' WIN' if g<0 else '')
    else: gs='--'
    print(f'{nm:8}{f(pfo)}{f(base,9)}{f(a)}{f(pc)}{gs:>14}')
print('-'*86)
print(f'  PFO {wins}/{done} 셀' + ('   ★★★ 5셀 전부 이김! ★★★' if wins==5 and done==5 else ''))
"
