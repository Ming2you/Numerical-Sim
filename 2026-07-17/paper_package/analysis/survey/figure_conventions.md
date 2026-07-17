# 그림 컨벤션 서베이 및 처방 보고서 (에이전트 렌즈 1, 2026-07-18)

## Part A. 서베이 결과 — 접근한 논문의 그림 인벤토리

### A-1. Wu, Li, Xi (2022), IEEE TCST 30(1):57-70 — **그림 인벤토리 미확인**
- IEEE Xplore 페이월. Semantic Scholar openAccessPdf 없음. arXiv/저자 버전 검색 실패. 로컬 PDF 없음.
- **결과 그림 목록은 미확인이며 발명하지 않음.** 기관 계정으로 원문 그림 목록(결과 절 시계열 구성·TTS 보고 방식) 확인이 1순위 TODO.
- 그때까지 같은 계보(METANET+urban queue, De Schutter 계열)의 Van den Berg 2007을 검증된 대리 컨벤션으로 사용.

### A-2. Hegyi, De Schutter, Hellendoorn (2005), TR-C 13(3):185-209 — **접근 성공** (저자 PDF, 캡션 전수 추출)
| Fig | 유형 | 내용 |
|---|---|---|
| 1 | 개념도 | Fundamental diagram, critical density/speed 정의 |
| 2-3 | 개념도 | speed limit이 상태를 옮기는 메커니즘 |
| 4 | 블록도 | MPC 구조 |
| 5 | 모델도 | METANET link-segment 분할 |
| 6 | 네트워크도 | 벤치마크 망(VSL 2구간 + metered on-ramp, 라벨) |
| 7 | 시계열 | **demand scenario 독립 그림** |
| 8/9/10 | 결과 시계열 | NC / RM only / VSL+RM — **케이스당 1그림 동일 레이아웃 반복** |
| 11-14 | 네트워크도+결과 | 두 번째 벤치마크 + 변형 |

핵심 관례: ① 비교는 overlay가 아니라 동일 레이아웃 반복 ② 밀도는 ρ_crit 수치와 함께(33.5 veh/km 명기, "임계 접근 시 metering 점진 활성"을 캡션 수준에서 결합) ③ 캡션은 takeaway 포함 완결 문장 2-3개, TTS 스칼라는 본문 수치로.

### A-3. Keyvan-Ekbatani, Kouvelas, Papamichail, Papageorgiou (2012), TR-B 46(10) — **박사논문 5장으로 검증**
- NFD(total weighted flow vs occupancy), TTS vs time(gated/non-gated), **ordered flow(검정) vs actual flow(유색)** overlay, 제어 후 operational NFD(운영점 구름, **replication 겹침**).
- 핵심 관례: ① 성능 시계열 표준형 = 누적 지표 vs time 두 곡선 ② 명령=검정/실현=유색 ③ 운영점 증거는 FD/NFD 평면 산점 구름.

### A-4. Papamichail & Papageorgiou, HERO — **그림 인벤토리 미확인**
- 텍스트 검증: ramp queue-length/waiting time control 루프 존재 → **ramp 큐를 명시적 보고 대상으로 삼는 전통** 확인. 그림 축 구성은 미확인 — ramp-queue-as-cost 그림의 축 설계는 VdB07 Fig 9 차용.

### A-5. Van den Berg, Hegyi, De Schutter, Hellendoorn (2007), EJTIR — **접근 성공(로컬 PDF)**
- Fig 1-7 모델·변수 정의도, Fig 8 케이스스터디 망, **Fig 9 큐 제약 효과(최대 큐 12 veh 제약선)**, **Table 1: TTS를 freeway/urban으로 분해한 표가 1차 결과 보고 수단**.
- 핵심 관례: 통합 urban+freeway 논문은 **스칼라 성능=분해 표, 그림=메커니즘 증거 1-2장**.

## Part B. 처방 — 동결 프레임(§1-§5)별 그림 설계

전역: 단일 축(서브플롯 금지) → **패널을 독립 그림으로 분해하되 시간축 범위·눈금을 그림군 내 동일 고정**, 캡션에 "시간축은 Fig. X와 동일" 명시. 선 구분: solid/dashed/dotted/dash-dot + marker, 축당 최대 4곡선. **기준(NC·명령)=검정, 제안=유색**. 공통 오버레이: warmup shading, 제어 활성 수직 점선, ρ_crit 수평 점선+라벨. 캡션: 첫 문장=무엇(축·조건), 둘째 문장=읽을 결론.

### §1 (표 유지 + 보조 그림 2)
- **Fig 1a 수요 시나리오 독립 그림**(Hegyi Fig 7): x=time, y=demand(veh/h), origin별 곡선, 펄스 shading.
  캡션: "Demand profiles for the sustained and pulse scenarios. The pulse scenario injects …% of nominal demand during the shaded interval."
- **Fig 1b 누적 TTS vs time overlay**(K-E Fig 5-2/5-4): 대표 시나리오 1개, NC(검정)/WU-CD-F/P-CENT/제안.
  캡션: "Cumulative TTS under the four controllers for scenario X. The hierarchical controller diverges from WU-CD-F after control activation (vertical line), accounting for the −…% gap in Table Y."
- (선택) Fig 1c 격차 분해 dot plot — 전례 없음, 지면 여유 시.

### §2 (임계선 운영)
- **Fig 2a 밀도 vs 임계선(필수)**(Hegyi Fig 9): x=time, y=병목 세그먼트 밀도(veh/km/lane), ρ_crit 수평 점선+수치, 케이스당 1그림 반복 또는 NC(검정)+제안(유색) 2곡선 1장.
  캡션: "Density of the bottleneck segment under {controller}. The controller holds the operating point just below the critical density ρ_crit = … veh/km/lane (dashed line); metering activates at the vertical marker."
- **Fig 2b FD 운영점 구름**(K-E Fig 5-10/5-18): x=density, y=flow, 제어 전(회색)/후(유색) 점, ρ_crit 수직 점선.
  캡션: "Operating points on the flow–density plane before (grey) and after (color) control. Gating/metering confines operation to the uncongested side of ρ_crit."
- **Fig 2c 제어 입력 계단 플롯**(Hegyi Fig 9-10): metering rate zero-order-hold, VSL·green은 각각 별도 그림.
  캡션: "Ramp-metering command under the hierarchical controller. The rate drops as the mainstream density approaches ρ_crit (cf. Fig. 2a, identical time axis)."

### §3 (가격 채널 — 직접 전례 없음, 문법 차용)
- **Fig 3a 채널별 가격 시계열**: y=0 수평 참조선 필수(부호가 주장), warmup shading.
  캡션: "Inter-network price signals over time. Φ_F→U remains negative throughout congestion onset, quantifying the spurious pressure identified in §3."
- **Fig 3b 가격×이동폭 누적 곡선**(단위 환산 규약 반영, K-E 누적 문법).
  캡션: "Cumulative externality transfer per channel, converted to TTS-equivalent units. The u→f channel carries …% of the total gain."
- **Fig 3c 명령 vs 실현 overlay**(K-E Fig 5-3 직차용): 검정=목표, 유색=실현.
  캡션: "Ordered (black) versus realized (color) boundary flow at the urban–freeway interface. Tracking degrades only during the pulse interval."

### §4
- **Fig 4a criticality heatmap**: x=시나리오, y=link/segment, color=max ρ/ρ_crit(=1을 diverging 중심).
  캡션: "Peak density ratio ρ/ρ_crit per link and scenario. Cells above 1 (red) indicate links that cross criticality; the freeway merge is the only universally critical element."
- **Fig 4b coupling graph**(라벨 네트워크도 문법): 간선 두께=결합 강도(가격×이동폭), 색=부호, 주채널 라벨.
- (선택) Fig 4c time-space 밀도도 — 접근 검증 4편에 없음 명기, 쓰면 NC/제안 2장 동일 colorbar.

### §5
- **Fig 5a replication 산포**(K-E '10 replications'): 결정론 단일시드면 생략 또는 시나리오 산포로 대체.
- **Fig 5b VSL 강도 dose-response**: 운영점 수직 점선.
- **Fig 5c ramp 큐 비용 그림(필수)**(VdB Fig 9 축 + HERO 전통): y=on-ramp queue(veh), 저장한계 수평선, NC(검정)/비교/제안.
  캡션: "On-ramp queue under each controller with the storage constraint (horizontal line). … the hierarchical controller respects the constraint while … saturates it."

## 요약
접근 성공 Hegyi05/K-E12/VdB07, 미확인 Wu22(기관 확인 TODO)/HERO. 필수 3그림(밀도-임계선, ramp-queue-as-cost, VdB식 분해표+메커니즘 배분) 충족.
