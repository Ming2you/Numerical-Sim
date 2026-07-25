# 진단 브리핑 — P-Stack이 PFO에 지는 이유 & 공정 수정 설계 (2026-07-25)

## 목표 & 공정성 제약
- **목표**: 계층형 Stackelberg-MPC 컨트롤러 **P-Stack(4)**가 분산 기준선 **PFO**를 5개 시나리오
  (Low/Med/Skew/Incident/High) 전부에서 이기게(windowed TTT 더 작게) 만든다.
- **공정성 제약(사용자 명령, 절대)**: 리더 rollout **깊이(LEADER_V_DEPTH)를 절대 늘리지 마라.**
  깊이를 늘려 이기면 "더 멀리 봐서" 이긴 것 → PFO/P-CENT 대비 불공정. 수정은 **목적함수/
  terminal cost/가격**에서만. terminal cost의 존재 이유가 "짧은 지평으로도 올바로 판단"이므로 이게 정도.

## 컨트롤러
- **PFO** = `WU-FAITHFUL-FOLLOWER`: 분산 기준선(리더 없음). Wu(2022) 충실 follower.
- **P-Stack(4)** = `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT`: 계층. 리더가 스칼라 예산(N_P 도심, N_UF 프리웨이)
  + per-lever 한계-외부성 가격 설정 → follower들이 Nash로 자기 지역 통행시간 최소화 응답.
  리더 목적 = held-plan H-step(=3, 540s) rollout TTT + far(MFD tail cost-to-go, FAR_GATE로 개폐).
- **P-CENT** = `CentralizedMPC`(구조격자): 중앙 오라클. 실시간 아니지만 상한 기준.

## 스코어보드 (windowed TTT, warm5~14400. 작을수록 좋음)
| cell | PFO | PS4 | G-CLF(R3) | P-CENT |
|---|---|---|---|---|
| Low(155) | 2961 | 2966 | 2966 | — |
| Med(170) | 3862 | **3781**✓ | 3781 | 3729 |
| Skew(170skew) | 3835 | **3808**✓ | 3808 | — |
| Incident(170inc) | **5497** | 5826✗ | 5818 | 5498 |
| High(190) | **5970** | 6131✗ | 6138 | 5599 |
- PS4는 Med/Skew만 이김. Incident/High 패배. Low 동률.
- **P-CENT는 High서 5599로 PFO(5970)를 371 이김** → High는 오라클 수준이면 PFO 이길 여지 실재.
  Incident는 PFO≈P-CENT(5497≈5498)라 오라클 수준 = "따라잡기" 목표.

## ★핵심 발견 1: freeway/urban 분할 (PS4는 freeway 과보호)
windowed total = freeway + urban:
| cell | ctrl | freeway | urban | urban% |
|---|---|---|---|---|
| Inc | PS4 | 2584 | 3242 | 55.6% |
| Inc | PFO | **3995** | **1503** | 27.3% |
| Inc | PCENT | 2874 | 2625 | 47.7% |
| High | PS4 | 2584 | 3547 | 57.8% |
| High | PFO | 2622 | 3348 | 56.1% |
| High | PCENT | **2768** | **2831** | 50.6% |
- **PS4는 항상 freeway 최저(2584)·urban 최고** = freeway 과보호/urban 희생.
- **오라클(P-CENT)·PFO는 freeway 혼잡을 수용하고 urban을 보호.**
- High 예: PCENT vs PS4 = freeway +184(나쁨), urban −716(좋음), net −532 승. **freeway 1 : urban 4 유리 트레이드.**
  PS4는 이 트레이드를 안 함 → 리더 목적이 freeway 완화를 과대평가(또는 urban 과소평가).

## ★핵심 발견 2: 메커니즘 = metering throughput 후퇴 → 경계 과-holding
per-step (Incident, 임계창): meter=total_metering_flow, bndQ=boundary_in_load_veh, uAcc=urban_accumulation_veh
| step | PS4 meter/bndQ/urbΔ | PFO meter/bndQ/urbΔ |
|---|---|---|
| 25 | **2400**/50/120 | **5792**/55/119 |
| 35 | 5417/350/371 | 4895/103/212 |
| 40 | 5100/599/532 | 5784/159/269 |
| 45 | 5056/650/650 | 4260/**15**/244 |
| 50 | 4029/692/457 | 2590/**23**/97 |
- **PFO: metering throughput 높게 지속 → boundary 큐 거의 0(15-159) → urban 큐 안 쌓임.**
- **PS4: metering 진동·후퇴(step25 2400 슬램) → 차를 경계에 붙잡음(과-holding) → bndQ 폭발(350-692) → urban TTT 누적.**
- High도 동일: 회복기(45-55) PCENT meter=6000/6000/4068(지속) vs PS4=6000/4436/3395(후퇴) →
  PCENT step55 uAcc=195(배수완료) vs PS4 uAcc=443(linger).

## ★핵심 발견 3: 내 CLF(Round3) 실패 원인 = boundary+protected 합산 벌점의 역인센티브
- 시도한 수정 Mod1 URBAN_CLF: 리더 목적의 urban terminal cost를 볼록 CLF로 재설계
  (far_urban = excess²·tc/(2·g_eff), excess=max(0,n_u−n_ref), n_u=protected+boundary).
  gated(far gate 동조): Low/Med/Skew 비트동일 보존, Inc/High만 발화.
- **결과: Inc G−base 겨우 −7, High +7(오히려 악화).** N_UF@25는 2400→5400 바뀌었으나(슬램 멈춤)
  TTT 개선 없음. High서 urbΔ 688→695(악화).
- **원인(실증): n_u = protected + boundary를 합쳐 벌점 → 리더가 "boundary를 urban에 쏟아부어
  합을 줄이는" 역인센티브. boundary(경계 대기)는 metering 유입률로 배수되는데(빠름), protected(도심
  gridlock)는 MFD 생산율로 배수(느림) — 둘을 같은 g_eff로 처리한 게 개념 결함.**
- 또한 old far_urban도 죽지 않았음(gate창 mean Inc 604/High 1469; 이전 "far dead"는 protected-only 측정오류).
  far는 이미 목적의 ~60% 지배(far/rollout: Inc 1.67, High 1.42).

## 리더 levers & 목적 구조
- levers: N_P(도심 예산), N_UF(프리웨이 예산), ramp metering, green split, VSL.
- 목적(depth0, mfd_far_at_d0=True): rollout_ttt(3스텝) + w·(w_urban·far_urban + w_fw·far_fw) + hinge(off).
  w=w_urban=w_fw=1.0 기본. FAR_GATE=3(폐쇄예보 OR capdrop실측)로 far 개폐.
- far_urban: urban reservoir(n²/(2·g)). far_fw: freeway 본선 2차 + ramp 큐 merge대기.
- 코드: `src/controllers/stackelberg_mpc.py::mfd_far_cost_to_go`(L86~), 호출 L2417(states[-1] 말단).

## 데이터·재현
- per-step 전체표: `2026-07-25/results/policy_comparison.txt` (Inc/High × 4컨트롤러).
- 원자료 CSV: `outputs/_diag/{pstack4,pfosplit,pcent,redesign_G}_{170inc,190}/<CTRL>/run_log.csv`.
  컨트롤러명: PS4/G=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT, PFO=WU-FAITHFUL-FOLLOWER, PCENT=P-CENT.
- 분석 python: `C:/Users/alsrj/anaconda3/python.exe` (PYTHONIOENCODING=utf-8 필수).
- windowed TTT = cumulative_total_ttt[time≤14400] − cumulative_total_ttt[step==4].
- 공통 컬럼: cumulative_{total,freeway,urban}_ttt, urban_accumulation_veh, boundary_in_load_veh,
  total_metering_flow, ramp_metering_release_actual_{R_D_E,R_D_W,R_F_E,R_F_W}_veh.
- **주의**: 긴 sim은 서브에이전트에서 절대 실행 금지(기존 로그 CSV만 분석). 시나리오 재실행은 메인세션 담당.
