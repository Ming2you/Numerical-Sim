# 능동 N_UF 스윕 곡률 분석(2026-07-22) — J(N_UF) 1차 vs 2차
"""스텝별 11점 (req_N_UF, objective) 스윕으로 J를 1차 vs 2차 적합.
nonlinearity = R^2_quad - R^2_lin. curv = 2차 계수(표준화; +볼록/-오목).
incident 폐쇄구간(step 10~20)서 튀면 = 선형 가격 부족·함수형 가격 이득의 직접 증거.
"""
import csv, os
import numpy as np

def load(path):
    bs = {}
    if not os.path.exists(path):
        return bs
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            s = int(float(r["step"])); x = float(r["req_N_UF"]); y = float(r["objective"])
        except (ValueError, KeyError):
            continue
        bs.setdefault(s, []).append((x, y))
    return bs

def fit(rows):
    a = np.array(rows, float)
    x, y = a[:, 0], a[:, 1]
    if len(y) < 6 or np.ptp(x) < 1e-9 or np.ptp(y) < 1e-9:
        return None
    xs = (x - x.mean()) / x.std()
    ys = (y - y.mean()) / y.std()
    sstot = float((ys ** 2).sum())
    def r2(deg):
        X = np.vander(xs, deg + 1)
        c, *_ = np.linalg.lstsq(X, ys, rcond=None)
        return 1.0 - float(((ys - X @ c) ** 2).sum()) / sstot, c
    r2l, _ = r2(1)
    r2q, cq = r2(2)
    return dict(r2l=r2l, r2q=r2q, nonlin=r2q - r2l, curv=float(cq[0]))

def summarize(tag, path, closure=(10, 20)):
    bs = load(path)
    print(f"\n===== {tag} =====")
    if not bs:
        print("  (데이터 없음)"); return
    print(f"  {'step':>4} {'R2_lin':>7} {'R2_quad':>8} {'nonlin':>7} {'curv':>7}")
    cl, ot = [], []
    for s in sorted(bs):
        f = fit(bs[s])
        if not f: continue
        mk = " <closure" if closure[0] <= s <= closure[1] else ""
        print(f"  {s:>4} {f['r2l']:>7.3f} {f['r2q']:>8.3f} {f['nonlin']:>7.3f} {f['curv']:>7.2f}{mk}")
        (cl if closure[0] <= s <= closure[1] else ot).append(f['nonlin'])
    if cl or ot:
        cm = sum(cl)/len(cl) if cl else float('nan')
        om = sum(ot)/len(ot) if ot else float('nan')
        print(f"  --- 평균 nonlinearity: 폐쇄구간={cm:.3f}(n={len(cl)}) / 그 외={om:.3f}(n={len(ot)})")

if __name__ == "__main__":
    root = r"C:\Users\alsrj\Desktop\Numerical-Sim-offiter\outputs\_wang3"
    summarize("INCIDENT (closure step10-20)", os.path.join(root, "curv_incident", "leader_cand.sweep.csv"))
    summarize("MEDIUM 170 (no closure)", os.path.join(root, "curv_170", "leader_cand.sweep.csv"), closure=(999, 999))
