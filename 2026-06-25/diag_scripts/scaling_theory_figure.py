# 이론 스케일링 그림: follower 수 n에 대한 centralized vs P-Stack 계산비용(coupled-eval/step), 측정 앵커.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["mathtext.fontset"] = "stix"

# --- 측정 앵커 (sweet_128, T=1440) ---
n0 = 7
delta = 23.0 / n0   # d=23 = n*delta
H = 3
pstack_meas = 1302.0

n = np.linspace(1, 24, 400)
dH = n * delta * H

# Centralized 진짜 ceiling(결합 dH차원 global 최적): 격자 k^(dH), k=2 보수적.
cent_true = 2.0 ** dH
# P-Stack 현 구현(coupled-rollout follower): O(n^2).
pstack_current = pstack_meas * (n / n0) ** 2
# P-Stack 이상(분해, 국소 rollout): O(n).
pstack_ideal = pstack_meas * (n / n0)

TRACT = 1e6  # 실용 tractability 한계(step당 eval) 예시

fig, ax = plt.subplots(figsize=(7.4, 5.2))
ax.plot(n, cent_true, color="#b2182b", lw=2.6, label=r"Centralized MPC (true optimum) $\;\sim k^{\,n\delta H}$  — exponential")
ax.plot(n, pstack_current, color="#2166ac", lw=2.6, label=r"P-Stack, current impl. $\;\sim n^{2}$")
ax.plot(n, pstack_ideal, color="#4393c3", lw=2.4, ls="--", label=r"P-Stack, decomposed (local follower) $\;\sim n$")

ax.axhline(TRACT, color="#444444", ls=":", lw=1.4)
ax.text(0.6, TRACT * 1.6, "practical tractability limit", fontsize=9, color="#444")

# centralized가 한계선을 넘는 n* 표시
nstar = (np.log2(TRACT)) / (delta * H)
ax.axvspan(nstar, 24, color="#fde0dc", alpha=0.45)
ax.text((nstar + 24) / 2, 1e16, "centralized\nintractable\nas true ceiling", ha="center", fontsize=9, color="#b2182b")

ax.scatter([n0], [pstack_meas], color="#2166ac", zorder=6, s=60, edgecolor="k")
ax.annotate("measured P-Stack (1302)", (n0, pstack_meas), textcoords="offset points",
            xytext=(10, -4), fontsize=9, color="#2166ac")
ax.axvline(n0, color="k", ls=":", lw=1.0)
ax.text(n0 + 0.3, 3e22, "current\nnetwork\n$n=7$", fontsize=9)

ax.set_yscale("log")
ax.set_ylim(1e1, 1e25)
ax.set_xlim(0, 24)
ax.set_xlabel(r"network size $n$  (number of follower subsystems)", fontsize=12)
ax.set_ylabel(r"computational cost  (coupled-model evals / control step)", fontsize=11)
ax.set_title("Why hierarchy scales: Centralized (exponential) vs P-Stack (polynomial)", fontsize=12)
ax.legend(fontsize=9.5, loc="lower right", framealpha=0.96)
ax.grid(True, which="major", alpha=0.25)
fig.tight_layout()
out = "reports/figures/fig_scaling_centralized_vs_pstack.png"
fig.savefig(out, dpi=150)
print("wrote", out, f"| n*(tractability) = {nstar:.1f}")
