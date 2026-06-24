# 2026-06-25 작업 노트 — sweet 부하 스윕으로 leader-value sweet spot 탐색

## 임무
freeway 양쪽(FW_E/FW_W)이 모두 jam되지 않으면서 적당히 혼잡 → PFO도 작동하지만
P-Stack(leader)이 더 크게 이득을 보는 부하 지점을 찾는다.

## 전제
- leader 가치는 capacity drop ON에서만 발생(2026-06-24 진단 #2). 현 default(미커밋):
  `capacity_drop_anticipation: true`, `metanet_nu_cong_km2_h: 250.0` 유지하고 스캔.
- 컨트롤러: NO-CONTROL / PROPOSED-FOLLOWERS-ONLY(PFO) / PROPOSED-STACKELBERG(P-Stack).
- LeaderValue = PFO_ttt - PStack_ttt (양수 = P-Stack 우위). PFO==P-Stack이면 leader가
  guard에 의해 PFO로 fallback(가치 0).

## 사전 측정 (sweet_122, T=3600, full budget)
- PFO == P-Stack == 34.568% 개선, **LeaderValue = 0.0**, leader 전 스텝 PFO fallback.
- terminal 방향상태: FW_E rho=92.6/spd=8.2 (거의 jam), FW_W rho=24.2/spd=65.3 (free) → 비대칭.
- 결론: merge ~111%(scale 1.22)는 leader 켜기엔 부족.

## 스윕 설계
- scenarios.yaml에 sweet_142/148/155 추가(기존 115/122/128/135 + 상한 앵커).
- 1차 스윕: T=1800, leader 예산 절감(max_evals 6, seed 5)로 7개를 한 프로세스로 실행
  (process pool 재사용 → 콜드스타트 1회). → `outputs/sweet_sweep_fast`.
- leader 켜지는 구간만 T=3600 full budget로 정밀 재실행 예정.

## 1차 스윕 결과
(채울 예정)

## 1차 스윕 결과 (T=1800, 예산 절감)
| 시나리오 | PFO% | P-Stack% | LeaderValue | LV% | leader활성 | maxN_UF* | jam |
|---|---|---|---|---|---|---|---|
| sweet_115 | 17.5 | 17.5 | 0 | 0 | 0 | 0 | moderate |
| sweet_122 | 25.0 | 25.0 | 0 | 0 | 0 | 0 | one-jam(FW_E) |
| **sweet_128** | 17.9 | **32.4** | **+96.9** | **17.6%** | 0.1 | 1500 | **moderate(양쪽 OK)** |
| sweet_135 | 23.4 | 34.8 | +91.5 | 14.9% | 0.1 | 1500 | free(양쪽 OK) |
| sweet_142 | 25.6 | 25.6 | 0 | 0 | 0 | 0 | one-jam |
| sweet_148 | 11.0 | 11.0 | 0 | 0 | 0 | 0 | BOTH-jam |
| sweet_155 | 11.6 | 25.3 | +156.5 | 15.5% | 0.1 | 1200 | one-jam |

- **sweet spot = sweet_128**(merge~117%): 양쪽 jam 없이 PFO 작동(17.9%) + P-Stack +17.6% 우위.
- **maxN_P*=0 전 구간**: leader 가치는 전부 N_UF(freeway metering) 채널. urban N_P 미사용.
- 비단조(122/142/148 jam·leader무) → 축소예산 영향, 정밀 재실행 필요.

## authority probe (sweet_128, warmup=6 혼잡)
- N_P* 도달박스 [-634, 994]인데 **실현범위는 [231, 586]만**(나머지는 dead saturation 평원).
- intent [180~587]만 살아있고 거기서 **total TTT 142.4→133.9(~6%) 변동** → N_P*에 권한 있음.
- leader continuous 탐색이 평원에서 gradient=0이라 N_P*=0(floor)에 갇힘 → ~6% TTT 미회수.
- 결론: 층2(N_P 박스 타이트닝)은 정직성+성능 둘 다 가치 있음(평원 제거 → 옵티마이저가 권한 구간 탐색).

## 층1 출력폐쇄 구현/검증 (stackelberg_mpc.py)
- commit control의 N_P*/N_UF* ← follower realized(net-inflow는 coordinator feasible-set 진단으로
  직접 계산, metering은 clip된 ramp_metering 합). intent는 leader_intent_*/leader_selected_*로 보존.
- 버그2개 수정: ① realized 키가 production 경로 미전파 → coordinator로 직접 계산 ② commit이 다음
  seed로 누수 → `_normalize_previous_leader_reference`에서 seeding은 intent 복원(분리).
- 검증(sweet_128, T=1620, distributed/serial, 9스텝):
  - baseline(no closure) total_ttt=454.6068
  - closure 분리 전 453.9795(seed 누수로 −0.63)
  - **closure 분리 후 454.6068 = baseline 정확 일치 → TTT 불변 + closed=1 realized 보고**
- 기존 unittest 3실패는 closure와 무관(allocation 미사용·VSL 선택, stash baseline 동일).

## 결론 / sweet spot
- **sweet_128**이 임무 답(양쪽 jam 없음 + PFO 작동 + P-Stack +17.6%). T=3600 정밀 재실행으로 확정 예정.
- 층1 완료(정직 보고, 불변). 층2 진행 결정(authority+plateau 확인).
