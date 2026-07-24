# leader x granularity 2x2 최종표 — PFO(2/4) vs P-Stack(4/21), 5셀 (2026-07-24)
# leader 기여(동일 9-agent) = PStack(4)-PFO(4); 세밀도 효과 = PStack(4)-PStack(21)
import os
import numpy as np, pandas as pd
BASE = "C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
PS = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF = "WU-FAITHFUL-FOLLOWER"
CELLS = [("Low", "155"), ("Medium", "170"), ("Med-skew", "170skew"),
         ("Med-incident", "170inc"), ("High", "190")]

def load(rel):
    p = os.path.join(BASE, rel); return pd.read_csv(p) if os.path.exists(p) else None
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if (d is not None and k in d.columns) else None
def win(d, warm=5, hi=14400):
    if d is None: return None
    cum = num(d, "cumulative_total_ttt"); st = num(d, "step"); t = num(d, "time_sec")
    bi = next((i for i, s in enumerate(st) if s == warm - 1), None)
    end = len(d) - 1
    if t is not None:
        for i in range(len(t)):
            if t[i] > hi: end = i - 1; break
    return cum[end] - (cum[bi] if bi is not None else 0)

def cost(d, warm=6):
    # 활성 스텝(리더 켜지는 step>=warm)만 평균 — warmup solve=0 희석 제거
    if d is None: return (None, None)
    ct = num(d, "computation_time_sec"); st = num(d, "step")
    if ct is None: return (None, None)
    m = st >= warm if st is not None else np.ones(len(ct), bool)
    a = ct[m]; a = a[np.isfinite(a)]
    if a.size == 0: return (None, None)
    return (float(np.mean(a)), float(np.max(a)))

def f(x): return f"{x:7.1f}" if x is not None else "   미완"
print("=" * 108)
print("leader × granularity 2×2 (현재코드·S_max10·T=14400, windowed TTT 900-14400)")
print(f"{'cell':13}{'PFO(2)':>9}{'PFO(4)':>9}{'PStk(4)':>9}{'PStk(21)':>10}"
      f"{'leader@9':>10}{'gran4→21':>10}{'PFO2→4':>9}")
print(f"{'':13}{'7ag':>9}{'9ag':>9}{'9ag+L':>9}{'21ag+L':>10}{'PS4-PFO4':>10}{'PS4-PS21':>10}{'':>9}")
print("-" * 108)
rows = []
for nm, c in CELLS:
    p2 = win(load(f"outputs/_diag/pfo_{c}/{FF}/run_log.csv"))
    p4 = win(load(f"outputs/_diag/pfosplit_{c}/{FF}/run_log.csv"))
    s4 = win(load(f"outputs/_diag/pstack4_{c}/{PS}/run_log.csv"))
    s21 = win(load(f"outputs/_diag/camp_s10on_{c}/{PS}/run_log.csv"))
    lead = f"{s4-p4:+.1f}" if (s4 is not None and p4 is not None) else "-"
    gran = f"{s4-s21:+.1f}" if (s4 is not None and s21 is not None) else "-"
    pfo24 = f"{p4-p2:+.1f}" if (p2 is not None and p4 is not None) else "-"
    print(f"{nm:13}{f(p2)}{f(p4)}{f(s4)}{f(s21):>10}{lead:>10}{gran:>10}{pfo24:>9}")
    rows.append((nm, p2, p4, s4, s21))
print("=" * 108)
print("leader@9 (PS4-PFO4)<0 → 동일 9-agent서 leader가 TTT 낮춤 = follower수 아닌 leader 기여.")
print("gran4→21 (PS4-PS21)<0 → 4-agent가 21-agent보다 나음 = '이득=follower수' 기각.")
print("주의: PStk(4)는 supervisor(SUP_PFO)·segment-box 제거된 순수 leader+4agent.")
print("      PFO(4)→PStk(4)만 깨끗한 leader 격리(base env 동일, 컨트롤러만 차이).")

# ---- computation cost (활성 스텝 mean, max) ----
print("\n" + "=" * 108)
print("computation cost — step당 solve time (활성 step≥6 mean / max, 초)")
print(f"{'cell':13}{'PFO(2)':>16}{'PFO(4)':>16}{'PStk(4)':>16}{'PStk(21)':>16}")
print(f"{'':13}{'mean/max':>16}{'mean/max':>16}{'mean/max':>16}{'mean/max':>16}")
print("-" * 108)
def cc(rel):
    m, mx = cost(load(rel))
    return f"{m:.1f}/{mx:.0f}" if m is not None else "미완"
for nm, c in CELLS:
    a = cc(f"outputs/_diag/pfo_{c}/{FF}/run_log.csv")
    b = cc(f"outputs/_diag/pfosplit_{c}/{FF}/run_log.csv")
    d = cc(f"outputs/_diag/pstack4_{c}/{PS}/run_log.csv")
    e = cc(f"outputs/_diag/camp_s10on_{c}/{PS}/run_log.csv")
    print(f"{nm:13}{a:>16}{b:>16}{d:>16}{e:>16}")
print("=" * 108)
print("PFO=leader 없음(초단위). PStk(4)=leader+4agent(감독자·box 없음). PStk(21)=flagship 21agent+감독자.")
print("실시간 예산=180s/step(1800s DT×0.1). PStk(4)↔(21) 배수가 세밀도+감독자 비용.")
