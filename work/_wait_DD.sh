#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
while :; do
  done=1
  for c in 155 170 170skew 170inc 190; do
    f="outputs/_diag/DD_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 ); [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break; sleep 30
done
echo "===== R44 DONE ====="
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
print('='*96)
print('★깊이 요인 분해 — 리더 rollout 6스텝 vs 3스텝 (규칙은 동일)')
print('='*96)
print(f'{\"cell\":8}{\"PFO\":>9} | {\"이산@6\":>9}{\"이산@3\":>9} | {\"연속@6\":>9}{\"연속@3\":>9}')
wins={'d6':0,'d3':0,'c6':0,'c3':0}
for cell,nm in [('155','Low'),('170','Med'),('170skew','Skew'),('170inc','Inc'),('190','High')]:
    pfo=W(load(f'pfosplit_{cell}',FF))
    d6=W(load(f'FIN2_{cell}')); d3=W(load(f'DD_{cell}'))
    c6=W(load(f'S_{cell}'));   c3=W(load(f'E0_{cell}'))
    def g(v,k):
        if v is None or pfo is None: return '   --'
        gap=v-pfo
        if gap<0: wins[k]+=1
        return f'{gap:+9.1f}'
    print(f'{nm:8}{pfo:>9.1f} | {g(d6,\"d6\")}{g(d3,\"d3\")} | {g(c6,\"c6\")}{g(c3,\"c3\")}')
print('-'*96)
print(f'  승수: 이산@6={wins[\"d6\"]}/5  이산@3={wins[\"d3\"]}/5  연속@6={wins[\"c6\"]}/5  연속@3={wins[\"c3\"]}/5')
print('  → @6 대비 @3에서 크게 떨어지면 \"P-Stack 우위는 리더의 깊은 rollout 덕\"이 확정')
"
