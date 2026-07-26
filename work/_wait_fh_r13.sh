#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT; FF=WU-FAITHFUL-FOLLOWER
while :; do
  done=1
  for cell in 170inc 190 170; do
    f="outputs/_diag/fh_ps_H6_${cell}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
    g="outputs/_diag/fh_pfo_H6_${cell}/$FF/run_log.csv"
    m=$( [ -f "$g" ] && wc -l < "$g" || echo 0 ); [ "$m" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R13 FAIR-HORIZON H6 DONE ====="
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
print('★공정 지평 심화(H3 vs H6, 양쪽 동일) — 계층이 분산보다 더 얻는가?')
print(f'{\"cell\":7}| {\"PFO@H3\":>8}{\"PFO@H6\":>8}{\"PFOgain\":>8} | {\"PS@H3\":>8}{\"PS@H6\":>8}{\"PSgain\":>8} | {\"H6차이\":>9}')
for cell,nm in [('170','Med'),('170inc','Inc'),('190','High')]:
    p3=W(load(f'pfosplit_{cell}',FF))
    p6=W(load(f'fh_pfo_H6_{cell}',FF))
    s3=W(load(f'spill_wu2_{cell}',PS)) or W(load(f'spill_A_{cell}',PS))
    s6=W(load(f'fh_ps_H6_{cell}',PS))
    def f(v,w=8): return f'{v:>{w}.0f}' if v is not None else f'{\"--\":>{w}}'
    pg=f'{p3-p6:+.0f}' if (p3 and p6) else '--'
    sg=f'{s3-s6:+.0f}' if (s3 and s6) else '--'
    d6=f'{s6-p6:+.0f}' if (s6 and p6) else '--'
    mk=' WIN' if (s6 and p6 and s6<p6) else ''
    print(f'{nm:7}| {f(p3)}{f(p6)}{pg:>8} | {f(s3)}{f(s6)}{sg:>8} | {d6:>9}{mk}')
print()
print('  gain = H3 - H6 (양수면 깊어져서 개선). H6차이 = PS@H6 - PFO@H6 (음수면 계층 승).')
print('  ★해석: PSgain > PFOgain 이면 \"조정 가치는 lookahead가 있어야 발현\" 논문 스토리 성립.')
"
