# green 넓은 sweep 분석: TTT_global(green) 곡선이 선형(6s 충분)이냐 비선형(넓은 probe가 이득)이냐 판정 (2026-07-23)
import sys, os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TAG = sys.argv[1] if len(sys.argv) > 1 else "skew"
CSV = f"outputs/_diag/green_sweep_{TAG}.csv"
OUT = f"2026-07-23/results/fig_green_sweep_{TAG}.png"

d = pd.read_csv(CSV)
d = d[d["ttt"] != "ERR"].copy()
d["ttt"] = pd.to_numeric(d["ttt"], errors="coerce")
d["p1"] = pd.to_numeric(d["p1"], errors="coerce")
d["ref_p1"] = pd.to_numeric(d["ref_p1"], errors="coerce")

combos = sorted(set(zip(d["step"], d["signal"])))
print(f"조합 {len(combos)}개: {combos}")
print(f"\n{'step':>4}{'sig':>4}{'ref':>6}{'TTT@ref':>10}{'최소green':>10}{'최소TTT':>9}{'이득':>8}   기울기 g(±w) [넓힐수록 커지면 6s가 놓침]")

def grad(p, ttt, ref, w):
    ih = int(np.argmin(np.abs(p - (ref + w)))); il = int(np.argmin(np.abs(p - (ref - w))))
    if abs(p[ih] - p[il]) < 1e-6:
        return np.nan
    return (ttt[ih] - ttt[il]) / (p[ih] - p[il])

# 판정 집계
verdicts = []
fig, axes = plt.subplots(1, max(1, len(set(d["step"]))), figsize=(3.4 * len(set(d["step"])), 3.8), squeeze=False)
steps_sorted = sorted(set(d["step"]))
for ax, stp in zip(axes[0], steps_sorted):
    for sig, sub in d[d["step"] == stp].groupby("signal"):
        sub = sub.sort_values("p1")
        p = sub["p1"].to_numpy(); ttt = sub["ttt"].to_numpy(); ref = sub["ref_p1"].iloc[0]
        iref = int(np.argmin(np.abs(p - ref))); tref = ttt[iref]
        imin = int(np.argmin(ttt)); pmin = p[imin]; tmin = ttt[imin]
        gs = {w: grad(p, ttt, ref, w) for w in [6, 12, 20, 40]}
        gain_local = abs(gs[6] * 6)      # 6s probe가 보는 이득 규모
        gain_wide = tref - tmin          # 넓게 봤을 때 실제 최대 이득
        nonlinear = (gain_wide > 2.0 * max(gain_local, 1e-9)) and (abs(pmin - ref) > 8)
        verdicts.append((stp, sig, gain_local, gain_wide, abs(pmin - ref), nonlinear))
        print(f"{stp:>4}{sig:>4}{ref:>6.0f}{tref:>10.2f}{pmin:>10.0f}{tmin:>9.2f}{tref - tmin:>8.2f}   " +
              " ".join(f"±{w}:{gs[w]:+.3f}" for w in [6, 12, 20, 40]))
        ax.plot(p, ttt, marker="o", ms=3, label=f"sig {sig}")
        ax.axvline(ref, color="0.6", ls="--", lw=0.8)
        ax.plot([pmin], [tmin], "rv", ms=7)
    ax.set_title(f"step {stp} (t={int(stp)*180}s)"); ax.set_xlabel("green p1 [s]")
    ax.set_ylabel("TTT_global (rollout surrogate)"); ax.legend(fontsize=8)
fig.suptitle(f"green 넓은 sweep — TTT vs green ({TAG}); ▽=곡선최소, --=현재 ref", fontsize=11)
fig.tight_layout()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=170, bbox_inches="tight")
print(f"\nsaved {OUT}")

nl = sum(1 for v in verdicts if v[5])
print(f"\n=== 판정 ===")
print(f"비선형(넓게 봐야 이득) 조합: {nl}/{len(verdicts)}")
if nl == 0:
    print("→ 곡선 거의 선형/최소점이 ref 근처. 6s probe로 충분. green 약함 = 물리 레버리지(넓게 봐도 안 커짐). 가설 기각.")
else:
    print("→ 일부 조합서 먼 곳에 최소점. 6s가 큰-스케일 이득을 놓침. 넓은 probe면 green 가격 커짐. 가설 지지.")
