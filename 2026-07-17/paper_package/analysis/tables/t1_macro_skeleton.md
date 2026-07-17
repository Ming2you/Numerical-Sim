# 표1 골격 — 6셀 × 5컨트롤러 (wTTT, veh·h)

| cell | NC | WU-CD-F | PFO | P-CENT | walk-MVG |
|---|---|---|---|---|---|
| sweet_155_w | 런 대기 | 런 대기 | 런 대기 | 런 대기 | 1685.35 |
| sweet_170_w | 런 대기 | 런 대기 | 런 대기 | 런 대기 | 2684.33 |
| sweet_170_skew15_w | 런 대기 | 런 대기 | 런 대기 | 런 대기 | 2666.97 |
| sweet_170_incident_w | 런 대기 | 런 대기 | 런 대기 | 런 대기 | 2295.23 |
| sweet_190_w | 런 대기 | 런 대기 | 런 대기 | 런 대기 | 5155.59 |
| sweet_200_w | 런 대기 | 런 대기 | 런 대기 | 런 대기 | 8684.25 |

## walk-MVG 상세

| cell | wTTT (veh·h) | % vs PFO ref | comp mean (s) | comp max (s) | completed (veh) |
|---|---|---|---|---|---|
| sweet_155_w | 1685.35 | 5.1 | 66.11 | 116.47 | 10222.5 |
| sweet_170_w | 2684.33 | 11.14 | 68.93 | 98.75 | 10999.0 |
| sweet_170_skew15_w | 2666.97 | 9.81 | 69.42 | 111.24 | 11015.4 |
| sweet_170_incident_w | 2295.23 | 3.03 | 65.31 | 111.67 | 10999.1 |
| sweet_190_w | 5155.59 | 9.38 | 74.01 | 117.98 | 11705.3 |
| sweet_200_w | 8684.25 | -20.68 | 70.69 | 132.44 | 9778.8 |

주석.
- wTTT = cumulative_total_ttt[끝] − cumulative_total_ttt[step==19 행] (0-인덱스; 웜업 20스텝 누적치, 채점창 step 20..59).
- % vs PFO ref: §0.4 수치 기준선 (155_w 1776 / 170_w 3021 / 170_skew15 2957 / 170_incident 2367 / 190_w 5689 / 200_w 7196).
- comp = run_log `computation_time_sec`, 채점창만. 벽시계라 같은 머신 런끼리만 비교.
- completed = Σ `boundary_out_sink_veh` (채점창) — urban 경계 sink 유출 프록시. 전 네트워크 완주 컬럼 부재.
- 200_w는 §5 한계 전용 — 본문 표 편입 금지.
- NC/WU-CD-F/PFO/P-CENT: 런 대기 (§6 런 큐).