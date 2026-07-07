# joint g_meter x g_vsl — metering의 marginal cost가 VSL 활성 시에만 살아나는지(상보성) 확인
# fixed로 전진 후, 각 상태에서 VSL(상류seg) 2수준 x metering(ramp cap frac) 3수준 그리드로 전역 TTT
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
import statistics as stx

SC="sweet_190"; T=7200.0
cfg=ExperimentConfig.from_file(str(ROOT/"src/config/default.yaml"),{"simulation":{"T_total":T}})
scenario=load_scenarios(str(ROOT/"src/config/scenarios.yaml"))[SC]
cfg=apply_scenario_network_overrides(cfg,scenario)
profile=DemandProfile(cfg,scenario); sim=MixedTrafficSimulator(cfg)
ctrl=StackelbergWuMeteredController(cfg)
net=cfg.network; hz=cfg.mpc.horizon_steps; ci=cfg.simulation.control_interval
fixed=ControlAction.fixed(cfg)
links=list(net.freeway_links)
UP={}; RAMPS={}
for link in links:
    n_seg=len(sim.state.freeway_density[link])
    ramps=[r for r in net.ramps if net.ramp_to_freeway.get(r)==link]
    midx=_ramp_merge_index(cfg,ramps[0],n_seg) if ramps else n_seg//2
    UP[link]=[i for i in range(n_seg) if i<midx]; RAMPS[link]=(ramps,midx)
allramps=list(net.ramps)
VSET=[100,60]; MFRAC=[0.4,0.7,1.0]

def rampq(st): return sum(max(0.0,st.ramp_queue.get(r,0.0)) for r in allramps)
def rho_merge_mean(states):
    return stx.mean(stx.mean(s.freeway_density[l][RAMPS[l][1]] for s in states) for l in links)

def build(vsl,frac):
    c=fixed.copy(); c.vsl=dict(fixed.vsl); c.ramp_metering=dict(fixed.ramp_metering)
    for link in links:
        for i in UP[link]: c.vsl[f"{link}__seg{i}"]=float(vsl)
        if vsl<99.5: c.vsl[link]=min(c.vsl.get(link,vsl),float(vsl))
    for r in allramps:
        c.ramp_metering[r]=frac*net.ramp_capacity_veh_h[r]
    return c

def probe(state,forecast,q0):
    print(f"    {'':8s}"+"".join(f"  m={f:.1f}cap" for f in MFRAC)+"     (TTT / rampQ_term / rho_merge)")
    grid={}
    for vsl in VSET:
        ttts=[]; qs=[]; rms=[]
        for f in MFRAC:
            states,ttt=ctrl._predict(state,build(vsl,f),forecast)
            ttts.append(ttt); qs.append(rampq(states[-1])); rms.append(rho_merge_mean(states))
        grid[vsl]=ttts
        g=(ttts[-1]-ttts[0])  # metering 0.4→1.0에서 전역 TTT 변화 = g_meter 방향(음=방류가 이득)
        print(f"    VSL{vsl:>3} TTT "+" ".join(f"{t:>9.1f}" for t in ttts)+f"   g_meter(Δ0.4→1.0)={g:+.1f}")
        print(f"    {'':7s}Q  "+" ".join(f"{q:>9.0f}" for q in qs))
    # 상보성 지표: g_meter가 VSL60서 더 음(방류 이득 커짐)?
    g100=grid[100][-1]-grid[100][0]; g60=grid[60][-1]-grid[60][0]
    print(f"    >> g_meter@VSL100={g100:+.1f}  vs  g_meter@VSL60={g60:+.1f}   상보성={'YES' if g60<g100-0.2 else 'no'}(VSL내리면 방류가 더 이득)")

prev=fixed.copy()
for step in range(30):
    t=step*ci; forecast=profile.horizon(t,hz)
    if step in (9,15,21,27):
        print(f"=== step {step+1} t={t:.0f}s rampQ0={rampq(sim.state):.0f} ===",flush=True)
        probe(sim.state.copy(),forecast,rampq(sim.state)); print(flush=True)
    sim.step(fixed.copy(),forecast[0],step); prev=fixed.copy()
print("판정: VSL100서 g_meter≈0(flat)인데 VSL60서 g_meter<0(방류 이득)면 → metering가격은 VSL과 joint로만 산다=가설 확증.",flush=True)
