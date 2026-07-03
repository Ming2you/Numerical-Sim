# [진단 probe] leader-계산가능 per-signal marginal price로 국소 green argmin을 truth로 이동시키는지 검증
"""Step-B1 marginal-price probe (SPEC 참조: _stepB_probe).

Step A는 downstream S_eff 정보채널(oracle)이 국소 argmin을 truth로 못 옮김을 보였다
(0/15). 이 probe는 **가격 채널**을 검증한다: leader가 유한차분으로 계산 가능한 per-signal
marginal price g_i = d(전역 horizon TTT)/dp1 를 구해, 국소 own-TTS 비용에 선형 가격항을
더한 priced_cost의 argmin이 truth/legacy 쪽으로 이동하는지 본다.

두 가격 변형을 함께 계산한다:
  - full        : g_i = d(전역 TTT)/dp1 (자기 own-TTS 변화분 포함).
  - externality : g_ext_i = g_i - d(local_cost)/dp1  (Pigouvian, 이중계상 제거).

Step A 하네스(work/step_a_oracle_probe.py)의 cfg/replay/score/truth 함수를 그대로 재사용한다.

CLI:
  python -B work/step_b_marginal_price_probe.py --scenario sweet_190 \
      --legacy-trace <control_timeseries.csv> --steps 20,26,35 --output outputs/_stepB_probe
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.demand import DemandProfile
from src.models.state import ControlAction
from src.controllers.wu_faithful_follower import WuFaithfulFollower

from work.step_a_oracle_probe import (
    build_cfg,
    load_legacy_controls,
    replay_to_step,
    score_candidate,
    truth_horizon_ttt,
)

# 유한차분 스텝(후보 linspace 간격 ~6초 수준)과 가격 가중치 스윕.
DELTA = 6.0
W_SWEEP = [0.0, 0.5, 1.0, 2.0]
# step_a JSON 재현 대조 시 부동소수 허용오차.
REPRO_TOL = 1e-6


def _argmin_p1(pairs: List[tuple]) -> float:
    """[(p1, cost), ...]에서 최소 cost의 p1 반환."""
    return min(pairs, key=lambda t: t[1])[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="sweet_190")
    ap.add_argument("--legacy-trace", required=True)
    ap.add_argument("--steps", default="20,26,35")
    ap.add_argument("--output", default="outputs/_stepB_probe")
    args = ap.parse_args()

    steps = [int(x) for x in str(args.steps).split(",") if str(x).strip() != ""]
    out_dir = ROOT / args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg, scenario = build_cfg(args.scenario)
    profile = DemandProfile(cfg, scenario)
    controls = load_legacy_controls(cfg, args.legacy_trace)
    horizon = max(1, cfg.mpc.horizon_steps)
    net = cfg.network
    green_min = float(net.green_min)
    green_max = float(net.green_max)

    follower = WuFaithfulFollower(cfg)

    # step_a JSON(있으면) 로드 → local_cost/truth_ttt 재현 대조.
    stepa_path = ROOT / "outputs" / "_stepA_probe" / "step_a_results.json"
    stepa = None
    if stepa_path.exists():
        stepa = json.load(open(stepa_path))
        print(f"[repro] loaded step_a JSON: {stepa_path}", flush=True)
    else:
        print(f"[repro] step_a JSON not found at {stepa_path} (skip repro check)", flush=True)

    def clamp(v: float) -> float:
        return max(green_min, min(green_max, float(v)))

    results: Dict[str, object] = {
        "scenario": args.scenario,
        "legacy_trace": str(args.legacy_trace),
        "horizon_steps": horizon,
        "delta": DELTA,
        "w_sweep": W_SWEEP,
        "steps": {},
    }

    # 집계 카운터: (w, variant) -> truth로 이동한 신호-step 수.
    moved_full: Dict[float, int] = {w: 0 for w in W_SWEEP}
    moved_ext: Dict[float, int] = {w: 0 for w in W_SWEEP}
    n_total = 0
    sign_pred_hits = 0     # B0 부호예측(A/C<0, D/F>0)과 일치한 신호-step 수
    sign_pred_total = 0    # A/C/D/F만 카운트(B는 예측 없음)

    repro_local_max = 0.0
    repro_truth_max = 0.0

    print(f"=== Step-B1 marginal-price probe  scenario={args.scenario}  "
          f"horizon={horizon}  delta={DELTA} ===", flush=True)

    for k in steps:
        if any((k + j) not in controls for j in range(horizon)):
            print(f"SKIP step {k}: legacy control missing in horizon window.", flush=True)
            continue

        state_k = replay_to_step(cfg, profile, controls, k)
        demand_k = profile.at(state_k.time_sec)

        # follower _solve_followers 프롤로그 미러(step_a와 동일).
        control = ControlAction.uncontrolled(cfg)
        control.green_times = dict(controls[k].green_times)
        control.offsets = dict(controls[k].offsets)
        control.vsl = dict(controls[k].vsl)
        control.ramp_metering = dict(controls[k].ramp_metering)
        control.inflow_outflow_allocation = {}
        coupling = follower._wu._coupling(state_k, control, demand_k)
        s_eff_frozen = follower._frozen_s_eff(state_k)
        reservoir_drain = follower._frozen_reservoir_drain(state_k, control, demand_k)
        freeway_congestion = follower._frozen_freeway_congestion(state_k)
        snapshot = ControlAction(
            ramp_metering=dict(control.ramp_metering),
            vsl=dict(control.vsl),
            green_times=dict(control.green_times),
            offsets=dict(control.offsets),
            inflow_outflow_allocation={},
        )

        print(f"\n--- step {k} (t={state_k.time_sec:.0f}s) ---", flush=True)
        header = (f"{'sig':>3} {'legacy':>6} {'local':>6} {'truth':>6} "
                  f"{'g_i':>9} {'dloc':>8} {'g_ext':>9} {'sgn?':>4} "
                  f"{'pF@1':>6} {'pE@1':>6} {'mvF':>4} {'mvE':>4}")
        print(header, flush=True)

        step_out: Dict[str, object] = {}
        for signal in net.signals:
            candidates = follower._urban_green_candidates(signal, state_k, coupling, snapshot)
            legacy_p1 = float(controls[k].green_times.get(
                f"{signal}_p1", net.effective_green_total / 2.0))
            p1_0 = clamp(legacy_p1)

            # 후보별 국소/truth 곡선.
            local_curve: List[tuple] = []
            truth_curve: List[tuple] = []
            for p1 in candidates:
                lc = score_candidate(
                    follower, signal, p1, state_k, coupling, s_eff_frozen,
                    reservoir_drain, freeway_congestion, snapshot, demand_k, None,
                )
                tt = truth_horizon_ttt(cfg, profile, controls, state_k, k, signal, p1)
                local_curve.append((float(p1), float(lc)))
                truth_curve.append((float(p1), float(tt)))

            local_argmin = _argmin_p1(local_curve)
            truth_argmin = _argmin_p1(truth_curve)

            # --- step_a JSON 재현 대조 (같은 후보 p1의 frozen_cost/truth_ttt와 비교) ---
            if stepa is not None:
                sa = stepa.get("steps", {}).get(str(k), {}).get(signal)
                if sa is not None:
                    sa_map = {round(c["p1"], 6): c for c in sa["candidates"]}
                    for (p1, lc), (_, tt) in zip(local_curve, truth_curve):
                        key = round(p1, 6)
                        if key in sa_map:
                            dl = abs(lc - sa_map[key]["frozen_cost"])
                            dt = abs(tt - sa_map[key]["truth_ttt"])
                            repro_local_max = max(repro_local_max, dl)
                            repro_truth_max = max(repro_truth_max, dt)

            # --- per-signal marginal gradient (중심차분, 클램프된 평가점) ---
            p_hi = clamp(p1_0 + DELTA)
            p_lo = clamp(p1_0 - DELTA)
            two_delta = p_hi - p_lo  # 클램프 시 유효 폭 사용
            if two_delta <= 0:
                g_i = 0.0
                d_local = 0.0
            else:
                truth_hi = truth_horizon_ttt(cfg, profile, controls, state_k, k, signal, p_hi)
                truth_lo = truth_horizon_ttt(cfg, profile, controls, state_k, k, signal, p_lo)
                g_i = (truth_hi - truth_lo) / two_delta
                local_hi = score_candidate(
                    follower, signal, p_hi, state_k, coupling, s_eff_frozen,
                    reservoir_drain, freeway_congestion, snapshot, demand_k, None,
                )
                local_lo = score_candidate(
                    follower, signal, p_lo, state_k, coupling, s_eff_frozen,
                    reservoir_drain, freeway_congestion, snapshot, demand_k, None,
                )
                d_local = (local_hi - local_lo) / two_delta
            g_ext = g_i - d_local

            # --- B0 부호예측 확인: A/C는 g_i<0 기대, D/F는 g_i>0 기대 ---
            sign_ok = "-"
            if signal in ("A", "C"):
                sign_pred_total += 1
                ok = g_i < 0.0
                sign_pred_hits += int(ok)
                sign_ok = "OK" if ok else "x"
            elif signal in ("D", "F"):
                sign_pred_total += 1
                ok = g_i > 0.0
                sign_pred_hits += int(ok)
                sign_ok = "OK" if ok else "x"

            # --- priced 곡선(full / externality) over 후보집합, w별 argmin ---
            w_full_arg: Dict[str, float] = {}
            w_ext_arg: Dict[str, float] = {}
            for w in W_SWEEP:
                priced_full = [(p1, lc + w * g_i * (p1 - p1_0)) for (p1, lc) in local_curve]
                priced_ext = [(p1, lc + w * g_ext * (p1 - p1_0)) for (p1, lc) in local_curve]
                af = _argmin_p1(priced_full)
                ae = _argmin_p1(priced_ext)
                w_full_arg[str(w)] = af
                w_ext_arg[str(w)] = ae

            n_total += 1
            base_full = abs(w_full_arg["0.0"] - truth_argmin)  # w=0 == local_argmin distance
            base_ext = abs(w_ext_arg["0.0"] - truth_argmin)
            mv_full_1 = "-"
            mv_ext_1 = "-"
            for w in W_SWEEP:
                if abs(w_full_arg[str(w)] - truth_argmin) < base_full:
                    moved_full[w] += 1
                if abs(w_ext_arg[str(w)] - truth_argmin) < base_ext:
                    moved_ext[w] += 1
            # w=1.0 이동 여부(표시용)
            mv_full_1 = "Y" if abs(w_full_arg["1.0"] - truth_argmin) < base_full else "n"
            mv_ext_1 = "Y" if abs(w_ext_arg["1.0"] - truth_argmin) < base_ext else "n"

            print(f"{signal:>3} {legacy_p1:6.1f} {local_argmin:6.1f} {truth_argmin:6.1f} "
                  f"{g_i:9.4f} {d_local:8.4f} {g_ext:9.4f} {sign_ok:>4} "
                  f"{w_full_arg['1.0']:6.1f} {w_ext_arg['1.0']:6.1f} "
                  f"{mv_full_1:>4} {mv_ext_1:>4}", flush=True)

            step_out[signal] = {
                "legacy_p1": legacy_p1,
                "p1_0": p1_0,
                "local_argmin": local_argmin,
                "truth_argmin": truth_argmin,
                "g_i": g_i,
                "g_ext_i": g_ext,
                "d_local_dp1": d_local,
                "sign_pred_ok": (sign_ok == "OK") if sign_ok != "-" else None,
                "priced_argmin_full": w_full_arg,
                "priced_argmin_ext": w_ext_arg,
                "local_curve": [[p, c] for (p, c) in local_curve],
                "truth_curve": [[p, c] for (p, c) in truth_curve],
            }
        results["steps"][str(k)] = step_out

    results["summary"] = {
        "n_signal_steps": n_total,
        "moved_to_truth_full": {str(w): moved_full[w] for w in W_SWEEP},
        "moved_to_truth_ext": {str(w): moved_ext[w] for w in W_SWEEP},
        "sign_pred_hits": sign_pred_hits,
        "sign_pred_total": sign_pred_total,
        "repro_local_max_abs_diff": repro_local_max,
        "repro_truth_max_abs_diff": repro_truth_max,
    }

    out_json = out_dir / "step_b_results.json"
    with open(out_json, "w") as fh:
        json.dump(results, fh, indent=2)

    print(f"\n=== SUMMARY (signal-steps = {n_total}) ===", flush=True)
    for w in W_SWEEP:
        print(f"  w={w:>3}:  moved-to-truth  full={moved_full[w]}/{n_total}   "
              f"ext={moved_ext[w]}/{n_total}", flush=True)
    print(f"  g_i sign matches B0 prediction (A/C<0,D/F>0): "
          f"{sign_pred_hits}/{sign_pred_total}", flush=True)
    if stepa is not None:
        print(f"  [repro] max |local-frozen| = {repro_local_max:.3e}   "
              f"max |truth-truth| = {repro_truth_max:.3e}   "
              f"(tol {REPRO_TOL:.0e}) -> "
              f"{'OK' if max(repro_local_max, repro_truth_max) < REPRO_TOL else 'MISMATCH'}",
              flush=True)
    print(f"wrote {out_json}", flush=True)


if __name__ == "__main__":
    main()
