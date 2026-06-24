# leader 벌점/목적함수 진단용 4개 그림: objective 성분분해·ρ vs ρ_crit·urban vs half-cap·freeway capacity-drop(한계비용) (heavy1.50, 4 controllers)
"""사용자 요청 4개 그림. heavy_demand_150, 컨트롤러 4종(no-control + WU-CD-F + PFO + P-Stack).

A. objective 성분분해(누적 stacked): freeway TTT + urban TTT + half-cap penalty + density penalty.
B. ρ(실제 freeway 밀도) vs ρ_crit 같이 (excess 아님).
C. urban movement 큐(실제) vs half-cap(0.5·cap) 라인 같이 (excess 아님).
D. freeway flow–density 기본도 + ρ_crit: capacity-drop = "차 1대 더의 한계비용" 기전.
   (TTT는 차량수×Δt라 vehicle-hour당 비용은 두 서브시스템이 동일 -> 차이는 freeway flow 붕괴에서 옴.)

실행: PYTHONPATH=<repo> python -B 2026-06-24/diag_scripts/penalty_analysis_figs.py
"""
from __future__ import annotations

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.models.state import ExperimentConfig
from src.models.urban_queue_model import movement_storage_capacity

plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["mathtext.fontset"] = "stix"

BASE = "outputs/analysis_matrix_3600_extra/runs/heavy_demand_150"
OUT = "reports/figures"
os.makedirs(OUT, exist_ok=True)
CTRL = ["NO-CONTROL", "WU-CD-F", "PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG"]
CLAB = {"NO-CONTROL": "no-control", "WU-CD-F": "WU-CD-F",
        "PROPOSED-FOLLOWERS-ONLY": "PFO", "PROPOSED-STACKELBERG": "P-Stack"}
COL = {"NO-CONTROL": "#7f7f7f", "WU-CD-F": "#ff7f0e",
       "PROPOSED-FOLLOWERS-ONLY": "#1f77b4", "PROPOSED-STACKELBERG": "#d62728"}

cfg = ExperimentConfig.from_file("src/config/default.yaml")
net = cfg.network
RHO_CRIT = float(net.rho_crit)
TCH = float(cfg.simulation.T_c_h)
THR = float(cfg.leader.mfd_storage_threshold_ratio)
BCAP = float(cfg.leader.mfd_boundary_queue_capacity_veh)
W_MFD = float(cfg.leader.mfd_storage_weight)
W_F = float(cfg.leader.w_F)
SEG_L = float(net.freeway_segment_length_km)
LANES = float(net.freeway_lanes)
SEGS = int(net.freeway_segments_per_link)
FW_LINKS = list(net.freeway_links)

# half-cap 용량 맵(leader _urban_halfcap_excess와 동일): boundary는 220, 그 외는 movement 저장용량.
CAP = {m: (BCAP if str(s.get("kind", "")) in {"boundary_in", "boundary_out"}
           else max(float(movement_storage_capacity(cfg, m, s)), 1e-9))
       for m, s in net.urban_movements.items()}
HALFCAP_TOTAL = sum(THR * c for c in CAP.values())
FULLCAP_TOTAL = sum(CAP.values())


def rd(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fl(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def state(c):
    return rd(f"{BASE}/{c}/state_timeseries.csv")


def prog(c):
    return rd(f"{BASE}/{c}/progress_summary.csv")


def tmin(n):
    return [i * 3 for i in range(n)]


def halfcap_excess_series(st):
    """실제 state별 movement half-cap 초과분(veh)."""
    return [sum(max(0.0, fl(r.get(f"movement_queue_{m}")) - THR * cap) for m, cap in CAP.items()) for r in st]


def urban_queue_series(st):
    """실제 state별 urban movement 총 큐(veh) — half-cap 라인과 비교용."""
    return [sum(fl(r.get(f"movement_queue_{m}")) for m in CAP) for r in st]


def density_excess_series(st):
    """state별 freeway density 초과분 합(차량) — 링크평균 ρ 근사(per-segment 미로깅)."""
    out = []
    for r in st:
        ex = 0.0
        for link in FW_LINKS:
            rho = fl(r.get(f"rho_{link}_mean"))
            ex += SEGS * SEG_L * LANES * max(0.0, rho - RHO_CRIT)
        out.append(ex)
    return out


def cumsum(xs):
    out, s = [], 0.0
    for x in xs:
        s += x
        out.append(s)
    return out


# ---------- A. objective 성분분해 (누적 stacked, 2x2) ----------
fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True, sharey=True)
for ax, c in zip(axes.ravel(), CTRL):
    st, pg = state(c), prog(c)
    n = len(st)
    t = tmin(n)
    cum_fw = [fl(r.get("cumulative_freeway_ttt")) for r in pg]
    cum_ur = [fl(r.get("cumulative_urban_ttt")) for r in pg]
    cum_hc = cumsum([e * W_MFD * TCH for e in halfcap_excess_series(st)])
    cum_de = cumsum([e * W_F * TCH for e in density_excess_series(st)])
    m = min(len(t), len(cum_fw), len(cum_ur), len(cum_hc), len(cum_de))
    ax.stackplot(t[:m], cum_fw[:m], cum_ur[:m], cum_hc[:m], cum_de[:m],
                 labels=["freeway TTT", "urban TTT", "half-cap penalty", "density penalty"],
                 colors=["#d62728", "#1f77b4", "#9467bd", "#2ca02c"], alpha=0.85)
    ax.set_title(CLAB[c], fontsize=11)
    ax.grid(True, alpha=0.3)
axes[0, 0].legend(fontsize=8, loc="upper left")
for ax in axes[1, :]:
    ax.set_xlabel("time (min)")
for ax in axes[:, 0]:
    ax.set_ylabel("cumulative objective (veh·h)")
fig.suptitle("Leader-objective decomposition (cumulative) — heavy1.50", fontsize=12)
fig.tight_layout()
fig.savefig(f"{OUT}/figA_objective_decomp.png", dpi=130)
plt.close(fig)

# ---------- B. ρ vs ρ_crit ----------
fig, ax = plt.subplots(figsize=(7.8, 4.4))
for c in CTRL:
    st = state(c)
    n = len(st)
    rho_mean = [sum(fl(r.get(f"rho_{l}_mean")) for l in FW_LINKS) / len(FW_LINKS) for r in st]
    ax.plot(tmin(n), rho_mean, label=CLAB[c], color=COL[c], marker="o", ms=2)
ax.axhline(RHO_CRIT, color="k", ls="--", lw=1.0, label=r"$\rho_{\mathrm{crit}}=%.1f$" % RHO_CRIT)
ax.set_xlabel("time (min)")
ax.set_ylabel(r"freeway density $\rho$ (veh/km/lane, link-mean)")
ax.set_title(r"Freeway density vs $\rho_{\mathrm{crit}}$ — heavy1.50")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/figB_rho_vs_crit.png", dpi=130)
plt.close(fig)

# ---------- C. urban 큐 vs half-cap 라인 ----------
fig, ax = plt.subplots(figsize=(7.8, 4.4))
for c in CTRL:
    st = state(c)
    ax.plot(tmin(len(st)), urban_queue_series(st), label=CLAB[c], color=COL[c], marker="o", ms=2)
ax.axhline(HALFCAP_TOTAL, color="k", ls="--", lw=1.0, label=r"half-cap ($0.5\sum$cap)=%.0f" % HALFCAP_TOTAL)
ax.axhline(FULLCAP_TOTAL, color="k", ls=":", lw=1.0, label=r"full cap ($\sum$cap)=%.0f" % FULLCAP_TOTAL)
ax.set_xlabel("time (min)")
ax.set_ylabel("total urban movement queue (veh)")
ax.set_title("Urban movement storage vs half-cap line — heavy1.50")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/figC_urban_vs_halfcap.png", dpi=130)
plt.close(fig)

# ---------- D. freeway flow–density 기본도 (METANET 평형 FD 혼잡 가지 = 한계비용 기전) ----------
# 주의: METANET 평형 FD는 단일값이라 hysteresis loop가 없다 -> 이건 breakdown capacity drop이
# 아니라 "과포화(혼잡) 가지"다. flow가 rho_crit 이후 감소 -> 방출 저하 -> 누적 증폭 -> veh·h 증가.
fig, ax = plt.subplots(figsize=(7.8, 4.4))
for c in CTRL:
    st = state(c)
    xs, ys = [], []
    for r in st:
        for link in FW_LINKS:
            rho = fl(r.get(f"rho_{link}_mean"))
            spd = fl(r.get(f"speed_{link}_mean"))
            xs.append(rho)
            ys.append(rho * spd * LANES)  # flow = 밀도×속도×차로 (veh/h)
    ax.scatter(xs, ys, label=CLAB[c], color=COL[c], s=18, alpha=0.7)
ax.axvline(RHO_CRIT, color="k", ls="--", lw=1.0, label=r"$\rho_{\mathrm{crit}}=%.1f$" % RHO_CRIT)
ax.set_xlabel(r"freeway density $\rho$ (veh/km/lane)")
ax.set_ylabel("freeway flow (veh/h)")
ax.set_title("METANET equilibrium FD: congested branch past " + r"$\rho_{\mathrm{crit}}$ (single-valued, no hysteresis) — heavy1.50")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/figD_freeway_fd.png", dpi=130)
plt.close(fig)

print("DONE figs:", [f for f in os.listdir(OUT) if f.startswith(("figA", "figB", "figC", "figD"))])
print(f"half-cap total={HALFCAP_TOTAL:.0f}  full cap={FULLCAP_TOTAL:.0f}  rho_crit={RHO_CRIT}")
