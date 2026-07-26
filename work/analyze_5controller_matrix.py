# 5컨트롤러 × 5시나리오 비교표 (새 VSL 코드, S_max=10) — 2026-07-24
import os
import numpy as np, pandas as pd

CELLS = ["155", "170", "170skew", "170inc", "190"]
NAME = {"155": "Low", "170": "Medium", "170skew": "Med-skew", "170inc": "Med-incident", "190": "High"}
# (라벨, 디렉토리 tag, 컨트롤러 폴더명)
CTRLS = [
    ("No control", "mtx_NO-CONTROL", "NO-CONTROL"),
    ("Wu (WU-CD-F)", "mtx_WU-CD-F", "WU-CD-F"),
    ("PFO", "mtx_WU-FAITHFUL-FOLLOWER", "WU-FAITHFUL-FOLLOWER"),
    ("P-CENT", "mtx_P-CENT", "P-CENT"),
    ("P-Stack", "camp_s10on", "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"),
]
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if k in d.columns else None
def win(d, warm=5):
    cum = num(d, "cumulative_total_ttt"); st = num(d, "step")
    bi = next((i for i, s in enumerate(st) if s == warm - 1), None)
    return cum[-1] - (cum[bi] if bi is not None else 0)
def load(tag, ctl, cell):
    p = f"outputs/_diag/{tag}_{cell}/{ctl}/run_log.csv"
    if not os.path.exists(p): return None
    d = pd.read_csv(p)
    return d if len(d) >= 80 else None

# ── TTT 표 ──
T = {}
for lab, tag, ctl in CTRLS:
    for cell in CELLS:
        d = load(tag, ctl, cell)
        T[(lab, cell)] = win(d) if d is not None else None

print("=" * 96)
print("windowed TTT (veh·h, 900–14,400 s) — 새 VSL 코드(smoothness 0) + S_max=10")
print(f"{'Controller':16}" + "".join(f"{NAME[c]:>15}" for c in CELLS))
for lab, _, _ in CTRLS:
    print(f"{lab:16}" + "".join(
        (f"{T[(lab,c)]:>15.1f}" if T[(lab, c)] is not None else f"{'(미완)':>15}") for c in CELLS))

# ── NC 대비 개선율 ──
print("\n" + "=" * 96)
print("TTT reduction vs No control (%)  [양수=개선]")
print(f"{'Controller':16}" + "".join(f"{NAME[c]:>15}" for c in CELLS))
for lab, _, _ in CTRLS:
    if lab == "No control": continue
    row = ""
    for c in CELLS:
        nc, v = T[("No control", c)], T[(lab, c)]
        row += f"{(nc-v)/nc*100:>+15.1f}" if (nc is not None and v is not None) else f"{'-':>15}"
    print(f"{lab:16}{row}")

# ── 계산시간 ──
print("\n" + "=" * 96)
print("평균 계산시간 per control update (s)")
print(f"{'Controller':16}" + "".join(f"{NAME[c]:>15}" for c in CELLS))
for lab, tag, ctl in CTRLS:
    row = ""
    for cell in CELLS:
        d = load(tag, ctl, cell)
        if d is None: row += f"{'-':>15}"; continue
        ct = num(d, "computation_time_sec"); ct = ct[ct > 0.01] if ct is not None else None
        row += f"{np.nanmean(ct):>15.1f}" if ct is not None and len(ct) else f"{'-':>15}"
    print(f"{lab:16}{row}")
