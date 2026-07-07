# (C) 검토 — 9분 base + V_f(=free-flow T(loc) + w_D·밀도초과)의 gradient가 60분 ground truth 부호와 맞나
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
ctrl=StackelbergWuMeteredController(cfg)
net=cfg.network; ci=cfg.simulation.control_interval; hz=cfg.mpc.horizon_steps
fixed=ControlAction.fixed(cfg)
links=list(net.freeway_links)
Lseg=net.freeway_segment_length_km; lanes=net.freeway_lanes; vfree=net.v_free; rho_crit=net.rho_crit
segtt=Lseg/vfree
URBAN_T=0.04  # off-ramp/urban 하류 경로 nominal 시간(h)
# 링크별 free-flow time-to-exit Bellman (off-ramp seg1,2 β=0.2, seg3→exit)
Tseg={}
for link in links:
    T3=segtt
    T2=segtt+0.2*URBAN_T+0.8*T3
    T1=segtt+0.2*URBAN_T+0.8*T2
    T0=segtt+T1
    Tseg[link]=[T0,T1,T2,T3]
def Tramp(link): return segtt+Tseg[link][2]
UP={}; RAMPS={}
for link in links:
    n=len(sim.state.freeway_density[link]); rs=[r for r in net.ramps if net.ramp_to_freeway.get(r)==link]
    UP[link]=[i for i in range(n) if i<_ramp_merge_index(cfg,rs[0],n)]; RAMPS[link]=rs
allramps=list(net.ramps)

def build(vsl,frac):
    c=fixed.copy(); c.vsl=dict(fixed.vsl); c.ramp_metering=dict(fixed.ramp_metering)
    for link in links:
        for i in UP[link]: c.vsl[f"{link}__seg{i}"]=float(vsl)
        if vsl<99.5: c.vsl[link]=min(c.vsl.get(link,vsl),float(vsl))
    for r in allramps: c.ramp_metering[r]=frac*net.ramp_capacity_veh_h[r]
    return c

def Vf(state, w_D):
    vf=0.0; dens_ex=0.0
    for link in links:
        for i,rho in enumerate(state.freeway_density[link]):
            n=rho*Lseg*lanes
            vf += n*Tseg[link][i]
            dens_ex += max(0.0, rho-rho_crit)*Lseg*lanes
    for r in allramps:
        vf += max(0.0,state.ramp_queue.get(r,0.0))*Tramp(net.ramp_to_freeway[r])
    vf += state.objective_urban_vehicles(net, False)*URBAN_T
    vf += state.off_ramp_storage_occupancy_veh(net)*URBAN_T
    return vf + w_D*dens_ex, dens_ex

def base9(state, control, t0):
    s=state.copy(); tot=0.0; fc=profile.horizon(t0,hz)
    last=None
    for k in range(hz):
        res=run_coupled_interval(s, control, fc[min(k,len(fc)-1)], cfg); s.time_sec+=ci; tot+=res.freeway_ttt+res.urban_ttt; last=s.copy()
    return tot, last

def truth60(state, control, t0):
    s=state.copy(); tot=0.0; fc=profile.horizon(t0,20)
    for k in range(20):
        res=run_coupled_interval(s, control, fc[min(k,len(fc)-1)], cfg); s.time_sec+=ci; tot+=res.freeway_ttt+res.urban_ttt
    return tot

def probe(state,t0):
    print(f"    {'lever':>8} | {'truth60(부호=정답)':>18} | {'C: base9+Vf 부호(w_D=0/2/8)':>30}")
    # g_release: VSL100, frac 0.4 vs 1.0
    for name,(vh,fh,vl,fl) in [("release",(100,1.0,100,0.4)), ("vsl↓",(60,1.0,100,1.0))]:
        chi=build(vh,fh); clo=build(vl,fl)
        gt = truth60(state,chi,t0)-truth60(state,clo,t0)
        row=[]
        for wD in (0.0,2.0,8.0):
            bhi,shi=base9(state,chi,t0); blo,slo=base9(state,clo,t0)
            vfhi,_=Vf(shi,wD); vflo,_=Vf(slo,wD)
            g=(bhi+vfhi)-(blo+vflo); row.append(g)
        sign=lambda x:'+' if x>1 else ('-' if x<-1 else '0')
        print(f"    {name:>8} | {gt:>10.1f} [{sign(gt)}] | "+"  ".join(f"{g:>8.1f}[{sign(g)}]" for g in row))

prev=fixed.copy()
for step in range(30):
    t=step*ci
    if step in (10,16,22):  # step16=방류가 장기 손해였던 곳
        rq=sum(max(0.0,sim.state.ramp_queue.get(r,0.0)) for r in allramps)
        print(f"=== step {step+1} t={t:.0f}s rampQ={rq:.0f} ===",flush=True)
        probe(sim.state.copy(),t); print(flush=True)
    sim.step(fixed.copy(), profile.horizon(t,hz)[0], step); prev=fixed.copy()
print("판정: C의 부호가 truth60 부호와 일치하면(특히 step16 방류=+, peak 방류/VSL=-) → (C) 작동. w_D가 step16 과방류를 -에서 +로 뒤집어야 downside 성공.",flush=True)
