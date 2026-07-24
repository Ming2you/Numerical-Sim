# 같은 state에서 가격의 인과 효과를 보여주는 반사실 그림: cfon(실제) vs cfoff(가격없었으면) + 한계가격 (2026-07-23)
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

CELL = sys.argv[1] if len(sys.argv) > 1 else "170skew"
C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
OUT = f"2026-07-23/results/fig_price_suppression_{CELL}.png"

d = pd.read_csv(f"outputs/_diag/cf_{CELL}/{C}/run_log.csv")
def num(k): return pd.to_numeric(d[k], errors="coerce").to_numpy()
t = num("time_sec") / 60.0
WARM = 15.0

# 방향별 합: 동(E)=R_D_E+R_F_E, 서(W)=R_D_W+R_F_W
DIRS = [("Eastbound on-ramps", ["R_D_E", "R_F_E"]), ("Westbound on-ramps", ["R_D_W", "R_F_W"])]
BLACK = "black"; PRICE_C = "#c0392b"

fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2))
for ax, (title, ramps) in zip(axes, DIRS):
    cfon = np.nansum([num(f"cfon_meter_{r}") for r in ramps], axis=0)
    cfoff = np.nansum([num(f"cfoff_meter_{r}") for r in ramps], axis=0)
    price = np.nanmean([num(f"wu_b3_meter_price_{r}") for r in ramps], axis=0)
    ax.axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
    # cfon/cfoff가 동일(가격 미작동) 구간은 겹치고, 벌어지면 그 gap이 가격의 인과 효과
    ax.plot(t, cfon, color=BLACK, ls="-", lw=1.7, label="Applied (price ON)")
    ax.plot(t, cfoff, color=BLACK, ls="--", lw=1.4, label="Counterfactual (price OFF, same state)")
    # gap 음영 = 가격이 민 양
    ax.fill_between(t, cfoff, cfon, where=~np.isnan(cfon) & ~np.isnan(cfoff),
                    color=PRICE_C, alpha=0.15, lw=0)
    ax.set_ylabel("Metering rate [veh/h]"); ax.set_xlabel("Time [min]")
    ax.set_xlim(0, 240); ax.set_xticks(range(0, 241, 60)); ax.set_title(title, fontsize=11)
    ax2 = ax.twinx()
    ax2.plot(t, price, color=PRICE_C, ls=":", lw=1.5)
    ax2.set_ylabel("Metering marginal price", color=PRICE_C)
    ax2.tick_params(axis="y", labelcolor=PRICE_C)
    m = np.nanmax(np.abs(price)); m = m if m > 0 else 1.0
    ax2.set_ylim(-1.15 * m, 1.15 * m)
    ax2.axhline(0, color=PRICE_C, lw=0.4, alpha=0.4)
    # 요약 수치
    pk = (t >= 15) & (t < 87)
    net = np.nansum((cfon - cfoff)[pk])
    print(f"[{CELL}] {title}: 가격이 민 순량 Σ(cfon-cfoff)={net:+.0f} veh/h  (>0 완화, <0 억제)")

handles = [Line2D([0], [0], color=BLACK, ls="-", lw=1.7, label="Applied (price ON)"),
           Line2D([0], [0], color=BLACK, ls="--", lw=1.4, label="Counterfactual (price OFF, same state)"),
           Line2D([0], [0], color=PRICE_C, ls=":", lw=1.5, label="Metering marginal price"),
           plt.Rectangle((0, 0), 1, 1, fc=PRICE_C, alpha=0.15, ec="none", label="Price effect (gap)")]
fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.02), fontsize=9)
fig.tight_layout(rect=(0, 0, 1, 0.93))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=200, bbox_inches="tight")
print("saved", OUT)
