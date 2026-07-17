# 논문 최종 분석 계획 v2 — 3-Stage 틀의 walk-MVG 인스턴스화 (2026-07-17)

**모(母) 문서 = `docs/literature_grounded_post_analysis_plan.md`** (같은 repo). 분석의 틀 —
Stage 1(6컨트롤러 paired 비교) / Stage 2(Trigger→Action→Mediator→Outcome 이벤트 검증) /
Stage 3(coupling 정보·player ablation), 지표 정의, PASS/FAIL, 주장 가능/불가 — 는 전부
모 문서를 따른다. **이 문서는 모 문서를 최종 컨트롤러(walk-MVG)와 논문 5셀에 인스턴스화**
하고, ① 현 구현이 모 문서 가정과 다른 지점(적응 노트), ② 지금 데이터로 가능한 것 vs 런이
필요한 것, ③ 이번 세션(2026-07-16~17)의 신규 발견(§5 한계 절 소재)을 추가한다.

v1(도표 나열식)은 폐기. 단 v1의 컬럼 함정 사전·검증 목표치는 본 문서 §0에 승계.

---

## §0. 전제 (분석 시작 전 필독)

### 0.1 최종 컨트롤러와 6컨트롤러 매핑
모 문서 §2.1의 6컨트롤러를 현 코드베이스로 매핑하면:

| 모 문서 ID | 현 구현 | 상태 |
|---|---|---|
| WU-CD-F | `WU-CD-F` (기존 구현) | **런 필요** (5셀 × T=10800) |
| WU-MATCHED-STACKELBERG | 기존 구현 | **런 필요** |
| WU-CC-F | 기존 구현 | **런 필요** |
| PROPOSED-FOLLOWERS-ONLY | PFO = `WU-FAITHFUL-FOLLOWER` (**SEG13 금지**) | **런 필요** (수치 기준선은 §0.4) |
| **PROPOSED-STACKELBERG** | **walk-MVG** = `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT` + 아래 플래그 | **완료** — data/walk_mvg |
| PROPOSED-CENTRALIZED | P-CENT | **런 필요** (느림 — 계산 배율 ~8×) |

walk-MVG 플래그(재현 명령 전문은 §7):
`BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1
FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20`

★주의: 2026-07-13에 완료된 구(舊) 풀 매트릭스(4컬럼 표, ProposedLeaderValue +3,355 등)는
**구 컨트롤러·구 규약(T=7200 등)** 결과다. 참고는 하되 **새 표에 혼입 금지** — 전부 재실행.

### 0.2 논문 셀 5개 (+ 한계 서사용 1개) — 모 문서 §2.5 시나리오 축과의 대응
| 셀 | 모 문서 축 | walk-MVG (PFO 대비) |
|---|---|---|
| sweet_155_w | low demand — 불필요 activation 확인 | +5.10% |
| sweet_170_w | 중수요 / freeway bottleneck | +11.14% |
| sweet_170_skew15_w | urban boundary imbalance | +9.81% |
| sweet_170_incident_w | 본선 폐색(capacity-drop) | +3.03% |
| sweet_190_w | high transfer / combined stress | +9.38% |
| (sweet_200_w) | **§5 한계 전용** — 본문 표 금지 | −20.68% |

### 0.3 채점 규약
- NC 웜업 20스텝, T_total=10800(60스텝).
- **wTTT = cumulative_total_ttt[마지막 행] − cumulative_total_ttt[step==20 행]**.
- 개선% = (PFO_ref − wTTT)/PFO_ref × 100.
- **Delay 계산(모 문서 §2.6)**: free-flow reference는 시나리오별로 **별도 산출**(NC 재사용
  금지) — free-flow reference 런이 §6 큐에 있다. reference 확보 전에는 delay 열을 비우고
  TTT만 보고.
- seed: 현 스위트는 결정적 단일 seed. 모 문서 §2.7의 seed 통계는 **적용 불가**를 명기하고,
  bootstrap은 셀 축(across-scenario)으로 대체. 이는 주장 범위 §18("단일 run 일반화 금지")에
  걸리므로 서술에서 "시나리오별 사례 연구 + 5셀 일관성"으로 프레이밍.

### 0.4 PFO 수치 기준선 (2026-07-16 확정, 정수 반올림)
155_w 1,776 / 155_skew15 1,745 / 155_skew 1,791 / 155_incident 1,481 / 170_w 3,021 /
170_skew15 2,957 / 170_skew 3,081 / 170_incident 2,367 / 190_w 5,689 / 200_w 7,196.

### 0.5 ★컬럼 함정 사전 (실측으로 밟은 것 — 위반 시 분석 전체 오염)
| 함정 | 진실 |
|---|---|
| `leader_lambda_np_committed` | **λ가 아니라 boolean**. 0.425 = 커밋 duty cycle |
| 진짜 λ_P | `wu_faithful_lambda_P` (`wu_faithful_np_cand_lambda`=별칭, `*_applied`=또 다른 0/1) |
| `N_P_star`/`N_UF_star` (run_log) | **realized**(출력폐쇄). 리더 의도 = `leader_candidate_best_intent_*` |
| `wu_seg13_budget/presplit_*` | per-step last-write-wins — incumbent probe 오염. intent 컬럼은 신뢰 |
| `wu_faithful_np_pd_exit` | −1 미실행/0 K소진/1 잔차수렴/2 λ고정점. **2 & λ=cap = 경계 고착** |
| green 시계열 | control_timeseries의 `green_*_p{1,2}` (신호당 합 112 고정) |
| `metering_price_trust_frac` | 이동 제약 아님(가격 FD 폭). SEG13 경로에선 dead write |
| 박스 영수증 | `wu_seg13_meter_box_r/edge/total`, `wu_seg13_vsl_box_r` — **부재 = 훅 불발 = VOID** |
| allocation | **팔로워가 `{}`로 hard-disable** — `allocation_*` 컬럼 전부 0이 정상 |

### 0.6 데이터 패키지 (현재 커밋 기준)
```
data/<arm>/<cell>/{run_log, control_timeseries, state_timeseries, decision_diagnostics}.csv
  walk_mvg(본문) / farsa_ref(③ 앵커) / pd4_ref(진동 원인 상태) / box300_vsl10_ref(walk ablation 짝)
  × 논문 5셀 + 200_w
```
6컨트롤러의 나머지 5개와 free-flow reference, Stage 3 ablation 런은 **런 머신이 §6 큐로
생산해 같은 구조로 추가 커밋**한다.

---

## Stage 1 — 6컨트롤러 비교 (모 문서 §2 그대로, 5셀)

**분석 컴퓨터가 지금 할 수 있는 것**
- walk-MVG 열 전체: wTTT·urban/freeway 분해·완주 대수·terminal 잔존·compute
  (`computation_time_sec` — 벽시계라 같은 머신 런끼리만 비교).
- PFO 대비 개선%(수치 기준선), 표 골격(6컨트롤러 × 5셀) + "런 대기" 마킹.
- **fidelity matrix**(모 문서 §2.4)의 walk-MVG 행 초안 — plant/authority/objective/horizon/
  solver/coupling iteration. §5 발견(dual inert, 박스, walk)이 objective/solver 행의 정직한
  기재 사항.

**런 완료 후**
- paired comparison 6종(WuLeaderValue, ProposedLeaderValue, 중앙화 2종, package 차이 2종).
  ProposedLeaderValue = J(PFO) − J(walk-MVG) — **이번 논문의 헤드라인**.
- delay 계열 지표(free-flow reference 확보 후), throughput·terminal 동반 표기
  (모 문서 §2.6: "TTT만 낮추고 큐를 horizon 밖으로 미루면 개선 불인정").

산출: `analysis/stage1/six_controller_summary.csv`, `paired_comparisons.csv`,
`fidelity_matrix.md` (모 문서 §15 구조).

## Stage 2 — 메커니즘 검증 (모 문서 §3~8, 이벤트 단위)

공통 사슬 Trigger → Action → Mediator → Outcome, 이벤트 상태 6분류
(NOT_CHALLENGED … CONGESTION_SHIFT), pre/response/outcome window — 모 문서 그대로.

### 적응 노트 (현 구현이 모 문서 가정과 다른 곳 — 실측 근거)
| 컨트롤 | 모 문서 가정 | 현 구현 실측 | Stage 2 처리 |
|---|---|---|---|
| allocation | 활성 채널 | **hard-disable**(`{}` — movement cap 1400 고정) | 이벤트 카탈로그에서 제외, fidelity matrix에 명기 |
| offset | 활성 채널 | 일부 셀에서 0 동결(190/200_w 실측) | challenged 이벤트 0이면 NOT_CHALLENGED로 정직 보고 |
| green | trust 6s/step | 준수(max 6.00) | 그대로 |
| VSL | max_vsl_step 20 | walk-MVG는 VSL_BOX ±10(previous 앵커) | trigger-반응 지연에 박스 지연(스텝당 10) 반영 |
| metering | no-metering 대비 제한 | **m_prev±300 박스** + 예산사영 | 반응 지연 = ⌈필요이동/300⌉스텝 — incident 셀에서 특히 확인 |

### 이벤트 추출 (분석 컴퓨터, 지금 가능)
- VSL 이벤트(§6): trigger = ρ→ρ_crit 접근(state_timeseries 밀도), action = vsl_* 하강,
  mediator = 상류 sending flow·density-exceedance AUC. `vsl_response_delay`에 박스 지연 명기.
- metering 이벤트(§7): trigger = merge 밀도/receiving factor, action = ramp_metering 제한,
  mediator = merge 밀도 peak·mainline discharge, 비용 = ramp/`x_on` 큐.
  **walk-MVG 대 pd4_ref 대비가 핵심 그림**: pd4의 풀스팬 진동(λ 점프 스텝 Σ|Δ| 2,218)
  vs walk-MVG ≤300 — "같은 trigger에 침착한 반응".
- green 이벤트(§4의 green 부분): 부하 신호 쪽 서비스 이동 여부.
- 상호작용 사슬(§8): on-ramp response 사슬(receiving↓ → metering 강화 → x_on 증가 →
  urban green 관리 → 회복 후 완화)을 190_w에서 재구성.

### counterfactual (런 머신 필요 — §6 큐)
- frozen replay / closed-loop ablation은 시뮬 재실행이라 런 머신 담당.
  분석 컴퓨터는 이벤트 카탈로그(t0, window, 방향 정확도)를 먼저 완성해 replay 대상
  이벤트 목록을 런 머신에 넘긴다.

산출: `analysis/stage2/control_event_catalog.csv`, `vsl_events.csv`, `metering_events.csv`,
`interaction_chain_events.csv`.

## Stage 3 — coupling 정보·player 가치 (모 문서 §9~13)

기본 컨트롤러 = walk-MVG. 케이스: FULL / NO_U_TO_F / NO_F_TO_U / NO_CROSS / LOCAL_ONLY +
FIXED_URBAN / FIXED_FREEWAY / FIXED_ALL — **전부 런 필요**(기존 Stage 3 인프라 재사용,
8케이스 × 5셀 = 40런). 분석 컴퓨터는 런 도착 후:
- 방향별 한계가치, BidirectionalSynergy, Shapley-style Φ_{U→F}/Φ_{F→U} (모 문서 §12 식).
- 구 결과(u→f 주채널, Φ_F_to_U 음수, FIXED_ALL 파국 초가산)와의 정합/변화 보고 —
  단 구 결과는 구 컨트롤러이므로 "재확인" 프레임.

산출: `analysis/stage3/*.csv` (모 문서 §15).

## §5. 한계·메커니즘 검증 절 소재 (신설 — 2026-07-16~17 세션 발견)

전부 측정 완료, data/로 재현 가능. Stage 2의 "정직 보고" 원칙의 연장.

1. **dual 가격 감사**: ③에서 λ_P·λ_UF 비영 0/40(λ_UF는 mode 기본 equality라 갱신 자체
   없음, λ_P는 corrector 음수 잔차 clip). NP_OFF bit-identical 10/10. PD를 켜면 λ가
   {0,10} bang-bang(중간값 0/400) — gain을 내부 착지(1.0)로 바꾸면 오히려 평균 −5.32%.
   → 실작동 조정 = **N_UF hard budget(BUDGET_OFF 시 −79%) + marginal price**.
2. **선형 가격 × 이산 후보 = bang-bang**: 내부 rung 0/160, 부호→끝점 80~85%,
   시간평균은 내부값(~1,295) = bang-bang이 내부 최적을 흉내. 처방 = 박스(외삽 제거,
   폭=가격 FD 측정폭 300) — pd4_ref 데이터로 재현.
   **후속 A/B 완료(2026-07-17 저녁, 기각 2건)**: 박스 위에서 (a) cross 2종 부활,
   (b) metering 가격 가중 0.5 — 둘 다 **박스 끝 선택률을 못 바꿈**(85~100% 유지;
   pw0.5는 5/10셀 bit-identical = 반감해도 여전히 지배). 각자 다른 극단 셀을 깨뜨림
   (crossON: 200 +11.0로 구제하나 190 −47.2 / pw0.5: 170_incident −77.9).
   **세 번째 두더지 잡기**(PD4: skew↔190, 박스: 170s↔200, cross: 200↔190) — 극단 부하
   셀은 단일 처방으로 동시 구제 불가. 끝점 선택은 박스 내에서 강건 → 남은 경로는
   2차 자기항(3점 FD)뿐이나 기대값 낮음, 선택 과제.
3. **200_w 서사** (그림 1순위): 회복기 리더 intent — ③ 5485→6000 / box300_vsl10 **3190
   고착** / walk-MVG **5805 해방**(BOX-WALK가 가설 확증). 잔여 −20.7% = rate limit 물리
   (③는 턴에서 +2,400/step, 박스는 +300). 데이터: 3팔 × 200_w.
4. **VSL rate limit은 원래 Jacobi 반복 단위**: ③ 스텝당 최대 50(명목 20의 2.5배,
   112/7020) — VSL_BOX(previous 앵커)로 교정. ③ 결과에 포함되나 전 구성 공유라 A/B 무오염.
5. **리더 trust region 부재·우회가 load-bearing**: 명목 반경 1500은 앵커 우회로 무효
   (후보 항상 [1200,6000]), 강제 시 파국 2회 독립 확인(−19.99%/−32.31%).
6. **기각 계보 표**: gain1.0 / STRICT×2 / 구box300(VSL구멍) / up600·up900(올림 확대) /
   BUDGET_OFF / walk-M(중단). 모 문서 §18 "사후 튜닝 금지"에 대한 응답 — 전 팔이
   사전 등록식 A/B였고 전부 데이터로 기각됐음을 표로.

## §6. 런 머신 큐 (이 컴퓨터 — 우선순위 순)

| 순위 | 런 | 목적 | 규모 |
|---|---|---|---|
| 0 | (진행 중) crossON / weight0.5 | §5-2 처방 갱신 | 20런 |
| 1 | **free-flow reference × 5셀** | Stage 1 delay 계산 전제 | 5런, 빠름 |
| 1 | **PFO 풀런 × 5셀** (`WU-FAITHFUL-FOLLOWER`, **SEG13 금지**) | Stage 1·2 | 5런 |
| 1 | NC × 5셀 | 표 참고 열 | 5런 |
| 2 | WU-CD-F / WU-MATCHED-STACKELBERG / WU-CC-F × 5셀 | Stage 1 Wu group | 15런 |
| 3 | P-CENT × 5셀 | 중앙화 상한 | 5런(느림) |
| 4 | Stage 3 ablation 8케이스 × 5셀 | Stage 3 | 40런 |
| 5 | Stage 2 counterfactual replay (이벤트 목록 도착 후) | Stage 2 | 이벤트 수만큼 |
| 6 | leave-one-out 21 agent × 5셀 | 임계성 히트맵(선택) | 105런 |

★기준선 재현 검증: 각 baseline 첫 런은 기존 수치(§0.4 등)와 대조 후 본runs 진행.
★PFO에 SEG13 주면 5배 악화(실측) — 금지.

## §7. 재현 명령

```bash
# walk-MVG (최종)
BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
python work/run_claude_style_five_controller.py --scenario <cell> --T-total 10800 \
  --controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT --output <dir>
# ③ 앵커: CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20
# PD4: ③ + NP_PD_ITER=4 NP_BIAS=1
# box300_vsl10: PD4 + METER_BOX=300 VSL_BOX=10
```
코드: offiter repo `cross-gate` 브랜치, e2d144b 이후.
