# 다음 할 일 — P-Stack(4) 자율 재설계 (사용자 지시, 2026-07-24)

> 사용자가 AI에게 **자유도 부여**. 아래를 다음 작업 세션에서 실행할 것. (이 MD 작성 시점엔 실행 안 함 — 저장·푸쉬만.)

## 지시 (사용자 원문 요지)

P-Stack(4)를 여기저기 수동으로 고치는 게 다 안 통함. 그래서 AI가 **서브에이전트 3종**으로 자율 진행:

1. **원인 검증 에이전트** — P-Stack(4)가 PFO보다 나쁜 원인을 검증.
2. **컨트롤러 설계 에이전트** — 원인 검증 결과에 따라 새 컨트롤러(leader-follower objective) 설계.
3. **구현 에이전트** — 설계한 컨트롤러 구현.

추가 지시:
- **인터넷 서칭**해서 objective에 어떤 항을 넣으면 좋을지 조사, **넣었다 뺐다** 하며 leader-follower objective function 전 영역을 골고루 탐색.
- **사본(copy)에서** 작업할 것 (원본 오염 금지).
- **설계 컨트롤러가 PFO보다 5개 시나리오 전부에서 좋을 때까지** 계속 run.

## 성공 기준 (하드)

새 컨트롤러 windowed TTT < PFO(pfosplit) **5셀 전부**: Low(155)/Medium(170)/Skew(170skew)/Incident(170inc)/High(190). 참고 목표는 P-CENT(오라클).

---

## 현재까지 진단 (재도출 금지 — 이걸 출발점으로)

### 문제
P-Stack(4)=`pstack4_`(leader+PFO_SPLIT=2, 4-agent, 감독자 없음) windowed TTT vs PFO:
- Low 2966/PFO2961(+5), Med 3781/3862(**−81**), Skew 3808/3835(**−26**), Inc 5826/5497(**+329**), High 6131/5970(**+161**).
- **Med/Skew 이기고 Inc/High 크게 짐.**

### 원인 (측정됨)
- **Incident**: leader가 freeway 과-metering → freeway delay 2046(PFO 3456)로 과보호, urban delay 1972(PFO 233)로 **과전가**. freeway는 capacity-drop이라 어차피 잼(ρ~180)이라 metering이 잼을 못 풀고 **urban으로만 밀어냄**. → 덜 조이는 게 나음. 리더가 92% PFO를 따라가는데 사고순간(step25 t=4680) N_UF를 2400(PFO 5100)으로 슬램하는 몇 단발 스파이크가 5000초 뒤 urban 붕괴로 cascade.
- **High**: metering은 PFO와 동일(합 137). 차이는 **green split** — 신호 F에 phase1 green +16초 과-조정 → urban delay 2191(PFO 1992)로 악화. (VSL 동일 100.)
- **공통 근본**: leader objective가 **평평/오판**. incident서 leader-선택 objective 316.4 vs PFO-incumbent 317.2 = **Δ0.8인데 실제 TTT 329 차이**. objective가 진짜 차이를 400배 과소표현 → 후보 구별 못함(held-plan H-step rollout이 지평 밖 urban buildup 못봄). per-ramp 가격 ~0(gradient 죽음)이라 배분도 균일.

### 안 통한 처방들 (재시도 금지)
- **far weight**: incident만 −179(끄는게 나음), 나머지 far-gate off라 무관. PS4 여전히 PFO 패.
- **far 완전 off**(pstack4faroff_): incident 5826→5647(개선) but PFO 5497 여전히 패. Low/Med/Skew 변화 0.
- **leader hinge**(LEADER_HINGE=1, ttthinge_): 무익, High +149 악화.
- **box-walk**(LINK_BOX_WALK): PS4서 완전 무효(bit-identical).
- **감독자**(SUP_PFO/SUP_GATE=fargate): incident서 fargate가 감독자 꺼서 무효(5826→5829).
- **PFO anchor**(all_evaluations 필터, env PFO_ANCHOR=1, stackelberg_mpc.py:595): 구현했으나 step25 슬램이 refined 스텝(bounds 강제)이라 부족 가능.
- **far-split**(urban/freeway reservoir 분리가중, MFD_FAR_W_URBAN/FREEWAY): 진행중(task bmbj3vo9k, 30런). 완료 시 analyze_farsplit_grid.py로 확인. 단 Low/Skew는 far-gate off라 무의미.

### 오라클·비교 (핵심)
- **P-CENT(중앙 grid, 목적함수=P-Stack과 동일)가 valid oracle**: 전 셀 PFO 이상 (Inc 5498≈PFO5497, High **5599**, Med **3729** 최소). **차이=freeway↔urban 균형**(P-Stack 과-metering, P-CENT 균형). **램프 차등 아님**(P-Stack std 2.8 > P-CENT 1.9). P-CENT 잔류혼잡도 매번 최저.
- **b13(21-agent+감독자, camp_s10on_)은 PFO와 경쟁적**: Low/High 이김(2927<2961, **5809**<5970), Inc 근소패(5609 vs 5497), Med/Skew 근소패. **stripped PS4보다 훨씬 나음.** b13 우위=**21-agent 세밀도**(감독자 아님 — incident서 감독자 off). freeway/urban도 b13 2500/1301로 균형.
- **PFO는 far 없음**(leader 전용). PFO 강함=버그 아니라 발견.

### 방향 (설계 힌트)
"덜 조여라" — freeway 과보호(metering)·green 오조정을 줄여 **urban을 지키게**. objective가 지평 밖 urban 비용을 보게 만들거나(정확한 종단비용), 후보를 closed-loop replay로 채점(held-plan 근시 제거), 또는 per-ramp/green 가격이 non-zero로 배분을 옳게 몰게. 문헌(MFD/perimeter control, gating, ramp metering ALINEA, MPC terminal cost)에서 objective 항 조사.

---

## 재현 정보 (필수)

- **repo**: Numerical-Sim-offiter, branch `cross-gate`. 사본에서 작업.
- **시뮬 python**: `C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` (anaconda 아님). 분석용 pandas는 `C:/Users/alsrj/anaconda3/python.exe` + `PYTHONIOENCODING=utf-8`.
- **실행**: `PY -u work/run_claude_style_five_controller.py --scenario <SC> --T-total 14400 --controllers <CTRL> --output <OUT>`.
- **셀→시나리오**: 155=sweet_155_w, 170=sweet_170_w, 170skew=sweet_170_skew15_w, 170inc=sweet_170_incident_w, 190=sweet_190_w. (skew=urban 방향비 1.5, freeway 대칭.)
- **컨트롤러**: PFO=`WU-FAITHFUL-FOLLOWER`, P-Stack=`P-STACK-WU-FAITHFUL-ALLPRICE-JOINT`(클래스 F1StackelbergWuMeteredController), P-CENT=`P-CENT`(grid, dense=False가 빠름/sparse).
- **P-Stack(4) env**: `WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111 NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1 BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2` (unset SEG13 METER_BOX VSL_BOX SUP_PFO SUP_GATE).
- **windowed TTT**: cumulative_total_ttt[end(t≤14400)] − cumulative[step==WARM−1=4]. 지역분해=summary.csv(freeway_delay/urban_delay=TTT−자유류ref, ref는 컨트롤러 무관 상수라 비교=TTT비교). delay 절대값은 urban_avg_speed_km_h=50 가정 의존 — raw TTT 권장.
- **긴 sim은 메인세션 background bash**(서브에이전트 금지 — 못 기다림). kill: cmdline[0]에 'codex-runtimes' 매칭(self-kill 회피).
- **objective 코드**: leader V = `_predict`(held-plan H-step rollout TTT) + `mfd_far_cost_to_go`(far, gated) + `leader_hinge_cost`(hinge, 기본 off). stackelberg_mpc.py. far 분리가중 이미 구현(w_urban/w_fw, line ~103·203).
- **핵심 스크립트**: work/analyze_pcent_vs_pstack.py, analyze_farsplit_grid.py, analyze_2x2_leader_granularity.py.

## 진행 중 (인계)
- **far-split 30런 (task bmbj3vo9k)**: 실행중일 수 있음. 완료 시 analyze_farsplit_grid.py. Inc/High만 정보 있음(Low/Skew far-off).
