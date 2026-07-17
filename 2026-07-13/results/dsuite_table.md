# dual-binding suite 최종 표 — 새 다이아몬드 plant (2026-07-13)
망: merge 3/5·off 2/4 (5d2341e). baseline (2.3, 1.36, 1.36) × {1.36, 1.69, 2.05}, T=3600 펄스.

## total TTT [veh·h]

| 셀 | NC | WU-CD-F | PFO-link | P-Stack | P-Stack−PFO |
|---|---|---|---|---|---|
| dmid (×1.36) | 1,859.0 | 1,771.3 | **1,216.0** | 1,242.8 | +26.8 |
| dhigh (×1.69) | 2,978.7 | 2,870.7 | 2,124.9 | **2,063.8** | **−61.1** |
| dhigh2 (×2.05) | 4,115.2 | 3,973.5 | **3,158.8** | 3,304.5 | +145.7 |

## delay 분해 (u_dly / f_dly / term_u / term_f)

| 셀 | PFO-link | P-Stack | 해석 |
|---|---|---|---|
| dmid | 336/215/307/138 | 447/131/557/152 | freeway 과보호(f −84)를 urban(+111)으로 지불 |
| dhigh | 1,001/344/1,483/202 | 959/325/1,751/173 | **양축 동시 우위(u −42, f −19)** |
| dhigh2 | 1,729/524/3,229/227 | 1,766/633/3,230/663 | freeway 잔존 +435 — 극한서 청산 실기 |

## 판정
- **펄스(청산형) dual-binding에서 P-Stack vs PFO = 1승 2패** — externality 무대를 만들어도
  일과성 스트레스에선 국소 metering(PFO)이 이기거나 동급. 균형 강도(dhigh, u/f 1,102/1,097
  NC 대칭)에서만 양축 동시 우위로 계층이 승리.
- 패배 셀의 기제가 대칭적: dmid = 중강도 과보호(hinge/far 보호 비용이 무대 수요 초과),
  dhigh2 = 극한서 freeway 잔존 방치(청산 국면 전환 실기). leader의 보호-흡수 전환 캘리브레이션이
  sustained 기준으로 동결된 탓.
- **미해방 채널 주의**: 펄스에선 λ̂(admission 채널)가 deadband(절대 stock 게이트)에 막혀
  전 스텝 휴면 + fallback guard 억압 — 현 P-Stack은 조정 채널 절반이 잠긴 상태의 성적.
- WU-CD-F는 dual에서 NC 대비 −3.6~−4.7%로 무력(metering 부재) — 권한 격차 재확인.

## 남은 가설(미측정 — 주장 금지)
externality 가치의 본무대는 dual-binding **sustained**(T=7200)일 것 — 펄스는 국소 근시안이
유리한 청산 동역학, sustained는 가격·예산이 적분되는 평형 압력. 측정 전까지는 가설.

## 원자료
outputs/_dsuite/8seg_pulse_d{mid,high,high2}_{base3,flag}/ (구망 부분출력은 _dsuite_oldnet_partial)
