# terminal cost 전제 검토 — release·VSL의 marginal이 horizon(9분) 밖에서 살아나는가?
# rollout을 3/10/20 step으로 늘려 d(TTT)/d(release), d(TTT)/d(VSL)가 지평 길이에 따라 어떻게 변하나
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(r"C:\Users\alsrj\Desktop\Numerical-Sim")
sys.path.insert(0, str(ROOT))
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig, ControlAction
from src.models.metanet import _ramp_merge_index
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.coupling import run_coupled_interval

SC="sweet_190"; T=7200.0
cfg=ExperimentConfig.from_file(str(ROOT/"src/config/default.yaml"),{"simulation":{"T_total":T}})
scenario=load_scenarios(str(ROOT/"src/config/scenarios.yaml"))[SC]
cfg=apply_scenario_network_overrides(cfg,scenario)
profile=DemandProfile(cfg,scenario); sim=MixedTrafficSimulator(cfg)
ctrl=StackelbergWuMeteredController(cfg)  # net만 사용
net=cfg.network; ci=cfg.simulation.control_interval
fixed=ControlAction.fixed(cfg)
links=list(net.freeway_links)
UP={}
for link in links:
    n_seg=len(sim.state.freeway_density[link])
    ramps=[r for r in net.ramps if net.ramp_to_freeway.get(r)==link]
    midx=_ramp_merge_index(cfg,ramps[0],n_seg) if ramps else n_seg//2
    UP[link]=[i for i in range(n_seg) if i<midx]
allramps=list(net.ramps)
HORIZONS=[3,10,20]  # 9분 / 30분 / 60분

def build(vsl,frac):
    c=fixed.copy(); c.vsl=dict(fixed.vsl); c.ramp_metering=dict(fixed.ramp_metering)
    for link in links:
        for i in UP[link]: c.vsl[f"{link}__seg{i}"]=float(vsl)
        if vsl<99.5: c.vsl[link]=min(c.vsl.get(link,vsl),float(vsl))
    for r in allramps: c.ramp_metering[r]=frac*net.ramp_capacity_veh_h[r]
    return c

def rollout_ttt(state, control, t0, nsteps):
    s=state.copy(); tot=0.0
    fc=profile.horizon(t0, nsteps)
    for k in range(nsteps):
        res=run_coupled_interval(s, control, fc[min(k,len(fc)-1)], cfg)
        s.time_sec += ci; tot += res.freeway_ttt + res.urban_ttt
    return tot

def probe(state,t0):
    print(f"    {'H(min)':>7} | {'g_release(Δfrac0.4→1.0)':>24} | {'g_vsl(Δ100→60)':>16}")
    for H in HORIZONS:
        # g_release: VSL=100 고정, metering 0.4 vs 1.0
        tr_lo=rollout_ttt(state, build(100,0.4), t0, H)
        tr_hi=rollout_ttt(state, build(100,1.0), t0, H)
        g_rel=tr_hi-tr_lo
        # g_vsl: metering 1.0 고정, VSL 100 vs 60
        tv_hi=rollout_ttt(state, build(100,1.0), t0, H)
        tv_lo=rollout_ttt(state, build(60,1.0),  t0, H)
        g_vsl=tv_lo-tv_hi   # VSL 내림(100→60)의 TTT 변화(음=이득)
        print(f"    {H*3:>7} | {g_rel:>24.1f} | {g_vsl:>16.1f}")

prev=fixed.copy()
for step in range(30):
    t=step*ci
    if step in (9,15,21):
        rq=sum(max(0.0,sim.state.ramp_queue.get(r,0.0)) for r in allramps)
        print(f"=== step {step+1} t={t:.0f}s rampQ={rq:.0f} ===",flush=True)
        probe(sim.state.copy(), t); print(flush=True)
    sim.step(fixed.copy(), profile.horizon(t,3)[0], step); prev=fixed.copy()
print("판정: H 늘릴수록 g_release·g_vsl이 더 음(-)으로 커지면 → 이득이 horizon 밖 → terminal cost가 잡을 게 있음(작동 전제 OK).",flush=True)
print("      9분(H=3)선 ~0인데 30/60분서 크게 음이면 → 9분 근시가 주범, terminal cost 필요 확증.",flush=True)
