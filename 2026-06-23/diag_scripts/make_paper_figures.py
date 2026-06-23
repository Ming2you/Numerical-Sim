# 사후분석 논문급 그림 일괄 생성 — analysis_matrix_3600 데이터 기반(일회용 분석 스크립트).
import os, csv, glob
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from src.models.state import ExperimentConfig
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.grid": True,
    "grid.alpha": 0.3, "axes.axisbelow": True, "figure.dpi": 200,
    "savefig.bbox": "tight", "axes.spines.top": False, "axes.spines.right": False,
})
BASE = "outputs/analysis_matrix_3600"
OUT = "reports/figures"; os.makedirs(OUT, exist_ok=True)
SCN = ["medium_demand", "peak_demand", "oversaturated_demand", "incident_or_capacity_drop"]
SLAB = {"medium_demand":"medium","peak_demand":"peak","oversaturated_demand":"oversat.","incident_or_capacity_drop":"incident"}
CTRL = ["NO-CONTROL","WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]
CLAB = {"NO-CONTROL":"No-control","WU-CD-F":"P-WU","PROPOSED-FOLLOWERS-ONLY":"PFO","PROPOSED-STACKELBERG":"P-Stack"}
COL  = {"NO-CONTROL":"#8c8c8c","WU-CD-F":"#ff7f0e","PROPOSED-FOLLOWERS-ONLY":"#1f77b4","PROPOSED-STACKELBERG":"#d62728"}

def rd(p): return list(csv.DictReader(open(p,encoding="utf-8"))) if os.path.exists(p) else []
def fl(x):
    try: return float(x)
    except: return None
summ = rd(f"{BASE}/analysis/summary_with_no_control.csv") + rd(f"{BASE}/all_no_control_summary.csv")
def srow(sc,c): return next((r for r in summ if r.get("scenario")==sc and r.get("controller_id")==c),None)
def sval(sc,c,k):
    r=srow(sc,c); return fl(r.get(k)) if r else None
def ts(sc,c,f): return rd(f"{BASE}/runs/{sc}/{c}/{f}")
scen=load_scenarios("src/config/scenarios.yaml")

# FIG1 demand profiles
fig,ax=plt.subplots(figsize=(7,4))
for sc in SCN:
    cfg=apply_scenario_network_overrides(ExperimentConfig.from_file("src/config/default.yaml"),scen[sc])
    prof=DemandProfile(cfg,scen[sc]); t=[k*3 for k in range(20)]
    tot=[sum(prof.at(k*180).freeway_mainline.values())+sum(prof.at(k*180).urban_boundary.values())+sum(prof.at(k*180).ramp_arrival.values()) for k in range(20)]
    ax.plot(t,tot,marker="o",ms=3,label=SLAB[sc])
ax.set_xlabel("time (min)"); ax.set_ylabel("total demand rate (veh/h)")
ax.set_title("Fig.1  Demand profiles by scenario"); ax.legend()
fig.savefig(f"{OUT}/fig01_demand_profiles.png"); plt.close(fig)

# FIG2 demand composition
fig,ax=plt.subplots(figsize=(7,4)); dt=0.05
comp={s:{"freeway":0,"urban":0,"on_ramp":0,"off_ramp":0} for s in SCN}
for sc in SCN:
    cfg=apply_scenario_network_overrides(ExperimentConfig.from_file("src/config/default.yaml"),scen[sc]); net=cfg.network
    prof=DemandProfile(cfg,scen[sc])
    for k in range(20):
        d=prof.at(k*180)
        comp[sc]["freeway"]+=sum(d.freeway_mainline.values())*dt
        comp[sc]["urban"]+=sum(d.urban_boundary.values())*dt
        comp[sc]["on_ramp"]+=sum(d.ramp_arrival.values())*dt
        comp[sc]["off_ramp"]+=sum(d.freeway_mainline.get(fw,0)*float(net.off_ramp_split_ratio.get(o,0)) for o,fw in net.off_ramp_from_freeway.items())*dt
x=np.arange(len(SCN)); parts=["urban","freeway","on_ramp","off_ramp"]
pcol={"urban":"#4c72b0","freeway":"#dd8452","on_ramp":"#55a868","off_ramp":"#c44e52"}
bot=np.zeros(len(SCN))
for p in parts:
    vals=np.array([comp[s][p] for s in SCN]); ax.bar(x,vals,bottom=bot,label=p,color=pcol[p]); bot+=vals
ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCN]); ax.set_ylabel("total demand (veh)")
ax.set_title("Fig.2  Demand composition"); ax.legend(ncol=4,fontsize=9)
fig.savefig(f"{OUT}/fig02_demand_composition.png"); plt.close(fig)

# FIG3 macro TTT
fig,ax=plt.subplots(figsize=(8,4.2)); x=np.arange(len(SCN)); w=0.2
for i,c in enumerate(CTRL):
    ax.bar(x+(i-1.5)*w,[sval(s,c,"total_ttt") or 0 for s in SCN],w,label=CLAB[c],color=COL[c])
ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCN]); ax.set_ylabel("Total TTT (veh*h)")
ax.set_title("Fig.3  Total TTT by scenario and controller"); ax.legend()
fig.savefig(f"{OUT}/fig03_macro_ttt.png"); plt.close(fig)

# FIG4 improvement
fig,ax=plt.subplots(figsize=(8,4.2)); x=np.arange(len(SCN)); w=0.25
for i,c in enumerate(["WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]):
    ax.bar(x+(i-1)*w,[sval(s,c,"total_ttt_improvement_vs_no_control_pct") or 0 for s in SCN],w,label=CLAB[c],color=COL[c])
ax.axhline(0,color="k",lw=0.8); ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCN])
ax.set_ylabel("TTT improvement vs no-control (%)"); ax.set_title("Fig.4  TTT improvement over no-control"); ax.legend()
fig.savefig(f"{OUT}/fig04_improvement.png"); plt.close(fig)

# FIG5 throughput vs terminal
fig,axes=plt.subplots(1,2,figsize=(10,4.2))
for ax,sc in zip(axes,["peak_demand","incident_or_capacity_drop"]):
    cs=CTRL; comp_=[sval(sc,c,"completed_vehicles") or 0 for c in cs]; term=[sval(sc,c,"terminal_total_vehicles") or 0 for c in cs]
    x=np.arange(len(cs)); w=0.38
    ax.bar(x-w/2,comp_,w,label="completed",color="#55a868"); ax.bar(x+w/2,term,w,label="terminal",color="#c44e52")
    ax.set_xticks(x); ax.set_xticklabels([CLAB[c] for c in cs],rotation=15,fontsize=9); ax.set_title(SLAB[sc]); ax.set_ylabel("vehicles")
axes[0].legend()
fig.suptitle("Fig.5  Completed vs terminal vehicles")
fig.savefig(f"{OUT}/fig05_throughput_terminal.png"); plt.close(fig)

# FIG6 freeway/urban decomposition
fig,ax=plt.subplots(figsize=(8,4.2)); cs=["WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]
labels=[];fwy=[];urb=[]
for sc in ["peak_demand","incident_or_capacity_drop"]:
    for c in cs: labels.append(f"{SLAB[sc]}\n{CLAB[c]}"); fwy.append(sval(sc,c,"freeway_ttt") or 0); urb.append(sval(sc,c,"urban_ttt") or 0)
x=np.arange(len(labels)); ax.bar(x,fwy,label="freeway TTT",color="#dd8452"); ax.bar(x,urb,bottom=fwy,label="urban TTT",color="#4c72b0")
ax.set_xticks(x); ax.set_xticklabels(labels,fontsize=8); ax.set_ylabel("TTT (veh*h)"); ax.set_title("Fig.6  Freeway/urban TTT decomposition"); ax.legend()
fig.savefig(f"{OUT}/fig06_freeway_urban.png"); plt.close(fig)

# FIG7 leader targets
ps=ts("peak_demand","PROPOSED-STACKELBERG","progress_summary.csv")
t=[int(float(r["step"]))*3 for r in ps]; npv=[fl(r.get("N_P_star")) for r in ps]; nuf=[fl(r.get("N_UF_star")) for r in ps]
fig,ax1=plt.subplots(figsize=(7.5,4))
ax1.plot(t,npv,marker="o",ms=3,color="#d62728"); ax1.set_xlabel("time (min)"); ax1.set_ylabel("N_P* (veh)",color="#d62728"); ax1.tick_params(axis="y",labelcolor="#d62728")
ax2=ax1.twinx(); ax2.plot(t,nuf,marker="s",ms=3,color="#1f77b4"); ax2.grid(False); ax2.set_ylabel("N_UF* (veh/h)",color="#1f77b4"); ax2.tick_params(axis="y",labelcolor="#1f77b4")
ax1.set_title("Fig.7  Leader targets over time (peak, P-Stack)")
fig.savefig(f"{OUT}/fig07_leader_targets.png"); plt.close(fig)

# FIG8 step TTT
fig,ax=plt.subplots(figsize=(7.5,4))
for c in CTRL:
    p=ts("peak_demand",c,"progress_summary.csv")
    if not p: continue
    ax.plot([int(float(r["step"]))*3 for r in p],[fl(r.get("step_total_ttt")) for r in p],marker="o",ms=2.5,label=CLAB[c],color=COL[c])
ax.set_xlabel("time (min)"); ax.set_ylabel("step TTT (veh*h)"); ax.set_title("Fig.8  Per-step TTT over time (peak)"); ax.legend()
fig.savefig(f"{OUT}/fig08_step_ttt.png"); plt.close(fig)

# FIG9 control activation
def meanseries(sc,c,prefix):
    ct=ts(sc,c,"control_timeseries.csv")
    if not ct: return None,None
    cols=[k for k in ct[0] if k.startswith(prefix)]
    return [i*3 for i in range(len(ct))],[np.mean([fl(r[k]) for k in cols if fl(r.get(k)) is not None]) for r in ct]
fig,axes=plt.subplots(1,3,figsize=(13,3.8))
for ax,(pref,lab) in zip(axes,[("ramp_metering_","ramp metering (veh/h)"),("green_","green (s)"),("offset_","offset (s)")]):
    for c in ["PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]:
        t,v=meanseries("peak_demand",c,pref)
        if t: ax.plot(t,v,label=CLAB[c],color=COL[c],marker="o",ms=2)
    ax.set_xlabel("time (min)"); ax.set_title(lab)
axes[0].legend()
fig.suptitle("Fig.9  Network-mean control activation (peak)")
fig.savefig(f"{OUT}/fig09_control_activation.png"); plt.close(fig)

# FIG10 ramp micro coupling
def stcol(sc,c,col):
    st=ts(sc,c,"state_timeseries.csv")
    if not st or col not in st[0]: return None,None
    return [i*3 for i in range(len(st))],[fl(r.get(col)) for r in st]
def ctcol(sc,c,col):
    ct=ts(sc,c,"control_timeseries.csv")
    if not ct or col not in ct[0]: return None,None
    return [i*3 for i in range(len(ct))],[fl(r.get(col)) for r in ct]
fig,ax1=plt.subplots(figsize=(7.5,4.2)); c="PROPOSED-FOLLOWERS-ONLY"
t,q=stcol("peak_demand",c,"ramp_queue_R_D_W"); _,m=ctcol("peak_demand",c,"ramp_metering_R_D_W")
st=ts("peak_demand",c,"state_timeseries.csv"); fwcols=[k for k in st[0] if k.startswith("freeway_density_FW_W")]
fwd=[np.mean([fl(r[k]) for k in fwcols if fl(r.get(k)) is not None]) for r in st] if fwcols else None
ax1.plot(t,q,color="#55a868",marker="o",ms=2,label="on-ramp queue R_D_W (veh)")
ax1.set_xlabel("time (min)"); ax1.set_ylabel("on-ramp queue (veh)",color="#55a868"); ax1.tick_params(axis="y",labelcolor="#55a868")
ax2=ax1.twinx(); ax2.grid(False); ax2.plot(t,m,color="#d62728",marker="s",ms=2,label="metering rate (veh/h)")
if fwd is not None: ax2.plot(t,np.array(fwd)*10,color="#1f77b4",ls="--",label="FW_W density x10")
ax2.set_ylabel("metering / scaled density")
l1,la1=ax1.get_legend_handles_labels(); l2,la2=ax2.get_legend_handles_labels(); ax1.legend(l1+l2,la1+la2,fontsize=8,loc="upper left")
ax1.set_title("Fig.10  Ramp-level (micro) coupling - PFO, peak, R_D_W")
fig.savefig(f"{OUT}/fig10_coupling_micro.png"); plt.close(fig)

# FIG11 network macro coupling
fig,(axA,axB)=plt.subplots(1,2,figsize=(11,4.2))
for c in CTRL:
    p=ts("peak_demand",c,"progress_summary.csv")
    if not p: continue
    axA.plot([int(float(r["step"]))*3 for r in p],[fl(r.get("cumulative_total_ttt")) for r in p],label=CLAB[c],color=COL[c])
axA.set_xlabel("time (min)"); axA.set_ylabel("cumulative TTT (veh*h)"); axA.set_title("cumulative TTT"); axA.legend(fontsize=9)
for c in ["NO-CONTROL","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]:
    st=ts("peak_demand",c,"state_timeseries.csv")
    if not st: continue
    rq=[k for k in st[0] if k.startswith("ramp_queue_")]
    axB.plot([i*3 for i in range(len(st))],[sum(fl(r[k]) or 0 for k in rq) for r in st],label=CLAB[c],color=COL[c])
axB.set_xlabel("time (min)"); axB.set_ylabel("total on-ramp queue (veh)"); axB.set_title("aggregate on-ramp queue"); axB.legend(fontsize=9)
fig.suptitle("Fig.11  Network-level (macro) coupling response (peak)")
fig.savefig(f"{OUT}/fig11_coupling_macro.png"); plt.close(fig)

# FIG12 computation
fig,(a1,a2)=plt.subplots(1,2,figsize=(10,4)); cs=["WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]
comp=[np.mean([sval(s,c,"computation_time_sec") or 0 for s in SCN]) for c in cs]
a1.bar([CLAB[c] for c in cs],comp,color=[COL[c] for c in cs]); a1.set_ylabel("computation time (s)"); a1.set_title("computation cost (3600 s run)")
a2.bar([CLAB[c] for c in cs],[x/3600 for x in comp],color=[COL[c] for c in cs]); a2.axhline(1.0,color="k",ls="--",lw=0.8,label="real-time limit")
a2.set_ylabel("real-time ratio"); a2.set_title("real-time ratio (<1 ok)"); a2.legend()
fig.suptitle("Fig.12  Computational practicality")
fig.savefig(f"{OUT}/fig12_computation.png"); plt.close(fig)

# FIG13 accumulation trajectory
fig,ax=plt.subplots(figsize=(7.5,4))
for c in ["NO-CONTROL","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]:
    t,acc=stcol("peak_demand",c,"urban_protected_accumulation_veh")
    if t: ax.plot(t,acc,label=CLAB[c],color=COL[c])
ax.axhline(509.45,color="k",ls="--",lw=0.9,label="N_P,crit ~ 509")
ax.set_xlabel("time (min)"); ax.set_ylabel("protected accumulation N_P (veh)"); ax.set_title("Fig.13  Protected accumulation trajectory (peak)"); ax.legend(fontsize=9)
fig.savefig(f"{OUT}/fig13_accumulation.png"); plt.close(fig)

print("DONE:", sorted(os.path.basename(p) for p in glob.glob(f"{OUT}/*.png")))