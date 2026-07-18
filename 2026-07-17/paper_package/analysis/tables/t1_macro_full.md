# 표 1 — 5컨트롤러 × 5시나리오 (2026-07-18 확정, WARM=20, wTTT [veh·h])

자동 생성: `analysis/scripts/make_table1.py`. 컨트롤러 = No control / Wu / PFO (box) / Centralized / P-Stack (walk-MVG).

## 표 1 — wTTT [veh·h] (괄호 = NC 대비 개선%)

| Scenario | No control | Wu | PFO (box) | Centralized | P-Stack (walk-MVG) |
|---|---|---|---|---|---|
| Low demand | 8977 | 6427 (+28.4%) | 1689 (+81.2%) | 1614 (+82.0%) | 1685 (+81.2%) |
| Med demand | 13028 | 8754 (+32.8%) | 7967 (+38.8%) | 2488 (+80.9%) | 2684 (+79.4%) |
| Med demand (skewed) | 13175 | 12183 (+7.5%) | 2838 (+78.5%) | 2517 (+80.9%) | 2667 (+79.8%) |
| Med demand (incident) | 9581 | 9111 (+4.9%) | 7413 (+22.6%) | 2354 (+75.4%) | 2295 (+76.0%) |
| High demand | 16518 | 16277 (+1.5%) | 5491 (+66.8%) | 4705 (+71.5%) | 5156 (+68.8%) |

## 표 1b — wTTT의 urban / freeway 분해 [veh·h]

| Scenario | No control | Wu | PFO (box) | Centralized | P-Stack (walk-MVG) |
|---|---|---|---|---|---|
| Low demand | 4106 / 4872 | 3411 / 3016 | 844 / 845 | 885 / 728 | 952 / 733 |
| Med demand | 6545 / 6483 | 5205 / 3549 | 4616 / 3351 | 1275 / 1213 | 1559 / 1125 |
| Med demand (skewed) | 6689 / 6486 | 6192 / 5990 | 1751 / 1087 | 1397 / 1121 | 1515 / 1152 |
| Med demand (incident) | 4764 / 4817 | 4555 / 4556 | 4168 / 3245 | 1395 / 959 | 1323 / 972 |
| High demand | 8779 / 7739 | 8608 / 7670 | 4137 / 1354 | 3273 / 1432 | 3745 / 1411 |

표기 = urban / freeway. 합 = 표1 total.

## 표 1c — 종단 잔존 차량 N_end [veh] (보조행)

| Scenario | No control | Wu | PFO (box) | Centralized | P-Stack (walk-MVG) |
|---|---|---|---|---|---|
| Low demand | 7950 | 5502 | 264 | 262 | 286 |
| Med demand | 10859 | 7187 | 6262 | 262 | 278 |
| Med demand (skewed) | 10962 | 10301 | 272 | 263 | 281 |
| Med demand (incident) | 8332 | 8006 | 6011 | 262 | 281 |
| High demand | 13342 | 13280 | 1243 | 606 | 1107 |

N_end = 마지막 180s 스텝 TTT 증분 × 20 = 종단 시점 망 내 차량 수.

## 메모

- 개선% = NC 대비 (NC_wTTT − wTTT)/NC_wTTT × 100. NC는 절대 wTTT만 표기.
- PFO는 이동 한계 부과(box) 버전만 사용 — 무제한 PFO는 논문 제외.
- P-CENT(centralized) = structured grid, 이동 한계 미부과(rate-limit-free 상한).
- sweet_200_w(초고부하)는 논문 제외.