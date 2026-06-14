# Option C: 강제 98% state에서 segment 벡터 후보별 cost/ΔTTS 진단 스크립트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.state import ExperimentConfig, TrafficState, ControlAction, segment_vsl
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.metanet import effective_lane_profile
from src.controllers.wu_distributed import WuDistributedController, _wu_fixed_control


def congested_config():
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {"mpc": {"horizon_steps": 1, "max_nash_iter": 5}},
    )


def congested_state(cfg):
    net = cfg.network
    state = TrafficState.initial(cfg)
    for movement in net.urban_movements:
        state.urban_movement_queue[movement] = 80.0
    # 최종 test_c fixture와 동일: 상류 free-flow(ρ<ρ_crit), 병목 seg2 jam.
    for link in net.freeway_links:
        state.freeway_density[link] = [15.0, 20.0, 40.0]
        state.freeway_speed[link] = [88.0, 80.0, 48.0]
    for ramp in net.ramps:
        state.ramp_queue[ramp] = 0.0
    for off_ramp in net.off_ramps:
        sl = net.off_ramp_storage_link[off_ramp]
        cap = net.urban_link_storage_veh[sl]
        state.urban_link_storage[sl] = 0.02 * cap
    for link, cap in net.urban_link_storage_veh.items():
        state.urban_link_storage[link] = min(state.urban_link_storage.get(link, cap), 0.05 * cap)
    return state


def main():
    cfg = congested_config()
    ctl = WuDistributedController(cfg)
    state = congested_state(cfg)
    demand = DemandProfile(cfg, ScenarioConfig("test", freeway_scale=1.0, ramp_scale=0.8)).at(0.0)
    previous = _wu_fixed_control(cfg)
    vsl_max = max(cfg.freeway_follower.vsl_set)
    for link in cfg.network.freeway_links:
        previous.vsl[link] = vsl_max

    profile, lane_diag = effective_lane_profile(state, cfg)
    print("=== 전제 ===")
    for link in cfg.network.freeway_links:
        print(f"  {link}: lambda_eff_last={lane_diag[f'lambda_eff_{link}_last']:.4f} "
              f"capacity_drop_active={lane_diag.get('capacity_drop_active')}")

    coupling = ctl._coupling(state, previous, demand)
    print("=== p_down ===")
    for link in cfg.network.freeway_links:
        print(f"  p_down_{link}={coupling.get(f'p_down_{link}', 0.0):.4f}")

    n_seg = cfg.network.freeway_segments_per_link
    link = cfg.network.freeway_links[0]
    candidates = ctl._freeway_segment_candidates(link, n_seg, previous)
    print(f"=== {link} 후보 수 = {len(candidates)} ===")

    # 후보별 cost 직접 측정(controller 내부 로직과 동일 경로를 단독 재현하지 않고
    # _solve_freeway_agent를 후보 1개씩 강제하기 위해 단순 후보-cost 평가를 재현).
    # 여기서는 _solve_freeway_agent를 패치 없이 각 후보를 previous로 강제 비교한다.
    import copy
    results = []
    for vec in candidates:
        prev_force = copy.deepcopy(previous)
        # previous를 이 후보로 두면 candidates 가지치기가 달라지므로,
        # 대신 단일 후보만 평가하도록 임시 vsl_set 제약 대신 직접 cost를 재현한다.
        results.append(vec)

    # 직접: _solve_freeway_agent를 호출해 선택 벡터 확인 + all-max 대비 cost 출력.
    vsl_dict, best_obj, evals = ctl._solve_freeway_agent(link, state, coupling, demand, previous, None)
    seg_sel = [vsl_dict[f"{link}__seg{i}"] for i in range(n_seg)]
    print(f"선택된 segment 벡터 {link}: {seg_sel}  obj={best_obj:.4f} evals={evals}")

    # all-max 후보의 cost를 따로 측정(상류↓ 후보 ΔTTS 비교용).
    sweep_seg = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"=== 후보별 cost(seg{sweep_seg} sweep, 나머지 상류=max, seg2=max) ===")
    for v0 in sorted(cfg.freeway_follower.vsl_set):
        cand = copy.deepcopy(previous)
        for i in range(n_seg):
            cand.vsl[f"{link}__seg{i}"] = vsl_max
        cand.vsl[f"{link}__seg{sweep_seg}"] = float(v0)
        # _solve_freeway_agent의 cost 평가를 재현하려면 후보 1개만 평가해야 한다.
        # 임시로 previous=cand로 두고 후보집합을 {cand} 한 점으로 좁힌다(max_vsl_step=0).
        tiny_cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"mpc": {"horizon_steps": 1, "max_nash_iter": 5},
             "freeway_follower": {"max_vsl_step": 0.0}},
        )
        tiny_ctl = WuDistributedController(tiny_cfg)
        tiny_coupling = tiny_ctl._coupling(state, cand, demand)
        vd, obj, _ = tiny_ctl._solve_freeway_agent(link, state, tiny_coupling, demand, cand, None)
        print(f"  seg0={v0:>5.0f} seg1=100 seg2=100 -> obj={obj:.5f}")


if __name__ == "__main__":
    main()
