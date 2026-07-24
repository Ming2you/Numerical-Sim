# 모든 대기 런 완료까지 폴링 후 자동 결과 집계(2026-07-23) — hinge matrix + N_UF cap + VSL cooldown
import csv, glob, time, sys
from pathlib import Path
sys.path.insert(0, '.')

ROOT = Path('.')
CT = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"

def rl(path_glob):
    g = glob.glob(path_glob)
    return g[0] if g else None

# 대기 대상
targets = {}
arms = ['base', 'objhinge', 'pricehinge', 'bothhinge']
cells = ['155', '170', '170skew', '170inc', '190', '190skew', '190inc']
for a in arms:
    for c in cells:
        targets[f"hm_{a}_{c}"] = f"outputs/hinge_matrix/{a}_{c}/{CT}/run_log.csv"
for cap in ['3500', '4000', '4500']:
    targets[f"nufcap_{cap}"] = f"outputs/_diag/nufcap_{cap}/{CT}/run_log.csv"
targets["vslcool_115"] = f"outputs/_diag/vslcool_115/{CT}/run_log.csv"

def complete(p):
    try:
        with open(p, encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f) >= 81
    except Exception:
        return False

# 폴링 (최대 4시간)
t0 = time.time()
while time.time() - t0 < 4*3600:
    done = [k for k, p in targets.items() if complete(p)]
    if len(done) == len(targets):
        break
    time.sleep(60)

# ---- 분석 ----
def windowed(p, WARM=5):
    try:
        rows = list(csv.DictReader(open(p, newline='', encoding='utf-8', errors='ignore')))
        cum = [float(r['cumulative_total_ttt']) for r in rows]
        steps = [int(float(r['step'])) for r in rows]
        bi = next((i for i, s in enumerate(steps) if s == WARM-1), None)
        return cum[-1] - (cum[bi] if bi is not None else 0.0)
    except Exception:
        return None
def window(p, s_lo, s_hi, WARM=5):  # 특정 스텝창 total ttt
    try:
        rows = list(csv.DictReader(open(p, newline='', encoding='utf-8', errors='ignore')))
        cum = {int(float(r['step'])): float(r['cumulative_total_ttt']) for r in rows}
        return cum.get(s_hi, 0) - cum.get(s_lo, 0)
    except Exception:
        return None
def avgcol(p, col, t0s, t1s):
    try:
        rows = list(csv.DictReader(open(p, newline='', encoding='utf-8', errors='ignore')))
        vs = [float(r[col]) for r in rows if t0s <= float(r['time_sec']) < t1s and r.get(col) not in (None, '')]
        return sum(vs)/len(vs) if vs else None
    except Exception:
        return None

out = []
out.append(f"=== 자동 결과 집계 (완료 {len(done)}/{len(targets)}, 경과 {(time.time()-t0)/60:.0f}분) ===\n")

# 참조(main 5셀 table2 + held-out ho_*)
ref = {"155": (3061, 2988, 2942), "170": (4558, 3864, 3794), "170skew": (4582, 3938, 3867),
       "170inc": (5977, 5953, 5013), "190": (6897, 6157, 5718),
       "190skew": (6882, 6299, 5757), "190inc": (8556, 9230, 8016)}  # NC/PFO/P-CENT

out.append("## 1. hinge 매트릭스 (windowed TTT, 괄호=base대비Δ%)")
out.append(f"{'cell':9}{'base':>8}{'objhinge':>13}{'pricehinge':>13}{'both':>13}   NC/PFO/PCENT")
for c in cells:
    b = windowed(targets[f"hm_base_{c}"])
    row = f"{c:9}{(b or 0):8.0f}"
    for a in ['objhinge', 'pricehinge', 'bothhinge']:
        v = windowed(targets[f"hm_{a}_{c}"])
        row += (f"{v:6.0f}({(v-b)/b*100:+.1f}%)".rjust(13) if (v and b) else f"{'..':>13}")
    nc, pf, pc = ref[c]
    row += f"   {nc}/{pf}/{pc}"
    out.append(row)

out.append("\n## 2. N_UF 캡 반사실 (190skew; base loose=6379, PFO=6299, P-CENT=5757)")
out.append(f"{'cap':8}{'windowed':>10}{'realized N_UF(peak)':>20}")
for cap in ['3500', '4000', '4500']:
    p = targets[f"nufcap_{cap}"]
    w = windowed(p); nuf = avgcol(p, 'leader_realized_N_UF_star', 900, 5220)
    out.append(f"{cap:8}{(w if w else 0):10.1f}{(nuf if nuf else 0):20.0f}")

out.append("\n## 3. VSL cooldown=115 강제 반사실 (190skew; base=6379)")
p = targets["vslcool_115"]
w = windowed(p)
# cooldown창(step29~79) total ttt: base vs forced
bp = targets["hm_base_190skew"]
cd_base = window(bp, 29, 79); cd_forced = window(p, 29, 79)
out.append(f"  전체 windowed: base 6379 → VSL115강제 {(w if w else 0):.1f} (Δ={(w-6378.9) if w else 0:+.1f})")
out.append(f"  cooldown창(step29~79) total: base {cd_base if cd_base else 0:.1f} → forced {cd_forced if cd_forced else 0:.1f}")

txt = "\n".join(out)
print(txt)
Path("outputs/_diag/AUTO_REPORT.txt").write_text(txt, encoding='utf-8')
print("\n[written: outputs/_diag/AUTO_REPORT.txt]")
