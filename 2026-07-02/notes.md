# 2026-07-02 작업 노트 — finding #3/#5 수정 + λ-dual 병리 진단·수정(A1+A2)

## 1. Finding #3/#5 수정 (커밋 acd16e9, Codex 3c171ce와 합류)

- **Finding #3** (freeway agent 로컬 모델의 reservoir arrival/release 순서): 내가 수정을 준비하는 사이
  Codex가 원격(3c171ce)에서 독립적으로 동일 진단·동일 수정을 먼저 푸시했다. rebase에서 원격 버전 채택,
  내 중복 커밋은 드롭. 차이는 release 차감 시점뿐(포화 근처 2차 효과)이고 핵심(유입 적재 전 release 결정)은 동일.
- **Finding #5** (P-Stack leader prefilter action-blind): `StackelbergWuMeteredController._proxy_score_candidate`
  오버라이드 신설 — N_UF_star를 follower hard-budget 규칙(ω_F·N_UF, 용량비례)대로 metering에 투영 후
  `_predict`(plant rollout)로 후보-의존 채점. 수정 전 전 후보 proxy 동점(index순 통과) → 수정 후
  objective spread 0.09~9.06. 한계: N_P(λ) 차원은 여전히 proxy가 근사하지 않음.
- 신규 판별 테스트 2건: HEAD에서 정확히 버그 신호로 실패, 수정 코드에서 통과(독립 재현 완료).
- 코딩/검증 에이전트 분리 수행. 검증 에이전트가 세션 토큰 한도로 중단됐으나 디스크 산출물
  (outputs/_finding35_verify)과 내 직접 재현으로 검증 완결.

## 2. λ-dual 메커니즘 병리 진단 (P-Stack, 3 시나리오 × 3600s)

배경: "leader budget을 follower에 강제하는 λ항 때문에 follower가 잘못 작동하는 게 아닌가"(사용자 가설).
GNE 검토 결과 현행 λ-dual이 이미 variational GNE 계산법이므로, hard-slice 전환(옵션 B) 대신
확장성(1-D 가격, n-무관)을 보존하는 dual 수리(A1+A2)로 방향 결정. 진단 스크립트:
scratchpad/diag_lambda.py (solve 가로채기 + Jacobi/이분법/commit sweep 호출 스트림 분석).

수정 전 실측(dual solve = leader 후보 평가 단위):

| | sweet_128 | sweet_155 | bal_med |
|---|---|---|---|
| λ<0 발동률 | 21/62 (34%) | 22/62 (35%) | 26/63 (41%) |
| commit sweep green flip | 59/62 solve | 54/62 | 52/63 |
| flip 규모(green 초) 중앙값 | 30.0 | 30.0 | 30.0 |

- **(i) 음수 λ**: b0d9737의 signed equality 추적이 원인. target>자연유입이면 λ<0으로 follower가
  보호구역 유입을 늘리도록 보상받고, Σnin(λ)이 계단함수라 target을 평균 67~89 veh/h **초과**(overshoot).
- **(iii) off-equilibrium commit**: λ*를 수렴 후 이분법으로 찾고 1회 재해로 green을 커밋 —
  coupling 재수렴 없음. 합의 green을 중앙값 30초(총 112초의 27%)씩 뒤집은 채 커밋.

## 3. A1+A2 수정 (이 커밋)

- **A1**: 음수 λ 금지 — `_bisect_lambda_for_np` 전체 삭제(음수 분기 포함).
- **A2**: step 내 이분법·commit sweep 폐지 → **λ를 control step 간 적분 갱신**으로 전환.
  `_lambda_np_update`: λ_next = clip(λ + 0.01·(Σnin − projected_target), 0, 10.0).
  green은 Jacobi 합의값 그대로 커밋. anti-windup은 기존 `_np_feasible_range` 투영 재사용.
- **λ 오염 방지**: solve() 내 `self._lambda_P` 영속 갱신 삭제(P-Stack이 step당 후보마다 solve를
  부르므로). λ_next는 diagnostics(`wu_faithful_lambda_next`)로만 노출, **선택된 후보의 것만**
  `_select_with_fallback_guard`에서 commit. PFO incumbent 선택 시 λ 동결(plant 무영향, 새 정보 없음).
- 신규 테스트 3건(비음수·cap·방향 / commit green==합의 sweep / solve의 λ 불변) 통과.
- 회귀: six_controller+constraints 127 tests 중 실패 9건은 HEAD 스냅샷에서도 동일(전부 기존 stale
  테스트, 이번 변경 기인 0건).

## 4. 수정 후 재측정 (3 시나리오 × 3600s)

| | sweet_128 | sweet_155 | bal_med |
|---|---|---|---|
| 음수 λ / flip | **0 / 0** | **0 / 0** | **0 / 0** |
| λ>0 solve | 0 | 44/63 | 55/62 |
| TTT before→after | 737.2→742.2 (+0.7%) | 1385.3→1398.2 (+0.9%) | 917.1→921.8 (+0.5%) |
| \|Σnin−target\| 평균 | 29.0→31.5 | 37.8→117.9 | 21.7→135.2 |
| PFO 선택(20 step) | 20 (tie-break 20) | 17 (tie-break 4) | 19 (tie-break 1) |
| leader 후보 선택/λ 커밋 | 0 | 3 | 1 |
| step당 시간 | ~25s → **14.6s (−42%)** | | |

## 5. 해석 (중요)

1. **병리는 완전 소멸, 성능은 중립~미세 악화(+0.5~0.9%)**. 이유: λ 병리는 대부분 후보 "평가"를
   오염시켰을 뿐, PFO tie-break guard가 오염된 leader 후보를 기각해 plant까지는 거의 도달하지
   않았었다. 즉 guard가 병리를 격리하고 있었던 것.
2. tracking 잔차 증가(117~135 veh/h)는 적분 갱신의 설계된 지연 — 단 음수 λ의 강제 유입 overshoot와
   달리 "λ=0에서 자연 유입 vs 투영 target"의 무해한 격차가 대부분.
3. **다음 병목이 명확해짐**: leader 후보가 이제 가끔 tie-break을 뚫는데(sweet_155 3/20) 실현 TTT는
   미세 악화 — leader의 full 평가(follower 응답 예측 + objective)가 실제 plant와 어긋나 있다는 뜻.
   λ 메커니즘이 아니라 **leader 평가 충실도**가 남은 문제. finding #4 때 확인한 "모델-공간 비교의
   한계"와 같은 뿌리.
4. 계산 이득(-42%/step)과 확장성 확보(1-D 가격 유지, 등식→complementarity)는 그 자체로 가치.

## 6. TODO

- leader full 평가 충실도 조사(모델-공간 vs plant-공간 순위 비교) — 남은 병목.
- 혼잡 시나리오에서 λ 적분 dynamics 관찰(gain 0.01 적정성) — sweet_155/bal_med에서 λ>0가
  70~89% solve에서 활성인 건 확인, 수렴 궤적은 미분석.
- green-metering ablation(사용자 제안: metering 없이 green으로 metering 재현) — 대기 중.
- tie-break 기각률·제어강도(선제 metering) 측정 — leader 가치 스토리용.
