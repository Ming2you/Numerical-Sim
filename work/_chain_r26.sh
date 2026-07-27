#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
# 현재 배치가 끝날 때까지 대기(동시 실행 과다 방지) 후 R26 투입
while :; do
  n=$(/c/Users/alsrj/anaconda3/python.exe -c "
import psutil
print(sum(1 for p in psutil.process_iter(['cmdline']) if (p.info['cmdline'] or []) and 'codex-runtimes' in (p.info['cmdline'][0] or '').replace(chr(92),'/') and any('run_claude' in c for c in p.info['cmdline'])))")
  [ "$n" -le 2 ] && break
  sleep 60
done
bash work/launch_alloc_r26.sh
bash work/launch_alloc_low_r27.sh
bash work/launch_prefilter_r28.sh
bash work/launch_r29.sh
