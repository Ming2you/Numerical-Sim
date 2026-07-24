# 독립 검증: coarse_local이 live 경로인지 + 실제 center에서 반경위반이 나는지 폐루프로 계측.
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.controllers.leader import Leader

runner = importlib.import_module('run_claude_style_five_controller')

T_TOTAL = 26 * 180.0
cfg0, _ = runner.build_cfg('sweet_170_incident_w', T_TOTAL)
R = float(cfg0.mpc.leader_local_nuf_radius_veh_h)
interval = float(cfg0.simulation.control_interval)
refresh_steps = max(1, int(round(float(cfg0.mpc.leader_global_refresh_sec) / interval)))
print("control_interval=%.0f  global_refresh_sec=%.0f  -> refresh_steps=%d"
      % (interval, cfg0.mpc.leader_global_refresh_sec, refresh_steps))
print("leader_local_nuf_radius_veh_h =", R)
print()

# 실제 호출을 가로채 기록(반환값 그대로 통과 = 프로덕션 동작 불변)
records = []
_orig = Leader.refined_candidates


def spy(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _orig(self, state, center, previous, demand, forecast, count)
    vals = [a.N_UF_star for a in out]
    records.append({
        "step": int(round(float(state.time_sec) / interval)),
        "count_arg": count,
        "center": float(center.N_UF_star),
        "min": min(vals), "max": max(vals), "n": len(out),
    })
    return out


Leader.refined_candidates = spy
out_root = ROOT / 'work' / '_verify_radius_out'
try:
    runner.run_one('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', 'sweet_170_incident_w',
                   T_TOTAL, out_root, None)
finally:
    Leader.refined_candidates = _orig

print()
print("refined_candidates 총 호출 = %d" % len(records))
if not records:
    print("!! 한 번도 호출되지 않음 = 죽은 경로 (주장 반증)")
    sys.exit()

# coarse_local 시그니처 = count 인자가 채워진 호출(stackelberg_mpc.py:771)
local = [r for r in records if r["count_arg"] is not None]
print("그중 coarse_local 시그니처(count 지정) = %d" % len(local))
print()

viol = 0
print("%5s %9s %8s | %9s %9s | %9s %9s | %s"
      % ('step', 'count_arg', 'center', '반경下', '반경上', '후보min', '후보max', '판정'))
print('-' * 88)
for r in local:
    lo_exp, hi_exp = r["center"] - R, r["center"] + R
    bad = (r["min"] < lo_exp - 1) or (r["max"] > hi_exp + 1)
    viol += bool(bad)
    print("%5d %9s %8.0f | %9.0f %9.0f | %9.0f %9.0f | %s (n=%d)"
          % (r["step"], r["count_arg"], r["center"], lo_exp, hi_exp,
             r["min"], r["max"], '★반경위반' if bad else 'OK', r["n"]))

print()
print("반경위반 %d/%d (coarse_local 호출)" % (viol, len(local)))
centers = sorted(set(round(r["center"]) for r in local))
ranges = sorted(set((round(r["min"]), round(r["max"])) for r in local))
print("서로 다른 center 값 =", centers)
print("서로 다른 (후보min,후보max) =", ranges)
print("=> 후보범위가 center와 무관한가? %s" % (len(ranges) == 1 and len(centers) > 1))
