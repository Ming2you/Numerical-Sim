# §0 부속 — 튜닝 공개·기준선 공정성·Wu 재현 충실도

> 인용 규약은 `tables/t0_params_controller.md`와 동일. Wu 페이지는 IEEE TCST 30(1),
> 2022, pp. 57–70의 저널 쪽수다(로컬 PDF p.N = 저널 p.56+N).

## (a) 튜닝 공개

제안 컨트롤러(P-Stack walk-MVG)의 모든 노브는 사후 손튜닝이 아니라 **측정형 A/B
사다리**로 고정되었다. 측정 스위트는 10셀(sweet_155_w, 155_skew15_w, 155_skew_w,
155_incident_w, 170_w, 170_skew15_w, 170_skew_w, 170_incident_w, 190_w, 200_w;
`work/mvg_only_queue.sh`)이며, 각 구성 변경은 이 스위트 전체에서 wTTT로 채점된 뒤
채택 또는 기각되었다. 주요 노브의 결정 근거는 다음과 같다. metering 가격 FD 폭은
δ 스캔(60→300)으로 300 veh/h를 선택하되 trust_frac=0.20과 짝으로만 적용했고, 회랑
예산 하한(α=0.65)이 선결 조건임을 함께 측정했다(runner:276–287). metering 이동 박스
반경 R=300은 별도 튜닝값이 아니라 **가격 FD 측정 반폭(0.20×1500=300)과의 일치**로
정한 값이다 — 즉 선형 가격을 측정된 구간 안에서만 사용하고 측정 밖 외삽을 구조적으로
제거한다(follower:2422–2438). VSL 박스 반폭 ±10 km/h도 자유 모수가 아니라 vsl_set
격자 간격(10 km/h) 그 자체다(state.py:569; follower:2396–2403). green 이동 한계 ±6 s는
가격 FD 폭 δ=6 s와 동일 폭이다(sw:53, 62).

기각된 팔은 전부 사전 등록식 A/B로 데이터에 의해 기각되었고 계보를 표로 남긴다
(ANALYSIS_PLAN_FINAL.md §5-2, §5-6). cross 가격 2종 부활(190_w −47.2%p 악화),
metering 가격 가중 0.5(170_incident −77.9%p; 5/10셀 비트동일 = 반감해도 가격 지배),
2차 자기항(구현 전 fd3 3점 곡률 진단으로 사전 기각 — 볼록 61%로 동전 수준, 대상 셀은
오목), PD gain 1.0, 리더 반경 STRICT(파국 2회 독립 확인), 비대칭 박스 up600/900,
BUDGET_OFF(−79%), walk-M(중단)이 그 목록이다.

**정직성 조항(한계 공개).** 본 연구의 평가 셀과 개발 셀은 일치한다 — 별도의 held-out
시나리오 집합은 없다. 위 A/B 사다리가 측정형이었다 해도 구성 선택 자체가 같은 셀에서
이루어졌으므로, 최종 구성의 성능 수치는 **in-sample 성격**을 가진다. 이는 결정적
시뮬레이터·단일 실행 규약(§0.1)과 함께 본 논문의 명시적 한계로 공개하며, 강건성
주장은 개별 수치가 아니라 시나리오 간 방향 일관성에 한정한다.

## (b) 기준선 공정성

**PFO 재현 게이트.** 기준선 PFO(제안 계열의 분산 하한)는 신규 런 6/6 셀이 동결 준거
수치와 Δ < 0.6 veh·h로 일치함을 확인한 뒤에만 본 런으로 사용했다
(`tables/t1_macro_full.md` 메모). PFO에 SEG13 분해를 부여하면 5배 악화되므로 기준선
명령에서 금지했다(`work/baseline_queue.sh`).

**PFO+box.** 제안 컨트롤러와 **동일한 이동 한계**(metering prev±300 박스 5점, green
prev±6 s)를 공유한다(follower:806–810, 2831–2846). 구현 검증은 두 방향으로 수행했다.
플래그 OFF에서 PFO와 36스텝 비트동일함을 확인했고, ON에서 per-step 이동이 정확히
meter ≤300 / green ≤6을 전 셀에서 지키며 이동성(34회)이 보존됨을 확인했다
(2026-07-17/notes.md §12). VSL은 무제한 PFO의 실측 이동이 0이라 한계를 부과하지
않았다(state.py:396–400 주석).

**P-CENT.** 중앙화 기준선에는 이동 한계를 **의도적으로 부과하지 않았다**(사용자 결정
2026-07-18). 이는 비교 조건 불일치가 아니라 rate-limit-free **상한(upper bound)**
프레이밍이다 — 분산·이동 한계·가격 전송이 모두 제거된 지점의 도달 성능을 재는
도구다. 정밀화하면, 실런의 P-CENT 솔버는 연속 NLP가 아니라 **전권 joint 행동공간의
centralized structured grid search(coarse→fine), serial(단일 프로세스 직렬)**이다 —
이 런타임에 scipy가 없어 SLSQP 경로가 성립하지 않았고 ImportError 폴백이 발동했음이
실런 진단(`centralized_slsqp_available=0.0`)으로 확정되었다(cm:554–577, 437–501).
따라서 P-CENT는 spec 16.13의 "동일 budget centralized numerical reference"이지 연속
최적화 천장이 아니며, 본문에서도 그렇게 서술한다.

**WU-CD-F.** 문헌 재현 기준선에는 본 논문의 이동 한계를 부과하지 않았다(문헌 충실
유지; 실측 per-step 최대 VSL 50 / green 36). Wu의 명목 제약에 대응하는 것은 내부
드리프트 클램프(max_vsl_step=20, dc:3026)뿐이다.

## (c) Wu(2022) 재현 충실도 매트릭스

Wu et al. (2022), "Distributed Integrated Control of a Mixed Traffic Network With
Urban and Freeway Networks," IEEE TCST 30(1), pp. 57–70을 로컬 PDF에서 직접 확인해
작성했다. WU-CD-F는 Wu의 분산 조정 구조를 본 플랜트/규모에 이식한 재현이며, 아래
6축이 발표 선택과 본 구현의 편차 전량이다.

| 축 | Wu(2022) 발표 선택 | 본 구현 | 영향 |
|---|---|---|---|
| **Plant** | 예측모델 = S-model + 비목적지 METANET(p. 58, §II); 평가 플랜트 = SUMO 미시 시뮬레이션(p. 65, §V-A) — 모델-플랜트 불일치 내재. off-ramp spillback은 차선수 축소식 Eq. 22(γ, b)로 모델링(p. 61) | 예측모델 = 평가 플랜트(동일 수치 플랜트; METANET 8-seg/링크 + phase-resolved urban 큐 — model-plant match, §0.1 선언). Wu Eq. 22는 재현(lane_reduction=1.0 = full 1-lane; yaml:174–180). 추가로 Wu에 없는 CTM receiving/supply 제약(본선 origin 큐 state.py:830–832, 출구 용량 1600 yaml:95)과 혼잡 regime ν_cong capacity-drop(yaml:165–166)을 플랜트에 넣었다 | 본 구현의 플랜트가 결합·절벽 측면에서 더 가혹하다. model-plant match는 §5 한계로 공개 — 성능 수치는 모델 오차 강건성을 포함하지 않는다 |
| **Authority** | u = [vlim(링크별), g(교차로별)]만 — ramp metering 없음(Eq. 24, p. 61); cycle·offset은 고정 가정(p. 58); VSL은 감소 방향만 v_max=20 km/h 제한(one-sided, Eq. 28, p. 62) | WU-CD-F = green+VSL만, metering=용량 고정, offset=0 고정(dc:346–364) — 권한 충실. urban allocation 채널은 hard-disable(빈 dict → 상수 movement cap 1400 veh/h; dc:363, local_signal_plant.py:30–31, 79–90). 본 플랜트에는 offset 동역학이 존재하나 WU-CD-F는 Wu의 고정 offset 가정대로 0 고정. VSL 클램프는 양방향 ±20(dc:3026) — Wu는 one-sided | 권한 격차 축(제안 계열의 metering·offset 권한)이 문헌 재현과 분리 유지된다. 양방향 VSL 클램프는 Wu보다 보수적(증가 방향도 제한) |
| **Objective** | 전역 TTS + 제어변동 2차 페널티 (Δu)ᵀR(Δu)(Eq. 24, p. 61); 분산 시 agent별 local TTS + 수렴 가속 근접항 J_inter(P_i)(Eq. 34, p. 64). R, P_i 수치 미공개 — **미확인** | agent별 own-TTS(램프 큐·밀도 페널티 포함) + smoothness 가중 0.1(state.py:573–574; dc:2688). J_inter 대응항 없음 — under-relaxation이 그 역할을 대신한다 | 변동 억제 기구는 양쪽에 있으나 형태·수치 동일성은 성립하지 않는다(R 미공개라 검증 불가) |
| **Horizon** | Np = 10, Tc = 60 s → 600 s 예측(p. 65); Tu=60 s(=cycle), Tf=10 s | H = 3, Tc = 180 s → 540 s 예측(yaml:182); Tu=5 s, Tf=10 s — urban은 cycle 집계가 아니라 phase-resolved 5 s substep | 예측 시간창은 유사(600 vs 540 s)하나 스텝 수·urban 시간 해상도가 다르다. 제어 주기도 60 vs 180 s |
| **Solver** | urban agent = MILP(CPLEX), freeway agent = NLP(SQP, MATLAB), 시작점 5개; CC도 SQP(p. 66, §V-C) | 이산 후보 열거 + 국소 플랜트 rollout 채점(green 1 s / VSL 10 km/h 양자화; runner:78–83, yaml:227–229). 연속 NLP·MILP 없음 | 어느 쪽도 전역 최적 보장이 없다(Wu = 다중시작 국소해, 본 구현 = 격자 국소해). 본 구현의 격자는 Wu보다 성기나 rollout은 결합 플랜트 전체를 전진시킨다 |
| **Coupling iteration** | 병렬 agent 최적화 + 상호작용 변수 ỹ 통신(Steps 1–6, p. 64–65); 직전 시각 값으로 warm-start; J_inter로 수렴 가속; 종료 ‖ỹ^(s+1)−ỹ^(s)‖<ε 또는 s>S_max, 사례연구 S_max=5(p. 65–66). ε 값 미공개 — **미확인** | WU-CD-F = Jacobi snapshot 반복 ≤ max_nash_iter=10, coupling residual < 10⁻³, under-relaxation α=0.8, best-so-far commit(dc:1837, 1927, 2914). P-Stack follower의 Jacobi sweep은 s_max=min(10,5)=5로 Wu의 S_max=5와 일치(follower:3777) | 반복 상한·감쇠 기구가 다르다(J_inter 근접항 vs α 블렌딩). 미수렴 시 Wu는 "suboptimal 해 커밋", 본 구현은 best-so-far 커밋으로 동일 정신 |

**미확인 항목 정리.** ① R, P_i 행렬 수치와 ε 허용오차(논문 미공개). ② freeway agent
수의 본문 상충 — p. 65는 "two freeway agents", p. 66은 "six freeway agents"로
서술이 엇갈린다(재현에는 영향 없음 — 본 구현의 agent 분할은 자체 망 기준). ③ 시나리오
1–3의 수요 프로파일 수치(정성 서술만 확인됨).


**SLSQP 변형 실측(2026-07-18)**: scipy 설치 후 단독 런에서 첫 결정 스텝 425.8 s(제어주기 180 s의 2.4배, grid의 ~10배) — **실시간 위반으로 제외**. P-CENT-grid가 '동일 budget의 실시간 가능한 중앙집중 참조'로 정당함이 사후 확인됨. (역사적으로는 scipy 부재로 조용히 grid 폴백됐던 것 — 진단 마커 slsqp_available=0.0이 증거.)