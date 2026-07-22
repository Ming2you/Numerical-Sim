# 리더 목적함수 곡면 곡률 진단(2026-07-22) — price 1차 vs 2차 필요성
"""스텝별 후보 (N_P,N_UF,objective)로 J를 1차 평면 vs 2차 곡면 적합.

nonlinearity index = R^2_quad - R^2_lin (2차 곡률이 평면 너머 설명하는 분산 비율).
incident 폐쇄구간(step 10~20, t=1800~3600s)서 이게 튀면 = 선형 가격이 그 국면을
못 담고 함수형(2차) 가격이 이득이라는 직접 증거.
"""
import csv, sys, glob, os
import numpy as np

def load(path):
    by_step = {}
    if not os.path.exists(path):
        return by_step
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            s = int(float(r["step"])); np_ = float(r["N_P_star"]); nuf = float(r["N_UF_star"]); o = float(r["objective"])
        except (ValueError, KeyError):
            continue
        by_step.setdefault(s, []).append((np_, nuf, o))
    return by_step

def fit_step(rows):
    a = np.array(rows, float)
    x1, x2, y = a[:, 0], a[:, 1], a[:, 2]
    m = len(y)
    if m < 12 or np.ptp(y) < 1e-9:
        return None
    # 표준화(조건수 개선)
    def z(v):
        s = v.std(); return (v - v.mean()) / s if s > 1e-12 else v * 0.0
    z1, z2, zy = z(x1), z(x2), z(y)
    if z1.std() < 1e-9 and z2.std() < 1e-9:
        return None
    ss_tot = float((zy ** 2).sum())
    if ss_tot < 1e-12:
        return None
    def r2(cols):
        X = np.column_stack(cols)
        coef, *_ = np.linalg.lstsq(X, zy, rcond=None)
        res = zy - X @ coef
        return 1.0 - float((res ** 2).sum()) / ss_tot, coef
    one = np.ones(m)
    r2_lin, _ = r2([one, z1, z2])
    r2_quad, cq = r2([one, z1, z2, z1 ** 2, z2 ** 2, z1 * z2])
    return dict(m=m, r2_lin=r2_lin, r2_quad=r2_quad, nonlin=r2_quad - r2_lin,
                nuf_curv=float(cq[4]))  # N_UF^2 계수(표준화)

def summarize(tag, path, closure=(10, 20)):
    bs = load(path)
    print(f"\n===== {tag}  ({path.split(os.sep)[-2] if os.sep in path else path}) =====")
    if not bs:
        print("  (데이터 없음)"); return
    rows = []
    for s in sorted(bs):
        f = fit_step(bs[s])
        if f: rows.append((s, f))
    if not rows:
        print("  (적합 가능한 스텝 없음 — 스텝당 후보 부족)"); return
    print(f"  {'step':>4} {'m':>3} {'R2_lin':>7} {'R2_quad':>8} {'nonlin':>7} {'NUFcurv':>8}")
    for s, f in rows:
        mark = " <closure" if closure[0] <= s <= closure[1] else ""
        print(f"  {s:>4} {f['m']:>3} {f['r2_lin']:>7.3f} {f['r2_quad']:>8.3f} {f['nonlin']:>7.3f} {f['nuf_curv']:>8.3f}{mark}")
    def avg(pred):
        vs = [f['nonlin'] for s, f in rows if pred(s)]
        return (sum(vs) / len(vs), len(vs)) if vs else (float('nan'), 0)
    cl = avg(lambda s: closure[0] <= s <= closure[1])
    lt = avg(lambda s: s < closure[0] or s > closure[1] + 8)
    print(f"  --- 평균 nonlinearity: 폐쇄구간(step {closure[0]}~{closure[1]})={cl[0]:.3f} (n={cl[1]}) / 그 외={lt[0]:.3f} (n={lt[1]})")

if __name__ == "__main__":
    root = r"C:\Users\alsrj\Desktop\Numerical-Sim-offiter\outputs\_wang3"
    summarize("INCIDENT (closure 1800-3600s = step10-20)", os.path.join(root, "curv_incident", "leader_cand.allcand.csv"))
    summarize("MEDIUM 170 (no closure)", os.path.join(root, "curv_170", "leader_cand.allcand.csv"), closure=(999, 999))
