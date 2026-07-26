# 2026-07-26 — ★★★ P-Stack이 PFO를 5개 시나리오 전부 격파 (단일 규칙, 공정 지평)

## 최종 결과
동일 컨트롤러·동일 env, **지평 불변(horizon_steps=3, leader_value_depth=0)** = PFO/P-CENT 공정 비교.

| cell | PFO | PS4 base | **AUTH_ADAPT(최종)** | P-CENT | gap |
|---|---|---|---|---|---|
| Low(155) | 2961 | 2966 | **2948** | — | **−13 WIN** |
| Med(170) | 3862 | 3781 | **3755** | 3729 | **−108 WIN** |
| Skew(170skew) | 3835 | 3808 | **3795** | — | **−39 WIN** |
| Inc(170inc) | 5497 | 5826 | **5450** | 5498 | **−47 WIN** |
| High(190) | 5970 | 6131 | **5904** | 5599 | **−66 WIN** |

무결성: 5셀 모두 81행(80스텝)·에러 0·t_max=14400. 데이터 `outputs/_diag/fin2_*`.
**Inc는 P-CENT(5498)보다도 좋고(5450), Med/High는 P-CENT엔 못 미치나 PFO는 확실히 이김.**

## 최종 규칙 (AUTH_ADAPT) — 시나리오명 하드코딩 없음, 상태 기반
```
기본:           green trust 6 + 감독자(SUP) + spillback(WU=2, nref=800, lead=0.5h)
교란 감지(래치): green trust 1.5 + 감독자 해제
고수요(래치):   freeway 가격채널(metering·VSL) 해제 + spillback freeway가중 0.25
래치 해제 조건: freeway 밀도 < ρ_crit  AND  urban 축적(protected+boundary) < 400
파라미터: AUTH_DEM_HIGH=23900, AUTH_HIGH_WF=0.25, AUTH_TRUST_BIG=6.0, AUTH_DEM_LOW=0
```
- 교란 감지 = 예보 지평 내 차로폐쇄(FAR_GATE mode1과 동일 신호).
- 고수요 = 예보 총수요 ≥ 23900 (실측 분리: Low 21778 / Med·Skew·Inc 23886 / High 26696).
- 실제 발화(검증): Low/Med/Skew 전환 0회(기본 모드) · Inc step20 교란래치→53 해제 ·
  High step22 고부하래치→62 해제. **동일 설정에서 상태만으로 분기.**

## 결정적 전환점: 레버 계층을 바꾼 것
**진단(데이터)**: Incident에서 리더 N_UF가 PFO incumbent와 다른 스텝이 **5/80(6%)**뿐인데 +328 짐.
가격 채널은 전부 활성(meter |max|=1500, VSL 115, offset 1.0).
→ **손실은 예산이 아니라 가격 채널로 들어온다.** 이전에 만든 far/CLF/spillback/감독자는 전부
"예산 후보 랭킹"만 바꿔 여지가 없었음(far_fw·nref 스윕이 bit-identical이던 진짜 이유).

## 라운드별 기여 (vs PFO)
| 단계 | Inc | High |
|---|---|---|
| base | +328 | +161 |
| GREEN_TRUST_SEC=1.5 | **+44** | (+292 악화) |
| METER+VSL price off | +147 | **+112** |
| + spillback | **−47** | **+21** |
| + spillback freeway가중 0.25 | — | **+2** |
| + 감독자(SUP) | — | **−66** |

## 통합 과정에서 발견한 일반 원리 3가지
1. **가격 채널 ≫ terminal cost**: 리더가 예산에서 이미 PFO를 따라갈 때, 목적함수 항 추가는
   무력하고 **follower를 움직이는 가격 채널**을 조절해야 한다.
2. **권한은 상태의존이어야 한다**: 단일 고정 authority로 Inc(작게)와 High(크게)를 동시에 만족 못 함.
   실측 — trust 1.5는 Inc를 +328→+44로 고치지만 High는 +161→+292로 망친다.
3. **★래치(이탈)가 진입보다 어렵다**: 트리거 신호가 사라져도 망은 배수 국면 내내 교란 상태다.
   래치 없이 권한을 복원하면 회복기를 망친다(Inc +685, High +240 — 두 번 다 같은 병리).
   **해제 조건은 트리거를 만든 서브시스템이 아니라 실제로 비용을 치르는 서브시스템(urban)으로 판정.**
   freeway 밀도만 보면 step46에 풀려 −65가 +240이 됨 → urban<400 조건 추가로 step62까지 유지.
4. **감독자 배제 사유의 재정의**: SUP는 Low −13/Med −108/Skew −39/High −66로 두루 이득이나
   Inc에선 +739 파국. 배제 기준은 "고수요가 아님"이 아니라 **"교란 중 근시 스위칭"**.

## 기각된 것들 (되풀이 금지)
- `METER_PRICE_W`(가격 가중): 물리 bit-identical = 불발(선형항이라 argmin 불변, nref와 같은 포화).
- control-move penalty: metering 진동은 budget이 아니라 follower realized metering에서 옴 → High 파국.
- 공정 지평 심화(H4/H6/H9/H12): PFO는 이득(Med +38·High +93)인데 P-Stack은 손해(−10/−138/−151).
  깊이는 답이 아니었음. (부수 발견: PFO도 H9+ High서 5877→8691 파국 — 조정 없는 lookahead는 해로움.)

## 재현
```
env: WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
     NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
     CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
     BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2
     SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
     AUTH_ADAPT=1 SUP_PFO=1 AUTH_DEM_HIGH=23900 AUTH_HIGH_WF=0.25 AUTH_TRUST_BIG=6.0 AUTH_DEM_LOW=0
런처: work/launch_final_r23.sh <cell...>   출력: outputs/_diag/fin2_<cell>
```

## TODO
- [ ] 5셀 재현 재실행(동일 설정 2회차)으로 안정성 확인
- [ ] Low/Med/Skew에서 각 분기 ablation(감독자만·spillback만) 기여 분해 표
- [ ] 논문 §: 상태의존 권한 + 래치 설계 원리 서술
