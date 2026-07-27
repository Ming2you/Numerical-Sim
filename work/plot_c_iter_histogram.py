# (c) best-response 수렴 — iteration 히스토그램(5셀) + 시퀀스별 수렴 분포 (2026-07-24)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
CELLS = [("Low", "155"), ("Medium", "170"), ("Med-skew", "170skew"),
         ("Med-incident", "170inc"), ("High", "190")]
S_MAX = 10
fig, ax = plt.subplots(1, 2, figsize=(12.2, 4.2))

# ── (좌) 5셀 제어 epoch당 iteration 히스토그램 ──
w = 0.16
xs = np.arange(1, S_MAX + 1)
for i, (name, cell) in enumerate(CELLS):
    p = f"outputs/_w60/pstack_{cell}/{C}/run_log.csv"
    if not os.path.exists(p): continue
    d = pd.read_csv(p)
    it = pd.to_numeric(d["nash_iterations"], errors="coerce").dropna().astype(int)
    bc = np.bincount(it, minlength=S_MAX + 1)[1:S_MAX + 1] / len(it) * 100
    ax[0].bar(xs + (i - 2) * w, bc, width=w, label=f"{name} (n={len(it)})")
ax[0].axvline(S_MAX + 0.5, color="red", ls="--", lw=1.2)
ax[0].text(S_MAX + 0.45, ax[0].get_ylim()[1] * 0.92, f"$S_{{max}}$={S_MAX}",
           color="red", ha="right", fontsize=9)
ax[0].set_xticks(xs); ax[0].set_xlabel("best-response iterations per control update")
ax[0].set_ylabel("share of control updates [%]")
ax[0].set_title("(c1) iteration count distribution (all cells)")
ax[0].legend(fontsize=8); ax[0].grid(axis="y", alpha=0.3)

# ── (우) 시퀀스별 '수렴까지 반복수' 누적분포 (showcase) ──
rp = "outputs/_w60/pstack_170skew/resid.resid.csv"
if os.path.exists(rp):
    r = pd.read_csv(rp)
    for k in ["iteration", "residual", "tol"]:
        r[k] = pd.to_numeric(r[k], errors="coerce")
    tol = r["tol"].dropna().iloc[0]
    seq = (r["iteration"].diff() <= 0).cumsum()
    conv = []
    for _, s in r.groupby(seq):
        hit = s[s["residual"] < tol]
        conv.append(int(hit["iteration"].iloc[0]) if len(hit) else S_MAX + 1)
    conv = np.array(conv)
    bc = np.bincount(conv, minlength=S_MAX + 2)[1:S_MAX + 1]
    ax[1].bar(xs, bc / len(conv) * 100, color="0.45", label="converged at iteration $k$")
    cum = np.cumsum(bc) / len(conv) * 100
    ax2 = ax[1].twinx()
    ax2.plot(xs, cum, color="tab:red", marker="o", ms=4, lw=1.6, label="cumulative")
    ax2.set_ylabel("cumulative converged [%]", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red"); ax2.set_ylim(0, 105)
    ax2.axhline(100, color="tab:red", ls=":", lw=0.8)
    ax[1].set_xticks(xs); ax[1].set_xlabel("iterations to reach $\\epsilon$")
    ax[1].set_ylabel("share of best-response solves [%]")
    ax[1].set_title(f"(c2) convergence distribution (Med-skew, {len(conv)} solves)")
    ax[1].grid(axis="y", alpha=0.3)
    nc = int((conv > S_MAX).sum())
    print(f"(c2) {len(conv)} solves: {(conv<=S_MAX).mean()*100:.1f}% converged ≤{S_MAX}, "
          f"미수렴 {nc}개, 중앙값 {np.median(conv[conv<=S_MAX]):.0f}회")
fig.tight_layout()
os.makedirs("2026-07-24/results", exist_ok=True)
fig.savefig("2026-07-24/results/fig_c_iteration_hist.png", dpi=170, bbox_inches="tight")
print("saved 2026-07-24/results/fig_c_iteration_hist.png")
