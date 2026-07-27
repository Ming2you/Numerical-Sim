# incident 격자 probe 분석 — 사고 때 리더의 N_UF 레버가 무력화되는지 검증 (2026-07-24)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

G = "outputs/_diag/gridprobe_inc/grid.grid.csv"
C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG = f"outputs/_diag/gridprobe_inc/{C}/run_log.csv"
g = pd.read_csv(G)
for k in ["step", "N_P", "N_UF", "objective", "sel_N_P", "sel_N_UF"]:
    g[k] = pd.to_numeric(g[k], errors="coerce")
g = g.dropna(subset=["N_P", "N_UF", "objective"])

log = pd.read_csv(LOG) if os.path.exists(LOG) else None
def lv(step, col):
    if log is None or col not in log.columns: return np.nan
    s = pd.to_numeric(log["step"], errors="coerce").to_numpy()
    i = np.where(s == step)[0]
    return pd.to_numeric(log[col], errors="coerce").to_numpy()[i[0]] if len(i) else np.nan

steps = sorted(g["step"].dropna().unique())
LABEL = {8: "pre-incident", 14: "incident", 17: "incident", 25: "recovery"}
print("=" * 98)
print("incident 격자 probe — N_UF 방향 J_L 변화 (평평하면 레버 무력)")
for s in steps:
    sub = g[g["step"] == s]
    byn = sub.groupby("N_UF")["objective"].mean()
    rng = byn.max() - byn.min()
    # 포화 판정: 상위 절반 구간의 변동
    hi = byn[byn.index >= np.median(byn.index.to_numpy())]
    flat = hi.max() - hi.min()
    oE, oW = lv(s, "leader_nuf_omega_FW_E"), lv(s, "leader_nuf_omega_FW_W")
    # 포화점 = max(cap/omega), cap=3000/link
    sat = max(3000.0 / max(oE, 1e-9), 3000.0 / max(oW, 1e-9))
    print(f"\n[step {int(s)} {LABEL.get(int(s),''):13}] ω=({oE:.2f},{oW:.2f})  이론 포화점 N_UF={sat:,.0f}")
    print(f"   J_L 전체변동={rng:8.2f}   상위절반 변동={flat:8.4f}  "
          f"{'← 무차별(레버 무력)' if flat < 0.01 * max(abs(byn.mean()),1) else ''}")
    print("   " + "  ".join(f"{int(k)}:{v:.1f}" for k, v in byn.items()))

# 그림: 스텝별 J_L vs N_UF
fig, ax = plt.subplots(figsize=(7.4, 4.6))
for s in steps:
    sub = g[g["step"] == s]
    byn = sub.groupby("N_UF")["objective"].mean()
    ax.plot(byn.index, byn.values, marker="o", ms=4, label=f"step {int(s)} ({LABEL.get(int(s),'')})")
ax.set_xlabel("$N_{UF}$ requested [veh/h]"); ax.set_ylabel("leader objective $J_L$")
ax.set_title("Leader objective vs requested freeway budget (Med-incident)")
ax.legend(fontsize=8); ax.grid(alpha=0.3)
fig.tight_layout()
os.makedirs("2026-07-24/results", exist_ok=True)
fig.savefig("2026-07-24/results/fig_incident_nuf_authority.png", dpi=170, bbox_inches="tight")
print("\nsaved 2026-07-24/results/fig_incident_nuf_authority.png")
