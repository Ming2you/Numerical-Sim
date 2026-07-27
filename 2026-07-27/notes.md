# 2026-07-27 — 5/5(단, 리더 6스텝 조건) → ★조건 오류 발견·정정, 3v3 재출발

> ## ⚠️ 이 문서 아래 "5/5"는 **리더 6스텝 : PFO 3스텝** 조건이다 (공정 아님)
> **발견(2026-07-27 후반)**: `make_controller`의 ALLPRICE-JOINT 분기에 숨은 기본값이 있었다 —
> `LEADER_V_DEPTH`를 지정하지 않으면 `leader_value_depth`를 자동으로 3으로 올린다.
> 그래서 "depth를 건드리지 않는다"가 곧 **리더 rollout = horizon(3) + depth(3) = 6스텝**을
> 의미했고, PFO(3스텝)와의 비교는 동일 지평이 아니었다. 아래 5/5 표에 그 라벨을 붙인다.
> - 조치: 그 if문 **삭제**(사용자 지시). 이제 기본 `leader_value_depth=0` = 리더도 3스텝.
>   깊이가 필요하면 env로 **명시적으로만**. 단 depth=0이면 far/spillback 가산 게이트
>   (`depth>0 or far_at_d0`)가 닫히므로 터미널 항을 쓰려면 `FAR_D0=1` 동반 필요.
> - ★깊이 요인 분해(규칙 고정, 깊이만 변경):
>   | | 이산 규칙 | 연속 규칙 |
>   |---|---|---|
>   | 리더 6스텝 | **5/5** | 4/5 |
>   | 리더 3스텝 | **1/5** | 1/5 |
>   → **P-Stack 우위는 조정 규칙이 아니라 리더의 깊은 rollout에서 나왔다.**
> - 사용자 결정: **3 vs 3으로 확정**하고 그 조건에서 다시 만든다(6v6 비교는 폐기).

## (구) 결과 — 리더 6스텝 : PFO 3스텝 조건
**감독자(SUP_PFO) 미사용 · 예산(N_UF) 유지 · 새 메커니즘 추가 없음.**

| cell | PFO | PS4 base | **최종** | P-CENT | gap |
|---|---|---|---|---|---|
| Low(155) | 2961.1 | 2965.8 | **2948.3** | — | **−12.85 WIN** |
| Med(170) | 3862.3 | 3780.8 | **3754.6** | 3729.0 | **−107.75 WIN** |
| Skew(170skew) | 3834.6 | 3808.5 | **3795.4** | — | **−39.27 WIN** |
| Inc(170inc) | 5497.3 | 5825.7 | **5450.4** | 5498.4 | **−46.93 WIN** |
| High(190) | 5969.6 | 6131.1 | **5904.0** | 5598.8 | **−65.57 WIN** |

무결성: 5셀 81행(80스텝)·에러 0·t_max=14400·**감독자 활성 0**. 데이터 `outputs/_diag/FIN2_*`.
**Inc는 P-CENT 오라클(5498)보다도 우수.**

## 최종 설정 (AUTH_ADAPT 3-분기, 파라미터만)
```
공통: SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
      AUTH_ADAPT=1 AUTH_DEM_LOW=22500 AUTH_DEM_HIGH=23900
      AUTH_TRUST_BIG=6.0 AUTH_TRUST_SMALL=1.5
      (SUP_PFO 미사용, BUDGET_OFF 미사용)
분기별:
  교란(래치) : trust 1.5 · 가격 ON  · spillback WF 0    · budget_fair OFF
  적재(peak) : trust 6   · 가격 OFF · WF 0.20 · far_fw 0.5 · budget_fair ON
  저부하     : trust 6   · 가격 ON  · WF 1.0            · budget_fair OFF
래치 해제: freeway 밀도<ρ_crit AND urban 축적(protected+boundary)<400
런처: work/launch_final_r39.sh <cell...>   출력: outputs/_diag/FIN2_<cell>
```

## High 격차 축소 경과 (파라미터 튜닝만)
+161(base) → +2(가격off+spillback WF.25) → +0.57(BUDGET_FAIR) → +0.51(far_fw 0.5)
→ +0.17(far_fw0.5 × WF0.20) → **−1.20(OFFSET_PRICE=0)** → 최종 통합에서 −65.57

★마지막 관문을 뚫은 건 **`OFFSET_PRICE=0`**. 메모리에 "offset은 죽은 채널(‖가격‖~0.01)"로
기록됐던 채널인데, 격차가 0.17까지 좁혀지자 그 미세한 해악이 결정적이었다.
**교훈: 힘이 약해 무시하던 채널이 마지막 승부를 가른다.**

## ★코덱스 노선 배제 (측정 근거)
코덱스(다른 에이전트) 5/5를 내가 독립 재현 — 문서 수치와 **전 셀 오차 0.0**으로 일치
(Low −7/Med −100/Skew −7/Inc −198/High −153). PFO 기준선도 완전 동일(웜업 ~110 차감 차이뿐).
그러나 **그들 스택에서 BUDGET_OFF만 제거하면 0/5로 붕괴**(Low +81/Med +386/Skew +500/Inc +198/High +422).
→ 그들의 적응형 metering·N_P dual 튜닝은 **N_UF 예산이 없는 세계에서만 유효**. 예산 유지 요구와 양립 불가.
데이터: `2026-07-27/results/codex_budget_restored_0of5.txt`

## 기각 목록 (되풀이 금지)
- **LINK_SHARE=price**(가격이 링크 예산 배분): β 키울수록 단조 악화(+32→+335). 한계가격은 *비용*만
  담아서 편익 큰 링크까지 굶긴다. density 휴리스틱이 사실 편익 대리변수 역할을 하고 있었음.
- **BUDGET_OFF**: 내 아키텍처에선 파국(Inc +450 / High +275). 예산은 실제로 일을 하고 있음.
- **파라미터 정체 구간**: WU·nref·lead·GREEN_TRUST·PREFILTER_TOPK·NUF_RADIUS·OPT12·NASH_SMAX 등
  전부 bit-identical. 이유 — 3스텝 지평 안에서 **후보 간 urban 말단 상태가 거의 동일**(urban은 느림)
  → urban 계열 항은 상수처럼 작동해 판별력 없음. **freeway 계열만 판별력 있음**
  (SPILLBACK_WF, MFD_FAR_W_FREEWAY가 live였던 이유).
- hinge(+143), PRICE_ITER 2/3(+26/+174), RAMP_OFFSET=0(+58), GREEN_PRICE=0(+5.2), MERGE_DELTA 0.95(+108).

## 미해결 / 후속 확인 필요
- **Med의 분기 토글**: peak-seen 래치는 sticky로 설계했으나 Med 가격이 산발적으로 on/off
  (High는 설계대로 step23~61 OFF로 깨끗). FIN2 Med(3754.6)가 순수 적재분기(V_170 3765.1)·
  순수 저부하분기(U_170 3780.8) **둘 다보다 좋음** → 토글이 우연히 유리하게 작동 중일 가능성.
  분기 상태 로깅(loaded/prices)을 추가해 재확인 중(`outputs/_diag/dbg_med`).
  **결과가 토글에 의존한다면 재현성·설명력이 약하므로 반드시 규명할 것.**
- 재현 재실행(동일 설정 2회차)로 안정성 확인.
- 분기별 ablation 기여표(각 분기 파라미터의 단독 효과).

---

# ★3 vs 3 재출발 (2026-07-27 후반, 사용자 지정 조건)

리더도 3스텝(`LEADER_V_DEPTH=0`, 터미널 항 유지 위해 `FAR_D0=1`). PFO 3스텝. 감독자X · 예산O.

## 3v3 기준선 (적응규칙·spillback 전부 없음)
| cell | PFO@3 | 순수 P-Stack@3 (FAR_D0=1) | proxy 경로 | **내 튜닝@3** |
|---|---|---|---|---|
| Low | 2961.1 | +58.4 | +56.5 | **+25.4** |
| Med | 3862.3 | −20.9 | −20.9 | **−66.6 WIN** |
| Skew | 3834.6 | +14.4 | +14.4 | **+12.0** |
| Inc | 5497.3 | +631.2 | +316.2 | **+60.3** |
| High | 5969.6 | +493.1 | +493.1 | **+174.9** |

- 순수 기준선은 1/5. **spillback+적응규칙이 3스텝에서도 크게 기여**(Inc +316→+60, High +493→+175)
  하지만 아직 부족. 현재 3v3 성적 = **1/5** (Med만 승).
- 채점 경로: FAR_D0=1과 proxy가 Inc 빼고 동일. Inc는 proxy가 유리(+316 vs +631)
  → depth 0에서 far 항이 Inc에 해로움.
- 지금까지 쓴 파라미터는 **전부 depth-6 기준 최적값**이라 3스텝엔 부적합 → 재튜닝 진행 중.

## 3v3 튜닝 지침 (이번 세션 실측)
- 3스텝 지평 안에서 **후보 간 urban 말단 상태가 거의 동일**(urban은 느림) → urban 계열 항은
  상수처럼 작동해 **판별력 없음**. **freeway 계열(SPILLBACK_WF, MFD_FAR_W_FREEWAY)만 live.**
- 남은 격차 순: Skew +12.0 → Low +25.4 → Inc +60.3 → High +174.9. 가까운 것부터 뒤집는다.

## 코덱스 노선 배제 (측정)
코덱스 5/5를 독립 재현(문서와 오차 0.0). 그러나 **BUDGET_OFF만 제거하면 0/5로 붕괴**
(Low +81/Med +386/Skew +500/Inc +198/High +422) → 그들 튜닝은 예산 부재와 분리 불가.
데이터: `2026-07-27/results/codex_budget_restored_0of5.txt`

## 기각 목록
- LINK_SHARE=price(가격이 링크 배분): β↑일수록 단조 악화(+32→+335). 한계가격은 *비용*만 담아
  편익 큰 링크를 굶긴다. density 휴리스틱이 편익 대리변수 역할을 하고 있었음.
- BUDGET_OFF: 내 아키텍처에선 파국(Inc +450 / High +275).
- 연속 활성화의 **상태량 입력**(n_u): 내생 피드백에 갇힘 — 컨트롤러가 잘하면 활성화가 안 켜지고,
  안 켜지니 개선 못 함(High a_L 0.007~0.064 고착). → 외생 변수(예보 수요) 입력으로 교체.
- control-move penalty, hinge(+143), PRICE_ITER 2/3, RAMP_OFFSET=0, MERGE_DELTA 0.95.

## 미해결
- 3v3에서 5/5 달성 (진행 중).
- 이산 3분기는 분기=시나리오라 룩업테이블 성격 → **연속 활성화(지수형)로 재설계 중**
  (사용자 설계: 작을 땐 거의 0, 커지면 폭발). 견고성은 **미사용 시나리오 hold-out**으로 검증 필요
  (사용 가능: 140/160/200/220/240 및 155_incident/155_skew 등).
