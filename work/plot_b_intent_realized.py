# (b) 재작성 — intent(리더가 commit한 요청) vs realized(follower 실현), _w60 showcase (2026-07-24)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
D = "outputs/_w60/pstack_170skew"
log = pd.read_csv(f"{D}/{C}/run_log.csv")
def n(k): return pd.to_numeric(log[k], errors="coerce").to_numpy() if k in log.columns else None
t = n("time_sec") / 60.0
WARM = 15.0

iu, ru = n("leader_intent_N_UF_star"), n("leader_realized_N_UF_star")
ip, rp = n("leader_intent_N_P_star"), n("leader_realized_N_P_star")
pp = n("leader_projected_N_P_star")   # 실현가능 구간으로 사영된 N_P 목표

fig, ax = plt.subplots(1, 3, figsize=(14.0, 4.1))

# (b1) N_UF: intent vs realized
ax[0].axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
ax[0].plot(t, iu, color="tab:orange", ls="--", lw=1.8, label="intent $N_{UF}^*$ (leader request)")
ax[0].plot(t, ru, color="black", ls="-", lw=1.2, label="realized $N_{UF}$ (follower)")
ax[0].set_ylabel("$N_{UF}$ [veh/h]"); ax[0].set_title("(b1) freeway inflow budget")
ax[0].legend(fontsize=8, loc="lower right")

# (b2) N_P: intent → projected → realized
ax[1].axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
ax[1].plot(t, ip, color="tab:red", ls=":", lw=1.5, label="raw intent $N_P^*$")
if pp is not None:
    ax[1].plot(t, pp, color="tab:blue", ls="--", lw=1.6, label="projected (feasible) $N_P^*$")
ax[1].plot(t, rp, color="black", ls="-", lw=1.2, label="realized $N_P$")
ax[1].set_ylabel("$N_P$ [veh]"); ax[1].set_title("(b2) protected urban budget")
ax[1].legend(fontsize=8, loc="upper right")

# (b3) 추종 오차
ax[2].axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
ax[2].axhline(0, color="0.6", lw=0.8)
ax[2].plot(t, ru - iu, color="tab:orange", lw=1.4, label="$N_{UF}$: realized − intent")
base = pp if pp is not None else ip
ax[2].plot(t, rp - base, color="tab:blue", lw=1.2, alpha=0.8, label="$N_P$: realized − projected")
ax[2].set_ylabel("tracking error"); ax[2].set_title("(b3) budget tracking error")
ax[2].legend(fontsize=8)

for a in ax:
    a.set_xlabel("Time [min]"); a.set_xlim(0, 240); a.set_xticks(range(0, 241, 60))
fig.tight_layout()
os.makedirs("2026-07-24/results", exist_ok=True)
fig.savefig("2026-07-24/results/fig_b_intent_realized.png", dpi=170, bbox_inches="tight")

# 통계
for lab, a, b in [("N_UF (intent→realized)", iu, ru),
                  ("N_P  (raw intent→realized)", ip, rp),
                  ("N_P  (projected→realized)", pp, rp)]:
    if a is None: continue
    m = ~np.isnan(a) & ~np.isnan(b); g = np.abs(a - b)
    big = m & (g > 1)
    rel = np.nanmean(g[m]) / np.nanmean(np.abs(a[m])) * 100
    s = f"  {lab:28} |gap| 평균={np.nanmean(g[m]):8.2f} 최대={np.nanmax(g[m]):8.1f} 상대={rel:5.2f}%  갭>1={int(big.sum())}/{int(m.sum())}"
    if big.sum(): s += f"  (t={t[big].min():.0f}~{t[big].max():.0f}분)"
    print(s)
print("saved 2026-07-24/results/fig_b_intent_realized.png")
