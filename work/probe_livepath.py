# 실제 플래그십 런에서 refined_candidates가 실행 경로에 있는지 + 반경위반 여부를 계측.
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.controllers.leader import Leader

runner = importlib.import_module('run_claude_style_five_controller')

SC = 'sweet_170_incident_w'
cfg, scenario = runner.build_cfg(SC, 12 * 180.0)
R = float(cfg.mpc.leader_local_nuf_radius_veh_h)

calls = []
orig = Leader.refined_candidates


def patched(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = orig(self, state, center, previous, demand, forecast, count)
    vals = [a.N_UF_star for a in out]
    calls.append((float(center.N_UF_star), min(vals), max(vals), len(out)))
    return out


Leader.refined_candidates = patched

import tempfile
out_root = Path(tempfile.mkdtemp(prefix='probe_lp_'))
res = runner.run_one('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', SC, 12 * 180.0, out_root, None)
print("refined_candidates 호출 횟수 =", len(calls))
print()
print("%10s | %10s %10s | %10s %10s | %s" % ('center', '반경下', '반경上', '후보min', '후보max', '판정'))
print('-' * 76)
viol_n = 0
for ctr, lo, hi, n in calls[:20]:
    lo_exp, hi_exp = ctr - R, ctr + R
    viol = (lo < lo_exp - 1) or (hi > hi_exp + 1)
    viol_n += bool(viol)
    print("%10.0f | %10.0f %10.0f | %10.0f %10.0f | %s (n=%d)"
          % (ctr, lo_exp, hi_exp, lo, hi, '★위반' if viol else 'OK', n))
print()
print("총 %d 호출 중 반경위반 %d" % (len(calls), sum(
    1 for ctr, lo, hi, n in calls if (lo < ctr - R - 1) or (hi > ctr + R + 1))))
