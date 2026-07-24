# granularity 비교: P-Stack(21) vs PFO(2) vs PFO(4) — follower 수 vs 성능 (2026-07-24)
import os
import numpy as np, pandas as pd
PS = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF = "WU-FAITHFUL-FOLLOWER"
CELLS = [("Low", "155"), ("Medium", "170"), ("Med-skew", "170skew"), ("Med-incident", "170inc"), ("High", "190")]
def win(p, warm=5):
    if not os.path.exists(p): return None
    d = pd.read_csv(p); c = pd.to_numeric(d["cumulative_total_ttt"], errors="coerce").to_numpy()
    s = pd.to_numeric(d["step"], errors="coerce").to_numpy()
    bi = next((i for i, x in enumerate(s) if x == warm - 1), None)
    return c[-1] - (c[bi] if bi is not None else 0)

print("=" * 84)
print("granularity 비교 (현재코드·S_max10·T=14400, windowed TTT) — follower 수 ↔ 성능")
print(f"{'cell':13}{'PStack(21)':>12}{'PFO(2)':>10}{'PFO(4)':>10}{'PS−PFO2':>10}{'PS−PFO4':>10}{'PFO2→4':>9}")
for nm, c in CELLS:
    ps = win(f"outputs/_diag/camp_s10on_{c}/{PS}/run_log.csv")
    p2 = win(f"outputs/_diag/pfo_{c}/{FF}/run_log.csv")
    p4 = win(f"outputs/_diag/pfosplit_{c}/{FF}/run_log.csv")
    def f(x): return f"{x:.1f}" if x is not None else "미완"
    d2 = f"{ps-p2:+.1f}" if (ps and p2) else "-"
    d4 = f"{ps-p4:+.1f}" if (ps and p4) else "-"
    dp = f"{p4-p2:+.1f}" if (p2 and p4) else "-"
    print(f"{nm:13}{f(ps):>12}{f(p2):>10}{f(p4):>10}{d2:>10}{d4:>10}{dp:>9}")
print("=" * 84)
print("PS−PFO<0 = P-Stack이 PFO보다 나음(TTT 낮음). PFO2→4<0 = 4-agent가 2-agent보다 나음.")
print("follower 수: P-Stack=21(16seg+5urban), PFO(2)=2freeway+5urban=7, PFO(4)=4freeway+5urban=9.")
print("→ 세밀도(agent수)와 성능의 관계가 단조가 아니면(예: PFO 2→4 개선인데 P-Stack 21은 더 나쁨)")
print("  '이득=follower 수'는 기각되고, 진짜 요인(metering authority·leader·조정)이 드러남.")
