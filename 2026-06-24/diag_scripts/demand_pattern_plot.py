# 6개 제안 시나리오의 시간별 수요(freeway/urban/ramp) 패턴 플롯 — 설계 검증용(일부는 scenarios.yaml 미반영, 제안값 기준)
"""제안 6 시나리오의 demand-over-time을 시나리오별 패널로 그린다.

- 기존형(half-sine peak=1+0.22·sin(πx))은 실제 DemandProfile로 계산.
- transient_surge는 신규 temporal profile(낮은 baseline→볼록 상승→회복)로, DemandProfile 출력에서
  half-sine 성분을 나눠내고 surge 배수를 곱해 표현(수요는 peak 배수에 선형이므로 정확).
- skew는 공간 재분배(총량 보존)라 시간별 총수요는 peak×1.4와 동일 → 패널에 명시.

실행: PYTHONPATH=<repo> python -B 2026-06-24/diag_scripts/demand_pattern_plot.py
"""
from __future__ import annotations

import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.models.state import ExperimentConfig
from src.models.demand import ScenarioConfig, DemandProfile

plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["mathtext.fontset"] = "stix"

OUT = "reports/figures"
os.makedirs(OUT, exist_ok=True)
cfg = ExperimentConfig.from_file("src/config/default.yaml")
T = cfg.simulation.T_total


def halfsine(x: float) -> float:
    return 1.0 + 0.22 * math.sin(math.pi * min(max(x, 0.0), 1.0))


def surge(x: float) -> float:
    # 낮은 baseline(0.6, capacity 아래 의도) → 볼록 상승(~1.7, 위) → 회복(0.6).
    return 0.6 + 1.1 * math.exp(-((x - 0.45) / 0.13) ** 2)


# (제목, ScenarioConfig, temporal-profile, 비고)
PEAK = dict(urban_scale=1.25, freeway_scale=1.20, ramp_scale=1.25)
PEAK14 = {k: v * 1.4 for k, v in PEAK.items()}
SCENARIOS = [
    ("peak", ScenarioConfig(name="peak", **PEAK), "halfsine", ""),
    ("peak × 1.4", ScenarioConfig(name="peak140", **PEAK14), "halfsine", ""),
    ("transient surge", ScenarioConfig(name="surge", urban_scale=1.3, freeway_scale=1.25, ramp_scale=1.3),
     "surge", "low->bump->recover (crosses capacity)"),
    ("freeway-heavy", ScenarioConfig(name="fwheavy", urban_scale=1.0, freeway_scale=1.6, ramp_scale=1.1),
     "halfsine", ""),
    ("urban-heavy", ScenarioConfig(name="urheavy", urban_scale=1.6, freeway_scale=1.0, ramp_scale=1.1),
     "halfsine", ""),
    ("skew @ peak x1.4", ScenarioConfig(name="skew", urban_boundary_weight_override={"in_C_top": 2.5, "in_C_right": 2.5, "in_F_right": 2.5}, **PEAK14),
     "halfsine", "spatial skew (total = peak x1.4)"),
]

n_steps = 80
xs = [i / (n_steps - 1) for i in range(n_steps)]
tmin = [x * T / 60.0 for x in xs]

fig, axes = plt.subplots(2, 3, figsize=(14, 7.5), sharex=True)
ymax = 0.0
panels = []
for (title, scn, prof, note), ax in zip(SCENARIOS, axes.ravel()):
    dp = DemandProfile(cfg, scn)
    fw, ur, rp = [], [], []
    for x in xs:
        d = dp.at(x * T)  # DemandProfile은 halfsine(peak) 포함
        scale = (surge(x) / halfsine(x)) if prof == "surge" else 1.0
        fw.append(sum(d.freeway_mainline.values()) * scale)
        ur.append(sum(d.urban_boundary.values()) * scale)
        rp.append(sum(d.ramp_arrival.values()) * scale)
    ax.plot(tmin, fw, label="freeway mainline", color="#d62728", lw=2)
    ax.plot(tmin, ur, label="urban boundary", color="#1f77b4", lw=2)
    ax.plot(tmin, rp, label="ramp", color="#2ca02c", lw=2)
    ttl = title + (f"\n({note})" if note else "")
    ax.set_title(ttl, fontsize=10)
    ax.grid(True, alpha=0.3)
    ymax = max(ymax, max(fw), max(ur), max(rp))
    panels.append(ax)

for ax in panels:
    ax.set_ylim(0, ymax * 1.05)
for ax in axes[1, :]:
    ax.set_xlabel("time (min)")
for ax in axes[:, 0]:
    ax.set_ylabel("demand (veh/h, total)")
axes[0, 0].legend(fontsize=8, loc="upper right")
fig.suptitle("Proposed 6 scenarios — demand over time (design draft)", fontsize=12)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_demand_patterns.png", dpi=130)
plt.close(fig)
print("saved:", f"{OUT}/fig_demand_patterns.png", "| ymax=%.0f" % ymax)
