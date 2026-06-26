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

## 층2 (N_P 박스 타이트닝) — 구현·검증·반증·롤백
2-probe 실측 도달범위로 N_P 후보 박스를 좁히는 층2를 구현(leader transient slot +
orchestrator 2-probe + flag)하고 sweet_128에서 검증했다.
- 박스는 **기계적으로 정상 작동**: applied=1, [403,688]/[231,645]/... 측정·주입됨.
- 그러나 **컨트롤러 동작 0 변화**: intent N_P 전 스텝 0(여전), realized 값·total_ttt가
  층1과 **비트 단위 동일**(454.6068).
- **가설 반증**: 평원이 leader를 가둔 게 아니다. leader는 박스와 무관하게 **PFO fallback(N_P=0)**
  을 고른다. authority probe에서 N_P 권한이 보였던 건 그 probe가 `stackelberg_enable_fallback=False`
  였기 때문 — 실제 컨트롤러(fallback ON)에선 **PFO가 N_P-active 후보를 이긴다.**
- **진짜 병목 = fallback guard(PFO 우위) / leader objective 정렬**, 박스 아님.
- 판정: 층2는 무익(스텝당 follower solve 2회만 추가, 결과 동일) → **전부 롤백.** 층1만 유지.
- 다음 후보(원하면): PFO가 왜 N_P-active를 이기는지 — leader objective 가중/정렬 진단, 또는
  fallback guard 임계 재검토. (박스가 아니라 여기가 N_P 활용의 관문.)

## ★ 핵심 발견: fallback guard가 N_P 개선(~9%)을 억누름 (사용자 지적 적중)
fallback을 끄고 PFO/fb-on/fb-off TTT를 직접 비교(sweet_128, 8스텝):
| | total_ttt | vs PFO | N_P |
|---|---|---|---|
| PFO | 370.65 | — | — |
| P-Stack **fb-ON**(현 production) | 352.88 | +4.8% | maxN_P=0 (N_UF만) |
| P-Stack **fb-OFF** | **320.75** | **+13.5%** | **maxN_P=497** |

- **fb-OFF가 fb-ON보다 32 TTT(~9%) 더 좋다.** fallback guard가 진짜 개선을 버리고 있었음.
- N_P는 redundant 아님 — leader 가치를 +17.8→+49.9(≈3배)로 키움.
- **근본원인**: leader objective의 TTT 어긋남(벌점 mfd/density/boundary). N_P-active leader는
  실제 TTT가 좋은데 penalized obj가 높아, guard가 penalized obj로 PFO와 비교→기각. 게다가
  fallback incumbent가 탐색을 pruning해 fb-ON에선 searchBest=0(N_P 안 보임).
- **앞선 "N_P 구조적 redundant" 결론은 틀림** — fallback pruning 아티팩트를 오독한 것. 사용자가
  fallback 끄라고 끝까지 민 것이 이 ~9%를 드러냄.

### 진단 경로(반증의 반증 기록)
- np_authority_probe(fallback=False): N_P 권한 있음(TTT 142→134).
- 층2 박스 타이트닝: 무익(fb-ON에선 fallback이 막아 박스 무관).
- np_activation_vs_demand(fb-ON): N_P intent=0 → "demand/구조" 오결론 유발.
- np_search_vs_fallback(fb-ON): searchBest=0 → fallback pruning 아티팩트.
- reverse_pfo_in_box: PFO점 box 안(box 문제 아님), objective가 TTT와 어긋남(N_P=643 vs TTT N_P~457).
- **compare_fallback_ttt(fb-OFF): 결정타 — fb-OFF가 PFO/fb-ON 압도(+13.5%/+9%).**

## (a) guard를 rollout-TTT 비교로 수정 — 구현·검증 완료
- `_fallback_guard_rejects`: 1차 기각을 penalized obj 대신 **realized rollout-TTT**로
  (`leader_ttt > fallback_ttt + margin`이면 기각). flag `stackelberg_fallback_guard_use_rollout_ttt`
  (기본 true), rollout_ttt 결측 시 기존 obj 로직 fallback. terminal/completed severe는 유지.
- 검증(8스텝, fb-ON):
  | 시나리오 | 수정 전 | 수정 후 | PFO |
  |---|---|---|---|
  | sweet_128 | 352.88 (+4.8%) | **319.9 (+13.7%)** | 370.65 |
  | sweet_115 | 246.82 (=PFO) | 248.97 (−0.9%) | 246.82 |
  | sweet_190 | 756.59 (=PFO) | 756.59 (=PFO) | 756.59 |
- **per-step rollout 예측 한계**: 128(복리이득)/115(근소손해)를 per-step으론 구분 못 함.
  margin 선택 트레이드오프 — lenient(동률 채택): 128 +13.7%, 115 −0.9% / margin≈0: 128 +5.7%, 115 0%.
  → **사용자 결정 lenient**(헤드라인 최대화, 저부하 −0.9% 수용).

## (b) deep 과포화 over-metering — 진단: headroom 없음(근본 한계)
- sweet_190 분해: leader가 freeway −20 개선하나 boundary_in 큐 +186 폭증 → urban +36 → net +16.5 악화.
  (사용자 직관 "boundary 막힘" 메커니즘적으로 맞음.)
- (정정 2026-06-26) **boundary는 이미 leader penalty에 들어가 있다** — `_urban_halfcap_excess`가
  boundary_in/out movement를 `mfd_boundary_queue_capacity_veh=220`의 50%(110/gate) 초과분으로
  가격책정(`mfd_storage_weight=1.0`, `mfd_penalty_mode=all_urban_halfcap` 활성). 별도 `w_boundary_in`
  (=0.0)은 redundant 항. 즉 "boundary 누락"은 틀린 진단.
- **진짜 병목 = leader 예측 호라이즌이 9분(horizon_steps=3 × control_interval=180s)** 인데 boundary
  buildup은 ~24분(8 control step)에 걸쳐 621까지 감. leader는 누적 초반만 봐서 과metering 대가를
  과소평가 → half-cap도 w_boundary_in도 예측창에서 안 물림. (w=1 무효=예측 boundary≈작음, w=20에서야
  반응=작은 예측치 증폭. 게다가 621이 7게이트 분산 시 ~89/gate라 110 임계 미달이기도.)
- 근본 해결은 가중치가 아니라 **horizon_steps 확장**(다스텝 누적을 보게) — 후보당 rollout 비용↑.
  (사용자: 현 개선으로 충분, 미착수.)
- 근본원인: 과포화(수요>용량)는 총지연 비가역. leader는 지연을 freeway↔boundary로 재배치만.
- (a) guard가 sweet_190을 옳게 PFO로 defer → 회귀 없음. **deep 과포화는 leader 가치구간 아님(정상).**
- (확정) leader 가치 = moderate 혼잡(sweet_128). (a)가 거기서 +13.7% 해금.

## 결론 / sweet spot
- **sweet_128**이 임무 답. guard를 TTT로 고치니 production(fb-ON) 이득이 +4.8%→**+13.7%**.
- 층1 완료(커밋 cb6fc8e). 층2(박스) 반증·롤백. **진짜 레버 = fallback guard 척도/ leader objective 정렬.**
- 다음: (a) fb-OFF가 항상 좋은지(sweet_190/115 비교 진행중) → guard 비활성 vs guard를 rollout-TTT로
  비교하게 수정 결정, (b) sweet_128 T=3600 정밀 재실행, (c) capacity-drop ON 커밋 여부.
