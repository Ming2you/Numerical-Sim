# 논문 최종 분석 계획 — walk-MVG, 5셀 (2026-07-17 확정)

**이 문서는 다른 컴퓨터에서 자립 실행 가능하도록 작성됐다.** 세션 컨텍스트 없이 이 문서와
`data/`만으로 분석을 시작할 수 있다. 2026-07-15 `analysis_plan.md`(§1~4 골격)를 계승하되,
당시와 달라진 것 — 최종 컨트롤러(walk-MVG), 셀 선정(5셀), §5 신설(한계·메커니즘 검증) —
을 전부 반영했다.

---

## 0. 확정 사항 (전제)

### 0.1 최종 컨트롤러 = walk-MVG
러너: `work/run_claude_style_five_controller.py`, 컨트롤러 `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT`.
```
BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
python work/run_claude_style_five_controller.py --scenario <cell> --T-total 10800 \
  --controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT --output <dir>
```
구성 요소(전부 2026-07-17 커밋, offiter repo `cross-gate` 브랜치):
| 요소 | 플래그 | 내용 | 커밋 |
|---|---|---|---|
| PD4 | NP_PD_ITER=4, NP_BIAS=1 | N_P dual primal-dual 4회(λ bang-bang {0,10}) | (기존) |
| METER-BOX | METER_BOX=300 | metering 후보 = m_prev±300 이동박스 5점 + 예산사영 동일박스 | 0314db7 |
| VSL-BOX | VSL_BOX=10 | VSL 앵커 previous 고정 ±10(기존 snapshot 앵커는 스텝당 50 위반) | 787200a |
| BOX-WALK | BOX_WALK=1 | 리더 rollout(depth 8)에서 metering을 N_UF* 방향 ±300/step 전진 | cd9ddb4 |
| BOX-WALK-VG | BOX_WALK_VG=1 | VSL·green 끝 지속(edge persistence) walk | e2d144b |
| state-aware far | FAR_STATE_AWARE=1 | 터미널 ramp traverse를 V(ρ)로 | (기존 ③) |
| cross OFF | CROSS_OFF=1 | cross 2종 비활성 | (기존 ③) |

### 0.2 논문 셀 5개 (+ 한계 서사용 1개)
| 셀 | 축 | walk-MVG (PFO 대비) |
|---|---|---|
| sweet_155_w | 강도 하단 | +5.10% |
| sweet_170_w | 강도 중단 | +11.14% |
| sweet_170_skew15_w | 공간 gradient | +9.81% |
| sweet_170_incident_w | 문턱/capacity-drop | +3.03% |
| sweet_190_w | 강도 상단 | +9.38% |
| (sweet_200_w) | **§5 한계 서사 전용** | −20.68% — 본문 표엔 미포함, 한계 절에서 정직 공개 |

### 0.3 채점 규약 (절대 변경 금지)
- NC 웜업 20스텝(`WARMUP_NC_STEPS=20`), T_total=10800(60스텝), 분석창 = windowed TTT.
- **wTTT = cumulative_total_ttt[마지막 행] − cumulative_total_ttt[step==20 행]**
  (run_log.csv를 step 오름차순 정렬 후 index 19 = WARM−1. 관례: `r[WARM-1]`, WARM=20).
- 개선% = (PFO_ref − wTTT)/PFO_ref × 100.

### 0.4 PFO 기준선 (2026-07-16 FINAL_matrix_terminal_cross.md, 정수 반올림 저장본)
| 셀 | PFO wTTT |
|---|---|
| sweet_155_w | 1,776 |
| sweet_155_skew15_w | 1,745 |
| sweet_155_skew_w | 1,791 |
| sweet_155_incident_w | 1,481 |
| sweet_170_w | 3,021 |
| sweet_170_skew15_w | 2,957 |
| sweet_170_skew_w | 3,081 |
| sweet_170_incident_w | 2,367 |
| sweet_190_w | 5,689 |
| sweet_200_w | 7,196 |

★PFO **풀 로그**는 이 패키지에 없다(수치 기준선만 있음). §1·§2에 PFO 시계열이 필요하면
아래 §6의 "재실행 필요 목록"대로 발주할 것.

### 0.5 ★컬럼 함정 사전 (이번 세션에서 실측으로 밟은 것들 — 다른 컴퓨터 필독)
| 함정 | 진실 |
|---|---|
| `leader_lambda_np_committed` | **λ가 아니라 boolean** `float(lam_next is not None)`. 0.425 같은 값 = 커밋 duty cycle |
| 진짜 λ_P | `wu_faithful_lambda_P` (`wu_faithful_np_cand_lambda`는 별칭, `*_applied`는 또 다른 0/1 플래그) |
| `N_P_star`/`N_UF_star` (run_log) | **realized** (출력폐쇄가 덮어씀). 리더 의도 = `leader_candidate_best_intent_N_P_star`/`..._N_UF_star` |
| `wu_seg13_budget_*`, `wu_seg13_presplit_*` | per-step **last-write-wins** — incumbent probe(leader=None)가 마지막에 쓰면 0/이월값. 오염 주의. intent 컬럼은 신뢰 가능 |
| `wu_faithful_np_pd_exit` | −1=PD 미실행, 0=K소진, 1=잔차수렴, 2=λ고정점. **exit=2 & λ=cap = 경계 고착(수렴 아님)** |
| green 시계열 | run_log가 아니라 **control_timeseries.csv** (`green_{A..F}_p{1,2}`, 신호당 합 112 고정) |
| `metering_price_trust_frac` | 이동 제약 아님 — 가격 FD 폭. SEG13 경로에선 **읽히지도 않음**(dead write) |
| 박스 영수증 | `wu_seg13_meter_box_r/edge/total`, `wu_seg13_vsl_box_r`, (비대칭시) `_rup` — **r 컬럼 부재 = 훅 불발 = 런 VOID** |

### 0.6 데이터 패키지 구조
```
data/<arm>/<cell>/{run_log.csv, control_timeseries.csv, state_timeseries.csv, decision_diagnostics.csv}
  arm ∈ { walk_mvg          — 최종 컨트롤러
        , farsa_ref         — ③(구 동결: PD 없음·박스 없음) — §5 비교 앵커
        , pd4_ref           — PD4(박스 없음) — 진동/190 손해의 원인 상태
        , box300_vsl10_ref  — 박스만(walk 없음) — walk ablation 짝 }
  cell ∈ 5 논문셀 + sweet_200_w
```

---

## §1. 거시 지표 표 (macro)

**표 1**: 5셀 × 컨트롤러 — wTTT, PFO 대비 개선%, 완주/잔존 대수, ATT, mean/max step
compute(s), 실시간(180s) 대비 비율.

- 컨트롤러 열: NC / WU-CD-F(문헌 Wu) / PFO / **walk-MVG** (+P-CENT 상한 병기 가능하면).
- **지금 데이터로 가능**: walk-MVG 열 전부(data/walk_mvg). compute는 run_log
  `computation_time_sec`(벽시계라 머신 의존 — 같은 머신 런끼리만 비교).
- **재실행 필요**: NC/WU-CD-F/PFO 풀런 × 5셀 (§6 목록). PFO는 수치 기준선으로 개선%만은
  지금도 계산 가능.
- 완주/잔존: state_timeseries 마지막 행의 네트워크 잔존 대수 + demand 총량에서 유도.
- 핵심 메시지(기존 유지): 계층 = 실시간 경계 내 + 권한 격차(metering)와 조정 격차 분리.

## §2. 메커니즘 (어떻게 개선하나)

컨트롤러별 "무엇을 해서 이득이 나는가"를 시계열로 분해. **이번 세션에서 이미 확보된
결정적 그림 3종**을 중심으로.

### 2a. metering 평활성 (박스의 존재 이유) — 그림
- PD4 vs walk-MVG, 190_w: 램프별 metering 시계열 겹쳐 그리기.
  PD4는 풀스팬 점프(|Δ|=1125, λ 점프 스텝에서 Σ|Δ|=2,218 = 총량의 45%),
  walk-MVG는 per-ramp |Δ| ≤ 300.
- 데이터: control_timeseries `ramp_metering_R_{D,F}_{E,W}`.
- 수치 곁들임: λ 점프 스텝(13개)의 Σ|Δ| 2,217.9 vs 평시 516.9 (pd4_ref 190_w에서 재현 가능
  — λ는 run_log `wu_faithful_lambda_P`).

### 2b. 200_w 회복 서사 (§5와 공유) — 그림
- ③ vs box300_vsl10 vs walk-MVG, 200_w: (i) Σmetering 시계열, (ii) 리더 intent
  (`leader_candidate_best_intent_N_UF_star`) 시계열, (iii) 누적 TTT 차이(vs ③).
- 확보된 수치: 회복기(step 40+) intent — ③ 5485→6000 / box300_vsl10 **3190 고착** /
  walk-MVG **5805→6000 (해방)**. TTT 발산은 전부 턴(step 40) 이후.
- 메시지: "채점 맹점은 walk로 고쳐짐(intent 해방), 잔여 손실은 rate limit의 물리
  (③는 턴에서 한 스텝 +2,400, 박스는 +300/step)".

### 2c. 레버별 이동 준수 감사 — 표
| 레버 | 명목 | ③ 실측 max|Δ|/step | walk-MVG 실측 |
|---|---|---|---|
| green | trust 6s | 6.00 (준수) | 6.00 |
| VSL | max_vsl_step 20 | **50 (2.5배 위반**, 10셀 112/7020) | **10.0** (VSL_BOX) |
| metering | (제약 부재) | 1125 (격자 전폭) | **300.0** |
- 재현: control_timeseries에서 per-step |Δ| max. VSL 위반 원인 = snapshot 앵커
  (sweep마다 재앵커) — §5 소재.

### 2d. 기존 계획 유지 항목
- NC vs 제어: 방류량 시계열·본선 밀도 궤적·capacity-drop 이력 (state_timeseries).
- 시나리오별 지배 메커니즘 지도: 중=재배분 / skew=공간이관 / incident=흡수보호 /
  고(190)=임계선 운영.

## §3. 가격 채널의 의미

### 3a. ★선형 가격 × 이산 후보 = bang-bang (이번 세션 핵심 발견 — 그림+표)
- **실측**(190_w, 160 램프×스텝, 박스 도입 전): 내부 rung 선택 **0/160**, 끝점 60~62%,
  나머지 38~40%는 예산 사영 산물. **"가격 부호 + → 최소, − → 최대" 적중 80~85%**.
- 원인: 팔로워 비용에 가격이 `g_m·(m−m_ref)` **1차**로 들어가 이산 격자에서 argmin이
  항상 끝점. 시간평균(~1,295/램프)은 내부값 = bang-bang이 내부 최적을 흉내.
- 재현 스크립트 골격: pd4_ref/farsa_ref의 control_timeseries에서 rung 분류
  {375,525,750,1050,1500} ±0.5 + run_log `wu_b3_meter_price_R_*` 부호 대조.
- **처방의 서사**: 외삽 제거(박스=측정폭 300) → walk(다중스텝 시야). 곡률 자체는 미도입
  (2차 자기항은 후속 과제 — 진행 중인 crossON/weight0.5 A/B 결과로 갱신할 것, §6).

### 3b. 채널 감사표 (기존 계획 유지 + 갱신)
- 5채널(green/metering/vsl/cross 2종) 소δ/대δ/행동/판정. 이미 확보: green 강함 /
  metering 영역구속→δ300 / vsl active / **cross 2종은 박스 위 재시험 진행 중**(§6).
- 가격의 물리적 의미(Weitzman/Roberts-Spence 3점: 가격 단독=나선, 수량 하한=안정화,
  하이브리드=회랑×δ) — 기존 서술 유지.

### 3c. ★dual 가격 감사 (신규 — §5와 공유)
- **③에서 λ_P·λ_UF 둘 다 항상 0** (비영 0/40): λ_UF는 mode 기본 "equality"라 갱신조차
  안 됨, λ_P는 corrector 실현-공간 잔차가 음수라 max(0,·)에 잘림. NP_OFF bit-identical
  10/10로 행동 확인.
- PD를 켜면 λ가 {0,10} bang-bang(400스텝 중간값 0) — gain 0.25 × 잔차 31.6~400 → 95%가
  한 방에 cap. **gain을 1.0으로 내리면(내부 dual) 오히려 파국**(평균 −5.32%) — "경계
  고착이 우연히 유익"이라는 정직한 보고.
- 실제 작동 조정 수단 = **N_UF hard budget + marginal price(58컬럼 전부 비영)**.
- 재현: run_log `wu_faithful_lambda_P`, `leader_lambda_uf_committed`, `wu_faithful_np_pd_exit`.

## §4. 네트워크 임계성 (기존 계획 유지, 셀만 교체)

### 4a. Leave-one-out (O(n))
- agent i 고정(no-control/fixed) → ΔwTTT. 21 agent × **5셀 = 105런**(hold: 이 컴퓨터
  가용 시간 나면 발주 — Stage3 ablation 인프라 재사용). 산출: 임계성 히트맵.
### 4b. Coupling flux Φ (기존 진단서 추출)
- Phi_{i→j} 방향 그래프, u→f 주채널 정량. decision_diagnostics에서 추출.

## §5. 한계와 메커니즘 검증 (신설 — 이번 세션의 핵심 자산)

리뷰어 선제 방어 절. 전부 측정 완료, data/에 재현 데이터 있음.

1. **dual 가격 inert** (§3c와 공유) — Stackelberg dual 기계장치는 플래그십에서 논다.
   설계의 기둥으로 서술 금지, "조정의 지도" 프레임(수량이 작동, 가격은 marginal 채널만)으로.
2. **200_w = rate limit의 물리적 비용** (§2b와 공유) — walk로 채점 맹점은 교정
   (intent 3190→5805 확증), 잔여 −20.7%는 +300/step 액추에이터 한계. 큰 up-jump 허용은
   측정 기각(up600/900: 파국 2셀→5셀 확산, 평균 −36~−40%).
3. **VSL rate limit은 원래 Jacobi 반복 단위였다** — 스텝당 최대 2.5×(50) 관측, VSL_BOX로
   교정. ③ 결과들엔 이 위반이 포함돼 있으나 전 구성 공유라 A/B는 무오염.
4. **리더 trust region 부재/우회** — 명목 반경 1500은 앵커 우회로 무효(후보 항상 전 범위
   [1200,6000]), 강제(STRICT)하면 파국(③기반 −19.99%, PD4기반 −32.31% — 2번 독립 확인).
   우회는 load-bearing. 리더는 크게 뛰어야 하고, 팔로워를 박스로 묶는 것이 옳은 분업.
5. **기각 계보 표** (전부 측정): gain1.0 / STRICT×2 / 구box300(VSL구멍) / up600 / up900 /
   walk-M(중단) / BUDGET_OFF(예산 제거 시 평균 −79%, hard budget은 필수 채널).
6. (선택) **오귀속 방법론 각주**: bit-identical은 훅 불발일 수 있다 — 플래그 A/B는 진단
   영수증으로 검증(BUDGET_OFF 20런 무효 사건).

## §6. 이 컴퓨터(런 머신)의 잔여 런 큐

| 우선 | 런 | 목적 | 규모 |
|---|---|---|---|
| ★1 | **NC × 5셀** (T=10800, WARM=20) | §1 표의 NC 열 | 5런, 빠름 |
| ★1 | **PFO 풀런 × 5셀** (`--controllers WU-FAITHFUL-FOLLOWER`, SEG13 금지!) | §1·§2 시계열 | 5런 |
| ★1 | **WU-CD-F × 5셀** | §1 문헌 비교 열 | 5런 |
| 2 | crossON / weight0.5 (진행 중, ~17:30) | §3a 처방 갱신 — 이기면 구성 재고 | 20런 |
| 3 | P-CENT × 5셀 | §1 중앙 상한 열 | 5런(느림) |
| 4 | leave-one-out 105런 | §4a | 하룻밤 |

★주의: PFO 기준선 런에 **SEG13을 주면 5배 악화**(1,791→8,906, 2026-07-16 실측) — 기준선
명령엔 SEG13 금지. 새 기준선은 기존 셀 수치로 재현 검증 후 사용.

## §7. 재현 명령 축약

```bash
# walk-MVG (최종)
BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 python ...
# ③ (비교 앵커)          : CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20
# PD4 (박스 없음)         : +NP_PD_ITER=4 NP_BIAS=1
# box300+vsl10 (walk 없음): +METER_BOX=300 VSL_BOX=10
```
코드 스냅샷: offiter repo `cross-gate` 브랜치, 커밋 e2d144b 이후 (METER_PRICE_W 훅 포함).
