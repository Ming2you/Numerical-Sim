# 알고리즘 검증 그림 프로토타입 (b) target vs realized + (c) residual/iteration — 기존 데이터로 (2026-07-23)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
CELLS = [("Low", "155"), ("Medium", "170"), ("Skew", "170skew"), ("Incident", "170inc"), ("High", "190")]
EPS = 0.001; S_MAX = 5
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if k in d.columns else None

# ── (c) 통계: 전체 셀 pooled ──
res_ctrl = []; res_obj = []; iters = []; conv = []
for _, cell in CELLS:
    d = pd.read_csv(f"outputs/_diag/cf_{cell}/{C}/run_log.csv")
    for k, acc in [("nash_residual_control", res_ctrl), ("nash_residual_objective", res_obj),
                   ("nash_iterations", iters), ("nash_converged", conv)]:
        v = num(d, k)
        if v is not None: acc.extend(v[~np.isnan(v)])
res_ctrl = np.array(res_ctrl); iters = np.array(iters); conv = np.array(conv)
conv_rate = conv.mean() * 100
hit_cap = (iters >= S_MAX).mean() * 100
print(f"=== (c) best-response 통계 (전체 {len(iters)} epochs) ===")
print(f"convergence rate = {conv_rate:.1f}%  |  S_max({S_MAX}) 도달 = {hit_cap:.1f}%")
print(f"iteration 평균 = {iters.mean():.2f}, 최대 = {iters.max():.0f}")
print(f"residual_control: 평균 {res_ctrl.mean():.4f}, 중앙 {np.median(res_ctrl):.4f}, 95th {np.percentile(res_ctrl,95):.4f}, 최대 {res_ctrl.max():.4f}")
print(f"수렴 epoch residual < ε({EPS}) 확인: {(res_ctrl[conv==1] < EPS).mean()*100:.0f}%")

fig, ax = plt.subplots(1, 3, figsize=(13.5, 4.0))
# 패널 (c1): residual CDF
rs = np.sort(res_ctrl); cdf = np.arange(1, len(rs)+1) / len(rs)
ax[2].plot(rs, cdf, color="black", lw=1.8)
ax[2].axvline(EPS, color="red", ls="--", lw=1.2, label=f"ε={EPS}")
ax[2].set_xscale("log"); ax[2].set_xlabel("best-response control residual"); ax[2].set_ylabel("CDF (epochs)")
ax[2].set_title(f"(c) residual — conv {conv_rate:.0f}%, S_max hit {hit_cap:.0f}%")
ax[2].legend(fontsize=9); ax[2].grid(alpha=0.3)
# 패널 (c2 inset): iteration 분포 → 별도 작은 축 대신 텍스트
ax[1].hist(iters, bins=np.arange(0.5, S_MAX+1.5, 1), color="0.5", edgecolor="black")
ax[1].axvline(S_MAX, color="red", ls="--", lw=1.2, label=f"S_max={S_MAX}")
ax[1].set_xlabel("best-response iterations"); ax[1].set_ylabel("epochs")
ax[1].set_title("(c) iteration 분포"); ax[1].legend(fontsize=9)

# ── (b) target vs realized: skew ──
d = pd.read_csv(f"outputs/_diag/cf_170skew/{C}/run_log.csv")
t = num(d, "time_sec") / 60.0
for tgt, rel, lab, c in [("leader_candidate_best_N_P_star", "leader_realized_N_P_star", "N_P", "tab:blue"),
                         ("leader_candidate_best_N_UF_star", "leader_realized_N_UF_star", "N_UF", "tab:orange")]:
    ax[0].plot(t, num(d, tgt), color=c, ls="--", lw=1.3, label=f"{lab} target")
    ax[0].plot(t, num(d, rel), color=c, ls="-", lw=1.6, label=f"{lab} realized")
ax[0].axvspan(0, 15, color="0.85", alpha=0.6, lw=0)
ax[0].set_xlabel("Time [min]"); ax[0].set_ylabel("budget [veh/h]"); ax[0].set_xlim(0, 240)
ax[0].set_title("(b) leader target vs realized (skew)"); ax[0].legend(fontsize=8, ncol=2)
gap_uf = np.abs(num(d, "leader_candidate_best_N_UF_star") - num(d, "leader_realized_N_UF_star"))
print(f"\n=== (b) skew: N_UF |target-realized| 평균={np.nanmean(gap_uf):.1f} 최대={np.nanmax(gap_uf):.0f} ===")

fig.tight_layout()
os.makedirs("2026-07-23/results", exist_ok=True)
fig.savefig("2026-07-23/results/fig_proto_algo_verification.png", dpi=160, bbox_inches="tight")
print("saved 2026-07-23/results/fig_proto_algo_verification.png")
