# 2026-07-25 작업 요약 — P-Stack(4) 공정 재설계 (depth 불변)

## 무엇을 했나
목표: 계층형 Stackelberg-MPC **P-Stack(4)**가 분산 기준선 **PFO**를 5셀(Low/Med/Skew/Incident/High)
전부 이기게 만들기. **제약(사용자 명령): 리더 rollout 깊이(LEADER_V_DEPTH)는 절대 변경 금지**
— 깊이를 늘려 이기면 PFO/P-CENT 대비 불공정. 수정은 목적함수/terminal cost/가격에서만.

작업 순서:
1. Round2 E콤보(depth6) **폐기**(불공정) — 프로세스 kill.
2. **Mod1 URBAN_CLF** 구현: 리더 목적의 urban terminal cost를 볼록 CLF+기울기외삽으로 재설계,
   far gate 동조(gated) 플래그 추가. (코드: `stackelberg_mpc.py`, `state.py`, `run_claude_*.py`)
3. **Round3**(gated CLF, 5셀) 실행·판정.
4. **정책 역설계**: PS4/PFO/P-CENT의 freeway·urban TTT 분할 + per-step 제어(metering/boundary) 추출.
5. **Probe**(far_fw 하향가중, ground truth) 실행.
6. **진단 워크플로우**(4렌즈 원자료 검증 → 진단 잠금) — Phase1-2 완료.

## 핵심 결과

### R3 gated CLF — 실패
| cell | PFO | PS4 | G-CLF | 판정 |
|---|---|---|---|---|
| Low/Med/Skew | 2961/3862/3835 | 2966/**3781**/**3808** | 동일 | base 비트동일(승리 보존) |
| Incident | 5497 | 5826 | 5818 | −7뿐(무개선) |
| High | 5970 | 6131 | 6138 | +7(악화) |
→ Low/Med/Skew 안전 보존. Inc/High 못 고침. 실패원인 실증: boundary-dump 역인센티브 +
  freeway-capdrop gate가 High urban 캐스케이드(step49-75)에 못 닿음.

### Probe far_fw 하향 — 방향 맞으나 불충분
- Incident: far_fw off → 5826→5647(−179), 오라클 균형쪽 이동. 그러나 여전히 PFO에 +150 패.
- High: 6131→6129(**무력**). freeway-gate가 좁아 far 거의 발화 안 함.
→ ★"순수 재가중"은 사망. "freeway-gated 수정"은 High 원천적으로 못 닿음.

### ★★ 확정 진단 (원자료 재검증, 전문 `results/LOCKED_DIAGNOSIS.md`)
PS4는 freeway를 과보호하고 차를 경계에 과-holding해 진다. 두 시간분리 실패, 하나의 뿌리:
- **(A) 온셋**: Inc st25 리더가 freeway예산 N_UF 5700→2400 슬램 → 3스텝(540s) rollout 안 값싼
  freeway 완화를 얻으나 차를 경계에 쏟음. 이게 씨뿌린 urban 캐스케이드 정점은 **step42-43 =
  결정보다 17스텝(~3000s) 뒤 = 지평 밖**이라 rollout이 원천적으로 못 봄.
- **(B) 회복**: 오라클의 진짜 승리 행동은 metering이 아니라 **도심 green 서비스 확대**
  (PCENT green 60-70 vs PS4 45-56 → 동부하 배출 +72~85%). PS4는 도심이 안 빠져 못 이김.
- **구조 뿌리**: far_urban이 boundary+protected를 단일 g_eff로 합산배수 + N_UF는 도심에 지렛대
  없음(R3 실증) + urban 가격이 배출 flow 아닌 축적 stock(n²/2g)에 걸림.

## 다음 수정 스펙 (진단 처방 종합, 깊이 불변)
우선순위 순:
1. **[최우선] urban 배출-flow 가격화**: stock(n²/2g) 대신/추가로 urban 배출율(green-split 서비스
   throughput)을 가격화 → "내보내기(green 확대)"가 터미널 비용을 낮추는 싼 길이 되게. 오라클의
   회복기 green 확대를 리더가 스스로 선택하게. `mfd_far_cost_to_go`의 urban 항에 배출-flow 보상 추가.
2. **far_urban 탈합산 + 경계 홀딩 과금**: protected(느린 MFD 배수)와 boundary(경계 대기) 분리.
   boundary를 "즉시 배수가능"으로 값싸게 두지 말고 하류 urban TTT로 과금 → 온셋 N_UF 슬램을 값비싸게.
3. **always-on(freeway-gate 비의존)**: probe가 증명하듯 High 캐스케이드는 gate 닫힌 뒤 → 경계큐
   증가율·urban state 기반 leading 항으로 always-on. (n_ref는 운영점 아래로 — R3 기울기0 함정 회피)
4. **레버↔가격 정합**: urban 가격은 N_P·green 레버에, boundary-holding 가격은 N_UF/metering에.

**피할 함정**: R3 boundary-dump / n_ref≈운영점(기울기0) / 순수 재가중 / stock-vs-flow / 온셋 N_UF 슬램.

## 산출물
- `notes.md` — 상세 작업 노트 + 전 측정치.
- `results/LOCKED_DIAGNOSIS.md` — 워크플로우 진단 종합(원자료 재검증).
- `results/BRIEFING.md` — 진단 브리핑(데이터 딕셔너리 포함).
- `results/policy_comparison.txt` — PS4/PFO/P-CENT per-step 정책·성과 비교.
- `modified_code/` — 수정 코드 백업. `work/` — 런처·분석 스크립트.

## 미완/주의
- 워크플로우 Phase3-5(설계 4안 상세·적대검증·구현스펙)는 인터럽트로 미완 — 위 "다음 수정 스펙"이
  진단에서 직접 종합한 대체안. 재개하려면 `resumeFromRunId: wf_b61c79b2-667`.
- 최종 확정은 위 스펙 구현 → 5셀 실행 → PFO 전부 이기는지 판정 후. **아직 이긴 컨트롤러 없음**
  (현재 최선도 Inc/High서 PFO에 짐).
