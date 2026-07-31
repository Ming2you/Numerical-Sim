#!/bin/bash
set -u
read -r KIND A B <<< "$1"
cd /c/Users/alsrj/Desktop/NumSim-mine || exit 1
if [ "$KIND" = "MS" ]; then unset VS; bash work/run_ms_only_job.sh "$A" "$B"
else export VS="$A"; bash work/run_ms_only_job.sh 0 "$B"; fi
