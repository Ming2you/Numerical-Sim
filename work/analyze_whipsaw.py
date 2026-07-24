# out_whipsaw_*.json 분석 — 진동 폭/주기, wTTT 비교, |ΔN_UF|~stepTTT 상관, V(N_UF) 평탄도.
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parents[1]


def load(tag):
    p = ROOT / 'work' / ('out_whipsaw_%s.json' % tag)
    if not p.exists():
        return None
    return json.load(open(p, encoding='utf-8'))


def pearson(x, y):
    n = len(x)
    if n < 3:
        return float('nan')
    mx, my = sum(x) / n, sum(y) / n
    sx = (sum((a - mx) ** 2 for a in x)) ** 0.5
    sy = (sum((b - my) ** 2 for b in y)) ** 0.5
    if sx <= 0 or sy <= 0:
        return float('nan')
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def analyze(tag):
    d = load(tag)
    if d is None:
        print('%s: MISSING' % tag)
        return None
    win = [r for r in d['rows'] if not r['warm']]
    nuf = [r['nuf'] for r in win]
    ttt = [r['step_ttt'] for r in win]
    wttt = sum(ttt)
    dn = [abs(nuf[i] - nuf[i - 1]) for i in range(1, len(nuf))]
    # sign changes of successive deltas = whipsaw reversals
    raw = [nuf[i] - nuf[i - 1] for i in range(1, len(nuf))]
    nz = [v for v in raw if abs(v) > 1.0]
    rev = sum(1 for i in range(1, len(nz)) if nz[i] * nz[i - 1] < 0)
    print('\n===== %s  (enforce=%s radius=%s) =====' % (tag, d['meta']['enforce'], d['meta']['radius']))
    print('calls: %s' % d['meta']['calls'])
    print('window steps=%d  wTTT=%.2f' % (len(win), wttt))
    print('N_UF: min=%.0f max=%.0f span=%.0f  mean|Δ|=%.0f max|Δ|=%.0f  반전=%d/%d'
          % (min(nuf), max(nuf), max(nuf) - min(nuf),
             sum(dn) / max(len(dn), 1), max(dn) if dn else 0, rev, max(len(nz) - 1, 0)))
    over = sum(1 for v in dn if v > d['meta']['radius'] + 1)
    print('|Δ| > radius(%.0f) 인 스텝: %d/%d' % (d['meta']['radius'], over, len(dn)))
    # candidate range vs radius
    outside = []
    for r in win:
        for rc in r.get('ref_calls', []):
            outside.append(rc['n_outside_radius'] / max(rc['raw_n'], 1))
    if outside:
        print('refined 후보 중 반경 밖 비율: 평균 %.1f%% (스텝 %d)' % (100 * sum(outside) / len(outside), len(outside)))
    # correlation |dNUF|(t) vs step_TTT(t)
    if len(dn) >= 3:
        print('corr(|ΔN_UF|_t , stepTTT_t) = %+.3f' % pearson(dn, ttt[1:]))
    print('\nstep  nuf       Δ        stepTTT   n_ev  V평탄도(obj_stay-obj_best)  obj범위')
    for i, r in enumerate(win):
        ev = r.get('evals', [])
        flat = ''
        rng = ''
        if ev:
            objs = [e['obj'] for e in ev]
            best = min(ev, key=lambda e: e['obj'])
            pn = win[i - 1]['nuf'] if i > 0 else r['nuf']
            stay = min(ev, key=lambda e: abs(e['nuf'] - pn))
            flat = '%10.3f' % (stay['obj'] - best['obj'])
            rng = '%.3f' % (max(objs) - min(objs))
        d_ = ('%+8.0f' % (r['nuf'] - win[i - 1]['nuf'])) if i > 0 else '%8s' % '-'
        print('%4d %8.0f %s %9.2f  %4d  %s  %s'
              % (r['step'], r['nuf'], d_, r['step_ttt'], len(ev), flat, rng))
    return {'wttt': wttt, 'nuf': nuf, 'ttt': ttt, 'rows': win, 'meta': d['meta']}


b = analyze('base')
e = analyze('enf')
if b and e:
    print('\n\n===== 비교 =====')
    print('wTTT  base=%.2f  enforced=%.2f  Δ=%+.2f (%+.2f%%)'
          % (b['wttt'], e['wttt'], e['wttt'] - b['wttt'],
             100 * (e['wttt'] - b['wttt']) / b['wttt']))
    bn, en = b['nuf'], e['nuf']
    bd = [abs(bn[i] - bn[i - 1]) for i in range(1, len(bn))]
    ed = [abs(en[i] - en[i - 1]) for i in range(1, len(en))]
    print('mean|ΔN_UF|  base=%.0f  enforced=%.0f' % (sum(bd) / len(bd), sum(ed) / len(ed)))
    print('N_UF span    base=%.0f  enforced=%.0f' % (max(bn) - min(bn), max(en) - min(en)))
    print('\nstep   base_nuf  enf_nuf   base_TTT   enf_TTT')
    for i in range(min(len(b['rows']), len(e['rows']))):
        print('%4d %9.0f %9.0f %10.2f %10.2f'
              % (b['rows'][i]['step'], bn[i], en[i], b['ttt'][i], e['ttt'][i]))
