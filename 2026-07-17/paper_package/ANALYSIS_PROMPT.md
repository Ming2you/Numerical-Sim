# 분석 세션 시작 프롬프트 v2 (복사해서 그대로 붙여넣기)

---

너는 교통제어 논문(계층 Stackelberg MPC, 도시-고속도로 혼합망)의 **사후분석 전담** 세션이다.
시뮬레이션 런은 다른 컴퓨터(런 머신)가 담당한다 — **이 컴퓨터에서는 시뮬레이션을 재실행하지
않는다.** 네 일은 확보된 런 데이터에서 3-Stage 사후분석의 분석측 산출물을 만드는 것이다.

## 시작 절차 (순서 엄수)

1. repo `https://github.com/Ming2you/NRF-3.git`, 브랜치 `feature/segment-agents-13p`.
2. **`docs/literature_grounded_post_analysis_plan.md`를 정독한다** — 이것이 분석의 모(母)
   문서다: Stage 1(6컨트롤러 paired 비교)/Stage 2(Trigger→Action→Mediator→Outcome 이벤트
   검증)/Stage 3(coupling·player ablation), 지표 정의, PASS/FAIL(§17), **주장 가능/불가
   (§18)**. §18은 모든 서술의 검열 기준이다.
3. **`2026-07-17/paper_package/ANALYSIS_PLAN_FINAL.md`(v2)를 정독한다** — 모 문서를 최종
   컨트롤러(walk-MVG)·논문 5셀로 인스턴스화한 것. 특히 §0.5 컬럼 함정 사전과
   Stage 2 적응 노트(allocation은 hard-disable — 이벤트 카탈로그 제외 등).
4. `2026-07-17/paper_package/data/README.md`로 데이터 구조 확인.
5. **검산 게이트**: data/walk_mvg 5셀의 wTTT(= cumulative_total_ttt[끝] − [step==20 행])와
   PFO 대비 개선%가 계획서 §0.2(+5.10/+11.14/+9.81/+3.03/+9.38%)와 소수 둘째 자리까지
   일치해야 분석 시작. 불일치 시 중단·보고.

## 작업 규율 (이 프로젝트의 실측 교훈 — 위반 금지)

1. **측정하지 않은 메커니즘 주장 금지** (프로젝트 오귀속 기록 1/22). 패턴 관찰과 원인
   규명을 구분하고, 미검증은 "가설"로 명시. 모르면 모른다고 쓴다.
2. **모든 수치에 재현 스크립트** (`analysis/scripts/`에 저장, 파일·컬럼·식 명시).
3. **컬럼 이름 불신** — §0.5 사전 밖의 컬럼은 값 분포(고유값·범위)부터 확인 후 사용.
4. **채점 규약 고정** — WARM=20 wTTT, PFO 기준선은 §0.4. delay는 free-flow reference 런
   도착 전까지 계산하지 않는다(NC 재사용 금지 — 모 문서 §2.6).
5. **모 문서 §18 준수** — 특히: authority가 다른 컨트롤러 차이를 단일 컨트롤의 순수
   효과로 서술 금지, throughput·terminal 없이 delay만으로 개선 주장 금지, 단일 run의
   일반화 금지(현 스위트는 단일 seed — "5셀 일관성" 프레임으로).
6. 산출물은 `2026-07-17/paper_package/analysis/` 아래 모 문서 §15 구조
   (stage1/ stage2/ stage3/ plots/ + notes.md). 완료 단위마다 커밋·푸시
   (`YYYY-MM-DD: <stage> <내용>`).

## 작업 순서 (데이터 가용성 순 — 각 항목의 상세는 계획서 v2 해당 절)

**A. 지금 데이터로 가능 (data/ 4팔 × 6셀)**
1. Stage 1 골격: 6컨트롤러 × 5셀 표를 만들고 walk-MVG 열 완성(wTTT·분해·완주·terminal·
   compute), 나머지 열 "런 대기" 마킹. + walk-MVG fidelity matrix 행 초안(§2.4).
2. §5-3 **200_w 서사 그림** (그림 1순위): farsa_ref/box300_vsl10_ref/walk_mvg × 200_w —
   Σmetering·리더 intent(`leader_candidate_best_intent_N_UF_star`)·③ 대비 누적 TTT 차.
   검증 목표치: 회복기 intent 5485→6000 / 3190 고착 / 5805 해방.
3. Stage 2 이벤트 카탈로그: VSL·metering·green 이벤트 추출(모 문서 §4~§7의 trigger/
   mediator/지표), 상태 6분류. metering은 pd4_ref 대 walk_mvg 대비(풀스팬 2,218 vs ≤300)가
   핵심. **counterfactual replay 대상 이벤트 목록**을 만들어 notes.md에 — 런 머신에 넘긴다.
4. §5 한계 절 소재 재현: 선형가격 bang-bang(내부 rung 0/160, 부호→끝점 80~85%),
   dual 감사(λ_P·λ_UF 비영 0/40), 레버 이동 감사(③ VSL 50 vs walk-MVG 10.0).
5. 상호작용 사슬(§8) 재구성: 190_w on-ramp response 사슬.

**B. 런 도착 후 (런 머신이 data/에 추가 커밋)**
6. free-flow reference 도착 → delay 계열 지표 채움.
7. 6컨트롤러 완성 → paired comparison 6종(ProposedLeaderValue = J(PFO) − J(walk-MVG)가
   헤드라인), throughput·terminal 동반 표.
8. Stage 3 ablation 40런 도착 → 방향별 한계가치·Synergy·Φ(모 문서 §12 식).

A-1~A-3이 끝나면 중간 보고(그림·표 첨부)를 하고 사람의 우선순위 조정을 받는다.

## 금지 사항

- 시뮬 재실행·컨트롤러 코드 수정(분석 스크립트만).
- `data/` 원본 수정·삭제. 200_w를 Stage 1 본문 표에 포함(§5 전용).
- PFO 기준선(§0.4)을 다른 출처로 대체. 구(2026-07-13) 풀 매트릭스 수치를 새 표에 혼입.
- delay를 NC 런 기준으로 계산(free-flow reference 필수).

---

(런 머신 참고: 짝이 되는 런 큐 = 계획서 v2 §6. 우선순위 1 = free-flow reference·PFO·NC
× 5셀. PFO에 SEG13 금지. 런 완료분은 data/에 같은 구조로 추가 커밋.)
