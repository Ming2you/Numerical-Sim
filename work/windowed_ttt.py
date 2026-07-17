# T=10800 계열(warm 3600 + 이벤트 + 쿨다운)의 warm-up 제외 창 [3600,10800] TTT 집계.
# run_log.csv의 cumulative_total_ttt 차분으로 계산 — 재실행 불필요, 표준 관행(burn-in 제외).
import csv
import glob
import os
import sys

WARM_STEPS = 20  # 3600s / 180s


def windowed(d):
    subs = [s for s in glob.glob(os.path.join(d, '*')) if os.path.isdir(s)]
    out = []
    for s in subs:
        p = os.path.join(s, 'run_log.csv')
        if not os.path.exists(p):
            continue
        rows = sorted(csv.DictReader(open(p, encoding='utf-8')), key=lambda r: float(r['step']))
        if len(rows) <= WARM_STEPS:
            continue
        cum_w = float(rows[WARM_STEPS - 1]['cumulative_total_ttt'])
        cum_T = float(rows[-1]['cumulative_total_ttt'])
        # 창 내 완주(있으면): boundary_out_sink + mainline_exit×T_c
        comp = 0.0
        for r in rows[WARM_STEPS:]:
            comp += float(r.get('boundary_out_sink_veh') or 0)
            comp += float(r.get('mainline_exit_flow_total') or 0) * (180.0 / 3600.0)
        out.append((os.path.basename(s), cum_T - cum_w, comp))
    return out


if __name__ == '__main__':
    pats = sys.argv[1:] or [
        'outputs/_wsuite/8seg_*', 'outputs/_dsust/8seg_*', 'outputs/_dsym/8seg_*',
        'outputs/_phase1/8seg_dsym_110_pd4_fbon', 'outputs/_phase1/8seg_dhigh2w_pd4_fbon',
    ]
    for pat in pats:
        for d in sorted(glob.glob(pat)):
            for name, ttt, comp in windowed(d):
                att = ttt / comp * 60.0 if comp > 0 else 0.0
                print(f"{os.path.basename(d):32s} {name[:12]:12s} wTTT={ttt:9.1f} wComp={comp:8.0f} wATT={att:6.2f}")
