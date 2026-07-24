# nofric 6셀 완료 판정 확인용 임시 스크립트
import csv, os
for c in ['155','170','170skew','170inc','190','190skew']:
    p = f'outputs/_diag/nofric_{c}/P-STACK-WU-FAITHFUL-ALLPRICE-JOINT/run_log.csv'
    if not os.path.exists(p):
        print(c, ': run_log 없음(실행중)')
        continue
    with open(p, encoding='utf-8', errors='ignore') as f:
        lines = sum(1 for _ in f)
    rows = list(csv.DictReader(open(p, encoding='utf-8', errors='ignore')))
    last = int(float(rows[-1]['step'])) if rows else -1
    ok = '충족' if lines >= 81 else '미달'
    print(c, ': 줄수=', lines, ' 마지막step=', last, ' 대기기준(>=81)=', ok)
