# 2026-07-15 재선형화(SQP walk) 실험 + 원고 검토

## 배경 — 사용자 통찰에서 출발
metering δ 고정의 문제(155_w 과잉조임 δ300=+21, 200_w cliff 19%)를 부하적응으로 풀려다,
게이팅 신호(본선밀도)가 155/170을 못 가려 **부하적응 δ 기각**(155_w 0.67~0.80× vs 170_w
0.75~0.78× — 겹침). 사용자 제안 = "trust 경계에 닿으면 그 자리서 재선형화"(SQP) —
δ 크게 대신 작은 δ로 여러 걸음.

## offset 재선형화 — 메커니즘 검증 성공, 성능 가치 0
- 구현: `_offset_price_relinearize_walk`(워크트리 Numerical-Sim-offiter, 브랜치
  origin/offset-relin), env `OFFSET_INNER_ITER=K`. 기본 OFF 비트동일.
- **검증**: full 190_w에서 offset 0→**105s** 도달(joint 직접탐색 45~90s 수준), inner_iter=4.
  → **선형 가격 + 재선형화로 뾰족한 레버 제어 가능** 확정(메커니즘).
- **★3-way 분해로 성능 오귀속 정정**:
  | 190_w | wTTT |
  |---|---|
  | joint만(편입 기본) | 5044.6 |
  | 가격ON + relin OFF | **4735.3** |
  | 가격ON + relin K4 | 4733.9 |
  | PFO | 5689.4 |
  → **재선형화 TTT 기여 = −1.4(노이즈)**. −309는 OFFSET_PRICE 활성화 자체의 부수효과.
  **offset 값(0 vs 105s)이 TTT에 무관** — 가격 모드가 다른 걸(green 탐색 smoothness/trust?)
  바꾸는 것으로 추정, 원인 미규명 → **편입 불가**(원인 모르는 이득 = hinge 교훈).

## metering 재선형화 — 절벽 셀 실패, 통일 불가
- 구현: `_metering_price_relinearize_walk`(워크트리 Numerical-Sim-meterrelin),
  env `METER_INNER_ITER` (**METER_PRICE_DELTA=60과 짝 필수** — 미지정 시 δ300이라 설계 붕괴).
  비트동일 확인(170_skew_w 720s = 60.377 일치).
- **4셀 A/B** (walk δ60+K4 vs δ300, windowed [3600,10800]):
  | 셀 | walk | δ300 | PFO | 판정 |
  |---|---|---|---|---|
  | 155_w | **1680.5** | 1796.5 | 1776 | −116 승(PFO도 −95) |
  | 170_skew_w | 3095.1 | 3028.0 | 3081 | +67 패 |
  | 190_w | **4886.3** | 5068.5 | 5689 | −182 승 |
  | 200_w | 7527.2 | 6204.8 | 7196 | **+1322 대패**(δ60 7467보다도 나쁨) |
- **판정: 통일 불가.** walk = "똑똑한 δ60" — 경/고부하 승, **절벽 지배 극한 참패**.
- load-adaptive 작동 자체는 확인(부하↑→걸음↑: 200_w 45% vs 155_w 23%; 앵커 단조하강
  1402→1364→1273→1055). 회랑 floor 준수, cliffup 전 셀 낮음.

### ★근본 원인 (논문 재료)
도달거리는 충분(K4×60 + follower ±60 = 300 = δ300 사거리, 실제 앵커 19까지 내려감).
문제는 **±60 국소 secant가 240 떨어진 capacity-drop 절벽에 눈이 멂**(cliffup 4%) →
문턱에서 먼 곳의 externality 가격이 약함 → 과소보호 + 앵커 요동(19~1500).
δ300의 넓은 단일 secant는 +300 probe가 breakdown 근처를 찍어 **강한 보호 신호** 획득.
**우리가 원했던 "cliffup 낮음"이 곧 절벽 셀 실패 메커니즘.**
후속 설계 가능성(미구현): **step 반경(δ60)과 measure 반경(±300) 분리**.

## §3 확정 문장 재료
1. "가격 추정의 **probe 반경은 externality의 곡률 스케일에 맞아야** 한다. 좁은 국소 secant는
   먼 capacity-drop 절벽에 눈이 멀어, 과포화 레짐에선 넓은 반경 probe가 필수." —
   Weitzman prices-vs-quantities의 정밀 확장.
2. "뾰족한 레버(offset)도 재선형화로 선형가격 제어 가능"(메커니즘 입증; 성능 가치는 별개).

## 원고 검토 (Section 2.3.1, 식 23~27)
- **★식 24·26 오류**: `g_ext^(c)`의 (c) 첨자 제거 필요 — 우변 Ψ_g(ū_F^prb; X)가 후보 무관인데
  좌변만 (c) → 자기모순. 리뷰 2.2 해소안(가격=후보불변, dual/예산만 후보별)과도 모순.
  수정: θ_L^(c) = {λ̂_P^(c), g_ext}, g_ext(k_c) = Ψ_g(ū_F^prb; X(k_c)).
- 식 27 정밀화: ∂/∂u는 구현상 **대칭 FD(secant)**; TTS_global은 **horizon-H**(terminal Φ 제외
  — E1 이중계상 회피)임을 명시; TTS_local,i는 **순수 own-TTS**(가격·dual·정규화 제외).
- dual(식 25): 형식화는 맞으나 동결·시험 무대에서 λ̂≈0(휴면) — 결과 주장이 dual에 기대면 안 됨.
- terminal cost(식 31/32) 정밀화: **T_c 인자 누락**; n_P는 **경계큐 포함**; G_U는 2단 계단
  (MFD 근사)·G_F 상수; μ_r^merge = C_r·R(ρ_m)·T_c with R(ρ)=clip((ρmax−ρ)/(ρmax−ρcrit),0,1);
  t_r은 "in-ramp"가 아니라 **merge 후 하류 본선 주행시간** (I−m_r)·ℓ/v_free.

## 동결 구성 (변경 없음)
FH3 · hinge OFF · 부등식+회랑 α=0.65 · metering δ300/trust0.20 · regret k=3 · β̂ 계기 ·
joint 탐색 유지. 재선형화(offset/metering)는 **편입 안 함** — 메커니즘 규명은 §3 재료.
cross 가격 2종은 "애초에 고려 안 함"으로 서술(코드 제거는 다음 동결 시).

## 진행 중
- offset 가격(OFFSET_PRICE=1) 3셀 검증(155/170_skew/200) — 190_w의 −309가 전 셀 이득인지,
  원인 규명 없이 편입할지 판정용. 결과에 따라 편입 or §3 재료로만.
