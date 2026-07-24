# 실행 중 python sim 런/대기스크립트 정확 조회(자기 배제)
import subprocess, json, os
me = os.getpid()
ps = subprocess.run(['powershell.exe','-NoProfile','-Command',
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json"],
  capture_output=True, text=True)
try: data = json.loads(ps.stdout)
except Exception: data = []
if isinstance(data, dict): data = [data]
runs, waits = [], []
for p in data:
    pid = p.get('ProcessId'); cl = (p.get('CommandLine') or '')
    if pid == me: continue
    if ' -c ' in cl or cl.rstrip().endswith('-c'): continue  # 인라인 배제
    if 'run_claude_style_five_controller.py' in cl and '--scenario' in cl:
        out = cl.split('--output ')[-1].split(' ')[0] if '--output' in cl else '?'
        runs.append((pid, out))
    if 'wait_' in cl and '.py' in cl and 'run_claude' not in cl:
        waits.append((pid, cl.split('.py')[0].split('\\')[-1].split('/')[-1]))
print('실행 중 sim 런:', len(runs))
for pid, out in sorted(runs, key=lambda x: x[1]): print('  PID', pid, out)
print('대기 스크립트:', waits if waits else '없음')
