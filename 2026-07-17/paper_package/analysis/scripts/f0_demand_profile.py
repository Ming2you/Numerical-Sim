# §0 그림: 6셀 수요 스케일 프로파일(사다리꼴 펄스) + 사고 구간 음영 — demand.py 식을 그대로 재현
"""f0_demand_profile — 수치 출처(발명 금지):
  - 사다리꼴 펄스: src/models/demand.py:192-210 (_pulse_fraction), :257-264
      (effective scale = base + (class-base)·pulse(t), 펄스 모드에선 내장 sine 피크 OFF).
  - 6셀 공통 타이밍: scenarios.yaml (sweet_*_w) — base 0.5, start 3600 s, ramp-up 300 s,
      plateau 3600 s, ramp-down 300 s  → 플래토 = [3900, 7500] s = [65, 125] min.
  - class scale: 155_w 1.55 / 170_w·170_skew15_w·170_incident_w 1.70 / 190_w 1.90 / 200_w 2.00
      (urban=freeway=ramp 동일 배율).
  - 사고(170_incident_w): FW_E seg 6, 2차로 중 1차로 폐쇄, [4500, 6300) s = [75, 105) min
      (scenarios.yaml sweet_170_incident_w; metanet.py:244-245 유효차로 감산).
  - 채점 규약: T=10800 s(60스텝×180 s), NC 웜업 step 0..19(0-60 min) — ANALYSIS_PLAN §0.3.
"""
import numpy as np

import pubstyle as ps

BASE = 0.5
START, UP, PLATEAU, DOWN = 3600.0, 300.0, 3600.0, 300.0
T_TOTAL = 10800.0
INCIDENT = (4500.0, 6300.0)  # sweet_170_incident_w, FW_E seg6, 1/2 lanes

CURVES = [  # (class scale, label, gray level)
    (1.55, "×1.55 (155_w)", "0.72"),
    (1.70, "×1.70 (170_w / skew15 / incident)", "0.50"),
    (1.90, "×1.90 (190_w)", "0.28"),
    (2.00, "×2.00 (200_w)", "0.0"),
]


def pulse(t):
    """demand.py:192-210의 사다리꼴 pulse(t)∈[0,1]을 벡터로 재현."""
    t = np.asarray(t, dtype=float)
    out = np.zeros_like(t)
    rise = (t > START) & (t <= START + UP)
    out[rise] = (t[rise] - START) / UP
    out[(t > START + UP) & (t <= START + UP + PLATEAU)] = 1.0
    fall = (t > START + UP + PLATEAU) & (t <= START + UP + PLATEAU + DOWN)
    out[fall] = 1.0 - (t[fall] - START - UP - PLATEAU) / DOWN
    return out


def main():
    ps.sanity_gate()
    fig, ax = ps.new_fig()
    ps.shade_warmup(ax)
    # 사고 구간(170_incident_w 한정) 음영
    ax.axvspan(INCIDENT[0] / 60.0, INCIDENT[1] / 60.0, color="#AA3377",
               alpha=0.10, zorder=0, linewidth=0)
    ax.text((INCIDENT[0] + INCIDENT[1]) / 120.0, 0.56,
            "incident (170_incident_w):\nFW_E seg 6, 1/2 lanes,\n75–105 min",
            ha="center", va="bottom", fontsize=6.0, color="#AA3377")

    t = np.linspace(0.0, T_TOTAL, 2161)
    for scale, label, gray in CURVES:
        eff = BASE + (scale - BASE) * pulse(t)
        ax.plot(t / 60.0, eff, color=gray, linewidth=1.2, label=label)

    ps.time_axis(ax)
    ax.set_ylim(0.0, 2.95)
    ax.set_ylabel("Demand scale (× nominal base rates)")
    ax.legend(loc="upper left", fontsize=6.2, borderaxespad=0.4)
    ps.save(fig, "f0_demand_profile")


if __name__ == "__main__":
    main()
