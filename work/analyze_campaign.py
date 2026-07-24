# 캠페인 종합: item1 S_max{5,10} 일반화 + item2 price ablation(새 VSL+S_max10) + (c)수렴곡선 (2026-07-24)
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
CELLS = ["155", "170", "170skew", "170inc", "190"]
NAME = {"155": "Low", "170": "Medium", "170skew": "Med-skew", "170inc": "Med-incident", "190": "High"}
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if k in d.columns else None
def load(tag, cell):
    p = f"outputs/_diag/camp_{tag}_{cell}/{C}/run_log.csv"
    return pd.read_csv(p) if os.path.exists(p) else None
def win(d, warm=5):
    cum = num(d, "cumulative_total_ttt"); st = num(d, "step")
    bi = next((i for i, s in enumerate(st) if s == warm - 1), None)
    return cum[-1] - (cum[bi] if bi is not None else 0)
def stats(d):
    t = num(d, "time_sec"); pk = (t >= 900) & (t < 5220)
    cv = num(d, "nash_converged"); it = num(d, "nash_iterations"); ct = num(d, "computation_time_sec")
    ct = ct[ct > 0.01] if ct is not None else np.array([np.nan])
    return win(d), np.nanmean(cv[pk]) * 100, np.nanmean(it), np.nanmean(ct)

# ── item1: S_max=5 vs 10 (price-ON) ──
print("=" * 88)
print("ITEM 1 — S_max=5 vs 10 일반화 (price-ON, T=14400)")
print(f"{'cell':12}{'TTT_s5':>10}{'TTT_s10':>10}{'ΔTTT%':>8}{'conv5%':>8}{'conv10%':>9}{'solve5':>8}{'solve10':>8}")
for cell in CELLS:
    d5, d10 = load("s5on", cell), load("s10on", cell)
    if d5 is None or d10 is None:
        print(f"{NAME[cell]:12} (미완: s5={d5 is not None} s10={d10 is not None})"); continue
    t5, c5, i5, ct5 = stats(d5); t10, c10, i10, ct10 = stats(d10)
    print(f"{NAME[cell]:12}{t5:>10.1f}{t10:>10.1f}{(t10-t5)/t5*100:>+8.2f}{c5:>8.0f}{c10:>9.0f}{ct5:>8.1f}{ct10:>8.1f}")
print("→ ΔTTT≈0 이면 S_max=10 무손실, conv10=100%면 free win 일반화 확정")

# ── item2: price ablation (S_max=10, ON vs OFF) → 새 TABLE 4 ──
print("\n" + "=" * 88)
print("ITEM 2 — 가격 기여 (S_max=10, 새 VSL, ON=s10on vs OFF=s10off)")
print(f"{'cell':12}{'ON':>10}{'OFF':>10}{'ΔTTT':>9}{'기여%':>8}")
for cell in CELLS:
    on, off = load("s10on", cell), load("s10off", cell)
    if on is None or off is None:
        print(f"{NAME[cell]:12} (미완: on={on is not None} off={off is not None})"); continue
    wo, wf = win(on), win(off)
    print(f"{NAME[cell]:12}{wo:>10.1f}{wf:>10.1f}{wf-wo:>+9.1f}{(wf-wo)/wo*100:>+8.2f}")
print("→ 구 TABLE4(구코드/PRICE_CF오염): Low−0.5/Med+8.8/Skew+4.2/Inc0/High+9.9 와 비교")

# ── (c) 수렴 곡선: skew S_max=10 ──
rp = f"outputs/_diag/camp_s10on_170skew/resid.resid.csv"
if os.path.exists(rp):
    r = pd.read_csv(rp)
    for c2 in ["step", "iteration", "residual", "tol"]:
        r[c2] = pd.to_numeric(r[c2], errors="coerce")
    tol = r["tol"].dropna().iloc[0]
    # 시퀀스 분절: iteration이 감소하면 새 시퀀스
    r = r.reset_index(drop=True); seq = (r["iteration"].diff() <= 0).cumsum()
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    plotted = 0
    for _, sub in r.groupby(seq):
        sub = sub[sub["residual"] > 0]
        if len(sub) >= 3:
            ax.plot(sub["iteration"], sub["residual"], marker="o", ms=3, alpha=0.5, lw=1)
            plotted += 1
        if plotted >= 30: break
    ax.axhline(tol, color="red", ls="--", lw=1.3, label=f"ε={tol}")
    ax.set_yscale("log"); ax.set_xlabel("best-response iteration"); ax.set_ylabel("coupling residual")
    ax.set_title(f"(c) Follower best-response convergence (skew, S_max=10, {plotted} epochs)")
    ax.legend(); ax.grid(alpha=0.3)
    os.makedirs("2026-07-24/results", exist_ok=True)
    fig.tight_layout(); fig.savefig("2026-07-24/results/fig_c_convergence.png", dpi=160, bbox_inches="tight")
    print(f"\n(c) 수렴곡선 저장: 2026-07-24/results/fig_c_convergence.png ({plotted} sequences)")
else:
    print(f"\n(c) resid 파일 없음: {rp}")
