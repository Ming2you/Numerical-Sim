#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
while :; do
  n=$(/c/Users/alsrj/anaconda3/python.exe -c "
import psutil
print(sum(1 for p in psutil.process_iter(['cmdline']) if (p.info['cmdline'] or []) and 'codex-runtimes' in (p.info['cmdline'][0] or '').replace(chr(92),'/') and any('run_claude' in c for c in p.info['cmdline'])))")
  [ "$n" -le 4 ] && break
  sleep 60
done
bash work/launch_tune_r31.sh
