# 알고리즘 검증 3패널 (a)(b)(c) — _w60 논문 시나리오 showcase (2026-07-24)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
D = "outputs/_w60/pstack_170skew"
OUTDIR = "2026-07-24/results"
os.makedirs(OUTDIR, exist_ok=True)
log = pd.read_csv(f"{D}/{C}/run_log.csv")
def n(k): return pd.to_numeric(log[k], errors="deprecated" if False else "coerce").to_numpy() if k in log.columns else None
t = n("time_sec") / 60.0
WARM = 15.0

fig = plt.figure(figsize=(14.4, 4.3))

# ── (a) candidate landscape ──
ax = fig.add_subplot(1, 3, 1)
g = pd.read_csv(f"{D}/grid.grid.csv")
for c2 in ["N_P", "N_UF", "objective", "sel_N_P", "sel_N_UF"]:
    g[c2] = pd.to_numeric(g[c2], errors="coerce")
g = g.dropna(subset=["N_P", "N_UF", "objective"])
nps, nufs = np.sort(g["N_P"].unique()), np.sort(g["N_UF"].unique())
Z = np.full((len(nufs), len(nps)), np.nan)
for _, r in g.iterrows():
    Z[np.searchsorted(nufs, r["N_UF"]), np.searchsorted(nps, r["N_P"])] = r["objective"]
im = ax.pcolormesh(nps, nufs, Z, cmap="viridis_r", shading="nearest")
plt.colorbar(im, ax=ax, label="leader objective $J_L$")
ax.plot(g["sel_N_P"].iloc[0], g["sel_N_UF"].iloc[0], marker="*", ms=22,
        color="red", mec="black", mew=1.2, label="selected")
ax.set_xlabel("$N_P$ (urban budget) [veh]"); ax.set_ylabel("$N_{UF}$ (freeway inflow budget) [veh/h]")
ax.set_title("(a) Candidate-wise leader objective"); ax.legend(loc="lower right", fontsize=8)
o = g["objective"].to_numpy()
print(f"(a) J_L 범위 {o.min():.1f}~{o.max():.1f} (상대변동 {(o.max()-o.min())/abs(o.mean())*100:.1f}%), "
      f"최소점 N_P={g.loc[o.argmin(),'N_P']:.0f} N_UF={g.loc[o.argmin(),'N_UF']:.0f}, "
      f"선택 N_P={g['sel_N_P'].iloc[0]:.0f} N_UF={g['sel_N_UF'].iloc[0]:.0f}")

# ── (b) target vs realized ──
ax = fig.add_subplot(1, 3, 2)
tp, rp = n("leader_candidate_best_N_P_star"), n("leader_realized_N_P_star")
tu, ru = n("leader_candidate_best_N_UF_star"), n("leader_realized_N_UF_star")
ax.axvspan(0, WARM, color="0.85", alpha=0.6, lw=0)
ax.plot(t, tu, color="tab:orange", ls="--", lw=1.6, label="target $N_{UF}^*$")
ax.plot(t, ru, color="black", ls="-", lw=1.2, label="realized $N_{UF}$")
ax.set_ylabel("$N_{UF}$ [veh/h]"); ax.set_xlabel("Time [min]")
ax.set_xlim(0, 240); ax.set_xticks(range(0, 241, 60))
ax2 = ax.twinx()
ax2.plot(t, tp, color="tab:blue", ls="--", lw=1.4, alpha=0.8)
ax2.plot(t, rp, color="tab:blue", ls="-", lw=1.0, alpha=0.5)
ax2.set_ylabel("$N_P$ [veh]", color="tab:blue"); ax2.tick_params(axis="y", labelcolor="tab:blue")
ax.set_title("(b) Leader targets vs realized"); ax.legend(loc="lower right", fontsize=8)
for lab, a, b in [("N_P", tp, rp), ("N_UF", tu, ru)]:
    m = ~np.isnan(a) & ~np.isnan(b); gg = np.abs(a - b)
    print(f"(b) {lab}: |gap| 평균={np.nanmean(gg[m]):.1f} 최대={np.nanmax(gg[m]):.1f}, "
          f"상대={np.nanmean(gg[m])/np.nanmean(np.abs(a[m]))*100:.2f}%")

# ── (c) convergence ──
ax = fig.add_subplot(1, 3, 3)
r = pd.read_csv(f"{D}/resid.resid.csv")
for c2 in ["step", "iteration", "residual", "tol"]:
    r[c2] = pd.to_numeric(r[c2], errors="coerce")
tol = r["tol"].dropna().iloc[0]
r = r.reset_index(drop=True); seq = (r["iteration"].diff() <= 0).cumsum()
plotted = 0
for _, sub in r.groupby(seq):
    sub = sub[sub["residual"] > 0]
    if len(sub) >= 3:
        ax.plot(sub["iteration"], sub["residual"], marker="o", ms=2.5, alpha=0.45, lw=0.9)
        plotted += 1
    if plotted >= 40: break
ax.axhline(tol, color="red", ls="--", lw=1.3, label=f"$\\epsilon$={tol}")
ax.set_yscale("log"); ax.set_xlabel("best-response iteration"); ax.set_ylabel("coupling residual")
cv = n("nash_converged"); it = n("nash_iterations")
pk = (t >= 15) & (t < 87)
ax.set_title(f"(c) Follower convergence (conv {np.nanmean(cv[pk])*100:.0f}% in peak)")
ax.legend(fontsize=8); ax.grid(alpha=0.3)
print(f"(c) conv peak={np.nanmean(cv[pk])*100:.0f}% 전체={np.nanmean(cv)*100:.0f}%, "
      f"iter 평균={np.nanmean(it):.2f} 최대={np.nanmax(it):.0f}, {plotted} sequences")

fig.tight_layout()
fig.savefig(f"{OUTDIR}/fig_abc_w60.png", dpi=170, bbox_inches="tight")
print(f"saved {OUTDIR}/fig_abc_w60.png")
