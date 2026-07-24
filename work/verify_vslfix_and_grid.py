# VSL 수정 검증(cooldown 115 회복) + conv율 + (a) candidate 격자 heatmap (2026-07-23)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
D = "outputs/_diag/final_skew_s10"
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if k in d.columns else None

log = pd.read_csv(f"{D}/{C}/run_log.csv")
ctl = pd.read_csv(f"{D}/{C}/control_timeseries.csv")
t = num(log, "time_sec"); pk = (t >= 900) & (t < 5220)
tc = num(ctl, "time_sec")

# ── 1) VSL cooldown 회복 검증 ──
vsl = num(ctl, "vsl_FW_E")
cool = tc >= 6000  # cooldown (peak 종료 후)
print("=== VSL 수정 검증 ===")
print(f"  VSL_FW_E: peak 최소={np.nanmin(vsl[(tc>=900)&(tc<5220)]):.0f}  cooldown(>6000s) 평균={np.nanmean(vsl[cool]):.1f} 최종={vsl[-1]:.0f} km/h")
print(f"  → cooldown서 115 근처로 회복하면 수정 성공 (전엔 100 고착)")

# ── 2) conv율 ──
cv = num(log, "nash_converged"); it = num(log, "nash_iterations")
print(f"\n=== 수렴 (S_max=10) ===")
print(f"  conv율 peak={np.nanmean(cv[pk])*100:.0f}% 전체={np.nanmean(cv)*100:.0f}%  iter평균={np.nanmean(it):.2f} 최대={np.nanmax(it):.0f}")

# ── 3) windowed TTT ──
def win(d, warm=5):
    cum = num(d, "cumulative_total_ttt"); st = num(d, "step")
    bi = next((i for i, s in enumerate(st) if s == warm - 1), None)
    return cum[-1] - (cum[bi] if bi is not None else 0)
print(f"\n  windowed TTT(full 900-14400) = {win(log):.1f}")
base = f"outputs/hinge_matrix/base_170skew/{C}/run_log.csv"
if os.path.exists(base):
    print(f"  (참고 구base_170skew = {win(pd.read_csv(base)):.1f}; 단 구코드라 직접비교 주의)")

# ── 4) (a) candidate 격자 heatmap ──
gp = f"{D}/grid.grid.csv"
if os.path.exists(gp):
    g = pd.read_csv(gp)
    for c2 in ["N_P", "N_UF", "objective", "sel_N_P", "sel_N_UF"]:
        g[c2] = pd.to_numeric(g[c2], errors="coerce")
    g = g.dropna(subset=["N_P", "N_UF", "objective"])
    print(f"\n=== (a) 격자 heatmap: {len(g)}점, N_P[{g['N_P'].min():.0f},{g['N_P'].max():.0f}] N_UF[{g['N_UF'].min():.0f},{g['N_UF'].max():.0f}] ===")
    nps = np.sort(g["N_P"].unique()); nufs = np.sort(g["N_UF"].unique())
    Z = np.full((len(nufs), len(nps)), np.nan)
    for _, r in g.iterrows():
        Z[np.searchsorted(nufs, r["N_UF"]), np.searchsorted(nps, r["N_P"])] = r["objective"]
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    im = ax.pcolormesh(nps, nufs, Z, cmap="viridis_r", shading="nearest")
    plt.colorbar(im, label="leader objective J_L")
    selp, selu = g["sel_N_P"].iloc[0], g["sel_N_UF"].iloc[0]
    ax.plot(selp, selu, marker="*", ms=24, color="red", mec="black", mew=1.2, label="selected candidate")
    ax.set_xlabel("N_P (protected urban budget)"); ax.set_ylabel("N_UF (freeway inflow budget)")
    ax.set_title("(a) Candidate-wise leader objective (skew, peak step 17)")
    ax.legend(loc="lower right")
    os.makedirs("2026-07-23/results", exist_ok=True)
    fig.tight_layout(); fig.savefig("2026-07-23/results/fig_a_grid_heatmap.png", dpi=160, bbox_inches="tight")
    print("saved 2026-07-23/results/fig_a_grid_heatmap.png")
else:
    print(f"\n(a) grid 파일 없음: {gp}")
