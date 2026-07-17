# 논문 그림 공통 모듈 — Times New Roman 단일 axes 스타일, 컨트롤러 스타일맵, 데이터 로더, wTTT 채점·sanity gate
"""
사용법: 모든 그림 스크립트는
    import pubstyle as ps
    ps.sanity_gate()          # §0.4 PFO 기준선 대비 walk_mvg 개선% 재계산 검증 (불일치 시 즉시 중단)
    fig, ax = ps.new_fig()
    ...
    ps.save(fig, "f_xxx_yyy") # analysis/figures/에 PDF + PNG(600dpi) 동시 저장

채점 규약 (ANALYSIS_PLAN_FINAL.md §0.3):
  wTTT = cumulative_total_ttt[마지막 행] − cumulative_total_ttt[웜업 종료 행]
  ★주의: run_log의 step 컬럼은 0-인덱스(0..59). 계획서의 "step==20 행"은 1-기반 서술이며,
  실제 웜업 종료 행은 step==19 (0..19 = NC 웜업 20스텝, 채점창 = step 20..59).
  이 해석으로 6셀 전부 §0.2 기대 개선%와 소수 2자리까지 일치함을 sanity_gate()가 보증.
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
WARM_ROW = WARM_STEPS - 1              # wTTT 기준 행: step==19 (0-인덱스, 웜업 20스텝 누적치)

# ---------------------------------------------------------------- 셀/팔 정의
CELLS = [
    "sweet_155_w", "sweet_170_w", "sweet_170_skew15_w",
    "sweet_170_incident_w", "sweet_190_w", "sweet_200_w",
]
# §0.4 PFO 수치 기준선 (정수 반올림)
PFO_REF = {
    "sweet_155_w": 1776, "sweet_170_w": 3021, "sweet_170_skew15_w": 2957,
    "sweet_170_incident_w": 2367, "sweet_190_w": 5689, "sweet_200_w": 7196,
}
# §0.2 walk-MVG 기대 개선% (sanity gate 목표치)
EXPECTED_IMP = {
    "sweet_155_w": 5.10, "sweet_170_w": 11.14, "sweet_170_skew15_w": 9.81,
    "sweet_170_incident_w": 3.03, "sweet_190_w": 9.38, "sweet_200_w": -20.68,
}

ARMS = ["walk_mvg", "farsa_ref", "pd4_ref", "box300_vsl10_ref"]
LABEL = {
    "walk_mvg": "walk-MVG (P-Stack)",
    "farsa_ref": "FAR-SA anchor",
    "pd4_ref": "PD4 (no box)",
    "box300_vsl10_ref": "BOX (no walk)",
    "nc": "NC",
    "pfo": "PFO",
}
# 고정 컨트롤러 스타일맵 — 전 그림 공통. 흑백 인쇄에서도 선종+명도로 구분되도록 설계.
STYLE = {
    "walk_mvg":         dict(color="#000000", linestyle="-",  linewidth=1.3),
    "farsa_ref":        dict(color="#4D4D4D", linestyle="--", linewidth=1.1),
    "pd4_ref":          dict(color="#4477AA", linestyle=":",  linewidth=1.4),
    "box300_vsl10_ref": dict(color="#EE7733", linestyle="-.", linewidth=1.1),
    # 예약 (런 도착 후 사용) — NC / PFO
    "nc":  dict(color="#66CCEE", linestyle=(0, (5, 1.5, 1, 1.5, 1, 1.5)), linewidth=1.1),
    "pfo": dict(color="#AA3377", linestyle=(0, (7, 3)), linewidth=1.1),
}

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
    "legend.frameon": True,         # 곡선 위에 얹혀도 읽히도록 흰 배경
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
    """NC 웜업(0–60 min) 음영 + 종료 경계선. 텍스트 라벨은 캡션 담당(충돌 방지)."""
    ax.axvspan(0.0, WARM_END_MIN, color="0.92", zorder=0, linewidth=0)
    ax.axvline(WARM_END_MIN, color="0.6", linewidth=0.6, linestyle=(0, (2, 2)), zorder=1)


def time_axis(ax, tmax_min=180.0):
    """x축을 분 단위로 표준화 (30분 눈금)."""
    ax.set_xlim(0, tmax_min)
    ax.set_xticks(np.arange(0, tmax_min + 1, 30))
    ax.set_xlabel("Time (min)")


def minutes(steps):
    """step 인덱스(0-기반) → 분. step s의 제어는 [3s, 3(s+1)) min 구간에 적용."""
    return np.asarray(steps, dtype=float) * STEP_MIN


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


def sanity_gate(tol=0.005, verbose=True):
    """walk_mvg 6셀 개선%를 §0.4 기준선으로 재계산해 §0.2 목표치와 소수 2자리 일치 검증.
    불일치 시 SystemExit — 그림 생성 전 반드시 호출."""
    fails = []
    for cell in CELLS:
        rl = load("walk_mvg", cell, "run_log", usecols=["step", "cumulative_total_ttt"])
        imp = (PFO_REF[cell] - wttt(rl)) / PFO_REF[cell] * 100.0
        if abs(imp - EXPECTED_IMP[cell]) >= tol:
            fails.append(f"{cell}: got {imp:+.2f}% expected {EXPECTED_IMP[cell]:+.2f}%")
    if fails:
        raise SystemExit("SANITY GATE FAIL — 채점 규약/데이터 불일치:\n  " + "\n  ".join(fails))
    if verbose:
        print("sanity gate PASS (walk_mvg 6/6 cells match expected improvement to 2 dp)")
