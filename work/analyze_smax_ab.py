# S_max A/B 분석: (c)수렴율 + (b)채점-실행 N_UF 갭 + (a)candidate heatmap (2026-07-23)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
SMAX = [5, 10, 20]
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if k in d.columns else None

# ── (b)+(c) S_max별 비교 표 ──
print("=" * 78)
print(f"{'S_max':>6}{'conv율%':>9}{'iter평균':>9}{'iter최대':>9}{'res중앙':>10}{'res95th':>10}"
      f"{'NUF갭평균':>11}{'NUF갭최대':>11}")
rows = []
for s in SMAX:
    p = f"outputs/_diag/smax_skew_s{s}/{C}/run_log.csv"
    if not os.path.exists(p):
        print(f"{s:>6}  (미완/없음)"); continue
    d = pd.read_csv(p); t = num(d, "time_sec"); pk = (t >= 900) & (t < 5220)
    cv = num(d, "nash_converged"); it = num(d, "nash_iterations"); rc = num(d, "nash_residual_control")
    tgt = num(d, "leader_candidate_realized_N_UF_star")  # 채점이 예측한 realized
    rel = num(d, "leader_realized_N_UF_star")             # 실행 realized
    gap = np.abs(tgt - rel)
    convr = np.nanmean(cv) * 100
    print(f"{s:>6}{convr:>9.1f}{np.nanmean(it):>9.2f}{np.nanmax(it):>9.0f}"
          f"{np.nanmedian(rc):>10.4f}{np.nanpercentile(rc,95):>10.4f}"
          f"{np.nanmean(gap[pk]):>11.1f}{np.nanmax(gap[pk]):>11.0f}")
    rows.append((s, convr, np.nanmean(gap[pk]), np.nanmax(gap[pk])))
print("=" * 78)
print("판정: S_max↑ 시 conv율↑ AND NUF갭↓ 이면 → 비수렴이 갭 원인(살릴수있음).")
print("      conv율은 오르는데 갭 안 닫히면 → follower가 예산 무시(근본수정 필요).")

# ── (a) candidate heatmap: S_max=5 run, 대표 peak 스텝 ──
allcand = f"outputs/_diag/smax_skew_s5/cand.allcand.csv"
if os.path.exists(allcand):
    cd = pd.read_csv(allcand)
    for c2 in ["N_P_star", "N_UF_star", "objective", "step"]:
        cd[c2] = pd.to_numeric(cd[c2], errors="coerce")
    steps = sorted(cd["step"].dropna().unique())
    # peak 근처 스텝(t≈3000s → step 17 근방) 우선, 없으면 중앙
    target_step = min(steps, key=lambda x: abs(x - 17)) if steps else None
    sub = cd[cd["step"] == target_step].dropna(subset=["N_P_star", "N_UF_star", "objective"])
    print(f"\n(a) candidate heatmap: step {target_step}, 후보 {len(sub)}개")
    if len(sub) > 3:
        # 선택된 candidate = 최소 objective
        imin = sub["objective"].idxmin()
        fig, ax = plt.subplots(figsize=(6.2, 5.0))
        sc = ax.scatter(sub["N_P_star"], sub["N_UF_star"], c=sub["objective"],
                        cmap="viridis_r", s=120, edgecolor="0.3")
        ax.scatter(sub.loc[imin, "N_P_star"], sub.loc[imin, "N_UF_star"],
                   marker="*", s=420, color="red", edgecolor="black", zorder=5, label="selected (min J_L)")
        plt.colorbar(sc, label="leader objective J_L")
        ax.set_xlabel("N_P (protected urban budget)"); ax.set_ylabel("N_UF (freeway inflow budget)")
        ax.set_title(f"(a) Candidate-wise leader objective — step {target_step} (skew)")
        ax.legend()
        os.makedirs("2026-07-23/results", exist_ok=True)
        fig.tight_layout(); fig.savefig("2026-07-23/results/fig_a_candidate_heatmap.png", dpi=160, bbox_inches="tight")
        print("saved 2026-07-23/results/fig_a_candidate_heatmap.png")
else:
    print(f"\n(a) allcand 파일 없음: {allcand}")
