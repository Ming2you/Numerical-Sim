# Figure 6 스타일 6패널 — NC vs Proposed + marginal price (METER_SMOOTH=0.01, skew) 2026-07-24
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

RUN = sys.argv[1] if len(sys.argv) > 1 else "outputs/_ms/w0.01_170skew"
TAG = sys.argv[2] if len(sys.argv) > 2 else "w0.01"
C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
_cell = os.environ.get("CELL") or ("170skew" if "170skew" in RUN else RUN.rstrip("/").split("_")[-1])
NC = os.path.join(r"C:\Users\alsrj\Desktop\Numerical-Sim-offiter", "outputs", "_w60", f"nc_{_cell}", "NO-CONTROL")
RHO_CRIT = 31.5
OUT = f"2026-07-24/results/fig6_{TAG}_skew.png"

ctl = pd.read_csv(f"{RUN}/{C}/control_timeseries.csv")
sta = pd.read_csv(f"{RUN}/{C}/state_timeseries.csv")
nc_s = pd.read_csv(f"{NC}/state_timeseries.csv")
def col(df, k): return pd.to_numeric(df[k], errors="coerce").to_numpy() if k in df.columns else None
def tmin(df): return pd.to_numeric(df["time_sec"], errors="coerce").to_numpy() / 60.0
BAD = ("ref", "delta", "enabled", "refresh", "refreshed", "skipped", "trust", "count", "_sec")
def pmean(df, pre):
    cs = [c for c in df.columns if c.startswith(pre) and not any(b in c for b in BAD)]
    return df[cs].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy() if cs else None

t, tn = tmin(ctl), tmin(nc_s)
WARM = 15.0
SIG = list("ABCDF")
RMP = [f"ramp_metering_R_{x}" for x in ["D_E", "F_E", "D_W", "F_W"]]

fig, ax = plt.subplots(3, 2, figsize=(9.6, 8.6)); ax = ax.ravel()
BLK, PRC = "black", "black"

def connect(x, y):
    """결측(웜업·감독자 PFO 스왑 스텝)을 선형보간해 선을 잇는다. 양끝 결측은 그대로 둔다."""
    if y is None: return None
    y = np.asarray(y, dtype=float); ok = ~np.isnan(y)
    if ok.sum() < 2: return y
    out = y.copy()
    fill = np.interp(x, np.asarray(x)[ok], y[ok])
    lo, hi = np.where(ok)[0][0], np.where(ok)[0][-1]
    idx = np.arange(len(y))
    inner = (~ok) & (idx > lo) & (idx < hi)
    out[inner] = fill[inner]
    return out

def price_axis(a, x, p, ylab):
    if p is None or np.all(np.isnan(p)): return
    p = connect(x, p)
    a2 = a.twinx()
    a2.plot(x, p, color=PRC, ls="--", lw=1.2)
    a2.set_ylabel(ylab, fontsize=9)
    m = np.nanmax(np.abs(p)); m = m if m > 0 else 1.0
    a2.set_ylim(-1.15 * m, 1.15 * m)
    a2.axhline(0, color="0.6", lw=0.5, ls=":")

# (a) density
a = ax[0]; a.axvspan(0, WARM, color="0.85", lw=0)
a.plot(tn, col(nc_s, "rho_FW_E_mean"), color=BLK, ls="-.", lw=1.2)
a.plot(t, col(sta, "rho_FW_E_mean"), color=BLK, ls="-", lw=1.7)
a.axhline(RHO_CRIT, color="0.6", ls="--", lw=0.9)
a.set_ylabel("Density [veh/km/lane]"); a.set_title("(a)", loc="left", fontsize=11)

# (b) urban vehicles
a = ax[1]; a.axvspan(0, WARM, color="0.85", lw=0)
k = "urban_vehicles" if "urban_vehicles" in sta.columns else "urban_protected_accumulation_veh"
a.plot(tn, col(nc_s, k), color=BLK, ls="-.", lw=1.2)
a.plot(t, col(sta, k), color=BLK, ls="-", lw=1.7)
a.set_ylabel("Vehicles [veh]"); a.set_title("(b)", loc="left", fontsize=11)

# (c) metering + price
a = ax[2]; a.axvspan(0, WARM, color="0.85", lw=0)
a.plot(t, ctl[RMP].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy(), color=BLK, lw=1.6)
a.set_ylabel("Metering Rate [veh/h]"); a.set_title("(c)", loc="left", fontsize=11)
price_axis(a, t, pmean(ctl, "diag_wu_b3_meter_price_R_"), "Marginal Price")

# (d) green + price
a = ax[3]; a.axvspan(0, WARM, color="0.85", lw=0)
a.plot(t, ctl[[f"green_{s}_p1" for s in SIG]].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy(),
       color=BLK, lw=1.6)
a.set_ylabel("Green time [sec]"); a.set_title("(d)", loc="left", fontsize=11)
price_axis(a, t, pmean(ctl, "diag_wu_b2_price_"), "Marginal Price")

# (e) VSL + price — VSL_COL로 링크/세그먼트 선택(기본 FW_E)
VC = os.environ.get("VSL_COL", "vsl_FW_E")
a = ax[4]; a.axvspan(0, WARM, color="0.85", lw=0)
a.plot(t, col(ctl, VC), color=BLK, lw=1.6)
a.set_ylabel("Speed Limit [km/h]"); a.set_title("(e)", loc="left", fontsize=11)
_link = "FW_W" if "FW_W" in VC else "FW_E"
price_axis(a, t, pmean(ctl, f"diag_wu_b3_vsl_price_{_link}"), "Marginal Price")

# (f) offset + price
a = ax[5]; a.axvspan(0, WARM, color="0.85", lw=0)
a.plot(t, ctl[[f"offset_{s}" for s in SIG]].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy(),
       color=BLK, lw=1.6)
a.set_ylabel("Offset [s]"); a.set_title("(f)", loc="left", fontsize=11)
price_axis(a, t, pmean(ctl, "diag_wu_f3_offset_price_"), "Marginal Price")

for a in ax:
    a.set_xlabel("Time [min]"); a.set_xlim(0, 240); a.set_xticks(range(0, 241, 60))
handles = [Line2D([0], [0], color=BLK, ls="-.", lw=1.2, label="No Control"),
           Line2D([0], [0], color=BLK, ls="-", lw=1.7, label="Proposed"),
           Line2D([0], [0], color=BLK, ls="--", lw=1.2, label="Marginal Price")]
fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.005))
fig.tight_layout(rect=(0, 0, 1, 0.975))
os.makedirs("2026-07-24/results", exist_ok=True)
fig.savefig(OUT, dpi=175, bbox_inches="tight")
print("saved", OUT)
for lab, v in [("density peak", col(sta, "rho_FW_E_mean")), ("urban peak", col(sta, k)),
               ("metering", ctl[RMP].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy()),
               ("VSL("+VC+")", col(ctl, VC))]:
    print(f"  {lab:14} 범위 [{np.nanmin(v):.1f}, {np.nanmax(v):.1f}]")
