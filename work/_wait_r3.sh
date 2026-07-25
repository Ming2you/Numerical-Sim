#!/usr/bin/env bash
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
cells="155 170 170skew 170inc 190"
while :; do
  done=1
  for c in $cells; do
    f="outputs/_diag/redesign_G_${c}/$PS/run_log.csv"
    n=$( [ -f "$f" ] && wc -l < "$f" || echo 0 )
    [ "$n" -lt 80 ] && done=0
  done
  [ "$done" = 1 ] && break
  sleep 30
done
echo "===== R3 ALL DONE ====="
PYTHONIOENCODING=utf-8 /c/Users/alsrj/anaconda3/python.exe work/analyze_redesign_r3.py
