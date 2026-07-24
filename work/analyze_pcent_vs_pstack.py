# P-CENT(중앙) vs P-Stack vs PFO — 광범위 교통 KPI 비교 (2026-07-24)
# 목적: centralized가 P-Stack과 유별나게 다른 점(특히 freeway/urban 전가, 램프 차등, 잔류혼잡).
import os
import pandas as pd, numpy as np
BASE = "C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
def sload(folder):  # summary.csv (컨트롤러 공통 KPI)
    p = os.path.join(BASE, f"outputs/_diag/{folder}/summary.csv")
    return pd.read_csv(p).iloc[0] if os.path.exists(p) else None
def rload(folder, ctrl):
    p = os.path.join(BASE, f"outputs/_diag/{folder}/{ctrl}/run_log.csv")
    return pd.read_csv(p) if os.path.exists(p) else None
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if (d is not None and k in d.columns) else None
def pk(d, k, lo=900, hi=5220):
    v = num(d, k); t = num(d, "time_sec")
    return float(np.nanmean(v[(t >= lo) & (t < hi)])) if v is not None else None
RAMPS = ["R_D_E", "R_D_W", "R_F_E", "R_F_W"]
def ramp_diff(d):  # peak 램프간 metering std (차등 배분 정도)
    vals = [num(d, f"ramp_metering_release_actual_{r}_veh") for r in RAMPS]
    if any(v is None for v in vals): return None, None
    t = num(d, "time_sec"); m = (t >= 900) & (t < 5220)
    arr = np.vstack(vals)[:, m]
    return float(np.nanmean(arr)), float(np.nanmean(np.nanstd(arr, axis=0)))

CTRL = {"PFO": ("pfosplit", "WU-FAITHFUL-FOLLOWER"),
        "P-Stack": ("pstack4", "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"),
        "P-CENT": ("pcent", "P-CENT")}
CELLS = [("Incident", "170inc"), ("High", "190"), ("Medium", "170")]

for nm, cell in CELLS:
    print("=" * 96)
    print(f"### {nm} ({cell}) — P-CENT vs P-Stack vs PFO 광범위 KPI")
    rows = {}
    for c, (fpre, ctrl) in CTRL.items():
        s = sload(f"{fpre}_{cell}"); d = rload(f"{fpre}_{cell}", ctrl)
        if s is None: rows[c] = None; continue
        mt, mstd = ramp_diff(d)
        rows[c] = dict(
            TTT=s.get("total_ttt"), delay=s.get("total_delay"),
            fdelay=s.get("freeway_delay"), udelay=s.get("urban_delay"),
            done=s.get("completed_vehicles"), term=s.get("terminal_total_vehicles"),
            thru=s.get("network_throughput_veh_h"),
            uacc=pk(d, "urban_accumulation_mean_veh"),
            rampq=pk(d, "leader_ramp_queue_veh") if pk(d, "leader_ramp_queue_veh") is not None else pk(d, "onramp_approach_queue_veh"),
            meter=mt, meterstd=mstd, cpu=s.get("mean_step_compute_sec"))
    hdr = ["metric"] + list(CTRL.keys())
    print(f"{'metric':16}" + "".join(f"{k:>12}" for k in CTRL))
    def line(key, label, fmt="{:.0f}"):
        vs = []
        for c in CTRL:
            v = rows[c][key] if rows[c] else None
            vs.append(fmt.format(v) if v is not None and np.isfinite(v) else "미완")
        print(f"{label:16}" + "".join(f"{x:>12}" for x in vs))
    line("TTT", "총TTT"); line("delay", "총delay")
    line("fdelay", "freeway delay"); line("udelay", "urban delay")
    line("done", "완료(throughput)"); line("term", "잔류(uncleared)")
    line("thru", "throughput/h"); line("uacc", "urban 누적")
    line("meter", "metering 방류"); line("meterstd", "램프차등(std)", "{:.1f}")
    line("cpu", "compute s/step", "{:.1f}")
print("=" * 96)
print("주목: (1)P-CENT도 freeway↓urban↑ 전가하나(fdelay/udelay) (2)램프차등(std) P-CENT>P-Stack? (3)잔류·throughput 우열")
