# 가격 효과만 분리: Δmetering=(cfon-cfoff)를 한계가격과 겹쳐 co-movement로 억제/완화를 직접 보임 (2026-07-23)
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

CELL = sys.argv[1] if len(sys.argv) > 1 else "170skew"
C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
OUT = f"2026-07-23/results/fig_price_effect_{CELL}.png"

d = pd.read_csv(f"outputs/_diag/cf_{CELL}/{C}/run_log.csv")
def num(k): return pd.to_numeric(d[k], errors="coerce").to_numpy()
t = num("time_sec") / 60.0
WARM = 15.0
DIRS = [("Eastbound on-ramps", ["R_D_E", "R_F_E"]), ("Westbound on-ramps", ["R_D_W", "R_F_W"])]
DELTA_C = "#1f4e79"; PRICE_C = "#c0392b"

fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2), sharey=True)
for ax, (title, ramps) in zip(axes, DIRS):
    cfon = np.nansum([num(f"cfon_meter_{r}") for r in ramps], axis=0)
    cfoff = np.nansum([num(f"cfoff_meter_{r}") for r in ramps], axis=0)
    price = np.nanmean([num(f"wu_b3_meter_price_{r}") for r in ramps], axis=0)
    delta = cfon - cfoff  # 가격의 인과 효과: >0 완화(더 열음), <0 억제(더 조임)
    ax.axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
    ax.axhline(0, color="0.6", lw=0.8)
    # Δ를 0 기준 채움: 양(완화)=파랑, 음(억제)=빨강계열
    ax.fill_between(t, 0, delta, where=(delta >= 0), color=DELTA_C, alpha=0.35, lw=0, label="loosened (Δ>0)")
    ax.fill_between(t, 0, delta, where=(delta < 0), color=PRICE_C, alpha=0.35, lw=0, label="suppressed (Δ<0)")
    ax.plot(t, delta, color=DELTA_C, lw=1.3)
    ax.set_ylabel("Price effect on metering\nΔ = applied − counterfactual [veh/h]")
    ax.set_xlabel("Time [min]"); ax.set_xlim(0, 240); ax.set_xticks(range(0, 241, 60))
    ax.set_title(title, fontsize=11)
    ax2 = ax.twinx()
    ax2.plot(t, price, color=PRICE_C, ls=":", lw=1.5)
    ax2.set_ylabel("Metering marginal price", color=PRICE_C)
    ax2.tick_params(axis="y", labelcolor=PRICE_C)
    m = np.nanmax(np.abs(price)); m = m if m > 0 else 1.0
    ax2.set_ylim(-1.15 * m, 1.15 * m); ax2.axhline(0, color=PRICE_C, lw=0.3, alpha=0.4)
    pk = (t >= 15) & (t < 87); nz = pk & (np.abs(delta) > 1e-6) & ~np.isnan(price)
    r = np.corrcoef(price[nz], delta[nz])[0, 1] if nz.sum() > 3 else float("nan")
    ax.text(0.97, 0.05, f"Σ={np.nansum(delta[pk]):+.0f} veh/h\ncorr(price,Δ)={r:+.2f}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7"))

handles = [plt.Rectangle((0,0),1,1, fc=DELTA_C, alpha=0.35, ec="none", label="loosened (price opens ramp)"),
           plt.Rectangle((0,0),1,1, fc=PRICE_C, alpha=0.35, ec="none", label="suppressed (price restricts ramp)"),
           Line2D([0],[0], color=PRICE_C, ls=":", lw=1.5, label="Metering marginal price")]
fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.03), fontsize=9)
fig.tight_layout(rect=(0, 0, 1, 0.92))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=200, bbox_inches="tight")
print("saved", OUT)
