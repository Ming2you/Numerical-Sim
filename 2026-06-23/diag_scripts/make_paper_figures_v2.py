# 사후분석 논문급 그림 v2 — Times New Roman + 수식 subscript + 8시나리오 + green-queue split 정렬 + skew + perimeter.
import os, csv, glob
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from src.models.state import ExperimentConfig
from src.models.urban_queue_model import movement_storage_capacity
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides

plt.rcParams.update({
    "font.family": "Times New Roman", "mathtext.fontset": "stix",
    "font.size": 12, "axes.grid": True, "grid.alpha": 0.3, "axes.axisbelow": True,
    "figure.dpi": 200, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
})
D1 = "outputs/analysis_matrix_3600"; D2 = "outputs/analysis_matrix_3600_extra"
OUT = "reports/figures"; os.makedirs(OUT, exist_ok=True)
DIR = {"medium_demand":D1,"peak_demand":D1,"oversaturated_demand":D1,"incident_or_capacity_drop":D1,
       "heavy_demand_140":D2,"heavy_demand_150":D2,"skew_peak":D2,"skew_heavy":D2}
# 수요 오름차순 + skew 별도
SCN = ["medium_demand","peak_demand","heavy_demand_140","heavy_demand_150","oversaturated_demand","incident_or_capacity_drop","skew_peak","skew_heavy"]
SLAB = {"medium_demand":"medium","peak_demand":"peak","heavy_demand_140":"heavy1.40","heavy_demand_150":"heavy1.50",
        "oversaturated_demand":"oversat","incident_or_capacity_drop":"incident","skew_peak":"skew-peak","skew_heavy":"skew-heavy"}
CTRL=["NO-CONTROL","WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]
CLAB={"NO-CONTROL":"No-control","WU-CD-F":"P-WU","PROPOSED-FOLLOWERS-ONLY":"PFO","PROPOSED-STACKELBERG":"P-Stack"}
COL={"NO-CONTROL":"#8c8c8c","WU-CD-F":"#ff7f0e","PROPOSED-FOLLOWERS-ONLY":"#1f77b4","PROPOSED-STACKELBERG":"#d62728"}

def rd(p): return list(csv.DictReader(open(p,encoding="utf-8"))) if os.path.exists(p) else []
def fl(x):
    try: return float(x)
    except: return None
def ts(sc,c,f): return rd(f"{DIR[sc]}/runs/{sc}/{c}/{f}")
_summ=None
def summ():
    global _summ
    if _summ is None:
        _summ=[]
        for d in (D1,D2):
            _summ+=rd(f"{d}/analysis/summary_with_no_control.csv")+rd(f"{d}/all_no_control_summary.csv")
    return _summ
def sval(sc,c,k):
    r=next((r for r in summ() if r.get("scenario")==sc and r.get("controller_id")==c),None)
    return fl(r.get(k)) if r else None

scen=load_scenarios("src/config/scenarios.yaml")
cfg0=ExperimentConfig.from_file("src/config/default.yaml")
SIGNALS=list(cfg0.network.signals)
specs=cfg0.network.urban_movements

# ---- FIG1 demand profiles (수요-스케일 시나리오) ----
fig,ax=plt.subplots(figsize=(7,4))
for sc in ["medium_demand","peak_demand","heavy_demand_140","heavy_demand_150","oversaturated_demand","incident_or_capacity_drop"]:
    cfg=apply_scenario_network_overrides(ExperimentConfig.from_file("src/config/default.yaml"),scen[sc])
    prof=DemandProfile(cfg,scen[sc])
    t=[k*3 for k in range(20)]
    tot=[sum(prof.at(k*180).freeway_mainline.values())+sum(prof.at(k*180).urban_boundary.values())+sum(prof.at(k*180).ramp_arrival.values()) for k in range(20)]
    ax.plot(t,tot,marker="o",ms=3,label=SLAB[sc])
ax.set_xlabel("time (min)"); ax.set_ylabel("total demand rate (veh/h)")
ax.set_title("Demand profiles by scenario"); ax.legend(fontsize=9)
fig.savefig(f"{OUT}/fig01_demand_profiles.png"); plt.close(fig)

# ---- FIG2 demand composition ----
fig,ax=plt.subplots(figsize=(8,4)); dt=0.05
parts=["urban","freeway","on_ramp","off_ramp"]; pcol={"urban":"#4c72b0","freeway":"#dd8452","on_ramp":"#55a868","off_ramp":"#c44e52"}
comp={s:{p:0 for p in parts} for s in SCN}
for sc in SCN:
    cfg=apply_scenario_network_overrides(ExperimentConfig.from_file("src/config/default.yaml"),scen[sc]); net=cfg.network
    prof=DemandProfile(cfg,scen[sc])
    for k in range(20):
        d=prof.at(k*180)
        comp[sc]["freeway"]+=sum(d.freeway_mainline.values())*dt; comp[sc]["urban"]+=sum(d.urban_boundary.values())*dt
        comp[sc]["on_ramp"]+=sum(d.ramp_arrival.values())*dt
        comp[sc]["off_ramp"]+=sum(d.freeway_mainline.get(fw,0)*float(net.off_ramp_split_ratio.get(o,0)) for o,fw in net.off_ramp_from_freeway.items())*dt
x=np.arange(len(SCN)); bot=np.zeros(len(SCN))
for p in parts:
    v=np.array([comp[s][p] for s in SCN]); ax.bar(x,v,bottom=bot,label=p,color=pcol[p]); bot+=v
ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCN],rotation=30,ha="right",fontsize=9); ax.set_ylabel("total demand (veh)")
ax.set_title("Demand composition"); ax.legend(ncol=4,fontsize=9)
fig.savefig(f"{OUT}/fig02_demand_composition.png"); plt.close(fig)

# ---- FIG3 skew visualization (peak vs skew_peak per-gate, total preserved) ----
fig,ax=plt.subplots(figsize=(8,4))
gates=cfg0.network.boundary_in_links
def gate_dem(sc):
    cfg=apply_scenario_network_overrides(ExperimentConfig.from_file("src/config/default.yaml"),scen[sc])
    d=DemandProfile(cfg,scen[sc]).at(900.0); return [d.urban_boundary[g] for g in gates]
x=np.arange(len(gates)); w=0.4
ax.bar(x-w/2,gate_dem("peak_demand"),w,label="peak (gradient)",color="#1f77b4")
ax.bar(x+w/2,gate_dem("skew_peak"),w,label="skew-peak (hotspot, same total)",color="#d62728")
ax.set_xticks(x); ax.set_xticklabels([g.replace("in_","") for g in gates],rotation=30,ha="right",fontsize=9)
ax.set_ylabel("boundary inflow demand (veh/h)"); ax.set_title("Spatial demand skew (total preserved)"); ax.legend(fontsize=9)
fig.savefig(f"{OUT}/fig03_skew_demand.png"); plt.close(fig)

# ---- FIG4 improvement % (8 scenarios x 3 ctrl) ----
fig,ax=plt.subplots(figsize=(9.5,4.4)); x=np.arange(len(SCN)); w=0.25
for i,c in enumerate(["WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]):
    ax.bar(x+(i-1)*w,[sval(s,c,"total_ttt_improvement_vs_no_control_pct") or 0 for s in SCN],w,label=CLAB[c],color=COL[c])
ax.axhline(0,color="k",lw=0.8); ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCN],rotation=30,ha="right",fontsize=9)
ax.set_ylabel("TTT improvement vs no-control (%)"); ax.set_title("TTT improvement over no-control"); ax.legend()
fig.savefig(f"{OUT}/fig04_improvement.png"); plt.close(fig)

# ---- FIG5 P-Stack minus PFO gap (핵심: leader 가치) ----
fig,ax=plt.subplots(figsize=(9,4.2))
gap=[(sval(s,"PROPOSED-STACKELBERG","total_ttt_improvement_vs_no_control_pct") or 0)-(sval(s,"PROPOSED-FOLLOWERS-ONLY","total_ttt_improvement_vs_no_control_pct") or 0) for s in SCN]
colors=["#d62728" if g>0 else "#8c8c8c" for g in gap]
ax.bar(np.arange(len(SCN)),gap,color=colors)
ax.axhline(0,color="k",lw=0.8)
ax.set_xticks(np.arange(len(SCN))); ax.set_xticklabels([SLAB[s] for s in SCN],rotation=30,ha="right",fontsize=9)
ax.set_ylabel("P-Stack $-$ PFO improvement (pp)"); ax.set_title("Leader value: P-Stack advantage over PFO")
for i,g in enumerate(gap): ax.text(i,g+(0.3 if g>=0 else -0.6),f"{g:+.1f}",ha="center",fontsize=8)
fig.savefig(f"{OUT}/fig05_pstack_pfo_gap.png"); plt.close(fig)

# ---- FIG6 throughput vs terminal (heavy_150, skew_heavy) ----
fig,axes=plt.subplots(1,2,figsize=(10,4.2))
for ax,sc in zip(axes,["heavy_demand_150","skew_heavy"]):
    comp_=[sval(sc,c,"completed_vehicles") or 0 for c in CTRL]; term=[sval(sc,c,"terminal_total_vehicles") or 0 for c in CTRL]
    x=np.arange(len(CTRL)); w=0.38
    ax.bar(x-w/2,comp_,w,label="completed",color="#55a868"); ax.bar(x+w/2,term,w,label="terminal",color="#c44e52")
    ax.set_xticks(x); ax.set_xticklabels([CLAB[c] for c in CTRL],rotation=15,fontsize=9); ax.set_title(SLAB[sc]); ax.set_ylabel("vehicles")
axes[0].legend()
fig.suptitle("Completed vs terminal vehicles")
fig.savefig(f"{OUT}/fig06_throughput_terminal.png"); plt.close(fig)

# ---- FIG7 freeway/urban decomposition (heavy_150, skew_heavy, incident) ----
fig,ax=plt.subplots(figsize=(9,4.2)); cs=["WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]
labels=[];fwy=[];urb=[]
for sc in ["heavy_demand_150","skew_heavy","incident_or_capacity_drop"]:
    for c in cs: labels.append(f"{SLAB[sc]}\n{CLAB[c]}"); fwy.append(sval(sc,c,"freeway_ttt") or 0); urb.append(sval(sc,c,"urban_ttt") or 0)
x=np.arange(len(labels)); ax.bar(x,fwy,label="freeway TTT",color="#dd8452"); ax.bar(x,urb,bottom=fwy,label="urban TTT",color="#4c72b0")
ax.set_xticks(x); ax.set_xticklabels(labels,fontsize=7.5); ax.set_ylabel("TTT (veh·h)"); ax.set_title("Freeway / urban TTT decomposition"); ax.legend()
fig.savefig(f"{OUT}/fig07_freeway_urban.png"); plt.close(fig)

# ---- FIG8 leader targets (heavy_150) ----
ps=ts("heavy_demand_150","PROPOSED-STACKELBERG","progress_summary.csv")
t=[int(float(r["step"]))*3 for r in ps]; npv=[fl(r.get("N_P_star")) for r in ps]; nuf=[fl(r.get("N_UF_star")) for r in ps]
fig,ax1=plt.subplots(figsize=(7.5,4))
ax1.plot(t,npv,marker="o",ms=3,color="#d62728"); ax1.set_xlabel("time (min)")
ax1.set_ylabel(r"$N_P^{\ast}$ (veh)",color="#d62728"); ax1.tick_params(axis="y",labelcolor="#d62728")
ax2=ax1.twinx(); ax2.plot(t,nuf,marker="s",ms=3,color="#1f77b4"); ax2.grid(False)
ax2.set_ylabel(r"$N_{UF}^{\ast}$ (veh/h)",color="#1f77b4"); ax2.tick_params(axis="y",labelcolor="#1f77b4")
ax1.set_title(r"Leader targets $N_P^{\ast}$, $N_{UF}^{\ast}$ over time (heavy1.50, P-Stack)")
fig.savefig(f"{OUT}/fig08_leader_targets.png"); plt.close(fig)

# ---- FIG9 step TTT divergence (heavy_150) ----
fig,ax=plt.subplots(figsize=(7.5,4))
for c in CTRL:
    p=ts("heavy_demand_150",c,"progress_summary.csv")
    if not p: continue
    ax.plot([int(float(r["step"]))*3 for r in p],[fl(r.get("step_total_ttt")) for r in p],marker="o",ms=2.5,label=CLAB[c],color=COL[c])
ax.set_xlabel("time (min)"); ax.set_ylabel("step TTT (veh·h)"); ax.set_title("Per-step TTT over time (heavy1.50)"); ax.legend()
fig.savefig(f"{OUT}/fig09_step_ttt.png"); plt.close(fig)

# ---- green-queue SPLIT alignment 계산 ----
p1mv={S:[m for m,s in specs.items() if s.get("signal")==S and str(s.get("phase",""))==f"{S}_p1"] for S in SIGNALS}
p2mv={S:[m for m,s in specs.items() if s.get("signal")==S and str(s.get("phase",""))==f"{S}_p2"] for S in SIGNALS}
def green_queue_align(sc,c):
    st=ts(sc,c,"state_timeseries.csv"); ct=ts(sc,c,"control_timeseries.csv")
    if not st or not ct: return None
    cors=[]
    for S in SIGNALS:
        gp1=f"green_{S}_p1"; gp2=f"green_{S}_p2"
        if gp1 not in ct[0]: continue
        gsplit=[]; qsplit=[]
        for rs,rc in zip(st,ct):
            q1=sum(fl(rs.get(f"movement_queue_{m}")) or 0 for m in p1mv[S]); q2=sum(fl(rs.get(f"movement_queue_{m}")) or 0 for m in p2mv[S])
            g1=fl(rc.get(gp1)); g2=fl(rc.get(gp2))
            if g1 is None or g2 is None: continue
            gsplit.append(g1-g2); qsplit.append(q1-q2)
        if len(gsplit)>3:
            ga=np.array(gsplit); qa=np.array(qsplit)
            if ga.std()>1e-6 and qa.std()>1e-6: cors.append(float(np.corrcoef(ga,qa)[0,1]))
    return np.mean(cors) if cors else None

# ---- FIG10 green-queue split alignment (PFO vs P-Stack, scenarios) ----
fig,ax=plt.subplots(figsize=(9,4.2)); x=np.arange(len(SCN)); w=0.38
for i,c in enumerate(["PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]):
    vals=[(green_queue_align(s,c) or 0) for s in SCN]
    ax.bar(x+(i-0.5)*w,vals,w,label=CLAB[c],color=COL[c])
ax.axhline(0,color="k",lw=0.8); ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCN],rotation=30,ha="right",fontsize=9)
ax.set_ylabel("corr(green split, queue split)"); ax.set_title("Green-split follows queue asymmetry (per-signal, mean)"); ax.legend()
fig.savefig(f"{OUT}/fig10_green_queue_align.png"); plt.close(fig)

# ---- FIG11 ramp-feeding green skew (D,F vs A,B,C) ----
def mean_green_split(sc,c,sigset):
    ct=ts(sc,c,"control_timeseries.csv")
    if not ct: return None
    vals=[]
    for r in ct:
        for S in sigset:
            g1=fl(r.get(f"green_{S}_p1")); g2=fl(r.get(f"green_{S}_p2"))
            if g1 is not None and g2 is not None: vals.append(abs(g1-g2))
    return np.mean(vals) if vals else None
fig,ax=plt.subplots(figsize=(8.5,4.2)); x=np.arange(len(SCN)); w=0.38
for i,c in enumerate(["PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]):
    vals=[(mean_green_split(s,c,["D","F"]) or 0) for s in SCN]
    ax.bar(x+(i-0.5)*w,vals,w,label=CLAB[c],color=COL[c])
ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCN],rotation=30,ha="right",fontsize=9)
ax.set_ylabel("|green split| at ramp signals D,F (s)"); ax.set_title("Green differentiation at ramp-feeding signals (D,F)"); ax.legend()
fig.savefig(f"{OUT}/fig11_ramp_green.png"); plt.close(fig)

# ---- FIG12 ramp-level micro coupling (skew_heavy, PFO, R_D_W) ----
def stcol(sc,c,col):
    st=ts(sc,c,"state_timeseries.csv")
    if not st or col not in st[0]: return None,None
    return [i*3 for i in range(len(st))],[fl(r.get(col)) for r in st]
def ctcol(sc,c,col):
    ct=ts(sc,c,"control_timeseries.csv")
    if not ct or col not in ct[0]: return None,None
    return [i*3 for i in range(len(ct))],[fl(r.get(col)) for r in ct]
fig,ax1=plt.subplots(figsize=(7.5,4.2)); SC_M="skew_heavy"; c="PROPOSED-FOLLOWERS-ONLY"
t,q=stcol(SC_M,c,"ramp_queue_R_D_W"); _,m=ctcol(SC_M,c,"ramp_metering_R_D_W")
ax1.plot(t,q,color="#55a868",marker="o",ms=2,label="on-ramp queue R_D_W (veh)")
ax1.set_xlabel("time (min)"); ax1.set_ylabel("on-ramp queue (veh)",color="#55a868"); ax1.tick_params(axis="y",labelcolor="#55a868")
ax2=ax1.twinx(); ax2.grid(False); ax2.plot(t,m,color="#d62728",marker="s",ms=2,label="metering rate (veh/h)")
ax2.set_ylabel("metering rate (veh/h)",color="#d62728"); ax2.tick_params(axis="y",labelcolor="#d62728")
l1,la1=ax1.get_legend_handles_labels(); l2,la2=ax2.get_legend_handles_labels(); ax1.legend(l1+l2,la1+la2,fontsize=8,loc="upper left")
ax1.set_title("Ramp-level (micro) coupling — PFO, skew-heavy, R_D_W")
fig.savefig(f"{OUT}/fig12_coupling_micro.png"); plt.close(fig)

# ---- FIG13 network macro coupling (heavy_150) ----
fig,(axA,axB)=plt.subplots(1,2,figsize=(11,4.2))
for c in CTRL:
    p=ts("heavy_demand_150",c,"progress_summary.csv")
    if not p: continue
    axA.plot([int(float(r["step"]))*3 for r in p],[fl(r.get("cumulative_total_ttt")) for r in p],label=CLAB[c],color=COL[c])
axA.set_xlabel("time (min)"); axA.set_ylabel("cumulative TTT (veh·h)"); axA.set_title("cumulative TTT"); axA.legend(fontsize=9)
for c in ["NO-CONTROL","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]:
    st=ts("heavy_demand_150",c,"state_timeseries.csv")
    if not st: continue
    rq=[k for k in st[0] if k.startswith("ramp_queue_")]
    axB.plot([i*3 for i in range(len(st))],[sum(fl(r[k]) or 0 for k in rq) for r in st],label=CLAB[c],color=COL[c])
axB.set_xlabel("time (min)"); axB.set_ylabel("total on-ramp queue (veh)"); axB.set_title("aggregate on-ramp queue"); axB.legend(fontsize=9)
fig.suptitle("Network-level (macro) coupling response (heavy1.50)")
fig.savefig(f"{OUT}/fig13_coupling_macro.png"); plt.close(fig)

# ---- FIG14 realized half-cap movement excess, 3 controllers (heavy_150) ----
# leader가 벌점화하는 half-cap 초과분을 *실제 시뮬 state*에서 컨트롤러별로 재계산해 비교한다.
# (leader 진단값은 P-Stack에만 있고 horizon-합산이라 비교 불가 -> 동일 공식을 단일 state에 적용.)
# 우상향 자체는 1.5x 수요의 oversaturation(모두 증가); 곡선 간 격차가 leader 통제 증거다.
_thr=float(cfg0.leader.mfd_storage_threshold_ratio)
_bcap=float(cfg0.leader.mfd_boundary_queue_capacity_veh)
_cap={m:(_bcap if str(s.get("kind","")) in {"boundary_in","boundary_out"}
         else max(float(movement_storage_capacity(cfg0,m,s)),1e-9))
      for m,s in cfg0.network.urban_movements.items()}
def _halfcap_excess(sc,c):
    st=ts(sc,c,"state_timeseries.csv")
    if not st: return None,None
    t=[i*3 for i in range(len(st))]
    ex=[sum(max(0.0,(fl(r.get(f"movement_queue_{m}")) or 0.0)-_thr*cap) for m,cap in _cap.items()) for r in st]
    return t,ex
fig,ax=plt.subplots(figsize=(7.8,4.2))
for c in ["NO-CONTROL","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]:
    t,ex=_halfcap_excess("heavy_demand_150",c)
    if t: ax.plot(t,ex,label=CLAB[c],color=COL[c],marker="o",ms=2)
ax.set_ylim(bottom=0)  # 초과분은 >=0; 축 여백이 만드는 가짜 음수 눈금 제거
ax.set_xlabel("time (min)"); ax.set_ylabel("realized half-cap movement excess (veh)")
ax.legend(fontsize=9,loc="upper left")
ax1=ax  # 아래 공통 마무리 코드 호환
ax1.set_title("Realized half-cap movement excess (heavy1.50): leader suppresses, not prevents")
fig.savefig(f"{OUT}/fig14_accumulation.png"); plt.close(fig)

# ---- FIG15 B_sum redistribution under skew ----
fig,ax=plt.subplots(figsize=(7.5,4))
for c in ["NO-CONTROL","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]:
    p=ts("skew_peak",c,"progress_summary.csv")
    if not p or "mean_B_sum_step" not in p[0]: continue
    ax.plot([int(float(r["step"]))*3 for r in p],[fl(r.get("mean_B_sum_step")) for r in p],label=CLAB[c],color=COL[c])
ax.set_xlabel("time (min)"); ax.set_ylabel("boundary imbalance $B_{sum}$"); ax.set_title("Boundary balance under spatial skew (skew-peak)"); ax.legend(fontsize=9)
fig.savefig(f"{OUT}/fig15_skew_balance.png"); plt.close(fig)

# ---- FIG16 VSL (incident) ----
fig,ax=plt.subplots(figsize=(7.5,4))
for c in CTRL:
    ct=ts("incident_or_capacity_drop",c,"control_timeseries.csv")
    if not ct: continue
    vc=[k for k in ct[0] if k.startswith("vsl")]
    if not vc: continue
    vals=[np.mean([fl(r[k]) for k in vc if fl(r.get(k)) is not None]) for r in ct]
    ax.plot([i*3 for i in range(len(ct))],vals,label=CLAB[c],color=COL[c],marker="o",ms=2)
ax.set_xlabel("time (min)"); ax.set_ylabel("network-mean VSL (km/h)"); ax.set_title("VSL activation (incident / capacity-drop)"); ax.legend(fontsize=9)
fig.savefig(f"{OUT}/fig16_vsl.png"); plt.close(fig)

# ---- FIG17 computation / real-time ratio ----
fig,(a1,a2)=plt.subplots(1,2,figsize=(10,4)); cs=["WU-CD-F","PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]
comp=[np.mean([sval(s,c,"computation_time_sec") or 0 for s in SCN]) for c in cs]
a1.bar([CLAB[c] for c in cs],comp,color=[COL[c] for c in cs]); a1.set_ylabel("computation time (s)"); a1.set_title("computation cost (3600 s run)")
a2.bar([CLAB[c] for c in cs],[x/3600 for x in comp],color=[COL[c] for c in cs]); a2.axhline(1.0,color="k",ls="--",lw=0.8,label="real-time limit")
a2.set_ylabel("real-time ratio"); a2.set_title("real-time ratio (<1 = faster than real time)"); a2.legend()
fig.suptitle("Computational practicality")
fig.savefig(f"{OUT}/fig17_computation.png"); plt.close(fig)

# ---- 콘솔: green-queue/ramp-skew/skew-B_sum 정량 (md용) ----
print("=== green-queue split alignment (mean corr) ===")
for sc in ["peak_demand","heavy_demand_150","skew_peak","skew_heavy"]:
    print(f"  {sc}: PFO={green_queue_align(sc,'PROPOSED-FOLLOWERS-ONLY'):+.2f}  P-Stack={green_queue_align(sc,'PROPOSED-STACKELBERG'):+.2f}")
print("=== |green split| at D,F (ramp) vs A,B,C ===")
for sc in ["skew_heavy"]:
    for c in ["PROPOSED-FOLLOWERS-ONLY","PROPOSED-STACKELBERG"]:
        print(f"  {sc} {CLAB[c]}: DF={mean_green_split(sc,c,['D','F']):.1f}  ABC={mean_green_split(sc,c,['A','B','C']):.1f}")
print("DONE:", len(glob.glob(f"{OUT}/*.png")), "figs")
