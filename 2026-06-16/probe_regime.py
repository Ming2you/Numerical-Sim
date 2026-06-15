# A''-1 regime 계측 probe (작업 후 삭제) — off-ramp 홍수 + 유한 출구용량 G2 검증
import sys

from src.models.demand import DemandProfile, ScenarioConfig, apply_scenario_network_overrides
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator
from src.models.urban_queue_model import _effective_available_space


def occ(state, cfg, link):
    cap = cfg.network.urban_link_storage_veh[link]
    return (cap - state.urban_link_storage.get(link, cap)) / max(cap, 1e-9)


def eff_occ(state, cfg, link):
    """유효 점유율 = 1 - S_eff/cap (movement 점큐 포함, S_eff 일관)."""
    cap = cfg.network.urban_link_storage_veh[link]
    s_eff = _effective_available_space(state, cfg, link)
    return (cap - s_eff) / max(cap, 1e-9)


def run(off_ramp_split, exit_cap=None, urban_scale=1.2, freeway_scale=1.5, steps=40):
    overrides = {}
    if exit_cap is not None:
        overrides = {"network": {"boundary_out_capacity_veh_h": exit_cap}}
    cfg = ExperimentConfig.from_file("src/config/default.yaml", overrides)
    scenario = ScenarioConfig(
        "regime",
        urban_scale=urban_scale,
        freeway_scale=freeway_scale,
        ramp_scale=1.0,
        off_ramp_split_ratio_override={k: off_ramp_split for k in cfg.network.off_ramps},
    )
    cfg = apply_scenario_network_overrides(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    demand = DemandProfile(cfg, scenario)
    control = ControlAction.uncontrolled(cfg)
    or_arr = 0.0
    or_dep = 0.0
    sink = 0.0
    for step_idx in range(steps):
        log = sim.step(control, demand.at(sim.state.time_sec), step_idx)
        or_arr += log.diagnostics.get("coupling_offramp_arrivals_accepted_veh", 0.0)
        or_dep += log.diagnostics.get("offramp_departures_veh", 0.0)
        sink += log.diagnostics.get("boundary_out_sink_veh", 0.0)
    state = sim.state
    grid_links = [l for l in cfg.network.urban_link_storage_veh if "_to_" in l]
    out_links = [l for l in cfg.network.urban_link_storage_veh if l.endswith("_out")]
    or_storage = list(cfg.network.off_ramp_storage_link.values())
    # off-ramp 하류 grid 링크: off-ramp가 합류하는 노드(D,F)에서 나가는 링크
    offramp_down = ["D_to_A", "D_to_E", "F_to_C", "F_to_E", "D_left_out", "F_right_out"]
    exit_q = sum(
        state.urban_movement_queue.get(m, 0.0)
        for m, s in cfg.network.urban_movements.items()
        if s.get("kind") == "boundary_out"
    )
    internal_q = sum(
        state.urban_movement_queue.get(m, 0.0)
        for m, s in cfg.network.urban_movements.items()
        if s.get("kind") == "internal"
    )
    return {
        "exit_q": exit_q,
        "internal_q": internal_q,
        "grid_max": max(occ(state, cfg, l) for l in grid_links),
        "grid_mean": sum(occ(state, cfg, l) for l in grid_links) / len(grid_links),
        "grid_eff_max": max(eff_occ(state, cfg, l) for l in grid_links),
        "offr_dn_eff_max": max(eff_occ(state, cfg, l) for l in offramp_down),
        "offr_dn_eff_mean": sum(eff_occ(state, cfg, l) for l in offramp_down) / len(offramp_down),
        "out_max": max(occ(state, cfg, l) for l in out_links),
        "out_mean": sum(occ(state, cfg, l) for l in out_links) / len(out_links),
        "or_storage_max": max(occ(state, cfg, l) for l in or_storage),
        "or_storage_mean": sum(occ(state, cfg, l) for l in or_storage) / len(or_storage),
        "offramp_down_max": max(occ(state, cfg, l) for l in offramp_down),
        "offramp_down_mean": sum(occ(state, cfg, l) for l in offramp_down) / len(offramp_down),
        "N_P": state.protected_accumulation_veh(cfg.network),
        "or_arr": or_arr,
        "or_dep": or_dep,
        "sink": sink,
    }


def fmt(d):
    return " ".join(f"{k}={v:.3f}" for k, v in d.items())


if __name__ == "__main__":
    caps = [None]
    if len(sys.argv) > 1:
        caps = [None if a == "none" else float(a) for a in sys.argv[1:]]
    for cap in caps:
        flood = run(0.6, exit_cap=cap)
        blocked = run(0.0, exit_cap=cap)
        print(f"=== exit_cap={cap} ===")
        print(f"  FLOOD  (split=0.6): {fmt(flood)}")
        print(f"  BLOCKED(split=0.0): {fmt(blocked)}")
        print(f"  relief grid_max: {flood['grid_max']:.3f} -> {blocked['grid_max']:.3f} "
              f"(drop {flood['grid_max']-blocked['grid_max']:.3f})")
        print(f"  relief offramp_down_max: {flood['offramp_down_max']:.3f} -> {blocked['offramp_down_max']:.3f}")
