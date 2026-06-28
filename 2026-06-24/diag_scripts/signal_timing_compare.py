# perimeter 교차로(D) movement별 green-window+offset+큐를 PFO vs P-Stack로 비교(Fig 4.16 스타일), on-ramp movement 강조
from __future__ import annotations
import csv
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from src.models.state import ExperimentConfig

plt.rcParams["font.family"] = "Times New Roman"; plt.rcParams["mathtext.fontset"] = "stix"
BASE = "outputs/leadervalue_demand_15/runs/demand_15"
NODE = "D"
cfg = ExperimentConfig.from_file("src/config/default.yaml")
net = cfg.network
CYCLE = net.cycle_length; LOST = net.lost_time
mv = {m: s for m, s in net.urban_movements.items() if str(s.get("intersection")) == NODE}

KIND_COLOR = {"on_ramp": "#d62728", "off_ramp": "#9467bd", "boundary_in": "#2ca02c",
              "boundary_out": "#1f77b4", "internal": "#7f7f7f"}
def is_onramp(s): return "on" in str(s.get("destination", "")).lower() or str(s.get("kind", "")) == "on_ramp"

def last_row(c, fn):
    return list(csv.DictReader(open(f"{BASE}/{c}/{fn}")))[-1]

def green_windows(g1, g2, off):
    """phase별 green 구간(offset 적용, cycle wrap)."""
    def wrap(a, b):
        a %= CYCLE; b_=a+(b-a)
        if b_ <= CYCLE: return [(a, b_)]
        return [(a, CYCLE), (0, b_-CYCLE)]
    p1 = wrap(off, off+g1)
    p2 = wrap(off+g1+LOST, off+g1+LOST+g2)
    return {"%s_p1" % NODE: p1, "%s_p2" % NODE: p2}

ctrls = [("PROPOSED-FOLLOWERS-ONLY", "PFO"), ("PROPOSED-STACKELBERG", "P-Stack")]
order = sorted(mv.keys(), key=lambda m: (mv[m].get("phase", ""), not is_onramp(mv[m]), m))

fig, axes = plt.subplots(1, 2, figsize=(14, 9), sharey=True)
for ax, (c, lbl) in zip(axes, ctrls):
    ct = last_row(c, "control_timeseries.csv"); st = last_row(c, "state_timeseries.csv")
    g1 = float(ct[f"green_{NODE}_p1"]); g2 = float(ct[f"green_{NODE}_p2"]); off = float(ct[f"offset_{NODE}"])
    win = green_windows(g1, g2, off)
    qmax = max(float(st.get(f"movement_queue_{m}", 0) or 0) for m in order) or 1.0
    for i, m in enumerate(order):
        s = mv[m]; ph = s.get("phase"); kind = str(s.get("kind", "internal"))
        onr = is_onramp(s)
        y = len(order) - 1 - i
        # cycle 배경(red) + green window
        ax.add_patch(Rectangle((0, y-0.35), CYCLE, 0.7, facecolor="#e74c3c", alpha=0.25, edgecolor="none"))
        for (a, b) in win.get(ph, []):
            ax.add_patch(Rectangle((a, y-0.35), b-a, 0.7, facecolor="#27ae60",
                                   edgecolor=("gold" if onr else "none"), lw=(2.5 if onr else 0)))
        # 큐 막대 (cycle 오른쪽에 별도 스케일)
        q = float(st.get(f"movement_queue_{m}", 0) or 0)
        ax.add_patch(Rectangle((CYCLE+8, y-0.3), 40*q/qmax, 0.6,
                               facecolor=KIND_COLOR.get(kind, "#7f7f7f"),
                               edgecolor=("gold" if onr else "k"), lw=(2.0 if onr else 0.4)))
        ax.text(CYCLE+8+40*q/qmax+2, y, f"{q:.0f}", va="center", fontsize=7)
        lab = f"{s.get('approach')}→{s.get('exit')}" + ("  [ON-RAMP]" if onr else "")
        ax.text(-4, y, lab, va="center", ha="right", fontsize=7,
                fontweight=("bold" if onr else "normal"),
                color=("#d62728" if onr else "black"))
    ax.set_xlim(-30, CYCLE+60); ax.set_ylim(-1, len(order))
    ax.set_yticks([]); ax.set_xlabel("cycle time (s)  |  green=GO, red=STOP  |  right bar = queue (veh)")
    ax.set_title(f"{lbl}  (node {NODE}: g_p1={g1:.0f}, g_p2={g2:.0f}, offset={off:.0f})", fontsize=10)
    ax.axvline(CYCLE, color="k", lw=0.5)
fig.suptitle(f"Perimeter intersection {NODE}: signal green-window + queue (demand_15, capdrop ON) — on-ramp movements highlighted (gold)", fontsize=11)
fig.tight_layout()
fig.savefig("reports/figures/fig_signal_timing_D_pfo_vs_pstack.png", dpi=130); plt.close(fig)
print("saved fig_signal_timing_D_pfo_vs_pstack.png |", len(order), "movements")
