# 논문 그림 공통 모듈 — Times New Roman 단일 axes, 5컨트롤러 스타일맵, 통용 시나리오명, 데이터 로더, NC기준 sanity gate
"""
사용법: 모든 그림 스크립트는
    import pubstyle as ps
    ps.sanity_gate()          # walk_mvg 5셀 NC대비 개선%를 표1과 재대조 (불일치 시 즉시 중단)
    fig, ax = ps.new_fig()
    ...
    ps.save(fig, "f_xxx_yyy") # analysis/figures/에 PDF + PNG(600dpi) 동시 저장

채점 규약:
  wTTT = cumulative_total_ttt[마지막 행] − cumulative_total_ttt[step==19 행 (웜업 20스텝 종료)]
  개선% = (NC_wTTT − wTTT)/NC_wTTT × 100  (표1과 동일한 NC 기준)
컨트롤러(2026-07-18 사용자 확정 5종): no control / wu / pfo (box) / p-stack(walk-MVG) / centralized.
무제한 PFO·sweet_200_w는 논문에서 제외.
"""
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless 필수
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- 경로
PKG = Path(__file__).resolve().parents[2]          # .../paper_package
DATA = PKG / "data"                                # 읽기 전용
FIGDIR = PKG / "analysis" / "figures"
TABDIR = PKG / "analysis" / "tables"
FIGDIR.mkdir(parents=True, exist_ok=True)
TABDIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 시간축 규약
STEP_MIN = 3.0            # 1 step = 180 s = 3 min
WARM_STEPS = 20           # step 0..19 = NC 웜업
WARM_END_MIN = WARM_STEPS * STEP_MIN   # 60 min
WARM_ROW = WARM_STEPS - 1              # wTTT 기준 행: step==19 (0-인덱스)

# ---------------------------------------------------------------- 셀 정의 (5셀, 200 제외)
CELLS = [
    "sweet_155_w", "sweet_170_w", "sweet_170_skew15_w",
    "sweet_170_incident_w", "sweet_190_w",
]
# 통용 시나리오명 (그림 축·범례·캡션·표에 사용)
SCEN_NAME = {
    "sweet_155_w": "Low demand",
    "sweet_170_w": "Med demand",
    "sweet_170_skew15_w": "Med demand (skewed)",
    "sweet_170_incident_w": "Med demand (incident)",
    "sweet_190_w": "High demand",
}

def scen(cell):
    """내부 셀명 → 통용 시나리오명."""
    return SCEN_NAME.get(cell, cell)

# NC 기준선 wTTT (표1 확정값) — 개선%·sanity의 분모
NC_REF = {
    "sweet_155_w": 8977, "sweet_170_w": 13028, "sweet_170_skew15_w": 13175,
    "sweet_170_incident_w": 9581, "sweet_190_w": 16518,
}
# walk-MVG NC대비 기대 개선% (sanity gate 목표치; offset price 편입판 2026-07-18)
EXPECTED_IMP = {
    "sweet_155_w": 81.22, "sweet_170_w": 79.40, "sweet_170_skew15_w": 79.76,
    "sweet_170_incident_w": 76.04, "sweet_190_w": 68.83,
}

# ---------------------------------------------------------------- 컨트롤러 (5종, 표시 순서)
CONTROLLERS = ["nc", "wu", "pfo_box", "pcent", "walk_mvg"]
LABEL = {
    "nc": "No control",
    "wu": "Wu",
    "pfo_box": "PFO (box)",
    "pcent": "Centralized",
    "walk_mvg": "P-Stack (walk-MVG)",
    # P-Stack 변형 — §3 처방사다리(기각 계보) 전용, 메인 비교엔 미사용
    "farsa_ref": "FAR-SA anchor",
    "pd4_ref": "PD4 (no box)",
    "box300_vsl10_ref": "BOX (no walk)",
}
# 고정 스타일맵 — 흑백 인쇄에서도 선종+명도로 구분. walk_mvg=주인공(검정 실선).
STYLE = {
    "nc":       dict(color="#66CCEE", linestyle=(0, (5, 1.5, 1, 1.5)), linewidth=1.0),
    "wu":       dict(color="#AA3377", linestyle=(0, (7, 3)),           linewidth=1.0),
    "pfo_box":  dict(color="#EE7733", linestyle="-.",                  linewidth=1.1),
    "pcent":    dict(color="#4477AA", linestyle=":",                   linewidth=1.4),
    "walk_mvg": dict(color="#000000", linestyle="-",                   linewidth=1.4),
    # 변형(예약)
    "farsa_ref":        dict(color="#4D4D4D", linestyle="--", linewidth=1.0),
    "pd4_ref":          dict(color="#228833", linestyle=":",  linewidth=1.1),
    "box300_vsl10_ref": dict(color="#CCBB44", linestyle="-.", linewidth=1.0),
}
# P-Stack 처방사다리 변형(§3d 기각계보/§5 전용)
PSTACK_VARIANTS = ["walk_mvg", "farsa_ref", "pd4_ref", "box300_vsl10_ref"]
ARMS = PSTACK_VARIANTS  # 하위호환 별칭(변형 비교 그림) — 메인 5컨트롤러는 CONTROLLERS

# ---------------------------------------------------------------- rcParams (import 시 적용)
_FONT = "Times New Roman"
_available = {f.name for f in fm.fontManager.ttflist}
if _FONT not in _available:
    warnings.warn(f"'{_FONT}' 폰트를 찾지 못했습니다 — serif 폴백 사용. 저널 제출 전 확인 필요.")
plt.rcParams.update({
    "font.family": _FONT,
    "mathtext.fontset": "stix",
    "font.size": 9,
    "axes.labelsize": 9.5,
    "axes.titlesize": 9.5,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.linewidth": 0.8,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "figure.figsize": (3.5, 2.4),   # 단일 컬럼 저널 그림
    "figure.dpi": 120,
    "savefig.dpi": 600,
    "pdf.fonttype": 42,             # TrueType 임베드 (저널 요구)
    "ps.fonttype": 42,
    "legend.frameon": True,
    "legend.framealpha": 0.9,
    "legend.edgecolor": "none",
    "legend.borderpad": 0.3,
    "legend.handlelength": 2.2,
})


# ---------------------------------------------------------------- 그림 유틸
def new_fig(width=3.5, height=2.4):
    """단일 axes 그림 생성 — subplot 금지 규약의 유일한 진입점."""
    fig, ax = plt.subplots(1, 1, figsize=(width, height))
    return fig, ax


def save(fig, name):
    """PDF(벡터) + PNG(600dpi) 동시 저장. name은 확장자 없는 파일명."""
    fig.tight_layout(pad=0.3)
    for ext in ("pdf", "png"):
        out = FIGDIR / f"{name}.{ext}"
        fig.savefig(out, bbox_inches="tight", pad_inches=0.02)
        print(f"  saved {out}")
    plt.close(fig)


def shade_warmup(ax):
    """NC 웜업(0–60 min) 음영 + 종료 경계선. 텍스트 라벨은 캡션 담당."""
    ax.axvspan(0.0, WARM_END_MIN, color="0.92", zorder=0, linewidth=0)
    ax.axvline(WARM_END_MIN, color="0.6", linewidth=0.6, linestyle=(0, (2, 2)), zorder=1)


def time_axis(ax, tmax_min=180.0):
    """x축을 분 단위로 표준화 (30분 눈금)."""
    ax.set_xlim(0, tmax_min)
    ax.set_xticks(np.arange(0, tmax_min + 1, 30))
    ax.set_xlabel("Time (min)")


def minutes(steps):
    """step 인덱스(0-기반) → 분."""
    return np.asarray(steps, dtype=float) * STEP_MIN


def style(arm):
    """컨트롤러/변형 스타일 dict + label 반환용 헬퍼."""
    return dict(STYLE.get(arm, dict(color="0.3", linestyle="-", linewidth=1.0)),
                label=LABEL.get(arm, arm))


# ---------------------------------------------------------------- 데이터 로더
_cache = {}


def load(arm, cell, kind, usecols=None):
    """data/<arm>/<cell>/<kind>.csv 로드 (읽기 전용, 캐시)."""
    key = (arm, cell, kind, tuple(usecols) if usecols else None)
    if key not in _cache:
        _cache[key] = pd.read_csv(DATA / arm / cell / f"{kind}.csv", usecols=usecols)
    return _cache[key]


# ---------------------------------------------------------------- 채점
def wttt(run_log):
    """wTTT = cum_total_ttt[마지막] − cum_total_ttt[step==WARM_ROW]. 단위 veh·h."""
    cum = run_log["cumulative_total_ttt"]
    base = run_log.loc[run_log["step"] == WARM_ROW, "cumulative_total_ttt"].iloc[0]
    return float(cum.iloc[-1] - base)


def improvement(arm, cell):
    """NC 대비 개선% (표1 규약)."""
    rl = load(arm, cell, "run_log", usecols=["step", "cumulative_total_ttt"])
    return (NC_REF[cell] - wttt(rl)) / NC_REF[cell] * 100.0


def sanity_gate(tol=0.05, verbose=True):
    """walk_mvg 5셀 NC대비 개선%를 표1 목표치와 대조. 불일치 시 SystemExit."""
    fails = []
    for cell in CELLS:
        imp = improvement("walk_mvg", cell)
        if abs(imp - EXPECTED_IMP[cell]) >= tol:
            fails.append(f"{cell}: got {imp:+.2f}% expected {EXPECTED_IMP[cell]:+.2f}%")
    if fails:
        raise SystemExit("SANITY GATE FAIL — 채점 규약/데이터 불일치:\n  " + "\n  ".join(fails))
    if verbose:
        print("sanity gate PASS (walk_mvg 5/5 cells match expected NC-relative improvement)")
