# 손튜닝 성분(예: leader hinge, 예산 등식/부등식)의 단독 기여를 짧은 닫힌루프 셀로 측정하는 카나리아 스크립트
"""이벤트 트리거 오프라인 감사 도구(plant/무대 변경 시 1회 실행) — 상시 안전장치 아님
(상시 안전은 β̂ 표류·regret guard가 담당). 부품 기여의 부호는 short-horizon에서 판정
가능, replay 채점은 metering 판정을 속이므로(07-08 교훈) 닫힌 루프 단축만 허용.

사용 예:
  <PY> -B work/component_canary.py --scenario sweet_155 --T-total 3600 \
      [--controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT]

각 토글 셀은 subprocess로 work/run_claude_style_five_controller.py를 호출하고
(outputs/_canary/<scenario>/<tag>), summary.json의 total_ttt로 한국어 기여 표를 출력한다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "work" / "run_claude_style_five_controller.py"

# (성분 이름, 기준 대비 추가 env, 설명) — 모든 셀은 SEG13=1 공통.
#   baseline        : SEG13=1만(현행 기본 구성 = hinge ON, 예산 equality).
#   LEADER_HINGE=0  : leader hinge 채점 해제 → Δ = hinge의 단독 기여.
#   SEG13_INEQ=1    : 예산 등식→부등식(Σmeter ≤ budget) → Δ = 등식 구속의 단독 기여.
TOGGLES = [
    ("baseline", {}),
    ("hinge_off", {"LEADER_HINGE": "0"}),
    ("ineq_on", {"SEG13_INEQ": "1"}),
]


def run_cell(tag: str, extra_env: dict, scenario: str, t_total: float, controller: str) -> float:
    """토글 셀 1개 실행(이미 결과가 있으면 재사용) 후 total_ttt 반환."""
    out_dir = ROOT / "outputs" / "_canary" / scenario / tag
    summary_path = out_dir / "summary.json"
    if not summary_path.exists():
        env = dict(os.environ)
        env["SEG13"] = "1"
        env.update(extra_env)
        cmd = [
            sys.executable, "-B", str(RUNNER),
            "--scenario", scenario,
            "--T-total", str(t_total),
            "--controllers", controller,
            "--output", str(out_dir),
        ]
        print(f"[카나리아] {tag} 실행: {' '.join(cmd)} (env: SEG13=1 {extra_env})", flush=True)
        subprocess.run(cmd, cwd=str(ROOT), env=env, check=True)
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("controller_id") == controller:
            return float(row["total_ttt"])
    raise RuntimeError(f"{summary_path}에 {controller} 요약이 없음")


def main() -> None:
    parser = argparse.ArgumentParser(description="성분 카나리아(닫힌루프 단축 감사)")
    parser.add_argument("--scenario", default="sweet_155")
    parser.add_argument("--T-total", type=float, default=3600.0)
    parser.add_argument("--controllers", default="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT")
    args = parser.parse_args()

    controller = args.controllers.split(",")[0].strip()
    ttt = {}
    for tag, extra_env in TOGGLES:
        ttt[tag] = run_cell(tag, extra_env, args.scenario, args.T_total, controller)

    base = ttt["baseline"]
    # 표: 성분 | ON TTT(기준) | OFF/ALT TTT(변형) | 기여 Δ(변형−기준) | 부호.
    # Δ>0 = 변형이 더 나쁨 = 성분(기준 구성)이 개선에 기여. Δ<0 = 성분이 해로움.
    rows = [
        ("leader_hinge", base, ttt["hinge_off"], ttt["hinge_off"] - base),
        ("budget_equality(vs INEQ)", base, ttt["ineq_on"], ttt["ineq_on"] - base),
    ]
    print()
    print(f"=== 성분 카나리아: {args.scenario} T={args.T_total:.0f}s {controller} ===")
    header = f"{'성분':<26} | {'ON TTT':>10} | {'OFF/ALT TTT':>11} | {'기여(Δ)':>10} | 부호"
    print(header)
    print("-" * len(header))
    for name, on_v, off_v, delta in rows:
        sign = "개선 기여(+)" if delta > 0 else ("악화(−)" if delta < 0 else "중립(0)")
        print(f"{name:<26} | {on_v:>10.1f} | {off_v:>11.1f} | {delta:>+10.1f} | {sign}")
    print()
    print("주의: short-horizon 닫힌루프 판정 — 부호 판정용이며 크기는 풀-horizon과 다를 수 있음.")


if __name__ == "__main__":
    main()
