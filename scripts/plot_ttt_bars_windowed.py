# windowed(A) total TTT 그룹 막대그림 — 참조 Fig 스타일(흑백 해칭) 재현(2026-07-21)
"""5 시나리오 × 5 컨트롤러 windowed total TTT [veh·h] 막대그래프.

데이터 = 창 [900s,14400s](warmup 제외, buffer 포함) total TTT.
컨트롤러 라벨은 참조 그림과 동일: No Control / Coordinated(Wu) /
Aug. Coordinated(PFO) / Centralized(dense) / Proposed(P-Stack b13).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 12,
    "axes.linewidth": 1.0,
})

classes = ["Low", "Medium", "Medium-Skew", "Medium-Incident", "High"]
# windowed total TTT [veh·h]
data = {
    "No Control": [3061, 4558, 4582, 5977, 6897],
    "Dist.":      [3006, 4325, 4383, 5843, 7261],
    "Aug. Dist.": [2988, 3864, 3938, 5953, 6157],
    "Centralized":[2942, 3794, 3867, 5013, 5718],
    "Proposed":   [2990, 3810, 3990, 5546, 5735],
}
order = ["No Control", "Dist.", "Aug. Dist.", "Centralized", "Proposed"]
hatches = {
    "No Control": "///",
    "Dist.":      "---",
    "Aug. Dist.": "|||",
    "Centralized":"....",
    "Proposed":   "xxx",
}
fills = {
    "No Control": "white",
    "Dist.":      "white",
    "Aug. Dist.": "white",
    "Centralized":"white",
    "Proposed":   "0.82",
}

fig, ax = plt.subplots(figsize=(8.2, 4.6))
n = len(order)
bw = 0.16
xs = list(range(len(classes)))

nc_vals = data["No Control"]

def imp_label(name, k):
    base = nc_vals[k]
    v = (base - data[name][k]) / base * 100.0 if base else 0.0
    if abs(v) < 0.05:
        return "0.0%"
    return f"{'+' if v > 0 else '−'}{abs(v):.1f}%"

bars_for_legend = []
for i, name in enumerate(order):
    offs = [x + (i - (n - 1) / 2) * bw for x in xs]
    b = ax.bar(offs, data[name], width=bw, facecolor=fills[name],
               edgecolor="black", linewidth=0.9, hatch=hatches[name], label=name)
    bars_for_legend.append(b)
    for k, rect in enumerate(b):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 80,
                imp_label(name, k), rotation=45, rotation_mode="anchor",
                ha="left", va="bottom", fontsize=6.5)

ax.set_ylabel("TTT [veh h]")
ax.set_xticks(xs)
ax.set_xticklabels(classes, fontsize=10.5)
ax.set_ylim(0, 8600)
ax.set_yticks([0, 4000, 8000])
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: "0" if v == 0 else f"{v/1000:g}k"))
ax.yaxis.grid(True, color="0.8", linewidth=0.8)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

leg = ax.legend(
    loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=5,
    frameon=False, handlelength=1.6, handletextpad=0.5, columnspacing=1.2,
    fontsize=10,
)

fig.tight_layout()
out_png = r"C:\Users\alsrj\Desktop\Numerical-Sim-offiter\outputs\_wang3\fig_ttt_bars_windowed.png"
out_pdf = r"C:\Users\alsrj\Desktop\Numerical-Sim-offiter\outputs\_wang3\fig_ttt_bars_windowed.pdf"
fig.savefig(out_png, dpi=220, bbox_inches="tight")
fig.savefig(out_pdf, bbox_inches="tight")
print("saved:", out_png)
print("saved:", out_pdf)
