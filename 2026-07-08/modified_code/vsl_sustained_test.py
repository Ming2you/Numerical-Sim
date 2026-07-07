# (2) 제대로 — closed-loop에서 freeway 상류 VSL을 처음부터 지속 강제 → merge subcritical 유지+ramp 배수+TTT 검증
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(r"C:\Users\alsrj\Desktop\Numerical-Sim")
sys.path.insert(0, str(ROOT))
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig
from src.models.metanet import _ramp_merge_index
from src.simulation.simulator import MixedTrafficSimulator
import statistics as stx

SC="sweet_190"; T=7200.0
FORCE=float(sys.argv[1]) if len(sys.argv)>1 else 100.0   # 100=강제 없음(baseline)

cfg=ExperimentConfig.from_file(str(ROOT/"src/config/default.yaml"),{"simulation":{"T_total":T}})
scenario=load_scenarios(str(ROOT/"src/config/scenarios.yaml"))[SC]
cfg=apply_scenario_network_overrides(cfg,scenario)
profile=DemandProfile(cfg,scenario); sim=MixedTrafficSimulator(cfg)
ctrl=StackelbergWuMeteredController(cfg)   # B2TR 계열(leader N_UF/metering 현실적)
ctrl.signal_price_enabled=True; ctrl.signal_price_trust_sec=ctrl.signal_price_delta_sec
net=cfg.network; hz=cfg.mpc.horizon_steps; ci=cfg.simulation.control_interval
links=list(net.freeway_links)
META={}
for link in links:
    n_seg=len(sim.state.freeway_density[link])
    ramps=[r for r in net.ramps if net.ramp_to_freeway.get(r)==link]
    midx=_ramp_merge_index(cfg,ramps[0],n_seg) if ramps else n_seg//2
    META[link]=(n_seg,ramps,midx,[i for i in range(n_seg) if i<midx])

def rho_merge_now(st):
    return stx.mean(st.freeway_density[link][META[link][2]] for link in links)
def rampq_now(st):
    return sum(max(0.0,st.ramp_queue.get(r,0.0)) for r in net.ramps)

prev=None; steps=max(1,int(round(cfg.simulation.T_total/ci)))
rho_over=[]; nuf=[]
print(f"==== FORCE VSL={FORCE} (상류 seg) ====",flush=True)
for step in range(steps):
    t=step*ci; forecast=profile.horizon(t,hz)
    control=ctrl.decide(sim.state.copy(),forecast,prev,cfg)
    if FORCE<99.5:
        control.vsl=dict(control.vsl)
        for link in links:
            for i in META[link][3]:
                control.vsl[f"{link}__seg{i}"]=FORCE
            control.vsl[link]=min(control.vsl.get(link,FORCE),FORCE)
    sim.step(control,forecast[0],step); prev=control.copy()
    nuf.append(float(control.N_UF_star)); rho_over.append(rho_merge_now(sim.state))
    if step%6==0 or step==steps-1:
        print(f"  step {step+1:2d} cum={sim.total_ttt:.0f} u={sim.urban_ttt:.0f} f={sim.freeway_ttt:.0f} rho_merge={rho_merge_now(sim.state):.1f} rampQ={rampq_now(sim.state):.0f} N_UF={control.N_UF_star:.0f}",flush=True)
if hasattr(ctrl,"close"): ctrl.close()
supercrit=sum(1 for r in rho_over if r>net.rho_crit)
print(f"---- FORCE={FORCE}: total={sim.total_ttt:.0f} urban={sim.urban_ttt:.0f} freeway={sim.freeway_ttt:.0f} "
      f"N_UF_mean={stx.mean(nuf):.0f} rho_merge_mean={stx.mean(rho_over):.1f} supercrit_steps={supercrit}/{steps}",flush=True)
print("ref(내머신,B2TR계열 baseline은 FORCE=100 런으로 잡음). 판정: FORCE↓서 total↓+supercrit↓+N_UF↑ 면 VSL lever 실재.",flush=True)
