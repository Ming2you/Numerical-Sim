# (b) Selected leader targets vs realized responses — clean 런(PRICE_CF 없음, S_max=10) 2026-07-24
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
D = "outputs/_diag/camp_s10on_170skew"
log = pd.read_csv(f"{D}/{C}/run_log.csv")
def n(k): return pd.to_numeric(log[k], errors="coerce").to_numpy() if k in log.columns else None
t = n("time_sec") / 60.0
WARM = 15.0

tgt_np, rel_np = n("leader_candidate_best_N_P_star"), n("leader_realized_N_P_star")
tgt_uf, rel_uf = n("leader_candidate_best_N_UF_star"), n("leader_realized_N_UF_star")
ramp = n("ramp_metering_releases_veh")
merge = n("mainline_exit_flow_total")

fig, ax = plt.subplots(1, 3, figsize=(13.6, 4.0))
# (b1) N_P
ax[0].axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
ax[0].plot(t, tgt_np, color="tab:blue", ls="--", lw=1.6, label="target $N_P^*$")
ax[0].plot(t, rel_np, color="black", ls="-", lw=1.3, label="realized $N_P$")
ax[0].set_ylabel("urban budget [veh]"); ax[0].set_title("(b1) protected urban accumulation")
# (b2) N_UF
ax[1].axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
ax[1].plot(t, tgt_uf, color="tab:orange", ls="--", lw=1.6, label="target $N_{UF}^*$")
ax[1].plot(t, rel_uf, color="black", ls="-", lw=1.3, label="realized $N_{UF}$")
ax[1].set_ylabel("freeway inflow budget [veh/h]"); ax[1].set_title("(b2) aggregate metering budget")
# (b3) 교통 물리량
ax[2].axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
ax[2].plot(t, ramp, color="tab:red", lw=1.4, label="ramp releases [veh]")
ax2 = ax[2].twinx()
ax2.plot(t, merge, color="tab:green", lw=1.2, alpha=0.8, label="mainline exit flow")
ax2.set_ylabel("mainline exit flow [veh/h]", color="tab:green"); ax2.tick_params(axis="y", labelcolor="tab:green")
ax[2].set_ylabel("ramp releases [veh]", color="tab:red"); ax[2].tick_params(axis="y", labelcolor="tab:red")
ax[2].set_title("(b3) realized traffic response")
for a in ax:
    a.set_xlabel("Time [min]"); a.set_xlim(0, 240); a.set_xticks(range(0, 241, 60))
ax[0].legend(fontsize=9); ax[1].legend(fontsize=9)
fig.tight_layout()
os.makedirs("2026-07-24/results", exist_ok=True)
fig.savefig("2026-07-24/results/fig_b_target_realized.png", dpi=160, bbox_inches="tight")

# 추종 정확도
pk = (t >= 15) & (t < 87)
for lab, tg, rl in [("N_P", tgt_np, rel_np), ("N_UF", tgt_uf, rel_uf)]:
    g = np.abs(tg - rl)
    rel_err = np.nanmean(g[pk]) / np.nanmean(np.abs(tg[pk])) * 100
    print(f"{lab}: peak |target-realized| 평균={np.nanmean(g[pk]):.1f} 최대={np.nanmax(g[pk]):.1f} "
          f"(상대오차 {rel_err:.2f}%)  target범위=[{np.nanmin(tg):.0f},{np.nanmax(tg):.0f}]")
print("saved 2026-07-24/results/fig_b_target_realized.png")
