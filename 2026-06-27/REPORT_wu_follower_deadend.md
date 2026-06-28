# [리포트] 경량 분해 follower 시도 — 의미 없음(원복 완료)

작성 2026-06-27. 결론부터: **proposed Stackelberg의 follower를 경량 분해로 바꾸는 시도는 n=7에서 의미가
없었다. 관련 코드는 전부 원복**했고(아래 "원복 범위"), 이 문서만 기록으로 남긴다.

## 동기
`PROPOSED-STACKELBERG`(leader + `DistributedCoordinator` follower)가 느림(sweet_128, T=1440 기준 ~1964s).
follower가 후보마다 full-coupled 전역 rollout이라 비싸다고 보고, Wu(2022)식 국소분해로 O(n) follower를
만들면 빨라질 것이라 가정했다.

## 전제부터 틀렸음
비교군 `WU-CD-F`(19.45%@82s)가 "경량 Wu 분해"라고 알고 있었으나, 어댑터 실측 결과
**`WU-CD-F = DistributedCoordinator(ablation="WU_GREEN_VSL_ONLY_TTT")`(중량 full-coupled)** 였다.
진짜 경량 분해(`WuDistributedController`)는 `WU-MATCHED`만 쓰고, 그건 0%(무력)다.

## 시도와 결과 (전부 하네스 실측)
| 방식 | green 56 탈출 | 개선율 | 속도 |
|---|---|---|---|
| 경량 집계모델 그대로(`WuDistributedController`) | ✗(전구간 56/56) | 0% | 빠름 |
| + 하류 저장(spillback) cap | ✗ | 0% | 빠름 |
| 후보를 urban-only real plant로 채점 | D/F만 | **−0.5%** | ~2.2× 빠름 |
| 후보를 full-coupled real plant로 채점 | (T짧아 미검출) | ~0% | **원본과 동급(이득 0)** |

### 왜 각각 실패했나
- **집계모델 56/56**: phase를 집계 큐 하나로 보고 균일 포화유율 사용 → 대칭 sat·고수요 포화에서
  throughput이 green-split에 무관 → 목적함수가 평평 → smoothness가 split을 prev=56(=total/2)에 고정.
- **spillback cap 무효**: cap이 binding 안 함(하류 가용저장 833 ≫ 1스텝 discharge 196; 차량이 교차로
  점큐가 아니라 link storage(이동중)에 쌓임). 집계모델은 패치로 못 살린다.
- **urban-only real plant −0.5%**: 실제 plant로 채점하니 퇴화는 깨지나(D/F 이동), freeway 결합 가치를
  못 봐 중심신호(A/B/C)가 무동작 → 부분제어가 오히려 약간 해롭다.
- **full-coupled real plant 무이득**: 결합을 유지하면 품질은 보존되지만 per-eval 비용이 원본과 같아
  속도 이득이 사라진다. 후보수만 225 vs 300(−25%)이고 leader가 ×24로 곱해 체감 무이득.

## 핵심 교훈(왜 의미 없었나)
1. **follower의 가치는 결합(urban↔freeway)에 있다.** 결합을 빼고 채점하면 빨라지지만 가치를 잃고,
   결합을 유지하면 가치는 남지만 안 빨라진다 — 공짜 점심 없음.
2. **n=7은 분해이득을 보기엔 너무 작다.** 분해의 O(n)는 큰 n에서만 joint의 상수항을 이긴다. 점근적
   이득은 이미 이론 그림 `reports/figures/fig_scaling_centralized_vs_pstack.png`이 담당한다(논문 서사 확보됨).
3. **n=7에서 실제 속도 lever는 follower가 아니라 leader다.** `WU-CD-F`(follower 단독)=82s vs
   `PROPOSED-STACKELBERG`(leader+같은 follower)=1964s. 24× 차이는 leader가 후보마다 full follower를
   호출해서다. 빠르게 하려면 leader candidate 평가를 캐싱/coarse 사전필터/warm-start로 줄여야 한다
   (검증된 23.88%는 유지).

## 원복 범위 (이번에 되돌린 코드)
- 삭제: `src/controllers/wu_style_follower.py`.
- 원복(6306690이 추가한 wu_style 분량 제거, 6306690^과 일치 확인):
  `src/analysis/authority.py`, `src/controllers/stackelberg_mpc.py`(`wu_style` 모드),
  `src/experiments/six_controller_comparison.py`(`PROPOSED-STACKELBERG-WU` 어댑터),
  `src/models/state.py`(validation), `src/controllers/wu_distributed.py`(WU-MATCHED TTT-선택 시도 — 0%라 무효).
- **보존(정상 작업)**: scaling 이론 그림·스크립트, fallback guard 수정·Layer1 출력폐쇄, sweet 시나리오/capacity-drop config.

## 다음(필요 시)
leader candidate 평가 비용 절감으로 P-Stack 속도 개선(검증된 23.88% 유지). follower 분해는 큰 n 스케일링
실증이 필요할 때만 별도로.
