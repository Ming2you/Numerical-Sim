# price ON vs OFF를 원본 Figure 6 스타일 6패널로 한 축에 dash만 다르게 겹쳐 그리는 스크립트 (2026-07-23)
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

CELL = sys.argv[1] if len(sys.argv) > 1 else "170skew"
C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
BASE = "outputs/_diag"
RHO_CRIT = 31.5
OUT = f"2026-07-23/results/fig_price_onoff_{CELL}.png"

def rd(kind, f):
    return pd.read_csv(f"{BASE}/{kind}_{CELL}/{C}/{f}")

# ON = 가격 켠 닫힌루프(cf), OFF = 4채널 전부 끈 닫힌루프(alloff)
on_c, on_s = rd("cf", "control_timeseries.csv"), rd("cf", "state_timeseries.csv")
off_c, off_s = rd("alloff", "control_timeseries.csv"), rd("alloff", "state_timeseries.csv")

def tmin(df):  # time_sec -> min
    return pd.to_numeric(df["time_sec"], errors="coerce").to_numpy() / 60.0

def col(df, name):
    return pd.to_numeric(df[name], errors="coerce").to_numpy()

def meanpre(df, prefix, exclude=("ref", "enabled", "refresh", "count")):
    cs = [x for x in df.columns if x.startswith(prefix) and not any(e in x for e in exclude)]
    return df[cs].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy() if cs else None

GREENS = [f"green_{x}_p1" for x in "ABCDF"]
OFFS = [f"offset_{x}" for x in "ABCDF"]
RMP = [f"ramp_metering_R_{x}" for x in ["D_E", "D_W", "F_E", "F_W"]]

# (라벨, 좌축 series 추출함수, 좌축 라벨, 우축 price 추출함수 or None, 우축 라벨)
def lever_metering(c): return c[RMP].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy()
def lever_green(c):    return c[GREENS].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy()
def lever_offset(c):   return c[OFFS].apply(pd.to_numeric, errors="coerce").mean(axis=1).to_numpy()

PANELS = [
    ("(a)", "s", lambda s: col(s, "rho_FW_E_mean"), "Density [veh/km/lane]", None, None, RHO_CRIT),
    ("(b)", "s", lambda s: col(s, "urban_protected_accumulation_veh"), "Vehicles [veh]", None, None, None),
    ("(c)", "c", lever_metering, "Metering Rate [veh/h]", "diag_wu_b3_meter_price_R_", "Marginal Price", None),
    ("(d)", "c", lever_green, "Green time [sec]", "diag_wu_b2_price_", "Marginal Price", None),
    ("(e)", "c", lambda c: col(c, "vsl_FW_E"), "Speed Limit [km/h]", "diag_wu_b3_vsl_price_FW_E__seg", "Marginal Price", None),
    ("(f)", "c", lever_offset, "Offset [s]", "diag_wu_f3_offset_price_", "Marginal Price", None),
]

fig, axes = plt.subplots(3, 2, figsize=(9.2, 8.2))
axes = axes.ravel()
BLACK = "black"; PRICE_C = "#c0392b"; WARM = 15.0  # warm-up 0~900s = 0~15min

for ax, (tag, src, getf, ylab, pricepre, plab, hline) in zip(axes, PANELS):
    on_df = on_s if src == "s" else on_c
    off_df = off_s if src == "s" else off_c
    t_on, t_off = tmin(on_df), tmin(off_df)
    y_on, y_off = getf(on_df), getf(off_df)
    ax.axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)          # warm-up 음영
    if hline is not None:
        ax.axhline(hline, color="0.5", ls=(0, (6, 4)), lw=0.9)   # 임계밀도
    ax.plot(t_on, y_on, color=BLACK, ls="-", lw=1.6)            # Price ON = 실선
    ax.plot(t_off, y_off, color=BLACK, ls="--", lw=1.4)         # Price OFF = 파선
    ax.set_ylabel(ylab); ax.set_xlim(0, 240); ax.set_xticks(range(0, 241, 60))
    ax.set_xlabel("Time [min]")
    ax.text(0.03, 0.94, tag, transform=ax.transAxes, fontsize=11, fontweight="bold",
            va="top", ha="left", bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    if pricepre is not None:                                    # 우축: ON의 marginal price만
        p_on = meanpre(on_c, pricepre)
        if p_on is not None:
            ax2 = ax.twinx()
            ax2.plot(tmin(on_c), p_on, color=PRICE_C, ls=":", lw=1.4)
            ax2.set_ylabel(plab, color=PRICE_C)
            ax2.tick_params(axis="y", labelcolor=PRICE_C)
            m = np.nanmax(np.abs(p_on)); m = m if m > 0 else 1.0
            ax2.set_ylim(-1.15 * m, 1.15 * m)
            ax2.axhline(0, color=PRICE_C, lw=0.4, alpha=0.4)

handles = [Line2D([0], [0], color=BLACK, ls="-", lw=1.6, label="Price ON (proposed)"),
           Line2D([0], [0], color=BLACK, ls="--", lw=1.4, label="Price OFF (budget-only)"),
           Line2D([0], [0], color=PRICE_C, ls=":", lw=1.4, label="Marginal Price (ON)")]
fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.0))
fig.suptitle("")
fig.tight_layout(rect=(0, 0, 1, 0.965))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=200, bbox_inches="tight")
print("saved", OUT)
# 요약 수치
print(f"[{CELL}] density peak  ON={np.nanmax(col(on_s,'rho_FW_E_mean')):.1f}  OFF={np.nanmax(col(off_s,'rho_FW_E_mean')):.1f}  (crit {RHO_CRIT})")
print(f"[{CELL}] urban peak    ON={np.nanmax(col(on_s,'urban_protected_accumulation_veh')):.0f}  OFF={np.nanmax(col(off_s,'urban_protected_accumulation_veh')):.0f}")
print(f"[{CELL}] offset max    ON={np.nanmax(lever_offset(on_c)):.1f}  OFF={np.nanmax(lever_offset(off_c)):.1f}")
