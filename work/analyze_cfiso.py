# PRICE_CF 격리 + PFO 비교검토: P-Stack(CF-on) vs P-Stack(CF-off) vs PFO (2026-07-24)
import os
import numpy as np, pandas as pd
PS = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; PFO = "WU-FAITHFUL-FOLLOWER"
CELLS = ["155", "170", "170skew", "170inc", "190"]
NAME = {"155": "Low", "170": "Medium", "170skew": "Med-skew", "170inc": "Med-incident", "190": "High"}
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if k in d.columns else None
def load(path): return pd.read_csv(path) if os.path.exists(path) else None
def win(d, lo=900, hi=14400, warm=5):
    if d is None: return None
    t = num(d, "time_sec"); cum = num(d, "cumulative_total_ttt"); st = num(d, "step")
    bi = next((i for i, s in enumerate(st) if s == warm - 1), None)
    # hi 컷 (다른 window와 맞추기 위해)
    end = len(d) - 1
    for i in range(len(t)):
        if t[i] > hi: end = i - 1; break
    return cum[end] - (cum[bi] if bi is not None else 0)
def conv(d):
    if d is None: return float("nan")
    t = num(d, "time_sec"); pk = (t >= 900) & (t < 5220); cv = num(d, "nash_converged")
    return np.nanmean(cv[pk]) * 100 if cv is not None else float("nan")

print("=" * 96)
print("PRICE_CF 격리 + PFO 비교검토 (현재코드·S_max10·T=14400, windowed TTT 900-14400)")
print(f"{'cell':13}{'PStack CFon':>13}{'PStack CFoff':>14}{'PFO':>10}{'CF on-off Δ':>13}{'PStack−PFO':>12}")
for cell in CELLS:
    cfon = load(f"outputs/_diag/cfiso_{cell}/{PS}/run_log.csv")
    cfoff = load(f"outputs/_diag/camp_s10on_{cell}/{PS}/run_log.csv")
    pfo = load(f"outputs/_diag/pfo_{cell}/{PFO}/run_log.csv")
    won, woff, wpfo = win(cfon), win(cfoff), win(pfo)
    def f(x): return f"{x:.1f}" if x is not None else "미완"
    cfd = f"{won-woff:+.1f}" if (won is not None and woff is not None) else "-"
    pgap = f"{woff-wpfo:+.1f}" if (woff is not None and wpfo is not None) else "-"
    print(f"{NAME[cell]:13}{f(won):>13}{f(woff):>14}{f(wpfo):>10}{cfd:>13}{pgap:>12}")
print("=" * 96)
print("판정1 (PRICE_CF 오염): CF on-off Δ≈0 → PRICE_CF 결백. |Δ| 크면 오염 실재.")
print("판정2 (PStack vs PFO): PStack−PFO<0 → P-Stack이 PFO보다 나음(TTT 낮음). >0면 P-Stack이 짐.")

# PFO 정상성 체크 (SEG13 누수로 깨지면 TTT가 NC급 폭발)
print("\n=== PFO 정상성 (깨졌으면 TTT가 P-Stack의 ~2배+) ===")
for cell in CELLS:
    pfo = load(f"outputs/_diag/pfo_{cell}/{PFO}/run_log.csv")
    ps = load(f"outputs/_diag/camp_s10on_{cell}/{PS}/run_log.csv")
    wp, ws = win(pfo), win(ps)
    if wp and ws:
        ratio = wp / ws
        flag = "⚠️깨진듯" if ratio > 1.6 else "정상범위"
        print(f"  {NAME[cell]:13} PFO/PStack = {ratio:.2f}  {flag}")
