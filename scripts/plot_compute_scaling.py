# 3 컨트롤러(Aug.Dist./P-Stack/Centralized-grid) player 수 대비 계산비용 스케일링(2026-07-22)
"""Computation-cost scaling vs network size for the three optimizing controllers.

측정: 사례망(=1x)서 스텝당 실측 avg = Aug.Dist 2.3s / Proposed(P-Stack) 39.0s /
Centralized(grid) 220.0s. 곡선은 각 구조의 online 복잡도를 그 실측점에 앵커한 해석 곡선.
- Aug.Dist., P-Stack: O(n) 선형(분산 로컬예산 / 저차원 리더+선형 follower).
- Centralized(grid): joint 제어 차원 d=O(n) 직접최적화 → 초선형(보수적으로 O(n^3);
  exhaustive grid는 지수라 더 가파름). 논문 centralized=grid와 라벨 일치.
가로 점선 = 제어주기 180s(실시간 가능 경계).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                     "font.size": 12, "axes.linewidth": 1.0})

N0 = 21                              # 사례망 크기: 5 intersections + 16 freeway segments
n = np.linspace(14, 120, 300)        # network size n (players/agents)
aug = 2.3 * (n / N0)                 # O(n)
pstack = 39.0 * (n / N0)             # O(n)  (CAND49; CAND25 ~ 26)
cent = 220.0 * (n / N0)**3           # super-linear O(n^3) (grid over d=O(n) joint control)

fig, ax = plt.subplots(figsize=(7.6, 5.0))
ax.plot(n, cent,   "k--",  lw=2.4, label=r"Centralized $\sim O(n^{3})$")
ax.plot(n, pstack, "k-",   lw=2.4, label=r"Proposed $\sim O(n)$")
ax.plot(n, aug,    "k:",   lw=2.6, label=r"Aug. Dist. $\sim O(n)$")

# 실측 앵커점(n0=21, case study)
ax.plot([N0,N0,N0], [2.3,39.0,220.0], "o", mfc="white", mec="black", ms=7, zorder=5)
ax.axvline(N0, color="0.75", lw=1.0, ls=":")
ax.text(N0+1.2, 1.25, "case study\n(n = 21)", ha="left", va="bottom", fontsize=8.5, color="0.35")

# 실시간 경계
ax.axhline(180, color="0.5", lw=1.2, ls=(0,(6,4)))
ax.text(44, 330, "control interval (180 s)", ha="left", va="center", fontsize=9, color="0.35")

ax.set_yscale("log")
ax.set_xlabel(r"Network size $n$ (intersections + freeway segments)")
ax.set_ylabel("Computation cost per step [s]")
ax.set_xlim(14, 120); ax.set_ylim(1.2, 3e4)
ax.minorticks_off()                          # minor 눈금·gridline 제거(정리)
ax.set_yticks([1e1, 1e2, 1e3, 1e4])          # 데케이드만: 10^1~10^4
ax.grid(True, which="major", axis="y", color="0.9", lw=0.7)
for sp in ("top","right"): ax.spines[sp].set_visible(False)
ax.legend(loc="lower right", frameon=False, fontsize=10.5)

fig.tight_layout()
base = r"C:\Users\alsrj\Desktop\Numerical-Sim-offiter\outputs\_wang3\fig_compute_scaling"
fig.savefig(base+".png", dpi=220, bbox_inches="tight")
fig.savefig(base+".pdf", bbox_inches="tight")
print("saved:", base+".png / .pdf")
