# 2026-07-13 작업 노트

## 1. r̂ 편향 보정 구현 (커밋 c1c5b9b, NP_BIAS=1, 기본 OFF)

### 배경 — λ̂ 휴면 근본원인
NP-CAND-λ̂ 채널이 전 셀에서 λ̂=0으로 휴면. 원인은 **계획 공간 vs 실현 공간 불일치**.
- 예측(계획) Σnin ≈ 2,123 > target 1,730 (+368, 40/40 스텝) — 모델은 항상 초과를 예측.
- 실현 ΔN_P×H ≈ 1,500 < σ_min — 실측은 상한에 닿은 적 없음(모델 낙관 편향 ~30%).
- corrector가 실현 Q를 계획 target과 비교하므로 λ가 오를 수 없는 구조.
- 등식제약/음수 λ 대안은 실측으로 기각(28,242 파국·보조금 병리, 07-12 기록).

### 구현
- `wu_faithful_follower.py` — `_np_bias_ratio` EWMA 추적. 스텝 시작 1회 블록에서
  ratio = clip(실현 Q / |예측 Σnin|, 0.05, 2.0), EWMA β=0.3.
  corrector: `λ = Π[λ + γ(Q_real − r̂·Ñ_committed)]`, predictor: target을 `r̂·Ñ^(c)`로 환산.
  플래그 OFF면 r̂=1.0 곱 → **비트동일**(IEEE754 1.0*x 정확).
- `state.py` — `mpc.np_bias_correction: bool = False` (동결 헤드라인 매트릭스 보호).
- 러너 — `NP_BIAS=1` 훅, 진단 `wu_faithful_np_bias_ratio` 수출.

### 스모크 (sweet_190, 720s=4스텝, NP_BIAS=1)
- bias_ratio: 1.0 → 0.866 → 0.702 → 0.542 (EWMA 정상 추적, 워밍업이라 실현/예측 비율 낮음).
- λ̂=0 유지 — 워밍업 구간 실현 유입(≈1,200) < r̂·1,730이므로 정상 거동.
- 발동 실측(혼잡 피크 도달 셀)은 사용자 지시로 제외 — 디폴트 전환 전 A/B 별도 결정.
- 출력: `outputs/_npbias_smoke/on/`.

### 주의
- 활성화 시 190 계열 거동이 바뀔 수 있음(실현 ~1,500 > r̂·1,730 ≈ 1,211 → λ̂ 발동 예상).
  **디폴트 ON 전환은 반드시 5-suite A/B 후 결정.**

## 2. WU-CD-F 컬럼 완료 → 4컬럼 메인 표 확정 (results/main_table_4col.md)
- 문헌 Wu(green+VSL only, metering 용량 고정) 12셀 완료: sustained 7(T=7200) + suite pulse 5(T=3600).
  (중간보고 때 22,901.8을 190으로 오기 — 실제는 170_skew. 190 = 28,324.3. 정정.)
- 비교 유효성: 셀별 free_flow_reference 전 컬럼 일치 확인(190=2507.448 등). NC 원자료는
  컨트롤러 무관이므로 λ수선 전 xval(155계열)·_8seg/nc(190)·_170(170계열) 값 사용 가능.
- 핵심: WU-CD-F는 sustained −1.2~−9.4%(155_skew만 −20.8%, green 재배분 레짐), 펄스 169%+
  사실상 NC 동급 → **권한 격차(metering, −40%p↑)와 조정 격차(P-Stack−PFO-link, sustained 7/7승
  −23~−1,281)가 표에서 분리**. 구 "WU" 컬럼은 PFO-link(권한 동등 ablation)로 재라벨 확정.
- P-CENT 8-seg 재측정 반영: 190 = 18,527.4 (계층 −15.5% 우위, 계산 1/8). 구 4-seg 17,929 대체.

## 3. P-CENT 8-seg 전셀 발주 + 계산비용 집계 (사용자 지시)
- P-CENT SLSQP 나머지 11셀 3체인 병렬 발주(suite 5 / 155계열 3 / 170계열 3,
  outputs/_pcent/slsqp_8seg_{suite,155fam,170fam}.log). 단독 실측 475s/스텝 기준
  sustained 셀당 ~5.3h — 병렬 경합 감안 총 16~30h 예상.
- 계산비용 사다리(12셀 mean_step_compute_sec): PFO-link 3.6s < WU-CD-F 11.1s <
  계층 59.2s < P-CENT 475.3s. **계층만 ci 180s 실시간 경계 내(33%), P-CENT는 2.6배 초과.**
  상세는 results/main_table_4col.md 계산비용 절.

## 4. urban-binding 펄스 suite 설계·발주 (사용자 지시)
### 배경
suite 5셀의 delay 분해로 P-Stack≈PFO의 원인 확인 — 혼잡의 59~95%가 freeway·ramp 몫이고
urban은 자유류 근방(NC u_delay 37~896 vs sustained 190의 15,146). leader의 채널(urban green
가격·N_P)은 urban 포화를 전제로 하므로 suite에선 얹을 마진이 없음. 사용자 지시 =
"urban이 혼잡해지는 baseline을 찾아 같은 1.36/1.69/2.05 펄스를 걸어라".

### 캘리브레이션 (NC 프로브, freeway=ramp=0.5 고정)
- urban_scale 스윕: U 1.6/2.0/2.4/2.8/3.2 → u_delay −41/−31/+11/+89/+196.
- **U100(urban 방류천장) = 2.4** (delay 0-교차 = 유입≈최대 방류 개시점).
- 강도 검증(NC): ×1.36 u_delay 215·잔존 325 / ×1.69 510·723 / ×2.05 928·1,368,
  f_delay는 28/37/67로 자유류 유지 — **기존 suite의 정확한 거울상**(urban-binding).

### 셀 정의 (scenarios.yaml 추가 — 순수 additive, 실행 중 체인 무영향)
- pulse_umid: urban 3.264 / fw·ramp 0.68 (= (2.4, 0.5, 0.5)×1.36)
- pulse_uhigh: urban 4.056 / fw·ramp 0.845 (×1.69)
- pulse_uhigh2: urban 4.92 / fw·ramp 1.025 (×2.05, fw는 천장 1.36의 75%로 부임계)
- 펄스 구조 동일(base 0.5, 900/300/900/300, T=3600 20스텝).

### 발주
- 4-arm(NC/WU-CD-F/PFO-link/P-Stack SEG13=1 equality — 동결 12셀과 동일 구성 확인:
  postsplit==budget, presplit<budget 스텝도 budget으로 상향 = equality) × 3셀,
  outputs/_usuite/. 프로브 스크립트는 scratchpad(probe_urban_ceiling.py).

## 5. urban suite 결과 — 판정: urban-binding에선 green-only Wu가 전승
| 셀 | NC | WU-CD-F | PFO-link | P-Stack |
|---|---|---|---|---|
| umid(×1.36) | 802.6 | **753.2** | 761.6 | 766.0 |
| uhigh(×1.69) | 1,196.8 | **1,157.4** | 1,183.3 | 1,173.5 |
| uhigh2(×2.05) | 1,741.5 | **1,705.5** | 1,755.6(NC↓) | 1,722.6 |

- 전 컨트롤러 개선폭 작음(최선 −2.1~−4.9%) — urban 혼잡의 lever는 green 재배분뿐
  (경계 유입 외생·turning ratio 고정), freeway-binding의 −32~−45%와 대조.
- **WU-CD-F 3/3 전승** — green이 유일 lever인 무대에선 문헌 Wu가 최적(포화×skew 게이트 정합).
  metering 권한(PFO/P-Stack 강점)은 freeway 자유류라 무용.
- P-Stack>PFO 2/3(uhigh −9.8·uhigh2 −33.0, umid +4.4): uhigh2에서 PFO는 NC보다 악화
  (own-TTS 국소 휴리스틱 심층포화 역효과)를 leader가 교정. 방향은 가설대로, 크기 0.6~1.9%.
- **논문 지도 3축 완성**: freeway-binding sustained=계층 필수 / freeway-binding pulse=국소 충분
  / urban-binding=마진 자체 소멸·green-Wu 최적 → 계층 가치 = 결합 스트레스(양망 동시) 레짐.

### λ̂ 부동 제3원인 (uhigh2 step-쌍 추적)
- 유일 위반 스텝(step 7: 실현 2,035 > 커밋 target 1,831, +204)에서 **경부하 deadband가
  신호 폐기** — 게이트가 절대 stock 기준(accum 588 < 0.9×N_P_crit 1,142=1,028)인데
  펄스는 stock이 flow 지연 추종이라 loading edge에서 항상 미달.
- 함의: NP_BIAS=1(r̂)만으론 펄스에서 안 열림 — deadband 게이트 재설계(커밋 target 연동
  또는 예측 stock 기준) 필요. **구조 변경이라 사용자 승인 대기.**

## 6. dual-binding suite 설계·발주 (사용자 교정)
### 사용자 교정
"내가 말한 건 urban도 freeway도 혼잡한 상황 — 한쪽만 혼잡하면 local info로 충분하고,
둘 다 혼잡해야 externality 항을 가진 P-Stack이 좋을 것." §4~5의 urban-only suite는
설계 의도와 다른 무대였음(결과는 green-lever 단축 자료로 보존).

### 캘리브레이션
- freeway=ramp를 단독 천장 1.36에 고정하고 urban 스윕: 1.36/1.8/2.2/2.6 →
  u_delay −49/−46/−11/+63. **결합 urban 천장 U* = 2.3** (0-교차 ≈2.26; 단독 2.4보다
  낮음 = off-ramp 유입 결합 효과).
- dual baseline = (2.3, 1.36, 1.36), 셀 = ×{1.36, 1.69, 2.05}.
  freeway축 1.85/2.3/2.8은 기존 suite와 정확히 동일(비교 대칭성).
- NC 사전검증(u_delay/f_delay/잔존): dmid 427/758/1,157 · dhigh 1,135/1,027/3,020 ·
  dhigh2 1,880/1,300/4,667 — **양망 동시 스트레스 + 단일축 대비 초가산**(dhigh u 1,135
  vs u-suite 510, f 1,027 vs f-suite 976) = externality 무대 형성 확인.

### 셀 정의(scenarios.yaml 추가)
- pulse_dmid: urban 3.128 / fw·ramp 1.85
- pulse_dhigh: urban 3.887 / fw·ramp 2.3
- pulse_dhigh2: urban 4.715 / fw·ramp 2.8

### 발주
- 4-arm(NC/WU-CD-F/PFO-link/P-Stack SEG13=1) × 3셀 → outputs/_dsuite/.
- 세션 재시작으로 P-CENT 3체인 사망 확인(각 1스텝 손실) → sustained 2체인(155/170계열)만
  재발주, suite용 P-CENT는 suite 구성 확정 뒤로 보류.

## 7. plant 변경 — 다이아몬드 인터체인지 재배치 (사용자 승인, 5d2341e)
### 스펙 (사용자 정확 지정)
seg2 off(OR_D) / seg3 on(R_D) / seg4 off(OR_F) / seg5 on(R_F) — merge만 4→3, 6→5 이동.
구 seg4의 merge+off 동거 해소, 각 인터체인지 내 exit가 entrance 상류(무 weaving),
마지막 merge(5) 뒤 tail 2세그. default.yaml + test_metanet_equations 기하 assert 갱신.

### 재캘리브레이션 — 천장 불변 판명
- freeway축: 구 suite 하중(1.85/2.3/2.8 flat) NC 교차검증 → f_delay 730/1,058/1,328
  (구망 688/976/1,273, +4~8%) — **1.36 기준 유지**.
- urban 결합천장: fw=1.36 고정 스윕 1.8/2.1/2.4/2.7 → −46/−23/+21/+87, 0-교차 ≈2.26
  → **U*=2.3 유지** (off-ramp 위치 불변이라 당연). pulse_d* 시나리오 수치 그대로 유효.
- dual 3셀 NC(새 plant): 384/811/985 · 1,102/1,097/2,934 · 1,839/1,370/4,563 —
  dhigh가 u/f 거의 완전 대칭(1,102/1,097).

### 처리
- 구망 체인 3개(세션 재시작으로 이미 사망) 확인 폐기, _dsuite 부분출력 →
  _dsuite_oldnet_partial 보관 이동. **구망 기준 기존 측정치(4컬럼 표 등)는 이제 구-plant
  역사 자료** — 새 plant 재측정 필요 목록: 메인 sustained 표·WU-CD-F 컬럼·suite·oracle·P-CENT.
- 주의: incident 시나리오들의 폐색 seg 번호(3, 6, 7)는 구 기하 의미 — 새 기하에선
  seg3=R_D merge·seg6=본선 tail로 의미가 바뀌므로 incident 셀 재정의 필요.
- d-suite 4-arm×3셀 새 plant 재발주(outputs/_dsuite/). 전체 단위테스트 백그라운드 실행 중.

## 8. dual suite 최종(새 plant) — 펄스 dual에서 1승 2패 (results/dsuite_table.md)
- dmid PFO +26.8 / **dhigh 계층 −61.1(양축 동시 우위)** / dhigh2 PFO +145.7.
- 패인 대칭: 중강도 과보호(f −84를 u +111로 지불) vs 극한 청산 실기(term_f +435).
- λ̂ deadband 휴면 + fallback guard = 조정 채널 절반 잠긴 상태의 성적임을 병기.
- 미측정 가설: externality 본무대 = dual-binding **sustained**(T=7200) — 사용자 결정 대기.
- 단위테스트: 기하 민감 4모듈(139개) 전부 통과, 전체 287 중 실패 7+에러 2는 legacy
  하네스(six_controller 등) 추정 — verbose 재실행으로 목록 확정 중.

## TODO
- [ ] 실패 9건 목록 확정(전체 verbose 실행 중) → plant 소행 여부 판정
- [ ] 새 plant 재측정 프로그램 결정(sustained 표·WU-CD-F·P-CENT·oracle — 사용자와 범위 협의)
- [ ] incident 셀 폐색 위치 재정의(새 기하 기준)
- [ ] 8-seg oracle 재실행(open-loop bound, 구 14,223은 4-seg 값)
- [ ] ε-gap probe 프로덕션 1셀
- [ ] 원고 수정시트 일괄 적용(Word 닫힌 후) + notation rename 실행

## 9. UNLOCK 스모크 판정 → 방법 A 채택 (bf58364)
- dhigh2 1800s(SEG13+NP_BIAS+NP_DEADBAND_V2+FB_OFF): λ̂ step1 헛발화(2.59, base 구간) 후
  진짜 위반(step8 +612, step9 +542)에서 0 유지. r̂는 0.05 클립 바닥으로 오염.
- 3중 고장 확정: ① Q_real=ΔN_P×H가 평형/청산서 0 붕괴(흐름 vs 재고차분 불일치)
  ② r̂ 오염+헛발화 ③ step8~9 λ 유실(배선 추적 필요, applied=0 구간 5~7과 연관 의심).
- 판정: cross-step 적분 사슬(1회 적분+실현 신호+r̂+deadband)은 땜질 불가 →
  **방법 A(candidate 내부 primal-dual, λ^(κ+1)=Π[λ^(κ)+γ(Σν^(κ)−Ñ)])** 채택(사용자 제안).
  계획-공간 신호만 쓰므로 재고측정·r̂·deadband 전부 불요, cross-step 지연 제거.
- 구현 발주: NP_PD_ITER=K 플래그(기본 0=OFF 비트동일), K≤5 조기수렴, γ 25배율,
  최종 λ로 Jacobi 재수렴 후 커밋(off-equilibrium 방지). λ 유실 진단 포함.

## 10. 단위테스트 실패 9건 판정 — 전부 pre-existing (plant 무관)
- pre-plant 커밋(9865155) 임시 워크트리서 동일 3모듈 재실행 → **동일 9건 실패(이름까지 일치)**.
- 구성: forecast_awareness 4(off-ramp 예측 계열) + six_controller 3 + post_analysis 2(legacy 하네스).
- 결론: 다이아몬드 plant 변경은 테스트 무결(기하 민감 139개 통과 + 실패는 전부 선재).
  실패 9건 수리는 별도 백로그(legacy 하네스 정리 시점에 일괄).

## 11. 방법 A 구현 완료 (8410094) — 상세는 커밋 메시지·§9 참조
- λ 유실 3원인 확정(초기충전 오독 / PFO 선택 스텝 pending 단절 / 실현공간 트리거).
- OFF 비트동일 검증(3런 state_timeseries 일치), 스모크: 오발동 소멸·λ cap 발화·Σν 실이동
  (2,054→1,765)·계산 ~1.1×. 주의: cap 10 포화(잔차 +99~+534) → cap 상향 A/B 후보.
- 본 A/B(dual 3셀, NP_PD_ITER=4+FB_OFF) 실행 중 → 잠긴 baseline 1,243/2,064/3,305 대조.
