# [진단 probe] follower green 후보 채점에 downstream S_eff 시변 oracle을 주입해 랭킹 이동 검증
"""Step-A 오라클 상한 probe (SPEC 참조: _stepA_probe).

follower 국소 rollout은 downstream 가용공간을 `_frozen_s_eff(state)` 현재 스냅샷 한 장으로
고정한다 → horizon 동안 downstream 변화를 못 본다. 이 probe는 그 downstream을 legacy 제어로
전진시킨 **시변 궤적 oracle**로 대체하고, follower의 green 후보(p1) 랭킹이 좋은 방향
(legacy green / full-plant 최적)으로 이동하는지 검증한다.

세 방식으로 각 후보 p1을 채점한다:
  (a) frozen : 현재 코드(s_eff = _frozen_s_eff 스냅샷 고정).
  (b) oracle : (a)와 동일하되 rollout에 s_eff_by_substep=oracle 궤적 주입(monkeypatch).
  (c) truth  : ego 신호만 green 바꾸고 나머지·freeway는 legacy 고정, full coupled plant를
               horizon_steps회 전진해 누적 (freeway_ttt+urban_ttt).

채점은 production `_solve_urban_agent_local`을 신호별·후보별로 호출해 얻는다(단일 후보로
`_urban_green_candidates`를 몽키패치해 그 후보의 cost를 best_obj로 추출).

CLI:
  python -B work/step_a_oracle_probe.py --scenario sweet_190 \
      --legacy-trace <control_timeseries.csv> --steps 20,26,35 --output outputs/_stepA_probe
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.controllers.wu_faithful_follower as wff_module
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import (
    DemandProfile,
    apply_scenario_network_overrides,
    load_scenarios,
)
from src.models.state import ControlAction, ExperimentConfig
from src.models.urban_queue_model import _effective_available_space
from src.simulation.coupling import run_coupled_interval
from src.simulation.simulator import MixedTrafficSimulator


# ---------------------------------------------------------------------------
# cfg / demand 구성
# ---------------------------------------------------------------------------
def build_cfg(scenario_name: str):
    overrides = {
        "mpc": {"relaxed_quantized_controls": True, "grid_parallel_backend": "serial"},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
    scenario = scenarios[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    return cfg, scenario


# ---------------------------------------------------------------------------
# legacy control_timeseries.csv 로드 → step -> ControlAction
# ---------------------------------------------------------------------------
def load_legacy_controls(cfg: ExperimentConfig, csv_path: str) -> Dict[int, ControlAction]:
    """control_timeseries.csv를 step -> ControlAction로 복원.

    컬럼 매핑(simulator.control_row 기준):
      green_{signal}_p1 / _p2 -> green_times["{signal}_p1"/"_p2"]
      offset_{signal}         -> offsets["{signal}"]
      ramp_metering_{ramp}    -> ramp_metering["{ramp}"]
      vsl_{link}_seg{i}       -> vsl["{link}__seg{i}"]  (segment_vsl 조회 키)
      vsl_{link}              -> vsl["{link}"]          (link fallback 키)
    주의: CSV의 time_sec는 step 종료 후 값((step+1)*control_interval)이라 demand time과
    다르다. demand time은 step 컬럼으로 재구성한다(replay 시).
    """
    net = cfg.network
    controls: Dict[int, ControlAction] = {}
    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            step = int(round(float(row["step"])))
            ctrl = ControlAction.uncontrolled(cfg)
            ctrl.inflow_outflow_allocation = {}
            # green
            for signal in net.signals:
                for phase in ("p1", "p2"):
                    key = f"green_{signal}_{phase}"
                    if key in row and row[key] != "":
                        ctrl.green_times[f"{signal}_{phase}"] = float(row[key])
                okey = f"offset_{signal}"
                if okey in row and row[okey] != "":
                    ctrl.offsets[signal] = float(row[okey])
            # ramp metering
            for ramp in net.ramps:
                key = f"ramp_metering_{ramp}"
                if key in row and row[key] != "":
                    ctrl.ramp_metering[ramp] = float(row[key])
            # vsl (segment + link fallback)
            for link in net.freeway_links:
                lkey = f"vsl_{link}"
                if lkey in row and row[lkey] != "":
                    ctrl.vsl[link] = float(row[lkey])
                for i in range(net.freeway_segments_per_link):
                    skey = f"vsl_{link}_seg{i}"
                    if skey in row and row[skey] != "":
                        ctrl.vsl[f"{link}__seg{i}"] = float(row[skey])
            controls[step] = ctrl
    return controls


# ---------------------------------------------------------------------------
# state replay: initial state에서 legacy 제어로 step k까지 전진
# ---------------------------------------------------------------------------
def replay_to_step(cfg, profile, controls: Mapping[int, ControlAction], k: int):
    """initial state에서 legacy 제어를 step 0..k-1까지 전진 → state_k(state at start of step k).

    각 step j에서 demand = profile.at(j*control_interval), control = controls[j].
    run_coupled_interval은 state를 in-place 전진하고 time_sec는 수동 증가시킨다.
    """
    dt = cfg.simulation.control_interval
    sim = MixedTrafficSimulator(cfg)
    state = sim.state
    for j in range(k):
        demand = profile.at(state.time_sec)
        ctrl = controls[j]
        run_coupled_interval(state, ctrl, demand, cfg)
        state.time_sec += dt
    return state


# ---------------------------------------------------------------------------
# oracle s_eff 궤적 추출
# ---------------------------------------------------------------------------
def build_oracle_s_eff(cfg, profile, controls, state_k, k: int):
    """state_k에서 legacy 제어로 horizon_steps회 전진, 각 interval 종료 후 모든 urban 링크
    S_eff를 기록 → piecewise-constant로 확장해 s_eff_by_substep[link] (길이 horizon*K_cu) 생성.

    각 interval j의 값으로 그 interval의 K_cu substep을 채운다. interval 시작 전이 아니라
    **종료 후** 값을 쓰는 이유: 그 구간 동안 downstream이 도달하는 상태를 근사하기 위함
    (SPEC 4번 지시).
    """
    dt = cfg.simulation.control_interval
    K_cu = max(1, cfg.simulation.K_cu)
    horizon = max(1, cfg.mpc.horizon_steps)
    urban_links = list(cfg.network.urban_link_storage_veh)

    s = state_k.copy()
    per_interval: List[Dict[str, float]] = []  # interval j 종료 후 링크별 S_eff
    for j in range(horizon):
        demand = profile.at(s.time_sec)
        ctrl = controls[k + j]
        run_coupled_interval(s, ctrl, demand, cfg)
        s.time_sec += dt
        snap = {link: float(_effective_available_space(s, cfg, link)) for link in urban_links}
        per_interval.append(snap)

    s_eff_by_substep: Dict[str, List[float]] = {}
    for link in urban_links:
        prof: List[float] = []
        for j in range(horizon):
            prof.extend([per_interval[j][link]] * K_cu)
        s_eff_by_substep[link] = prof
    return s_eff_by_substep


# ---------------------------------------------------------------------------
# frozen/oracle 채점: production _solve_urban_agent_local을 단일 후보로 호출
# ---------------------------------------------------------------------------
def _make_oracle_rollout_wrappers(oracle_s_eff: Mapping[str, Sequence[float]]):
    """세 rollout 함수를 감싸 s_eff_by_substep=oracle_s_eff를 주입하는 래퍼 dict 반환.
    _solve_urban_agent_local이 어느 경로(plain/phased/ramp_aware)를 타든 oracle이 먹는다.
    호출처가 이 링크 movement의 receiving 링크만 s_eff0에 담으므로, oracle에서도 해당
    링크만 유효(나머지 키는 rollout 내부 s_eff에 없어 무시)."""
    orig_plain = wff_module.rollout_local_tts
    orig_phased = wff_module.rollout_local_tts_phased
    orig_ramp = wff_module.rollout_local_tts_ramp_aware

    def plain(*args, **kwargs):
        kwargs.setdefault("s_eff_by_substep", oracle_s_eff)
        return orig_plain(*args, **kwargs)

    def phased(*args, **kwargs):
        kwargs.setdefault("s_eff_by_substep", oracle_s_eff)
        return orig_phased(*args, **kwargs)

    def ramp(*args, **kwargs):
        kwargs.setdefault("s_eff_by_substep", oracle_s_eff)
        return orig_ramp(*args, **kwargs)

    return {
        "rollout_local_tts": plain,
        "rollout_local_tts_phased": phased,
        "rollout_local_tts_ramp_aware": ramp,
    }, (orig_plain, orig_phased, orig_ramp)


def score_candidate(
    follower: WuFaithfulFollower,
    signal: str,
    p1: float,
    state,
    coupling,
    s_eff_frozen,
    reservoir_drain,
    freeway_congestion,
    snapshot: ControlAction,
    demand,
    oracle_s_eff: Optional[Mapping[str, Sequence[float]]] = None,
) -> float:
    """production _solve_urban_agent_local을 이 신호의 단일 후보 p1로 호출해 그 후보 cost 반환.

    `_urban_green_candidates`를 [p1]만 반환하도록 임시 몽키패치 → 후보가 하나뿐이라
    best_obj가 곧 그 p1의 채점 cost다. oracle_s_eff가 주어지면 rollout 함수 3개를 감싸
    s_eff_by_substep을 주입한다.
    """
    arr_movement = follower._per_movement_arrivals(signal, state, snapshot, demand)

    orig_cand = follower._urban_green_candidates
    follower._urban_green_candidates = lambda *a, **k: [float(p1)]  # type: ignore

    patched = None
    if oracle_s_eff is not None:
        wrappers, originals = _make_oracle_rollout_wrappers(oracle_s_eff)
        wff_module.rollout_local_tts = wrappers["rollout_local_tts"]
        wff_module.rollout_local_tts_phased = wrappers["rollout_local_tts_phased"]
        wff_module.rollout_local_tts_ramp_aware = wrappers["rollout_local_tts_ramp_aware"]
        patched = originals
    try:
        best_p1, best_obj, _, _ = follower._solve_urban_agent_local(
            signal, state.copy(), coupling, arr_movement, s_eff_frozen,
            reservoir_drain, freeway_congestion, snapshot,
            None, 0.0, None, 1.0, demand,
        )
    finally:
        follower._urban_green_candidates = orig_cand  # type: ignore
        if patched is not None:
            (wff_module.rollout_local_tts,
             wff_module.rollout_local_tts_phased,
             wff_module.rollout_local_tts_ramp_aware) = patched
    return float(best_obj)


# ---------------------------------------------------------------------------
# ground-truth: ego 신호만 green 바꾸고 나머지·freeway legacy 고정, full plant horizon TTT
# ---------------------------------------------------------------------------
def truth_horizon_ttt(cfg, profile, controls, state_k, k: int, signal: str, p1: float) -> float:
    dt = cfg.simulation.control_interval
    horizon = max(1, cfg.mpc.horizon_steps)
    total = cfg.network.effective_green_total
    s = state_k.copy()
    ttt = 0.0
    for j in range(horizon):
        demand = profile.at(s.time_sec)
        ctrl = controls[k + j].copy()
        ctrl.green_times[f"{signal}_p1"] = float(p1)
        ctrl.green_times[f"{signal}_p2"] = float(total - p1)
        r = run_coupled_interval(s, ctrl, demand, cfg)
        ttt += float(r.freeway_ttt) + float(r.urban_ttt)
        s.time_sec += dt
    return float(ttt)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="sweet_190")
    ap.add_argument("--legacy-trace", required=True)
    ap.add_argument("--steps", default="20", help="comma-separated step indices")
    ap.add_argument("--output", default="outputs/_stepA_probe")
    args = ap.parse_args()

    steps = [int(x) for x in str(args.steps).split(",") if str(x).strip() != ""]
    out_dir = ROOT / args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg, scenario = build_cfg(args.scenario)
    profile = DemandProfile(cfg, scenario)
    controls = load_legacy_controls(cfg, args.legacy_trace)
    horizon = max(1, cfg.mpc.horizon_steps)
    max_step_needed = max(steps) + horizon
    missing = [j for j in range(max(steps) + horizon) if j not in controls]
    if missing:
        print(f"WARN: legacy trace missing steps {missing[:10]}... "
              f"(need 0..{max_step_needed - 1})", flush=True)

    follower = WuFaithfulFollower(cfg)
    net = cfg.network

    results: Dict[str, object] = {
        "scenario": args.scenario,
        "legacy_trace": str(args.legacy_trace),
        "horizon_steps": horizon,
        "steps": {},
    }

    print(f"=== Step-A oracle probe  scenario={args.scenario}  horizon={horizon} ===", flush=True)
    header = (f"{'step':>4} {'sig':>3} {'legacy':>7} {'frozen':>7} {'oracle':>7} "
              f"{'truth':>7} {'|o-t|<|f-t|':>11} {'|o-L|<|f-L|':>11}")

    for k in steps:
        if any((k + j) not in controls for j in range(horizon)):
            print(f"SKIP step {k}: legacy control missing in horizon window.", flush=True)
            continue
        state_k = replay_to_step(cfg, profile, controls, k)
        demand_k = profile.at(state_k.time_sec)

        # follower _solve_followers 프롤로그와 동일한 동결 결합/스냅샷 구성.
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

        oracle_s_eff = build_oracle_s_eff(cfg, profile, controls, state_k, k)

        print(f"\n--- step {k} (t={state_k.time_sec:.0f}s) ---", flush=True)
        print(header, flush=True)

        step_out: Dict[str, object] = {}
        for signal in net.signals:
            candidates = follower._urban_green_candidates(signal, state_k, coupling, snapshot)
            legacy_p1 = float(controls[k].green_times.get(
                f"{signal}_p1", net.effective_green_total / 2.0))

            rows = []
            for p1 in candidates:
                frozen_cost = score_candidate(
                    follower, signal, p1, state_k, coupling, s_eff_frozen,
                    reservoir_drain, freeway_congestion, snapshot, demand_k, None,
                )
                oracle_cost = score_candidate(
                    follower, signal, p1, state_k, coupling, s_eff_frozen,
                    reservoir_drain, freeway_congestion, snapshot, demand_k, oracle_s_eff,
                )
                truth_ttt = truth_horizon_ttt(cfg, profile, controls, state_k, k, signal, p1)
                rows.append((float(p1), frozen_cost, oracle_cost, truth_ttt))

            p1s = [r[0] for r in rows]
            argmin_frozen = p1s[min(range(len(rows)), key=lambda i: rows[i][1])]
            argmin_oracle = p1s[min(range(len(rows)), key=lambda i: rows[i][2])]
            argmin_truth = p1s[min(range(len(rows)), key=lambda i: rows[i][3])]

            metric_toward_truth = abs(argmin_oracle - argmin_truth) < abs(argmin_frozen - argmin_truth)
            metric_toward_legacy = abs(argmin_oracle - legacy_p1) < abs(argmin_frozen - legacy_p1)

            print(f"{k:>4} {signal:>3} {legacy_p1:7.1f} {argmin_frozen:7.1f} "
                  f"{argmin_oracle:7.1f} {argmin_truth:7.1f} "
                  f"{str(metric_toward_truth):>11} {str(metric_toward_legacy):>11}", flush=True)

            step_out[signal] = {
                "legacy_p1": legacy_p1,
                "argmin_frozen_p1": argmin_frozen,
                "argmin_oracle_p1": argmin_oracle,
                "argmin_truth_p1": argmin_truth,
                "oracle_closer_to_truth": bool(metric_toward_truth),
                "oracle_toward_legacy": bool(metric_toward_legacy),
                "candidates": [
                    {"p1": r[0], "frozen_cost": r[1], "oracle_cost": r[2], "truth_ttt": r[3]}
                    for r in rows
                ],
            }
        results["steps"][str(k)] = step_out

    # 집계 요약
    n_toward_truth = 0
    n_toward_legacy = 0
    n_total = 0
    for k_str, step_out in results["steps"].items():
        for signal, so in step_out.items():
            n_total += 1
            n_toward_truth += int(so["oracle_closer_to_truth"])
            n_toward_legacy += int(so["oracle_toward_legacy"])
    results["summary"] = {
        "n_signal_steps": n_total,
        "n_oracle_closer_to_truth": n_toward_truth,
        "n_oracle_toward_legacy": n_toward_legacy,
    }

    out_json = out_dir / "step_a_results.json"
    with open(out_json, "w") as fh:
        json.dump(results, fh, indent=2)

    print(f"\n=== SUMMARY ===", flush=True)
    print(f"signal-steps scored : {n_total}", flush=True)
    print(f"oracle closer to full-plant truth : {n_toward_truth}/{n_total}", flush=True)
    print(f"oracle moved toward legacy green   : {n_toward_legacy}/{n_total}", flush=True)
    print(f"wrote {out_json}", flush=True)


if __name__ == "__main__":
    main()
